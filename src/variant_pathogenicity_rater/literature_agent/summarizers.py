from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.literature_agent.query import criteria_for_request
from variant_pathogenicity_rater.literature_agent.schema import (
    CriterionSummary,
    LiteratureRecord,
    LiteratureSearchInput,
)


def summarize_literature_by_criterion(
    records: list[LiteratureRecord],
    request: LiteratureSearchInput,
) -> list[CriterionSummary]:
    summaries: list[CriterionSummary] = []
    for criterion in criteria_for_request(request):
        if criterion == "PS3_BS3":
            summaries.extend(_functional(records))
        elif criterion == "PS2_PM6":
            summaries.extend(_de_novo(records))
        elif criterion == "PP1":
            summaries.append(_segregation(records))
        elif criterion == "PS4":
            summaries.append(_case_control(records))
        elif criterion == "PM3":
            summaries.append(_trans(records))
        elif criterion == "PP4":
            summaries.append(_phenotype(records))
        elif criterion == "PS1_PM5":
            summaries.extend(_ps1_pm5(records))
        elif criterion == "PM1":
            summaries.append(_pm1(records))
        elif criterion == "PVS1":
            summaries.append(_pvs1(records))
    return [summary for summary in summaries if summary.supporting_records or summary.limitations]


def _functional(records: list[LiteratureRecord]) -> list[CriterionSummary]:
    functional = _records_for(records, {"functional", "assay", "ps3", "bs3"})
    abnormal = [item for item in functional if _has_any(item, {"reduced", "abnormal", "loss", "damaging"})]
    normal = [item for item in functional if _has_any(item, {"normal", "no effect", "no_effect", "benign"})]
    return [
        _summary(
            "PS3",
            "functional_assay",
            abnormal,
            "Functional assay literature suggests abnormal or reduced function.",
            "supporting" if abnormal else "none",
            "Were assay validity, disease relevance, controls, and effect direction explicitly established?",
        ),
        _summary(
            "BS3",
            "functional_assay",
            normal,
            "Functional assay literature suggests normal function or no damaging effect.",
            "supporting" if normal else "none",
            "Were benign functional assay controls and calibration adequate for BS3 review?",
        ),
    ]


def _de_novo(records: list[LiteratureRecord]) -> list[CriterionSummary]:
    de_novo = _records_for(records, {"de_novo", "de novo", "trio", "parentage"})
    confirmed = [
        item
        for item in de_novo
        if _truthy(item, "confirmed_de_novo") and _truthy(item, "parentage_confirmed")
    ]
    unconfirmed = [
        item
        for item in de_novo
        if item not in confirmed and (_truthy(item, "de_novo_reported") or _has_any(item, {"de novo"}))
    ]
    return [
        _summary(
            "PS2",
            "de_novo",
            confirmed,
            "Confirmed de novo reports with parentage support PS2 review.",
            "supporting" if confirmed else "none",
            "Was parentage confirmed for each de novo assertion?",
        ),
        _summary(
            "PM6",
            "de_novo",
            unconfirmed,
            "Reported de novo observations without complete parentage support PM6 review.",
            "supporting" if unconfirmed else "none",
            "Is the de novo event confirmed or assumed, and is the variant exact?",
        ),
    ]


def _segregation(records: list[LiteratureRecord]) -> CriterionSummary:
    selected = _records_for(records, {"segregation", "cosegregation", "pedigree", "pp1"})
    return _summary(
        "PP1",
        "segregation",
        selected,
        "Segregation literature may support PP1 review.",
        "supporting" if selected else "none",
        "What pedigree structure and informative segregation count support PP1?",
    )


def _case_control(records: list[LiteratureRecord]) -> CriterionSummary:
    selected = _records_for(records, {"case-control", "case control", "enrichment", "unrelated", "ps4"})
    return _summary(
        "PS4",
        "case_control_or_enrichment",
        selected,
        "Case-control, enrichment, or unrelated-case literature may support PS4 review.",
        "supporting" if selected else "none",
        "Are cases independent, statistically enriched, and counted only once?",
    )


def _trans(records: list[LiteratureRecord]) -> CriterionSummary:
    selected = _records_for(records, {"trans", "compound heterozygous", "biallelic", "pm3"})
    confirmed = [item for item in selected if _truthy(item, "confirmed_trans") or _field(item, "phase") == "trans"]
    return _summary(
        "PM3",
        "trans_observation",
        confirmed or selected,
        "Biallelic or compound-heterozygous literature may support PM3 review.",
        "supporting" if confirmed else "none",
        "Is phase explicitly confirmed as trans rather than inferred?",
    )


def _phenotype(records: list[LiteratureRecord]) -> CriterionSummary:
    selected = _records_for(records, {"phenotype specificity", "specific phenotype", "pp4"})
    return _summary(
        "PP4",
        "phenotype_specificity",
        selected,
        "Phenotype specificity literature may support PP4 review only.",
        "none",
        "Is the phenotype highly specific for the queried gene-disease association?",
    )


