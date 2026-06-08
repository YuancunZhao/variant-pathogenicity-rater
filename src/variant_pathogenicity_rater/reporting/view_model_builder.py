from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.data_sources.provider_result import ProviderRuntimeResult
from variant_pathogenicity_rater.evidence.status import EvidenceStatusView, build_evidence_status_view
from variant_pathogenicity_rater.reporting.view_models import (
    ClassificationReportView,
    EvidenceReportEntryView,
    EvidenceReportView,
    EvidenceSectionsView,
    ProviderReportView,
    ReportViewModel,
    ReviewReportView,
    VariantReportView,
)
from variant_pathogenicity_rater.schemas.classification import ClassificationResult
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem
from variant_pathogenicity_rater.schemas.report import (
    DataSourceSummary,
    EvidenceReportEntry,
    VariantReportSummary,
)


CLASSIFICATION_LABELS = {
    "pathogenic": "Pathogenic",
    "likely_pathogenic": "Likely Pathogenic",
    "vus": "Variant of Uncertain Significance",
    "likely_benign": "Likely Benign",
    "benign": "Benign",
}


def build_report_view_model(result: ClassificationResult | dict[str, Any]) -> ReportViewModel:
    """Build a render-ready ``ReportViewModel`` from a ``ClassificationResult``.

    This is the **single data-preparation boundary** for report rendering.
    It extracts classification internals (including per-criterion decision
    data, source provenance, and reviewed-evidence metadata) so that
    ``generator.py`` does not need to interpret raw classification state.

    ``generator.py`` consumes only the ``ReportViewModel`` and its
    ``VariantReportSummary`` — it does not inspect raw classification
    fields or provider-mode metadata directly.
    """
    classification_result, provider_payload = _classification_and_provider_payload(result)
    evidence_entries = [_evidence_entry(item) for item in classification_result.evidence_items]
    status_views = [build_evidence_status_view(item) for item in classification_result.evidence_items]
    summary = _summary(classification_result, evidence_entries, status_views)
    evidence_views = _evidence_views(classification_result.evidence_items, status_views)
    evidence_sections = _evidence_sections(evidence_entries, status_views)
    return ReportViewModel(
        variant=_variant_view(classification_result, summary),
        context=_context_view(classification_result),
        providers=_provider_views(provider_payload),
        evidence=evidence_views,
        evidence_sections=evidence_sections,
        classification=ClassificationReportView(
            final_classification=str(classification_result.final_classification),
            confidence=classification_result.confidence,
            combination_rule=classification_result.applied_combination_rule,
            human_review_required=classification_result.human_review_required,
        ),
        review=ReviewReportView(
            review_flags=list(classification_result.review_flags),
            blocking_reasons=_blocking_reasons(classification_result),
            questions=[],
            limitations=list(classification_result.limitations),
        ),
        summary=summary,
        audit_trail=list(classification_result.audit_trail),
        has_computational_evidence=any(
            view.code in {"PP3", "BP4"} for view in evidence_views
        ),
        has_spliceai_evidence=any(
            "spliceai" in str(trigger).lower()
            for item in classification_result.evidence_items
            for trigger in item.triggered_by
        ),
    )


def _classification_and_provider_payload(
    result: ClassificationResult | dict[str, Any],
) -> tuple[ClassificationResult, dict[str, Any]]:
    if isinstance(result, ClassificationResult):
        return result, {}
    if not isinstance(result, dict):
        raise TypeError("build_report_view_model requires a ClassificationResult or rate_variant result dict.")
    classification_payload = result.get("classification_result") or result
    classification_result = ClassificationResult.model_validate(classification_payload)
    provider_payload = ((result.get("step_results") or {}).get("provider_runtime") or {})
    if not isinstance(provider_payload, dict):
        provider_payload = {}
    return classification_result, provider_payload


def _summary(
    result: ClassificationResult,
    entries: list[EvidenceReportEntry],
    status_views: list[EvidenceStatusView],
) -> VariantReportSummary:
    variant = result.variant
    applied_entries = [
        entry for entry, status in zip(entries, status_views, strict=False)
        if status.is_applied
    ]
    candidate_entries = [
        entry for entry, status in zip(entries, status_views, strict=False)
        if not status.is_applied
    ]
    return VariantReportSummary(
        variant_id=variant.variant_id,
        gene_symbol=variant.gene_symbol,
        transcript=_transcript_label(variant),
        hgvs_c=variant.hgvs_c,
        hgvs_p=variant.hgvs_p,
        genomic_location=(
            f"{variant.genome_build}:{variant.chrom}:{variant.pos}:"
            f"{variant.ref}>{variant.alt}"
        ),
        final_classification=str(result.final_classification),
        classification_label=CLASSIFICATION_LABELS.get(
            str(result.final_classification),
            str(result.final_classification),
        ),
        confidence=result.confidence,
        applied_combination_rule=result.applied_combination_rule,
        triggered_acmg_evidence=applied_entries,
        candidate_acmg_evidence=candidate_entries,
        pathogenic_evidence_summary=result.pathogenic_evidence_summary,
        benign_evidence_summary=result.benign_evidence_summary,
        conflicting_evidence=result.conflicting_evidence,
        clinvar_conflict_detected=_clinvar_conflict_detected(result),
        limitations=result.limitations,
        human_review_note="Human review is required. This framework does not provide a final clinical assertion.",
        data_source_summary=_data_source_summary(result.evidence_items),
        review_flags=result.review_flags,
        transcript_selection=result.transcript_selection,
        transcript_validation=result.transcript_validation,
        variant_resolution=result.variant_resolution,
        context_consistency=result.context_consistency,
        vcep_profile_context=result.vcep_profile_context,
    )


