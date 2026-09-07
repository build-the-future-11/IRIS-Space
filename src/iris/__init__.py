"""IRIS astronomical discovery platform.

The public objects exported here are deliberately dependency-free.  Pipeline
components may therefore exchange validated candidate records without loading
the scientific Python stack or making network calls.
"""

from iris.config import ConfigError, IRISConfig, load_config
from iris.domain import (
    Candidate,
    CandidateState,
    CheckStatus,
    Evidence,
    EvidenceKind,
    Observation,
)

__all__ = [
    "Candidate",
    "CandidateState",
    "CheckStatus",
    "ConfigError",
    "Evidence",
    "EvidenceKind",
    "IRISConfig",
    "Observation",
    "load_config",
]

__version__ = "0.2.0"
