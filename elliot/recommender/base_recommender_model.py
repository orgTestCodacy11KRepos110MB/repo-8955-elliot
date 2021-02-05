"""
Module description:

"""

__version__ = '0.1'
__author__ = 'Vito Walter Anelli, Claudio Pomo'
__email__ = 'vitowalter.anelli@poliba.it, claudio.pomo@poliba.it'

from abc import ABC
from abc import abstractmethod


class BaseRecommenderModel(ABC):
    def __init__(self, data, config, params, *args, **kwargs):
        """
        This class represents a recommender model. You can load a pretrained model
        by specifying its checkpoint path and use it for training/testing purposes.

        Args:
            data: data loader object
            params: dictionary with all parameters
        """
        self._data = data
        self._config = config
        self._params = params

        self._restore_epochs = getattr(self._params.meta, "restore_epoch", -1)
        self._validation_metric = getattr(self._params.meta, "validation_metric", "nDCG@10").split("@")
        self._validation_k = int(self._validation_metric[1]) if len(self._validation_metric) > 1 else 10
        self._validation_metric = self._validation_metric[0]
        self._save_weights = getattr(self._params.meta, "save_weights", False)
        self._save_recs = getattr(self._params.meta, "save_recs", False)
        self._verbose = getattr(self._params.meta, "verbose", None)
        self._validation_rate = getattr(self._params.meta, "validation_rate", 1)
        self._compute_auc = getattr(self._params.meta, "compute_auc", False)
        self._epochs = getattr(self._params, "epochs", 2)
        if self._epochs < self._validation_rate:
            raise Exception(f"The first validation epoch ({self._validation_rate}) is later than the overall number of epochs ({self._epochs}).")
        self._batch_size = getattr(self._params, "batch_size", -1)
        self._results = []
        self._params_list = []

    def get_params_shortcut(self):
        return "_".join([str(p[2])+":"+ str(p[5](getattr(self, p[0])) if p[5] else getattr(self, p[0])) for p in self._params_list])

    def autoset_params(self):
        """
        Define Parameters as tuples: (variable_name, public_name, shortcut, default, reading_function, printing_function)
        Example:

        self._params_list = [
            ("_similarity", "similarity", "sim", "cosine", None, None),
            ("_user_profile_type", "user_profile", "up", "tfidf", None, None),
            ("_item_profile_type", "item_profile", "ip", "tfidf", None, None),
            ("_mlpunits", "mlp_units", "mlpunits", "(1,2,3)", lambda x: list(make_tuple(x)), lambda x: str(x).replace(",", "-")),
        ]
        """
        print("\nLoading parameters: ")
        for variable_name, public_name, shortcut, default, reading_function, _ in self._params_list:
            if reading_function is None:
                setattr(self, variable_name, getattr(self._params, public_name, default))
            else:
                setattr(self, variable_name, reading_function(getattr(self._params, public_name, default)))
            print(f"Parameter {public_name} set to {getattr(self, variable_name)}")
        if not self._params_list:
            print("No parameters defined")

    @abstractmethod
    def train(self):
        pass

    @abstractmethod
    def get_recommendations(self, *args):
        pass

    @abstractmethod
    def get_loss(self):
        pass

    @abstractmethod
    def get_params(self):
        pass

    @abstractmethod
    def get_results(self):
        pass

    # @abstractmethod
    # def get_statistical_results(self):
    #     pass
    #
    # @abstractmethod
    # def get_test_results(self):
    #     pass
    #
    # @abstractmethod
    # def get_test_statistical_results(self):
    #     pass
