from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.schemas.variant import (
    GenomeBuild,
    NormalizationResult,
    Transcript,
    Variant,
    VariantType,
)

SUPPORTED_INPUT_FORMATS = {"hgvs", "vcf_like", "structured"}
SMALL_INDEL_MAX_BP = 50
ALLELE_RE = re.compile(r"^[ACGTN]+$", re.IGNORECASE)
TRANSCRIPT_RE = re.compile(r"^(?P<accession>[A-Z]{2}_[0-9]+)(?:\.(?P<version>[0-9]+))?")
HGVS_C_SUB_RE = re.compile(r":c\.(?P<pos>[-*]?\d+(?:[+-]\d+)?)(?P<ref>[ACGT])>(?P<alt>[ACGT])$", re.I)
HGVS_C_DEL_RE = re.compile(r":c\.(?P<pos>[-*]?\d+(?:[+-]\d+)?)(?:_(?P<end>[-*]?\d+))?del(?P<seq>[ACGT]+)?$", re.I)
HGVS_C_DUP_RE = re.compile(r":c\.(?P<pos>[-*]?\d+(?:[+-]\d+)?)(?:_(?P<end>[-*]?\d+))?dup(?P<seq>[ACGT]+)?$", re.I)
HGVS_C_INS_RE = re.compile(
    r":c\.(?P<start>[-*]?\d+(?:[+-]\d+)?)_(?P<end>[-*]?\d+(?:[+-]\d+)?)ins(?P<seq>[ACGT]+)$",
    re.I,
)
HGVS_C_DELINS_RE = re.compile(
    r":c\.(?P<pos>[-*]?\d+(?:[+-]\d+)?)(?:_(?P<end>[-*]?\d+))?delins(?P<seq>[ACGT]+)$",
    re.I,
)


class NormalizationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "NORMALIZATION_ERROR",
        warnings: list[str] | None = None,
        unresolved_fields: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.warnings = warnings or []
        self.unresolved_fields = unresolved_fields or []


def normalize_variant(payload: dict[str, Any]) -> NormalizationResult:
    """Normalize phase-1 HGVS-like or VCF-like variant input.

    This module deliberately avoids liftover, transcript mapping, and external API
    normalization. Fields that cannot be resolved locally are reported explicitly.
    """

    if not isinstance(payload, dict):
        raise NormalizationError("Variant normalization input must be a JSON object.")

    data = _unwrap_variant(payload)
    input_format = _detect_input_format(data)
    warnings: list[str] = []
    unresolved: list[str] = []

    if input_format == "vcf_like":
        variant = _normalize_vcf_like(data, warnings, unresolved)
    elif input_format == "hgvs":
        variant = _normalize_hgvs_like(data, warnings, unresolved)
    else:
        variant = _normalize_structured(data, warnings, unresolved)

    return NormalizationResult(
        status="normalized",
        input_format=input_format,
        normalized_variant=variant,
        normalization_warnings=_unique(warnings),
        unresolved_fields=_unique(unresolved),
        human_review_required=True,
    )


def _unwrap_variant(payload: dict[str, Any]) -> dict[str, Any]:
    variant = payload.get("variant", payload)
    if not isinstance(variant, dict):
        raise NormalizationError("The 'variant' field must be an object when provided.")
    return variant


def _detect_input_format(data: dict[str, Any]) -> str:
    requested = data.get("input_type") or data.get("format")
    if requested is not None:
        requested = str(requested).lower()
        if requested not in SUPPORTED_INPUT_FORMATS:
            raise NormalizationError(
                f"Unsupported input_type '{requested}'.",
                code="UNSUPPORTED_INPUT_FORMAT",
            )
        return requested
    if any(key in data for key in ("vcf", "chromosome", "chrom", "position", "pos")):
        return "vcf_like"
    if any(key in data for key in ("hgvs", "hgvs_c", "hgvs_p", "transcript")):
        return "hgvs"
    return "structured"


