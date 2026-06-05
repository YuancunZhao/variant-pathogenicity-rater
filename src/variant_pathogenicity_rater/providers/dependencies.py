from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.providers.identity import (
    VariantIdentity,
    identity_aliases_for_clinvar,
    identity_aliases_for_literature,
    identity_aliases_for_vep,
    validate_gnomad_variant_id,
)
from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


class ProviderDependencyStatus(StrEnum):
    SATISFIED = "satisfied"
    MISSING_IDENTITY = "missing_identity"
    INVALID_IDENTITY = "invalid_identity"
    UNSUPPORTED_IDENTITY = "unsupported_identity"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


class ProviderDependency(SchemaModel):
    provider_name: str = Field(..., min_length=1)
    required_fields: list[str] = Field(default_factory=list)
    accepted_aliases: list[str] = Field(default_factory=list)


class ProviderDependencyCheck(SchemaModel):
    provider_name: str = Field(..., min_length=1)
    required_fields: list[str] = Field(default_factory=list)
    satisfied: bool = False
    status: ProviderDependencyStatus = ProviderDependencyStatus.UNKNOWN
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    skip_reason: str | None = None
    identity_snapshot: dict[str, Any] = Field(default_factory=dict)


def check_gnomad_dependency(identity: VariantIdentity) -> ProviderDependencyCheck:
    validated = validate_gnomad_variant_id(identity)
    required = ["genome_build", "chrom", "pos", "ref", "alt", "gnomad_variant_id"]
    if validated.gnomad_variant_id:
        return _check(
            "gnomad",
            required,
            True,
            ProviderDependencyStatus.SATISFIED,
            identity=validated,
        )

    status = ProviderDependencyStatus.INVALID_IDENTITY
    missing = [field for field in ("genome_build", "chrom", "pos", "ref", "alt") if not getattr(identity, field)]
    if missing:
        status = ProviderDependencyStatus.MISSING_IDENTITY
    elif identity.genome_build and str(identity.genome_build) != "GRCh38":
        status = ProviderDependencyStatus.UNSUPPORTED_IDENTITY
    reason = (
        "gnomAD dependency was not satisfied because provider-layer identity is not suitable "
        "for a validated gnomAD variant_id."
    )
    return _check(
        "gnomad",
        required,
        False,
        status,
        identity=validated,
        skip_reason=reason,
        limitations=[
            reason,
            *validated.limitations,
            "gnomAD provider was skipped before GraphQL; skipped is not no_record and cannot trigger PM2.",
        ],
    )


def check_vep_dependency(identity: VariantIdentity) -> ProviderDependencyCheck:
    coordinate_valid = all((identity.genome_build, identity.chrom, identity.pos, identity.ref, identity.alt))
    aliases = identity_aliases_for_vep(identity)
    hgvs_available = bool(identity.hgvs_c or identity.hgvs_g or any(":" in alias and "c." in alias for alias in aliases))
    if coordinate_valid or hgvs_available:
        return _check(
            "vep",
            ["coordinate_or_hgvs"],
            True,
            ProviderDependencyStatus.SATISFIED,
            identity=identity,
        )
    reason = "VEP dependency was not satisfied because neither usable coordinate nor HGVS alias was available."
    return _check(
        "vep",
        ["coordinate_or_hgvs"],
        False,
        ProviderDependencyStatus.MISSING_IDENTITY,
        identity=identity,
        skip_reason=reason,
        limitations=[reason, "VEP provider was skipped before request; skipped is not a provider no_record."],
    )


def check_clinvar_dependency(identity: VariantIdentity) -> ProviderDependencyCheck:
    aliases = identity_aliases_for_clinvar(identity)
    if aliases:
        return _check(
            "clinvar",
            ["clinvar_alias"],
            True,
            ProviderDependencyStatus.SATISFIED,
            identity=identity,
        )
    reason = "ClinVar dependency was not satisfied because no Variation ID, rsID, HGVS, gene+HGVS, or coordinate alias was available."
    return _check(
        "clinvar",
        ["clinvar_alias"],
        False,
        ProviderDependencyStatus.MISSING_IDENTITY,
        identity=identity,
        skip_reason=reason,
        limitations=[reason, "ClinVar provider was skipped before query; skipped is not no_record."],
    )


def check_literature_dependency(
    identity: VariantIdentity,
    *,
    explicit_query: str | None = None,
    pmids: list[str] | None = None,
) -> ProviderDependencyCheck:
    aliases = identity_aliases_for_literature(identity)
    if identity.gene or aliases or explicit_query or pmids:
        return _check(
            "literature",
            ["gene_or_variant_alias_or_query"],
            True,
            ProviderDependencyStatus.SATISFIED,
            identity=identity,
        )
    reason = "Literature dependency was not satisfied because no gene, variant alias, search query, or PMID was available."
    return _check(
        "literature",
        ["gene_or_variant_alias_or_query"],
        False,
        ProviderDependencyStatus.MISSING_IDENTITY,
        identity=identity,
        skip_reason=reason,
        limitations=[reason, "Literature provider was skipped before query; skipped is not no_record."],
    )


def dependency_skip_payload(check: ProviderDependencyCheck) -> dict[str, Any]:
    return {
        "records": [],
        "limitations": list(check.limitations),
        "review_flags": [flag.model_dump(mode="json") for flag in check.review_flags],
        "provider_dependency": check.model_dump(mode="json"),
        "provenance": {
            "provider_dependency": check.model_dump(mode="json"),
            "provider_mode": "dependency_skipped",
            "query": {"identity_snapshot": check.identity_snapshot},
        },
    }


def _check(
    provider_name: str,
    required_fields: list[str],
    satisfied: bool,
    status: ProviderDependencyStatus,
    *,
    identity: VariantIdentity,
    skip_reason: str | None = None,
    limitations: list[str] | None = None,
) -> ProviderDependencyCheck:
    review_flags = []
    if not satisfied:
        review_flags.append(
            ReviewFlag(
                code=f"PROVIDER_DEPENDENCY_{provider_name.upper()}_{str(status).upper()}",
                message=skip_reason or f"{provider_name} provider dependency was not satisfied.",
                severity="warning",
                blocking=False,
            )
        )
    return ProviderDependencyCheck(
        provider_name=provider_name,
        required_fields=required_fields,
        satisfied=satisfied,
        status=status,
        limitations=_unique(limitations or []),
        review_flags=review_flags,
        skip_reason=skip_reason,
        identity_snapshot=identity.model_dump(mode="json"),
    )


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
