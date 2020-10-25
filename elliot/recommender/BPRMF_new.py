from recommender.RecommenderModel import RecommenderModel
from recommender.Evaluator import Evaluator
from utils.read import find_checkpoint
from utils.write import save_obj
from config.configs import *
from copy import deepcopy
from time import time
from abc import ABC
import tensorflow as tf


class BPRMF(RecommenderModel, ABC):
    def __init__(self, data, params):
        """
        Create a BPR-MF instance.
        (see https://arxiv.org/pdf/1205.2618 for details about the algorithm design choices).

        Args:
            data: data loader object
            params: model parameters {k: embedding size,
                                      [l_w, l_b]: regularization,
                                      optimizer: training optimizer (with its parameters)}
        """
        super(BPRMF, self).__init__(data, params)
        self.k = self.params.k
        self.l_w = self.params.l_w
        self.l_b = self.params.l_b

        self.evaluator = Evaluator(self, data, params.k)

        # Initialize Model Parameters
        initializer = tf.initializers.GlorotUniform()
        self.Bi = tf.Variable(tf.zeros(self.num_items), name='Bi', dtype=tf.float32)
        self.Gu = tf.Variable(initializer(shape=[self.num_users, self.k]), name='Gu', dtype=tf.float32)
        self.Gi = tf.Variable(initializer(shape=[self.num_items, self.k]), name='Gi', dtype=tf.float32)

        self.optimizer = tf.optimizers.Adam(self.params.lr)
        self.saver_ckpt = tf.train.Checkpoint(optimizer=self.optimizer, model=self)

    def call(self, inputs, training=None, mask=None):
        """
        Generates prediction for passed users and items indices

        Args:
            inputs: user, item (batch)
            training: Boolean or boolean scalar tensor, indicating whether to run
            the `Network` in training mode or inference mode.
            mask: A mask or list of masks. A mask can be
            either a tensor or None (no mask).

        Returns:
            prediction and extracted model parameters
        """
        user, item = inputs
        beta_i = tf.nn.embedding_lookup(self.Bi, item)
        gamma_u = tf.nn.embedding_lookup(self.Gu, user)
        gamma_i = tf.nn.embedding_lookup(self.Gi, item)

        xui = beta_i + tf.tensordot(gamma_u, gamma_i, axes=[[1], [1]])

        return xui, beta_i, gamma_u, gamma_i

    def predict_all(self):
        """
        Get full predictions on the whole users/items matrix.

        Returns:
            The matrix of predicted values.
        """
        return self.Bi + tf.tensordot(self.Gu, self.Gi, axes=[[1], [1]])

    def train_step(self, batch):
        """
        Apply a single training step on one batch.

        Args:
            batch: batch used for the current train step

        Returns:
            loss value at the current batch
        """
        user, pos, neg = batch
        with tf.GradientTape() as tape:
            xu_pos, beta_pos, gamma_u, gamma_pos = self(inputs=(user, pos))
            xu_neg, beta_neg, gamma_u, gamma_neg = self(inputs=(user, neg))

            difference = tf.clip_by_value(xu_pos - xu_neg, -80.0, 1e8)
            loss = tf.reduce_sum(tf.nn.softplus(-difference))

            # regularization
            reg_loss = self.l_w * tf.reduce_sum([tf.nn.l2_loss(gamma_u),
                                                 tf.nn.l2_loss(gamma_pos),
                                                 tf.nn.l2_loss(gamma_neg)]) \
                       + self.l_b * tf.nn.l2_loss(beta_pos) \
                       + self.l_b * tf.nn.l2_loss(beta_neg) / 10

            loss += reg_loss

        grads = tape.gradient(loss, [self.Bi, self.Gu, self.Gi])
        self.optimizer.apply_gradients(zip(grads, [self.Bi, self.Gu, self.Gi]))

        return loss.numpy()

    def train(self):
        if self.restore():
            self.restore_epochs += 1
        else:
            print("Training from scratch...")

        # initialize the max_ndcg to memorize the best result
        max_hr = 0
        best_model = self
        best_epoch = self.restore_epochs
        results = {}

        for epoch in range(self.restore_epochs, self.epochs + 1):
            start_ep = time()
            batches = self.data.shuffle(self.batch_size)
            self.train_step(batches)
            epoch_text = 'Epoch {0}/{1}'.format(epoch, self.epochs)
            self.evaluator.eval(epoch, results, epoch_text, start_ep)

            # print and log the best result (HR@10)
            if max_hr < results[epoch]['hr'][self.evaluator.k - 1]:
                max_hr = results[epoch]['hr'][self.evaluator.k - 1]
                best_epoch = epoch
                best_model = deepcopy(self)

            if epoch % self.verbose == 0 or epoch == 1:
                self.saver_ckpt.save('{0}/weights-{1}-BPR_MF'.format(weight_dir, epoch))

        self.evaluator.store_recommendation()
        save_obj(results, '{0}/{1}-results'.format(results_dir, self.path_output_rec_result.split('/')[-2]))

        # Store the best model
        print("Store Best Model at Epoch {0}".format(best_epoch))
        saver_ckpt = tf.train.Checkpoint(optimizer=self.optimizer, model=best_model)
        saver_ckpt.save('{0}/best-weights-{1}'.format(self.path_output_rec_weight, best_epoch))
        best_model.evaluator.store_recommendation()

    def restore(self):
        if self.restore_epochs > 1:
            try:
                checkpoint_file = find_checkpoint(weight_dir, self.restore_epochs, self.epochs,
                                                  self.rec)
                self.saver_ckpt.restore(checkpoint_file)
                print("Model correctly Restored at Epoch: {0}".format(self.restore_epochs))
                return True
            except Exception as ex:
                print("Error in model restoring operation! {0}".format(ex))
        else:
            print("Restore Epochs Not Specified")
        return False