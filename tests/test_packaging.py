from __future__ import annotations

import importlib


def test_import_package_and_cli_module() -> None:
    package = importlib.import_module("variant_pathogenicity_rater")
    cli = importlib.import_module("variant_pathogenicity_rater.cli")

    assert package is not None
    assert callable(cli.main)
