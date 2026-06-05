from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from typing import Any

from pydantic import Field

from variant_pathogenicity_rater.pipeline.output_schema import add_text_canonical_fields
from variant_pathogenicity_rater.pipeline.rate_variant import HUMAN_REVIEW_NOTICE, rate_variant
from variant_pathogenicity_rater.runtime.options import (
    runtime_options_from_text_input,
    runtime_options_to_pipeline_dict,
)
from variant_pathogenicity_rater.schemas.common import SchemaModel


STAGE = "natural_language_variant_input_wrapper"
TOOL_NAME = "rate_variant_from_text"

TRANSCRIPT_RE = re.compile(
    r"\b(?P<transcript>(?:N[MR]_\d+(?:\.\d+)?|ENST\d+(?:\.\d+)?))\b",
    re.I,
)
HGVS_C_RE = re.compile(
    r"\b(?P<hgvs_c>(?:(?:N[MR]_\d+(?:\.\d+)?|ENST\d+(?:\.\d+)?):)?"
    r"c\.[A-Za-z0-9_*+\-.>]+(?:delins|del|dup|ins)?[A-Za-z0-9]*)\b",
    re.I,
)
HGVS_P_RE = re.compile(
    r"\b(?P<hgvs_p>(?:(?:NP_\d+(?:\.\d+)?|ENSP\d+(?:\.\d+)?):)?"
    r"p\.[A-Za-z0-9_*+\-.>]+)\b",
    re.I,
)
GENOMIC_RE = re.compile(
    r"\b(?:(?P<build>GRCh3[78])\s+)?(?:chr)?(?P<chrom>[1-9]|1[0-9]|2[0-2]|X|Y|M|MT)"
    r":(?P<pos>\d+)\s+(?P<ref>[ACGT]+)>(?P<alt>[ACGT]+)\b",
    re.I,
)
GENE_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}\b")
SHORT_ALIAS_RE = re.compile(r"\b(?P<alias>\d+(?:_\d+)?del[A-Z0-9]+)\b", re.I)

INHERITANCE_ALIASES = {
    "AD": "autosomal_dominant",
    "AUTOSOMAL DOMINANT": "autosomal_dominant",
    "AUTOSOMAL_DOMINANT": "autosomal_dominant",
    "常染色体显性遗传": "autosomal_dominant",
    "常染色体显性": "autosomal_dominant",
    "AR": "autosomal_recessive",
    "AUTOSOMAL RECESSIVE": "autosomal_recessive",
    "AUTOSOMAL_RECESSIVE": "autosomal_recessive",
    "常染色体隐性遗传": "autosomal_recessive",
    "常染色体隐性": "autosomal_recessive",
}

DISEASE_ALIASES = {
    "HBOC": "Hereditary breast and ovarian cancer syndrome",
    "CF": "cystic fibrosis",
    "PKU": "phenylketonuria",
    "遗传性乳腺卵巢癌综合征": "hereditary breast and ovarian cancer",
    "CYSTIC FIBROSIS": "cystic fibrosis",
    "HEARING LOSS": "hearing loss",
}

DISEASE_KEYWORDS_EN = (
    "disease",
    "syndrome",
    "cancer",
    "carcinoma",
    "cardiomyopathy",
    "hearing loss",
    "fibrosis",
    "phenylketonuria",
)
DISEASE_KEYWORDS_ZH = (
    "综合征",
    "疾病",
    "肿瘤",
    "癌",
    "耳聋",
    "听力损失",
    "囊性纤维化",
    "苯丙酮尿症",
    "心肌病",
)

GENE_EXCLUDE = {
    "AD",
    "AR",
    "HBOC",
    "CF",
    "PKU",
    "GRCH37",
    "GRCH38",
    "CHR",
    "CA",
    "GT",
    "AG",
    "CT",
    "CTT",
}


class ParsedFieldProvenance(SchemaModel):
    field: str
    value: Any
    source_text: str
    rule: str
    confidence: float = Field(default=1.0, ge=0, le=1)


class ParsedPhenotypeTerm(SchemaModel):
    label: str
    hpo_id: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence_text_span: str | None = None
    language: str | None = None
    parser_source: str = "ai_assisted"
    requires_user_confirmation: bool = True


