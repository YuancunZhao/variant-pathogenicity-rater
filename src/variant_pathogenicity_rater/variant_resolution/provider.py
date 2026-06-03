from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.variant_resolution.schema import VariantResolutionRecord


DEFAULT_RESOLUTION_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "transcript_resolution"
    / "brca1_resolution.jsonl"
)


def load_resolution_records(raw: Any = None) -> tuple[list[VariantResolutionRecord], list[str]]:
    records: list[VariantResolutionRecord] = []
    limitations: list[str] = []
    if DEFAULT_RESOLUTION_FIXTURE.exists():
        default_records, default_limitations = _load_payload(DEFAULT_RESOLUTION_FIXTURE)
        records.extend(default_records)
        limitations.extend(default_limitations)
    if raw is not None:
        extra_records, extra_limitations = _load_payload(raw)
        records.extend(extra_records)
        limitations.extend(extra_limitations)
    return records, _unique(limitations)


def find_resolution_record(
    records: list[VariantResolutionRecord],
    *,
    gene: str | None,
    hgvs_c: str | None,
    transcript: str | None,
) -> VariantResolutionRecord | None:
    if not hgvs_c:
        return None
    query_gene = (gene or "").upper()
    query_hgvs = _canonical_hgvs_c(hgvs_c)
    query_transcript = _canonical_transcript(transcript or _transcript_from_hgvs(hgvs_c))

    candidates: list[VariantResolutionRecord] = []
    for record in records:
        if query_gene and record.gene.upper() != query_gene:
            continue
        if _canonical_hgvs_c(record.hgvs_c) != query_hgvs:
            continue
        candidates.append(record)
    if query_transcript:
        for record in candidates:
            if _canonical_transcript(record.transcript) == query_transcript:
                return record
    return candidates[0] if candidates else None


def _load_payload(raw: Any) -> tuple[list[VariantResolutionRecord], list[str]]:
    limitations: list[str] = []
    payload: Any
    if isinstance(raw, Path):
        payload = raw.read_text(encoding="utf-8")
    elif isinstance(raw, str):
        path = Path(raw)
        payload = path.read_text(encoding="utf-8") if path.exists() else raw
    else:
        payload = raw
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return [], []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = []
            for index, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    payload.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    limitations.append(f"Malformed transcript resolution JSONL line {index}: {exc}")
    if isinstance(payload, dict):
        payload = payload.get("records") or payload.get("transcript_resolution") or [payload]
    if not isinstance(payload, list):
        return [], ["Transcript resolution fixture must be a list, object, JSON array, JSONL text, or path."]

    records: list[VariantResolutionRecord] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            limitations.append(f"Transcript resolution record {index} is not an object.")
            continue
        try:
            records.append(VariantResolutionRecord.model_validate(item))
        except ValidationError as exc:
            limitations.append(f"Malformed transcript resolution record {index}: {exc.__class__.__name__}: {exc}")
    return records, _unique(limitations)


def _canonical_hgvs_c(value: str) -> str:
    text = value.strip()
    if ":" in text:
        text = text.split(":", 1)[1]
    return text.upper()


def _canonical_transcript(value: str | None) -> str | None:
    if not value:
        return None
    return value.split(":", 1)[0].strip().upper()


def _transcript_from_hgvs(value: str | None) -> str | None:
    if value and ":" in value:
        return value.split(":", 1)[0]
    return None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))
