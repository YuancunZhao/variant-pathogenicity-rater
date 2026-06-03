from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from variant_pathogenicity_rater.reporting.templates import (
    CANDIDATE_EVIDENCE_CAUTION,
    CLINVAR_CONFLICT_ALERT,
    COMPUTATIONAL_CAUTION,
    HUMAN_REVIEW_NOTE,
    MODE_TEMPLATES,
    SPLICEAI_CAUTION,
    VUS_NOTE,
    ZH_CANDIDATE_EVIDENCE_CAUTION,
    ZH_CLASSIFICATION_LABELS,
    ZH_CLINVAR_CONFLICT_ALERT,
    ZH_COMPUTATIONAL_CAUTION,
    ZH_EXTERNAL_SOURCE_CAUTION,
    ZH_HUMAN_REVIEW_NOTE,
    ZH_LITERATURE_CAUTION,
    ZH_MACHINE_PROPOSAL_NOTE,
    ZH_NOT_FINAL_ASSERTION,
    ZH_REVIEWED_EVIDENCE_CAUTION,
    ZH_SPLICEAI_CAUTION,
    ZH_VUS_NOTE,
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
from variant_pathogenicity_rater.literature_agent.schema import LiteratureAgentResult


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
    if report_language == ReportLanguage.CHINESE:
        summary.classification_label = _zh_classification_label(summary.final_classification)
        summary.human_review_note = ZH_HUMAN_REVIEW_NOTE

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


def render_literature_evidence_section(
    literature_result: LiteratureAgentResult | dict[str, Any],
) -> str:
    """Render an optional literature-agent section without touching classifier output."""

    result = (
        literature_result
        if isinstance(literature_result, LiteratureAgentResult)
        else LiteratureAgentResult.model_validate(literature_result)
    )
    lines = [
        "## Literature Evidence Assessment",
        "- Not automatically applied to ACMG classification.",
        "- This section is separate from Applied ACMG Evidence and does not change final classification wording.",
    ]
    if not result.literature_evidence_assessments:
        lines.append("- No literature evidence assessments were supplied.")
    for item in result.literature_evidence_assessments:
        lines.append(
            f"- {item.candidate_code} / {item.suggested_strength}; "
            f"type: {item.evidence_type}; confidence: {item.confidence:.2f}; "
            f"citation: {item.citation or item.pmid or item.doi or 'not provided'}"
        )
        lines.append(f"  - Why not automatically applied: {item.reason_not_applied}")
        if item.extracted_claims:
            lines.append("  - Extracted claims: " + "; ".join(item.extracted_claims))
        if item.provenance.get("extraction", {}).get("ambiguity_flags"):
            flags = item.provenance["extraction"]["ambiguity_flags"]
            lines.append("  - Ambiguity flags: " + ", ".join(flags))
    if result.review_questions:
        lines.extend(["", "### Human Review Checklist"])
        lines.extend(f"- {question}" for question in result.review_questions)
    if result.citations:
        lines.extend(["", "### Citations"])
        lines.extend(f"- {citation}" for citation in result.citations)
    if result.limitations:
        lines.extend(["", "### Literature Agent Limitations"])
        lines.extend(f"- {item}" for item in result.limitations)
    return "\n".join(lines)


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
        transcript_selection=result.transcript_selection,
        transcript_validation=result.transcript_validation,
        variant_resolution=result.variant_resolution,
        context_consistency=result.context_consistency,
        vcep_profile_context=result.vcep_profile_context,
    )


