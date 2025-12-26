# Maintainer Review

## Strengths

- Clear pipeline separation and single-responsibility services make the system testable and extensible.
- RenderSpec + renderer profiles provide a clean abstraction for output formats.
- Demo mode and integration scaffolding enable end-to-end validation without external APIs.
- QC tooling (ffprobe + loudnorm) provides measurable quality checks.
- CI separates unit/integration concerns and keeps PRs fast.
- Packaging now uses hatch-vcs, which simplifies versioning and releases.

## Risks / Technical Debt

- Optional dependency paths (edge-tts, ffmpeg) are still environment-sensitive and can fail in non-obvious ways.
- Demo fallback relies on external binaries; error messaging has improved but should remain consistent across commands.
- Versioning depends on git metadata; builds in shallow clones or tarball contexts may need documented handling.
- Windows/Linux portability needs more explicit validation (paths, open command, ffmpeg availability).
- Run manifest schema is v1 without an explicit schema or backward-compat strategy.

## Next Improvements (Actionable)

1) P0 / S — Add a JSON schema for `run.json` and validate in tests.
2) P0 / M — Add `techsprint runs --json` for machine-readable tooling.
3) P1 / M — Standardize error types (TechSprintError) across CLI and services.
4) P1 / M — Add an optional `--no-media-probe` flag for faster runs in constrained environments.
5) P1 / L — Introduce a small telemetry hook interface (no vendor lock-in) for structured run events.
6) P2 / S — Add Windows/Linux-specific docs for ffmpeg install and demo usage.
7) P2 / M — Add non-English demo fixtures to validate language/locale behavior.
8) P2 / M — Add “open latest run folder” command for quick inspection.
9) P2 / L — Provide a migration guide for future manifest v2 (schema evolution plan).
10) P2 / L — Expand QC into a “quality gate” CLI that fails on thresholds.

## Recommended Release Checklist

- Ensure `uv run pytest -q` passes locally.
- Run `UV_CACHE_DIR=.uv-cache uv build` and verify sdist/wheel output.
- Verify `techsprint run --demo` produces final.mp4 + run.json.
- Confirm `techsprint doctor` reports expected environment info.
- Tag release (semver), push tags, and verify CI green on main.
