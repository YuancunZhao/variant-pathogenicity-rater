from __future__ import annotations

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.schemas import (
    EvidenceCode,
    EvidenceDirection,
    EvidenceItem,
    EvidenceSource,
    EvidenceStrength,
    GeneDiseaseContext,
    Variant,
)


def _variant() -> Variant:
    return Variant(
        variant_id="GRCh38-1-100-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=100,
        ref="A",
        alt="G",
        gene_symbol="GENE1",
    )


def _context() -> GeneDiseaseContext:
    return GeneDiseaseContext(
        gene_symbol="GENE1",
        disease_name="Example disease",
        inheritance_mode="autosomal dominant",
        disease_prevalence=0.0001,
    )


def _item(
    code: EvidenceCode,
    strength: EvidenceStrength,
    direction: EvidenceDirection,
    suffix: str | None = None,
) -> EvidenceItem:
    evidence_id = f"ev-{code.value.lower()}-{suffix or strength.value}"
    return EvidenceItem(
        evidence_id=evidence_id,
        code=code,
        strength=strength,
        direction=direction,
        reason=f"{code.value} test evidence.",
        source=EvidenceSource(name="unit-test"),
        confidence=0.9,
        requires_review=True,
        triggered_by=["unit_test"],
    )


def test_pathogenic_combination_with_very_strong_and_strong() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.PVS1, EvidenceStrength.VERY_STRONG, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.PS3, EvidenceStrength.STRONG, EvidenceDirection.PATHOGENIC),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "pathogenic"
    assert result.applied_combination_rule == "pathogenic: 1 very_strong + >=1 strong"
    assert result.human_review_required is True


def test_likely_pathogenic_combination_with_three_moderate_items() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.PM1, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.PM5, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "likely_pathogenic"
    assert result.applied_combination_rule == "likely_pathogenic: >=3 moderate"


def test_benign_combination_with_ba1_stand_alone() -> None:
    result = classify_acmg(
        [_item(EvidenceCode.BA1, EvidenceStrength.STAND_ALONE, EvidenceDirection.BENIGN)],
        _variant(),
        _context(),
    )

    assert result.final_classification == "benign"
    assert result.applied_combination_rule == "benign: BA1 stand_alone"


def test_likely_benign_combination_with_two_supporting_items() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.BP4, EvidenceStrength.SUPPORTING, EvidenceDirection.BENIGN),
            _item(EvidenceCode.BP7, EvidenceStrength.SUPPORTING, EvidenceDirection.BENIGN),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "likely_benign"
    assert result.applied_combination_rule == "likely_benign: >=2 supporting"


def test_default_vus_when_evidence_is_insufficient() -> None:
    result = classify_acmg(
        [_item(EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC)],
        _variant(),
        _context(),
    )

    assert result.final_classification == "vus"
    assert result.applied_combination_rule == "default_vus"


def test_conflicting_pathogenic_and_benign_thresholds_default_to_vus() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.PVS1, EvidenceStrength.VERY_STRONG, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.PS3, EvidenceStrength.STRONG, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.BA1, EvidenceStrength.STAND_ALONE, EvidenceDirection.BENIGN),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "vus"
    assert result.applied_combination_rule == "conflicting_classification_thresholds"
    assert result.conflicting_evidence
    assert "CONFLICTING_PATHOGENIC_AND_BENIGN_EVIDENCE" in {
        flag.code for flag in result.review_flags
    }


def test_duplicate_code_is_collapsed_to_one_count() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC, "a"),
            _item(EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC, "b"),
            _item(EvidenceCode.PM3, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "vus"
    assert any("Duplicate PM2 pathogenic evidence was collapsed" in item for item in result.limitations)


def test_strength_modification_is_preserved_and_reported() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.PVS1, EvidenceStrength.STRONG, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.PM2, EvidenceStrength.MODERATE, EvidenceDirection.PATHOGENIC),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "likely_pathogenic"
    assert result.applied_combination_rule == "likely_pathogenic: 1 strong + 1-2 moderate"
    assert any("PVS1 applied at strong strength" in item for item in result.limitations)


def test_pp3_is_capped_at_supporting_and_cannot_overweight_classification() -> None:
    result = classify_acmg(
        [
            _item(EvidenceCode.PP3, EvidenceStrength.STRONG, EvidenceDirection.PATHOGENIC),
            _item(EvidenceCode.BA1, EvidenceStrength.STAND_ALONE, EvidenceDirection.BENIGN),
        ],
        _variant(),
        _context(),
    )

    assert result.final_classification == "vus"
    assert result.applied_combination_rule == "opposing_evidence_vus_review"
    assert result.conflicting_evidence
    assert any("PP3 was capped at supporting strength" in item for item in result.limitations)
    assert "OPPOSING_PATHOGENIC_AND_BENIGN_EVIDENCE" in {flag.code for flag in result.review_flags}
