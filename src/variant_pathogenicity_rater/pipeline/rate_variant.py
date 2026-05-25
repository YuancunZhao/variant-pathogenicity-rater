from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from variant_pathogenicity_rater.annotation import GenericTableAdapter, select_transcript
from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.acmg.computational_rules import evaluate_computational_predictions
from variant_pathogenicity_rater.acmg.population_rules import evaluate_population_rules
from variant_pathogenicity_rater.pvs1 import generate_pvs1_evidence
from variant_pathogenicity_rater.context_consistency import evaluate_context_consistency
from variant_pathogenicity_rater.config.thresholds import (
    computational_thresholds_from_options,
    population_thresholds_from_options,
)
from variant_pathogenicity_rater.data_sources.config import (
    DataSourcesConfig,
    load_data_sources_config,
)
from variant_pathogenicity_rater.data_sources.providers import (
    build_clinvar_provider,
    build_computational_provider,
    build_literature_provider,
    build_population_provider,
)
from variant_pathogenicity_rater.evidence.clinvar import ClinVarQuery
from variant_pathogenicity_rater.evidence.literature import (
    extract_literature_evidence,
)
from variant_pathogenicity_rater.normalization import NormalizationError, normalize_variant
from variant_pathogenicity_rater.reporting import generate_report
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import ComputationalPrediction, EvidenceItem
from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant


HUMAN_REVIEW_NOTICE = (
    "Human review is required. This framework does not provide a final clinical assertion."
)


