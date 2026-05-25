from __future__ import annotations

from typing import Any

from variant_pathogenicity_rater.literature_agent.schema import LiteratureEvidenceExtraction


def extract_literature_claims(
    records: list[dict[str, Any]],
    *,
    gene: str,
    variant: str,
    transcript: str | None = None,
    disease: str | None = None,
) -> list[LiteratureEvidenceExtraction]:
    """Normalize structured literature records into extraction summaries.

    This intentionally avoids free-form LLM extraction. It preserves provenance from
    caller-provided records and marks ambiguous matching for manual review.
    """

    extractions: list[LiteratureEvidenceExtraction] = []
    for record in records:
        matched_gene = record.get("gene") or gene
        matched_variant = record.get("variant") or record.get("hgvs_c") or record.get("hgvs_p")
        possible_codes = record.get("possible_acmg_codes") or record.get("candidate_codes") or []
        flags: list[str] = []
        if matched_gene and str(matched_gene).upper() != gene.upper():
            flags.append("gene_mismatch")
        if matched_variant and str(matched_variant) != variant:
            flags.append("variant_not_exact")
        if record.get("disease") and disease and str(record["disease"]).lower() != disease.lower():
            flags.append("disease_mismatch")

        sentences = record.get("extracted_sentences") or record.get("sentences") or []
        claim = record.get("claim") or record.get("description")
        if claim and not sentences:
            sentences = [str(claim)]

        extractions.append(
            LiteratureEvidenceExtraction(
                matched_variant=str(matched_variant) if matched_variant else variant,
                matched_gene=str(matched_gene) if matched_gene else gene,
                matched_transcript=record.get("transcript") or transcript,
                matched_disease=record.get("disease") or disease,
                extracted_sentences=[str(sentence) for sentence in sentences],
                extraction_method=str(record.get("extraction_method") or "structured_record"),
                extraction_confidence=float(record.get("extraction_confidence", 0.5)),
                possible_acmg_codes=[str(code) for code in possible_codes],
                ambiguity_flags=flags + [str(flag) for flag in record.get("ambiguity_flags", [])],
            )
        )
    return extractions
