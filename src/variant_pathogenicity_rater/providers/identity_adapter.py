from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.providers.identity import VariantIdentity, validate_gnomad_variant_id
from variant_pathogenicity_rater.schemas.common import ReviewFlag


IDENTITY_FIELDS = (
    "gene",
    "transcript",
    "hgvs_c",
    "hgvs_p",
    "hgvs_g",
    "genome_build",
    "chrom",
    "pos",
    "ref",
    "alt",
    "variant_id_grch37",
    "variant_id_grch38",
    "gnomad_variant_id",
    "clinvar_variation_id",
    "rsid",
    "caid",
    "protein_change",
    "consequence",
)
CONFLICT_FIELDS = ("gene", "transcript", "hgvs_c", "hgvs_p", "genome_build", "chrom", "pos", "ref", "alt")


def variant_identity_from_normalized_variant(normalized_variant: Any) -> VariantIdentity:
    variant = _payload(normalized_variant)
    transcript = _payload(variant.get("transcript"))
    identity = VariantIdentity(
        gene=variant.get("gene_symbol") or variant.get("gene"),
        transcript=_transcript_accession(transcript),
        hgvs_c=variant.get("hgvs_c") or transcript.get("hgvs_c"),
        hgvs_p=variant.get("hgvs_p") or transcript.get("hgvs_p"),
        hgvs_g=variant.get("hgvs_g"),
        genome_build=_enum_value(variant.get("genome_build")),
        chrom=variant.get("chrom"),
        pos=variant.get("pos"),
        ref=variant.get("ref"),
        alt=variant.get("alt"),
        protein_change=variant.get("hgvs_p") or transcript.get("hgvs_p"),
        consequence=transcript.get("consequence"),
        identity_confidence=0.75,
        provenance=[
            {
                "source": "normalized_variant",
                "scope": "provider identity only; not ACMG evidence",
            }
        ],
        limitations=[
            "Provider-layer VariantIdentity was derived from normalized_variant and is not ACMG evidence."
        ],
    )
    return validate_gnomad_variant_id(identity)


def variant_identity_from_resolution(variant_resolution: Any) -> VariantIdentity:
    resolution = _payload(variant_resolution)
    resolved_variant = _payload(resolution.get("resolved_variant"))
    resolved_transcript = _payload(resolution.get("resolved_transcript"))
    resolved_protein = _payload(resolution.get("resolved_hgvs_p"))
    resolved_coordinate = _payload(resolution.get("resolved_coordinate"))
    variant_transcript = _payload(resolved_variant.get("transcript"))

    identity = VariantIdentity(
        gene=resolved_variant.get("gene_symbol")
        or resolved_transcript.get("gene_symbol")
        or variant_transcript.get("gene_symbol"),
        transcript=_transcript_accession(resolved_transcript) or _transcript_accession(variant_transcript),
        hgvs_c=resolved_variant.get("hgvs_c") or variant_transcript.get("hgvs_c"),
        hgvs_p=resolved_protein.get("hgvs_p") or resolved_variant.get("hgvs_p") or variant_transcript.get("hgvs_p"),
        hgvs_g=resolved_coordinate.get("hgvs_g") or resolved_variant.get("hgvs_g"),
        genome_build=_enum_value(resolved_coordinate.get("genome_build") or resolved_variant.get("genome_build")),
        chrom=resolved_coordinate.get("chrom") or resolved_variant.get("chrom"),
        pos=resolved_coordinate.get("pos") or resolved_variant.get("pos"),
        ref=resolved_coordinate.get("ref") or resolved_variant.get("ref"),
        alt=resolved_coordinate.get("alt") or resolved_variant.get("alt"),
        protein_change=resolved_protein.get("hgvs_p") or resolved_variant.get("hgvs_p"),
        consequence=resolved_protein.get("consequence") or variant_transcript.get("consequence"),
        identity_confidence=float(resolution.get("confidence") or 0.0),
        provenance=[
            {
                "source": "variant_resolution",
                "outcome": resolution.get("outcome"),
                "status": resolution.get("status"),
                "scope": "provider identity only; not ACMG evidence",
            },
            *list(resolution.get("provenance") or []),
        ],
        limitations=[
            "Provider-layer VariantIdentity was derived from variant_resolution and is not ACMG evidence.",
            *[str(item) for item in resolution.get("limitations") or []],
        ],
        review_flags=[ReviewFlag.model_validate(flag) for flag in resolution.get("review_flags") or []],
    )
    return validate_gnomad_variant_id(identity)


