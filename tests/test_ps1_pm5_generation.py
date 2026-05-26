from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from variant_pathogenicity_rater.acmg.combiner import classify_acmg
from variant_pathogenicity_rater.pipeline.batch import rate_variant_batch
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant
from variant_pathogenicity_rater.pipeline.real_world import run_annotation_batch_workflow
from variant_pathogenicity_rater.ps1_pm5 import generate_ps1_pm5_evidence
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord, EvidenceSource
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Transcript, Variant

ROOT = Path(__file__).resolve().parents[1]
MCP_SERVER = ROOT / "mcp-server"
if str(MCP_SERVER) not in sys.path:
    sys.path.insert(0, str(MCP_SERVER))


def _variant(
    *,
    hgvs_c: str = "NM_000001.1:c.76A>G",
    hgvs_p: str | None = "NP_000001.1:p.Lys26Arg",
) -> Variant:
    return Variant(
        variant_id="GRCh38-1-123-A-G",
        genome_build="GRCh38",
        variant_type="snv",
        chrom="1",
        pos=123,
        ref="A",
        alt="G",
        gene_symbol="GENE1",
        transcript=Transcript(
            accession="NM_000001",
            version="1",
            gene_symbol="GENE1",
            hgvs_c=hgvs_c,
            hgvs_p=hgvs_p,
        ),
        hgvs_c=hgvs_c,
        hgvs_p=hgvs_p,
    )


def _context(disease: str = "Example disease") -> GeneDiseaseContext:
    return GeneDiseaseContext(gene="GENE1", disease=disease)


def _clinvar(
    *,
    hgvs_c: str = "NM_000001.1:c.77A>G",
    hgvs_p: str | None = "NP_000001.1:p.Lys26Arg",
    significance: str = "Pathogenic",
    review_status: str = "reviewed by expert panel",
    condition: str = "Example disease",
    conflict: bool = False,
    germline_or_somatic: str = "germline",
    variation_id: str = "cv-1",
) -> ClinVarRecord:
    return ClinVarRecord(
        source=EvidenceSource(name="ClinVar", version="test", database_id=variation_id),
        variation_id=variation_id,
        gene_symbol="GENE1",
        transcript="NM_000001.1",
        hgvs_c=hgvs_c,
        hgvs_p=hgvs_p,
        protein_change=hgvs_p,
        chromosome="1",
        position=124,
        ref="A",
        alt="G",
        genome_build="GRCh38",
        clinical_significance=significance,
        review_status=review_status,
        review_stars=3 if "expert panel" in review_status else 1,
        submitter_count=3 if "single submitter" not in review_status else 1,
        condition=condition,
        conditions=[condition],
        conflicting_interpretations=conflict,
        conflict_status="conflicting interpretations" if conflict else None,
        germline_or_somatic=germline_or_somatic,
    )


def test_ps1_applied_safe_case() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[_clinvar()],
    )

    assert decisions[0].applied is True
    assert len(items) == 1
    assert items[0].code == "PS1"
    assert items[0].strength == "strong"
    assert items[0].requires_review is True
    assert items[0].supporting_data["not_pp5"] is True


def test_ps1_candidate_due_to_clinvar_conflict() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[_clinvar(conflict=True)],
    )

    assert decisions[0].applied is False
    assert decisions[0].clinvar_comparison.has_conflict is True
    assert len(items) == 1
    assert items[0].candidate_only is True
    assert items[0].strength == "none"


def test_ps1_blocked_by_condition_mismatch() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context("Example disease"),
        clinvar_records=[_clinvar(condition="Unrelated disorder")],
    )

    assert decisions[0].applied is False
    assert decisions[0].condition_match.blocking is True
    assert items == []


def test_pm5_applied_safe_case() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[
            _clinvar(
                hgvs_c="NM_000001.1:c.76A>C",
                hgvs_p="NP_000001.1:p.Lys26Asn",
                variation_id="cv-pm5",
            )
        ],
    )

    assert decisions[0].applied is True
    assert items[0].code == "PM5"
    assert items[0].strength == "moderate"


def test_pm5_candidate_due_to_low_quality_clinvar() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[
            _clinvar(
                hgvs_c="NM_000001.1:c.76A>C",
                hgvs_p="NP_000001.1:p.Lys26Asn",
                review_status="criteria provided, single submitter",
            )
        ],
    )

    assert decisions[0].applied is False
    assert decisions[0].candidate_only is True
    assert items[0].code == "PM5"
    assert items[0].strength == "none"


