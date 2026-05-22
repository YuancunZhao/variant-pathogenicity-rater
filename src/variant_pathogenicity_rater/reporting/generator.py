from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from variant_pathogenicity_rater.reporting.templates import (
    CLINVAR_CONFLICT_ALERT,
    COMPUTATIONAL_CAUTION,
    HUMAN_REVIEW_NOTE,
    MODE_TEMPLATES,
    VUS_NOTE,
    ZH_PLACEHOLDER,
)
from variant_pathogenicity_rater.schemas.classification import ClassificationResult
from variant_pathogenicity_rater.schemas.evidence import EvidenceItem
from variant_pathogenicity_rater.schemas.evidence import EvidenceStrength
from variant_pathogenicity_rater.schemas.report import (
    DataSourceSummary,
    EvidenceReportEntry,
    ReportFormat,
    ReportLanguage,
    ReportMode,
    VariantReport,
    VariantReportSummary,
)


CLASSIFICATION_LABELS = {
    "pathogenic": "Pathogenic",
    "likely_pathogenic": "Likely Pathogenic",
    "vus": "Variant of Uncertain Significance",
    "likely_benign": "Likely Benign",
    "benign": "Benign",
}


def generate_report(
    classification_result: ClassificationResult | None = None,
    *,
    output_format: ReportFormat | str = ReportFormat.MARKDOWN,
    mode: ReportMode | str = ReportMode.DETAILED,
    language: ReportLanguage | str = ReportLanguage.ENGLISH,
    **legacy_kwargs: Any,
) -> VariantReport:
    """Render a supplied ClassificationResult without recalculating ACMG logic."""

    result = classification_result or legacy_kwargs.get("classification_result")
    if not isinstance(result, ClassificationResult):
        raise TypeError("generate_report requires a ClassificationResult.")

    report_format = ReportFormat(output_format)
    report_mode = ReportMode(mode)
    report_language = ReportLanguage(language)
    summary = _summary(result)

    if report_format == ReportFormat.JSON:
        content: str | dict[str, Any] = _json_content(result, summary, report_mode, report_language)
    else:
        content = _text_content(result, summary, report_mode, report_language)
        if report_format == ReportFormat.PLAIN_TEXT:
            content = _plain_text(content)

    return VariantReport(
        report_id=_report_id(result, report_mode, report_format, report_language),
        result_id=result.result_id,
        mode=report_mode,
        output_format=report_format,
        language=report_language,
        summary=summary,
        content=content,
        source_result=result,
        human_review_required=True,
    )


def _summary(result: ClassificationResult) -> VariantReportSummary:
    variant = result.variant
    applied_entries = [
        _evidence_entry(item) for item in result.evidence_items if _is_applied_evidence(item)
    ]
    candidate_entries = [
        _evidence_entry(item) for item in result.evidence_items if not _is_applied_evidence(item)
    ]
    return VariantReportSummary(
        variant_id=variant.variant_id,
        gene_symbol=variant.gene_symbol,
        transcript=_transcript_label(variant),
        hgvs_c=variant.hgvs_c,
        hgvs_p=variant.hgvs_p,
        genomic_location=(
            f"{variant.genome_build}:{variant.chrom}:{variant.pos}:"
            f"{variant.ref}>{variant.alt}"
        ),
        final_classification=str(result.final_classification),
        classification_label=CLASSIFICATION_LABELS.get(
            str(result.final_classification),
            str(result.final_classification),
        ),
        confidence=result.confidence,
        applied_combination_rule=result.applied_combination_rule,
        triggered_acmg_evidence=applied_entries,
        candidate_acmg_evidence=candidate_entries,
        pathogenic_evidence_summary=result.pathogenic_evidence_summary,
        benign_evidence_summary=result.benign_evidence_summary,
        conflicting_evidence=result.conflicting_evidence,
        clinvar_conflict_detected=_clinvar_conflict_detected(result),
        limitations=result.limitations,
        human_review_note=HUMAN_REVIEW_NOTE,
        data_source_summary=_data_source_summary(result.evidence_items),
        review_flags=result.review_flags,
    )


def _evidence_entry(item: EvidenceItem) -> EvidenceReportEntry:
    return EvidenceReportEntry(
        evidence_id=item.evidence_id,
        code=str(item.code),
        strength=str(item.strength),
        direction=str(item.direction),
        rationale=item.reason,
        source=item.source.name,
        confidence=item.confidence,
        requires_review=item.requires_review,
        triggered_by=item.triggered_by,
        citation=item.supporting_data.get("citation"),
        provenance=item.source.provenance,
        limitations=list(item.supporting_data.get("limitations") or []),
        review_flags=item.review_flags,
    )


