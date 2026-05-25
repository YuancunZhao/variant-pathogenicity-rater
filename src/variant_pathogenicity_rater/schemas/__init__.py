"""Pydantic data contracts for SNV/small indel ACMG rating workflows."""

from __future__ import annotations

from typing import Any

_EXPORT_MODULES = {
    "ACMGClassification": "classification",
    "AnnotationParseResult": "annotation",
    "AuditTrail": "common",
    "BatchRecordError": "batch",
    "BatchResult": "batch",
    "BatchSummary": "batch",
    "BatchVariantResult": "batch",
    "ClassificationResult": "classification",
    "ClinVarRecord": "evidence",
    "ContextConsistency": "consistency",
    "ContextConsistencyCheck": "consistency",
    "ComputationalPrediction": "evidence",
    "DataSourceSummary": "report",
    "EvidenceCode": "acmg",
    "EvidenceDirection": "evidence",
    "EvidenceItem": "evidence",
    "EvidenceReportEntry": "report",
    "EvidenceSource": "evidence",
    "EvidenceStrength": "evidence",
    "FailedBatchRecord": "batch",
    "GeneDiseaseContext": "variant",
    "GenomeBuild": "variant",
    "LastExonInformation": "variant",
    "LiteratureCandidateEvidenceType": "evidence",
    "LiteratureClaim": "evidence",
    "LiteratureEvidence": "evidence",
    "LiteratureEvidenceQuality": "evidence",
    "LiteratureEvidenceType": "evidence",
    "LofteeFlags": "annotation",
    "NormalizationResult": "variant",
    "OnlineResolutionResult": "annotation",
    "PopulationFrequency": "evidence",
    "ReportFormat": "report",
    "ReportLanguage": "report",
    "ReportMode": "report",
    "ReviewFlag": "common",
    "SplicePrediction": "evidence",
    "Transcript": "variant",
    "TranscriptSelection": "annotation",
    "Variant": "variant",
    "VariantAnnotation": "annotation",
    "VariantIdentity": "variant",
    "VariantReport": "report",
    "VariantReportSummary": "report",
    "VariantType": "variant",
    "Zygosity": "variant",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    try:
        module_name = _EXPORT_MODULES[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    from importlib import import_module

    value = getattr(import_module(f"{__name__}.{module_name}"), name)
    globals()[name] = value
    return value