def _ps1_pm5(records: list[LiteratureRecord]) -> list[CriterionSummary]:
    selected = _records_for(records, {"same amino acid", "same residue", "different missense", "ps1", "pm5"})
    ps1 = [item for item in selected if _field(item, "residue_relationship") == "same_amino_acid" or _has_any(item, {"same amino acid"})]
    pm5 = [
        item
        for item in selected
        if _field(item, "residue_relationship") == "same_residue_different_missense"
        or _has_any(item, {"same residue", "different missense"})
    ]
    return [
        _summary(
            "PS1",
            "same_amino_acid",
            ps1,
            "Previously reported same-amino-acid variants may support PS1 review.",
            "supporting" if ps1 else "none",
            "Does the paper support the same amino acid change in the same disease context?",
        ),
        _summary(
            "PM5",
            "same_residue",
            pm5,
            "Previously reported same-residue missense variants may support PM5 review.",
            "supporting" if pm5 else "none",
            "Is this a different missense change at the same residue with matching disease context?",
        ),
    ]


def _pm1(records: list[LiteratureRecord]) -> CriterionSummary:
    selected = _records_for(records, {"hotspot", "critical domain", "functional domain", "pm1"})
    return _summary(
        "PM1",
        "hotspot_or_domain",
        selected,
        "Hotspot or critical-domain literature may support PM1 review.",
        "supporting" if selected else "none",
        "Is the region a disease-relevant hotspot or critical functional domain without benign variation?",
    )


def _pvs1(records: list[LiteratureRecord]) -> CriterionSummary:
    selected = _records_for(records, {"loss of function mechanism", "nmd", "nonsense mediated decay", "haploinsufficiency", "pvs1"})
    summary = _summary(
        "PVS1",
        "lof_nmd_mechanism",
        selected,
        "LoF, NMD, or disease-mechanism literature may support PVS1 mechanism review.",
        "none",
        "Does literature support LoF as the disease mechanism, and are exon/NMD caveats resolved?",
    )
    if selected:
        summary.limitations.append(
            "PVS1 literature summary is mechanism support only and does not run or override PVS1 scoring."
        )
    return summary


def _summary(
    criterion: str,
    domain: str,
    records: list[LiteratureRecord],
    text: str,
    strength: str,
    question: str,
) -> CriterionSummary:
    blocking = [flag for record in records for flag in _blocking_flags(record)]
    review = [flag for record in records for flag in _review_flags(record)]
    limitations = []
    if any(record.abstract and not record.full_text_excerpt for record in records):
        limitations.append("At least one record is abstract-only; full-text details require review.")
    if any(record.source.lower().startswith(("codex", "life science")) for record in records):
        limitations.append(
            "Codex/Life Science Research extracted claims are caller-supplied records and require manual review."
        )
    return CriterionSummary(
        criterion=criterion,
        evidence_domain=domain,
        summary=text if records else f"No {criterion} literature support found in supplied/offline records.",
        supporting_records=[record.record_id for record in records],
        extracted_claims=[claim for record in records for claim in record.extracted_claims],
        suggested_code=criterion if records and not blocking else None,
        suggested_strength=strength if records and not blocking else "none",
        confidence=_confidence(records),
        requires_manual_review=True,
        review_questions=[question],
        blocking_flags=blocking,
        review_flags=review,
        limitations=limitations,
    )


def _records_for(records: list[LiteratureRecord], keywords: set[str]) -> list[LiteratureRecord]:
    return [record for record in records if _has_any(record, keywords) or keywords.intersection(set(record.evidence_domains))]


def _has_any(record: LiteratureRecord, keywords: set[str]) -> bool:
    haystack = " ".join(
        str(item or "")
        for item in [
            record.study_type,
            record.title,
            record.abstract,
            record.full_text_excerpt,
            *record.evidence_domains,
            *record.extracted_claims,
        ]
    ).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _field(record: LiteratureRecord, key: str) -> str:
    return str(record.raw_record.get(key) or "").strip().lower()


def _truthy(record: LiteratureRecord, key: str) -> bool:
    value = record.raw_record.get(key)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "yes", "confirmed", "1"}


def _blocking_flags(record: LiteratureRecord) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if record.variant_match_level not in {None, "exact", "same_variant", "not_provided"}:
        flags.append(
            {
                "code": "LITERATURE_VARIANT_MISMATCH",
                "message": "Literature record does not exactly match the queried variant.",
                "severity": "warning",
                "blocking": True,
                "record_id": record.record_id,
            }
        )
    if record.disease_match_level not in {None, "exact", "same_disease", "not_provided"}:
        flags.append(
            {
                "code": "LITERATURE_DISEASE_MISMATCH",
                "message": "Literature record disease does not match the queried disease context.",
                "severity": "warning",
                "blocking": True,
                "record_id": record.record_id,
            }
        )
    return flags


def _review_flags(record: LiteratureRecord) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    confidence = _record_confidence(record)
    if confidence < 0.7:
        flags.append(
            {
                "code": "LITERATURE_LOW_EXTRACTION_CONFIDENCE",
                "message": "Literature extraction confidence is below the review threshold.",
                "severity": "warning",
                "blocking": True,
                "record_id": record.record_id,
            }
        )
    if record.abstract and not record.full_text_excerpt:
        flags.append(
            {
                "code": "LITERATURE_ABSTRACT_ONLY",
                "message": "Only abstract-level text was available for this literature record.",
                "severity": "info",
                "blocking": False,
                "record_id": record.record_id,
            }
        )
    return flags


def _confidence(records: list[LiteratureRecord]) -> float:
    if not records:
        return 0.3
    return min(_record_confidence(record) for record in records)


def _record_confidence(record: LiteratureRecord) -> float:
    value = record.raw_record.get("confidence", record.raw_record.get("extraction_confidence", 0.55))
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.55
