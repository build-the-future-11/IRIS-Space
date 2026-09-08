"""SIDEREA astronomical discovery platform.

The public objects exported here are deliberately dependency-free.  Pipeline
components may therefore exchange validated candidate records without loading
the scientific Python stack or making network calls.
"""

from siderea.config import ConfigError, SIDEREAConfig, load_config
from siderea.domain import (
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
    "SIDEREAConfig",
    "Observation",
    "load_config",
]

__version__ = "0.3.0"
