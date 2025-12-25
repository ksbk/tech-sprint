class TechSprintError(Exception):
    """Base exception for TechSprint."""


class DependencyMissingError(TechSprintError):
    """Raised when a required external dependency is missing."""


class ConfigurationError(TechSprintError):
    """Raised when configuration is invalid."""
