"""
Module description:

"""

__version__ = '0.1'
__author__ = 'Vito Walter Anelli, Claudio Pomo'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it'

import numpy as np
import pickle
import time
import typing as t
import scipy.sparse as sp

from evaluation.evaluator import Evaluator
from recommender.recommender_utils_mixin import RecMixin
from utils.folder import build_model_folder
from utils.write import store_recommendation

from recommender.base_recommender_model import BaseRecommenderModel
from recommender.NN.attribute_user_knn.attribute_user_knn_similarity import Similarity
from recommender.NN.attribute_user_knn.tfidf_utils import TFIDF

np.random.seed(42)


class AttributeUserKNN(RecMixin, BaseRecommenderModel):

    def __init__(self, data, config, params, *args, **kwargs):
        super().__init__(data, config, params, *args, **kwargs)

        self._restore = getattr(self._params, "restore", False)
        self._num_items = self._data.num_items
        self._num_users = self._data.num_users
        self._random = np.random

        self._params_list = [
            ("_num_neighbors", "neighbors", "nn", 40, None, None),
            ("_similarity", "similarity", "sim", "cosine", None, None),
            ("_profile_type", "profile", "profile", "binary", None, None)
        ]
        self.autoset_params()
        # self._num_neighbors = self._params.neighbors
        # self._similarity = self._params.similarity
        # self._profile_type = getattr(self._params, "profile", "binary")

        self._ratings = self._data.train_dict

        if self._profile_type == "tfidf":
            self._tfidf_obj = TFIDF(self._data.side_information_data.feature_map)
            self._tfidf = self._tfidf_obj.tfidf()
            self._user_profiles = self._tfidf_obj.get_profiles(self._ratings)
        else:
            self._user_profiles = {user: self.compute_binary_profile(user_items) for user, user_items in self._ratings.items()}

        self._i_feature_dict = {self._data.public_users[user]: {self._data.public_features[feature]: value for feature, value in user_features.items()} for user, user_features in self._user_profiles.items()}
        self._sp_i_features = self.build_feature_sparse_values()

        self._datamodel = Similarity(self._data, self._sp_i_features, self._num_neighbors, self._similarity)

        self._params.name = self.name

        build_model_folder(self._config.path_output_rec_weight, self.name)
        self._saving_filepath = f'{self._config.path_output_rec_weight}{self.name}/best-weights-{self.name}'

        start = time.time()
        if self._restore:
            self.restore_weights()
        else:
            self._datamodel.initialize()
        end = time.time()
        print(f"The similarity computation has taken: {end - start}")

        self.evaluator = Evaluator(self._data, self._params)

        if self._save_weights:
            with open(self._saving_filepath, "wb") as f:
                print("Saving Model")
                pickle.dump(self._datamodel.get_model_state(), f)

    def get_recommendations(self, k: int = 100):
        return {u: self._datamodel.get_user_recs(u, k) for u in self._ratings.keys()}

    @property
    def name(self):
        return f"AttributeUserKNN_{self.get_params_shortcut()}"

    def train(self):

        print(f"Transactions: {self._data.transactions}")
        best_metric_value = 0

        recs = self.get_recommendations(self.evaluator.get_needed_recommendations())
        result_dict = self.evaluator.eval(recs)
        self._results.append(result_dict)
        print(f'Finished')

        if self._results[-1][self._validation_k]["val_results"][self._validation_metric] > best_metric_value:
            print("******************************************")
            if self._save_recs:
                store_recommendation(recs, self._config.path_output_rec_result + f"{self.name}.tsv")

    def compute_binary_profile(self, user_items_dict: t.Dict):
        user_features = {}
        partial = 1/len(user_items_dict)
        for item in user_items_dict.keys():
            for feature in self._data.side_information_data.feature_map.get(item,[]):
                user_features[feature] = user_features.get(feature, 0) + partial
        return user_features

    def build_feature_sparse(self):

        rows_cols = [(i, f) for i, features in self._i_feature_dict.items() for f in features]
        rows = [u for u, _ in rows_cols]
        cols = [i for _, i in rows_cols]
        data = sp.csr_matrix((np.ones_like(rows), (rows, cols)), dtype='float32',
                             shape=(self._num_items, len(self._data.public_features)))
        return data

    def build_feature_sparse_values(self):
        rows_cols_values = [(u, f, v) for u, features in self._i_feature_dict.items() for f, v in features.items()]
        rows = [u for u, _, _ in rows_cols_values]
        cols = [i for _, i, _ in rows_cols_values]
        values = [r for _, _, r in rows_cols_values]

        data = sp.csr_matrix((values, (rows, cols)), dtype='float32',
                             shape=(self._num_users, len(self._data.public_features)))

        return data

    def restore_weights(self):
        try:
            with open(self._saving_filepath, "rb") as f:
                self._datamodel.set_model_state(pickle.load(f))
            print(f"Model correctly Restored")
            return True
        except Exception as ex:
            print(f"Error in model restoring operation! {ex}")