def rate_variant(arguments: dict[str, Any]) -> dict[str, Any]:
    options = _options(arguments)
    data_sources_config = load_data_sources_config(overrides=options.get("data_sources"))
    audit_trail: list[AuditTrail] = []
    limitations: list[str] = [
        "Mock mode is enabled by default; no network access was attempted.",
        "Phase 1 supports SNV and small indel variants only.",
        "All conclusions are machine proposals and require qualified human review.",
    ]
    evidence_items: list[EvidenceItem] = []
    step_results: dict[str, Any] = {}
    context_consistency: ContextConsistency | None = None

    normalized_variant: Variant | None = None
    normalization_result = _run_step(
        "normalize_variant",
        audit_trail,
        limitations,
        lambda: normalize_variant(_normalization_payload(arguments)),
    )
    if normalization_result is None or normalization_result.normalized_variant is None:
        return _failed_normalization_response(arguments, audit_trail, limitations, step_results)

    normalized_variant = normalization_result.normalized_variant
    step_results["normalize_variant"] = json.loads(normalization_result.model_dump_json())
    limitations.extend(normalization_result.normalization_warnings)

    context = _gene_disease_context(arguments, normalized_variant, limitations, audit_trail)

    transcript_selection: TranscriptSelection | None = None
    annotation_records = _annotation_records(options) if _should_select_transcript(options) else []
    if _should_select_transcript(options):
        transcript_selection = _run_step(
            "select_transcript",
            audit_trail,
            limitations,
            lambda: _select_transcript_step(annotation_records, normalized_variant, options),
        )
        if transcript_selection is not None:
            limitations.extend(transcript_selection.limitations)
            step_results["select_transcript"] = json.loads(transcript_selection.model_dump_json())

    population_frequency = None
    population_records = []
    if options.get("include_population", True):
        population_frequency = _run_step(
            "query_population_frequency",
            audit_trail,
            limitations,
            lambda: build_population_provider(
                data_sources_config.source("population"),
                _population_fixtures(options),
            ).query(normalized_variant),
        )
        if population_frequency is not None:
            population_records.append(population_frequency)
            step_results["query_population_frequency"] = json.loads(
                population_frequency.model_dump_json()
            )

            population_items = _run_step(
                "evaluate_population_rules",
                audit_trail,
                limitations,
                lambda: evaluate_population_rules(
                    normalized_variant,
                    context,
                    population_frequency,
                    population_thresholds_from_options(options.get("population_thresholds")),
                ),
            )
            if population_items is not None:
                evidence_items.extend(population_items)
                step_results["evaluate_population_rules"] = [
                    json.loads(item.model_dump_json()) for item in population_items
                ]

    if options.get("include_computational", True):
        computational_result = _run_step(
            "evaluate_computational_evidence",
            audit_trail,
            limitations,
            lambda: _evaluate_computational_step(
                options,
                normalized_variant,
                data_sources_config,
            ),
        )
        if computational_result is not None:
            computational_items, review_flags, summary = computational_result
            evidence_items.extend(computational_items)
            step_results["evaluate_computational_evidence"] = {
                "evidence_items": [json.loads(item.model_dump_json()) for item in computational_items],
                "review_flags": [json.loads(flag.model_dump_json()) for flag in review_flags],
                "summary": summary,
            }

    pvs1_result = _run_step(
        "evaluate_pvs1",
        audit_trail,
        limitations,
        lambda: generate_pvs1_evidence(
            normalized_variant,
            annotation=_selected_annotation_for_pvs1(annotation_records, transcript_selection),
            transcript_selection=transcript_selection,
            gene_disease_context=context,
            provider_data=_pvs1_provider_data(options),
            manual_overrides=_pvs1_manual_overrides(options),
            config=options.get("pvs1_config"),
        ),
    )
    if pvs1_result is not None:
        pvs1_item, pvs1_decision = pvs1_result
        step_results["evaluate_pvs1"] = {
            "decision": pvs1_decision.model_dump(mode="json"),
            "evidence_item": json.loads(pvs1_item.model_dump_json()) if pvs1_item else None,
        }
        limitations.extend(pvs1_decision.limitations)
        limitations.extend(pvs1_decision.blocking_reasons)
        if pvs1_item is not None:
            evidence_items.append(pvs1_item)

    clinvar_records = []
    if options.get("include_clinvar", True):
        clinvar_result = _run_step(
            "query_clinvar",
            audit_trail,
            limitations,
            lambda: build_clinvar_provider(
                data_sources_config.source("clinvar"),
                options.get("clinvar_records"),
            ).query(_clinvar_query(normalized_variant, context)),
        )
        if clinvar_result is not None:
            clinvar_records = list(clinvar_result.records)
            evidence_items.extend(clinvar_result.candidate_evidence_items)
            limitations.extend(clinvar_result.limitations)
            step_results["query_clinvar"] = json.loads(clinvar_result.model_dump_json())

    literature_records = []
    if options.get("include_literature", True):
        literature_result = _run_step(
            "search_literature_evidence",
            audit_trail,
            limitations,
            lambda: extract_literature_evidence(
                normalized_variant,
                context,
                build_literature_provider(
                    data_sources_config.source("literature"),
                    options.get("literature_records"),
                ),
            ),
        )
        if literature_result is not None:
            literature_records = list(literature_result.literature_records)
            evidence_items.extend(literature_result.candidate_evidence_items)
            limitations.extend(literature_result.limitations)
            step_results["search_literature_evidence"] = json.loads(
                literature_result.model_dump_json()
            )

    supplemental_items = _run_step(
        "load_mock_supplemental_evidence",
        audit_trail,
        limitations,
        lambda: _supplemental_evidence_items(options, normalized_variant),
    )
    if supplemental_items is not None:
        evidence_items.extend(supplemental_items)
        step_results["load_mock_supplemental_evidence"] = [
            json.loads(item.model_dump_json()) for item in supplemental_items
        ]

    context_consistency = _run_step(
        "evaluate_context_consistency",
        audit_trail,
        limitations,
        lambda: evaluate_context_consistency(
            normalized_variant,
            context,
            annotation_records=annotation_records,
            transcript_selection=transcript_selection,
            clinvar_records=clinvar_records,
            population_records=population_records,
            literature_records=literature_records,
        ),
    )
    if context_consistency is not None:
        limitations.extend(context_consistency.limitations)
        step_results["evaluate_context_consistency"] = json.loads(
            context_consistency.model_dump_json()
        )

    step_results["combine_all_evidence"] = {
        "evidence_item_count": len(evidence_items),
        "evidence_ids": [item.evidence_id for item in evidence_items],
    }
    audit_trail.append(_audit("combine_all_evidence", "completed"))

    classification_result = _run_step(
        "classify_acmg",
        audit_trail,
        limitations,
        lambda: classify_acmg(evidence_items, normalized_variant, context, _unique(limitations)),
    )
    if classification_result is None:
        classification_result = classify_acmg([], normalized_variant, context, _unique(limitations))
    classification_result.transcript_selection = transcript_selection
    classification_result.context_consistency = context_consistency
    if transcript_selection is not None:
        classification_result.review_flags = _unique_review_flags(
            [*classification_result.review_flags, *transcript_selection.review_flags]
        )
    if context_consistency is not None:
        classification_result.review_flags = _unique_review_flags(
            [
                *classification_result.review_flags,
                *_review_flags_from_context_consistency(context_consistency),
            ]
        )
    step_results["classify_acmg"] = json.loads(classification_result.model_dump_json())
    applied_evidence = _applied_evidence_items(evidence_items)
    review_note_evidence = _review_note_evidence_items(evidence_items)
    normalization_identity = (step_results.get("normalize_variant") or {}).get("variant_identity")

    report = _run_step(
        "generate_report",
        audit_trail,
        limitations,
        lambda: generate_report(
            variant=normalized_variant,
            classification_result=classification_result,
            evidence_items=evidence_items,
            limitations=_unique(limitations),
            audit_trail=audit_trail + classification_result.audit_trail,
        ),
    )
    if report is None:
        report = {
            "format": "json",
            "report_text": classification_result.report_text,
            "limitations": _unique(limitations),
            "human_review_required": True,
        }

    classification_result.limitations = _unique(limitations)
    if hasattr(report, "content") and hasattr(report, "model_dump_json"):
        classification_result.report_text = str(report.content)
        serialized_report = json.loads(report.model_dump_json())
    else:
        classification_result.report_text = str(report["report_text"])
        serialized_report = report
    step_results["generate_report"] = serialized_report
    combined_audit = audit_trail + classification_result.audit_trail

    return {
        "status": "ok",
        "tool": "rate_variant",
        "stage": "integrated_snv_small_indel_acmg_pipeline",
        "mock_mode": bool(options.get("mock_mode", True)),
        "data_source_modes": {
            name: source.mode for name, source in data_sources_config.sources.items()
        },
        "normalized_variant": json.loads(normalized_variant.model_dump_json()),
        "normalization_identity": normalization_identity,
        "classification_result": json.loads(classification_result.model_dump_json()),
        "evidence_items": [json.loads(item.model_dump_json()) for item in evidence_items],
        "applied_evidence": [json.loads(item.model_dump_json()) for item in applied_evidence],
        "review_note_evidence": [
            json.loads(item.model_dump_json()) for item in review_note_evidence
        ],
        "final_classification": classification_result.final_classification,
        "transcript_selection": (
            json.loads(transcript_selection.model_dump_json())
            if transcript_selection is not None
            else None
        ),
        "context_consistency": (
            json.loads(context_consistency.model_dump_json())
            if context_consistency is not None
            else None
        ),
        "consistency_warnings": (
            [json.loads(check.model_dump_json()) for check in context_consistency.warnings]
            if context_consistency is not None
            else []
        ),
        "report_text": classification_result.report_text,
        "report": serialized_report,
        "limitations": classification_result.limitations,
        "review_flags": [
            json.loads(flag.model_dump_json()) for flag in classification_result.review_flags
        ],
        "provenance": _provenance_summary(
            evidence_items,
            normalization_identity=normalization_identity,
            transcript_selection=transcript_selection,
            context_consistency=context_consistency,
        ),
        "human_review_required": True,
        "human_review": {"required": True, "notice": HUMAN_REVIEW_NOTICE},
        "audit_trail": [json.loads(event.model_dump_json()) for event in combined_audit],
        "step_results": step_results,
    }


