from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from variant_pathogenicity_rater.literature_agent.extraction import extract_literature_claims
from variant_pathogenicity_rater.literature_agent.safety import (
    NOT_APPLIED_REASON,
    base_limitations,
    candidate,
    confidence,
    normalized_text,
    truthy,
)
from variant_pathogenicity_rater.literature_agent.schema import (
    LiteratureAgentInput,
    LiteratureAgentResult,
    LiteratureEvidenceAssessment,
)


def assess_literature_evidence(payload: LiteratureAgentInput | dict[str, Any]) -> LiteratureAgentResult:
    request = (
        payload
        if isinstance(payload, LiteratureAgentInput)
        else LiteratureAgentInput.model_validate(payload)
    )
    records = list(request.literature_records)
    limitations = base_limitations()
    provenance: dict[str, Any] = {
        "agent": "acmg_literature_evidence",
        "version": "0.1.0",
        "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
        "offline_by_default": True,
        "online_search_requested": request.use_online_search,
        "input_pmids": request.pmids,
        "search_query": request.search_query,
    }
    if request.pmids and not records:
        limitations.append(
            "PMIDs were provided without literature_records; offline mode cannot retrieve abstracts."
        )
    if request.use_online_search:
        limitations.append(
            "Online search is opt-in but no network retrieval is performed by this local plugin implementation."
        )
        provenance["online_search_status"] = "not_performed"

    extractions = extract_literature_claims(
        records,
        gene=request.gene,
        variant=request.variant,
        transcript=request.transcript,
        disease=request.disease,
    )

    assessments: list[LiteratureEvidenceAssessment] = []
    for record, extraction in zip(records, extractions, strict=False):
        evidence_type = _record_type(record)
        if evidence_type == "functional":
            assessments.append(assess_functional_evidence(record, request))
        elif evidence_type == "de_novo":
            assessments.append(assess_de_novo_evidence(record, request))
        elif evidence_type == "segregation":
            assessments.append(assess_segregation_evidence(record, request))
        elif evidence_type in {"case_count", "case_report", "case_enrichment"}:
            assessments.append(assess_case_count_evidence(record, request))
        elif evidence_type == "phenotype_specificity":
            assessments.append(assess_phenotype_specificity(record, request))
        elif evidence_type in {"trans", "trans_observation", "pm3"}:
            assessments.append(assess_trans_observation(record, request))
        elif evidence_type in {"same_amino_acid", "same_residue", "residue", "ps1_pm5"}:
            assessments.append(assess_same_amino_acid_or_residue(record, request))
        else:
            assessments.append(_candidate_assessment("ACMG_candidate", evidence_type, record, request))

        assessments[-1].provenance["extraction"] = extraction.model_dump(mode="json")

    return LiteratureAgentResult(
        literature_evidence_assessments=assessments,
        suggested_evidence=[_suggested_item(item) for item in assessments],
        review_questions=generate_review_questions(assessments),
        citations=_citations(assessments),
        limitations=limitations,
        provenance=provenance,
    )


