from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from variant_pathogenicity_rater.data_sources.config import DataSourceConfig, ProviderMode
from variant_pathogenicity_rater.data_sources.online.literature_online import (
    fetch_online_literature_records,
)
from variant_pathogenicity_rater.literature_agent.assessment import assess_literature_evidence
from variant_pathogenicity_rater.literature_agent.deduplication import collapse_duplicate_records
from variant_pathogenicity_rater.literature_agent.query import build_query_plan
from variant_pathogenicity_rater.literature_agent.records import (
    normalize_literature_records,
    record_to_assessment_payload,
)
from variant_pathogenicity_rater.literature_agent.reviewed_draft import (
    create_reviewed_evidence_drafts,
)
from variant_pathogenicity_rater.literature_agent.schema import (
    CriterionSummary,
    LiteratureEvidenceAssessment,
    LiteratureSearchInput,
    LiteratureSearchResult,
)
from variant_pathogenicity_rater.literature_agent.summarizers import (
    summarize_literature_by_criterion,
)


NOT_APPLIED_REASON = (
    "Suggested literature evidence is not automatically applied to ACMG classification."
)


def search_and_summarize_literature(
    payload: LiteratureSearchInput | dict[str, Any],
) -> LiteratureSearchResult:
    request = (
        payload
        if isinstance(payload, LiteratureSearchInput)
        else LiteratureSearchInput.model_validate(payload)
    )
    query_plan = build_query_plan(request)
    limitations = [
        "Literature search and summary output is suggested evidence only.",
        "Literature-derived evidence is not added to applied evidence.",
        "The ACMG classification combiner is not invoked or modified.",
        "Manual review is required before any literature-derived criterion can be applied.",
    ]
    if request.pmids and not request.literature_records:
        limitations.append(
            "PMIDs were provided without literature_records; offline mode cannot retrieve abstracts."
        )
    online_records = []
    if request.use_online_search or request.use_online_pubmed or request.use_online_litvar:
        fetched, online_limitations = fetch_online_literature_records(
            request,
            config=DataSourceConfig(
                name="literature",
                mode=ProviderMode.ONLINE,
                online_enabled=True,
                source_version="PubMed/LitVar live",
                parser_version="literature-online-parser-v1",
                cache_dir=request.provider_cache_dir,
            ),
        )
        online_records = [record.model_dump(mode="json") for record in fetched]
        limitations.extend(online_limitations)

    normalized = normalize_literature_records([*request.literature_records, *online_records], request)
    deduped = collapse_duplicate_records(normalized.records)
    criterion_summaries = summarize_literature_by_criterion(deduped.records, request)
    assessment_records = [record_to_assessment_payload(record) for record in deduped.records]
    agent_result = assess_literature_evidence(
        {
            "gene": request.gene,
            "variant": request.variant,
            "transcript": request.transcript,
            "disease": request.disease,
            "inheritance": request.inheritance,
            "phenotype": request.phenotype,
            "literature_records": assessment_records,
            "pmids": request.pmids,
            "search_query": request.search_query,
            "use_online_search": request.use_online_search
            or request.use_online_pubmed
            or request.use_online_litvar,
        }
    )
    assessments = _merge_assessments_with_criterion_summaries(
        agent_result.literature_evidence_assessments,
        criterion_summaries,
    )
    suggested = [_candidate_suggestion(item) for item in assessments]
    evidence_items = [_candidate_evidence_item(item) for item in assessments]
    draft_payload = create_reviewed_evidence_drafts(
        {
            "literature_evidence_assessments": [item.model_dump(mode="json") for item in assessments],
            "suggested_evidence": suggested,
            "review_questions": _review_questions(criterion_summaries, agent_result.review_questions),
        }
    )
    blocking_flags = _unique_flags(
        [
            *normalized.review_flags,
            *[flag for summary in criterion_summaries for flag in summary.blocking_flags],
        ]
    )
    review_flags = _unique_flags(
        [flag for summary in criterion_summaries for flag in summary.review_flags]
    )
    citations = _citations(deduped.records, assessments)
    return LiteratureSearchResult(
        literature_search_results=deduped.records,
        literature_summary=_literature_summary(deduped.records, criterion_summaries),
        criterion_summaries=criterion_summaries,
        literature_evidence_assessments=assessments,
        suggested_evidence=suggested,
        evidence_items=evidence_items,
        review_questions=_review_questions(criterion_summaries, agent_result.review_questions),
        blocking_flags=blocking_flags,
        review_flags=review_flags,
        duplicate_groups=deduped.duplicate_groups,
        limitations=_unique(
            [
                *limitations,
                *normalized.limitations,
                *agent_result.limitations,
                *[item for summary in criterion_summaries for item in summary.limitations],
            ]
        ),
        reviewed_evidence_drafts=list(draft_payload.get("reviewed_evidence_drafts") or []),
        reviewed_evidence=list(draft_payload.get("reviewed_evidence") or []),
        query_plan=query_plan,
        citations=citations,
        provenance={
            "agent": "general_literature_search_and_summary_engine",
            "version": "0.1.0",
            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
            "offline_by_default": True,
            "online_pubmed_requested": request.use_online_pubmed or request.use_online_search,
            "online_litvar_requested": request.use_online_litvar or request.use_online_search,
            "caller_supplied_record_count": len(request.literature_records),
            "deduplicated_record_count": len(deduped.records),
        },
        applied_evidence=[],
        final_classification_changed=False,
        human_review={
            "required": True,
            "notice": "Literature search output is suggested evidence only; no classification change was made.",
        },
    )


