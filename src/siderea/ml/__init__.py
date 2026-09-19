"""Optional representation-learning tools for SIDEREA light curves.

The package is deliberately separated from operational candidate gating.  A
missing PyTorch installation does not prevent importing :mod:`siderea.ml`; calls
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
from .episodic_memory import EpisodicResidualMemory, MemoryEntry, RetrievalResult
from .evaluate import evaluate_jepa, extract_embeddings
from .jepa import (
    TSJEPA,
    IrregularTimeEncoder,
    make_contiguous_target_mask,
    representation_diagnostics,
)
from .quaternion import (
    QuaternionCausalAttention,
    QuaternionGate,
    QuaternionLinear,
    QuaternionRMSNorm,
    hamilton_product,
    quaternion_conjugate,
    quaternion_norm,
)
from .space_jepa_v2 import AQPMJEPA, SpaceJEPA2Config, aqpm_jepa_loss
from .space_jepa_v2_baselines import (
    GRUForecastBaseline,
    RealCausalTransformerBaseline,
    RealPredictiveJEPA,
)
from .space_jepa_v2_data import prepare_space_jepa_v2_batches
from .space_jepa_v2_evaluate import evaluate_space_jepa_v2
from .space_jepa_v2_router import route_space_jepa_v2_evidence
from .space_jepa_v2_train import (
    SpaceJEPA2TrainingConfig,
    load_space_jepa_v2_checkpoint,
    save_space_jepa_v2_checkpoint,
    train_space_jepa_v2,
)
from .train import TrainingConfig, load_checkpoint, save_checkpoint, train_jepa

try:
    import torch as _torch  # noqa: F401
except ImportError:  # pragma: no cover - depends on the installation profile.
    TORCH_AVAILABLE = False
else:
    TORCH_AVAILABLE = True


__all__ = [
    "AQPMJEPA",
    "DEFAULT_BAND_TO_ID",
    "BaselineConfig",
    "BaselineMetadata",
    "ChronologicalSplit",
    "EpisodicResidualMemory",
    "GRUForecastBaseline",
    "IrregularTimeEncoder",
    "LightCurveBatch",
    "LightCurveDataset",
    "MissingOptionalDependency",
    "MemoryEntry",
    "QuaternionCausalAttention",
    "QuaternionGate",
    "QuaternionLinear",
    "QuaternionRMSNorm",
    "RealCausalTransformerBaseline",
    "RealPredictiveJEPA",
    "RetrievalResult",
    "SKLEARN_AVAILABLE",
    "TOKEN_DIM",
    "TOKEN_FIELDS",
    "TOKENIZATION_CONTRACT_VERSION",
    "TORCH_AVAILABLE",
    "TSJEPA",
    "SupervisedBaseline",
    "SpaceJEPA2Config",
    "SpaceJEPA2TrainingConfig",
    "TokenizedLightCurve",
    "TrainingConfig",
    "VALUE_PRESENT_INDEX",
    "batch_token_contract_digest",
    "collate_light_curves",
    "chronological_split",
    "aqpm_jepa_loss",
    "evaluate_jepa",
    "evaluate_space_jepa_v2",
    "extract_embeddings",
    "fit_baseline",
    "hamilton_product",
    "load_baseline_bundle",
    "load_checkpoint",
    "load_space_jepa_v2_checkpoint",
    "make_contiguous_target_mask",
    "pad_light_curves",
    "prepare_space_jepa_v2_batches",
    "representation_diagnostics",
    "quaternion_conjugate",
    "quaternion_norm",
    "require_torch",
    "route_space_jepa_v2_evidence",
    "save_checkpoint",
    "save_space_jepa_v2_checkpoint",
    "save_baseline_bundle",
    "tokenize_light_curve",
    "train_jepa",
    "train_space_jepa_v2",
]
