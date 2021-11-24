def import_model_by_backend(tensorflow_cmd, pytorch_cmd):
    import sys
    for _backend in sys.modules["external"].backend:
        if _backend == "tensorflow":
            exec(tensorflow_cmd)
        elif _backend == "pytorch":
            exec(pytorch_cmd)
            break


from .most_popular import MostPop
from .msap import MSAPMF
from .AdversarialMF import AdversarialMF
from .ktup import KTUP
from .kgflex import KGFlex

import sys
for _backend in sys.modules["external"].backend:
    if _backend == "tensorflow":
        pass
    elif _backend == "pytorch":
        from .ngcf.NGCF import NGCF
        from .lightgcn.LightGCN import LightGCN
        from .pinsage.PinSage import PinSage
        from .gat.GAT import GAT
        from .gcmc.GCMC import GCMC
        from .disen_gcn.DisenGCN import DisenGCN
        from .mmgcn.MMGCN import MMGCN
        from .dgcf.DGCF import DGCF
        from .egcf.EGCF import EGCF