def test_pm5_blocked_by_same_amino_acid_not_different_missense() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[_clinvar(hgvs_c="NM_000001.1:c.76A>G")],
    )

    assert decisions[0].recommended_code is None
    assert decisions[0].applied is False
    assert "same nucleotide/genomic variant" in "; ".join(decisions[0].blocking_reasons)
    assert items == []


def test_same_exact_variant_with_unparseable_protein_does_not_trigger_ps1() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(
            hgvs_c="NM_000001.1:c.76_77del",
            hgvs_p="NP_000001.1:p.Lys26ArgfsTer3",
        ),
        context=_context(),
        clinvar_records=[
            _clinvar(
                hgvs_c="NM_000001.1:c.76_77del",
                hgvs_p="NP_000001.1:p.Lys26ArgfsTer3",
            )
        ],
    )

    assert decisions[0].recommended_code is None
    assert decisions[0].applied is False
    assert decisions[0].generation.status == "blocked"
    assert "same nucleotide/genomic variant" in "; ".join(decisions[0].blocking_reasons)
    assert items == []


def test_no_hgvs_p_is_candidate_only() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(hgvs_p=None),
        context=_context(),
        clinvar_records=[_clinvar()],
    )

    assert decisions[0].applied is False
    assert decisions[0].candidate_only is True
    assert items[0].candidate_only is True
    assert items[0].strength == "none"


def test_candidate_evidence_does_not_alter_classification() -> None:
    items, _decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[
            _clinvar(
                hgvs_c="NM_000001.1:c.76A>C",
                hgvs_p="NP_000001.1:p.Lys26Asn",
                review_status="criteria provided, single submitter",
            )
        ],
    )

    result = classify_acmg(items, _variant(), _context(), [])
    assert result.applied_combination_rule == "default_vus"


def test_applied_evidence_only_affects_classification_through_combiner() -> None:
    items, _decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[_clinvar()],
    )

    result = classify_acmg(items, _variant(), _context(), [])
    assert result.applied_combination_rule == "default_vus"
    assert result.pathogenic_evidence_summary[0].startswith("PS1 strong:")


def test_pipeline_and_report_preserve_ps1_pm5_boundaries() -> None:
    result = rate_variant(
        {
            "gene": "GENE1",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "hgvs_p": "NP_000001.1:p.Lys26Arg",
            "chromosome": "1",
            "position": 123,
            "ref": "A",
            "alt": "G",
            "disease": "Example disease",
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_literature": False,
                "clinvar_records": [
                    {
                        "variation_id": "cv-ps1",
                        "gene": "GENE1",
                        "transcript": "NM_000001.1",
                        "hgvs_c": "NM_000001.1:c.77A>G",
                        "hgvs_p": "NP_000001.1:p.Lys26Arg",
                        "clinical_significance": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "conditions": ["Example disease"],
                        "submitter_count": 3,
                        "conflicting_interpretations": False,
                        "germline_or_somatic": "germline",
                    }
                ],
            },
        }
    )

    assert result["step_results"]["evaluate_ps1_pm5_evidence"]["decisions"][0]["applied"] is True
    assert [item["code"] for item in result["applied_evidence"]] == ["PS1"]
    assert "not PP5" in result["report_text"]


def test_pipeline_candidate_ps1_pm5_remains_excluded() -> None:
    result = rate_variant(
        {
            "gene": "GENE1",
            "transcript": "NM_000001.1",
            "hgvs_c": "NM_000001.1:c.76A>G",
            "hgvs_p": "NP_000001.1:p.Lys26Arg",
            "chromosome": "1",
            "position": 123,
            "ref": "A",
            "alt": "G",
            "disease": "Example disease",
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_literature": False,
                "clinvar_records": [
                    {
                        "variation_id": "cv-pm5-low",
                        "gene": "GENE1",
                        "transcript": "NM_000001.1",
                        "hgvs_c": "NM_000001.1:c.76A>C",
                        "hgvs_p": "NP_000001.1:p.Lys26Asn",
                        "clinical_significance": "Pathogenic",
                        "review_status": "criteria provided, single submitter",
                        "conditions": ["Example disease"],
                        "submitter_count": 1,
                        "conflicting_interpretations": False,
                        "germline_or_somatic": "germline",
                    }
                ],
            },
        }
    )

    assert result["applied_evidence"] == []
    assert any(item["code"] == "PM5" for item in result["review_note_evidence"])
    assert result["classification_result"]["applied_combination_rule"] == "default_vus"


def test_transcript_mismatch_blocks_applied_evidence() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[
            _clinvar(
                hgvs_p="NP_999999.1:p.Lys26Arg",
                variation_id="cv-transcript-mismatch",
            )
        ],
    )

    assert decisions[0].applied is False
    assert decisions[0].amino_acid_match.transcript_or_protein_match is False
    assert all(item.applied is False for item in items)


