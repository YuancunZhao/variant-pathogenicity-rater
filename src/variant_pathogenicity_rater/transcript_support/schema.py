from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel


TranscriptValidationStatus = Literal["ok", "warning", "conflict", "insufficient"]


class CanonicalTranscript(SchemaModel):
    raw: str | None = None
    accession: str | None = None
    version: str | None = None
    source_family: Literal["refseq", "ensembl", "unknown"] = "unknown"


class TranscriptMetadata(SchemaModel):
    gene: str = Field(..., min_length=1)
    transcript: str = Field(..., min_length=1)
    transcript_version: str | None = None
    mane_status: str | None = None
    canonical: bool = False
    protein_coding: bool = False
    exon_count: int | None = Field(default=None, ge=1)
    cds_length: int | None = Field(default=None, ge=0)
    transcript_source: str = Field(..., min_length=1)
    genome_build: str = Field(..., min_length=1)
    protein_accession: str | None = None
    transcript_status: str = Field(..., min_length=1)
    nmd_relevance: str | None = None
    tags: list[str] = Field(default_factory=list)
    source_version: str | None = None
    parser_version: str = Field(..., min_length=1)
    raw_snapshot_ref: str | None = None
    retrieval_timestamp: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_fixture_provenance(self) -> TranscriptMetadata:
        if not self.source_version:
            self.provenance.setdefault("limitations", []).append(
                "Transcript fixture source_version is missing."
            )
        return self


class TranscriptValidationResult(SchemaModel):
    status: TranscriptValidationStatus = "insufficient"
    input_transcript: str | None = None
    normalized_input: CanonicalTranscript = Field(default_factory=CanonicalTranscript)
    matched_record: dict[str, Any] | None = None
    mane_select_candidates: list[dict[str, Any]] = Field(default_factory=list)
    canonical_candidates: list[dict[str, Any]] = Field(default_factory=list)
    protein_accession_match: bool | None = None
    protein_accession_expected: str | None = None
    protein_accession_observed: str | None = None
    user_transcript_provided: bool = False
    user_transcript_preserved: bool = True
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