def _normalize_vcf_like(
    data: dict[str, Any], warnings: list[str], unresolved: list[str]
) -> Variant:
    vcf = data.get("vcf", data)
    if not isinstance(vcf, dict):
        raise NormalizationError("The 'vcf' field must be an object.")

    chrom = _string_field(vcf, "chrom", "chromosome", required=True)
    pos = _int_field(vcf, "pos", "position", required=True)
    ref = _allele_field(vcf, "ref", required=True)
    alt = _alt_field(vcf, required=True)
    genome_build = _genome_build(vcf)

    variant_type = _classify_ref_alt(ref, alt)
    _reject_unsupported_ref_alt(ref, alt, variant_type)

    return _build_variant(
        genome_build=genome_build,
        variant_type=variant_type,
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        gene_symbol=_optional_str(vcf.get("gene") or vcf.get("gene_symbol")),
        hgvs_c=_optional_str(vcf.get("hgvs_c")),
        hgvs_p=_optional_str(vcf.get("hgvs_p")),
        hgvs_g=_optional_str(vcf.get("hgvs_g")),
        transcript=_transcript_from_fields(vcf, warnings),
        warnings=warnings,
    )


def _normalize_structured(
    data: dict[str, Any], warnings: list[str], unresolved: list[str]
) -> Variant:
    if all(key in data for key in ("chrom", "pos", "ref", "alt")) or all(
        key in data for key in ("chromosome", "position", "ref", "alt")
    ):
        return _normalize_vcf_like(data, warnings, unresolved)
    if "hgvs_c" in data or "transcript" in data:
        return _normalize_hgvs_like(data, warnings, unresolved)
    raise NormalizationError(
        "Input must include either VCF-like chrom/pos/ref/alt fields or HGVS-like transcript/hgvs_c fields.",
        code="SCHEMA_VALIDATION_ERROR",
        unresolved_fields=["input_type"],
    )


def _normalize_hgvs_like(
    data: dict[str, Any], warnings: list[str], unresolved: list[str]
) -> Variant:
    hgvs_c = _optional_str(data.get("hgvs_c") or data.get("hgvs"))
    hgvs_p = _optional_str(data.get("hgvs_p"))
    gene_symbol = _optional_str(data.get("gene") or data.get("gene_symbol"))
    transcript_value = _optional_str(data.get("transcript") or data.get("transcript_accession"))

    if hgvs_c and ":" in hgvs_c:
        transcript_value = transcript_value or hgvs_c.split(":", 1)[0]
    if not transcript_value:
        warnings.append("Missing transcript; transcript-dependent HGVS mapping is unresolved.")
        unresolved.append("transcript")
    if not hgvs_c:
        raise NormalizationError(
            "HGVS-like input requires 'hgvs_c' or 'hgvs'.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=["hgvs_c"],
        )
    if not hgvs_p:
        warnings.append("Missing hgvs_p; protein consequence is unresolved.")
        unresolved.append("hgvs_p")

    parsed = _parse_hgvs_c(hgvs_c, warnings, unresolved)
    variant_type = parsed["variant_type"]
    ref = parsed["ref"]
    alt = parsed["alt"]
    _reject_unsupported_ref_alt(ref, alt, variant_type)

    if "chrom" in data or "chromosome" in data:
        chrom = _string_field(data, "chrom", "chromosome", required=True)
    else:
        chrom = "unresolved"
        unresolved.append("chrom")
        warnings.append("Chromosome not resolved; no transcript mapping or external normalization was performed.")

    if "pos" in data or "position" in data:
        pos = _int_field(data, "pos", "position", required=True)
    else:
        pos = 1
        unresolved.append("pos")
        warnings.append("Genomic position not resolved; placeholder pos=1 is used to satisfy the Variant schema.")

    transcript = _transcript_from_fields(
        {
            **data,
            "gene_symbol": gene_symbol or "unknown",
            "transcript": transcript_value,
            "hgvs_c": hgvs_c,
            "hgvs_p": hgvs_p,
        },
        warnings,
    )

    return _build_variant(
        genome_build=_genome_build(data),
        variant_type=variant_type,
        chrom=chrom,
        pos=pos,
        ref=ref,
        alt=alt,
        gene_symbol=gene_symbol,
        hgvs_c=hgvs_c,
        hgvs_p=hgvs_p,
        hgvs_g=_optional_str(data.get("hgvs_g")),
        transcript=transcript,
        warnings=warnings,
    )


