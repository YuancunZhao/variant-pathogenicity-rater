from __future__ import annotations

from variant_pathogenicity_rater.natural_language_input import (
    parse_variant_text,
    rate_variant_from_text,
)
from variant_pathogenicity_rater.pipeline.rate_variant import rate_variant


OFFLINE_OPTIONS = {
    "include_population": False,
    "include_computational": False,
    "include_clinvar": False,
    "include_literature": False,
}


def _mock_ai_context(_text: str, _parsed: dict) -> dict:
    return {
        "disease_candidates": [
            {
                "disease_name": "Noonan syndrome",
                "normalized_disease_name": "Noonan syndrome",
                "disease_id": "MONDO:0018997",
                "inheritance": "autosomal_dominant",
                "confidence": 0.82,
                "evidence_text_span": "Noonan-like syndrome with short stature",
                "language": "en",
                "hpo_terms": [
                    {
                        "label": "Short stature",
                        "hpo_id": "HP:0004322",
                        "confidence": 0.76,
                        "evidence_text_span": "short stature",
                        "language": "en",
                    }
                ],
            }
        ],
        "hpo_terms": [
            {
                "label": "Short stature",
                "hpo_id": "HP:0004322",
                "confidence": 0.76,
                "evidence_text_span": "short stature",
                "language": "en",
            }
        ],
        "inheritance": "autosomal_dominant",
        "confidence": 0.82,
        "language": "en",
    }


def test_parse_english_hgvs_text_extracts_structured_fields() -> None:
    result = parse_variant_text("BRCA1 NM_007294.4:c.68_69delAG, HBOC, AD")

    assert result["status"] == "parsed"
    assert result["parsed_input"]["gene"] == "BRCA1"
    assert result["parsed_input"]["transcript"] == "NM_007294.4"
    assert result["parsed_input"]["hgvs_c"] == "NM_007294.4:c.68_69delAG"
    assert result["parsed_input"]["disease"] == "Hereditary breast and ovarian cancer syndrome"
    assert result["parsed_input"]["inheritance"] == "autosomal_dominant"
    assert "Genomic coordinate missing; PM2/population/PVS1 may be limited." in result[
        "normalization_warnings"
    ]


def test_parse_chinese_text_keeps_short_alias_candidate_only() -> None:
    result = parse_variant_text(
        "评估 BRCA1 185delAG，遗传性乳腺卵巢癌综合征，常染色体显性遗传"
    )

    assert result["status"] == "error"
    assert result["parsed_input"]["gene"] == "BRCA1"
    assert result["parsed_input"]["disease"] == "hereditary breast and ovarian cancer"
    assert result["parsed_input"]["inheritance"] == "autosomal_dominant"
    assert "hgvs_c" not in result["parsed_input"]
    assert result["alias_candidates"] == [
        {
            "alias": "185delAG",
            "type": "short_variant_name",
            "normalized": False,
            "reason": (
                "Short variant aliases are not silently normalized without an explicit "
                "dictionary match."
            ),
        }
    ]


def test_parse_transcript_hgvs_c_and_hgvs_p() -> None:
    result = parse_variant_text(
        "CFTR NM_000492.4:c.1521_1523delCTT p.Phe508del, cystic fibrosis, AR"
    )

    assert result["status"] == "parsed"
    assert result["parsed_input"]["gene"] == "CFTR"
    assert result["parsed_input"]["transcript"] == "NM_000492.4"
    assert result["parsed_input"]["hgvs_c"] == "NM_000492.4:c.1521_1523delCTT"
    assert result["parsed_input"]["hgvs_p"] == "p.Phe508del"
    assert result["parsed_input"]["disease"] == "cystic fibrosis"
    assert result["parsed_input"]["inheritance"] == "autosomal_recessive"


def test_parse_multiline_disease_condition_line() -> None:
    result = parse_variant_text(
        "BRCA1 NM_007294.4:c.68_69delAG\n"
        "Hereditary breast and ovarian cancer syndrome\n"
        "AD"
    )

    assert result["status"] == "parsed"
    assert result["parsed_input"]["disease"] == (
        "Hereditary breast and ovarian cancer syndrome"
    )
    assert "disease" not in result["missing_fields"]


def test_parse_multiline_hboc_alias_line() -> None:
    result = parse_variant_text("BRCA1 NM_007294.4:c.68_69delAG\nHBOC\nAD")

    assert result["status"] == "parsed"
    assert result["parsed_input"]["disease"] == (
        "Hereditary breast and ovarian cancer syndrome"
    )
    assert result["parsed_input"]["inheritance"] == "autosomal_dominant"


def test_parse_multiline_chinese_disease_phrase() -> None:
    result = parse_variant_text("BRCA1 NM_007294.4:c.68_69delAG\n遗传性乳腺卵巢癌综合征\nAD")

    assert result["status"] == "parsed"
    assert result["parsed_input"]["disease"] == "hereditary breast and ovarian cancer"
    assert "disease" not in result["missing_fields"]


