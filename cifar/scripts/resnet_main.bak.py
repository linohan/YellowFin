# Copyright 2016 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

"""ResNet Train/Eval module.
"""
import time
import sys

import cifar_input
import numpy as np
import resnet_model
import tensorflow as tf

FLAGS = tf.app.flags.FLAGS
tf.app.flags.DEFINE_string('dataset', 'cifar10', 'cifar10 or cifar100.')
tf.app.flags.DEFINE_string('mode', 'train', 'train or eval.')
tf.app.flags.DEFINE_string('train_data_path', '',
                           'Filepattern for training data.')
tf.app.flags.DEFINE_string('eval_data_path', '',
                           'Filepattern for eval data')
tf.app.flags.DEFINE_integer('image_size', 32, 'Image side length.')
tf.app.flags.DEFINE_string('train_dir', '',
                           'Directory to keep training outputs.')
tf.app.flags.DEFINE_string('eval_dir', '',
                           'Directory to keep eval outputs.')
tf.app.flags.DEFINE_integer('eval_batch_count', 50,
                            'Number of batches to eval.')
tf.app.flags.DEFINE_bool('eval_once', False,
                         'Whether evaluate the model only once.')
tf.app.flags.DEFINE_string('log_root', '',
                           'Directory to keep the checkpoints. Should be a '
                           'parent directory of FLAGS.train_dir/eval_dir.')
tf.app.flags.DEFINE_integer('num_gpus', 0,
                            'Number of gpus used for training. (0 or 1)')


def train(hps):
  """Training loop."""
  images, labels = cifar_input.build_input(
      FLAGS.dataset, FLAGS.train_data_path, hps.batch_size, FLAGS.mode)
  model = resnet_model.ResNet(hps, images, labels, FLAGS.mode)
  model.build_graph()

  param_stats = tf.contrib.tfprof.model_analyzer.print_model_analysis(
      tf.get_default_graph(),
      tfprof_options=tf.contrib.tfprof.model_analyzer.
          TRAINABLE_VARS_PARAMS_STAT_OPTIONS)
  sys.stdout.write('total_params: %d\n' % param_stats.total_parameters)

  tf.contrib.tfprof.model_analyzer.print_model_analysis(
      tf.get_default_graph(),
      tfprof_options=tf.contrib.tfprof.model_analyzer.FLOAT_OPS_OPTIONS)

  truth = tf.argmax(model.labels, axis=1)
  predictions = tf.argmax(model.predictions, axis=1)
  precision = tf.reduce_mean(tf.to_float(tf.equal(predictions, truth)))

  # hook variable to change lr online
  lr_val = hps.lrn_rate
  mom_val = hps.mom
  class _LearningRateSetterHook(tf.train.SessionRunHook):
    """Sets learning_rate based on global step."""

    def begin(self):
      self._lrn_rate = lr_val
      self._mom = mom_val
      self._clip_norm = hps.clip_norm_base / self._lrn_rate

    def before_run(self, run_context):
      return tf.train.SessionRunArgs(
          model.global_step,  # Asks for global step value.
          feed_dict={model.lrn_rate: self._lrn_rate,
                     model.mom: self._mom,
                     model.clip_norm: hps.clip_norm_base / self._lrn_rate})  # Sets learning rate

    def after_run(self, run_context, run_values):
      self._lrn_rate = lr_val
      self._mom = mom_val
      print "test lr and mu ", lr_val, mom_val
      # train_step = run_values.results
      # if train_step < 40000:
      #   self._lrn_rate = 0.1
      # elif train_step < 60000:
      #   self._lrn_rate = 0.01
      # elif train_step < 80000:
      #   self._lrn_rate = 0.001
      # else:
      #   self._lrn_rate = 0.0001

  iter_id = 0
  loss_list = []
  with tf.train.MonitoredTrainingSession(
      checkpoint_dir=FLAGS.log_root,
      # hooks=[logging_hook, _LearningRateSetterHook()],
      hooks=[_LearningRateSetterHook(), ],
      # chief_only_hooks=[summary_hook],
      # Since we provide a SummarySaverHook, we need to disable default
      # SummarySaverHook. To do that we set save_summaries_steps to 0.
      save_summaries_steps=0,
      config=tf.ConfigProto(allow_soft_placement=True, log_device_placement=True)) as mon_sess:
    start_time = time.time()
    # while not mon_sess.should_stop():
    while iter_id < 201:
      if iter_id % 50 == 0 and iter_id != 0:
        end_time = time.time()
        print("elapsed time: ", end_time - start_time)
        start_time = time.time()
      output_results = mon_sess.run( [model.train_op, model.cost] )
      loss_list.append(output_results[-1] )
      end_time = time.time()
      if iter_id % 100 == 0 and iter_id != 0:
        np.savetxt("loss_orig.txt", np.array(loss_list) )
      print("iter ", iter_id, " loss: ", output_results[-1] )
      iter_id += 1


def evaluate(hps):
  """Eval loop."""
  return None


def main(_):
  if FLAGS.num_gpus == 0:
    dev = '/cpu:0'
  elif FLAGS.num_gpus == 1:
    dev = '/gpu:0'
  else:
    raise ValueError('Only support 0 or 1 gpu.')

  if FLAGS.mode == 'train':
    batch_size = 128
  elif FLAGS.mode == 'eval':
    batch_size = 100

  if FLAGS.dataset == 'cifar10':
    num_classes = 10
  elif FLAGS.dataset == 'cifar100':
    num_classes = 100

  hps = resnet_model.HParams(batch_size=batch_size,
                             num_classes=num_classes,
                             min_lrn_rate=0.0001,
                             lrn_rate=0.1,
                             mom=0.9,
                             clip_norm_base=1000.0,
                             num_residual_units=5,
                             use_bottleneck=False,
                             weight_decay_rate=0.0002,
                             relu_leakiness=0.1,
                             optimizer='mom',
                             model_scope='train')

  with tf.device(dev), tf.variable_scope('train'):
    if FLAGS.mode == 'train':
      train(hps)
    elif FLAGS.mode == 'eval':
      evaluate(hps)


if __name__ == '__main__':
  tf.app.run()

# python resnet/resnet_main.py --train_data_path=cifar10/data_batch* --log_root=./tmp/resnet_model --train_dir=./tmp/resnet_model/train --dataset='cifar10'
# python resnet/resnet_main.py --train_data_path=cifar10/data_batch* --log_root=./tmp/resnet_model --train_dir=./tmp/resnet_model/train --dataset='cifar10' --num_gpus=1