class ParsedDiseaseCandidate(SchemaModel):
    disease_name: str
    normalized_disease_name: str | None = None
    disease_id: str | None = None
    hpo_terms: list[ParsedPhenotypeTerm] = Field(default_factory=list)
    inheritance: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    evidence_text_span: str | None = None
    language: str | None = None
    parser_source: str = "ai_assisted"
    requires_user_confirmation: bool = True
    ambiguity_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ParsedClinicalContext(SchemaModel):
    disease_candidates: list[ParsedDiseaseCandidate] = Field(default_factory=list)
    hpo_terms: list[ParsedPhenotypeTerm] = Field(default_factory=list)
    inheritance: str | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    language: str | None = None
    parser_source: str = "ai_assisted"
    requires_user_confirmation: bool = True
    ambiguity_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ParsedVariantTextResult(SchemaModel):
    status: str
    tool: str = TOOL_NAME
    stage: str = STAGE
    input_text: str
    parsed_input: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity_warnings: list[str] = Field(default_factory=list)
    normalization_warnings: list[str] = Field(default_factory=list)
    alias_candidates: list[dict[str, Any]] = Field(default_factory=list)
    field_provenance: list[ParsedFieldProvenance] = Field(default_factory=list)
    ai_assisted_context: ParsedClinicalContext | None = None
    context_candidates: list[ParsedDiseaseCandidate] = Field(default_factory=list)
    confirmed_context: dict[str, Any] | None = None
    context_confirmation_required: bool = True
    context_used_for_rating: str | None = None
    review_required: bool = True
    human_review: dict[str, Any] = Field(
        default_factory=lambda: {"required": True, "notice": HUMAN_REVIEW_NOTICE}
    )
    error: dict[str, Any] | None = None


class RateVariantFromTextResult(SchemaModel):
    status: str
    tool: str = TOOL_NAME
    stage: str = STAGE
    input_text: str
    parsed_input: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    ambiguity_warnings: list[str] = Field(default_factory=list)
    normalization_warnings: list[str] = Field(default_factory=list)
    alias_candidates: list[dict[str, Any]] = Field(default_factory=list)
    ai_assisted_context: ParsedClinicalContext | None = None
    context_candidates: list[ParsedDiseaseCandidate] = Field(default_factory=list)
    confirmed_context: dict[str, Any] | None = None
    context_confirmation_required: bool = True
    context_used_for_rating: str | None = None
    rate_variant_result: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    review_required: bool = True
    human_review: dict[str, Any] = Field(
        default_factory=lambda: {"required": True, "notice": HUMAN_REVIEW_NOTICE}
    )
    error: dict[str, Any] | None = None