def _evidence_entry(item: EvidenceItem) -> EvidenceReportEntry:
    pvs1_decision = item.supporting_data.get("pvs1_decision") or {}
    population_decision = item.supporting_data.get("population_evidence_decision") or {}
    computational_decision = item.supporting_data.get("computational_evidence_decision") or {}
    ps1_pm5_decision = item.supporting_data.get("ps1_pm5_decision") or {}
    ps1_pm5_generation = item.supporting_data.get("evidence_generation") or {}
    reviewed = item.supporting_data.get("reviewed_evidence") or {}
    clingen_match = item.supporting_data.get("clingen_erepo_match")
    clingen_record = item.supporting_data.get("clingen_erepo_record")
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
        pvs1_decision_path=list(item.supporting_data.get("decision_path") or pvs1_decision.get("decision_path") or []),
        pvs1_downgrade_reasons=list(item.supporting_data.get("downgrade_reasons") or pvs1_decision.get("downgrade_reasons") or []),
        pvs1_blocking_reasons=list(item.supporting_data.get("blocking_reasons") or pvs1_decision.get("blocking_reasons") or []),
        population_decision_path=list(population_decision.get("decision_path") or []),
        population_thresholds=dict(population_decision.get("thresholds_used") or {}),
        population_quality_checks=list(population_decision.get("quality_checks") or []),
        population_blocking_reasons=list(population_decision.get("blocking_reasons") or []),
        computational_predictor_summary=list(item.supporting_data.get("predictor_summary") or computational_decision.get("predictor_summary") or []),
        computational_thresholds=dict(item.supporting_data.get("thresholds_used") or computational_decision.get("thresholds_used") or {}),
        computational_quality_checks=list(item.supporting_data.get("quality_checks") or computational_decision.get("quality_checks") or []),
        computational_conflict_reasons=list(item.supporting_data.get("conflict_reasons") or computational_decision.get("conflict_reasons") or []),
        computational_consensus_direction=str(item.supporting_data.get("consensus_direction") or computational_decision.get("consensus_direction") or "") or None,
        ps1_pm5_decision_path=list(ps1_pm5_generation.get("decision_path") or []),
        ps1_pm5_quality_checks=list(ps1_pm5_decision.get("quality_checks") or []),
        ps1_pm5_blocking_reasons=list(ps1_pm5_decision.get("blocking_reasons") or []),
        ps1_pm5_downgrade_reasons=list(ps1_pm5_decision.get("downgrade_reasons") or []),
        ps1_pm5_review_note=item.supporting_data.get("review_note"),
        curator_decision=item.supporting_data.get("curator_decision") or reviewed.get("curator_decision"),
        curator_name=item.supporting_data.get("curator_name") or reviewed.get("curator_name"),
        review_date=item.supporting_data.get("review_date") or reviewed.get("review_date"),
        override_reason=item.supporting_data.get("override_reason") or reviewed.get("override_reason"),
        source_candidate_evidence_id=(
            item.supporting_data.get("source_candidate_evidence_id")
            or reviewed.get("source_candidate_evidence_id")
        ),
        reviewed_evidence_status=item.supporting_data.get("evidence_status") or reviewed.get("evidence_status"),
        reviewed_provenance=item.supporting_data.get("provenance") or reviewed.get("provenance"),
        clingen_erepo_match=clingen_match if isinstance(clingen_match, dict) else None,
        clingen_erepo_record=clingen_record if isinstance(clingen_record, dict) else None,
        clingen_erepo_criteria=list(item.supporting_data.get("criteria_applied") or []),
        clingen_erepo_summaries=list(item.supporting_data.get("evidence_summaries") or []),
        vcep_override=(
            item.supporting_data.get("vcep_override")
            if isinstance(item.supporting_data.get("vcep_override"), dict)
            else None
        ),
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
    if language == ReportLanguage.CHINESE:
        cautions = _zh_cautions(result, summary)
    applied_items = [entry.model_dump(mode="json") for entry in summary.triggered_acmg_evidence]
    candidate_items = [entry.model_dump(mode="json") for entry in summary.candidate_acmg_evidence]
    context_consistency = (
        summary.context_consistency.model_dump(mode="json")
        if summary.context_consistency
        else None
    )
    transcript_selection = (
        summary.transcript_selection.model_dump(mode="json")
        if summary.transcript_selection
        else None
    )
    transcript_validation = (
        summary.transcript_validation.model_dump(mode="json")
        if summary.transcript_validation
        else None
    )
    variant_resolution = (
        summary.variant_resolution.model_dump(mode="json")
        if summary.variant_resolution
        else None
    )
    return {
        "mode": mode,
        "language": language,
        "executive_summary": _executive_summary(summary),
        "variant": {
            "variant_id": summary.variant_id,
            "gene_symbol": summary.gene_symbol,
            "transcript": summary.transcript,
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
        "why_this_classification": _why_this_classification(summary, language),
        "applied_evidence": {
            "note": _localized_text(
                language,
                "Only these ACMG evidence items were treated as applied evidence in the supplied classification result.",
                "仅此处列出的 ACMG 证据条目在 supplied classification result 中被作为已计入证据处理。",
            ),
            "items": applied_items,
        },
        "review_note_evidence": {
            "note": _localized_text(
                language,
                "Candidate/review-note evidence was not counted by the classification combiner.",
                ZH_CANDIDATE_EVIDENCE_CAUTION,
            ),
            "items": candidate_items,
        },
        "clingen_erepo": {
            "note": _localized_text(
                language,
                "ClinGen ERepo assertions are curated external review notes and were not counted as applied ACMG evidence.",
                ZH_EXTERNAL_SOURCE_CAUTION,
            ),
            "items": [
                item
                for item in candidate_items
                if item.get("source") == "ClinGen Evidence Repository"
            ],
        },
        "vcep_profile": summary.vcep_profile_context,
        "evidence": {
            "pathogenic": summary.pathogenic_evidence_summary,
            "benign": summary.benign_evidence_summary,
            "conflicting": summary.conflicting_evidence,
            "applied_items": applied_items,
            "candidate_items": candidate_items,
        },
        "context_consistency": {
            "note": _localized_text(
                language,
                "Context consistency is review context only; it is not ACMG evidence and does not change the classification.",
                "上下文一致性仅为复核信息，不是 ACMG 证据，也不会改变分类。",
            ),
            "summary": context_consistency,
        },
        "transcript_selection": {
            "note": _localized_text(
                language,
                "Transcript selection is recommendation/review-note context only; it is not ACMG evidence.",
                "转录本选择仅为推荐/复核信息，不是 ACMG 证据。",
            ),
            "summary": transcript_selection,
        },
        "transcript_validation": {
            "note": _localized_text(
                language,
                "MANE/transcript validation is review context only; it is not ACMG evidence and does not change the classification.",
                "MANE/转录本验证仅为复核信息，不是 ACMG 证据，也不会改变分类。",
            ),
            "summary": transcript_validation,
        },
        "variant_resolution": {
            "note": _localized_text(
                language,
                "Variant resolution is descriptive context only; it is not ACMG evidence and does not change the classification.",
                "变异解析仅为描述性上下文，不是 ACMG 证据，也不会改变分类。",
            ),
            "summary": variant_resolution,
        },
        "data_sources": {
            "note": _localized_text(
                language,
                "Source provenance describes where evidence or review notes came from; it does not determine whether evidence was applied.",
                "数据来源与溯源说明证据或复核线索的来源；它本身不决定证据是否已计入。",
            ),
            "items": [
                source.model_dump(mode="json") for source in summary.data_source_summary
            ],
        },
        "limitations": summary.limitations,
        "missing_data": _missing_data(summary),
        "safety_notes": cautions + [HUMAN_REVIEW_NOTE],
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
    if language == ReportLanguage.CHINESE:
        return _zh_text_content(result, summary, mode)

    template = MODE_TEMPLATES[mode]
    lines = [
        f"# {template.title}",
        "",
        template.opening_label,
        "",
        "## Executive Summary",
        f"- Final machine proposal: {summary.classification_label}",
        "- This is not a final clinical or laboratory assertion.",
        f"- Applied ACMG evidence items: {len(summary.triggered_acmg_evidence)}",
        f"- Candidate/review-note evidence items: {len(summary.candidate_acmg_evidence)}",
        f"- Human review required: true",
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
        "",
        "## Why This Classification",
        f"- Machine proposal: {summary.classification_label}",
        f"- Combination rule supplied by classifier: {summary.applied_combination_rule or 'none'}",
        "- The report does not recompute or modify the classification.",
    ]
    if summary.pathogenic_evidence_summary:
        lines.append("- Applied pathogenic evidence summary: " + "; ".join(summary.pathogenic_evidence_summary))
    if summary.benign_evidence_summary:
        lines.append("- Applied benign evidence summary: " + "; ".join(summary.benign_evidence_summary))

    lines.extend(_caution_lines(result, summary, language))
    lines.extend(_variant_resolution_lines(summary))
    lines.extend(_transcript_selection_lines(summary))
    lines.extend(_transcript_validation_lines(summary))
    lines.extend(_context_consistency_lines(summary))
    lines.extend(_clingen_erepo_section(summary))
    lines.extend(_vcep_profile_section(summary))

    lines.extend(_evidence_chain_lines(summary, include_details=template.include_evidence_table))
    lines.extend(_manual_reviewed_evidence_section(summary))
    lines.extend(_conflicting_evidence_lines(summary))

    lines.extend(["", "## Limitations"])
    if summary.limitations:
        lines.extend(f"- {item}" for item in summary.limitations)
    else:
        lines.append("- No additional limitations were supplied beyond mandatory human review.")

    lines.extend(["", "## What Data May Be Missing"])
    lines.extend(f"- {item}" for item in _missing_data(summary))

    lines.extend(_data_source_lines(summary, include_details=template.include_audit_details))

    lines.extend(["", "## Safety Notes"])
    for note in _cautions(result, summary):
        lines.append(f"- {note}")
    lines.append(f"- {HUMAN_REVIEW_NOTE}")

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


def _zh_text_content(
    result: ClassificationResult,
    summary: VariantReportSummary,
    mode: ReportMode,
) -> str:
    template = MODE_TEMPLATES[mode]
    lines = [
        "# 变异致病性机器辅助判读报告",
        "",
        "实验室内部辅助判读/人工复核报告",
        "",
        "## 报告摘要",
        f"- 最终机器辅助分类建议: {summary.classification_label}",
        f"- 原始分类值: {summary.final_classification}",
        "- 本报告不是最终临床结论，不应作为独立的临床签发或诊断依据。",
        f"- 已计入证据数量: {len(summary.triggered_acmg_evidence)}",
        f"- 候选/复核证据数量: {len(summary.candidate_acmg_evidence)}",
        "- 人工复核必需: true",
        f"- 报告模式: {template.opening_label}",
        "",
        "## 变异基本信息",
        f"- 变异: {summary.variant_id}",
        f"- 基因: {summary.gene_symbol or '未提供'}",
        f"- 转录本: {summary.transcript or '未提供'}",
        f"- HGVS c.: {summary.hgvs_c or '未提供'}",
        f"- HGVS p.: {summary.hgvs_p or '未提供'}",
        f"- 基因组位置: {summary.genomic_location}",
        "",
        "## 机器辅助分类建议",
        f"- 机器辅助分类建议: {summary.classification_label}",
        f"- 分类组合规则: {summary.applied_combination_rule or '无'}",
        f"- 置信度: {summary.confidence:.2f}",
        "- 需要人工复核: true",
        f"- {ZH_MACHINE_PROPOSAL_NOTE}",
        f"- {ZH_NOT_FINAL_ASSERTION}",
        "",
        "## 分类依据说明",
        f"- 分类器提供的机器建议: {summary.classification_label}",
        f"- 分类器提供的组合规则: {summary.applied_combination_rule or '无'}",
        "- 报告仅呈现 supplied classifier output，不重新计算或修改分类。",
    ]
    if summary.pathogenic_evidence_summary:
        lines.append("- 已计入致病方向证据摘要: " + "; ".join(summary.pathogenic_evidence_summary))
    if summary.benign_evidence_summary:
        lines.append("- 已计入良性方向证据摘要: " + "; ".join(summary.benign_evidence_summary))

    lines.extend(["", "## 安全提示"])
    for note in _zh_cautions(result, summary):
        lines.append(f"- {note}")
    lines.append(f"- {ZH_HUMAN_REVIEW_NOTE}")

    lines.extend(_zh_applied_evidence_lines(summary, include_details=template.include_evidence_table))
    lines.extend(_zh_candidate_evidence_lines(summary, include_details=template.include_evidence_table))
    lines.extend(_zh_manual_reviewed_evidence_section(summary))
    lines.extend(_zh_external_evidence_section(summary))
    lines.extend(_zh_variant_resolution_section(summary))
    lines.extend(_zh_transcript_and_mane_section(summary))
    lines.extend(_zh_vcep_section(summary))

    lines.extend(["", "## 上下文一致性"])
    consistency = summary.context_consistency
    if consistency is None:
        lines.append("- 未提供上下文一致性摘要。")
    else:
        lines.extend(
            [
                f"- 状态: {consistency.status}",
                f"- 需要人工复核: {str(consistency.review_required).lower()}",
                "- 仅为复核上下文，不是 ACMG 证据，不是分类改变，也未被分类组合器计入。",
            ]
        )
        if consistency.conflicts:
            lines.append("- 冲突:")
            lines.extend(
                f"  - {check.check_name}: expected {check.expected}; observed {check.observed}; {check.reason}"
                for check in consistency.conflicts
            )
        if consistency.warnings:
            lines.append("- 警告/上下文不足:")
            lines.extend(
                f"  - {check.check_name}: expected {check.expected}; observed {check.observed}; {check.reason}"
                for check in consistency.warnings
            )
        if consistency.limitations:
            lines.append("- 一致性局限性: " + "; ".join(consistency.limitations))

    lines.extend(["", "## 冲突证据"])
    if summary.clinvar_conflict_detected:
        lines.append(f"- {ZH_CLINVAR_CONFLICT_ALERT}")
    if summary.conflicting_evidence:
        lines.extend(f"- {item}" for item in summary.conflicting_evidence)
    if not summary.clinvar_conflict_detected and not summary.conflicting_evidence:
        lines.append("- supplied classification result 未报告冲突证据。")

    lines.extend(["", "## 数据来源与溯源"])
    if not summary.data_source_summary:
        lines.append("- 未提供证据数据来源。")
    else:
        lines.append("- 数据来源与溯源说明证据或复核线索的来源；它本身不决定证据是否已计入。")
        for source in summary.data_source_summary:
            version = f" ({source.version})" if source.version else ""
            ids = ", ".join(source.evidence_ids) if source.evidence_ids else "none"
            lines.append(f"- {source.name}{version}: evidence IDs {ids}")
            if template.include_audit_details:
                if source.retrieval_timestamp:
                    lines.append(f"  - Retrieved: {source.retrieval_timestamp}")
                if source.raw_snapshot_ref:
                    lines.append(f"  - Raw snapshot: {source.raw_snapshot_ref}")
                if source.query:
                    lines.append(f"  - Query: {_json_fragment(source.query)}")

    lines.extend(["", "## 局限性"])
    if summary.limitations:
        lines.extend(f"- {item}" for item in summary.limitations)
    else:
        lines.append("- 除强制人工复核外，未提供额外局限性。")

    lines.extend(["", "## 可能缺失的数据"])
    lines.extend(f"- {item}" for item in _missing_data(summary))

    lines.extend(
        [
            "",
            "## 人工复核清单",
            "- 复核变异标准化结果、基因、转录本、HGVS 和基因组坐标。",
            "- 逐条复核所有已计入 ACMG 证据、证据强度、方向和 supporting data。",
            "- 确认候选/复核证据未被误当作已计入证据。",
            "- 核对 ClinVar、ClinGen ERepo、文献和 reviewed evidence 的 provenance/audit trail。",
            "- 解决冲突证据、上下文不一致、转录本/MANE 问题和所有局限性。",
            "- 在签发或临床使用前，由具备资质的人员形成最终判断。",
            "",
            "## 免责声明",
            f"- {ZH_MACHINE_PROPOSAL_NOTE}",
            f"- {ZH_HUMAN_REVIEW_NOTE}",
            f"- {ZH_NOT_FINAL_ASSERTION}",
            f"- {ZH_REVIEWED_EVIDENCE_CAUTION}",
            f"- {ZH_EXTERNAL_SOURCE_CAUTION}",
            f"- {ZH_LITERATURE_CAUTION}",
        ]
    )

    if template.include_audit_details and result.audit_trail:
        lines.extend(["", "## Audit Trail"])
        lines.extend(
            f"- {event.event_type} via {event.tool_name or 'system'} at "
            f"{event.timestamp.isoformat()}"
            for event in result.audit_trail
        )

    return "\n".join(lines)


def _zh_applied_evidence_lines(
    summary: VariantReportSummary,
    *,
    include_details: bool,
) -> list[str]:
    lines = ["", "## 已计入 ACMG 证据", "- 仅此 section 列出 supplied classification result 中已计入的证据。"]
    if not summary.triggered_acmg_evidence:
        lines.append("- 未提供已计入 ACMG 证据。")
        return lines
    for entry in summary.triggered_acmg_evidence:
        lines.append(
            f"- {entry.evidence_id}: {entry.code} / {entry.strength} / "
            f"{entry.direction}; source: {entry.source}; rationale: {entry.rationale}"
        )
        if include_details:
            lines.append(f"  - Confidence: {entry.confidence:.2f}")
            lines.append(f"  - Requires review: {str(entry.requires_review).lower()}")
            lines.extend(_zh_manual_review_lines(entry))
            if entry.triggered_by:
                lines.append(f"  - Triggered by: {', '.join(entry.triggered_by)}")
            if entry.pvs1_decision_path:
                lines.append("  - PVS1 decision path: " + " | ".join(entry.pvs1_decision_path))
            if entry.population_decision_path:
                lines.append("  - Population decision path: " + " | ".join(entry.population_decision_path))
            if entry.computational_predictor_summary:
                lines.append("  - Computational consensus: " + str(entry.computational_consensus_direction or "not available"))
            if entry.ps1_pm5_decision_path:
                lines.append("  - PS1/PM5 decision path: " + " | ".join(entry.ps1_pm5_decision_path))
            if entry.vcep_override:
                lines.append("  - VCEP override: " + _vcep_override_fragment(entry.vcep_override))
    return lines


def _zh_candidate_evidence_lines(
    summary: VariantReportSummary,
    *,
    include_details: bool,
) -> list[str]:
    lines = ["", "## 候选/复核证据", f"- {ZH_CANDIDATE_EVIDENCE_CAUTION}"]
    if not summary.candidate_acmg_evidence:
        lines.append("- 未提供候选/复核证据。")
        return lines
    for entry in summary.candidate_acmg_evidence:
        lines.append(
            f"- {entry.evidence_id}: {entry.code} / {entry.strength} / "
            f"{entry.direction}; status: 候选/复核证据，未计入分类组合器; "
            f"source: {entry.source}; rationale: {entry.rationale}"
        )
        if include_details:
            lines.append(f"  - Confidence: {entry.confidence:.2f}")
            lines.append("  - Status: candidate/review-note only; not used in classification")
            lines.extend(_zh_manual_review_lines(entry))
            if entry.citation:
                lines.append(f"  - Citation: {entry.citation}")
            if entry.provenance:
                lines.append("  - Provenance: " + _json_fragment(entry.provenance))
            if entry.review_flags:
                lines.append("  - Review flags: " + ", ".join(flag.code for flag in entry.review_flags))
            if entry.pvs1_blocking_reasons:
                lines.append("  - PVS1 blocking reasons: " + "; ".join(entry.pvs1_blocking_reasons))
            if entry.population_blocking_reasons:
                lines.append("  - Population blocking reasons: " + "; ".join(entry.population_blocking_reasons))
            if entry.computational_conflict_reasons:
                lines.append("  - Computational conflicts: " + "; ".join(entry.computational_conflict_reasons))
            if entry.ps1_pm5_review_note:
                lines.append("  - PS1/PM5 review note: " + entry.ps1_pm5_review_note)
            if entry.ps1_pm5_blocking_reasons:
                lines.append("  - PS1/PM5 blocking reasons: " + "; ".join(entry.ps1_pm5_blocking_reasons))
            if entry.vcep_override:
                lines.append("  - VCEP override: " + _vcep_override_fragment(entry.vcep_override))
    return lines


def _zh_manual_review_lines(entry: EvidenceReportEntry) -> list[str]:
    if entry.source != "manual_reviewed_evidence" and not entry.curator_decision:
        return []
    lines = ["  - Manual reviewed evidence: true"]
    if entry.reviewed_evidence_status:
        lines.append(f"  - Reviewed evidence status: {entry.reviewed_evidence_status}")
    if entry.curator_decision:
        lines.append(f"  - Curator decision: {entry.curator_decision}")
    if entry.curator_name:
        lines.append(f"  - Curator: {entry.curator_name}")
    if entry.review_date:
        lines.append(f"  - Review date: {entry.review_date}")
    if entry.source_candidate_evidence_id:
        lines.append(f"  - Source candidate evidence ID: {entry.source_candidate_evidence_id}")
    if entry.override_reason:
        lines.append(f"  - Override reason: {entry.override_reason}")
    if entry.reviewed_provenance:
        lines.append("  - Provenance: " + _json_fragment(entry.reviewed_provenance))
    return lines


def _zh_manual_reviewed_evidence_section(summary: VariantReportSummary) -> list[str]:
    entries = [*summary.triggered_acmg_evidence, *summary.candidate_acmg_evidence]
    reviewed_entries = [
        entry
        for entry in entries
        if entry.source == "manual_reviewed_evidence" or entry.curator_decision
    ]
    lines = [
        "",
        "## 人工审核证据",
        f"- {ZH_REVIEWED_EVIDENCE_CAUTION}",
    ]
    if not reviewed_entries:
        lines.append("- 未提供人工审核证据记录。")
        return lines
    for entry in reviewed_entries:
        lines.append(
            f"- {entry.evidence_id}: {entry.code} / {entry.reviewed_evidence_status or 'reviewed'}; "
            f"rationale: {entry.rationale}"
        )
        lines.extend(_zh_manual_review_lines(entry))
    return lines


def _zh_external_evidence_section(summary: VariantReportSummary) -> list[str]:
    external_sources = {"ClinVar", "ClinGen Evidence Repository", "Literature"}
    entries = [
        entry
        for entry in [*summary.triggered_acmg_evidence, *summary.candidate_acmg_evidence]
        if entry.source in external_sources
    ]
    lines = [
        "",
        "## ClinVar / ClinGen ERepo / 文献证据",
        f"- {ZH_EXTERNAL_SOURCE_CAUTION}",
        f"- {ZH_LITERATURE_CAUTION}",
    ]
    if not entries:
        lines.append("- 未提供 ClinVar、ClinGen ERepo 或文献证据条目。")
        return lines
    for entry in entries:
        status = "已计入" if entry in summary.triggered_acmg_evidence else "候选/复核，未计入"
        lines.append(
            f"- {entry.evidence_id}: source={entry.source}; status={status}; "
            f"code={entry.code}; rationale: {entry.rationale}"
        )
        if entry.citation:
            lines.append(f"  - Citation: {entry.citation}")
        if entry.provenance:
            lines.append("  - Provenance: " + _json_fragment(entry.provenance))
        if entry.clingen_erepo_record:
            lines.append("  - ClinGen ERepo record: " + _json_fragment(entry.clingen_erepo_record))
        if entry.clingen_erepo_match:
            lines.append("  - ClinGen ERepo match: " + _json_fragment(entry.clingen_erepo_match))
    return lines


def _zh_variant_resolution_section(summary: VariantReportSummary) -> list[str]:
    lines = [
        "",
        "## 变异解析摘要",
        "- 变异解析仅为描述性上下文，不是 ACMG 证据，不会改变分类组合器输出。",
    ]
    resolution = summary.variant_resolution
    if resolution is None:
        lines.append("- 未提供变异解析摘要。")
        return lines
    transcript = resolution.resolved_transcript
    protein = resolution.resolved_hgvs_p
    coordinate = resolution.resolved_coordinate
    exon = resolution.exon_context
    nmd = resolution.nmd_context
    lines.extend(
        [
            f"- 状态: {resolution.status}",
            f"- 置信度: {resolution.confidence:.2f}",
            f"- Transcript: {(transcript.transcript if transcript else None) or '未解析'}",
            f"- Protein consequence: {(protein.hgvs_p if protein else None) or '未解析'}",
            "- Coordinate: "
            + (
                f"{coordinate.genome_build}:{coordinate.chrom}:{coordinate.pos}:{coordinate.ref}>{coordinate.alt}"
                if coordinate and coordinate.chrom and coordinate.pos
                else "未解析"
            ),
            "- Exon: "
            + (
                f"{exon.exon_number}/{exon.total_exons}"
                if exon and exon.exon_number and exon.total_exons
                else "未解析"
            ),
            f"- NMD: {(nmd.status if nmd else 'unknown')}",
        ]
    )
    if resolution.limitations:
        lines.append("- 局限性: " + "; ".join(resolution.limitations))
    if resolution.review_flags:
        lines.append("- Review flags: " + ", ".join(flag.code for flag in resolution.review_flags))
    return lines


def _zh_transcript_and_mane_section(summary: VariantReportSummary) -> list[str]:
    lines = [
        "",
        "## 转录本 / MANE 验证",
        "- 转录本选择和 MANE/转录本验证仅为复核上下文，不是 ACMG 证据，也不会改变分类。",
    ]
    selection = summary.transcript_selection
    if selection is None:
        lines.append("- 未提供转录本选择摘要。")
    else:
        lines.extend(
            [
                f"- 推荐转录本: {selection.selected_transcript or 'none'}",
                f"- 基因: {selection.selected_gene or '未提供'}",
                f"- 原因: {selection.selection_reason}",
                f"- 置信度: {selection.selection_confidence:.2f}",
            ]
        )
    validation = summary.transcript_validation
    if validation is None:
        lines.append("- 未提供 MANE/转录本验证摘要。")
    else:
        matched = validation.matched_record or {}
        lines.extend(
            [
                f"- 验证状态: {validation.status}",
                f"- 输入转录本: {validation.input_transcript or '未提供'}",
                f"- 匹配转录本: {matched.get('transcript') or 'none'}",
                f"- MANE Select candidates: {len(validation.mane_select_candidates)}",
                f"- Canonical candidates: {len(validation.canonical_candidates)}",
            ]
        )
        if matched:
            lines.append(
                "- Matched transcript provenance: "
                f"source={matched.get('transcript_source') or 'not provided'}; "
                f"version={matched.get('source_version') or 'not provided'}; "
                f"build={matched.get('genome_build') or 'not provided'}"
            )
        if validation.limitations:
            lines.append("- 转录本验证局限性: " + "; ".join(validation.limitations))
    return lines


def _zh_vcep_section(summary: VariantReportSummary) -> list[str]:
    lines = [
        "",
        "## VCEP / 特殊规则提示",
        "- VCEP profile signals 为复核上下文；signal presence alone 未被计入 ACMG 证据，也未改变分类。",
    ]
    payload = summary.vcep_profile_context
    if not payload:
        lines.append("- 未提供 VCEP profile context。")
        return lines
    matches = payload.get("matches") or []
    if not matches:
        lines.append("- 未识别到匹配的 VCEP profile。")
    for match in matches:
        profile = match.get("profile") or {}
        lines.append(
            f"- {profile.get('profile_id') or 'profile'}: {profile.get('vcep_name') or 'VCEP not provided'}; "
            f"status={profile.get('status') or 'not provided'}; "
            f"version={profile.get('version') or 'not provided'}; "
            f"match_level={match.get('match_level') or 'not provided'}"
        )
        if profile.get("source"):
            lines.append(f"  - Source: {profile['source']}")
        if profile.get("citations"):
            lines.append("  - Citations: " + ", ".join(str(item) for item in profile["citations"]))
        if match.get("override_blocking_reasons"):
            lines.append("  - Override blocking reasons: " + "; ".join(str(item) for item in match["override_blocking_reasons"]))
    override = payload.get("override_context") or {}
    if override:
        lines.append(f"- Overrides explicitly enabled: {str(override.get('override_enabled', False)).lower()}")
        lines.append(f"- Overrides applied: {str(override.get('override_applied', False)).lower()}")
        if override.get("disabled_criteria"):
            lines.append("- Disabled criteria: " + ", ".join(str(item) for item in override["disabled_criteria"]))
    if payload.get("limitations"):
        lines.append("- VCEP 局限性: " + "; ".join(str(item) for item in payload["limitations"]))
    return lines


def _evidence_chain_lines(
    summary: VariantReportSummary,
    *,
    include_details: bool,
) -> list[str]:
    lines = ["", "## Applied ACMG Evidence", "- Only this section lists evidence counted by the supplied classification result."]
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
                lines.extend(_manual_review_lines(entry))
                if entry.triggered_by:
                    lines.append(f"  - Triggered by: {', '.join(entry.triggered_by)}")
                if entry.pvs1_decision_path:
                    lines.append("  - PVS1 decision path: " + " | ".join(entry.pvs1_decision_path))
                if entry.pvs1_downgrade_reasons:
                    lines.append("  - PVS1 downgrade reasons: " + "; ".join(entry.pvs1_downgrade_reasons))
                if entry.population_decision_path:
                    lines.append("  - Population decision path: " + " | ".join(entry.population_decision_path))
                if entry.population_thresholds:
                    lines.append("  - Population thresholds: " + _json_fragment(entry.population_thresholds))
                if entry.population_quality_checks:
                    lines.append("  - Population quality checks: " + _population_quality_fragment(entry.population_quality_checks))
                if entry.computational_predictor_summary:
                    lines.append("  - Computational consensus: " + str(entry.computational_consensus_direction or "not available"))
                    lines.append("  - Computational predictors: " + _computational_predictor_fragment(entry.computational_predictor_summary))
                if entry.computational_thresholds:
                    lines.append("  - Computational thresholds: " + _json_fragment(entry.computational_thresholds))
                if entry.computational_quality_checks:
                    lines.append("  - Computational quality checks: " + _population_quality_fragment(entry.computational_quality_checks))
                if entry.computational_conflict_reasons:
                    lines.append("  - Computational conflicts: " + "; ".join(entry.computational_conflict_reasons))
                if entry.ps1_pm5_review_note:
                    lines.append("  - PS1/PM5 review note: " + entry.ps1_pm5_review_note)
                if entry.ps1_pm5_decision_path:
                    lines.append("  - PS1/PM5 decision path: " + " | ".join(entry.ps1_pm5_decision_path))
                if entry.ps1_pm5_quality_checks:
                    lines.append("  - PS1/PM5 quality checks: " + _population_quality_fragment(entry.ps1_pm5_quality_checks))
                if entry.ps1_pm5_downgrade_reasons:
                    lines.append("  - PS1/PM5 downgrade reasons: " + "; ".join(entry.ps1_pm5_downgrade_reasons))
                if entry.ps1_pm5_blocking_reasons:
                    lines.append("  - PS1/PM5 blocking reasons: " + "; ".join(entry.ps1_pm5_blocking_reasons))
                if entry.vcep_override:
                    lines.append("  - VCEP override: " + _vcep_override_fragment(entry.vcep_override))
    lines.extend(["", "## Candidate / Review-Note Evidence", f"- {CANDIDATE_EVIDENCE_CAUTION}"])
    if not summary.candidate_acmg_evidence:
        lines.append("- No candidate-only ACMG evidence items were supplied.")
        return lines

    for entry in summary.candidate_acmg_evidence:
        lines.append(
            f"- {entry.evidence_id}: {entry.code} / {entry.strength} / "
            f"{entry.direction}; status: candidate/review-note only; source: {entry.source}; "
            f"rationale: {entry.rationale}"
        )
        if include_details:
            lines.append(f"  - Confidence: {entry.confidence:.2f}")
            lines.append("  - Status: candidate/review-note only; not used in classification")
            lines.extend(_manual_review_lines(entry))
            if entry.citation:
                lines.append(f"  - Citation: {entry.citation}")
            if entry.provenance:
                lines.append("  - Provenance: retained on evidence source")
            if entry.pvs1_decision_path:
                lines.append("  - PVS1 decision path: " + " | ".join(entry.pvs1_decision_path))
            if entry.pvs1_downgrade_reasons:
                lines.append("  - PVS1 downgrade reasons: " + "; ".join(entry.pvs1_downgrade_reasons))
            if entry.pvs1_blocking_reasons:
                lines.append("  - PVS1 blocking reasons: " + "; ".join(entry.pvs1_blocking_reasons))
            if entry.population_decision_path:
                lines.append("  - Population decision path: " + " | ".join(entry.population_decision_path))
            if entry.population_thresholds:
                lines.append("  - Population thresholds: " + _json_fragment(entry.population_thresholds))
            if entry.population_quality_checks:
                lines.append("  - Population quality checks: " + _population_quality_fragment(entry.population_quality_checks))
            if entry.population_blocking_reasons:
                lines.append("  - Population blocking reasons: " + "; ".join(entry.population_blocking_reasons))
            if entry.computational_predictor_summary:
                lines.append("  - Computational consensus: " + str(entry.computational_consensus_direction or "not available"))
                lines.append("  - Computational predictors: " + _computational_predictor_fragment(entry.computational_predictor_summary))
            if entry.computational_thresholds:
                lines.append("  - Computational thresholds: " + _json_fragment(entry.computational_thresholds))
            if entry.computational_quality_checks:
                lines.append("  - Computational quality checks: " + _population_quality_fragment(entry.computational_quality_checks))
            if entry.computational_conflict_reasons:
                lines.append("  - Computational conflicts: " + "; ".join(entry.computational_conflict_reasons))
            if entry.ps1_pm5_review_note:
                lines.append("  - PS1/PM5 review note: " + entry.ps1_pm5_review_note)
            if entry.ps1_pm5_decision_path:
                lines.append("  - PS1/PM5 decision path: " + " | ".join(entry.ps1_pm5_decision_path))
            if entry.ps1_pm5_quality_checks:
                lines.append("  - PS1/PM5 quality checks: " + _population_quality_fragment(entry.ps1_pm5_quality_checks))
            if entry.ps1_pm5_downgrade_reasons:
                lines.append("  - PS1/PM5 downgrade reasons: " + "; ".join(entry.ps1_pm5_downgrade_reasons))
            if entry.ps1_pm5_blocking_reasons:
                lines.append("  - PS1/PM5 blocking reasons: " + "; ".join(entry.ps1_pm5_blocking_reasons))
            if entry.vcep_override:
                lines.append("  - VCEP override: " + _vcep_override_fragment(entry.vcep_override))
    return lines


def _vcep_profile_section(summary: VariantReportSummary) -> list[str]:
    payload = summary.vcep_profile_context
    if not payload:
        return []
    lines = [
        "",
        "## VCEP Signal / Rule Profile",
        "- VCEP profile signals are review context only. Signal presence alone was not counted as ACMG evidence and did not change the classification.",
    ]
    matches = payload.get("matches") or []
    if not matches:
        lines.append("- No matching VCEP profile was identified.")
    for match in matches:
        profile = match.get("profile") or {}
        lines.append(
            f"- {profile.get('profile_id') or 'profile'}: {profile.get('vcep_name') or 'VCEP not provided'}; "
            f"status: {profile.get('status') or 'not provided'}; "
            f"version: {profile.get('version') or 'not provided'}; "
            f"match level: {match.get('match_level') or 'not provided'}"
        )
        if profile.get("source"):
            lines.append(f"  - Source: {profile['source']}")
        if profile.get("citations"):
            lines.append("  - Citations: " + ", ".join(str(item) for item in profile["citations"]))
        if match.get("override_blocking_reasons"):
            lines.append("  - Override blocking reasons: " + "; ".join(str(item) for item in match["override_blocking_reasons"]))
    override = payload.get("override_context") or {}
    if override:
        lines.append(f"- Overrides explicitly enabled: {str(override.get('override_enabled', False)).lower()}")
        lines.append(f"- Overrides applied: {str(override.get('override_applied', False)).lower()}")
        if override.get("blocked_reasons"):
            lines.append("- Blocked override reasons: " + "; ".join(str(item) for item in override["blocked_reasons"]))
        active = override.get("active_profile") or {}
        if active:
            lines.append(f"- Active profile: {active.get('profile_id')} / {active.get('version')}")
        if override.get("disabled_criteria"):
            lines.append("- Disabled criteria: " + ", ".join(str(item) for item in override["disabled_criteria"]))
    if payload.get("limitations"):
        lines.append("- Limitations: " + "; ".join(str(item) for item in payload["limitations"]))
    return lines


def _clingen_erepo_section(summary: VariantReportSummary) -> list[str]:
    entries = [
        entry for entry in summary.candidate_acmg_evidence if entry.source == "ClinGen Evidence Repository"
    ]
    if not entries:
        return []
    lines = [
        "",
        "## ClinGen Evidence Repository Match",
        "- ClinGen ERepo results are curated external assertions for review only; they were not automatically applied and were not counted as applied ACMG evidence.",
    ]
    for entry in entries:
        record = entry.clingen_erepo_record or {}
        match = entry.clingen_erepo_match or {}
        lines.append(
            f"- {record.get('record_id') or entry.evidence_id}: "
            f"{record.get('classification') or 'classification not provided'}; "
            f"match level: {match.get('match_level') or 'not provided'}; "
            f"confidence: {entry.confidence:.2f}"
        )
        lines.append(f"  - VCEP: {record.get('vcep_name') or 'not provided'}")
        lines.append(f"  - Condition: {record.get('disease_condition') or 'not provided'}")
        lines.append(
            f"  - Classification date/version: "
            f"{record.get('classification_date') or 'not provided'} / "
            f"{record.get('classification_version') or 'not provided'}"
        )
        if entry.clingen_erepo_criteria:
            criteria = [
                str(item.get("criterion") or item.get("code") or item)
                for item in entry.clingen_erepo_criteria
            ]
            lines.append("  - VCEP criteria summary: " + ", ".join(criteria))
        if entry.clingen_erepo_summaries:
            summaries = [
                str(item.get("summary_text") or item.get("summary") or item)
                for item in entry.clingen_erepo_summaries
            ]
            lines.append("  - Supporting summary: " + "; ".join(summaries))
        citations = record.get("citations") or []
        if citations:
            lines.append("  - Citations: " + ", ".join(str(item) for item in citations))
        if record.get("source_url"):
            lines.append(f"  - Source URL: {record['source_url']}")
        if entry.limitations:
            lines.append("  - Limitations: " + "; ".join(entry.limitations))
    return lines


def _manual_review_lines(entry: EvidenceReportEntry) -> list[str]:
    if entry.source != "manual_reviewed_evidence" and not entry.curator_decision:
        return []
    lines = ["  - Manual reviewed evidence: true"]
    if entry.reviewed_evidence_status:
        lines.append(f"  - Reviewed evidence status: {entry.reviewed_evidence_status}")
    if entry.curator_decision:
        lines.append(f"  - Curator decision: {entry.curator_decision}")
    if entry.curator_name:
        lines.append(f"  - Curator: {entry.curator_name}")
    if entry.review_date:
        lines.append(f"  - Review date: {entry.review_date}")
    if entry.source_candidate_evidence_id:
        lines.append(f"  - Source candidate evidence ID: {entry.source_candidate_evidence_id}")
    if entry.override_reason:
        lines.append(f"  - Override reason: {entry.override_reason}")
    return lines


def _manual_reviewed_evidence_section(summary: VariantReportSummary) -> list[str]:
    entries = [
        *summary.triggered_acmg_evidence,
        *summary.candidate_acmg_evidence,
    ]
    reviewed_entries = [
        entry
        for entry in entries
        if entry.source == "manual_reviewed_evidence" or entry.curator_decision
    ]
    if not reviewed_entries:
        return []
    lines = [
        "",
        "## Manual Reviewed Evidence",
        "- These records reflect explicit curator decisions; rejected and needs-more-info records are not counted by the classification combiner.",
    ]
    for entry in reviewed_entries:
        lines.append(
            f"- {entry.evidence_id}: {entry.code} / {entry.reviewed_evidence_status or 'reviewed'}; "
            f"rationale: {entry.rationale}"
        )
        if entry.curator_decision:
            lines.append(f"  - Curator decision: {entry.curator_decision}")
        if entry.curator_name:
            lines.append(f"  - Curator: {entry.curator_name}")
        if entry.review_date:
            lines.append(f"  - Review date: {entry.review_date}")
        if entry.source_candidate_evidence_id:
            lines.append(f"  - Source candidate evidence ID: {entry.source_candidate_evidence_id}")
        if entry.override_reason:
            lines.append(f"  - Override reason: {entry.override_reason}")
    return lines


def _variant_resolution_lines(summary: VariantReportSummary) -> list[str]:
    lines = [
        "",
        "## Variant Resolution Summary",
        "- Variant resolution is descriptive context only; it is not ACMG evidence and was not counted by the classification combiner.",
    ]
    resolution = summary.variant_resolution
    if resolution is None:
        lines.append("- No variant resolution summary was supplied.")
        return lines
    transcript = resolution.resolved_transcript
    protein = resolution.resolved_hgvs_p
    coordinate = resolution.resolved_coordinate
    exon = resolution.exon_context
    nmd = resolution.nmd_context
    lines.extend(
        [
            f"- Status: {resolution.status}",
            f"- Confidence: {resolution.confidence:.2f}",
            f"- Transcript: {(transcript.transcript if transcript else None) or 'unresolved'}",
            f"- Transcript source: {(transcript.transcript_source if transcript else None) or 'unknown'}",
            f"- Protein consequence: {(protein.hgvs_p if protein else None) or 'unresolved'}",
            "- Coordinate: "
            + (
                f"{coordinate.genome_build}:{coordinate.chrom}:{coordinate.pos}:{coordinate.ref}>{coordinate.alt}"
                if coordinate and coordinate.chrom and coordinate.pos
                else "unresolved"
            ),
            "- Exon: "
            + (
                f"{exon.exon_number}/{exon.total_exons}"
                if exon and exon.exon_number and exon.total_exons
                else "unresolved"
            ),
            f"- NMD: {(nmd.status if nmd else 'unknown')}",
        ]
    )
    if resolution.limitations:
        lines.append("- Resolution limitations: " + "; ".join(resolution.limitations))
    if resolution.review_flags:
        lines.append("- Review flags: " + ", ".join(flag.code for flag in resolution.review_flags))
    return lines


def _transcript_selection_lines(summary: VariantReportSummary) -> list[str]:
    lines = ["", "## Transcript Selection"]
    selection = summary.transcript_selection
    if selection is None:
        lines.append("- No transcript selection summary was supplied.")
        return lines

    lines.extend(
        [
            f"- Recommended transcript: {selection.selected_transcript or 'none'}",
            f"- Gene: {selection.selected_gene or 'not provided'}",
            f"- Reason: {selection.selection_reason}",
            f"- Confidence: {selection.selection_confidence:.2f}",
            "- Status: recommendation/review-note only; not ACMG evidence and not counted by the classification combiner",
            "- Human review required: true",
        ]
    )
    if selection.review_flags:
        lines.append(
            "- Review flags: "
            + ", ".join(flag.code for flag in selection.review_flags)
        )
    if selection.limitations:
        lines.append("- Selection limitations: " + "; ".join(selection.limitations))
    return lines


def _transcript_validation_lines(summary: VariantReportSummary) -> list[str]:
    lines = ["", "## Transcript Selection / MANE Validation"]
    validation = summary.transcript_validation
    if validation is None:
        lines.append("- No MANE/transcript validation summary was supplied.")
        return lines

    matched = validation.matched_record or {}
    lines.extend(
        [
            f"- Status: {validation.status}",
            f"- User/input transcript: {validation.input_transcript or 'not provided'}",
            f"- Matched transcript: {matched.get('transcript') or 'none'}",
            f"- MANE Select candidates: {len(validation.mane_select_candidates)}",
            f"- Canonical candidates: {len(validation.canonical_candidates)}",
            f"- Protein accession expected/observed: {validation.protein_accession_expected or 'not provided'} / {validation.protein_accession_observed or 'not provided'}",
            "- Status: review context only; not ACMG evidence and not counted by the classification combiner",
            "- User transcript preserved: true",
        ]
    )
    if matched:
        lines.append(
            "- Matched transcript provenance: "
            f"source={matched.get('transcript_source') or 'not provided'}; "
            f"version={matched.get('source_version') or 'not provided'}; "
            f"build={matched.get('genome_build') or 'not provided'}; "
            f"status={matched.get('transcript_status') or 'not provided'}"
        )
    if validation.review_flags:
        lines.append(
            "- Review flags: "
            + ", ".join(flag.code for flag in validation.review_flags)
        )
    if validation.limitations:
        lines.append("- Transcript validation limitations: " + "; ".join(validation.limitations))
    return lines


def _context_consistency_lines(summary: VariantReportSummary) -> list[str]:
    lines = ["", "## Context Consistency"]
    consistency = summary.context_consistency
    if consistency is None:
        lines.append("- No context consistency summary was supplied.")
        return lines

    lines.extend(
        [
            f"- Status: {consistency.status}",
            f"- Human review required: {str(consistency.review_required).lower()}",
            "- Review context only; not ACMG evidence, not a classification change, and not used by the classification combiner.",
        ]
    )
    if consistency.conflicts:
        lines.append("- Conflicts:")
        lines.extend(
            f"  - {check.check_name}: expected {check.expected}; observed {check.observed}; {check.reason}"
            for check in consistency.conflicts
        )
    if consistency.warnings:
        lines.append("- Warnings/insufficient context:")
        lines.extend(
            f"  - {check.check_name}: expected {check.expected}; observed {check.observed}; {check.reason}"
            for check in consistency.warnings
        )
    if consistency.limitations:
        lines.append("- Consistency limitations: " + "; ".join(consistency.limitations))
    return lines


def _conflicting_evidence_lines(summary: VariantReportSummary) -> list[str]:
    lines = ["", "## Conflicting Evidence"]
    if summary.clinvar_conflict_detected:
        lines.append(f"- {CLINVAR_CONFLICT_ALERT}")
    if summary.conflicting_evidence:
        lines.extend(f"- {item}" for item in summary.conflicting_evidence)
    conflict_flags = [
        flag for flag in summary.review_flags if "CONFLICT" in flag.code.upper()
    ]
    if conflict_flags:
        lines.append("- Review flags:")
        lines.extend(f"  - {flag.code}: {flag.message}" for flag in conflict_flags)
    elif not summary.clinvar_conflict_detected and not summary.conflicting_evidence:
        lines.append("- No conflicting evidence was reported in the supplied classification result.")
    return lines


def _data_source_lines(
    summary: VariantReportSummary,
    *,
    include_details: bool,
) -> list[str]:
    lines = ["", "## Data Sources / Provenance"]
    if not summary.data_source_summary:
        lines.append("- No evidence data sources were supplied.")
        return lines
    lines.append("- Provenance describes source origin and retrieval context; it does not mean a source was applied as ACMG evidence.")

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
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)


def _vcep_override_fragment(value: dict[str, Any]) -> str:
    profile = value.get("profile") or {}
    notes = value.get("notes") or []
    parts = [
        f"profile={profile.get('profile_id') or 'not provided'}",
        f"version={profile.get('version') or 'not provided'}",
        f"applied_to_item={str(value.get('override_applied_to_item', False)).lower()}",
    ]
    if notes:
        parts.append("notes=" + "; ".join(str(item) for item in notes))
    return "; ".join(parts)


def _population_quality_fragment(checks: list[dict[str, Any]]) -> str:
    return "; ".join(
        f"{check.get('name')}={'pass' if check.get('passed') else 'fail'}"
        for check in checks
    )


def _computational_predictor_fragment(calls: list[dict[str, Any]]) -> str:
    fragments = []
    for call in calls:
        score = call.get("score")
        score_text = "" if score is None else f" ({score})"
        fragments.append(f"{call.get('method')}={call.get('direction')}{score_text}")
    return "; ".join(fragments)


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
    return lines


def _cautions(result: ClassificationResult, summary: VariantReportSummary) -> list[str]:
    cautions: list[str] = []
    if summary.final_classification == "vus":
        cautions.append(VUS_NOTE)
    if any(str(item.code) in {"PP3", "BP4"} for item in result.evidence_items):
        cautions.append(COMPUTATIONAL_CAUTION)
    if any("spliceai" in trigger.lower() for item in result.evidence_items for trigger in item.triggered_by):
        cautions.append(SPLICEAI_CAUTION)
    if summary.candidate_acmg_evidence:
        cautions.append(CANDIDATE_EVIDENCE_CAUTION)
    if summary.clinvar_conflict_detected:
        cautions.append(CLINVAR_CONFLICT_ALERT)
    return cautions


def _zh_cautions(result: ClassificationResult, summary: VariantReportSummary) -> list[str]:
    cautions: list[str] = [ZH_MACHINE_PROPOSAL_NOTE, ZH_NOT_FINAL_ASSERTION]
    if summary.final_classification == "vus":
        cautions.append(ZH_VUS_NOTE)
    if any(str(item.code) in {"PP3", "BP4"} for item in result.evidence_items):
        cautions.append(ZH_COMPUTATIONAL_CAUTION)
    if any("spliceai" in trigger.lower() for item in result.evidence_items for trigger in item.triggered_by):
        cautions.append(ZH_SPLICEAI_CAUTION)
    if summary.candidate_acmg_evidence:
        cautions.append(ZH_CANDIDATE_EVIDENCE_CAUTION)
    if summary.clinvar_conflict_detected:
        cautions.append(ZH_CLINVAR_CONFLICT_ALERT)
    cautions.extend([ZH_REVIEWED_EVIDENCE_CAUTION, ZH_EXTERNAL_SOURCE_CAUTION, ZH_LITERATURE_CAUTION])
    return list(dict.fromkeys(cautions))


def _executive_summary(summary: VariantReportSummary) -> dict[str, Any]:
    return {
        "final_machine_proposal": summary.final_classification,
        "classification_label": summary.classification_label,
        "human_review_required": True,
        "applied_evidence_count": len(summary.triggered_acmg_evidence),
        "candidate_review_note_count": len(summary.candidate_acmg_evidence),
        "context_consistency_status": (
            summary.context_consistency.status if summary.context_consistency else None
        ),
        "clinvar_conflict_detected": summary.clinvar_conflict_detected,
    }


def _why_this_classification(
    summary: VariantReportSummary,
    language: ReportLanguage = ReportLanguage.ENGLISH,
) -> list[str]:
    if language == ReportLanguage.CHINESE:
        lines = [
            f"最终机器辅助分类建议: {summary.classification_label}。",
            f"已应用组合规则: {summary.applied_combination_rule or '无'}。",
            "报告仅呈现 supplied classifier output，不改变最终分类。",
        ]
        if summary.pathogenic_evidence_summary:
            lines.append("已计入致病方向证据: " + "; ".join(summary.pathogenic_evidence_summary))
        if summary.benign_evidence_summary:
            lines.append("已计入良性方向证据: " + "; ".join(summary.benign_evidence_summary))
        return lines
    lines = [
        f"Final machine proposal: {summary.classification_label}.",
        f"Applied combination rule: {summary.applied_combination_rule or 'none'}.",
        "The report presents the supplied classifier output without changing the final classification.",
    ]
    if summary.pathogenic_evidence_summary:
        lines.append("Applied pathogenic evidence: " + "; ".join(summary.pathogenic_evidence_summary))
    if summary.benign_evidence_summary:
        lines.append("Applied benign evidence: " + "; ".join(summary.benign_evidence_summary))
    return lines


def _localized_text(language: ReportLanguage, english: str, chinese: str) -> str:
    return chinese if language == ReportLanguage.CHINESE else english


def _zh_classification_label(value: str) -> str:
    return ZH_CLASSIFICATION_LABELS.get(value, value)


def _missing_data(summary: VariantReportSummary) -> list[str]:
    missing: list[str] = []
    if not summary.transcript:
        missing.append("No transcript was supplied in the variant summary.")
    if not summary.transcript_selection:
        missing.append("No transcript selection summary was supplied.")
    if not summary.context_consistency:
        missing.append("No context consistency summary was supplied.")
    if not summary.data_source_summary:
        missing.append("No evidence data source provenance was supplied.")
    if not summary.limitations:
        missing.append("No source-specific limitations were supplied beyond mandatory human review.")
    return missing or ["No additional missing-data notes were generated by the report renderer."]


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
        item.candidate_only
        or item.applied is False
        or str(item.strength) == EvidenceStrength.NONE.value
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