def merge_variant_identities(
    base: VariantIdentity,
    update: VariantIdentity | dict[str, Any],
    source: str,
) -> VariantIdentity:
    update_identity = update if isinstance(update, VariantIdentity) else VariantIdentity.model_validate(update)
    payload = base.model_dump(mode="python")
    conflicts = list(base.identity_conflicts)
    limitations = list(base.limitations)
    review_flags = list(base.review_flags)
    provenance = [
        *base.provenance,
        {
            "source": source,
            "scope": "provider identity merge only; not ACMG evidence",
            "update_confidence": update_identity.identity_confidence,
        },
        *update_identity.provenance,
    ]

    for field in IDENTITY_FIELDS:
        base_value = getattr(base, field)
        update_value = getattr(update_identity, field)
        if _missing(update_value):
            continue
        if _missing(base_value):
            payload[field] = update_value
            continue
        if field in CONFLICT_FIELDS and _different(base_value, update_value):
            conflict = {
                "field": field,
                "base": base_value,
                "update": update_value,
                "source": source,
            }
            conflicts.append(conflict)
            limitations.append(
                f"Provider identity conflict for {field}: kept base value {base_value!r}; ignored {update_value!r} from {source}."
            )
            review_flags.append(
                ReviewFlag(
                    code=f"PROVIDER_IDENTITY_{field.upper()}_CONFLICT",
                    message=(
                        f"Provider identity conflict for {field}; base value was preserved and "
                        f"{source} value requires review."
                    ),
                    severity="warning",
                    blocking=False,
                )
            )
            continue
        if update_identity.identity_confidence > base.identity_confidence and field not in CONFLICT_FIELDS:
            payload[field] = update_value

    payload["identity_confidence"] = max(base.identity_confidence, update_identity.identity_confidence)
    payload["identity_conflicts"] = _unique_conflicts([*conflicts, *update_identity.identity_conflicts])
    payload["limitations"] = _unique([*limitations, *update_identity.limitations])
    payload["review_flags"] = _unique_review_flags([*review_flags, *update_identity.review_flags])
    payload["provenance"] = provenance
    return validate_gnomad_variant_id(VariantIdentity.model_validate(payload))


def build_variant_identity(
    normalized_variant: Any | None = None,
    variant_resolution: Any | None = None,
    explicit_aliases: dict[str, Any] | None = None,
) -> VariantIdentity:
    identity = (
        variant_identity_from_normalized_variant(normalized_variant)
        if normalized_variant is not None
        else VariantIdentity(
            identity_confidence=0.0,
            limitations=["No normalized_variant was available for provider-layer VariantIdentity."],
            provenance=[{"source": "provider_identity_empty", "scope": "provider identity only; not ACMG evidence"}],
        )
    )
    if variant_resolution is not None:
        identity = merge_variant_identities(
            identity,
            variant_identity_from_resolution(variant_resolution),
            source="variant_resolution",
        )
    if explicit_aliases:
        alias_payload = {key: value for key, value in explicit_aliases.items() if key in IDENTITY_FIELDS}
        identity = merge_variant_identities(
            identity,
            VariantIdentity.model_validate(
                {
                    **alias_payload,
                    "identity_confidence": float(explicit_aliases.get("identity_confidence") or 0.5),
                    "provenance": [
                        {
                            "source": "explicit_aliases",
                            "scope": "provider identity only; not ACMG evidence",
                        }
                    ],
                }
            ),
            source="explicit_aliases",
        )
    return validate_gnomad_variant_id(identity)


def _payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="python")
    return {}


def _transcript_accession(transcript: dict[str, Any]) -> str | None:
    if not transcript:
        return None
    accession = transcript.get("accession") or transcript.get("transcript")
    version = transcript.get("version")
    if accession and version and "." not in str(accession):
        return f"{accession}.{version}"
    return accession


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _missing(value: Any) -> bool:
    return value is None or value == "" or value == []


def _different(left: Any, right: Any) -> bool:
    return str(left).strip().casefold() != str(right).strip().casefold()


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


def _unique_conflicts(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    seen = set()
    for value in values:
        key = (value.get("field"), str(value.get("base")), str(value.get("update")), value.get("source"))
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _unique_review_flags(values: list[ReviewFlag]) -> list[ReviewFlag]:
    output = []
    seen = set()
    for value in values:
        key = (value.code, value.message)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output
