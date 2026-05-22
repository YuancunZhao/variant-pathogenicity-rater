from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.annotation.resolvers import OnlineVariantNormalizer
from variant_pathogenicity_rater.schemas.common import ReviewFlag
from variant_pathogenicity_rater.schemas.variant import (
    GenomeBuild,
    NormalizationResult,
    Transcript,
    Variant,
    VariantIdentity,
    VariantType,
)

SUPPORTED_INPUT_FORMATS = {"hgvs", "vcf_like", "structured"}
SMALL_INDEL_MAX_BP = 50
ALLELE_RE = re.compile(r"^[ACGTN]+$", re.IGNORECASE)
CHROM_RE = re.compile(r"^(?:[1-9]|1[0-9]|2[0-2]|X|Y|M|MT|unresolved)$", re.I)
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


def normalize_variant(
    payload: dict[str, Any],
    *,
    online_normalizer: OnlineVariantNormalizer | None = None,
) -> NormalizationResult:
    """Normalize phase-1 HGVS-like or VCF-like variant input.

    This module deliberately avoids liftover, transcript mapping, and external API
    normalization. Fields that cannot be resolved locally are reported explicitly.
    """

    if not isinstance(payload, dict):
        raise NormalizationError("Variant normalization input must be a JSON object.")

    data = _unwrap_variant(payload)
    input_format = _detect_input_format(data)
    warnings: list[str] = []
    review_flags: list[str] = []
    limitations: list[str] = []
    unresolved: list[str] = []
    provenance: list[dict[str, Any]] = [
        {
            "source": "local_normalizer",
            "version": "hgvs-normalization-v2",
            "scope": "SNV/small-indel descriptive normalization",
            "input_hash": _input_hash(data),
        }
    ]

    if input_format == "vcf_like":
        variant = _normalize_vcf_like(data, warnings, review_flags, limitations, unresolved)
    elif input_format == "hgvs":
        variant = _normalize_hgvs_like(data, warnings, review_flags, limitations, unresolved)
    else:
        variant = _normalize_structured(data, warnings, review_flags, limitations, unresolved)

    _check_conflicts(data, variant, warnings, review_flags, limitations)
    _apply_online_normalizer(
        data,
        variant,
        warnings,
        review_flags,
        limitations,
        provenance,
        online_normalizer=online_normalizer,
    )
    identity = build_variant_identity(
        variant,
        original_input=data,
        normalization_status="normalized_with_review"
        if review_flags or unresolved
        else "normalized",
        unresolved_fields=_unique(unresolved),
        provenance=provenance,
    )

    return NormalizationResult(
        status="normalized",
        input_format=input_format,
        normalized_variant=variant,
        variant_identity=identity,
        normalization_warnings=_unique(warnings),
        review_flags=_review_flag_models(_unique(review_flags)),
        limitations=_unique(limitations),
        unresolved_fields=_unique(unresolved),
        provenance=provenance,
        human_review_required=True,
    )


def build_variant_identity(
    variant: Variant,
    *,
    original_input: dict[str, Any],
    normalization_status: str,
    unresolved_fields: list[str] | None = None,
    provenance: list[dict[str, Any]] | None = None,
) -> VariantIdentity:
    chrom = _normalize_chrom(variant.chrom)
    genomic_key = None
    if chrom != "unresolved" and variant.pos >= 1 and variant.ref and variant.alt:
        genomic_key = f"{chrom}-{variant.pos}-{variant.ref.upper()}-{variant.alt.upper()}"
    transcript = _transcript_label(variant.transcript)
    hgvs_key = f"{transcript}:{variant.hgvs_c}" if transcript and variant.hgvs_c else None
    protein_key = f"{transcript}:{variant.hgvs_p}" if transcript and variant.hgvs_p else None
    gene_variant_key = None
    if variant.gene_symbol:
        gene_variant_key = f"{variant.gene_symbol}:{hgvs_key or genomic_key or variant.variant_id}"
    normalized_key = genomic_key or hgvs_key or gene_variant_key or f"input:{_input_hash(original_input)}"
    return VariantIdentity(
        normalized_variant_key=normalized_key,
        genomic_key=genomic_key,
        hgvs_key=hgvs_key,
        protein_key=protein_key,
        gene_variant_key=gene_variant_key,
        input_hash=_input_hash(original_input),
        normalization_status=normalization_status,
        unresolved_fields=unresolved_fields or [],
        provenance=provenance or [],
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
    data: dict[str, Any],
    warnings: list[str],
    review_flags: list[str],
    limitations: list[str],
    unresolved: list[str],
) -> Variant:
    vcf = data.get("vcf", data)
    if not isinstance(vcf, dict):
        raise NormalizationError("The 'vcf' field must be an object.")

    chrom = _normalize_chrom(_string_field(vcf, "chrom", "chromosome", required=True))
    pos = _int_field(vcf, "pos", "position", required=True)
    ref = _allele_field(vcf, "ref", required=True)
    alt = _alt_field(vcf, required=True)
    genome_build = _genome_build(vcf)
    pos, ref, alt = _trim_ref_alt(pos, ref, alt, warnings)

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
    data: dict[str, Any],
    warnings: list[str],
    review_flags: list[str],
    limitations: list[str],
    unresolved: list[str],
) -> Variant:
    if all(key in data for key in ("chrom", "pos", "ref", "alt")) or all(
        key in data for key in ("chromosome", "position", "ref", "alt")
    ):
        return _normalize_vcf_like(data, warnings, review_flags, limitations, unresolved)
    if "hgvs_c" in data or "transcript" in data:
        return _normalize_hgvs_like(data, warnings, review_flags, limitations, unresolved)
    raise NormalizationError(
        "Input must include either VCF-like chrom/pos/ref/alt fields or HGVS-like transcript/hgvs_c fields.",
        code="SCHEMA_VALIDATION_ERROR",
        unresolved_fields=["input_type"],
    )