def test_parse_multiline_cftr_cystic_fibrosis() -> None:
    result = parse_variant_text("CFTR NM_000492.4:c.1521_1523delCTT\ncystic fibrosis\nAR")

    assert result["status"] == "parsed"
    assert result["parsed_input"]["gene"] == "CFTR"
    assert result["parsed_input"]["disease"] == "cystic fibrosis"
    assert result["parsed_input"]["inheritance"] == "autosomal_recessive"


def test_parse_multiline_gjb2_hearing_loss() -> None:
    result = parse_variant_text("GJB2 c.35delG\nhearing loss\nAR")

    assert result["status"] == "parsed"
    assert result["parsed_input"]["gene"] == "GJB2"
    assert result["parsed_input"]["disease"] == "hearing loss"
    assert result["parsed_input"]["inheritance"] == "autosomal_recessive"


def test_multiple_disease_like_lines_are_ambiguous() -> None:
    result = parse_variant_text(
        "BRCA1 NM_007294.4:c.68_69delAG\n"
        "breast cancer\n"
        "ovarian cancer\n"
        "AD"
    )

    assert result["status"] == "parsed"
    assert "disease" not in result["parsed_input"]
    assert "disease" in result["missing_fields"]
    assert any(
        "Multiple disease-like lines" in warning
        for warning in result["ambiguity_warnings"]
    )


def test_hgvs_only_still_has_missing_disease() -> None:
    result = parse_variant_text("BRCA1 NM_007294.4:c.68_69delAG")

    assert result["status"] == "parsed"
    assert "disease" not in result["parsed_input"]
    assert "disease" in result["missing_fields"]


def test_parse_genomic_coordinate_extracts_vcf_like_fields() -> None:
    result = parse_variant_text("GRCh38 chr17:43124027 CA>C BRCA1")

    assert result["status"] == "parsed"
    assert result["parsed_input"] == {
        "genome_build": "GRCh38",
        "chromosome": "17",
        "position": 43124027,
        "ref": "CA",
        "alt": "C",
        "gene": "BRCA1",
    }


def test_parse_inheritance_aliases_ad_and_ar() -> None:
    assert parse_variant_text("GJB2 c.35delG hearing loss AR")["parsed_input"][
        "inheritance"
    ] == "autosomal_recessive"
    assert parse_variant_text("BRCA1 c.68_69delAG HBOC AD")["parsed_input"][
        "inheritance"
    ] == "autosomal_dominant"


def test_parse_missing_transcript_and_hgvs_only_limitations() -> None:
    result = parse_variant_text("GJB2 c.35delG hearing loss AR")

    assert "transcript" in result["missing_fields"]
    assert "Transcript missing; PVS1/PS1/PM5 may be limited." in result[
        "normalization_warnings"
    ]
    assert (
        "HGVS-only input cannot be fully genomically normalized without transcript/genome mapping."
        in result["normalization_warnings"]
    )


def test_ambiguous_text_returns_warning() -> None:
    result = parse_variant_text("BRCA1 BRCA2 NM_007294.4:c.68_69delAG HBOC AD")

    assert result["status"] == "parsed"
    assert any("Multiple gene-like tokens" in warning for warning in result["ambiguity_warnings"])


def test_invalid_text_returns_structured_error_without_calling_rate_variant(monkeypatch) -> None:
    def fail_if_called(_payload):
        raise AssertionError("rate_variant should not be called")

    monkeypatch.setattr(
        "variant_pathogenicity_rater.natural_language_input.rate_variant",
        fail_if_called,
    )

    result = rate_variant_from_text("no variant here")

    assert result["status"] == "error"
    assert result["rate_variant_result"] is None
    assert result["error"]["code"] == "NO_SUPPORTED_VARIANT_SHAPE"


def test_parsed_input_does_not_invent_missing_fields() -> None:
    result = parse_variant_text("GJB2 c.35delG hearing loss AR")

    assert "transcript" not in result["parsed_input"]
    assert "chromosome" not in result["parsed_input"]
    assert "position" not in result["parsed_input"]
    assert "ref" not in result["parsed_input"]
    assert "alt" not in result["parsed_input"]


def test_text_wrapper_classification_matches_direct_rate_variant_for_equivalent_input() -> None:
    text_result = rate_variant_from_text(
        "BRCA1 NM_007294.4:c.68_69delAG, HBOC, AD",
        options=OFFLINE_OPTIONS,
    )
    direct_result = rate_variant(text_result["parsed_input"])

    assert text_result["status"] == "ok"
    assert text_result["input"]["original_input"]["text"] == (
        "BRCA1 NM_007294.4:c.68_69delAG, HBOC, AD"
    )
    assert text_result["input"]["parsed_input"] == text_result["parsed_input"]
    assert text_result["classification"]["final_classification"] == text_result[
        "rate_variant_result"
    ]["final_classification"]
    assert text_result["rate_variant_result"]["final_classification"] == direct_result[
        "final_classification"
    ]
    assert text_result["rate_variant_result"]["classification_result"]["final_classification"] == (
        direct_result["classification_result"]["final_classification"]
    )