def parse_variant_text(
    text: str,
    *,
    options: dict[str, Any] | None = None,
    output: str | None = None,
    language: str | None = None,
    report_mode: str | None = None,
    ai_assisted_parser: Callable[[str, dict[str, Any]], dict[str, Any] | ParsedClinicalContext]
    | None = None,
) -> dict[str, Any]:
    input_text = str(text or "").strip()
    if not input_text:
        return _parsed_error(text or "", "EMPTY_TEXT", "Text input is empty.")

    parsed_input: dict[str, Any] = {}
    warnings: list[str] = []
    ambiguity: list[str] = []
    aliases: list[dict[str, Any]] = []
    provenance: list[ParsedFieldProvenance] = []
    options = dict(options or {})
    confirmed_context = _confirmed_context(options)
    context_used_for_rating: str | None = None

    consumed: list[tuple[int, int]] = []
    _extract_genomic(input_text, parsed_input, provenance, consumed, warnings)
    _extract_hgvs(input_text, parsed_input, provenance, consumed, warnings, ambiguity)
    _extract_inheritance(input_text, parsed_input, provenance, consumed)
    _extract_aliases(input_text, aliases, consumed, ambiguity)
    _extract_gene(input_text, parsed_input, provenance, consumed, ambiguity)
    _extract_disease(input_text, parsed_input, provenance, consumed, ambiguity)
    if confirmed_context is not None:
        _apply_confirmed_context(parsed_input, confirmed_context)
        context_used_for_rating = "confirmed_context"
    _apply_report_options(parsed_input, output=output, language=language, report_mode=report_mode)

    missing = _missing_fields(parsed_input)
    ai_context = _maybe_parse_ai_context(
        input_text,
        parsed_input,
        missing,
        ambiguity,
        options,
        ai_assisted_parser,
    )
    if ai_context and ai_context.disease_candidates:
        parsed_input["context_candidates"] = [
            candidate.model_dump(mode="json") for candidate in ai_context.disease_candidates
        ]
    warnings.extend(_safety_warnings(parsed_input, missing))

    if not _has_supported_variant_shape(parsed_input):
        return _parsed_error(
            input_text,
            "NO_SUPPORTED_VARIANT_SHAPE",
            (
                "Could not parse a supported HGVS-like or genomic-coordinate "
                "SNV/small-indel variant shape."
            ),
            parsed_input=parsed_input,
            missing_fields=missing,
            ambiguity_warnings=_unique(ambiguity),
            normalization_warnings=_unique(warnings),
            alias_candidates=aliases,
            field_provenance=provenance,
            ai_assisted_context=ai_context,
            context_candidates=ai_context.disease_candidates if ai_context else [],
            confirmed_context=confirmed_context,
            context_confirmation_required=_context_confirmation_required(options, ai_context),
            context_used_for_rating=context_used_for_rating,
        )

    result = ParsedVariantTextResult(
        status="parsed",
        input_text=input_text,
        parsed_input=parsed_input,
        missing_fields=missing,
        ambiguity_warnings=_unique(ambiguity),
        normalization_warnings=_unique(warnings),
        alias_candidates=aliases,
        field_provenance=provenance,
        ai_assisted_context=ai_context,
        context_candidates=ai_context.disease_candidates if ai_context else [],
        confirmed_context=confirmed_context,
        context_confirmation_required=_context_confirmation_required(options, ai_context),
        context_used_for_rating=context_used_for_rating,
    )
    return add_text_canonical_fields(_dump(result))


def rate_variant_from_text(
    text: str,
    *,
    options: dict[str, Any] | None = None,
    output: str | None = None,
    language: str | None = None,
    report_mode: str | None = None,
    ai_assisted_parser: Callable[[str, dict[str, Any]], dict[str, Any] | ParsedClinicalContext]
    | None = None,
) -> dict[str, Any]:
    parsed = parse_variant_text(
        text,
        options=options,
        output=output,
        language=language,
        report_mode=report_mode,
        ai_assisted_parser=ai_assisted_parser,
    )
    parsed_input = copy.deepcopy(parsed.get("parsed_input") or {})
    runtime_options = runtime_options_from_text_input(
        parsed_input,
        options,
        language,
        output,
        report_mode,
    )
    parsed_input["options"] = runtime_options_to_pipeline_dict(runtime_options)
    if runtime_options.normalization_warnings:
        parsed["normalization_warnings"] = _unique(
            list(parsed.get("normalization_warnings") or [])
            + list(runtime_options.normalization_warnings)
        )

    if parsed.get("status") != "parsed":
        return _rate_error(text, parsed, parsed_input)

    if not _has_supported_variant_shape(parsed_input):
        return _rate_error(text, parsed, parsed_input)

    rate_result = rate_variant(parsed_input)
    result = RateVariantFromTextResult(
        status=rate_result.get("status", "error"),
        input_text=str(text or ""),
        parsed_input=parsed_input,
        missing_fields=list(parsed.get("missing_fields") or []),
        ambiguity_warnings=list(parsed.get("ambiguity_warnings") or []),
        normalization_warnings=list(parsed.get("normalization_warnings") or []),
        alias_candidates=list(parsed.get("alias_candidates") or []),
        ai_assisted_context=(
            ParsedClinicalContext.model_validate(parsed.get("ai_assisted_context"))
            if isinstance(parsed.get("ai_assisted_context"), dict)
            else None
        ),
        context_candidates=[
            ParsedDiseaseCandidate.model_validate(candidate)
            for candidate in parsed.get("context_candidates") or []
        ],
        confirmed_context=parsed.get("confirmed_context"),
        context_confirmation_required=bool(parsed.get("context_confirmation_required", True)),
        context_used_for_rating=parsed.get("context_used_for_rating"),
        rate_variant_result=rate_result,
        report=rate_result.get("report") if isinstance(rate_result, dict) else None,
        error=rate_result.get("error") if isinstance(rate_result, dict) else None,
    )
    return add_text_canonical_fields(_dump(result))


