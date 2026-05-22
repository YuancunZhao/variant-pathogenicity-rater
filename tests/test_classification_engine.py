from __future__ import annotations

import pytest

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.schemas import (
    ACMGClassification,
    EvidenceCode,
    EvidenceDirection,
    EvidenceItem,
    EvidenceStrength,
    GeneDiseaseContext,
    Variant,
)


def test_pathogenic_combination_from_pvs1_and_pm2(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    result = classify_acmg(
        [
            evidence_factory(EvidenceCode.PVS1, EvidenceStrength.VERY_STRONG, EvidenceDirection.PATHOGENIC),
            evidence_factory(EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
        ],
        snv_variant,
        lof_context,
    )

    assert result.final_classification == ACMGClassification.LIKELY_PATHOGENIC
    assert result.applied_combination_rule == "likely_pathogenic: 1 very_strong + 1 moderate"
    assert result.human_review_required is True


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        (
            [
                (EvidenceCode.PVS1, EvidenceStrength.VERY_STRONG, EvidenceDirection.PATHOGENIC),
                (EvidenceCode.PS3, EvidenceStrength.STRONG, EvidenceDirection.PATHOGENIC),
            ],
            ACMGClassification.PATHOGENIC,
        ),
        (
            [
                (EvidenceCode.PM1, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
                (EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
                (EvidenceCode.PM3, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
            ],
            ACMGClassification.LIKELY_PATHOGENIC,
        ),
        (
            [(EvidenceCode.BA1, EvidenceStrength.STAND_ALONE, EvidenceDirection.BENIGN)],
            ACMGClassification.BENIGN,
        ),
        (
            [
                (EvidenceCode.BS1, EvidenceStrength.STRONG, EvidenceDirection.BENIGN),
                (EvidenceCode.BP4, EvidenceStrength.SUPPORTING, EvidenceDirection.BENIGN),
            ],
            ACMGClassification.LIKELY_BENIGN,
        ),
        (
            [(EvidenceCode.PP3, EvidenceStrength.SUPPORTING, EvidenceDirection.PATHOGENIC)],
            ACMGClassification.UNCERTAIN_SIGNIFICANCE,
        ),
    ],
)
def test_final_classification_combinations(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
    items,
    expected: ACMGClassification,
) -> None:
    evidence_items = [evidence_factory(code, strength, direction) for code, strength, direction in items]

    result = classify_acmg(evidence_items, snv_variant, lof_context)

    assert result.final_classification == expected
    assert result.human_review_required is True


def test_conflicting_evidence_defaults_to_vus_with_review_flag(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    result = classify_acmg(
        [
            evidence_factory(EvidenceCode.PVS1, EvidenceStrength.VERY_STRONG, EvidenceDirection.PATHOGENIC),
            evidence_factory(EvidenceCode.PS3, EvidenceStrength.STRONG, EvidenceDirection.PATHOGENIC),
            evidence_factory(EvidenceCode.BA1, EvidenceStrength.STAND_ALONE, EvidenceDirection.BENIGN),
        ],
        snv_variant,
        lof_context,
    )

    assert result.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert result.applied_combination_rule == "conflicting_classification_thresholds"
    assert result.conflicting_evidence
    assert "CONFLICTING_PATHOGENIC_AND_BENIGN_EVIDENCE" in {flag.code for flag in result.review_flags}


def test_candidate_and_conflicting_evidence_are_not_counted(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    candidate = evidence_factory(
        EvidenceCode.PP5,
        EvidenceStrength.NONE,
        EvidenceDirection.PATHOGENIC,
        source_name="ClinVar",
    )
    conflicting = evidence_factory(
        EvidenceCode.PP5,
        EvidenceStrength.NONE,
        EvidenceDirection.CONFLICTING,
        source_name="ClinVar",
        evidence_id="ev-clinvar-conflict",
    )

    result = classify_acmg([candidate, conflicting], snv_variant, lof_context)

    assert result.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert any("was not counted" in limitation for limitation in result.limitations)


def test_candidate_evidence_does_not_participate_in_classification(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    candidate = evidence_factory(
        EvidenceCode.PVS1,
        EvidenceStrength.VERY_STRONG,
        EvidenceDirection.PATHOGENIC,
    )
    candidate.supporting_data["candidate_only"] = True
    applied = evidence_factory(
        EvidenceCode.PM2,
        EvidenceStrength.SUPPORTING,
        EvidenceDirection.PATHOGENIC,
        evidence_id="ev-pm2-supporting",
    )

    result = classify_acmg([candidate, applied], snv_variant, lof_context)

    assert result.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert any("candidate-only" in limitation for limitation in result.limitations)


def test_strength_none_does_not_participate_in_classification(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    none_strength = evidence_factory(
        EvidenceCode.PVS1,
        EvidenceStrength.NONE,
        EvidenceDirection.PATHOGENIC,
    )
    supporting = [
        evidence_factory(
            EvidenceCode.PP1,
            EvidenceStrength.SUPPORTING,
            EvidenceDirection.PATHOGENIC,
            evidence_id=f"ev-pp1-{idx}",
        )
        for idx in range(4)
    ]

    result = classify_acmg([none_strength, *supporting], snv_variant, lof_context)

    assert result.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert any("strength is none" in limitation for limitation in result.limitations)


def test_opposing_pathogenic_and_benign_evidence_defaults_to_vus_review(
    snv_variant: Variant,
    lof_context: GeneDiseaseContext,
    evidence_factory,
) -> None:
    result = classify_acmg(
        [
            evidence_factory(EvidenceCode.PVS1, EvidenceStrength.VERY_STRONG, EvidenceDirection.PATHOGENIC),
            evidence_factory(EvidenceCode.BS1, EvidenceStrength.STRONG, EvidenceDirection.BENIGN),
        ],
        snv_variant,
        lof_context,
    )

    assert result.final_classification == ACMGClassification.UNCERTAIN_SIGNIFICANCE
    assert result.applied_combination_rule == "opposing_evidence_vus_review"
    assert result.conflicting_evidence
    assert "OPPOSING_PATHOGENIC_AND_BENIGN_EVIDENCE" in {flag.code for flag in result.review_flags}
