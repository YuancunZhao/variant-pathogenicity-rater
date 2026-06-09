from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from variant_pathogenicity_rater.annotation import GenericTableAdapter, select_transcript
from variant_pathogenicity_rater.acmg.computational_rules import evaluate_computational_predictions
from variant_pathogenicity_rater.pvs1 import generate_pvs1_evidence
from variant_pathogenicity_rater.ps1_pm5 import generate_ps1_pm5_evidence
from variant_pathogenicity_rater.population import generate_population_evidence
from variant_pathogenicity_rater.context_consistency import evaluate_context_consistency
from variant_pathogenicity_rater.transcript_support import (
    TranscriptValidationResult,
    load_transcript_metadata_records,
    validate_transcript_metadata,
)
from variant_pathogenicity_rater.config.thresholds import (
    computational_thresholds_from_options,
    population_thresholds_from_options,
)
from variant_pathogenicity_rater.clingen_erepo import (
    ClinGenERepoQuery,
    build_clingen_erepo_provider,
)
from variant_pathogenicity_rater.clingen_erepo.provider import (
    EREPO_REVIEW_NOTE,
    clingen_erepo_candidate_evidence_id,
)
from variant_pathogenicity_rater.clingen_erepo.schema import ClinGenERepoMatchLevel
from variant_pathogenicity_rater.data_sources.config import (
    DataSourcesConfig,
    ProviderMode,
)
from variant_pathogenicity_rater.data_sources.providers import (
    build_clinvar_provider,
    build_computational_provider,
    build_literature_provider,
    build_population_provider,
)
from variant_pathogenicity_rater.evidence.clinvar import ClinVarQuery
from variant_pathogenicity_rater.evidence.literature import extract_literature_evidence
from variant_pathogenicity_rater.evidence.reviewed import process_reviewed_evidence
from variant_pathogenicity_rater.literature_agent import search_and_summarize_literature
from variant_pathogenicity_rater.providers import (
    ProviderDependencyCheck,
    ProviderExecutionPlan,
    dependency_check_from_plan,
    dependency_skip_payload,
)
from variant_pathogenicity_rater.schemas.acmg import EvidenceCode
from variant_pathogenicity_rater.schemas.annotation import TranscriptSelection, VariantAnnotation
from variant_pathogenicity_rater.schemas.common import AuditTrail, ReviewFlag
from variant_pathogenicity_rater.schemas.consistency import ContextConsistency
from variant_pathogenicity_rater.schemas.evidence import (
    ComputationalPrediction,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Variant
from variant_pathogenicity_rater.variant_resolution import (
    ResolvedProtein,
    VariantResolutionResult,
)
from variant_pathogenicity_rater.vcep_profiles import (
    apply_computational_threshold_overrides,
    apply_disabled_criteria,
    apply_population_threshold_overrides,
    apply_ps1_pm5_overrides,
    apply_pvs1_overrides,
    attach_computational_override_note,
    load_vcep_profiles,
    resolve_vcep_signal_and_overrides,
    vcep_override_metadata,
)
from variant_pathogenicity_rater.vcep_profiles.schema import (
    VCEPOverrideContext,
    VCEPSignalResult,
)


RunStep = Callable[[str, list[AuditTrail], list[str], Callable[[], Any]], Any | None]
AuditEventFactory = Callable[[str, str, list[str] | None], AuditTrail]


@dataclass(frozen=True)
class EvidencePhaseResult:
    evidence_items: list[EvidenceItem]
    context_consistency: ContextConsistency | None
    transcript_selection: TranscriptSelection | None
    transcript_validation: TranscriptValidationResult | None
    variant_resolution: VariantResolutionResult | None
    reviewed_evidence_records: list[dict[str, Any]]
    reviewed_review_flags: list[ReviewFlag]
    provider_dependency_review_flags: list[ReviewFlag]
    provider_dependency_checks: dict[str, Any]
    vcep_signal_result: VCEPSignalResult | None
    vcep_override_context: VCEPOverrideContext | None
    clingen_erepo_result: Any = None


@dataclass
class EvidencePhaseState:
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    context_consistency: ContextConsistency | None = None
    transcript_validation: TranscriptValidationResult | None = None
    transcript_selection: TranscriptSelection | None = None
    reviewed_evidence_records: list[dict[str, Any]] = field(default_factory=list)
    reviewed_review_flags: list[ReviewFlag] = field(default_factory=list)
    provider_dependency_review_flags: list[ReviewFlag] = field(default_factory=list)
    provider_dependency_checks: dict[str, Any] = field(default_factory=dict)
    vcep_signal_result: VCEPSignalResult | None = None
    vcep_override_context: VCEPOverrideContext | None = None
    clingen_erepo_result: Any = None


def run_evidence_phase(
    *,
    arguments: dict[str, Any],
    options: dict[str, Any],
    data_sources_config: DataSourcesConfig,
    normalized_variant: Variant,
    context: GeneDiseaseContext,
    variant_resolution: VariantResolutionResult | None,
    provider_identity: Any,
    provider_execution_plan: ProviderExecutionPlan | None = None,
    audit_trail: list[AuditTrail],
    limitations: list[str],
    step_results: dict[str, Any],
    run_step: RunStep,
    audit_event: AuditEventFactory,
    population_provider_builder: Callable[..., Any] = build_population_provider,
    literature_summarizer: Callable[..., Any] = search_and_summarize_literature,
) -> EvidencePhaseResult:
    state = EvidencePhaseState()

    if _should_resolve_vcep(options):
        vcep_profiles, vcep_load_limitations = load_vcep_profiles(options)
        limitations.extend(vcep_load_limitations)
        state.vcep_signal_result, state.vcep_override_context = run_step(
            "resolve_vcep_signal_and_overrides",
            audit_trail,
            limitations,
            lambda: resolve_vcep_signal_and_overrides(
                profiles=vcep_profiles,
                variant=normalized_variant,
                context=context,
                include_signals=bool(options.get("include_vcep_signals") or options.get("apply_vcep_overrides")),
                apply_overrides=bool(options.get("apply_vcep_overrides")),
            ),
        ) or (None, None)
        if state.vcep_signal_result is not None:
            limitations.extend(state.vcep_signal_result.limitations)
            limitations.extend(state.vcep_signal_result.warnings)
            step_results["resolve_vcep_signal"] = state.vcep_signal_result.model_dump(mode="json")
        if state.vcep_override_context is not None:
            limitations.extend(state.vcep_override_context.blocked_reasons)
            step_results["resolve_vcep_overrides"] = state.vcep_override_context.model_dump(mode="json")

    annotation_records = _annotation_records(options) if _should_select_transcript(options) else []
    if _should_select_transcript(options):
        state.transcript_selection = run_step(
            "select_transcript",
            audit_trail,
            limitations,
            lambda: _select_transcript_step(annotation_records, normalized_variant, options),
        )
        if state.transcript_selection is not None:
            limitations.extend(state.transcript_selection.limitations)
            step_results["select_transcript"] = json.loads(state.transcript_selection.model_dump_json())

    transcript_records, transcript_fixture_limitations = load_transcript_metadata_records(
        _transcript_fixture(options)
    )
    limitations.extend(transcript_fixture_limitations)
    if _should_validate_transcripts(options, transcript_records):
        state.transcript_validation = run_step(
            "validate_transcript_metadata",
            audit_trail,
            limitations,
            lambda: validate_transcript_metadata(
                variant=normalized_variant,
                context=context,
                annotation_records=annotation_records,
                transcript_selection=state.transcript_selection,
                transcript_records=transcript_records,
                provider_limitations=transcript_fixture_limitations,
            ),
        )
        if state.transcript_validation is not None:
            limitations.extend(state.transcript_validation.limitations)
            state.transcript_selection = _enrich_transcript_selection(
                state.transcript_selection,
                state.transcript_validation,
            )
            step_results["validate_transcript_metadata"] = json.loads(
                state.transcript_validation.model_dump_json()
            )

    population_frequency = None
    population_records = []
    population_thresholds = population_thresholds_from_options(options.get("population_thresholds"))
    population_thresholds = apply_population_threshold_overrides(
        population_thresholds,
        state.vcep_override_context,
    )
    if options.get("include_population", True):
        gnomad_dependency = dependency_check_from_plan(provider_execution_plan, "query_population_frequency")
        if gnomad_dependency is None:
            gnomad_dependency = _fallback_gnomad_check(provider_identity)
        state.provider_dependency_checks["gnomad"] = gnomad_dependency.model_dump(mode="json")
        if _online_source(data_sources_config, "population") and not gnomad_dependency.satisfied:
            _record_dependency_skip(
                "query_population_frequency",
                gnomad_dependency,
                step_results,
                limitations,
                state.provider_dependency_review_flags,
            )
        else:
            population_frequency = run_step(
                "query_population_frequency",
                audit_trail,
                limitations,
                lambda: population_provider_builder(
                    data_sources_config.source("population"),
                    _population_fixtures(options),
                ).query(normalized_variant),
            )
        if population_frequency is not None:
            population_records.append(population_frequency)
            step_results["query_population_frequency"] = json.loads(
                population_frequency.model_dump_json()
            )

    state.context_consistency = run_step(
        "evaluate_context_consistency",
        audit_trail,
        limitations,
        lambda: evaluate_context_consistency(
            normalized_variant,
            context,
            annotation_records=annotation_records,
            transcript_selection=state.transcript_selection,
            transcript_validation=state.transcript_validation,
            population_records=population_records,
        ),
    )
    if state.context_consistency is not None:
        limitations.extend(state.context_consistency.limitations)
        step_results["evaluate_context_consistency"] = json.loads(
            state.context_consistency.model_dump_json()
        )

    if population_frequency is not None:
        population_result = run_step(
            "evaluate_population_rules",
            audit_trail,
            limitations,
            lambda: generate_population_evidence(
                variant=normalized_variant,
                context=context,
                frequency=population_frequency,
                thresholds=population_thresholds,
                context_consistency=state.context_consistency,
                inheritance=context.inheritance_mode,
                disease_prevalence=context.disease_prevalence,
                penetrance=options.get("penetrance"),
                provider_provenance={
                    "source": (
                        population_frequency.source.model_dump(mode="json")
                        if population_frequency.source
                        else None
                    ),
                    "vcep_override": vcep_override_metadata(state.vcep_override_context),
                },
            ),
        )
        if population_result is not None:
            population_items, population_decision = population_result
            state.evidence_items.extend(population_items)
            limitations.extend(population_decision.limitations)
            limitations.extend(population_decision.blocking_reasons)
            step_results["evaluate_population_rules"] = [
                json.loads(item.model_dump_json()) for item in population_items
            ]
            step_results["evaluate_population_evidence"] = {
                "decision": population_decision.model_dump(mode="json"),
                "evidence_items": [json.loads(item.model_dump_json()) for item in population_items],
            }

    pvs1_result = run_step(
        "evaluate_pvs1",
        audit_trail,
        limitations,
        lambda: generate_pvs1_evidence(
            normalized_variant,
            annotation=_selected_annotation_for_pvs1(annotation_records, state.transcript_selection),
            transcript_selection=state.transcript_selection,
            gene_disease_context=context,
            context_consistency=state.context_consistency,
            transcript_validation=state.transcript_validation,
            provider_data=_pvs1_provider_data(options),
            manual_overrides=_pvs1_manual_overrides(options),
            config=options.get("pvs1_config"),
        ),
    )
    if pvs1_result is not None:
        pvs1_item, pvs1_decision = pvs1_result
        pvs1_item, pvs1_decision = apply_pvs1_overrides(
            pvs1_item,
            pvs1_decision,
            state.vcep_override_context,
        )
        step_results["evaluate_pvs1"] = {
            "decision": pvs1_decision.model_dump(mode="json"),
            "evidence_item": json.loads(pvs1_item.model_dump_json()) if pvs1_item else None,
        }
        limitations.extend(pvs1_decision.limitations)
        limitations.extend(pvs1_decision.blocking_reasons)
        if pvs1_item is not None:
            state.evidence_items.append(pvs1_item)

    if options.get("include_computational", True):
        vep_dependency = dependency_check_from_plan(provider_execution_plan, "evaluate_computational_evidence")
        if vep_dependency is None:
            vep_dependency = _fallback_vep_check(provider_identity)
        state.provider_dependency_checks["vep"] = vep_dependency.model_dump(mode="json")
        computational_result = run_step(
            "evaluate_computational_evidence",
            audit_trail,
            limitations,
            lambda: _skip_or_evaluate_computational_step(
                vep_dependency=vep_dependency,
                options=options,
                variant=normalized_variant,
                data_sources_config=data_sources_config,
                annotation=_selected_annotation_for_pvs1(annotation_records, state.transcript_selection),
                context_consistency=state.context_consistency,
                existing_evidence_items=state.evidence_items,
                vcep_override_context=state.vcep_override_context,
            ),
        )
        if computational_result is not None:
            if isinstance(computational_result, dict) and computational_result.get("provider_dependency"):
                limitations.extend(computational_result.get("limitations") or [])
                state.provider_dependency_review_flags.extend(
                    ReviewFlag.model_validate(flag)
                    for flag in computational_result.get("review_flags") or []
                    if isinstance(flag, dict)
                )
                step_results["evaluate_computational_evidence"] = computational_result
            else:
                computational_items, review_flags, summary, computational_predictions = computational_result
                computational_items = attach_computational_override_note(
                    computational_items,
                    state.vcep_override_context,
                )
                state.evidence_items.extend(computational_items)
                decision = summary.get("decision") or {}
                limitations.extend(decision.get("limitations") or [])
                limitations.extend(decision.get("conflict_reasons") or [])
                limitations.extend(decision.get("double_counting_warnings") or [])
                step_results["evaluate_computational_evidence"] = {
                    "evidence_items": [json.loads(item.model_dump_json()) for item in computational_items],
                    "review_flags": [json.loads(flag.model_dump_json()) for flag in review_flags],
                    "summary": summary,
                }
                variant_resolution = _enrich_resolution_from_computational_predictions(
                    variant_resolution,
                    computational_predictions,
                )
                if variant_resolution is not None:
                    step_results["resolve_variant"] = variant_resolution.model_dump(mode="json")

    clinvar_records = []
    if options.get("include_clinvar", True):
        clinvar_dependency = dependency_check_from_plan(provider_execution_plan, "query_clinvar")
        if clinvar_dependency is None:
            clinvar_dependency = _fallback_clinvar_check(provider_identity)
        state.provider_dependency_checks["clinvar"] = clinvar_dependency.model_dump(mode="json")
        if _online_source(data_sources_config, "clinvar") and not clinvar_dependency.satisfied:
            _record_dependency_skip(
                "query_clinvar",
                clinvar_dependency,
                step_results,
                limitations,
                state.provider_dependency_review_flags,
            )
            clinvar_result = None
        else:
            clinvar_result = run_step(
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
            state.evidence_items.extend(clinvar_result.candidate_evidence_items)
            limitations.extend(clinvar_result.limitations)
            step_results["query_clinvar"] = json.loads(clinvar_result.model_dump_json())

    if options.get("include_clingen_erepo", False):
        state.clingen_erepo_result = run_step(
            "query_clingen_erepo",
            audit_trail,
            limitations,
            lambda: build_clingen_erepo_provider(
                data_sources_config.source("clingen_erepo"),
                options.get("clingen_erepo_records"),
            ).query(
                _clingen_erepo_query(normalized_variant, context, options),
                variant=normalized_variant,
                context=context,
                clinvar_records=clinvar_records,
            ),
        )
        if state.clingen_erepo_result is not None:
            clingen_erepo_candidate_items = _clingen_erepo_candidate_items(
                state.clingen_erepo_result.matches
            )
            state.evidence_items.extend(clingen_erepo_candidate_items)
            limitations.extend(state.clingen_erepo_result.limitations)
            step_results["query_clingen_erepo"] = json.loads(
                state.clingen_erepo_result.model_dump_json()
            )

    literature_records = []
    if options.get("include_literature", True):
        if _use_online_literature(options):
            literature_dependency = dependency_check_from_plan(
                provider_execution_plan, "search_and_summarize_literature"
            )
            if literature_dependency is None:
                literature_dependency = _fallback_lit_check(
                    provider_identity,
                    explicit_query=options.get("search_query"),
                    pmids=options.get("pmids") or [],
                )
            state.provider_dependency_checks["literature"] = literature_dependency.model_dump(mode="json")
            if not literature_dependency.satisfied:
                _record_dependency_skip(
                    "search_and_summarize_literature",
                    literature_dependency,
                    step_results,
                    limitations,
                    state.provider_dependency_review_flags,
                )
                literature_summary_result = None
            else:
                literature_summary_result = run_step(
                    "search_and_summarize_literature",
                    audit_trail,
                    limitations,
                    lambda: literature_summarizer(
                        {
                            "gene": context.gene_symbol or normalized_variant.gene_symbol or "unknown",
                            "variant": normalized_variant.hgvs_c
                            or normalized_variant.hgvs_p
                            or normalized_variant.variant_id,
                            "transcript": _variant_transcript_label(normalized_variant),
                            "disease": context.disease_name,
                            "inheritance": context.inheritance_mode,
                            "phenotype": context.phenotype_terms,
                            "literature_records": options.get("literature_records") or [],
                            "pmids": options.get("pmids") or [],
                            "search_query": options.get("search_query"),
                            "variant_aliases": options.get("variant_aliases") or [],
                            "use_online_pubmed": bool(options.get("use_online_pubmed")),
                            "use_online_litvar": bool(options.get("use_online_litvar")),
                            "provider_cache_dir": options.get("provider_cache_dir"),
                        }
                    ),
                )
            if literature_summary_result is not None:
                limitations.extend(literature_summary_result.limitations)
                step_results["search_and_summarize_literature"] = (
                    literature_summary_result.model_dump(mode="json")
                )
        else:
            literature_result = run_step(
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
                state.evidence_items.extend(literature_result.candidate_evidence_items)
                limitations.extend(literature_result.limitations)
                step_results["search_literature_evidence"] = json.loads(
                    literature_result.model_dump_json()
                )

    supplemental_items = run_step(
        "load_mock_supplemental_evidence",
        audit_trail,
        limitations,
        lambda: _supplemental_evidence_items(options, normalized_variant),
    )
    if supplemental_items is not None:
        state.evidence_items.extend(supplemental_items)
        step_results["load_mock_supplemental_evidence"] = [
            json.loads(item.model_dump_json()) for item in supplemental_items
        ]

    state.context_consistency = run_step(
        "evaluate_context_consistency",
        audit_trail,
        limitations,
        lambda: evaluate_context_consistency(
            normalized_variant,
            context,
            annotation_records=annotation_records,
            transcript_selection=state.transcript_selection,
            transcript_validation=state.transcript_validation,
            clinvar_records=clinvar_records,
            population_records=population_records,
            literature_records=literature_records,
        ),
    )
    if state.context_consistency is not None:
        limitations.extend(state.context_consistency.limitations)
        step_results["evaluate_context_consistency"] = json.loads(
            state.context_consistency.model_dump_json()
        )

    if clinvar_records and options.get("include_ps1_pm5", True):
        ps1_pm5_result = run_step(
            "evaluate_ps1_pm5_evidence",
            audit_trail,
            limitations,
            lambda: generate_ps1_pm5_evidence(
                variant=normalized_variant,
                context=context,
                clinvar_records=clinvar_records,
                context_consistency=state.context_consistency,
                transcript_validation=state.transcript_validation,
                provider_provenance={"source_record_count": len(clinvar_records)},
            ),
        )
        if ps1_pm5_result is not None:
            ps1_pm5_items, ps1_pm5_decisions = ps1_pm5_result
            ps1_pm5_items = apply_ps1_pm5_overrides(ps1_pm5_items, state.vcep_override_context)
            state.evidence_items.extend(ps1_pm5_items)
            for decision in ps1_pm5_decisions:
                limitations.extend(decision.limitations)
                limitations.extend(decision.blocking_reasons)
            step_results["evaluate_ps1_pm5_evidence"] = {
                "decisions": [
                    decision.model_dump(mode="json") for decision in ps1_pm5_decisions
                ],
                "evidence_items": [
                    json.loads(item.model_dump_json()) for item in ps1_pm5_items
                ],
            }

    if state.vcep_override_context is not None and state.vcep_override_context.applied:
        state.evidence_items = apply_disabled_criteria(state.evidence_items, state.vcep_override_context)
        step_results["apply_vcep_disabled_criteria"] = {
            "disabled_criteria": list(state.vcep_override_context.disabled_criteria),
            "evidence_items": [json.loads(item.model_dump_json()) for item in state.evidence_items],
        }

    reviewed_payload = _reviewed_evidence_payload(arguments, options, limitations)
    reviewed_result = run_step(
        "process_reviewed_evidence",
        audit_trail,
        limitations,
        lambda: process_reviewed_evidence(reviewed_payload, state.evidence_items, normalized_variant),
    )
    if reviewed_result is not None:
        state.evidence_items.extend(reviewed_result.applied_items)
        state.evidence_items.extend(reviewed_result.review_note_items)
        limitations.extend(reviewed_result.limitations)
        state.reviewed_review_flags = list(reviewed_result.review_flags)
        state.reviewed_evidence_records = list(reviewed_result.reviewed_evidence_records)
        step_results["process_reviewed_evidence"] = {
            "reviewed_evidence_records": state.reviewed_evidence_records,
            "applied_items": [
                json.loads(item.model_dump_json()) for item in reviewed_result.applied_items
            ],
            "review_note_items": [
                json.loads(item.model_dump_json()) for item in reviewed_result.review_note_items
            ],
            "review_flags": [
                json.loads(flag.model_dump_json()) for flag in reviewed_result.review_flags
            ],
            "limitations": reviewed_result.limitations,
        }

    step_results["combine_all_evidence"] = {
        "evidence_item_count": len(state.evidence_items),
        "evidence_ids": [item.evidence_id for item in state.evidence_items],
    }
    audit_trail.append(audit_event("combine_all_evidence", "completed", None))

    return EvidencePhaseResult(
        evidence_items=state.evidence_items,
        context_consistency=state.context_consistency,
        transcript_selection=state.transcript_selection,
        transcript_validation=state.transcript_validation,
        variant_resolution=variant_resolution,
        reviewed_evidence_records=state.reviewed_evidence_records,
        reviewed_review_flags=state.reviewed_review_flags,
        provider_dependency_review_flags=state.provider_dependency_review_flags,
        provider_dependency_checks=state.provider_dependency_checks,
        vcep_signal_result=state.vcep_signal_result,
        vcep_override_context=state.vcep_override_context,
        clingen_erepo_result=state.clingen_erepo_result,
    )


def _clinvar_query(variant: Variant, context: GeneDiseaseContext) -> ClinVarQuery:
    query = ClinVarQuery.from_variant(variant)
    query.condition = context.disease_name
    query.include_gene_comparators = True
    return query


def _clingen_erepo_query(
    variant: Variant,
    context: GeneDiseaseContext,
    options: dict[str, Any],
) -> ClinGenERepoQuery:
    query_payload = dict(options.get("clingen_erepo_query") or {})
    query = ClinGenERepoQuery.from_variant(
        variant,
        context,
        ca_id=query_payload.get("ca_id") or query_payload.get("canonical_allele_id"),
        clinvar_variation_id=(
            query_payload.get("clinvar_variation_id")
            or query_payload.get("variation_id")
            or query_payload.get("variationID")
        ),
    )
    payload = query.model_dump(mode="json", exclude_none=True)
    payload.update(query_payload)
    return ClinGenERepoQuery.model_validate(payload)


def _clingen_erepo_candidate_items(matches: list[Any]) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    for match in matches:
        record = match.record
        direction = _erepo_direction(record.classification)
        code = EvidenceCode.BP6 if direction == EvidenceDirection.BENIGN else EvidenceCode.PP5
        item = EvidenceItem(
            evidence_id=clingen_erepo_candidate_evidence_id(record.record_id),
            code=code,
            strength=EvidenceStrength.NONE,
            direction=direction,
            reason=(
                "ClinGen Evidence Repository curated external assertion. "
                "This is a review note only and was not counted as applied ACMG evidence."
            ),
            source=EvidenceSource(
                name="ClinGen Evidence Repository",
                version=record.classification_version,
                url=record.source_url,
                database_id=record.record_id,
                query=match.query_variant,
                raw_snapshot_ref=record.raw_snapshot_hash,
                provenance=record.provenance,
            ),
            confidence=match.confidence,
            requires_review=True,
            candidate_only=True,
            applied=False,
            triggered_by=["clingen_erepo_match"],
            supporting_data={
                "candidate_only": True,
                "applied": False,
                "evidence_status": "candidate",
                "automatic_application": False,
                "review_note": EREPO_REVIEW_NOTE,
                "clingen_erepo_match": match.model_dump(mode="json"),
                "clingen_erepo_record": record.model_dump(mode="json"),
                "vcep_classification": record.classification,
                "vcep_name": record.vcep_name,
                "match_level": match.match_level,
                "criteria_applied": [
                    item.model_dump(mode="json") for item in record.criteria_applied
                ],
                "evidence_summaries": [
                    item.model_dump(mode="json") for item in record.evidence_summaries
                ],
                "limitations": match.limitations,
            },
            review_flags=match.review_flags,
        )
        if match.match_level == ClinGenERepoMatchLevel.SAME_GENE:
            item.reason = (
                "ClinGen VCEP gene-level curation activity signal only. "
                "No variant-level ClinGen ERepo match was identified."
            )
            item.triggered_by = ["clingen_erepo_gene_signal"]
        items.append(item)
    return items


def _erepo_direction(classification: str) -> EvidenceDirection:
    text = classification.lower()
    if "benign" in text:
        return EvidenceDirection.BENIGN
    if "pathogenic" in text:
        return EvidenceDirection.PATHOGENIC
    return EvidenceDirection.NEUTRAL


def _use_online_literature(options: dict[str, Any]) -> bool:
    return bool(options.get("use_online_pubmed") or options.get("use_online_litvar"))


def _online_source(data_sources_config: DataSourcesConfig, source_name: str) -> bool:
    source = data_sources_config.source(source_name)
    return source.mode == ProviderMode.ONLINE and bool(source.online_enabled)


def _record_dependency_skip(
    step_name: str,
    dependency_check: Any,
    step_results: dict[str, Any],
    limitations: list[str],
    review_flags: list[ReviewFlag],
) -> dict[str, Any]:
    payload = dependency_skip_payload(dependency_check)
    step_results[step_name] = payload
    limitations.extend(payload.get("limitations") or [])
    review_flags.extend(
        ReviewFlag.model_validate(flag)
        for flag in payload.get("review_flags") or []
        if isinstance(flag, dict)
    )
    return payload


def _reviewed_evidence_payload(
    arguments: dict[str, Any],
    options: dict[str, Any],
    limitations: list[str],
) -> Any:
    top_level_present = "reviewed_evidence" in arguments
    option_present = "reviewed_evidence" in options
    if top_level_present and option_present:
        limitations.append(
            "Both top-level reviewed_evidence and options.reviewed_evidence were supplied; "
            "top-level reviewed_evidence was used."
        )
    if top_level_present:
        return arguments.get("reviewed_evidence")
    return options.get("reviewed_evidence")


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
    payload.setdefault("data_version", "inline-population-fixture-v1")
    payload.setdefault("dataset_version", payload["data_version"])
    payload.setdefault("genome_build", _genome_build_from_variant_id(str(variant_id)))
    payload.setdefault("coverage_quality", "high")
    payload.setdefault("population_match", True)
    source = dict(payload.get("source") or {})
    source.setdefault("name", payload.get("data_source") or "inline_population_fixture")
    source.setdefault("version", payload.get("data_version"))
    source.setdefault("query", {"variant_id": str(variant_id)})
    payload["source"] = source
    return {str(variant_id): PopulationFrequency.model_validate(payload)}


def _genome_build_from_variant_id(variant_id: str) -> str | None:
    build = variant_id.split("-", 1)[0]
    return build if build in {"GRCh37", "GRCh38"} else None


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


def _skip_or_evaluate_computational_step(
    *,
    vep_dependency: Any,
    options: dict[str, Any],
    variant: Variant,
    data_sources_config: DataSourcesConfig,
    annotation: VariantAnnotation | None = None,
    context_consistency: ContextConsistency | None = None,
    existing_evidence_items: list[EvidenceItem] | None = None,
    vcep_override_context: VCEPOverrideContext | None = None,
) -> Any:
    if (
        options.get("computational_predictions") is None
        and _online_source(data_sources_config, "computational")
        and not vep_dependency.satisfied
    ):
        return dependency_skip_payload(vep_dependency)
    return _evaluate_computational_step(
        options,
        variant,
        data_sources_config,
        annotation=annotation,
        context_consistency=context_consistency,
        existing_evidence_items=existing_evidence_items,
        vcep_override_context=vcep_override_context,
    )


def _evaluate_computational_step(
    options: dict[str, Any],
    variant: Variant,
    data_sources_config: DataSourcesConfig,
    *,
    annotation: VariantAnnotation | None = None,
    context_consistency: ContextConsistency | None = None,
    existing_evidence_items: list[EvidenceItem] | None = None,
    vcep_override_context: VCEPOverrideContext | None = None,
) -> tuple[list[EvidenceItem], list[Any], dict[str, Any], list[ComputationalPrediction]]:
    predictions = _computational_predictions(options, variant, data_sources_config)
    thresholds = computational_thresholds_from_options(options.get("computational_thresholds"))
    thresholds = apply_computational_threshold_overrides(thresholds, vcep_override_context)
    items, review_flags, summary = evaluate_computational_predictions(
        variant,
        predictions,
        thresholds,
        annotation=annotation,
        context_consistency=context_consistency,
        existing_evidence_items=existing_evidence_items or [],
        provider_provenance={
            "source_count": len({prediction.source.name for prediction in predictions}),
            "vcep_override": vcep_override_metadata(vcep_override_context),
        },
    )
    return items, review_flags, summary, predictions


def _should_select_transcript(options: dict[str, Any]) -> bool:
    return bool(
        options.get("include_transcript_selection")
        or options.get("annotations") is not None
        or options.get("annotation_records") is not None
        or options.get("annotation_text") is not None
    )


def _should_validate_transcripts(
    options: dict[str, Any],
    transcript_records: list[Any],
) -> bool:
    return bool(
        options.get("include_transcript_validation")
        or options.get("include_mane_transcript_validation")
        or transcript_records
        or options.get("transcript_metadata_records") is not None
        or options.get("transcript_metadata_json") is not None
        or options.get("transcript_metadata_jsonl") is not None
    )


def _transcript_fixture(options: dict[str, Any]) -> Any:
    return (
        options.get("transcript_metadata_records")
        or options.get("transcript_metadata")
        or options.get("transcript_fixture")
        or options.get("mane_transcript_fixture")
        or options.get("transcript_metadata_json")
        or options.get("transcript_metadata_jsonl")
    )


def _select_transcript_step(
    annotations: list[VariantAnnotation],
    variant: Variant,
    options: dict[str, Any],
) -> TranscriptSelection:
    user_transcript = options.get("user_transcript") or _variant_transcript_label(variant)
    return select_transcript(annotations, user_transcript=user_transcript)


def _enrich_transcript_selection(
    selection: TranscriptSelection | None,
    validation: TranscriptValidationResult,
) -> TranscriptSelection | None:
    if selection is None:
        return None
    metadata_by_transcript = {
        item.get("transcript"): item
        for item in [
            *(validation.mane_select_candidates or []),
            *(validation.canonical_candidates or []),
            *([validation.matched_record] if validation.matched_record else []),
        ]
        if isinstance(item, dict) and item.get("transcript")
    }
    for collection_name in ("candidate_transcripts", "rejected_transcripts"):
        collection = getattr(selection, collection_name)
        for candidate in collection:
            transcript = candidate.get("transcript")
            metadata = metadata_by_transcript.get(transcript)
            if not metadata:
                continue
            candidate.update(
                {
                    "transcript_version": metadata.get("transcript_version"),
                    "mane_status": metadata.get("mane_status"),
                    "protein_accession": metadata.get("protein_accession"),
                    "transcript_status": metadata.get("transcript_status"),
                    "genome_build": metadata.get("genome_build"),
                    "exon_count": metadata.get("exon_count"),
                    "cds_length": metadata.get("cds_length"),
                    "nmd_relevance": metadata.get("nmd_relevance"),
                    "transcript_source": metadata.get("transcript_source"),
                    "tags": metadata.get("tags") or [],
                }
            )
    selection.review_flags = _unique_review_flags(
        [*selection.review_flags, *validation.review_flags]
    )
    selection.limitations = _unique([*selection.limitations, *validation.limitations])
    selection.provenance["transcript_validation"] = validation.provenance
    return selection


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


def _should_resolve_vcep(options: dict[str, Any]) -> bool:
    return bool(
        options.get("include_vcep_signals")
        or options.get("apply_vcep_overrides")
        or options.get("vcep_profile_records")
        or options.get("vcep_profile_file")
        or options.get("vcep_kb_dir")
    )


def _enrich_resolution_from_computational_predictions(
    resolution: VariantResolutionResult | None,
    predictions: list[ComputationalPrediction],
) -> VariantResolutionResult | None:
    if resolution is None:
        return None
    vep_prediction = _vep_resolution_prediction(predictions)
    if vep_prediction is None:
        return resolution
    hgvs_p = vep_prediction.hgvs_p or vep_prediction.protein_change
    if not hgvs_p:
        return resolution
    existing = resolution.resolved_hgvs_p
    if existing is not None and existing.hgvs_p:
        return resolution

    consequence = (
        vep_prediction.prediction
        if vep_prediction.prediction not in {"unavailable", "unknown"}
        else None
    )
    source_payload = vep_prediction.source.model_dump(mode="json")
    provenance = {
        "source": vep_prediction.source.name,
        "source_version": vep_prediction.source.version,
        "scope": "variant resolution only; not ACMG evidence",
        "provider_record": source_payload,
        "transcript": vep_prediction.transcript,
        "method": vep_prediction.method,
    }
    protein = ResolvedProtein(
        hgvs_p=hgvs_p,
        protein_accession=hgvs_p.split(":", 1)[0] if ":" in hgvs_p else None,
        consequence=consequence,
        confidence=0.6,
        limitations=[
            "Protein consequence was populated from Ensembl VEP descriptive output; it is not ACMG evidence."
        ],
        provenance=[provenance],
    )
    resolved_variant = resolution.resolved_variant
    if resolved_variant is not None:
        update: dict[str, Any] = {}
        if not resolved_variant.hgvs_p:
            update["hgvs_p"] = hgvs_p
        transcript = resolved_variant.transcript
        if transcript is not None:
            transcript_update: dict[str, Any] = {}
            if not transcript.hgvs_p:
                transcript_update["hgvs_p"] = hgvs_p
            if consequence and not transcript.consequence:
                transcript_update["consequence"] = consequence
            if transcript_update:
                update["transcript"] = transcript.model_copy(update=transcript_update)
        if update:
            resolved_variant = resolved_variant.model_copy(update=update)
    limitations = [
        item
        for item in resolution.limitations
        if item != "Protein consequence could not be resolved from local fixtures."
    ]
    limitations.append(
        "VEP descriptive protein/consequence facts were added to variant_resolution only; evidence generation remains evaluator-gated."
    )
    resolution_steps = [
        step.model_copy(update={"status": "resolved", "confidence": 0.6})
        if step.step_name == "protein_resolution"
        else step
        for step in resolution.resolution_steps
    ]
    return resolution.model_copy(
        update={
            "status": "partial" if resolution.status == "unresolved" else resolution.status,
            "confidence": max(resolution.confidence, 0.2),
            "resolved_hgvs_p": protein,
            "limitations": _unique(limitations),
            "resolution_steps": resolution_steps,
            "provenance": [
                *resolution.provenance,
                {
                    "source": vep_prediction.source.name,
                    "source_version": vep_prediction.source.version,
                    "scope": "VEP descriptive bridge for variant resolution only; not ACMG evidence",
                    "query": vep_prediction.source.query,
                    "raw_snapshot_ref": vep_prediction.source.raw_snapshot_ref,
                },
            ],
            "resolved_variant": resolved_variant,
        }
    )


def _vep_resolution_prediction(
    predictions: list[ComputationalPrediction],
) -> ComputationalPrediction | None:
    for prediction in predictions:
        source_name = prediction.source.name.lower()
        method = prediction.method.lower()
        if "vep" not in method and "computational" != source_name:
            continue
        if prediction.hgvs_p or prediction.protein_change:
            return prediction
    return None


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


# ── 79A-3D: lazy fallback helpers (only when plan is absent) ──────────


def _fallback_gnomad_check(identity: Any) -> ProviderDependencyCheck:
    from variant_pathogenicity_rater.providers.dependencies import (
        check_gnomad_dependency,
    )
    return check_gnomad_dependency(identity)


def _fallback_vep_check(identity: Any) -> ProviderDependencyCheck:
    from variant_pathogenicity_rater.providers.dependencies import (
        check_vep_dependency,
    )
    return check_vep_dependency(identity)


def _fallback_clinvar_check(identity: Any) -> ProviderDependencyCheck:
    from variant_pathogenicity_rater.providers.dependencies import (
        check_clinvar_dependency,
    )
    return check_clinvar_dependency(identity)


def _fallback_lit_check(
    identity: Any,
    *,
    explicit_query: str | None = None,
    pmids: list[str] | None = None,
) -> ProviderDependencyCheck:
    from variant_pathogenicity_rater.providers.dependencies import (
        check_literature_dependency,
    )
    return check_literature_dependency(
        identity,
        explicit_query=explicit_query,
        pmids=pmids or [],
    )
