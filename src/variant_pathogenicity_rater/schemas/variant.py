from __future__ import annotations

from enum import StrEnum

from pydantic import AliasChoices, Field, model_validator

from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag, SchemaModel


class GenomeBuild(StrEnum):
    GRCH37 = "GRCh37"
    GRCH38 = "GRCh38"


class VariantType(StrEnum):
    SNV = "snv"
    SMALL_INSERTION = "small_insertion"
    SMALL_DELETION = "small_deletion"
    SMALL_DELINS = "small_delins"


class Zygosity(StrEnum):
    HETEROZYGOUS = "heterozygous"
    HOMOZYGOUS = "homozygous"
    HEMIZYGOUS = "hemizygous"
    UNKNOWN = "unknown"


class Transcript(SchemaModel):
    accession: str = Field(..., min_length=1)
    version: str | None = None
    gene_symbol: str = Field(..., min_length=1)
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    exon: str | None = None
    consequence: str | None = None
    mane_select: bool = False
    canonical: bool = False


class LastExonInformation(SchemaModel):
    is_in_last_exon: bool | None = None
    is_in_penultimate_exon: bool | None = None
    exon_number: int | None = Field(default=None, ge=1)
    total_exons: int | None = Field(default=None, ge=1)
    distance_to_last_exon_junction: int | None = None
    within_terminal_region: bool | None = None
    predicted_to_escape_nmd: bool | None = None
    affects_critical_region: bool | None = None


class Variant(SchemaModel):
    variant_id: str = Field(..., min_length=1)
    genome_build: GenomeBuild
    variant_type: VariantType
    chrom: str = Field(..., min_length=1)
    pos: int = Field(..., ge=1)
    ref: str = Field(..., min_length=1)
    alt: str = Field(..., min_length=1)
    gene_symbol: str | None = None
    transcript: Transcript | None = None
    hgvs_g: str | None = None
    hgvs_c: str | None = None
    hgvs_p: str | None = None
    zygosity: Zygosity = Zygosity.UNKNOWN
    normalization_warnings: list[str] = Field(default_factory=list)
    review_flags: list[ReviewFlag] = Field(default_factory=list)
    audit_trail: list[AuditTrail] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_phase_one_variant_type(self) -> Variant:
        ref_len = len(self.ref)
        alt_len = len(self.alt)
        if self.variant_type == VariantType.SNV and (ref_len != 1 or alt_len != 1):
            raise ValueError("SNV variants must have one-base ref and alt alleles.")
        if self.variant_type != VariantType.SNV and max(ref_len, alt_len) > 50:
            raise ValueError("Phase 1 supports small indels up to 50 bp only.")
        return self


class NormalizationResult(SchemaModel):
    status: str = Field(..., pattern="^(normalized|rejected)$")
    input_format: str = Field(..., min_length=1)
    normalized_variant: Variant | None = None
    normalization_warnings: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class GeneDiseaseContext(SchemaModel):
    gene_symbol: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("gene_symbol", "gene"),
    )
    disease_name: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("disease_name", "disease"),
    )
    disease_id: str | None = None
    inheritance_mode: str | None = Field(
        default=None,
        validation_alias=AliasChoices("inheritance_mode", "inheritance"),
    )
    disease_prevalence: float | None = Field(default=None, ge=0, le=1)
    population_ancestry: str | None = None
    phenotype_terms: list[str] = Field(default_factory=list)
    transcript: Transcript | None = None
    lof_is_known_mechanism: bool | None = None
    transcript_is_biologically_relevant: bool | None = None
    last_exon_information: LastExonInformation | None = None
    nmd_prediction_available: bool = False
    nmd_predicted: bool | None = None
    source: str | None = None
    audit_trail: list[AuditTrail] = Field(default_factory=list)
