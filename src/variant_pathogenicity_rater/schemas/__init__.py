"""Pydantic data contracts for SNV/small indel ACMG rating workflows."""

from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.annotation import (
    AnnotationParseResult,
    LofteeFlags,
    OnlineResolutionResult,
    VariantAnnotation,
)
from variant_pathogenicity_rater.schemas.classification import (
    ACMGClassification,
    ClassificationResult,
)
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.evidence import (
    ClinVarRecord,
    ComputationalPrediction,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    LiteratureCandidateEvidenceType,
    LiteratureClaim,
    LiteratureEvidence,
    LiteratureEvidenceQuality,
    LiteratureEvidenceType,
    PopulationFrequency,
    SplicePrediction,
)
from variant_pathogenicity_rater.schemas.report import (
    DataSourceSummary,
    EvidenceReportEntry,
    ReportFormat,
    ReportLanguage,
    ReportMode,
    VariantReport,
    VariantReportSummary,
)
from variant_pathogenicity_rater.schemas.variant import (
    GeneDiseaseContext,
    GenomeBuild,
    LastExonInformation,
    NormalizationResult,
    Transcript,
    Variant,
    VariantType,
    Zygosity,
)

__all__ = [
    "ACMGClassification",
    "AuditTrail",
    "AnnotationParseResult",
    "ClassificationResult",
    "ClinVarRecord",
    "ComputationalPrediction",
    "DataSourceSummary",
    "EvidenceCode",
    "EvidenceDirection",
    "EvidenceItem",
    "EvidenceReportEntry",
    "EvidenceSource",
    "EvidenceStrength",
    "GeneDiseaseContext",
    "GenomeBuild",
    "LiteratureCandidateEvidenceType",
    "LiteratureClaim",
    "LiteratureEvidence",
    "LiteratureEvidenceQuality",
    "LiteratureEvidenceType",
    "LastExonInformation",
    "LofteeFlags",
    "NormalizationResult",
    "OnlineResolutionResult",
    "PopulationFrequency",
    "ReportFormat",
    "ReportLanguage",
    "ReportMode",
    "ReviewFlag",
    "SplicePrediction",
    "Transcript",
    "Variant",
    "VariantAnnotation",
    "VariantReport",
    "VariantReportSummary",
    "VariantType",
    "Zygosity",
]
