from __future__ import annotations

import re
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


SUPPORTED_GNOMAD_BUILDS = {"GRCh38"}
PLACEHOLDER_VALUES = {"", ".", "?", "unknown", "unresolved", "placeholder", "none", "null", "n"}
ALLELE_RE = re.compile(r"^[ACGT]+$", re.IGNORECASE)


class VariantIdentity(SchemaModel):
    """Provider-layer variant identity contract.

    This is separate from ``schemas.variant.VariantIdentity`` and is used only
    to describe provider query identity and aliases. It is not ACMG evidence.
    """

    gene: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    hgvs_g: str | None = None
    genome_build: str | None = None
    chrom: str | None = None
    pos: int | None = Field(default=None, ge=1)
    ref: str | None = None
    alt: str | None = None
    variant_id_grch37: str | None = None
    variant_id_grch38: str | None = None
    gnomad_variant_id: str | None = None
    clinvar_variation_id: str | None = None
    rsid: str | None = None
    caid: str | None = None
    protein_change: str | None = None
    consequence: str | None = None
    identity_confidence: float = Field(default=0.0, ge=0, le=1)
    identity_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)


def build_gnomad_variant_id(identity: VariantIdentity) -> str | None:
    """Build a gnomAD variant ID from validated provider identity fields."""

    validated = validate_gnomad_variant_id(identity)
    return validated.gnomad_variant_id


def validate_gnomad_variant_id(identity: VariantIdentity) -> VariantIdentity:
    """Return an identity copy with gnomAD ID populated only when valid."""

    limitations = list(identity.limitations)
    gnomad_variant_id = None
    missing = [
        field
        for field in ("genome_build", "chrom", "pos", "ref", "alt")
        if not getattr(identity, field)
    ]
    if missing:
        limitations.append(
            "gnomAD variant ID was not generated because required identity fields are missing: "
            + ", ".join(missing)
            + "."
        )
        return identity.model_copy(update={"gnomad_variant_id": None, "limitations": _unique(limitations)})

    genome_build = str(identity.genome_build)
    if genome_build not in SUPPORTED_GNOMAD_BUILDS:
        limitations.append(
            f"gnomAD variant ID was not generated because genome_build={genome_build} is not supported by this provider-layer validation."
        )
        return identity.model_copy(update={"gnomad_variant_id": None, "limitations": _unique(limitations)})

    chrom = _normalize_chrom(identity.chrom)
    ref = _normalize_allele(identity.ref)
    alt = _normalize_allele(identity.alt)
    invalid_parts = []
    if not chrom:
        invalid_parts.append("chrom")
    if identity.pos is None or int(identity.pos) < 1:
        invalid_parts.append("pos")
    if not _valid_allele(ref):
        invalid_parts.append("ref")
    if not _valid_allele(alt):
        invalid_parts.append("alt")
    if invalid_parts:
        limitations.append(
            "gnomAD variant ID was not generated because identity fields failed basic grammar: "
            + ", ".join(invalid_parts)
            + "."
        )
        return identity.model_copy(update={"gnomad_variant_id": None, "limitations": _unique(limitations)})

    gnomad_variant_id = f"{chrom}-{int(identity.pos)}-{ref}-{alt}"
    update: dict[str, Any] = {
        "chrom": chrom,
        "ref": ref,
        "alt": alt,
        "gnomad_variant_id": gnomad_variant_id,
        "variant_id_grch38": identity.variant_id_grch38 or gnomad_variant_id,
        "limitations": _unique(limitations),
    }
    return identity.model_copy(update=update)


def identity_aliases_for_clinvar(identity: VariantIdentity) -> list[str]:
    aliases = [
        identity.clinvar_variation_id,
        identity.rsid,
        identity.caid,
        identity.hgvs_c,
        identity.hgvs_p,
        identity.protein_change,
        identity.hgvs_g,
        _transcript_hgvs(identity),
        _coordinate_alias(identity),
        _gene_hgvs(identity),
    ]
    return _unique_aliases(aliases)


def identity_aliases_for_vep(identity: VariantIdentity) -> list[str]:
    aliases = [
        identity.hgvs_c,
        _transcript_hgvs(identity),
        identity.hgvs_g,
        _coordinate_alias(identity),
        identity.gnomad_variant_id,
    ]
    return _unique_aliases(aliases)


def identity_aliases_for_literature(identity: VariantIdentity) -> list[str]:
    aliases = [
        identity.gene,
        identity.hgvs_c,
        _transcript_hgvs(identity),
        identity.hgvs_p,
        identity.protein_change,
        identity.rsid,
        identity.caid,
        identity.clinvar_variation_id,
        _gene_hgvs(identity),
    ]
    return _unique_aliases(aliases)


def _normalize_chrom(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if _placeholder(text):
        return None
    if text.lower().startswith("chr"):
        text = text[3:]
    return text or None


def _normalize_allele(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if _placeholder(text):
        return None
    return text


def _valid_allele(value: str | None) -> bool:
    return bool(value and ALLELE_RE.match(value))


def _placeholder(value: Any) -> bool:
    return str(value).strip().lower() in PLACEHOLDER_VALUES


def _coordinate_alias(identity: VariantIdentity) -> str | None:
    chrom = _normalize_chrom(identity.chrom)
    ref = _normalize_allele(identity.ref)
    alt = _normalize_allele(identity.alt)
    if not all((identity.genome_build, chrom, identity.pos, ref, alt)):
        return None
    return f"{identity.genome_build}:{chrom}:{identity.pos}:{ref}>{alt}"


def _transcript_hgvs(identity: VariantIdentity) -> str | None:
    if not identity.transcript or not identity.hgvs_c:
        return None
    if str(identity.hgvs_c).startswith(str(identity.transcript)):
        return identity.hgvs_c
    return f"{identity.transcript}:{identity.hgvs_c}"


def _gene_hgvs(identity: VariantIdentity) -> str | None:
    if not identity.gene or not identity.hgvs_c:
        return None
    return f"{identity.gene} {identity.hgvs_c}"


def _unique_aliases(values: list[Any]) -> list[str]:
    aliases = []
    seen = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        aliases.append(text)
    return aliases


def _unique(values: list[str]) -> list[str]:
    output = []
    seen = set()
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