def test_ai_assisted_candidate_does_not_change_classification_without_confirmation() -> None:
    text = "PTPN11 NM_002834.4:c.922A>G\nNoonan-like with short stature"
    base = rate_variant_from_text(text, options=OFFLINE_OPTIONS)
    assisted = rate_variant_from_text(
        text,
        options={**OFFLINE_OPTIONS, "ai_assisted_context": True},
        ai_assisted_parser=_mock_ai_context,
    )

    assert assisted["context_confirmation_required"] is True
    assert assisted["context_used_for_rating"] is None
    assert assisted["context_candidates"][0]["requires_user_confirmation"] is True
    assert "disease" not in assisted["parsed_input"]
    assert assisted["rate_variant_result"]["final_classification"] == base["rate_variant_result"][
        "final_classification"
    ]


def test_confirmed_context_is_mapped_to_existing_rate_variant_context() -> None:
    result = rate_variant_from_text(
        "PTPN11 NM_002834.4:c.922A>G\nNoonan-like with short stature",
        options={
            **OFFLINE_OPTIONS,
            "ai_assisted_context": True,
            "confirmed_context": {
                "disease_name": "Noonan syndrome",
                "disease_id": "MONDO:0018997",
                "inheritance": "autosomal_dominant",
                "hpo_terms": [{"label": "Short stature", "hpo_id": "HP:0004322"}],
            },
        },
        ai_assisted_parser=_mock_ai_context,
    )

    assert result["context_confirmation_required"] is False
    assert result["context_used_for_rating"] == "confirmed_context"
    assert result["context"]["context_used_for_rating"] == "confirmed_context"
    assert result["context"]["confirmed_context"]["disease_name"] == "Noonan syndrome"
    assert result["parsed_input"]["disease"] == "Noonan syndrome"
    assert result["parsed_input"]["inheritance"] == "autosomal_dominant"
    assert result["parsed_input"]["phenotype_terms"] == ["HP:0004322"]
    assert result["rate_variant_result"]["classification_result"]["context_consistency"] is not None


def test_ai_assisted_multiple_disease_candidates_are_ambiguous() -> None:
    def ambiguous(_text: str, _parsed: dict) -> dict:
        return {
            "disease_candidates": [
                {"disease_name": "Noonan syndrome", "confidence": 0.7},
                {"disease_name": "LEOPARD syndrome", "confidence": 0.68},
            ],
            "ambiguity_warnings": ["Two plausible RASopathy diagnoses were present."],
            "confidence": 0.7,
        }

    result = parse_variant_text(
        "PTPN11 NM_002834.4:c.922A>G\nRASopathy phenotype",
        options={"ai_assisted_context": True},
        ai_assisted_parser=ambiguous,
    )

    assert "disease" not in result["parsed_input"]
    assert len(result["context_candidates"]) == 2
    assert result["ai_assisted_context"]["ambiguity_warnings"]
    assert result["context_candidates"][0]["requires_user_confirmation"] is True


def test_ai_assisted_hpo_terms_are_preserved() -> None:
    result = parse_variant_text(
        "PTPN11 NM_002834.4:c.922A>G\nshort stature phenotype",
        options={"ai_assisted_context": True},
        ai_assisted_parser=_mock_ai_context,
    )

    term = result["ai_assisted_context"]["hpo_terms"][0]
    candidate_term = result["context_candidates"][0]["hpo_terms"][0]
    assert term["label"] == "Short stature"
    assert term["hpo_id"] == "HP:0004322"
    assert term["requires_user_confirmation"] is True
    assert candidate_term["hpo_id"] == "HP:0004322"


def test_ai_assisted_chinese_disease_phrase_can_be_candidate() -> None:
    def chinese(_text: str, _parsed: dict) -> dict:
        return {
            "disease_candidates": [
                {
                    "disease_name": "努南综合征",
                    "normalized_disease_name": "Noonan syndrome",
                    "language": "zh",
                    "confidence": 0.8,
                    "evidence_text_span": "疑似努南综合征",
                }
            ],
            "confidence": 0.8,
            "language": "zh",
        }

    result = parse_variant_text(
        "PTPN11 NM_002834.4:c.922A>G\n疑似努南样表现",
        options={"ai_assisted_context": True},
        ai_assisted_parser=chinese,
    )

    assert result["context_candidates"][0]["disease_name"] == "努南综合征"
    assert result["context_candidates"][0]["normalized_disease_name"] == "Noonan syndrome"
    assert "disease" not in result["parsed_input"]


def test_direct_structured_context_remains_unchanged_without_ai() -> None:
    result = parse_variant_text(
        "BRCA1 NM_007294.4:c.68_69delAG\nHBOC\nAD",
        options={"ai_assisted_context": False},
    )

    assert result["parsed_input"]["disease"] == "Hereditary breast and ovarian cancer syndrome"
    assert result["context_candidates"] == []
    assert result["ai_assisted_context"] is None