def _variant_view(result: ClassificationResult, summary: VariantReportSummary) -> VariantReportView:
    resolution_status = None
    consequence = None
    if result.variant_resolution is not None:
        resolution_status = str(result.variant_resolution.status)
        if result.variant_resolution.resolved_hgvs_p is not None:
            consequence = result.variant_resolution.resolved_hgvs_p.consequence
    if consequence is None and result.variant.transcript is not None:
        consequence = result.variant.transcript.consequence
    return VariantReportView(
        gene=summary.gene_symbol,
        transcript=summary.transcript,
        hgvs_c=summary.hgvs_c,
        hgvs_p=summary.hgvs_p,
        coordinate=summary.genomic_location,
        consequence=consequence,
        resolution_status=resolution_status,
    )


def _context_view(result: ClassificationResult) -> dict[str, Any]:
    if result.context_consistency is None:
        return {}
    return result.context_consistency.model_dump(mode="json")


def _provider_views(provider_payload: dict[str, Any]) -> list[ProviderReportView]:
    views: list[ProviderReportView] = []
    for name, payload in provider_payload.items():
        if not isinstance(payload, dict):
            continue
        runtime = ProviderRuntimeResult.model_validate({"provider_name": name, **payload})
        views.append(
            ProviderReportView(
                provider_name=runtime.provider_name,
                requested_mode=runtime.requested_mode,
                configured_mode=runtime.configured_mode,
                outcome=str(runtime.outcome),
                records_count=runtime.records_count,
                limitations=list(runtime.limitations),
            )
        )
    return views


def _evidence_views(
    items: list[EvidenceItem],
    status_views: list[EvidenceStatusView] | None = None,
) -> list[EvidenceReportView]:
    views: list[EvidenceReportView] = []
    statuses = status_views or [build_evidence_status_view(item) for item in items]
    for item, status in zip(items, statuses, strict=False):
        views.append(
            EvidenceReportView(
                evidence_id=item.evidence_id,
                code=str(item.code),
                strength=str(item.strength),
                direction=str(item.direction),
                display_status=str(status.display_status),
                reason=status.reason,
                source_name=item.source.name,
                review_required=item.requires_review,
            )
        )
    return views


def _evidence_sections(
    entries: list[EvidenceReportEntry],
    status_views: list[EvidenceStatusView],
) -> EvidenceSectionsView:
    counted: list[EvidenceReportEntryView] = []
    review_note: list[EvidenceReportEntryView] = []
    manual_reviewed: list[EvidenceReportEntryView] = []
    external_source: list[EvidenceReportEntryView] = []
    clingen_erepo: list[EvidenceReportEntryView] = []
    external_sources = {"ClinVar", "ClinGen Evidence Repository", "Literature"}
    for entry, status in zip(entries, status_views, strict=False):
        view = EvidenceReportEntryView(
            entry=entry,
            display_status=str(status.display_status),
            review_status_label=status.reviewed_status,
            counted_by_classifier=status.is_applied,
            is_manual_reviewed=entry.source == "manual_reviewed_evidence"
            or bool(entry.curator_decision),
            is_external_source=entry.source in external_sources,
            is_clingen_erepo=entry.source == "ClinGen Evidence Repository",
        )
        if status.is_applied:
            counted.append(view)
        else:
            review_note.append(view)
        if view.is_manual_reviewed:
            manual_reviewed.append(view)
        if view.is_external_source:
            external_source.append(view)
        if view.is_clingen_erepo:
            clingen_erepo.append(view)
    return EvidenceSectionsView(
        counted=counted,
        review_note=review_note,
        manual_reviewed=manual_reviewed,
        external_source=external_source,
        clingen_erepo=clingen_erepo,
    )


