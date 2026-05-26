from __future__ import annotations

import re

from variant_pathogenicity_rater.ps1_pm5.schema import AminoAcidMatch, ParsedProteinChange
from variant_pathogenicity_rater.schemas.evidence import ClinVarRecord
from variant_pathogenicity_rater.schemas.variant import Variant


AA3_TO_1 = {
    "Ala": "A",
    "Arg": "R",
    "Asn": "N",
    "Asp": "D",
    "Cys": "C",
    "Gln": "Q",
    "Glu": "E",
    "Gly": "G",
    "His": "H",
    "Ile": "I",
    "Leu": "L",
    "Lys": "K",
    "Met": "M",
    "Phe": "F",
    "Pro": "P",
    "Ser": "S",
    "Thr": "T",
    "Trp": "W",
    "Tyr": "Y",
    "Val": "V",
    "Ter": "*",
    "Stop": "*",
}

AA_PATTERN = re.compile(
    r"^(?:(?P<accession>[A-Z]{1,3}_\d+(?:\.\d+)?):)?p\.?\(?"
    r"(?P<ref>[A-Z][a-z]{2}|[A-Z])(?P<pos>\d+)(?P<alt>[A-Z][a-z]{2}|[A-Z]|\*)\)?$"
)


def compare_amino_acid_change(variant: Variant, record: ClinVarRecord) -> AminoAcidMatch:
    query_hgvs_p = variant.hgvs_p or (variant.transcript.hgvs_p if variant.transcript else None)
    comparator_hgvs_p = record.hgvs_p or record.protein_change
    query = parse_protein_change(query_hgvs_p)
    comparator = parse_protein_change(comparator_hgvs_p)
    query_transcript = _variant_transcript(variant)
    comparator_transcript = record.transcript or _transcript_from_hgvs_c(record.hgvs_c)
    limitations = [*query.limitations, *comparator.limitations]

    same_residue = (
        query.parseable
        and comparator.parseable
        and query.position == comparator.position
        and query.ref_aa == comparator.ref_aa
    )
    same_amino_acid_change = (
        same_residue
        and query.alt_aa == comparator.alt_aa
        and query.change_type == "missense"
        and comparator.change_type == "missense"
    )
    different_missense_change = (
        same_residue
        and query.alt_aa != comparator.alt_aa
        and query.change_type == "missense"
        and comparator.change_type == "missense"
    )
    transcript_or_protein_match = _transcript_or_protein_match(
        query.accession,
        comparator.accession,
        query_transcript,
        comparator_transcript,
    )
    if query.parseable and comparator.parseable and not transcript_or_protein_match:
        limitations.append("Transcript/protein accession does not clearly match comparator.")

    confidence = "unavailable"
    if query.parseable and comparator.parseable:
        confidence = "high" if transcript_or_protein_match else "low"
    elif query.raw or comparator.raw:
        confidence = "low"

    return AminoAcidMatch(
        query_protein_accession=query.accession,
        comparator_protein_accession=comparator.accession,
        query_transcript=query_transcript,
        comparator_transcript=comparator_transcript,
        query_hgvs_p=query_hgvs_p,
        comparator_hgvs_p=comparator_hgvs_p,
        query_parsed=query,
        comparator_parsed=comparator,
        ref_aa=query.ref_aa if same_residue else None,
        position=query.position if same_residue else None,
        alt_aa=query.alt_aa if same_amino_acid_change else None,
        change_type=query.change_type if query.change_type == comparator.change_type else "unknown",
        protein_parseable=query.parseable and comparator.parseable,
        same_residue=same_residue,
        same_amino_acid_change=same_amino_acid_change,
        different_missense_change=different_missense_change,
        transcript_or_protein_match=transcript_or_protein_match,
        confidence=confidence,
        limitations=limitations,
    )


def parse_protein_change(value: str | None) -> ParsedProteinChange:
    text = (value or "").strip()
    if not text:
        return ParsedProteinChange(raw=value, limitations=["Protein consequence is missing."])
    normalized = text.replace(" ", "")
    match = AA_PATTERN.match(normalized)
    if not match:
        return ParsedProteinChange(
            raw=value,
            limitations=[f"Protein consequence could not be parsed: {value}"],
        )
    ref = _aa(match.group("ref"))
    alt = _aa(match.group("alt"))
    if ref is None or alt is None:
        return ParsedProteinChange(
            accession=match.group("accession"),
            raw=value,
            limitations=[f"Protein consequence contains unsupported amino acid code: {value}"],
        )
    change_type = "missense" if ref != alt and alt != "*" else "non_missense"
    return ParsedProteinChange(
        accession=match.group("accession"),
        raw=value,
        ref_aa=ref,
        position=int(match.group("pos")),
        alt_aa=alt,
        change_type=change_type,
        parseable=True,
    )


def _aa(value: str) -> str | None:
    if len(value) == 1:
        return value if value == "*" or value.isalpha() else None
    return AA3_TO_1.get(value)


def _variant_transcript(variant: Variant) -> str | None:
    if variant.transcript is None:
        return None
    if variant.transcript.version:
        return f"{variant.transcript.accession}.{variant.transcript.version}"
    return variant.transcript.accession


def _transcript_from_hgvs_c(value: str | None) -> str | None:
    if not value or ":" not in value:
        return None
    return value.split(":", 1)[0]


def _transcript_or_protein_match(
    query_protein: str | None,
    comparator_protein: str | None,
    query_transcript: str | None,
    comparator_transcript: str | None,
) -> bool:
    if query_protein and comparator_protein:
        return query_protein == comparator_protein
    if query_transcript and comparator_transcript:
        return query_transcript == comparator_transcript
    return False
