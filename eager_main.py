# coding:utf-8
import tensorflow as tf
import model
import input_data
tf.enable_eager_execution()

# model
depth = 10
height = 80
wigth = 200
chennel = 1

rnn_units = 64
num_class = 4

learning_rate = 0.05
batch_size = 64
epoch = 6
display_step = 1

logs_path = 'tensor_logs/'
path = 'sounds/'
fuckdata = input_data.input_data(train_file_dir=path, depth=depth, height=height, width=wigth, num_class=num_class)


def cal_loss(logits, lab_batch):
    cross_entropy = tf.nn.softmax_cross_entropy_with_logits_v2(labels=lab_batch, logits=logits)
    loss = tf.reduce_mean(cross_entropy)
    return loss


t3lm = model.The3dcnn_lstm_Model(rnn_units=rnn_units, num_class=num_class)

step = 1
while step * batch_size < 9999:
    batch_x, batch_y, epoch_index = fuckdata.next_batch(batch_size=batch_size, epoch=epoch)
    learning_rate = 0.05/(1+0.57*(epoch_index-1))
    if epoch_index > epoch:
        t = True
        d_rate = 0.3
    else:
        t = False
        d_rate = 0

    with tf.GradientTape() as tape:
        logits = t3lm.call(batch_x, training=t, drop_rate=d_rate)
        loss = cal_loss(logits, batch_y)

    optimizer = tf.train.GradientDescentOptimizer(learning_rate=learning_rate)
    grads = tape.gradient(loss, t3lm.variables)
    optimizer.apply_gradients(zip(grads, t3lm.variables))

    correct_pred = tf.equal(tf.argmax(logits, 1), tf.argmax(batch_y, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

    print('loss:{:.3f}, acc:{:.3f}, lr:{:.4f}'.format(loss, accuracy, learning_rate))
