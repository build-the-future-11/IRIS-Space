"""External-service adapters with explicit, fail-closed results."""

from .base import ResilientExecutor, ServiceResult

__all__ = ["ResilientExecutor", "ServiceResult"]