def _run_step(
    step_name: str,
    audit_trail: list[AuditTrail],
    limitations: list[str],
    func: Callable[[], Any],
) -> Any | None:
    audit_trail.append(_audit(step_name, "started"))
    try:
        result = func()
    except Exception as exc:  # noqa: BLE001 - pipeline must preserve failure as limitation.
        limitations.append(f"{step_name} failed: {exc.__class__.__name__}: {exc}")
        audit_trail.append(_audit(step_name, "failed", [str(exc)]))
        return None
    audit_trail.append(_audit(step_name, "completed"))
    return result


def _normalization_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    variant = arguments.get("variant")
    if isinstance(variant, dict):
        payload = dict(variant)
    else:
        payload = dict(arguments)
        payload.pop("options", None)

    aliases = {
        "gene": "gene_symbol",
        "chromosome": "chrom",
        "position": "pos",
    }
    for source, target in aliases.items():
        if source in arguments and target not in payload:
            payload[target] = arguments[source]

    for field in ["gene", "transcript", "hgvs_c", "hgvs_p", "chromosome", "position", "ref", "alt"]:
        if field in arguments and field not in payload:
            payload[field] = arguments[field]
    if "value" in payload and "hgvs" not in payload and "hgvs_c" not in payload:
        payload["hgvs"] = payload["value"]
    if "value" in arguments and "hgvs" not in payload and "hgvs_c" not in payload:
        payload["hgvs"] = arguments["value"]
    if "input_type" not in payload and "chrom" in payload and "pos" in payload:
        payload["input_type"] = "vcf_like"
    return payload