def _parse_hgvs_c(
    hgvs_c: str, warnings: list[str], unresolved: list[str]
) -> dict[str, str | VariantType]:
    searchable_hgvs = hgvs_c if ":" in hgvs_c else f"unresolved:{hgvs_c}"
    substitution = HGVS_C_SUB_RE.search(searchable_hgvs)
    if substitution:
        return {
            "variant_type": VariantType.SNV,
            "ref": substitution.group("ref").upper(),
            "alt": substitution.group("alt").upper(),
        }

    deletion = HGVS_C_DEL_RE.search(searchable_hgvs)
    if deletion:
        seq = (deletion.group("seq") or "N").upper()
        if seq == "N":
            warnings.append("HGVS deletion omitted the deleted sequence; ref is unresolved as 'N'.")
            unresolved.append("ref")
        warnings.append("HGVS deletion cannot be fully VCF-normalized without a genomic anchor base.")
        unresolved.append("alt")
        return {"variant_type": VariantType.SMALL_DELETION, "ref": seq, "alt": "N"}

    duplication = HGVS_C_DUP_RE.search(searchable_hgvs)
    if duplication:
        seq = (duplication.group("seq") or "N").upper()
        if seq == "N":
            warnings.append("HGVS duplication omitted the duplicated sequence; inserted base is unresolved as 'N'.")
            unresolved.append("alt")
        warnings.append("HGVS duplication cannot be fully VCF-normalized without a genomic anchor base.")
        unresolved.append("ref")
        return {"variant_type": VariantType.SMALL_INSERTION, "ref": "N", "alt": f"N{seq}"}

    insertion = HGVS_C_INS_RE.search(searchable_hgvs)
    if insertion:
        seq = insertion.group("seq").upper()
        warnings.append("HGVS insertion cannot be fully VCF-normalized without a genomic anchor base.")
        unresolved.append("ref")
        return {"variant_type": VariantType.SMALL_INSERTION, "ref": "N", "alt": f"N{seq}"}

    delins = HGVS_C_DELINS_RE.search(searchable_hgvs)
    if delins:
        seq = delins.group("seq").upper()
        warnings.append("HGVS delins cannot be fully VCF-normalized without transcript-to-genome mapping.")
        unresolved.append("ref")
        return {"variant_type": VariantType.SMALL_DELINS, "ref": "N", "alt": seq}

    if re.search(r":?c\.", searchable_hgvs, re.I) and not re.search(
        r"(del|dup|ins|delins|>|inv|con|g\.)", searchable_hgvs, re.I
    ):
        raise NormalizationError(
            "Malformed HGVS-like c. expression.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=["hgvs_c"],
        )

    raise NormalizationError(
        "Only SNV and small indel HGVS-like c. substitutions, deletions, duplications, insertions, and delins are supported in phase 1.",
        code="UNSUPPORTED_VARIANT_TYPE",
        unresolved_fields=["ref", "alt"],
    )


def _build_variant(
    *,
    genome_build: GenomeBuild,
    variant_type: VariantType,
    chrom: str,
    pos: int,
    ref: str,
    alt: str,
    gene_symbol: str | None,
    hgvs_c: str | None,
    hgvs_p: str | None,
    hgvs_g: str | None,
    transcript: Transcript | None,
    warnings: list[str],
) -> Variant:
    variant_id = f"{genome_build}-{chrom}-{pos}-{ref}-{alt}"
    try:
        return Variant(
            variant_id=variant_id,
            genome_build=genome_build,
            variant_type=variant_type,
            chrom=chrom,
            pos=pos,
            ref=ref,
            alt=alt,
            gene_symbol=gene_symbol,
            transcript=transcript,
            hgvs_g=hgvs_g,
            hgvs_c=hgvs_c,
            hgvs_p=hgvs_p,
            normalization_warnings=warnings,
        )
    except ValidationError as exc:
        raise NormalizationError(
            "Normalized variant failed schema validation.",
            code="SCHEMA_VALIDATION_ERROR",
            warnings=warnings,
            unresolved_fields=[],
        ) from exc


