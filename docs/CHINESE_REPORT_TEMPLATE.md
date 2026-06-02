# Chinese Report Template

The Chinese report template is a laboratory-internal review format for
`generate_report`. It renders an existing `ClassificationResult`; it does not
add ACMG criteria, rerun evidence generation, change evidence strength, modify
the classification combiner, or relax safety rules.

## Intended Use

Chinese reports are for internal auxiliary interpretation and human review.
They are machine proposals, not final clinical conclusions, and are not
clinical sign-out documents.

The template preserves these boundaries:

- Applied ACMG evidence is displayed separately from candidate/review-note
  evidence.
- Manual reviewed evidence is displayed separately with curator decision,
  review date, rationale, provenance, and audit-trail fields when supplied.
- ClinVar, ClinGen Evidence Repository, and literature records remain external
  review support unless already represented as applied evidence in the supplied
  classification result.
- VUS wording is conservative and must not imply a pathogenic or benign leaning.

## Sections

The `language=zh`, `mode=laboratory` markdown report includes:

- `报告摘要`
- `变异基本信息`
- `机器辅助分类建议`
- `分类依据说明`
- `已计入 ACMG 证据`
- `候选/复核证据`
- `人工审核证据`
- `ClinVar / ClinGen ERepo / 文献证据`
- `转录本 / MANE 验证`
- `VCEP / 特殊规则提示`
- `上下文一致性`
- `冲突证据`
- `数据来源与溯源`
- `局限性`
- `可能缺失的数据`
- `人工复核清单`
- `免责声明`

## Terminology

| English | Chinese |
|---|---|
| Pathogenic | 致病 |
| Likely Pathogenic | 疑似致病 |
| Variant of Uncertain Significance / VUS | 意义未明 |
| Likely Benign | 疑似良性 |
| Benign | 良性 |
| applied evidence | 已计入证据 |
| candidate/review-note evidence | 候选/复核证据 |
| reviewed evidence | 人工审核证据 |
| provenance | 数据来源与溯源 |
| limitation | 局限性 |
| machine proposal | 机器辅助分类建议 |
| human review required | 需要人工复核 |
| classification combiner | 分类组合器 |
| final clinical assertion | 最终临床结论 |

## Fixed Safety Wording

Chinese reports use fixed safety language for the core boundaries:

- `本报告中的分类为机器辅助分类建议，仅用于实验室内部辅助判读和人工复核。`
- `所有变异信息、证据条目、ACMG 标准、数据来源、局限性和分类建议均必须由具备资质的人员复核。`
- `候选/复核证据仅供人工评估；除非同时出现在“已计入 ACMG 证据”中，否则未被分类组合器计入。`
- `本报告不是最终临床结论，不应作为独立的临床签发或诊断依据。`
- `人工审核证据只有在 curator 明确给出 reviewed_applied 决策并提供 rationale、review date 和 provenance 后，才可作为已计入证据显示。`
- `ClinVar 和 ClinGen Evidence Repository 结果为外部整理资料和复核线索，不会自动作为 ACMG 证据计入，也不会自动决定分类。`
- `文献证据为候选/复核材料，系统不会自动将文献主张转换为已计入 ACMG 证据。`
- `意义未明表示现有证据不足以支持致病或良性分类；不得使用偏向致病或偏向良性的措辞，除非后续人工审核证据支持重新分类。`

## Output Options

Python and MCP report generation support:

- `output_format="markdown", language="zh", mode="laboratory"`
- `output_format="plain_text", language="zh", mode="laboratory"`
- `output_format="json", language="zh", mode="laboratory"`

The JSON report keeps stable top-level keys. Chinese localization changes
labels, notes, and safety text, not the key structure.

CLI examples:

```bash
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown-zh
vpr rate --gene BRCA1 --transcript NM_007294.4 --hgvs-c NM_007294.4:c.68A\>G --output markdown --language zh --report-mode laboratory
```

Batch `--language zh` adds a Chinese `summary_zh` triage note while preserving
the stable per-record output and existing `summary` fields.
