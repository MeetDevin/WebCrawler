import tensorflow as tf
import numpy as np
import bl_data

tf.enable_eager_execution()


class XNN(tf.keras.Model):

    def __init__(self, num_class, rnn_units):
        super(XNN, self).__init__()
        self.num_class = num_class
        self.rnn_units = rnn_units

        self.conv1 = tf.keras.layers.Conv2D(
            filters=4, kernel_size=[9, 9], strides=[1, 1], use_bias=True, activation=tf.nn.relu, padding='same',
            kernel_initializer=tf.keras.initializers.constant(value=1), bias_initializer=tf.zeros_initializer())
        self.pooling1 = tf.keras.layers.MaxPooling2D(pool_size=[2, 2], strides=[2, 2], padding='same')
        self.gap = tf.keras.layers.AveragePooling2D(pool_size=[40, 100], strides=[40, 100], padding='same')

        self.conv2 = tf.keras.layers.Conv2D(
            filters=16, kernel_size=[3, 3], strides=[1, 1], use_bias=True, activation=tf.nn.relu, padding='same',
            kernel_initializer=tf.keras.initializers.constant(value=1), bias_initializer=tf.zeros_initializer())
        self.pooling2 = tf.keras.layers.MaxPooling2D(pool_size=[2, 2], strides=[2, 2], padding='same')

        self.conv3 = tf.keras.layers.Conv2D(
            filters=8, kernel_size=[3, 3], strides=[1, 1], use_bias=True, activation=tf.nn.relu, padding='same',
            kernel_initializer=tf.keras.initializers.constant(value=1), bias_initializer=tf.zeros_initializer())
        self.pooling3 = tf.keras.layers.MaxPooling2D(pool_size=[2, 2], strides=[2, 2], padding='same')

        self.cell = tf.keras.layers.CuDNNLSTM(units=self.rnn_units)
        self.fc = tf.keras.layers.Dense(units=self.num_class, use_bias=True, activation=None,
                                        kernel_initializer=tf.keras.initializers.he_normal(),
                                        bias_initializer=tf.constant_initializer())

    def call_filter(self, input):
        conv1 = self.conv1(input)
        # conv1 = tf.layers.batch_normalization(conv1, training=True)
        pool1 = self.pooling1(conv1)  # (?, 40, 100, 4)
        gap = self.gap(pool1)  # (?, 4)

        return pool1.numpy(), gap.numpy()

    def call_recognizer(self, input):
        input = tf.cast(input, dtype=tf.float32)

        conv2 = self.conv2(input)
        conv2 = tf.layers.batch_normalization(conv2, training=True)
        pool2 = self.pooling2(conv2)  # (?, 20, 50, 16)
        conv3 = self.conv3(pool2)
        conv3 = tf.layers.batch_normalization(conv3, training=True)
        pool3 = self.pooling3(conv3)  # (?, 10, 25, 8)

        x_rnn = tf.transpose(pool3, [0, 2, 1, 3])  # [?, 25, 10, 8]
        x_rnns = tf.unstack(x_rnn, axis=-1)  # 展开通道维度
        x_rnn = tf.concat(x_rnns, axis=-1)  # 合并列维度 [?, 25, 80]

        rnn_out = self.cell(x_rnn)
        logits = self.fc(rnn_out)
        return logits

    def windows(self, length, window_size):
        start = 0
        while start < length:
            yield start, start + window_size
            start += int(window_size)

    def call(self, inputs, **kwargs):
        """
        :param inputs: list类型，(?, 80, width, 1), 每个元素具有不一样的width
        :param kwargs:
        :return: 模型输出
        """
        batch_features = []
        batch_filter_gap = []
        window_size = 200

        for img in inputs:  # (80, width, 1)
            shape = np.shape(img)
            best_feature = None
            best_gap = None
            max_score = 0

            for (start, end) in self.windows(shape[1], window_size=window_size):
                signal = img[:, start:end]  # (80, ,<=200, 1)

                if np.shape(signal)[1] == window_size:
                    signal = np.expand_dims(signal, axis=0)  # 添加batch_size维度 (1, 80, 200, 1)
                    signal = tf.cast(signal, dtype=tf.float32)
                    cnn_out,  gap = self.call_filter(signal)  # 调用cnn (1, 40, 100, 4), (1,1,1, 4)
                    cnn_out = np.squeeze(cnn_out, axis=0)  # 删除batch_size维度 (40, 100, 4)
                    gap = np.squeeze(gap)  # 删除长度是1的维度 (4, )

                    he = sum(gap)
                    if he >= max_score:
                        max_score = he
                        best_feature = cnn_out
                        best_gap = gap
            pass
            batch_features.append(best_feature)  # (?, 10, 25, 8)
            batch_filter_gap.append(best_gap)  # (?, 4)

        # 调用rnn
        logits = self.call_recognizer(batch_features)

        return logits, batch_filter_gap


# model
depth = 10
height = 80
wigth = 200
chennel = 1

rnn_units = 128
num_class = 4

batch_size = 32
epoch = 6
display_step = 1

dd = bl_data.batch_generator(file_dir='yield/images', num_class=num_class)
xnn = XNN(num_class=4, rnn_units=128)


def my_learning_rate(epoch_index, step):
    if epoch_index == 0:
        return 0.00001
    else:
        return 0.05 * (0.5**(epoch_index-1)) / (1 + step * 0.01)


def cal_loss(logits, batch_filter_gap, lab_batch):
    cross_entropy = tf.nn.softmax_cross_entropy_with_logits(labels=lab_batch, logits=logits)
    loss = tf.reduce_mean(cross_entropy)

    cross_entropy_filter = tf.nn.softmax_cross_entropy_with_logits(labels=lab_batch, logits=batch_filter_gap)
    loss_filter = tf.reduce_mean(cross_entropy_filter)
    return 0.2*loss_filter + loss


step = 1
while step * batch_size < 99999:
    batch_x, batch_y, epoch_index = dd.next_batch(batch_size=batch_size, epoch=epoch)
    lr = my_learning_rate(epoch_index, step)
    if epoch_index == 0:
        d_rate = 0
    else:
        d_rate = 0.3

    with tf.GradientTape() as tape:
        logits, batch_filter_gap = xnn.call(batch_x)
        loss = cal_loss(logits, batch_filter_gap, batch_y)

    optimizer = tf.train.AdamOptimizer(learning_rate=lr)
    grads = tape.gradient(loss, xnn.variables)
    optimizer.apply_gradients(zip(grads, xnn.variables))

    correct_pred = tf.equal(tf.argmax(logits, 1), tf.argmax(batch_y, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

    print('epoch_index:{}, loss:{:.3f}, acc:{:.3f}, lr:{:.4f}'.format(epoch_index, loss, accuracy, lr))