def assess_functional_evidence(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    valid = normalized_text(record.get("assay_validity")) in {"valid", "validated", "well_validated", "high"}
    controls = truthy(record.get("controls_adequate"))
    direction = normalized_text(record.get("functional_direction") or record.get("direction"))
    clear_direction = direction in {
        "loss_of_function",
        "reduced_function",
        "abnormal",
        "damaging",
        "pathogenic",
        "normal",
        "no_effect",
        "benign",
    }
    if valid and controls and clear_direction:
        if direction in {"normal", "no_effect", "benign"}:
            return _assessment("BS3", "supporting", "functional", record, request)
        return _assessment("PS3", "supporting", "functional", record, request)
    code = "BS3" if direction in {"normal", "no_effect", "benign"} else "PS3"
    return _candidate_assessment(
        candidate(code),
        "functional",
        record,
        request,
        "Functional assay validity, controls, or direction were not explicit enough.",
    )


def assess_de_novo_evidence(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    confirmed = truthy(record.get("confirmed_de_novo")) or normalized_text(record.get("de_novo_status")) == "confirmed"
    parentage = truthy(record.get("parentage_confirmed"))
    if confirmed and parentage:
        return _assessment("PS2", "supporting", "de_novo", record, request)
    if truthy(record.get("de_novo_reported")) or "de novo" in normalized_text(record.get("claim")):
        return _assessment("PM6", "supporting", "de_novo", record, request)
    return _candidate_assessment(candidate("PM6"), "de_novo", record, request)


def assess_segregation_evidence(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    count = _int_or_none(record.get("segregation_count"))
    if count and count > 0 and truthy(record.get("pedigree_context")):
        return _assessment("PP1", "supporting", "segregation", record, request)
    return _candidate_assessment(
        candidate("PP1"),
        "segregation",
        record,
        request,
        "Segregation count and pedigree context must both be explicit.",
    )


def assess_case_count_evidence(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    count = _int_or_none(record.get("case_count"))
    unrelated = truthy(record.get("multiple_unrelated_cases")) or truthy(record.get("unrelated_cases"))
    enrichment = truthy(record.get("case_control_enrichment")) or truthy(record.get("enrichment_logic"))
    if (count and count >= 2 and unrelated) or enrichment:
        return _assessment("PS4", "supporting", "case_count", record, request)
    return _candidate_assessment(
        candidate("PS4"),
        "case_count",
        record,
        request,
        "Single case reports or isolated cases cannot support a strong PS4 suggestion.",
    )


def assess_phenotype_specificity(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    return _candidate_assessment(
        candidate("PP4"),
        "phenotype_specificity",
        record,
        request,
        "PP4 is review-only here and cannot independently drive classification.",
    )


def assess_trans_observation(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    trans_status = normalized_text(record.get("trans_cis_status") or record.get("phase"))
    if trans_status == "trans" or truthy(record.get("confirmed_trans")):
        return _assessment("PM3", "supporting", "trans_observation", record, request)
    return _candidate_assessment(
        candidate("PM3"),
        "trans_observation",
        record,
        request,
        "PM3 requires explicit evidence that variants are in trans.",
    )


def assess_same_amino_acid_or_residue(
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
) -> LiteratureEvidenceAssessment:
    relationship = normalized_text(record.get("residue_relationship") or record.get("match_type"))
    if relationship == "same_amino_acid":
        return _assessment("PS1", "supporting", "same_amino_acid_or_residue", record, request)
    if relationship == "same_residue_different_missense":
        return _assessment("PM5", "supporting", "same_amino_acid_or_residue", record, request)
    code = "PM5" if relationship in {"same_residue", "same_codon"} else "PS1"
    return _candidate_assessment(
        candidate(code),
        "same_amino_acid_or_residue",
        record,
        request,
        "PS1/PM5 requires strict distinction among same amino acid, same residue, same codon, and nearby residue.",
    )


def generate_review_questions(
    assessments: list[LiteratureEvidenceAssessment],
) -> list[str]:
    questions = [
        "Does the cited article describe the exact queried variant, gene, disease, and transcript context?",
        "Is the evidence independent from other cited records and free from duplicate family or case counting?",
    ]
    for item in assessments:
        if item.evidence_type == "functional":
            questions.append("Were functional assay validity, controls, and effect direction explicitly established?")
        if item.evidence_type == "de_novo":
            questions.append("Was parentage confirmed for every de novo assertion?")
        if item.evidence_type == "segregation":
            questions.append("What is the pedigree structure and count of informative segregations?")
        if item.evidence_type == "case_count":
            questions.append("Are cases unrelated, enriched against controls, and counted only once?")
        if item.evidence_type == "trans_observation":
            questions.append("Is phase explicitly confirmed as trans?")
        if item.evidence_type == "same_amino_acid_or_residue":
            questions.append("Is the claim same amino acid, same residue with different missense, same codon, or nearby residue?")
    return list(dict.fromkeys(questions))


def _assessment(
    code: str,
    strength: str,
    evidence_type: str,
    record: dict[str, Any],
    request: LiteratureAgentInput | None,
) -> LiteratureEvidenceAssessment:
    return LiteratureEvidenceAssessment(
        candidate_code=code,
        suggested_strength=strength,
        evidence_type=evidence_type,
        variant_match_level=record.get("variant_match_level", "exact" if request else None),
        disease_match_level=record.get("disease_match_level"),
        phenotype_match_level=record.get("phenotype_match_level"),
        assay_validity=record.get("assay_validity"),
        case_count=_int_or_none(record.get("case_count")),
        segregation_count=_int_or_none(record.get("segregation_count")),
        de_novo_status=record.get("de_novo_status"),
        trans_cis_status=record.get("trans_cis_status") or record.get("phase"),
        inheritance_context=record.get("inheritance_context") or (request.inheritance if request else None),
        extracted_claims=_claims(record),
        citation=record.get("citation"),
        pmid=str(record["pmid"]) if record.get("pmid") else None,
        doi=record.get("doi"),
        source=record.get("source", "caller_supplied_literature_record"),
        confidence=confidence(record),
        requires_manual_review=True,
        reason_not_applied=NOT_APPLIED_REASON,
        limitations=base_limitations(),
        provenance={"record_id": record.get("record_id"), "input_record": record},
    )


def _candidate_assessment(
    code: str,
    evidence_type: str,
    record: dict[str, Any],
    request: LiteratureAgentInput | None = None,
    limitation: str | None = None,
) -> LiteratureEvidenceAssessment:
    item = _assessment(code, "none", evidence_type, record, request)
    if limitation:
        item.limitations.append(limitation)
    return item


def _suggested_item(item: LiteratureEvidenceAssessment) -> dict[str, Any]:
    return {
        "source_candidate_evidence_id": _suggested_evidence_id(item),
        "code": item.candidate_code,
        "strength": item.suggested_strength,
        "candidate_only": True,
        "applied": False,
        "requires_manual_review": True,
        "reason_not_applied": item.reason_not_applied,
        "citation": item.citation,
        "confidence": item.confidence,
    }


def _suggested_evidence_id(item: LiteratureEvidenceAssessment) -> str:
    record_id = item.provenance.get("record_id")
    if record_id:
        return str(record_id)
    payload = {
        "code": item.candidate_code,
        "strength": item.suggested_strength,
        "citation": item.citation,
        "pmid": item.pmid,
        "doi": item.doi,
        "claims": item.extracted_claims,
    }
    digest = sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:12]
    return f"literature-suggested-{item.candidate_code.removesuffix('_candidate')}-{digest}"


def _record_type(record: dict[str, Any]) -> str:
    return normalized_text(record.get("evidence_type") or record.get("type") or "unknown")


def _claims(record: dict[str, Any]) -> list[str]:
    claims = record.get("extracted_claims") or record.get("claims") or record.get("sentences")
    if isinstance(claims, list):
        return [str(claim) for claim in claims]
    claim = record.get("claim") or record.get("description")
    return [str(claim)] if claim else []


def _citations(assessments: list[LiteratureEvidenceAssessment]) -> list[str]:
    citations = []
    for item in assessments:
        citation = item.citation or (f"PMID:{item.pmid}" if item.pmid else None) or item.doi
        if citation:
            citations.append(citation)
    return list(dict.fromkeys(citations))


def _int_or_none(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
