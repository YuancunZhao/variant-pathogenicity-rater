from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.vcep_profiles.schema import VCEPProfile


SUPPORTED_SUFFIXES = {".json", ".jsonl"}


def load_vcep_profiles(options: dict[str, Any]) -> tuple[list[VCEPProfile], list[str]]:
    profiles: list[VCEPProfile] = []
    limitations: list[str] = []

    for raw in options.get("vcep_profile_records") or []:
        if not isinstance(raw, dict):
            limitations.append("VCEP profile record was ignored because it was not an object.")
            continue
        _append_profile(raw, profiles, limitations, source="options.vcep_profile_records")

    profile_file = options.get("vcep_profile_file")
    if isinstance(profile_file, str) and profile_file:
        profiles.extend(_load_profile_path(Path(profile_file), limitations))

    kb_dir = options.get("vcep_kb_dir")
    if isinstance(kb_dir, str) and kb_dir:
        base = Path(kb_dir)
        for subdir in ("disease_profiles", "rule_overrides", "vcep_signals"):
            path = base / subdir
            if not path.exists():
                continue
            for child in sorted(path.iterdir()):
                if child.is_file() and child.suffix.lower() in SUPPORTED_SUFFIXES:
                    profiles.extend(_load_profile_path(child, limitations))

    return profiles, limitations


def _load_profile_path(path: Path, limitations: list[str]) -> list[VCEPProfile]:
    profiles: list[VCEPProfile] = []
    if not path.exists():
        limitations.append(f"VCEP profile path does not exist: {path}")
        return profiles
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        limitations.append(f"VCEP profile path could not be read: {path}: {exc}")
        return profiles

    if path.suffix.lower() == ".jsonl":
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                limitations.append(f"VCEP JSONL parse failed at {path}:{line_number}: {exc}")
                continue
            _append_profile(raw, profiles, limitations, source=f"{path}:{line_number}")
        return profiles

    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        limitations.append(f"VCEP JSON parse failed at {path}: {exc}")
        return profiles
    records = raw if isinstance(raw, list) else [raw]
    for record in records:
        _append_profile(record, profiles, limitations, source=str(path))
    return profiles


def _append_profile(
    raw: Any,
    profiles: list[VCEPProfile],
    limitations: list[str],
    *,
    source: str,
) -> None:
    if not isinstance(raw, dict):
        limitations.append(f"VCEP profile from {source} was ignored because it was not an object.")
        return
    try:
        profiles.append(VCEPProfile.model_validate(raw))
    except ValidationError as exc:
        limitations.append(f"VCEP profile from {source} failed validation: {exc}")
