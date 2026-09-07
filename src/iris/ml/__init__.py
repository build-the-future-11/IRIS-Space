"""Optional representation-learning tools for IRIS light curves.

The package is deliberately separated from operational candidate gating.  A
missing PyTorch installation does not prevent importing :mod:`iris.ml`; calls
that need tensors raise a concise dependency error.
"""

from .baseline import (
    SKLEARN_AVAILABLE,
    BaselineConfig,
    BaselineMetadata,
    ChronologicalSplit,
    MissingOptionalDependency,
    SupervisedBaseline,
    chronological_split,
    fit_baseline,
    load_baseline_bundle,
    save_baseline_bundle,
)
from .dataset import (
    DEFAULT_BAND_TO_ID,
    TOKEN_DIM,
    TOKEN_FIELDS,
    TOKENIZATION_CONTRACT_VERSION,
    VALUE_PRESENT_INDEX,
    LightCurveBatch,
    LightCurveDataset,
    TokenizedLightCurve,
    batch_token_contract_digest,
    collate_light_curves,
    pad_light_curves,
    require_torch,
    tokenize_light_curve,
)
from .evaluate import evaluate_jepa, extract_embeddings
from .jepa import (
    TSJEPA,
    IrregularTimeEncoder,
    make_contiguous_target_mask,
    representation_diagnostics,
)
from .train import TrainingConfig, load_checkpoint, save_checkpoint, train_jepa

try:
    import torch as _torch  # noqa: F401
except ImportError:  # pragma: no cover - depends on the installation profile.
    TORCH_AVAILABLE = False
else:
    TORCH_AVAILABLE = True


__all__ = [
    "DEFAULT_BAND_TO_ID",
    "BaselineConfig",
    "BaselineMetadata",
    "ChronologicalSplit",
    "IrregularTimeEncoder",
    "LightCurveBatch",
    "LightCurveDataset",
    "MissingOptionalDependency",
    "SKLEARN_AVAILABLE",
    "TOKEN_DIM",
    "TOKEN_FIELDS",
    "TOKENIZATION_CONTRACT_VERSION",
    "TORCH_AVAILABLE",
    "TSJEPA",
    "SupervisedBaseline",
    "TokenizedLightCurve",
    "TrainingConfig",
    "VALUE_PRESENT_INDEX",
    "batch_token_contract_digest",
    "collate_light_curves",
    "chronological_split",
    "evaluate_jepa",
    "extract_embeddings",
    "fit_baseline",
    "load_baseline_bundle",
    "load_checkpoint",
    "make_contiguous_target_mask",
    "pad_light_curves",
    "representation_diagnostics",
    "require_torch",
    "save_checkpoint",
    "save_baseline_bundle",
    "tokenize_light_curve",
    "train_jepa",
]