def render_parsed_input_review(result: dict[str, Any]) -> str:
    parsed = result.get("parsed_input") or {}
    lines = ["## Parsed Input Review", "", "Parsed fields:"]
    if parsed:
        for key in sorted(key for key in parsed if key != "options"):
            lines.append(f"- {key}: {parsed[key]}")
    else:
        lines.append("- none")
    for label, key in [
        ("Missing fields", "missing_fields"),
        ("Ambiguity warnings", "ambiguity_warnings"),
        ("Normalization warnings", "normalization_warnings"),
    ]:
        values = result.get(key) or []
        lines.append("")
        lines.append(f"{label}:")
        if values:
            lines.extend(f"- {value}" for value in values)
        else:
            lines.append("- none")
    return "\n".join(lines)


def render_clinical_context_review(result: dict[str, Any]) -> str:
    lines = ["## Parsed Clinical Context Review", ""]
    confirmed = result.get("confirmed_context")
    candidates = result.get("context_candidates") or []
    ai_context = result.get("ai_assisted_context") or {}
    lines.append(f"Context confirmation required: {result.get('context_confirmation_required', True)}")
    lines.append(f"Context used for rating: {result.get('context_used_for_rating') or 'none'}")
    lines.append("")
    lines.append("Confirmed context:")
    if confirmed:
        for key in sorted(confirmed):
            lines.append(f"- {key}: {confirmed[key]}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Candidate context:")
    if candidates:
        for index, candidate in enumerate(candidates, start=1):
            lines.append(f"- candidate {index}: {candidate.get('disease_name')}")
            lines.append(
                "  requires_user_confirmation: "
                f"{candidate.get('requires_user_confirmation', True)}"
            )
            if candidate.get("hpo_terms"):
                labels = [
                    term.get("hpo_id") or term.get("label")
                    for term in candidate.get("hpo_terms") or []
                ]
                lines.append(f"  hpo_terms: {', '.join(str(label) for label in labels)}")
    else:
        lines.append("- none")
    if ai_context.get("limitations"):
        lines.append("")
        lines.append("AI-assisted context limitations:")
        lines.extend(f"- {item}" for item in ai_context["limitations"])
    return "\n".join(lines)


def _extract_genomic(
    text: str,
    parsed: dict[str, Any],
    provenance: list[ParsedFieldProvenance],
    consumed: list[tuple[int, int]],
    warnings: list[str],
) -> None:
    matches = list(GENOMIC_RE.finditer(text))
    if not matches:
        return
    match = matches[0]
    if len(matches) > 1:
        warnings.append("Multiple genomic coordinate candidates were found; the first was used.")
    build = match.group("build")
    if build:
        parsed["genome_build"] = "GRCh37" if build.lower() == "grch37" else "GRCh38"
        _prov(
            provenance,
            "genome_build",
            parsed["genome_build"],
            match.group("build"),
            "genomic_coordinate",
        )
    parsed["chromosome"] = match.group("chrom")
    parsed["position"] = int(match.group("pos"))
    parsed["ref"] = match.group("ref").upper()
    parsed["alt"] = match.group("alt").upper()
    for field in ("chromosome", "position", "ref", "alt"):
        _prov(provenance, field, parsed[field], match.group(0), "genomic_coordinate")
    consumed.append(match.span())


