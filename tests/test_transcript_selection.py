from __future__ import annotations

from variant_pathogenicity_rater.annotation import GenericTableAdapter, select_transcript
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


def _annotations(text: str):
    return GenericTableAdapter(source_version="selection-test").parse_text(text).annotations


def test_user_transcript_matched_is_preserved() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NM_000001.1,missense_variant,false,false,protein_coding
GENE1,NM_000002.1,stop_gained,true,true,protein_coding
"""
        ),
        user_transcript="NM_000001.1",
    )

    assert selection.selected_transcript == "NM_000001.1"
    assert selection.user_transcript_provided is True
    assert selection.user_transcript_matched is True
    assert "ACMG evidence" in selection.limitations[0]


def test_user_transcript_mismatch_does_not_substitute() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NM_000001.1,missense_variant,true,true,protein_coding
"""
        ),
        user_transcript="NM_999999.1",
    )

    assert selection.selected_transcript is None
    assert selection.user_transcript_matched is False
    assert [flag.code for flag in selection.review_flags] == ["USER_TRANSCRIPT_MISMATCH"]


def test_mane_select_is_preferred() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NM_000001.1,missense_variant,false,true,protein_coding
GENE1,NM_000002.1,missense_variant,true,false,protein_coding
"""
        )
    )

    assert selection.selected_transcript == "NM_000002.1"
    assert selection.mane_select_available is True


def test_canonical_fallback() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NM_000001.1,missense_variant,false,false,protein_coding
GENE1,NM_000002.1,missense_variant,false,true,protein_coding
"""
        )
    )

    assert selection.selected_transcript == "NM_000002.1"
    assert "Canonical transcript" in selection.selection_reason


def test_protein_coding_preference() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NR_000001.1,intron_variant,false,false,lncRNA
GENE1,NM_000002.1,missense_variant,false,false,protein_coding
"""
        )
    )

    assert selection.selected_transcript == "NM_000002.1"
    assert "Protein-coding" in selection.selection_reason


def test_multiple_equal_candidates_requires_review() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NM_000001.1,missense_variant,true,false,protein_coding
GENE1,NM_000002.1,missense_variant,true,false,protein_coding
"""
        )
    )

    codes = {flag.code for flag in selection.review_flags}
    assert "TRANSCRIPT_SELECTION_AMBIGUITY" in codes
    assert "MULTIPLE_MANE_SELECT_CONFLICT" in codes


def test_severe_consequence_tiebreaker_requires_review() -> None:
    selection = select_transcript(
        _annotations(
            """gene,transcript,consequence_terms,mane_select,canonical,transcript_biotype
GENE1,NM_000001.1,missense_variant,false,false,protein_coding
GENE1,NM_000002.1,stop_gained,false,false,protein_coding
"""
        )
    )

    codes = {flag.code for flag in selection.review_flags}
    assert selection.selected_transcript == "NM_000002.1"
    assert "SEVERE_CONSEQUENCE_TIEBREAKER_USED" in codes
    assert "TRANSCRIPT_SELECTION_AMBIGUITY" in codes


def test_no_annotation_records_limitation() -> None:
    selection = select_transcript([])

    assert selection.selected_transcript is None
    assert selection.selection_confidence == 0.0
    assert any("No annotation records" in limitation for limitation in selection.limitations)


def test_selection_does_not_change_classification_or_evidence() -> None:
    payload = {
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "NM_007294.4:c.68_69delAG",
        "hgvs_p": "NP_009225.1:p.Glu23ValfsTer17",
        "chromosome": "17",
        "position": 43092919,
        "ref": "AG",
        "alt": "A",
        "disease": "Hereditary breast and ovarian cancer",
        "inheritance": "autosomal dominant",
        "phenotype": ["HP:0003002"],
        "options": {
            "include_transcript_selection": True,
            "annotation_records": [
                {
                    "gene": "BRCA1",
                    "transcript": "NM_007294.4",
                    "consequence_terms": "frameshift_variant",
                    "mane_select": "true",
                    "canonical": "true",
                    "transcript_biotype": "protein_coding",
                }
            ],
        },
    }
    without_selection = dict(payload)
    without_selection["options"] = {}

    base = rate_variant(without_selection)
    selected = rate_variant(payload)

    assert selected["transcript_selection"]["selected_transcript"] == "NM_007294.4"
    assert selected["final_classification"] == base["final_classification"]
    assert [item["evidence_id"] for item in selected["evidence_items"]] == [
        item["evidence_id"] for item in base["evidence_items"]
    ]
    assert "Transcript Selection" in selected["report_text"]