def _normalize_hgvs_like(
    data: dict[str, Any],
    warnings: list[str],
    review_flags: list[str],
    limitations: list[str],
    unresolved: list[str],
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
        limitations.append("Protein HGVS is missing; protein-level identity requires review.")
        unresolved.append("hgvs_p")

    parsed = _parse_hgvs_c(hgvs_c, warnings, unresolved)
    variant_type = parsed["variant_type"]
    ref = parsed["ref"]
    alt = parsed["alt"]
    _reject_unsupported_ref_alt(ref, alt, variant_type)

    if "chrom" in data or "chromosome" in data:
        chrom = _normalize_chrom(_string_field(data, "chrom", "chromosome", required=True))
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
    chrom = _normalize_chrom(chrom)
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


def _trim_ref_alt(pos: int, ref: str, alt: str, warnings: list[str]) -> tuple[int, str, str]:
    original = (pos, ref, alt)
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref = ref[:-1]
        alt = alt[:-1]
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref = ref[1:]
        alt = alt[1:]
        pos += 1
    if (pos, ref, alt) != original:
        warnings.append("Common ref/alt sequence was trimmed for stable small-variant identity.")
    return pos, ref, alt


def _normalize_chrom(chrom: str) -> str:
    value = chrom.strip()
    if value.lower().startswith("chr"):
        value = value[3:]
    if value in {"m", "M"}:
        value = "MT"
    elif value.upper() in {"X", "Y", "MT", "UNRESOLVED"}:
        value = value.upper().replace("UNRESOLVED", "unresolved")
    if not CHROM_RE.fullmatch(value):
        raise NormalizationError(
            "Chromosome must be 1-22, X, Y, M/MT, or chr-prefixed equivalent.",
            code="SCHEMA_VALIDATION_ERROR",
            unresolved_fields=["chrom"],
        )
    return value


def _check_conflicts(
    data: dict[str, Any],
    variant: Variant,
    warnings: list[str],
    review_flags: list[str],
    limitations: list[str],
) -> None:
    hgvs_c = _optional_str(data.get("hgvs_c") or data.get("hgvs"))
    transcript_value = _optional_str(data.get("transcript") or data.get("transcript_accession"))
    if hgvs_c and transcript_value and ":" in hgvs_c:
        hgvs_transcript = hgvs_c.split(":", 1)[0]
        if _normalize_transcript_label(hgvs_transcript) != _normalize_transcript_label(transcript_value):
            review_flags.append("TRANSCRIPT_MISMATCH")
            warnings.append("Transcript field does not match the transcript embedded in HGVS c.; review required.")

    if hgvs_c and variant.chrom != "unresolved" and variant.ref and variant.alt:
        try:
            parsed = _parse_hgvs_c(hgvs_c, [], [])
        except NormalizationError:
            parsed = None
        if parsed and (parsed["ref"] != variant.ref or parsed["alt"] != variant.alt):
            review_flags.append("HGVS_GENOMIC_MISMATCH")
            warnings.append("HGVS c. allele does not match genomic ref/alt after local normalization; review required.")

    gene = _optional_str(data.get("gene") or data.get("gene_symbol"))
    transcript_gene = variant.transcript.gene_symbol if variant.transcript else None
    if gene and transcript_gene and transcript_gene != "unknown" and gene.upper() != transcript_gene.upper():
        review_flags.append("GENE_MISMATCH")
        warnings.append("Input gene does not match transcript gene metadata; review required.")

    if not variant.hgvs_p:
        limitations.append("Protein HGVS is missing or unresolved; protein identity is incomplete.")


def _apply_online_normalizer(
    data: dict[str, Any],
    variant: Variant,
    warnings: list[str],
    review_flags: list[str],
    limitations: list[str],
    provenance: list[dict[str, Any]],
    *,
    online_normalizer: OnlineVariantNormalizer | None,
) -> None:
    requested = bool(data.get("online_normalization") or data.get("use_online_normalizer"))
    if online_normalizer is None and not requested:
        limitations.append("Online variant normalization was disabled by default; no network access was attempted.")
        provenance.append({"source": "online_variant_normalizer", "status": "disabled_by_default"})
        return
    resolver = online_normalizer or OnlineVariantNormalizer()
    result = resolver.resolve(_online_query(data, variant))
    limitations.extend(result.limitations)
    if result.provenance is not None:
        provenance.append(json.loads(result.provenance.model_dump_json()))
    if result.resolved is None:
        return
    provenance.append({"source": "online_variant_normalizer", "status": "candidate", "cache_hit": result.cache_hit})
    candidate = _extract_online_candidate(result.resolved)
    confidence = _online_confidence(result.resolved)
    if confidence < 0.9:
        review_flags.append("ONLINE_NORMALIZER_CANDIDATE_LOW_CONFIDENCE")
        warnings.append("Online normalizer result was retained as candidate context because confidence was not high.")
        return
    if candidate and _candidate_matches_variant(candidate, variant):
        provenance.append({"source": "online_variant_normalizer", "status": "confirmed_high_confidence"})
    else:
        review_flags.append("ONLINE_NORMALIZER_CONFLICT")
        warnings.append("High-confidence online normalizer candidate conflicted with user input; user input was preserved.")


def _online_query(data: dict[str, Any], variant: Variant) -> dict[str, Any]:
    return {
        "input": data,
        "genomic_key": f"{variant.chrom}-{variant.pos}-{variant.ref}-{variant.alt}",
        "hgvs_c": variant.hgvs_c,
        "hgvs_p": variant.hgvs_p,
        "gene_symbol": variant.gene_symbol,
    }


def _extract_online_candidate(resolved: dict[str, Any]) -> dict[str, Any] | None:
    record = resolved.get("record")
    if isinstance(record, dict):
        for key in ("normalized_variant", "variant", "candidate"):
            value = record.get(key)
            if isinstance(value, dict):
                return value
        return record
    return None


def _online_confidence(resolved: dict[str, Any]) -> float:
    record = resolved.get("record")
    raw = record.get("confidence") if isinstance(record, dict) else resolved.get("confidence")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.5


def _candidate_matches_variant(candidate: dict[str, Any], variant: Variant) -> bool:
    chrom = _optional_str(candidate.get("chrom") or candidate.get("chromosome"))
    pos = candidate.get("pos") or candidate.get("position")
    ref = _optional_str(candidate.get("ref"))
    alt = _optional_str(candidate.get("alt"))
    if not all((chrom, pos, ref, alt)):
        return False
    try:
        return (
            _normalize_chrom(chrom or "") == variant.chrom
            and int(pos) == variant.pos
            and ref.upper() == variant.ref
            and alt.upper() == variant.alt
        )
    except (TypeError, ValueError, NormalizationError):
        return False


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


def _transcript_label(transcript: Transcript | None) -> str | None:
    if transcript is None:
        return None
    return f"{transcript.accession}.{transcript.version}" if transcript.version else transcript.accession


def _normalize_transcript_label(transcript: str) -> str:
    return transcript.strip().upper()


def _input_hash(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _review_flag_models(codes: list[str]) -> list[ReviewFlag]:
    messages = {
        "TRANSCRIPT_MISMATCH": "Transcript field does not match the transcript embedded in HGVS c.",
        "HGVS_GENOMIC_MISMATCH": "HGVS c. allele does not match genomic ref/alt after local normalization.",
        "GENE_MISMATCH": "Input gene does not match transcript gene metadata.",
        "ONLINE_NORMALIZER_CANDIDATE_LOW_CONFIDENCE": "Online normalizer result requires review before use.",
        "ONLINE_NORMALIZER_CONFLICT": "Online normalizer candidate conflicts with preserved user input.",
    }
    return [
        ReviewFlag(
            code=code,
            message=messages.get(code, "Normalization result requires human review."),
            severity="warning",
            blocking=False,
        )
        for code in codes
    ]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