def _extract_hgvs(
    text: str,
    parsed: dict[str, Any],
    provenance: list[ParsedFieldProvenance],
    consumed: list[tuple[int, int]],
    warnings: list[str],
    ambiguity: list[str],
) -> None:
    transcripts = list(TRANSCRIPT_RE.finditer(text))
    if transcripts:
        parsed["transcript"] = transcripts[0].group("transcript")
        _prov(
            provenance,
            "transcript",
            parsed["transcript"],
            transcripts[0].group(0),
            "transcript_regex",
        )
        consumed.append(transcripts[0].span())
        if len(transcripts) > 1:
            ambiguity.append("Multiple transcript candidates were found; the first was used.")

    hgvs_c_matches = list(HGVS_C_RE.finditer(text))
    if hgvs_c_matches:
        hgvs_c = hgvs_c_matches[0].group("hgvs_c")
        parsed["hgvs_c"] = hgvs_c
        _prov(provenance, "hgvs_c", hgvs_c, hgvs_c_matches[0].group(0), "hgvs_c_regex")
        consumed.append(hgvs_c_matches[0].span())
        if ":" not in hgvs_c and parsed.get("transcript"):
            warnings.append(
                "Transcript and bare hgvs_c were parsed separately; "
                "the parser did not rewrite HGVS."
            )
        if len(hgvs_c_matches) > 1:
            ambiguity.append("Multiple hgvs_c candidates were found; the first was used.")

    hgvs_p_matches = list(HGVS_P_RE.finditer(text))
    if hgvs_p_matches:
        hgvs_p = hgvs_p_matches[0].group("hgvs_p")
        parsed["hgvs_p"] = hgvs_p
        _prov(provenance, "hgvs_p", hgvs_p, hgvs_p_matches[0].group(0), "hgvs_p_regex")
        consumed.append(hgvs_p_matches[0].span())
        if len(hgvs_p_matches) > 1:
            ambiguity.append("Multiple hgvs_p candidates were found; the first was used.")


def _extract_inheritance(
    text: str,
    parsed: dict[str, Any],
    provenance: list[ParsedFieldProvenance],
    consumed: list[tuple[int, int]],
) -> None:
    upper = text.upper()
    for alias, normalized in INHERITANCE_ALIASES.items():
        pattern = re.escape(alias)
        match = re.search(pattern, text if _contains_cjk(alias) else upper, re.I)
        if match:
            parsed["inheritance"] = normalized
            _prov(provenance, "inheritance", normalized, match.group(0), "inheritance_alias")
            consumed.append(match.span())
            return


def _extract_aliases(
    text: str,
    aliases: list[dict[str, Any]],
    consumed: list[tuple[int, int]],
    ambiguity: list[str],
) -> None:
    for match in SHORT_ALIAS_RE.finditer(text):
        if _overlaps(match.span(), consumed):
            continue
        candidate = {
            "alias": match.group("alias"),
            "type": "short_variant_name",
            "normalized": False,
            "reason": (
                "Short variant aliases are not silently normalized without an explicit "
                "dictionary match."
            ),
        }
        aliases.append(candidate)
        consumed.append(match.span())
    if aliases:
        ambiguity.append(
            "Short variant alias candidate found; it was not converted to HGVS or "
            "genomic coordinates."
        )


def _extract_gene(
    text: str,
    parsed: dict[str, Any],
    provenance: list[ParsedFieldProvenance],
    consumed: list[tuple[int, int]],
    ambiguity: list[str],
) -> None:
    candidates: list[re.Match[str]] = []
    for match in GENE_RE.finditer(text):
        value = match.group(0)
        if value.upper() in GENE_EXCLUDE or re.match(r"^CHR", value, re.I):
            continue
        if _overlaps(match.span(), consumed):
            continue
        candidates.append(match)
    if not candidates:
        return
    parsed["gene"] = candidates[0].group(0)
    _prov(provenance, "gene", parsed["gene"], candidates[0].group(0), "gene_token_regex", 0.8)
    consumed.append(candidates[0].span())
    unique = _unique([candidate.group(0) for candidate in candidates])
    if len(unique) > 1:
        ambiguity.append(
            f"Multiple gene-like tokens were found: {', '.join(unique)}; "
            "the first was used."
        )