def _merge_assessments_with_criterion_summaries(
    assessments: list[LiteratureEvidenceAssessment],
    summaries: list[CriterionSummary],
) -> list[LiteratureEvidenceAssessment]:
    output = list(assessments)
    existing = {(item.candidate_code.removesuffix("_candidate"), tuple(item.extracted_claims)) for item in output}
    for summary in summaries:
        if not summary.supporting_records or not summary.suggested_code:
            continue
        key = (summary.suggested_code, tuple(summary.extracted_claims))
        if key in existing:
            continue
        output.append(
            LiteratureEvidenceAssessment(
                candidate_code=summary.suggested_code,
                suggested_strength=summary.suggested_strength,
                evidence_type=summary.evidence_domain,
                extracted_claims=summary.extracted_claims,
                confidence=summary.confidence,
                requires_manual_review=True,
                reason_not_applied=NOT_APPLIED_REASON,
                limitations=summary.limitations,
                provenance={
                    "criterion_summary": summary.model_dump(mode="json"),
                    "record_id": f"criterion-summary-{summary.criterion.lower()}",
                },
            )
        )
    return output


def _candidate_suggestion(item: LiteratureEvidenceAssessment) -> dict[str, Any]:
    code = item.candidate_code.removesuffix("_candidate")
    return {
        "source_candidate_evidence_id": _suggestion_id(item),
        "code": code,
        "strength": item.suggested_strength,
        "suggested_strength": item.suggested_strength,
        "candidate_only": True,
        "applied": False,
        "requires_review": True,
        "requires_manual_review": True,
        "reason_not_applied": item.reason_not_applied or NOT_APPLIED_REASON,
        "citation": item.citation,
        "pmid": item.pmid,
        "doi": item.doi,
        "title": _title_from_assessment(item),
        "source": item.source,
        "confidence": item.confidence,
        "extracted_claims": item.extracted_claims,
        "provenance": item.provenance,
    }


def _candidate_evidence_item(item: LiteratureEvidenceAssessment) -> dict[str, Any]:
    code = item.candidate_code.removesuffix("_candidate")
    direction = "benign" if code.startswith(("BS", "BP", "BA")) else "pathogenic"
    suggestion = _candidate_suggestion(item)
    return {
        "evidence_id": suggestion["source_candidate_evidence_id"],
        "code": code,
        "strength": "none",
        "suggested_strength": item.suggested_strength,
        "direction": direction,
        "reason": f"Candidate {code} literature evidence requires manual review.",
        "source": {
            "name": item.source or "general_literature_search",
            "retrieval_timestamp": None,
            "query": {},
            "provenance": item.provenance,
        },
        "confidence": item.confidence,
        "requires_review": True,
        "requires_manual_review": True,
        "candidate_only": True,
        "applied": False,
        "triggered_by": ["general_literature_search", item.evidence_type],
        "supporting_data": {
            **suggestion,
            "automatic_application": False,
            "human_review_required": True,
            "review_note": NOT_APPLIED_REASON,
        },
        "audit_trail": [],
        "review_flags": [],
    }


def _suggestion_id(item: LiteratureEvidenceAssessment) -> str:
    record_id = item.provenance.get("record_id")
    if record_id:
        return str(record_id)
    payload = {
        "code": item.candidate_code,
        "pmid": item.pmid,
        "doi": item.doi,
        "citation": item.citation,
        "claims": item.extracted_claims,
    }
    digest = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"literature-suggested-{item.candidate_code.removesuffix('_candidate')}-{digest}"


def _title_from_assessment(item: LiteratureEvidenceAssessment) -> str | None:
    raw = item.provenance.get("input_record")
    if isinstance(raw, dict) and raw.get("title"):
        return str(raw["title"])
    return None


def _review_questions(
    summaries: list[CriterionSummary],
    existing: list[str],
) -> list[str]:
    questions = [
        "Does each cited article describe the exact queried variant, gene, disease, and transcript context?",
        "Are duplicate families, cases, cohorts, and publications collapsed before any manual evidence review?",
        *existing,
        *[question for summary in summaries for question in summary.review_questions],
    ]
    return _unique(questions)


def _citations(records: list[Any], assessments: list[LiteratureEvidenceAssessment]) -> list[str]:
    citations: list[str] = []
    for record in records:
        citations.extend(record.citations)
    for item in assessments:
        if item.citation:
            citations.append(item.citation)
        if item.pmid:
            citations.append(f"PMID:{item.pmid}")
        if item.doi:
            citations.append(f"DOI:{item.doi}")
    return _unique(citations)


def _literature_summary(records: list[Any], summaries: list[CriterionSummary]) -> str:
    supported = [summary.criterion for summary in summaries if summary.supporting_records]
    if not records:
        return "No literature records were available from supplied/offline inputs."
    if not supported:
        return f"{len(records)} literature record(s) were normalized, with no criterion-specific support extracted."
    return (
        f"{len(records)} deduplicated literature record(s) were summarized for review-only "
        f"candidate support: {', '.join(_unique(supported))}."
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if value))


def _unique_flags(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for flag in flags:
        key = json.dumps(flag, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        output.append(flag)
    return output