def _clinvar_query(variant: Variant, context: GeneDiseaseContext) -> ClinVarQuery:
    query = ClinVarQuery.from_variant(variant)
    query.condition = context.disease_name
    return query


def _gene_disease_context(
    arguments: dict[str, Any],
    variant: Variant,
    limitations: list[str],
    audit_trail: list[AuditTrail],
) -> GeneDiseaseContext:
    context_payload = (
        arguments.get("gene_disease_context")
        or arguments.get("context")
        or arguments.get("options", {}).get("gene_disease_context")
        or {}
    )
    payload = dict(context_payload) if isinstance(context_payload, dict) else {}
    payload.setdefault("gene", arguments.get("gene") or variant.gene_symbol or "unknown")
    payload.setdefault("disease", arguments.get("disease") or "not provided")
    payload.setdefault("inheritance", arguments.get("inheritance"))
    phenotype = arguments.get("phenotype") or arguments.get("phenotype_terms")
    if phenotype and "phenotype_terms" not in payload:
        payload["phenotype_terms"] = phenotype if isinstance(phenotype, list) else [str(phenotype)]
    if variant.transcript and "transcript" not in payload:
        payload["transcript"] = variant.transcript.model_dump(mode="json")
    try:
        context = GeneDiseaseContext.model_validate(payload)
    except ValidationError as exc:
        limitations.append(f"gene_disease_context validation failed; fallback context used: {exc}")
        context = GeneDiseaseContext(
            gene=variant.gene_symbol or "unknown",
            disease_name="not provided",
        )
    audit_trail.append(
        _audit(
            "build_gene_disease_context",
            "completed",
            ["Context may be incomplete and requires review."],
        )
    )
    return context


def _options(arguments: dict[str, Any]) -> dict[str, Any]:
    options = dict(arguments.get("options") or {})
    options.setdefault("mock_mode", True)
    return options


def _population_fixtures(options: dict[str, Any]) -> dict[str, Any] | None:
    fixture = options.get("population_frequency")
    if not isinstance(fixture, dict):
        return None
    variant_id = fixture.get("variant_id")
    if not variant_id:
        return None
    from variant_pathogenicity_rater.schemas.evidence import PopulationFrequency

    payload = dict(fixture)
    payload.pop("variant_id", None)
    return {str(variant_id): PopulationFrequency.model_validate(payload)}


