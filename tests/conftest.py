from __future__ import annotations

import inspect

import typer.testing


def _patch_clirunner() -> None:
    if "mix_stderr" in inspect.signature(typer.testing.CliRunner).parameters:
        return

    class PatchedCliRunner(typer.testing.CliRunner):
        def __init__(self, *args, **kwargs):  # noqa: ANN002, ANN003
            kwargs.pop("mix_stderr", None)
            super().__init__(*args, **kwargs)

    typer.testing.CliRunner = PatchedCliRunner


_patch_clirunner()
