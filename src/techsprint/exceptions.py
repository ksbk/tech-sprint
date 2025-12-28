from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCategory(str, Enum):
    CONFIG = "config"
    DEPENDENCY = "dependency"
    RUNTIME = "runtime"


DEFAULT_EXIT_CODES: dict[ErrorCategory, int] = {
    ErrorCategory.RUNTIME: 1,
    ErrorCategory.CONFIG: 2,
    ErrorCategory.DEPENDENCY: 3,
}


@dataclass
class TechSprintError(Exception):
    """Base exception for TechSprint with standardized categories."""

    message: str
    category: ErrorCategory = ErrorCategory.RUNTIME
    exit_code: int | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)
        if self.exit_code is None:
            self.exit_code = DEFAULT_EXIT_CODES.get(self.category, 1)

    def label(self) -> str:
        return {
            ErrorCategory.CONFIG: "Configuration error",
            ErrorCategory.DEPENDENCY: "Dependency error",
            ErrorCategory.RUNTIME: "Runtime error",
        }.get(self.category, "Error")


class DependencyMissingError(TechSprintError):
    """Raised when a required external dependency is missing."""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.DEPENDENCY,
            exit_code=exit_code,
        )


class ConfigurationError(TechSprintError):
    """Raised when configuration is invalid."""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(
            message,
            category=ErrorCategory.CONFIG,
            exit_code=exit_code,
        )
