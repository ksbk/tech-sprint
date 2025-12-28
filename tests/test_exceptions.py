from techsprint.exceptions import (
    ConfigurationError,
    DependencyMissingError,
    ErrorCategory,
    TechSprintError,
)


def test_defaults_and_labels() -> None:
    err = TechSprintError("boom")
    assert err.category == ErrorCategory.RUNTIME
    assert err.exit_code == 1
    assert err.label() == "Runtime error"


def test_configuration_error_category_and_code() -> None:
    err = ConfigurationError("config oops")
    assert err.category == ErrorCategory.CONFIG
    assert err.exit_code == 2
    assert err.label() == "Configuration error"


def test_dependency_error_category_and_code_passthrough() -> None:
    err = DependencyMissingError("missing", exit_code=9)
    assert err.category == ErrorCategory.DEPENDENCY
    assert err.exit_code == 9
    assert err.label() == "Dependency error"
