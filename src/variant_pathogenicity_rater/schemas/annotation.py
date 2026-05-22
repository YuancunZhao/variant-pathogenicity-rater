from __future__ import annotations

from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.data_sources.provenance import ProvenanceMetadata
from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


class LofteeFlags(SchemaModel):
    """Placeholder for future LOFTEE annotations without interpreting them as ACMG evidence."""

    lof: str | None = None
    lof_filter: str | None = None
    lof_flags: str | None = None
    lof_info: str | None = None


class VariantAnnotation(SchemaModel):
    gene: str | None = None
    transcript: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    consequence: str | None = None
    exon: str | None = None
    intron: str | None = None
    canonical: bool | None = None
    mane_select: bool | None = None
    transcript_biotype: str | None = None
    consequence_terms: list[str] = Field(default_factory=list)
    splice_region: bool | None = None
    loftee_flags: LofteeFlags = Field(default_factory=LofteeFlags)
    dbsnp_id: str | None = None
    annotation_source: str = Field(..., min_length=1)
    provenance: ProvenanceMetadata
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class AnnotationParseResult(SchemaModel):
    annotations: list[VariantAnnotation] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class TranscriptSelection(SchemaModel):
    selected_transcript: str | None = None
    selected_gene: str | None = None
    selection_reason: str = Field(..., min_length=1)
    selection_confidence: float = Field(..., ge=0, le=1)
    candidate_transcripts: list[dict[str, Any]] = Field(default_factory=list)
    rejected_transcripts: list[dict[str, Any]] = Field(default_factory=list)
    mane_select_available: bool = False
    canonical_available: bool = False
    biologically_relevant_available: bool = False
    user_transcript_provided: bool = False
    user_transcript_matched: bool = False
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class OnlineResolutionResult(SchemaModel):
    resolved: dict[str, Any] | None = None
    provenance: ProvenanceMetadata | None = None
    cache_hit: bool = False
    limitations: list[str] = Field(default_factory=list)
