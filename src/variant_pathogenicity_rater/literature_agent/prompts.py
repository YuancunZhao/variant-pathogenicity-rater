from __future__ import annotations


SYSTEM_BOUNDARY = (
    "Extract candidate ACMG literature evidence only. Never apply evidence, never run the "
    "classification combiner, and always require manual review."
)


REVIEW_OUTPUT_FIELDS = [
    "candidate_code",
    "suggested_strength",
    "evidence_type",
    "variant_match_level",
    "disease_match_level",
    "phenotype_match_level",
    "extracted_claims",
    "citation",
    "confidence",
    "requires_manual_review",
    "reason_not_applied",
    "limitations",
]