def _computational_predictions(
    options: dict[str, Any],
    variant: Variant,
    data_sources_config: DataSourcesConfig,
) -> list[ComputationalPrediction]:
    raw_predictions = options.get("computational_predictions")
    if raw_predictions is None:
        return build_computational_provider(data_sources_config.source("computational")).query(variant)
    return [
        ComputationalPrediction.model_validate(prediction)
        for prediction in raw_predictions
        if isinstance(prediction, dict)
    ]


def _evaluate_computational_step(
    options: dict[str, Any],
    variant: Variant,
    data_sources_config: DataSourcesConfig,
) -> tuple[list[EvidenceItem], list[Any], dict[str, Any]]:
    predictions = _computational_predictions(options, variant, data_sources_config)
    return evaluate_computational_predictions(
        variant,
        predictions,
        computational_thresholds_from_options(options.get("computational_thresholds")),
    )


def _should_select_transcript(options: dict[str, Any]) -> bool:
    return bool(
        options.get("include_transcript_selection")
        or options.get("annotations") is not None
        or options.get("annotation_records") is not None
        or options.get("annotation_text") is not None
    )


def _select_transcript_step(
    annotations: list[VariantAnnotation],
    variant: Variant,
    options: dict[str, Any],
) -> TranscriptSelection:
    user_transcript = options.get("user_transcript") or _variant_transcript_label(variant)
    return select_transcript(annotations, user_transcript=user_transcript)


def _selected_annotation_for_pvs1(
    annotations: list[VariantAnnotation],
    transcript_selection: TranscriptSelection | None,
) -> VariantAnnotation | None:
    if not annotations:
        return None
    selected = transcript_selection.selected_transcript if transcript_selection else None
    if selected:
        for annotation in annotations:
            if annotation.transcript == selected:
                return annotation
    return annotations[0]


def _pvs1_provider_data(options: dict[str, Any]) -> dict[str, Any] | None:
    data = options.get("pvs1_provider_data") or options.get("pvs1_mock_context")
    return dict(data) if isinstance(data, dict) else None


def _pvs1_manual_overrides(options: dict[str, Any]) -> dict[str, Any] | None:
    data = options.get("pvs1_manual_overrides")
    return dict(data) if isinstance(data, dict) else None


def _annotation_records(options: dict[str, Any]) -> list[VariantAnnotation]:
    raw_annotations = options.get("annotations")
    if isinstance(raw_annotations, list):
        return [
            VariantAnnotation.model_validate(annotation)
            for annotation in raw_annotations
            if isinstance(annotation, dict)
        ]

    raw_records = options.get("annotation_records")
    if isinstance(raw_records, list):
        result = GenericTableAdapter(source_version="pipeline-options").parse_records(
            record for record in raw_records if isinstance(record, dict)
        )
        return result.annotations

    annotation_text = options.get("annotation_text")
    if isinstance(annotation_text, str):
        result = GenericTableAdapter(source_version="pipeline-options").parse_text(annotation_text)
        return result.annotations

    return []


def _variant_transcript_label(variant: Variant) -> str | None:
    if variant.transcript is None:
        return None
    if variant.transcript.version:
        return f"{variant.transcript.accession}.{variant.transcript.version}"
    return variant.transcript.accession


