from __future__ import annotations

from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.schemas.common import SchemaModel


class ComputationalEvidenceThresholds(SchemaModel):
    """Configurable cutoffs for PP3/BP4 computational evidence."""

    min_pathogenic_supporting_tools: int = Field(default=2, ge=1)
    min_benign_supporting_tools: int = Field(default=2, ge=1)
    revel_pathogenic: float = Field(default=0.75, ge=0, le=1)
    revel_benign: float = Field(default=0.15, ge=0, le=1)
    cadd_pathogenic: float = Field(default=20.0, ge=0)
    cadd_benign: float = Field(default=10.0, ge=0)
    sift_pathogenic: float = Field(default=0.05, ge=0, le=1)
    sift_benign: float = Field(default=0.05, ge=0, le=1)
    polyphen2_pathogenic: float = Field(default=0.85, ge=0, le=1)
    polyphen2_benign: float = Field(default=0.15, ge=0, le=1)
    spliceai_pathogenic: float = Field(default=0.5, ge=0, le=1)
    spliceai_benign: float = Field(default=0.1, ge=0, le=1)


class PopulationRuleThresholds(SchemaModel):
    """Configurable cutoffs for BA1/BS1/PM2 population evidence."""

    disease_specific: bool = False
    penetrance_provided: bool = False
    ba1_af_threshold: float = Field(default=0.05, ge=0, le=1)
    bs1_af_threshold: float = Field(default=0.01, ge=0, le=1)
    pm2_af_threshold: float = Field(default=0.0001, ge=0, le=1)
    min_allele_number: int = Field(default=2000, ge=0)
    high_confidence: float = Field(default=0.9, ge=0, le=1)
    missing_context_confidence_penalty: float = Field(default=0.2, ge=0, le=1)
    warning_confidence_penalty: float = Field(default=0.1, ge=0, le=1)
    founder_populations: list[str] = Field(
        default_factory=lambda: [
            "ashkenazi",
            "finnish",
            "amish",
            "acadian",
            "french canadian",
            "icelandic",
            "sardinian",
        ]
    )


def computational_thresholds_from_options(
    options: dict[str, Any] | None,
) -> ComputationalEvidenceThresholds:
    if not options:
        return ComputationalEvidenceThresholds()
    return ComputationalEvidenceThresholds.model_validate(options)


def population_thresholds_from_options(
    options: dict[str, Any] | None,
) -> PopulationRuleThresholds:
    if not options:
        return PopulationRuleThresholds()
    return PopulationRuleThresholds.model_validate(options)