def _transcript_from_fields(data: dict[str, Any], warnings: list[str]) -> Transcript | None:
    accession_value = _optional_str(data.get("transcript") or data.get("transcript_accession"))
    if not accession_value:
        return None

    match = TRANSCRIPT_RE.match(accession_value)
    accession = match.group("accession") if match else accession_value
    version = _optional_str(data.get("transcript_version"))
    if match and match.group("version"):
        version = version or match.group("version")

    gene_symbol = _optional_str(data.get("gene") or data.get("gene_symbol"))
    if not gene_symbol:
        gene_symbol = "unknown"
        warnings.append("Missing gene_symbol; transcript.gene_symbol set to 'unknown'.")

    return Transcript(
        accession=accession,
        version=version,
        gene_symbol=gene_symbol,
        hgvs_c=_optional_str(data.get("hgvs_c") or data.get("hgvs")),
        hgvs_p=_optional_str(data.get("hgvs_p")),
    )


def _classify_ref_alt(ref: str, alt: str) -> VariantType:
    if len(ref) == 1 and len(alt) == 1:
        return VariantType.SNV
    if len(ref) > len(alt):
        return VariantType.SMALL_DELETION
    if len(ref) < len(alt):
        return VariantType.SMALL_INSERTION
    return VariantType.SMALL_DELINS


def _reject_unsupported_ref_alt(ref: str, alt: str, variant_type: VariantType) -> None:
    if variant_type == VariantType.SNV and ref == alt:
        raise NormalizationError("Reference and alternate alleles are identical.", code="INVALID_ALLELE")
    if max(len(ref), len(alt)) > SMALL_INDEL_MAX_BP:
        raise NormalizationError(
            "Phase 1 supports SNV and small indel variants up to 50 bp only.",
            code="UNSUPPORTED_VARIANT_TYPE",
        )


def _genome_build(data: dict[str, Any]) -> GenomeBuild:
    raw = _optional_str(data.get("genome_build") or data.get("build")) or GenomeBuild.GRCH38
    try:
        return GenomeBuild(raw)
    except ValueError as exc:
        raise NormalizationError(
            "Unsupported genome_build. Use GRCh37 or GRCh38.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=["genome_build"],
        ) from exc


def _string_field(data: dict[str, Any], *names: str, required: bool = False) -> str:
    value = None
    for name in names:
        if name in data:
            value = data[name]
            break
    text = _optional_str(value)
    if text is None and required:
        raise NormalizationError(
            f"Missing required field '{names[0]}'.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=[names[0]],
        )
    return text or ""


def _int_field(data: dict[str, Any], *names: str, required: bool = False) -> int:
    value = None
    for name in names:
        if name in data:
            value = data[name]
            break
    if value is None and required:
        raise NormalizationError(
            f"Missing required field '{names[0]}'.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=[names[0]],
        )
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise NormalizationError(
            f"Field '{names[0]}' must be a positive integer.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=[names[0]],
        ) from exc
    if parsed < 1:
        raise NormalizationError(
            f"Field '{names[0]}' must be a positive integer.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=[names[0]],
        )
    return parsed


def _allele_field(data: dict[str, Any], name: str, required: bool = False) -> str:
    value = _optional_str(data.get(name))
    if not value and required:
        raise NormalizationError(
            f"Missing required field '{name}'.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=[name],
        )
    allele = (value or "").upper()
    if not ALLELE_RE.fullmatch(allele):
        raise NormalizationError(
            f"Field '{name}' must contain only A, C, G, T, or N bases.",
            code="INVALID_ALLELE",
            unresolved_fields=[name],
        )
    return allele


def _alt_field(data: dict[str, Any], required: bool = False) -> str:
    raw = data.get("alt")
    if isinstance(raw, list):
        if len(raw) != 1:
            raise NormalizationError(
                "Multi-allelic input is not supported in phase 1; submit one alternate allele at a time.",
                code="UNSUPPORTED_VARIANT_TYPE",
                unresolved_fields=["alt"],
            )
        raw = raw[0]
    text = _optional_str(raw)
    if text and "," in text:
        raise NormalizationError(
            "Multi-allelic input is not supported in phase 1; submit one alternate allele at a time.",
            code="UNSUPPORTED_VARIANT_TYPE",
            unresolved_fields=["alt"],
        )
    return _allele_field({"alt": text}, "alt", required=required)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