def _supplemental_evidence_items(
    options: dict[str, Any],
    variant: Variant,
) -> list[EvidenceItem]:
    raw_items = (
        options.get("mock_supplemental_evidence_items")
        or options.get("supplemental_evidence_items")
        or []
    )
    if not isinstance(raw_items, list):
        raise ValueError("mock_supplemental_evidence_items must be a list when provided.")

    items: list[EvidenceItem] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if not isinstance(raw_item, dict):
            raise ValueError("Each mock supplemental evidence item must be an object.")
        payload = dict(raw_item)
        payload.setdefault("evidence_id", f"ev-mock-{variant.variant_id}-{index}")
        payload.setdefault("confidence", 0.6)
        payload.setdefault("requires_review", True)
        payload.setdefault("triggered_by", ["curated_mock_benchmark"])
        payload.setdefault(
            "source",
            {
                "name": "curated_mock_benchmark",
                "version": "offline-v1",
                "query": {"variant_id": variant.variant_id},
            },
        )
        supporting_data = dict(payload.get("supporting_data") or {})
        supporting_data.setdefault("mock_only", True)
        supporting_data.setdefault("variant_id", variant.variant_id)
        payload["supporting_data"] = supporting_data
        items.append(EvidenceItem.model_validate(payload))
    return items


def _failed_normalization_response(
    arguments: dict[str, Any],
    audit_trail: list[AuditTrail],
    limitations: list[str],
    step_results: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "error",
        "tool": "rate_variant",
        "stage": "variant_normalization",
        "mock_mode": True,
        "normalized_variant": None,
        "classification_result": None,
        "evidence_items": [],
        "final_classification": None,
        "report_text": "Variant normalization failed. Human review is required.",
        "limitations": _unique(limitations),
        "human_review_required": True,
        "human_review": {"required": True, "notice": HUMAN_REVIEW_NOTICE},
        "audit_trail": [json.loads(event.model_dump_json()) for event in audit_trail],
        "step_results": step_results,
        "input": arguments,
    }


def _audit(step_name: str, status: str, notes: list[str] | None = None) -> AuditTrail:
    return AuditTrail(
        event_id=f"audit-{step_name}-{status}-{datetime.now(timezone.utc).timestamp():.6f}",
        event_type=f"{step_name}_{status}",
        tool_name=step_name,
        notes=notes or [],
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _unique_review_flags(flags: list[Any]) -> list[Any]:
    seen: set[str] = set()
    unique: list[Any] = []
    for flag in flags:
        code = getattr(flag, "code", None)
        if not code or code in seen:
            continue
        seen.add(code)
        unique.append(flag)
    return unique


def _applied_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return [item for item in items if _is_applied_evidence(item)]


def _review_note_evidence_items(items: list[EvidenceItem]) -> list[EvidenceItem]:
    return [item for item in items if not _is_applied_evidence(item)]


def _is_applied_evidence(item: EvidenceItem) -> bool:
    return not (
        item.candidate_only
        or item.applied is False
        or str(item.strength) == "none"
        or item.supporting_data.get("candidate_only")
        or item.supporting_data.get("evidence_status") == "candidate"
        or item.supporting_data.get("applied") is False
    )


def _provenance_summary(
    items: list[EvidenceItem],
    *,
    normalization_identity: Any,
    transcript_selection: TranscriptSelection | None,
    context_consistency: ContextConsistency | None,
) -> dict[str, Any]:
    return {
        "normalization_identity": normalization_identity if isinstance(normalization_identity, dict) else None,
        "evidence_sources": [
            {
                "evidence_id": item.evidence_id,
                "source": item.source.name,
                "version": item.source.version,
                "retrieval_timestamp": item.source.retrieval_timestamp,
                "query": item.source.query,
                "raw_snapshot_ref": item.source.raw_snapshot_ref,
                "candidate_only": item.candidate_only,
                "applied": item.applied,
            }
            for item in items
        ],
        "transcript_selection": (
            transcript_selection.provenance if transcript_selection is not None else None
        ),
        "context_consistency": (
            context_consistency.provenance if context_consistency is not None else None
        ),
    }


def _review_flags_from_context_consistency(consistency: ContextConsistency) -> list[ReviewFlag]:
    flags: list[ReviewFlag] = []
    for check in [*consistency.conflicts, *consistency.warnings]:
        flags.append(
            ReviewFlag(
                code=f"CONTEXT_{check.check_name.upper()}",
                message=check.reason,
                severity="error" if check.severity == "conflict" else "warning",
                blocking=check.severity in {"conflict", "insufficient"},
            )
        )
    return flags
