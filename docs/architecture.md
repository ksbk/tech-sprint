# Architecture

TechSprint uses OOP with explicit state:

- `Workspace` owns file paths and directories for a run
- `Artifacts` is the typed contract of outputs
- `Job` is the single context object passed through the system
- `Anchor` orchestrates a pipeline using composable services
- `Services` are stateless and testable

Replace the stub services with real implementations without changing orchestration.
