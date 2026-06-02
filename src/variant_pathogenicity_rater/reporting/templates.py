from __future__ import annotations

from dataclasses import dataclass

from variant_pathogenicity_rater.schemas.report import ReportMode


HUMAN_REVIEW_NOTE = (
    "This report is machine-generated and is not a final clinical assertion. "
    "A qualified human reviewer must verify the variant, evidence, ACMG criteria, "
    "limitations, and final classification before clinical or laboratory use."
)

ZH_HUMAN_REVIEW_NOTE = (
    "本报告为机器生成的辅助判读材料，不是最终临床结论。"
    "具备资质的人员必须在临床或实验室使用前复核变异、证据、ACMG 标准、"
    "局限性和分类建议。"
)

VUS_NOTE = (
    "The available evidence is insufficient to support a pathogenic or benign "
    "classification. The variant should be treated as a Variant of Uncertain "
    "Significance unless and until additional reviewed evidence becomes available."
)

ZH_VUS_NOTE = (
    "意义未明表示现有证据不足以支持致病或良性分类；不得使用偏向致病或偏向良性的措辞，"
    "除非后续人工审核证据支持重新分类。"
)

COMPUTATIONAL_CAUTION = (
    "Computational evidence is supporting evidence only and must not be treated "
    "as determinative without independent clinical, functional, segregation, or "
    "population evidence as applicable."
)

ZH_COMPUTATIONAL_CAUTION = (
    "计算预测证据仅为支持性证据；在适用场景下，不能脱离独立的临床、功能、"
    "家系或群体证据而作为决定性依据。"
)

SPLICEAI_CAUTION = (
    "SpliceAI is computational splice prediction only. It is not functional "
    "evidence and does not by itself apply PS3, BS3, or PVS1."
)

ZH_SPLICEAI_CAUTION = (
    "SpliceAI 仅为计算剪接预测，不是功能实验/RNA 验证证据，不能单独支持 "
    "PS3、BS3 或 PVS1。"
)

CLINVAR_CONFLICT_ALERT = (
    "ClinVar conflict detected: conflicting external assertions require prominent "
    "manual review and should not be resolved by this report alone."
)

ZH_CLINVAR_CONFLICT_ALERT = (
    "检测到 ClinVar 冲突：外部解释存在冲突，必须进行人工复核，不能仅由本报告解决。"
)

CANDIDATE_EVIDENCE_CAUTION = (
    "Candidate/review-note evidence is listed for manual evaluation only. It was "
    "not counted by the classification combiner unless it also appears under "
    "Applied ACMG Evidence."
)

ZH_CANDIDATE_EVIDENCE_CAUTION = (
    "候选/复核证据仅供人工评估；除非同时出现在“已计入 ACMG 证据”中，否则未被分类组合器计入。"
)

ZH_MACHINE_PROPOSAL_NOTE = (
    "本报告中的分类为机器辅助分类建议，仅用于实验室内部辅助判读和人工复核。"
)

ZH_NOT_FINAL_ASSERTION = (
    "本报告不是最终临床结论，不应作为独立的临床签发或诊断依据。"
)

ZH_REVIEWED_EVIDENCE_CAUTION = (
    "人工审核证据只有在 curator 明确给出 reviewed_applied 决策并提供 rationale、"
    "review date 和 provenance 后，才可作为已计入证据显示。"
)

ZH_EXTERNAL_SOURCE_CAUTION = (
    "ClinVar 和 ClinGen Evidence Repository 结果为外部整理资料和复核线索，"
    "不会自动作为 ACMG 证据计入，也不会自动决定分类。"
)

ZH_LITERATURE_CAUTION = (
    "文献证据为候选/复核材料，系统不会自动将文献主张转换为已计入 ACMG 证据。"
)

ZH_CLASSIFICATION_LABELS = {
    "pathogenic": "致病",
    "likely_pathogenic": "疑似致病",
    "vus": "意义未明",
    "likely_benign": "疑似良性",
    "benign": "良性",
}


@dataclass(frozen=True)
class ModeTemplate:
    title: str
    include_audit_details: bool
    include_evidence_table: bool
    include_reviewer_checklist: bool
    opening_label: str


MODE_TEMPLATES: dict[ReportMode, ModeTemplate] = {
    ReportMode.CONCISE: ModeTemplate(
        title="Variant Pathogenicity Report",
        include_audit_details=False,
        include_evidence_table=False,
        include_reviewer_checklist=False,
        opening_label="Concise machine-generated ACMG report",
    ),
    ReportMode.DETAILED: ModeTemplate(
        title="Detailed Variant Pathogenicity Report",
        include_audit_details=True,
        include_evidence_table=True,
        include_reviewer_checklist=True,
        opening_label="Detailed machine-generated ACMG report",
    ),
    ReportMode.LABORATORY: ModeTemplate(
        title="Laboratory Variant Pathogenicity Report",
        include_audit_details=True,
        include_evidence_table=True,
        include_reviewer_checklist=True,
        opening_label="Laboratory-facing machine-generated ACMG report",
    ),
    ReportMode.CLINICIAN: ModeTemplate(
        title="Clinician Variant Pathogenicity Report",
        include_audit_details=False,
        include_evidence_table=False,
        include_reviewer_checklist=True,
        opening_label="Clinician-facing machine-generated ACMG report",
    ),
}
