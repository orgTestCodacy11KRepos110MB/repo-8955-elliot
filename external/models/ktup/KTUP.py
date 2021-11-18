"""
Module description:

"""

__version__ = '0.1'
__author__ = 'Vito Walter Anelli, Claudio Pomo, Daniele Malitesta'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it'

from tqdm import tqdm
import numpy as np
import typing as t
from collections import defaultdict

from elliot.dataset.samplers import custom_sampler as cs
from elliot.evaluation.evaluator import Evaluator
from elliot.recommender import BaseRecommenderModel
from .KTUPModel import jtup
from . import triple_sampler as ts
from elliot.recommender.base_recommender_model import init_charger
from elliot.utils.write import store_recommendation
from elliot.recommender.knowledge_aware.kaHFM_batch.tfidf_utils import TFIDF
from elliot.recommender.recommender_utils_mixin import RecMixin

np.random.seed(42)


class KTUP(RecMixin, BaseRecommenderModel):
    @init_charger
    def __init__(self, data, config, params, *args, **kwargs):
        """
        Create a BPR-MF instance.
        (see https://arxiv.org/pdf/1205.2618 for details about the algorithm design choices).

        Args:
            data: data loader object
            params: model parameters {embed_k: embedding size,
                                      [l_w, l_b]: regularization,
                                      lr: learning rate}
        """
        self._random = np.random

        self._ratings = self._data.train_dict

        # autoset params
        self._params_list = [
            ("_l2_lambda", "l2_lambda", "l2", 0, None, None),
            ("_embedding_size", "embedding_size", "es", 100, int, None),
            ("_learning_rate", "lr", "lr", 0.001, None, None),
            ("_joint_ratio", "joint_ratio", "jr", 0.7, None, None),
            ("_L1", "L1_flag", "l1", True, None, None),
            ("_norm_lambda", "norm_lambda", "nl", 1, None, None),
            ("_kg_lambda", "kg_lambda", "kgl", 1, None, None),
            ("_use_st_gumbel", "use_st_gumbel", "gum", False, None, None),
            ("_loader", "loader", "load", "KGRec", None, None)
        ]
        self.autoset_params()
        self._step_to_switch = self._joint_ratio * 10
        self._side = getattr(self._data.side_information, self._loader, None)

        self._iteration = 0
        if self._batch_size < 1:
            self._batch_size = self._data.num_users


        self._sampler = cs.Sampler(self._data.i_train_dict)
        self._triple_sampler = ts.Sampler(self._side.entity_to_idx, self._side.Xs, self._side.Xp, self._side.Xo)

        self._i_items_set = list(range(self._num_items))

        new_map = defaultdict(lambda: -1)
        new_map.update({self._data.public_items[i]: idx for i, idx in self._side.public_items_entitiesidx.items()})
        ######################################

        self._model = jtup(self._learning_rate, self._L1, self._embedding_size, self._data.num_users, self._data.num_items, len(self._side.entity_set),
                           len(self._side.predicate_set), new_map)



    @property
    def name(self):
        return "kTUP" \
               + "_e:" + str(self._epochs) \
               + "_bs:" + str(self._batch_size) \
               + f"_{self.get_params_shortcut()}"

    def train(self):
        if self._restore:
            return self.restore_weights()

        best_metric_value = 0
        self._update_count = 0
        for it in range(self._epochs):
            loss = 0
            steps = 0
            with tqdm(total=int(self._data.transactions // self._batch_size), disable=not self._verbose) as t:
                if it % 10 < self._step_to_switch:
                    for batch in self._sampler.step(self._data.transactions, self._batch_size):
                        steps += 1
                        loss += self._model.train_step_rec(batch, is_rec=True)
                        t.set_postfix({'loss': f'{loss.numpy() / steps:.5f}'})
                        t.update()
                else:
                    for batch in self._triple_sampler.step(self._batch_size):
                        steps += 1
                        loss += self._model.train_step_kg(batch, is_rec=False, kg_lambda=self._kg_lambda)
                        t.set_postfix({'loss': f'{loss.numpy() / steps:.5f}'})
                        t.update()

            if not (it + 1) % self._validation_rate:
                recs = self.get_recommendations(self.evaluator.get_needed_recommendations())
                result_dict = self.evaluator.eval(recs)
                self._results.append(result_dict)

                print(f'Epoch {(it + 1)}/{self._epochs} loss {loss:.3f}')

                if self._results[-1][self._validation_k]["val_results"][self._validation_metric] > best_metric_value:
                    print("******************************************")
                    best_metric_value = self._results[-1][self._validation_k]["val_results"][self._validation_metric]
                    if self._save_weights:
                        self._model.save_weights(self._saving_filepath)
                    if self._save_recs:
                        store_recommendation(recs, self._config.path_output_rec_result + f"{self.name}-it:{it + 1}.tsv")

    def get_recommendations(self, k: int = 100):
        predictions_top_k_test = {}
        predictions_top_k_val = {}
        for index, offset in enumerate(range(0, self._num_users, self._batch_size)):
            offset_stop = min(offset + self._batch_size, self._num_users)
            predictions = self._model.get_recs(
                (
                    np.repeat(np.array(list(range(offset, offset_stop)))[:, None], repeats=self._num_items, axis=1),
                    np.array([self._i_items_set for _ in range(offset, offset_stop)])
                )
            )
            recs_val, recs_test = self.process_protocol(k, predictions, offset, offset_stop)

            predictions_top_k_val.update(recs_val)
            predictions_top_k_test.update(recs_test)
        return predictions_top_k_val, predictions_top_k_test