def _extract_disease(
    text: str,
    parsed: dict[str, Any],
    provenance: list[ParsedFieldProvenance],
    consumed: list[tuple[int, int]],
    ambiguity: list[str],
) -> None:
    upper = text.upper()
    for alias, disease in DISEASE_ALIASES.items():
        if _contains_cjk(alias):
            match = re.search(re.escape(alias), text)
        else:
            match = re.search(rf"\b{re.escape(alias)}\b", upper, re.I)
        if match:
            parsed["disease"] = disease
            _prov(provenance, "disease", disease, match.group(0), "disease_alias", 0.9)
            consumed.append(match.span())
            return

    line_candidates = _disease_line_candidates(text, parsed)
    if len(line_candidates) == 1:
        disease = line_candidates[0]
        parsed["disease"] = disease
        _prov(provenance, "disease", disease, disease, "disease_line_keyword", 0.8)
        return
    if len(line_candidates) > 1:
        ambiguity.append(
            "Multiple disease-like lines were found; disease was not selected automatically: "
            + "; ".join(line_candidates)
        )
        return

    pieces = [piece.strip(" ，,;；") for piece in re.split(r"[,，;；]", text)]
    for piece in pieces:
        if not piece:
            continue
        if not _contains_disease_keyword(piece):
            continue
        if _is_non_disease_line(piece):
            continue
        remaining = piece
        if parsed.get("gene"):
            remaining = re.sub(rf"\b{re.escape(str(parsed['gene']))}\b", "", remaining).strip()
        if remaining and not GENE_RE.fullmatch(remaining):
            parsed["disease"] = remaining
            _prov(provenance, "disease", remaining, piece, "disease_remaining_segment", 0.6)
            return


def _apply_report_options(
    parsed: dict[str, Any],
    *,
    output: str | None,
    language: str | None,
    report_mode: str | None,
) -> None:
    options: dict[str, Any] = {}
    resolved_language = language
    resolved_mode = report_mode
    if output == "markdown-zh":
        resolved_language = "zh"
        resolved_mode = resolved_mode or "laboratory"
    if resolved_language == "zh":
        resolved_mode = resolved_mode or "laboratory"
    if resolved_language:
        options["report_language"] = resolved_language
    if resolved_mode:
        options["report_mode"] = resolved_mode
    if options:
        parsed["options"] = options


