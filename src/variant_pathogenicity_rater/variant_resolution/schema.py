from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import ReviewFlag, SchemaModel
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


ResolutionStatus = Literal["resolved", "partial", "unresolved", "error"]
ResolutionOutcome = Literal["success", "partial", "no_record", "failure", "skipped"]
TranscriptSource = Literal[
    "user_supplied",
    "hgvs_embedded",
    "mane_select_recommendation",
    "mane_plus_clinical_recommendation",
    "canonical_recommendation",
    "fixture",
    "unknown",
]
NMDStatus = Literal["NMD_expected", "NMD_unlikely", "unknown"]


class ResolutionStep(SchemaModel):
    step_name: str = Field(..., min_length=1)
    status: ResolutionStatus
    confidence: float = Field(default=0.0, ge=0, le=1)
    message: str | None = None
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ResolvedTranscript(SchemaModel):
    transcript: str | None = None
    accession: str | None = None
    version: str | None = None
    gene_symbol: str | None = None
    transcript_source: TranscriptSource = "unknown"
    mane_status: str | None = None
    transcript_status: Literal["validated", "alternative", "unverified", "unresolved"] = "unverified"
    canonical_status: Literal["validated", "alternative", "unverified", "unresolved"] = "unverified"
    protein_accession: str | None = None
    user_transcript_provided: bool = False
    user_transcript_preserved: bool = True
    suggestion_only: bool = False
    confidence: float = Field(default=0.0, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ResolvedProtein(SchemaModel):
    hgvs_p: str | None = None
    protein_accession: str | None = None
    consequence: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ResolvedCoordinate(SchemaModel):
    genome_build: str | None = None
    chrom: str | None = None
    pos: int | None = Field(default=None, ge=1)
    ref: str | None = None
    alt: str | None = None
    hgvs_g: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class ExonContext(SchemaModel):
    exon_number: int | None = Field(default=None, ge=1)
    total_exons: int | None = Field(default=None, ge=1)
    cds_position: int | None = Field(default=None, ge=0)
    last_exon: bool | None = None
    penultimate_exon: bool | None = None
    distance_to_last_exon_junction: int | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class NMDContext(SchemaModel):
    status: NMDStatus = "unknown"
    nmd_expected: bool | None = None
    nmd_unlikely: bool | None = None
    nmd_confidence: float = Field(default=0.0, ge=0, le=1)
    limitations: list[str] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class VariantResolutionRecord(SchemaModel):
    gene: str = Field(..., min_length=1)
    hgvs_c: str = Field(..., min_length=1)
    transcript: str | None = None
    mane_status: str | None = None
    canonical: bool = False
    protein_accession: str | None = None
    hgvs_p: str | None = None
    consequence: str | None = None
    genome_build: str | None = None
    chrom: str | None = None
    pos: int | None = Field(default=None, ge=1)
    ref: str | None = None
    alt: str | None = None
    hgvs_g: str | None = None
    exon_number: int | None = Field(default=None, ge=1)
    total_exons: int | None = Field(default=None, ge=1)
    cds_position: int | None = Field(default=None, ge=0)
    distance_to_last_exon_junction: int | None = None
    nmd_status: NMDStatus | None = None
    source: str = Field(default="local_transcript_resolution_fixture", min_length=1)
    source_version: str | None = None
    raw_snapshot_ref: str | None = None
    confidence: float = Field(default=0.9, ge=0, le=1)
    provenance: dict[str, Any] = Field(default_factory=dict)


class VariantResolutionResult(SchemaModel):
    status: ResolutionStatus
    outcome: ResolutionOutcome = "skipped"
    confidence: float = Field(default=0.0, ge=0, le=1)
    resolved_transcript: ResolvedTranscript | None = None
    resolved_hgvs_p: ResolvedProtein | None = None
    resolved_coordinate: ResolvedCoordinate | None = None
    exon_context: ExonContext | None = None
    nmd_context: NMDContext | None = None
    limitations: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    resolution_steps: list[ResolutionStep] = Field(default_factory=list)
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    resolution_runtime: dict[str, Any] = Field(default_factory=dict)
    resolved_variant: Variant | None = None
    resolved_context: GeneDiseaseContext | None = None
