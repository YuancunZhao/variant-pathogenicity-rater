#!/usr/bin/env python3
"""Print local test-environment diagnostics for Variant Pathogenicity Rater."""

from __future__ import annotations

import importlib
import importlib.metadata
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
MCP_SERVER = ROOT / "mcp-server"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))


def package_status(import_name: str, distribution_name: str | None = None) -> str:
    distribution_name = distribution_name or import_name
    try:
        importlib.import_module(import_name)
    except Exception as exc:  # pragma: no cover - diagnostic output only
        return f"missing ({exc.__class__.__name__}: {exc})"

    try:
        version = importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        version = "installed, version unknown"
    return f"ok ({version})"


def main() -> int:
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")

    print("Package import status:")
    for import_name, distribution_name in [
        ("pydantic", "pydantic"),
        ("pytest", "pytest"),
        ("variant_pathogenicity_rater", "variant-pathogenicity-rater-mcp"),
        ("server", None),
        ("tools", None),
    ]:
        print(f"  {import_name}: {package_status(import_name, distribution_name)}")

    pytest_status = package_status("pytest", "pytest")
    print(f"pytest availability: {pytest_status}")

    project_status = package_status(
        "variant_pathogenicity_rater",
        "variant-pathogenicity-rater-mcp",
    )
    print(f"project import status: {project_status}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