def _missing_fields(parsed: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("gene", "transcript", "disease", "inheritance"):
        if not parsed.get(field):
            missing.append(field)
    if not all(parsed.get(field) for field in ("chromosome", "position", "ref", "alt")):
        missing.extend(
            field
            for field in ("chromosome", "position", "ref", "alt")
            if not parsed.get(field)
        )
    if not parsed.get("hgvs_c") and not all(
        parsed.get(field) for field in ("chromosome", "position", "ref", "alt")
    ):
        missing.append("hgvs_c")
    return _unique(missing)


def _safety_warnings(parsed: dict[str, Any], missing: list[str]) -> list[str]:
    warnings: list[str] = []
    if "transcript" in missing:
        warnings.append("Transcript missing; PVS1/PS1/PM5 may be limited.")
    if any(field in missing for field in ("chromosome", "position", "ref", "alt")):
        warnings.append("Genomic coordinate missing; PM2/population/PVS1 may be limited.")
    if "disease" in missing or "inheritance" in missing:
        warnings.append("Disease/inheritance missing; evidence confidence may be limited.")
    if parsed.get("hgvs_c") and any(field in missing for field in ("chromosome", "position")):
        warnings.append(
            "HGVS-only input cannot be fully genomically normalized without "
            "transcript/genome mapping."
        )
    return warnings


def _has_supported_variant_shape(parsed: dict[str, Any]) -> bool:
    has_hgvs = bool(parsed.get("hgvs_c"))
    has_genomic = all(parsed.get(field) for field in ("chromosome", "position", "ref", "alt"))
    return has_hgvs or has_genomic


def _rate_error(text: str, parsed: dict[str, Any], parsed_input: dict[str, Any]) -> dict[str, Any]:
    return add_text_canonical_fields(_dump(
        RateVariantFromTextResult(
            status="error",
            input_text=str(text or ""),
            parsed_input=parsed_input,
            missing_fields=list(parsed.get("missing_fields") or []),
            ambiguity_warnings=list(parsed.get("ambiguity_warnings") or []),
            normalization_warnings=list(parsed.get("normalization_warnings") or []),
            alias_candidates=list(parsed.get("alias_candidates") or []),
            error=parsed.get("error")
            or {
                "code": "NO_SUPPORTED_VARIANT_SHAPE",
                "message": "No supported variant shape was parsed; rate_variant was not called.",
            },
        )
    ))


def _parsed_error(
    input_text: str,
    code: str,
    message: str,
    *,
    parsed_input: dict[str, Any] | None = None,
    missing_fields: list[str] | None = None,
    ambiguity_warnings: list[str] | None = None,
    normalization_warnings: list[str] | None = None,
    alias_candidates: list[dict[str, Any]] | None = None,
    field_provenance: list[ParsedFieldProvenance] | None = None,
    ai_assisted_context: ParsedClinicalContext | None = None,
    context_candidates: list[ParsedDiseaseCandidate] | None = None,
    confirmed_context: dict[str, Any] | None = None,
    context_confirmation_required: bool = True,
    context_used_for_rating: str | None = None,
) -> dict[str, Any]:
    return _dump(
        ParsedVariantTextResult(
            status="error",
            input_text=input_text,
            parsed_input=parsed_input or {},
            missing_fields=missing_fields or [],
            ambiguity_warnings=ambiguity_warnings or [],
            normalization_warnings=normalization_warnings or [],
            alias_candidates=alias_candidates or [],
            field_provenance=field_provenance or [],
            ai_assisted_context=ai_assisted_context,
            context_candidates=context_candidates or [],
            confirmed_context=confirmed_context,
            context_confirmation_required=context_confirmation_required,
            context_used_for_rating=context_used_for_rating,
            error={"code": code, "message": message},
        )
    )


def _merge_options(existing: Any, extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in extra.items():
        if key == "data_sources" and isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def _normalize_inheritance_piece(piece: str) -> str | None:
    normalized = piece.strip().upper().replace("_", " ")
    return INHERITANCE_ALIASES.get(normalized) or INHERITANCE_ALIASES.get(piece.strip())


def _confirmed_context(options: dict[str, Any]) -> dict[str, Any] | None:
    context = options.get("confirmed_context") or options.get("reviewed_context")
    if not isinstance(context, dict) or not context:
        return None
    return copy.deepcopy(context)


def _apply_confirmed_context(parsed: dict[str, Any], context: dict[str, Any]) -> None:
    disease = (
        context.get("disease_name")
        or context.get("normalized_disease_name")
        or context.get("disease")
    )
    if disease:
        parsed["disease"] = str(disease)
    inheritance = context.get("inheritance") or context.get("inheritance_mode")
    if inheritance:
        parsed["inheritance"] = str(inheritance)
    hpo_terms = context.get("hpo_terms") or context.get("phenotype_terms")
    if isinstance(hpo_terms, list) and hpo_terms:
        parsed["phenotype_terms"] = [_phenotype_label(term) for term in hpo_terms]
    disease_id = context.get("disease_id")
    if disease_id:
        parsed.setdefault("gene_disease_context", {})["disease_id"] = str(disease_id)


def _maybe_parse_ai_context(
    text: str,
    parsed: dict[str, Any],
    missing: list[str],
    ambiguity: list[str],
    options: dict[str, Any],
    ai_assisted_parser: Callable[[str, dict[str, Any]], dict[str, Any] | ParsedClinicalContext]
    | None,
) -> ParsedClinicalContext | None:
    if not options.get("ai_assisted_context"):
        return None
    if not _should_run_ai_context(text, parsed, missing, ambiguity):
        return None
    if ai_assisted_parser is None:
        return ParsedClinicalContext(
            confidence=0.0,
            requires_user_confirmation=True,
            limitations=[
                "AI-assisted context parsing was requested, but no AI parser provider was supplied.",
                "No AI-derived context was used for rating.",
            ],
        )
    raw_context = ai_assisted_parser(text, copy.deepcopy(parsed))
    return _clinical_context_from_raw(raw_context)


def _should_run_ai_context(
    text: str,
    parsed: dict[str, Any],
    missing: list[str],
    ambiguity: list[str],
) -> bool:
    if "disease" in missing:
        return True
    if any("disease" in warning.lower() for warning in ambiguity):
        return True
    if _contains_complex_phenotype_text(text, parsed):
        return True
    return False


def _contains_complex_phenotype_text(text: str, parsed: dict[str, Any]) -> bool:
    if parsed.get("phenotype_terms"):
        return True
    lowered = text.lower()
    phenotype_markers = ("hpo:", "hp:", "phenotype", "seizure", "ataxia", "developmental delay")
    if any(marker in lowered for marker in phenotype_markers):
        return True
    return any(marker in text for marker in ("表型", "发育迟缓", "癫痫", "共济失调"))


def _clinical_context_from_raw(
    raw_context: dict[str, Any] | ParsedClinicalContext,
) -> ParsedClinicalContext:
    if isinstance(raw_context, ParsedClinicalContext):
        context = raw_context
    else:
        context = ParsedClinicalContext.model_validate(raw_context or {})
    context.parser_source = "ai_assisted"
    context.requires_user_confirmation = True
    context.disease_candidates = [
        _force_ai_disease_candidate(candidate) for candidate in context.disease_candidates
    ]
    context.hpo_terms = [_force_ai_phenotype_term(term) for term in context.hpo_terms]
    return context


def _force_ai_disease_candidate(candidate: ParsedDiseaseCandidate) -> ParsedDiseaseCandidate:
    candidate.parser_source = "ai_assisted"
    candidate.requires_user_confirmation = True
    candidate.hpo_terms = [_force_ai_phenotype_term(term) for term in candidate.hpo_terms]
    return candidate


def _force_ai_phenotype_term(term: ParsedPhenotypeTerm) -> ParsedPhenotypeTerm:
    term.parser_source = "ai_assisted"
    term.requires_user_confirmation = True
    return term


def _context_confirmation_required(
    options: dict[str, Any],
    ai_context: ParsedClinicalContext | None,
) -> bool:
    if _confirmed_context(options):
        return False
    if options.get("require_context_confirmation") is False and ai_context is None:
        return False
    return bool(ai_context and ai_context.requires_user_confirmation) or bool(
        options.get("require_context_confirmation", True)
    )


def _phenotype_label(term: Any) -> str:
    if isinstance(term, dict):
        return str(term.get("hpo_id") or term.get("label") or term)
    return str(term)


def _disease_line_candidates(text: str, parsed: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for line in text.splitlines():
        candidate = line.strip(" \t，,;；")
        if not candidate:
            continue
        if _is_non_disease_line(candidate):
            continue
        if not _contains_disease_keyword(candidate):
            continue
        if parsed.get("gene"):
            candidate = re.sub(
                rf"\b{re.escape(str(parsed['gene']))}\b",
                "",
                candidate,
                flags=re.I,
            ).strip(" \t，,;；")
        if candidate and not GENE_RE.fullmatch(candidate):
            candidates.append(candidate)
    return _unique(candidates)


def _is_non_disease_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if _normalize_inheritance_piece(stripped):
        return True
    if any(token in stripped for token in ("评估", "rate", "variant")):
        return True
    if HGVS_C_RE.search(stripped) or HGVS_P_RE.search(stripped) or GENOMIC_RE.search(stripped):
        return True
    if SHORT_ALIAS_RE.search(stripped) or TRANSCRIPT_RE.search(stripped):
        return True
    if GENE_RE.fullmatch(stripped):
        return True
    return False


def _contains_disease_keyword(value: str) -> bool:
    lower = value.lower()
    if any(keyword in lower for keyword in DISEASE_KEYWORDS_EN):
        return True
    return any(keyword in value for keyword in DISEASE_KEYWORDS_ZH)


def _prov(
    provenance: list[ParsedFieldProvenance],
    field: str,
    value: Any,
    source: str,
    rule: str,
    confidence: float = 1.0,
) -> None:
    provenance.append(
        ParsedFieldProvenance(
            field=field,
            value=value,
            source_text=source,
            rule=rule,
            confidence=confidence,
        )
    )


def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < other_end and end > other_start for other_start, other_end in spans)


def _contains_cjk(value: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in value)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            output.append(value)
    return output


def _dump(model: SchemaModel) -> dict[str, Any]:
    return json.loads(model.model_dump_json())