def _evidence_entry(item: EvidenceItem) -> EvidenceReportEntry:
    pvs1_decision = item.supporting_data.get("pvs1_decision") or {}
    population_decision = item.supporting_data.get("population_evidence_decision") or {}
    computational_decision = item.supporting_data.get("computational_evidence_decision") or {}
    ps1_pm5_decision = item.supporting_data.get("ps1_pm5_decision") or {}
    ps1_pm5_generation = item.supporting_data.get("evidence_generation") or {}
    reviewed = item.supporting_data.get("reviewed_evidence") or {}
    clingen_match = item.supporting_data.get("clingen_erepo_match")
    clingen_record = item.supporting_data.get("clingen_erepo_record")
    return EvidenceReportEntry(
        evidence_id=item.evidence_id,
        code=str(item.code),
        strength=str(item.strength),
        direction=str(item.direction),
        rationale=item.reason,
        source=item.source.name,
        confidence=item.confidence,
        requires_review=item.requires_review,
        triggered_by=item.triggered_by,
        citation=item.supporting_data.get("citation"),
        provenance=item.source.provenance,
        limitations=list(item.supporting_data.get("limitations") or []),
        review_flags=item.review_flags,
        pvs1_decision_path=list(item.supporting_data.get("decision_path") or pvs1_decision.get("decision_path") or []),
        pvs1_downgrade_reasons=list(item.supporting_data.get("downgrade_reasons") or pvs1_decision.get("downgrade_reasons") or []),
        pvs1_blocking_reasons=list(item.supporting_data.get("blocking_reasons") or pvs1_decision.get("blocking_reasons") or []),
        population_decision_path=list(population_decision.get("decision_path") or []),
        population_thresholds=dict(population_decision.get("thresholds_used") or {}),
        population_quality_checks=list(population_decision.get("quality_checks") or []),
        population_blocking_reasons=list(population_decision.get("blocking_reasons") or []),
        computational_predictor_summary=list(item.supporting_data.get("predictor_summary") or computational_decision.get("predictor_summary") or []),
        computational_thresholds=dict(item.supporting_data.get("thresholds_used") or computational_decision.get("thresholds_used") or {}),
        computational_quality_checks=list(item.supporting_data.get("quality_checks") or computational_decision.get("quality_checks") or []),
        computational_conflict_reasons=list(item.supporting_data.get("conflict_reasons") or computational_decision.get("conflict_reasons") or []),
        computational_consensus_direction=str(item.supporting_data.get("consensus_direction") or computational_decision.get("consensus_direction") or "") or None,
        ps1_pm5_decision_path=list(ps1_pm5_generation.get("decision_path") or []),
        ps1_pm5_quality_checks=list(ps1_pm5_decision.get("quality_checks") or []),
        ps1_pm5_blocking_reasons=list(ps1_pm5_decision.get("blocking_reasons") or []),
        ps1_pm5_downgrade_reasons=list(ps1_pm5_decision.get("downgrade_reasons") or []),
        ps1_pm5_review_note=item.supporting_data.get("review_note"),
        curator_decision=item.supporting_data.get("curator_decision") or reviewed.get("curator_decision"),
        curator_name=item.supporting_data.get("curator_name") or reviewed.get("curator_name"),
        review_date=item.supporting_data.get("review_date") or reviewed.get("review_date"),
        override_reason=item.supporting_data.get("override_reason") or reviewed.get("override_reason"),
        source_candidate_evidence_id=(
            item.supporting_data.get("source_candidate_evidence_id")
            or reviewed.get("source_candidate_evidence_id")
        ),
        reviewed_evidence_status=item.supporting_data.get("evidence_status") or reviewed.get("evidence_status"),
        reviewed_provenance=item.supporting_data.get("provenance") or reviewed.get("provenance"),
        clingen_erepo_match=clingen_match if isinstance(clingen_match, dict) else None,
        clingen_erepo_record=clingen_record if isinstance(clingen_record, dict) else None,
        clingen_erepo_criteria=list(item.supporting_data.get("criteria_applied") or []),
        clingen_erepo_summaries=list(item.supporting_data.get("evidence_summaries") or []),
        vcep_override=(
            item.supporting_data.get("vcep_override")
            if isinstance(item.supporting_data.get("vcep_override"), dict)
            else None
        ),
    )


def _data_source_summary(items: list[EvidenceItem]) -> list[DataSourceSummary]:
    by_source: dict[tuple[str, str | None], DataSourceSummary] = {}
    for item in items:
        key = (item.source.name, item.source.version)
        if key not in by_source:
            by_source[key] = DataSourceSummary(
                name=item.source.name,
                version=item.source.version,
                retrieval_timestamp=item.source.retrieval_timestamp,
                evidence_ids=[],
                query=item.source.query,
                raw_snapshot_ref=item.source.raw_snapshot_ref,
            )
        by_source[key].evidence_ids.append(item.evidence_id)
    return list(by_source.values())


def _clinvar_conflict_detected(result: ClassificationResult) -> bool:
    if result.conflicting_evidence:
        return any("clinvar" in item.lower() for item in result.conflicting_evidence)
    for item in result.evidence_items:
        status = build_evidence_status_view(item)
        if item.source.name.lower() == "clinvar" and (
            str(item.direction) == "conflicting"
            or any("conflict" in limitation.lower() for limitation in status.limitations)
            or "conflicting_interpretations" in status.provenance_summary
        ):
            return True
        if item.source.name.lower() == "clinvar" and bool(
            item.supporting_data.get("conflicting_interpretations")
        ):
            return True
    return False


def _blocking_reasons(result: ClassificationResult) -> list[str]:
    reasons: list[str] = []
    for flag in result.review_flags:
        if getattr(flag, "blocking", False):
            reasons.append(str(flag.message))
    return reasons


def _transcript_label(result_variant: Any) -> str | None:
    transcript = result_variant.transcript
    if transcript is None:
        return None
    if transcript.version:
        return f"{transcript.accession}.{transcript.version}"
    return transcript.accession