def _data_source_summary(items: list[EvidenceItem]) -> list[DataSourceSummary]:
    by_source: dict[tuple[str, str | None], DataSourceSummary] = {}
    for item in items:
        key = (item.source.name, item.source.version)
        if key not in by_source:
            by_source[key] = DataSourceSummary(
                name=item.source.name,
                version=item.source.version,
                retrieval_timestamp=item.source.retrieval_timestamp,
                evidence_ids=[],
                query=item.source.query,
                raw_snapshot_ref=item.source.raw_snapshot_ref,
            )
        by_source[key].evidence_ids.append(item.evidence_id)
    return list(by_source.values())


def _json_content(
    result: ClassificationResult,
    summary: VariantReportSummary,
    mode: ReportMode,
    language: ReportLanguage,
) -> dict[str, Any]:
    cautions = _cautions(result, summary)
    return {
        "mode": mode,
        "language": language,
        "variant": {
            "variant_id": summary.variant_id,
            "gene_symbol": summary.gene_symbol,
            "genomic_location": summary.genomic_location,
            "hgvs_c": summary.hgvs_c,
            "hgvs_p": summary.hgvs_p,
        },
        "final_classification": {
            "value": summary.final_classification,
            "label": summary.classification_label,
            "applied_combination_rule": summary.applied_combination_rule,
            "confidence": summary.confidence,
            "machine_proposal_only": True,
        },
        "evidence": {
            "pathogenic": summary.pathogenic_evidence_summary,
            "benign": summary.benign_evidence_summary,
            "conflicting": summary.conflicting_evidence,
            "applied_items": [
                entry.model_dump(mode="json") for entry in summary.triggered_acmg_evidence
            ],
            "candidate_items": [
                entry.model_dump(mode="json") for entry in summary.candidate_acmg_evidence
            ],
        },
        "limitations": summary.limitations,
        "cautions": cautions,
        "clinvar_conflict_detected": summary.clinvar_conflict_detected,
        "data_source_summary": [
            source.model_dump(mode="json") for source in summary.data_source_summary
        ],
        "review_flags": [flag.model_dump(mode="json") for flag in summary.review_flags],
        "human_review_required": True,
        "human_review_note": summary.human_review_note,
    }


def _text_content(
    result: ClassificationResult,
    summary: VariantReportSummary,
    mode: ReportMode,
    language: ReportLanguage,
) -> str:
    template = MODE_TEMPLATES[mode]
    lines = [
        f"# {template.title}",
        "",
        template.opening_label,
        "",
        "## Variant Summary",
        f"- Variant: {summary.variant_id}",
        f"- Gene: {summary.gene_symbol or 'not provided'}",
        f"- Transcript: {summary.transcript or 'not provided'}",
        f"- HGVS c.: {summary.hgvs_c or 'not provided'}",
        f"- HGVS p.: {summary.hgvs_p or 'not provided'}",
        f"- Genomic location: {summary.genomic_location}",
        "",
        "## Final Classification",
        f"- Machine proposal: {summary.classification_label}",
        f"- Applied combination rule: {summary.applied_combination_rule or 'none'}",
        f"- Confidence: {summary.confidence:.2f}",
        "- Human review required: true",
    ]

    lines.extend(_caution_lines(result, summary, language))

    lines.extend(_evidence_chain_lines(summary, include_details=template.include_evidence_table))
    lines.extend(_conflicting_evidence_lines(summary))

    lines.extend(["", "## Limitations"])
    if summary.limitations:
        lines.extend(f"- {item}" for item in summary.limitations)
    else:
        lines.append("- No additional limitations were supplied beyond mandatory human review.")

    lines.extend(_data_source_lines(summary, include_details=template.include_audit_details))

    if template.include_reviewer_checklist:
        lines.extend(
            [
                "",
                "## Human Review Checklist",
                "- Verify variant normalization and transcript selection.",
                "- Verify every ACMG evidence item and strength adjustment.",
                "- Resolve any conflicting evidence before sign-out.",
            ]
        )

    if template.include_audit_details and result.audit_trail:
        lines.extend(["", "## Audit Trail"])
        lines.extend(
            f"- {event.event_type} via {event.tool_name or 'system'} at "
            f"{event.timestamp.isoformat()}"
            for event in result.audit_trail
        )

    lines.extend(["", "## Human Review Note", HUMAN_REVIEW_NOTE])
    return "\n".join(lines)


