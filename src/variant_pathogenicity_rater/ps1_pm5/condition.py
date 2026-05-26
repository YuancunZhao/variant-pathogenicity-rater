from __future__ import annotations

import re

from variant_pathogenicity_rater.ps1_pm5.schema import ConditionMatch
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext


def evaluate_condition_match(
    context: GeneDiseaseContext,
    record: ClinVarRecord,
) -> ConditionMatch:
    query = _clean_condition(context.disease_name)
    conditions = [condition for condition in [record.condition, *record.conditions] if condition]
    if not query or query == "not provided":
        return ConditionMatch(
            query_condition=context.disease_name,
            comparator_conditions=conditions,
            match_type="missing",
            blocking=True,
            limitations=["Disease context is missing; PS1/PM5 cannot be applied."],
        )
    if not conditions:
        return ConditionMatch(
            query_condition=context.disease_name,
            comparator_conditions=[],
            match_type="missing",
            blocking=True,
            limitations=["ClinVar comparator condition is missing."],
        )

    query_terms = _terms(query)
    for condition in conditions:
        normalized = _clean_condition(condition)
        if normalized == query:
            return ConditionMatch(
                query_condition=context.disease_name,
                comparator_conditions=conditions,
                matched=True,
                match_type="exact",
                blocking=False,
                matched_terms=[query],
            )
        overlap = sorted(query_terms.intersection(_terms(normalized)))
        if overlap:
            return ConditionMatch(
                query_condition=context.disease_name,
                comparator_conditions=conditions,
                matched=True,
                match_type="normalized_overlap",
                blocking=False,
                matched_terms=overlap,
            )

    return ConditionMatch(
        query_condition=context.disease_name,
        comparator_conditions=conditions,
        match_type="mismatch",
        blocking=True,
        unmatched_terms=sorted(query_terms),
        limitations=["ClinVar comparator condition does not match the disease context."],
    )


def _clean_condition(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _terms(value: str) -> set[str]:
    stop = {
        "and",
        "or",
        "the",
        "not",
        "provided",
        "specified",
        "disease",
        "syndrome",
        "cancer",
        "disorder",
    }
    return {term for term in value.split() if len(term) >= 4 and term not in stop}