def test_somatic_only_clinvar_record_blocks_applied_evidence() -> None:
    items, decisions = generate_ps1_pm5_evidence(
        variant=_variant(),
        context=_context(),
        clinvar_records=[_clinvar(germline_or_somatic="somatic")],
    )

    assert decisions[0].applied is False
    assert decisions[0].clinvar_comparison.is_germline_applicable is False
    assert all(item.applied is False for item in items)


def test_batch_preserves_ps1_pm5_applied_and_review_note_separation() -> None:
    result = rate_variant_batch(
        {
            "records": [
                {
                    "gene": "GENE1",
                    "transcript": "NM_000001.1",
                    "hgvs_c": "NM_000001.1:c.76A>G",
                    "hgvs_p": "NP_000001.1:p.Lys26Arg",
                    "chromosome": "1",
                    "position": 123,
                    "ref": "A",
                    "alt": "G",
                    "disease": "Example disease",
                }
            ],
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_literature": False,
                "clinvar_records": [
                    {
                        "variation_id": "cv-batch-ps1",
                        "gene": "GENE1",
                        "transcript": "NM_000001.1",
                        "hgvs_c": "NM_000001.1:c.77A>G",
                        "hgvs_p": "NP_000001.1:p.Lys26Arg",
                        "clinical_significance": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "conditions": ["Example disease"],
                        "submitter_count": 3,
                        "conflicting_interpretations": False,
                        "germline_or_somatic": "germline",
                    }
                ],
            },
        }
    )

    record = result["results"][0]
    assert [item["code"] for item in record["applied_evidence"]] == ["PS1"]
    assert any(item["code"] == "PP5" for item in record["review_note_evidence"])


def test_annotated_batch_preserves_ps1_pm5_applied_evidence() -> None:
    result = run_annotation_batch_workflow(
        {
            "annotation_format": "generic",
            "records": [
                {
                    "gene": "GENE1",
                    "transcript": "NM_000001.1",
                    "hgvs_c": "NM_000001.1:c.76A>G",
                    "hgvs_p": "NP_000001.1:p.Lys26Arg",
                    "chrom": "1",
                    "pos": 123,
                    "ref": "A",
                    "alt": "G",
                }
            ],
            "gene_disease_context": {"gene": "GENE1", "disease": "Example disease"},
            "options": {
                "include_population": False,
                "include_computational": False,
                "include_literature": False,
                "clinvar_records": [
                    {
                        "variation_id": "cv-annotated-ps1",
                        "gene": "GENE1",
                        "transcript": "NM_000001.1",
                        "hgvs_c": "NM_000001.1:c.77A>G",
                        "hgvs_p": "NP_000001.1:p.Lys26Arg",
                        "clinical_significance": "Pathogenic",
                        "review_status": "reviewed by expert panel",
                        "conditions": ["Example disease"],
                        "submitter_count": 3,
                        "conflicting_interpretations": False,
                        "germline_or_somatic": "germline",
                    }
                ],
            },
        }
    )

    record = result["results"][0]
    assert [item["code"] for item in record["applied_evidence"]] == ["PS1"]


def test_mcp_rate_variant_returns_ps1_pm5_step_results() -> None:
    from tools.rate_variant import rate_variant as mcp_rate_variant

    result = asyncio.run(
        mcp_rate_variant(
            {
                "gene": "GENE1",
                "transcript": "NM_000001.1",
                "hgvs_c": "NM_000001.1:c.76A>G",
                "hgvs_p": "NP_000001.1:p.Lys26Arg",
                "chromosome": "1",
                "position": 123,
                "ref": "A",
                "alt": "G",
                "disease": "Example disease",
                "options": {
                    "include_population": False,
                    "include_computational": False,
                    "include_literature": False,
                    "clinvar_records": [
                        {
                            "variation_id": "cv-mcp-ps1",
                            "gene": "GENE1",
                            "transcript": "NM_000001.1",
                            "hgvs_c": "NM_000001.1:c.77A>G",
                            "hgvs_p": "NP_000001.1:p.Lys26Arg",
                            "clinical_significance": "Pathogenic",
                            "review_status": "reviewed by expert panel",
                            "conditions": ["Example disease"],
                            "submitter_count": 3,
                            "conflicting_interpretations": False,
                            "germline_or_somatic": "germline",
                        }
                    ],
                },
            }
        )
    )

    assert result["step_results"]["evaluate_ps1_pm5_evidence"]["decisions"][0]["applied"] is True
    assert [item["code"] for item in result["applied_evidence"]] == ["PS1"]