def _evidence_chain_lines(
    summary: VariantReportSummary,
    *,
    include_details: bool,
) -> list[str]:
    lines = ["", "## Triggered ACMG Evidence"]
    if not summary.triggered_acmg_evidence:
        lines.append("- No ACMG evidence items were supplied.")
    else:
        for entry in summary.triggered_acmg_evidence:
            lines.append(
                f"- {entry.evidence_id}: {entry.code} / {entry.strength} / "
                f"{entry.direction}; source: {entry.source}; rationale: {entry.rationale}"
            )
            if include_details:
                lines.append(f"  - Confidence: {entry.confidence:.2f}")
                lines.append(f"  - Requires review: {str(entry.requires_review).lower()}")
                if entry.triggered_by:
                    lines.append(f"  - Triggered by: {', '.join(entry.triggered_by)}")
    lines.extend(["", "## Candidate / Review-Note Evidence"])
    if not summary.candidate_acmg_evidence:
        lines.append("- No candidate-only ACMG evidence items were supplied.")
        return lines

    for entry in summary.candidate_acmg_evidence:
        lines.append(
            f"- {entry.evidence_id}: {entry.code} / {entry.strength} / "
            f"{entry.direction}; source: {entry.source}; rationale: {entry.rationale}"
        )
        if include_details:
            lines.append(f"  - Confidence: {entry.confidence:.2f}")
            lines.append("  - Status: candidate/review-note only; not used in classification")
            if entry.citation:
                lines.append(f"  - Citation: {entry.citation}")
            if entry.provenance:
                lines.append("  - Provenance: retained on evidence source")
    return lines


def _conflicting_evidence_lines(summary: VariantReportSummary) -> list[str]:
    lines = ["", "## Conflicting Evidence"]
    if summary.clinvar_conflict_detected:
        lines.append(f"- {CLINVAR_CONFLICT_ALERT}")
    if summary.conflicting_evidence:
        lines.extend(f"- {item}" for item in summary.conflicting_evidence)
    elif not summary.clinvar_conflict_detected:
        lines.append("- No conflicting evidence was reported in the supplied classification result.")
    return lines


def _data_source_lines(
    summary: VariantReportSummary,
    *,
    include_details: bool,
) -> list[str]:
    lines = ["", "## Data Source Summary"]
    if not summary.data_source_summary:
        lines.append("- No evidence data sources were supplied.")
        return lines

    for source in summary.data_source_summary:
        version = f" ({source.version})" if source.version else ""
        ids = ", ".join(source.evidence_ids) if source.evidence_ids else "none"
        lines.append(f"- {source.name}{version}: evidence IDs {ids}")
        if include_details:
            if source.retrieval_timestamp:
                lines.append(f"  - Retrieved: {source.retrieval_timestamp}")
            if source.raw_snapshot_ref:
                lines.append(f"  - Raw snapshot: {source.raw_snapshot_ref}")
            if source.query:
                lines.append(f"  - Query: {_json_fragment(source.query)}")
    return lines


def _json_fragment(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _caution_lines(
    result: ClassificationResult,
    summary: VariantReportSummary,
    language: ReportLanguage,
) -> list[str]:
    lines: list[str] = []
    cautions = _cautions(result, summary)
    if cautions:
        lines.extend(["", "## Cautions"])
        lines.extend(f"- {item}" for item in cautions)
    if language == ReportLanguage.CHINESE:
        lines.append(f"- {ZH_PLACEHOLDER}")
    return lines


def _cautions(result: ClassificationResult, summary: VariantReportSummary) -> list[str]:
    cautions: list[str] = []
    if summary.final_classification == "vus":
        cautions.append(VUS_NOTE)
    if any(str(item.code) in {"PP3", "BP4"} for item in result.evidence_items):
        cautions.append(COMPUTATIONAL_CAUTION)
    if summary.clinvar_conflict_detected:
        cautions.append(CLINVAR_CONFLICT_ALERT)
    return cautions


def _clinvar_conflict_detected(result: ClassificationResult) -> bool:
    if result.conflicting_evidence:
        return any("clinvar" in item.lower() for item in result.conflicting_evidence)
    return any(
        item.source.name.lower() == "clinvar"
        and (
            str(item.direction) == "conflicting"
            or bool(item.supporting_data.get("conflicting_interpretations"))
        )
        for item in result.evidence_items
    )


def _is_applied_evidence(item: EvidenceItem) -> bool:
    return not (
        str(item.strength) == EvidenceStrength.NONE.value
        or item.supporting_data.get("candidate_only")
        or item.supporting_data.get("evidence_status") == "candidate"
        or item.supporting_data.get("applied") is False
    )


def _transcript_label(result_variant: Any) -> str | None:
    transcript = result_variant.transcript
    if transcript is None:
        return None
    if transcript.version:
        return f"{transcript.accession}.{transcript.version}"
    return transcript.accession


def _plain_text(markdown: str) -> str:
    lines: list[str] = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            lines.append(line[2:])
        elif line.startswith("## "):
            heading = line[3:]
            lines.append("CONFLICTING EVIDENCE" if heading == "Conflicting Evidence" else heading)
        else:
            lines.append(line)
    return "\n".join(lines)


def _report_id(
    result: ClassificationResult,
    mode: ReportMode,
    output_format: ReportFormat,
    language: ReportLanguage,
) -> str:
    digest = sha256(
        f"{result.result_id}|{mode}|{output_format}|{language}".encode()
    ).hexdigest()[:12]
    return f"variant-report-{digest}"
