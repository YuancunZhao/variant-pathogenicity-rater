from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.consistency import (
    ContextConsistency,
    ContextConsistencyCheck,
    ConsistencySeverity,
)
from variant_pathogenicity_rater.schemas.evidence import (
    ClinVarRecord,
    LiteratureEvidence,
    PopulationFrequency,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant, VariantType
from variant_pathogenicity_rater.transcript_support.schema import TranscriptValidationResult


TRANSCRIPT_PREFIX_RE = re.compile(r"(?P<prefix>[A-Z]{2}_[0-9]+(?:\.[0-9]+)?):")
MISSING_DISEASE_VALUES = {"", "not provided", "unknown", "unspecified", "not specified", "none"}


def evaluate_context_consistency(
    variant: Variant,
    gene_disease_context: GeneDiseaseContext | None = None,
    *,
    annotation_records: list[VariantAnnotation] | None = None,
    transcript_selection: TranscriptSelection | None = None,
    transcript_validation: TranscriptValidationResult | None = None,
    clinvar_records: list[ClinVarRecord] | None = None,
    population_records: list[PopulationFrequency] | None = None,
    literature_records: list[LiteratureEvidence] | None = None,
) -> ContextConsistency:
    annotations = annotation_records or []
    clinvar = clinvar_records or []
    populations = population_records or []
    literature = literature_records or []
    checks: list[ContextConsistencyCheck] = []

    _check_gene_context(checks, variant, gene_disease_context, annotations)
    _check_transcript_context(checks, variant, gene_disease_context, annotations, transcript_selection)
    _check_transcript_validation(checks, transcript_validation)
    _check_hgvs_prefixes(checks, variant, annotations)
    _check_protein_hgvs_ambiguity(checks, variant, annotations)
    _check_consequence_vs_variant_type(checks, variant, annotations)
    _check_clinvar_condition(checks, gene_disease_context, clinvar)
    _check_population_context(checks, variant, gene_disease_context, populations)
    _check_inheritance(checks, gene_disease_context)
    _check_provider_builds(checks, variant, annotations, clinvar, populations, literature)
    _check_missing_disease_attempts(checks, gene_disease_context, populations)

    conflicts = [check for check in checks if check.severity == "conflict"]
    warnings = [check for check in checks if check.severity == "warning"]
    insufficient = [check for check in checks if check.severity == "insufficient"]
    if conflicts:
        status = "conflict"
    elif warnings:
        status = "warning"
    elif insufficient:
        status = "insufficient"
    else:
        status = "ok"

    return ContextConsistency(
        status=status,
        checks=checks,
        conflicts=conflicts,
        warnings=[*warnings, *insufficient],
        limitations=_limitations(conflicts, warnings, insufficient),
        review_required=status != "ok",
        provenance=[
            {
                "checker": "context_consistency_v1",
                "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                "annotation_record_count": len(annotations),
                "clinvar_record_count": len(clinvar),
                "population_record_count": len(populations),
                "literature_record_count": len(literature),
                "transcript_validation_status": transcript_validation.status if transcript_validation else None,
                "scope": "context validation only; not ACMG evidence",
            }
        ],
    )


def _check_gene_context(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    context: GeneDiseaseContext | None,
    annotations: list[VariantAnnotation],
) -> None:
    expected = _norm_gene(variant.gene_symbol or (context.gene_symbol if context else None))
    observed = sorted({_norm_gene(annotation.gene) for annotation in annotations if annotation.gene})
    if len(observed) > 1:
        _add(
            checks,
            "multiple_annotation_genes",
            "conflict",
            "annotation.gene",
            expected,
            observed,
            "Annotation records mention multiple genes; no single provider record may override the input gene.",
            "annotation_records",
        )
    if expected and observed and expected not in observed:
        _add(
            checks,
            "user_gene_vs_annotation_gene",
            "conflict",
            "gene_symbol",
            expected,
            observed,
            "User/input gene does not match the annotation gene context.",
            "variant+annotation_records",
        )


def _check_transcript_context(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    context: GeneDiseaseContext | None,
    annotations: list[VariantAnnotation],
    selection: TranscriptSelection | None,
) -> None:
    expected = _transcript_label(variant) or _transcript_label(context) if context else _transcript_label(variant)
    observed = sorted({_norm_transcript(annotation.transcript) for annotation in annotations if annotation.transcript})
    if len(observed) > 1:
        _add(
            checks,
            "multiple_annotation_transcripts",
            "warning",
            "annotation.transcript",
            expected,
            observed,
            "Annotation contains multiple transcripts; transcript-specific interpretation requires review.",
            "annotation_records",
        )
    if expected and observed and _norm_transcript(expected) not in observed:
        _add(
            checks,
            "user_transcript_vs_annotation_transcript",
            "conflict",
            "transcript",
            expected,
            observed,
            "User/input transcript was not present in annotation records.",
            "variant+annotation_records",
        )
    selected = selection.selected_transcript if selection else None
    variant_transcript = _transcript_label(variant)
    if selected and variant_transcript and not _same_transcript(selected, variant_transcript):
        _add(
            checks,
            "selected_transcript_vs_variant_transcript",
            "conflict",
            "transcript_selection.selected_transcript",
            variant_transcript,
            selected,
            "Selected transcript differs from the normalized variant transcript.",
            "transcript_selection",
        )


def _check_transcript_validation(
    checks: list[ContextConsistencyCheck],
    validation: TranscriptValidationResult | None,
) -> None:
    if validation is None:
        return
    if validation.status in {"conflict", "warning", "insufficient"}:
        severity = "conflict" if validation.status == "conflict" else validation.status
        _add(
            checks,
            "transcript_metadata_validation_status",
            severity,
            "transcript_validation.status",
            "ok",
            validation.status,
            "Transcript metadata validation requires review and cannot override user transcript context.",
            "transcript_validation",
        )
    for flag in validation.review_flags:
        if flag.code == "MANE_SELECT_TRANSCRIPT_SUPPORTED":
            continue
        severity = "conflict" if flag.blocking else "warning"
        _add(
            checks,
            flag.code.lower(),
            severity,
            "transcript_validation",
            "matched transcript/protein/build context",
            flag.code,
            flag.message,
            "transcript_validation",
        )


def _check_hgvs_prefixes(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    annotations: list[VariantAnnotation],
) -> None:
    variant_transcript = _transcript_label(variant)
    prefix = _hgvs_prefix(variant.hgvs_c)
    if prefix and variant_transcript and not _same_transcript(prefix, variant_transcript):
        _add(
            checks,
            "hgvs_transcript_prefix_vs_transcript_field",
            "conflict",
            "hgvs_c",
            variant_transcript,
            prefix,
            "HGVS c. transcript prefix differs from the transcript field.",
            "variant",
        )
    for annotation in annotations:
        prefix = _hgvs_prefix(annotation.hgvs_c)
        if prefix and annotation.transcript and not _same_transcript(prefix, annotation.transcript):
            _add(
                checks,
                "annotation_hgvs_prefix_vs_transcript_field",
                "conflict",
                "annotation.hgvs_c",
                annotation.transcript,
                prefix,
                "Annotation HGVS c. prefix differs from its transcript field.",
                annotation.annotation_source,
            )


def _check_protein_hgvs_ambiguity(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    annotations: list[VariantAnnotation],
) -> None:
    protein_values = [variant.hgvs_p, *(annotation.hgvs_p for annotation in annotations)]
    for value in [item for item in protein_values if item]:
        if ":" not in value and not (_transcript_label(variant) or variant.gene_symbol):
            _add(
                checks,
                "protein_hgvs_gene_transcript_ambiguity",
                "insufficient",
                "hgvs_p",
                "gene or transcript context",
                value,
                "Protein HGVS lacks an explicit transcript/gene context.",
                "variant+annotation_records",
            )


def _check_consequence_vs_variant_type(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    annotations: list[VariantAnnotation],
) -> None:
    terms = {
        term.lower()
        for annotation in annotations
        for term in [annotation.consequence, *annotation.consequence_terms]
        if term
    }
    if variant.transcript and variant.transcript.consequence:
        terms.add(variant.transcript.consequence.lower())
    if not terms:
        return
    if variant.variant_type == VariantType.SNV and terms.intersection({"frameshift_variant", "inframe_deletion", "inframe_insertion"}):
        _add(
            checks,
            "annotation_consequence_vs_variant_type",
            "warning",
            "consequence",
            str(variant.variant_type),
            sorted(terms),
            "Annotation consequence is unusual for the normalized variant type.",
            "annotation_records",
        )
    if variant.variant_type != VariantType.SNV and terms.intersection({"synonymous_variant", "missense_variant"}) and not any("frameshift" in term or "inframe" in term for term in terms):
        _add(
            checks,
            "annotation_consequence_vs_variant_type",
            "warning",
            "consequence",
            str(variant.variant_type),
            sorted(terms),
            "Small indel has only SNV-like consequence terms; review variant/consequence mapping.",
            "annotation_records",
        )


def _check_clinvar_condition(
    checks: list[ContextConsistencyCheck],
    context: GeneDiseaseContext | None,
    records: list[ClinVarRecord],
) -> None:
    disease = context.disease_name if context else None
    if _missing_disease(disease):
        if records:
            _add(
                checks,
                "clinvar_condition_vs_user_disease",
                "insufficient",
                "disease_name",
                "disease context",
                [record.condition or record.conditions for record in records],
                "ClinVar condition cannot be compared because disease context is missing.",
                "ClinVar",
            )
        return
    expected_tokens = _tokens(disease)
    for record in records:
        conditions = record.conditions or ([record.condition] if record.condition else [])
        if conditions and not any(expected_tokens.intersection(_tokens(condition)) for condition in conditions):
            _add(
                checks,
                "clinvar_condition_vs_user_disease",
                "conflict",
                "clinvar.condition",
                disease,
                conditions,
                "ClinVar condition does not match the user-provided disease context.",
                record.source.name,
            )


def _check_population_context(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    context: GeneDiseaseContext | None,
    records: list[PopulationFrequency],
) -> None:
    ancestry = context.population_ancestry if context else None
    for record in records:
        if record.population_match is False:
            _add(
                checks,
                "population_ancestry_context_mismatch",
                "conflict",
                "population_match",
                True,
                False,
                "Population provider marked the record as not ancestry-matched.",
                record.data_source,
            )
        if ancestry and ancestry.lower() not in record.population_name.lower():
            _add(
                checks,
                "population_ancestry_context_mismatch",
                "warning",
                "population_name",
                ancestry,
                record.population_name,
                "Population frequency ancestry/context differs from the provided disease context.",
                record.data_source,
            )
        if record.genome_build and str(record.genome_build) != str(variant.genome_build):
            _add(
                checks,
                "provider_genome_build_vs_input_genome_build",
                "conflict",
                "population_frequency.genome_build",
                str(variant.genome_build),
                record.genome_build,
                "Population provider genome build differs from input genome build.",
                record.data_source,
            )


def _check_inheritance(
    checks: list[ContextConsistencyCheck],
    context: GeneDiseaseContext | None,
) -> None:
    if context is None or not context.inheritance_mode:
        _add(
            checks,
            "inheritance_missing_or_inconsistent",
            "insufficient",
            "inheritance_mode",
            "inheritance mode",
            None,
            "Inheritance mode is missing; disease-specific interpretation requires manual review.",
            "gene_disease_context",
        )
        return
    disease = (context.disease_name or "").lower()
    inheritance = context.inheritance_mode.lower()
    if "recessive" in disease and "dominant" in inheritance:
        _add(
            checks,
            "inheritance_missing_or_inconsistent",
            "conflict",
            "inheritance_mode",
            "recessive disease context",
            context.inheritance_mode,
            "Provided inheritance mode conflicts with disease wording.",
            "gene_disease_context",
        )
    if "dominant" in disease and "recessive" in inheritance:
        _add(
            checks,
            "inheritance_missing_or_inconsistent",
            "conflict",
            "inheritance_mode",
            "dominant disease context",
            context.inheritance_mode,
            "Provided inheritance mode conflicts with disease wording.",
            "gene_disease_context",
        )


def _check_provider_builds(
    checks: list[ContextConsistencyCheck],
    variant: Variant,
    annotations: list[VariantAnnotation],
    clinvar: list[ClinVarRecord],
    populations: list[PopulationFrequency],
    literature: list[LiteratureEvidence],
) -> None:
    expected = str(variant.genome_build)
    for annotation in annotations:
        observed = _first_present(
            annotation.raw_fields.get("genome_build"),
            annotation.raw_fields.get("build"),
            annotation.raw_fields.get("assembly"),
        )
        if observed and str(observed) != expected:
            _add(checks, "provider_genome_build_vs_input_genome_build", "conflict", "annotation.genome_build", expected, observed, "Annotation genome build differs from input genome build.", annotation.annotation_source)
    for record in clinvar:
        observed = record.source.query.get("genome_build")
        if observed and str(observed) != expected:
            _add(checks, "provider_genome_build_vs_input_genome_build", "conflict", "clinvar.query.genome_build", expected, observed, "ClinVar query/result genome build differs from input genome build.", record.source.name)
    for record in populations:
        if record.genome_build and str(record.genome_build) != expected:
            continue
    for record in literature:
        observed = record.source.query.get("genome_build")
        if observed and str(observed) != expected:
            _add(checks, "provider_genome_build_vs_input_genome_build", "conflict", "literature.query.genome_build", expected, observed, "Literature query/result genome build differs from input genome build.", record.source.name)


def _check_missing_disease_attempts(
    checks: list[ContextConsistencyCheck],
    context: GeneDiseaseContext | None,
    populations: list[PopulationFrequency],
) -> None:
    if not _missing_disease(context.disease_name if context else None):
        return
    if populations:
        _add(
            checks,
            "disease_context_missing_but_population_or_pvs1_attempted",
            "insufficient",
            "disease_name",
            "disease context",
            "population_frequency",
            "Disease context is missing while population rules had source data available; BA1/BS1/PM2 confidence must not be elevated.",
            "rate_variant_pipeline",
        )


def _add(
    checks: list[ContextConsistencyCheck],
    name: str,
    severity: ConsistencySeverity,
    field: str,
    expected: Any,
    observed: Any,
    reason: str,
    source: str,
) -> None:
    checks.append(
        ContextConsistencyCheck(
            check_name=name,
            severity=severity,
            field=field,
            expected=expected,
            observed=observed,
            reason=reason,
            source=source,
            requires_review=severity != "ok",
        )
    )


def _limitations(
    conflicts: list[ContextConsistencyCheck],
    warnings: list[ContextConsistencyCheck],
    insufficient: list[ContextConsistencyCheck],
) -> list[str]:
    limitations: list[str] = []
    if conflicts:
        limitations.append("Context consistency conflict detected; human review is required before interpretation.")
    if warnings:
        limitations.append("Context consistency warnings are review flags only and are not ACMG evidence.")
    if insufficient:
        limitations.append("Context was insufficient for one or more consistency checks; do not elevate confidence from missing context.")
    if conflicts or warnings or insufficient:
        limitations.append("Provider context mismatch must not silently override user-provided gene, transcript, disease, ancestry, or genome build.")
    return list(dict.fromkeys(limitations))


def _norm_gene(value: str | None) -> str | None:
    return value.strip().upper() if value else None


def _norm_transcript(value: str | None) -> str | None:
    return value.strip().upper() if value else None


def _same_transcript(left: str, right: str) -> bool:
    return _norm_transcript(left) == _norm_transcript(right)


def _transcript_label(value: Any) -> str | None:
    transcript = getattr(value, "transcript", None)
    if transcript is None:
        return None
    version = getattr(transcript, "version", None)
    accession = getattr(transcript, "accession", None)
    if not accession:
        return None
    return f"{accession}.{version}" if version else str(accession)


def _hgvs_prefix(value: str | None) -> str | None:
    if not value:
        return None
    match = TRANSCRIPT_PREFIX_RE.match(value.strip())
    return match.group("prefix") if match else None


def _missing_disease(value: str | None) -> bool:
    return value is None or value.strip().lower() in MISSING_DISEASE_VALUES


def _tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    ignored = {"and", "or", "of", "the", "syndrome", "disease", "not", "specified", "type"}
    return {
        token
        for token in re.split(r"[^a-z0-9]+", value.lower())
        if len(token) >= 3 and token not in ignored
    }


def _first_present(*values: Any) -> Any | None:
    for value in values:
        if value not in (None, ""):
            return value
    return None
