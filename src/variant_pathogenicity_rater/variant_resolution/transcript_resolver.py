from __future__ import annotations

from variant_pathogenicity_rater.schemas.variant import Variant
from variant_pathogenicity_rater.transcript_support.validation import canonicalize_transcript
from variant_pathogenicity_rater.variant_resolution.schema import (
    ResolvedTranscript,
    VariantResolutionRecord,
)


def resolve_transcript(
    variant: Variant,
    record: VariantResolutionRecord | None,
) -> ResolvedTranscript:
    user_transcript = _variant_transcript(variant)
    embedded_transcript = _embedded_transcript(variant.hgvs_c)
    if user_transcript:
        norm = canonicalize_transcript(user_transcript)
        source = "hgvs_embedded" if embedded_transcript and embedded_transcript == user_transcript else "user_supplied"
        return ResolvedTranscript(
            transcript=user_transcript,
            accession=norm.accession,
            version=norm.version,
            gene_symbol=variant.gene_symbol,
            transcript_source=source,
            mane_status=record.mane_status if record else None,
            protein_accession=record.protein_accession if record else None,
            user_transcript_provided=True,
            user_transcript_preserved=True,
            suggestion_only=False,
            confidence=0.9 if record else 0.7,
            limitations=[] if record else ["No transcript resolution fixture matched the supplied transcript."],
            provenance=[_record_provenance(record)] if record else [],
        )
    if record and record.transcript:
        norm = canonicalize_transcript(record.transcript)
        status = (record.mane_status or "").lower()
        source = "mane_select_recommendation"
        if "plus" in status:
            source = "mane_plus_clinical_recommendation"
        elif "mane" in status:
            source = "mane_select_recommendation"
        elif record.canonical:
            source = "canonical_recommendation"
        return ResolvedTranscript(
            transcript=record.transcript,
            accession=norm.accession,
            version=norm.version,
            gene_symbol=record.gene,
            transcript_source=source,
            mane_status=record.mane_status,
            protein_accession=record.protein_accession,
            user_transcript_provided=False,
            user_transcript_preserved=True,
            suggestion_only=True,
            confidence=min(record.confidence, 0.75),
            limitations=["No user transcript was supplied; transcript is recommendation context only."],
            provenance=[_record_provenance(record)],
        )
    return ResolvedTranscript(
        gene_symbol=variant.gene_symbol,
        transcript_source="unknown",
        user_transcript_provided=False,
        user_transcript_preserved=True,
        suggestion_only=True,
        confidence=0.0,
        limitations=["Transcript could not be resolved from local fixtures."],
    )


def _variant_transcript(variant: Variant) -> str | None:
    if variant.transcript is None:
        return None
    if variant.transcript.version:
        return f"{variant.transcript.accession}.{variant.transcript.version}"
    return variant.transcript.accession


def _embedded_transcript(hgvs_c: str | None) -> str | None:
    if hgvs_c and ":" in hgvs_c:
        return hgvs_c.split(":", 1)[0]
    return None


def _record_provenance(record: VariantResolutionRecord | None) -> dict:
    if record is None:
        return {}
    return {
        "source": record.source,
        "source_version": record.source_version,
        "raw_snapshot_ref": record.raw_snapshot_ref,
        **record.provenance,
    }
