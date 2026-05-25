from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote


EMPTY_STRINGS = {"", "na", "n/a", "null", "none"}
ALLELE_FIELDS = {"ref", "alt"}
HGVS_FIELDS = {"hgvs", "hgvs_c", "hgvs_p", "hgvs_g"}
TEXT_FIELDS = {
    "gene",
    "gene_symbol",
    "transcript",
    "transcript_accession",
    "disease",
    "inheritance",
    "genome_build",
    "build",
}


@dataclass
class CleanedRecord:
    record: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


def strip_bom(value: str) -> str:
    return value.lstrip("\ufeff")


def normalize_column_name(key: Any) -> str | None:
    if key is None:
        return None
    raw = strip_bom(str(key)).strip()
    if not raw:
        return None
    lowered = raw.lower()
    if lowered.startswith("unnamed:") or lowered.startswith("unnamed_"):
        return None

    compact = re.sub(r"[\s\-]+", "_", raw.strip())
    upper = compact.upper()
    lower = compact.lower()
    aliases = {
        "#CHROM": "chromosome",
        "CHROM": "chromosome",
        "CHROMOSOME": "chromosome",
        "CHR": "chromosome",
        "POS": "position",
        "POSITION": "position",
        "START": "position",
        "REF": "ref",
        "ALT": "alt",
        "GENE": "gene",
        "SYMBOL": "gene",
        "GENE_SYMBOL": "gene",
        "GENE.REFGENE": "gene",
        "GENE_REFGENE": "gene",
        "TRANSCRIPT": "transcript",
        "TRANSCRIPT_ID": "transcript",
        "FEATURE": "transcript",
        "HGVS": "hgvs_c",
        "HGVSC": "hgvs_c",
        "HGVS_C": "hgvs_c",
        "HGVSP": "hgvs_p",
        "HGVS_P": "hgvs_p",
        "DISEASE": "disease",
        "DISEASE_NAME": "disease",
        "INHERITANCE": "inheritance",
        "INHERITANCE_MODE": "inheritance",
        "PHENOTYPE": "phenotype",
        "PHENOTYPE_TERMS": "phenotype_terms",
        "GENOME_BUILD": "genome_build",
        "BUILD": "build",
        "INPUT_TYPE": "input_type",
        "FORMAT": "format",
    }
    return aliases.get(upper, lower if lower in _known_lowercase_fields() else compact)


def clean_record(
    record: dict[str, Any],
    *,
    normalize_keys: bool = True,
    preserve_unknown_keys: bool = True,
) -> CleanedRecord:
    cleaned: dict[str, Any] = {}
    warnings: list[str] = []

    for raw_key, raw_value in record.items():
        key = normalize_column_name(raw_key) if normalize_keys else strip_bom(str(raw_key)).strip()
        if key is None:
            warnings.append(f"Ignored empty or Excel-generated column '{raw_key}'.")
            continue
        if not preserve_unknown_keys and key == str(raw_key).strip():
            continue
        value = clean_value(key, raw_value, warnings)
        if value is None:
            continue
        if key in cleaned and cleaned[key] != value:
            warnings.append(f"Column '{raw_key}' mapped to duplicate field '{key}'; later value was preserved.")
        cleaned[key] = value

    return CleanedRecord(record=cleaned, warnings=_unique(warnings))


def clean_value(field: str, value: Any, warnings: list[str]) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        original = value
        text = strip_bom(value).strip()
        if field not in ALLELE_FIELDS and text.lower() in EMPTY_STRINGS:
            if original != "":
                warnings.append(f"Field '{field}' empty marker was normalized to missing.")
            return None
        if field in ALLELE_FIELDS:
            allele = re.sub(r"\s+", "", text).upper()
            if allele != text:
                warnings.append(f"Field '{field}' was uppercased or whitespace-normalized.")
            return allele
        if field in HGVS_FIELDS:
            decoded = _decode_hgvs(text)
            if decoded != text:
                warnings.append(f"Field '{field}' was URL/HTML-decoded.")
            return decoded
        if field in TEXT_FIELDS and text != original:
            warnings.append(f"Field '{field}' surrounding whitespace was stripped.")
        return text
    return value


def normalize_chromosome_label(value: Any) -> str:
    text = strip_bom(str(value)).strip()
    if text.lower().startswith("chr"):
        text = text[3:]
    if text.upper() in {"M", "MT"}:
        return "MT"
    if text.upper() in {"X", "Y"}:
        return text.upper()
    return text


def is_comment_or_empty_line(line: str) -> bool:
    stripped = strip_bom(line).strip()
    return not stripped or stripped.startswith("#")


def is_metadata_line(line: str) -> bool:
    return strip_bom(line).lstrip().startswith("##")


def _decode_hgvs(value: str) -> str:
    decoded = html.unescape(unquote(value))
    decoded = decoded.strip()
    if any(ord(char) < 32 for char in decoded):
        return value
    return decoded


def _known_lowercase_fields() -> set[str]:
    return {
        "gene",
        "gene_symbol",
        "transcript",
        "transcript_accession",
        "transcript_version",
        "hgvs",
        "hgvs_c",
        "hgvs_p",
        "hgvs_g",
        "chrom",
        "chromosome",
        "position",
        "pos",
        "ref",
        "alt",
        "disease",
        "disease_name",
        "inheritance",
        "inheritance_mode",
        "phenotype",
        "phenotype_terms",
        "options",
        "variant",
        "gene_disease_context",
        "context",
        "input_type",
        "format",
        "genome_build",
        "build",
        "variant_type",
        "type",
    }


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
