from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tools import McpToolError, ToolDefinition, ToolRegistry

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_pathogenicity_rater.normalization import (  # noqa: E402
    NormalizationError,
    normalize_variant as normalize_variant_service,
)
from variant_pathogenicity_rater.evidence.population import (  # noqa: E402
    MockPopulationFrequencyProvider,
)
from variant_pathogenicity_rater.evidence.literature import (  # noqa: E402
    extract_literature_evidence as extract_literature_evidence_service,
)
from variant_pathogenicity_rater.evidence.clinvar import (  # noqa: E402
    ClinVarQuery,
    MockClinVarProvider,
)
from variant_pathogenicity_rater.acmg.population_rules import (  # noqa: E402
    evaluate_population_rules as evaluate_population_rules_service,
)
from variant_pathogenicity_rater.acmg.computational_rules import (  # noqa: E402
    evaluate_computational_predictions as evaluate_computational_predictions_service,
)
from variant_pathogenicity_rater.acmg.pvs1 import (  # noqa: E402
    evaluate_pvs1 as evaluate_pvs1_service,
)
from variant_pathogenicity_rater.reporting import (  # noqa: E402
    generate_report as generate_report_service,
)
from variant_pathogenicity_rater.pipeline.rate_variant import (  # noqa: E402
    rate_variant as rate_variant_pipeline,
)
from variant_pathogenicity_rater.config.thresholds import (  # noqa: E402
    computational_thresholds_from_options,
    population_thresholds_from_options,
)
from variant_pathogenicity_rater.schemas.classification import ClassificationResult  # noqa: E402
from variant_pathogenicity_rater.schemas.evidence import (  # noqa: E402
    ComputationalPrediction,
    PopulationFrequency,
)
from variant_pathogenicity_rater.schemas.report import (  # noqa: E402
    ReportFormat,
    ReportLanguage,
    ReportMode,
)
from variant_pathogenicity_rater.schemas.variant import GeneDiseaseContext, Transcript, Variant  # noqa: E402


HUMAN_REVIEW_NOTICE = (
    "Human review is required. This framework does not provide a final clinical assertion."
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _placeholder_result(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "tool": tool_name,
        "stage": "mcp_framework",
        "message": "ACMG business logic is intentionally not implemented in this phase.",
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "provenance": [],
            "limitations": [
                "SNV/small indel framework only.",
                "No variant normalization, evidence retrieval, ACMG evaluation, classification, or report rendering has been performed.",
            ],
        },
    }


async def rate_variant(arguments: dict[str, Any]) -> dict[str, Any]:
    has_wrapped_variant = isinstance(arguments.get("variant"), dict)
    has_flat_variant = any(
        key in arguments
        for key in (
            "gene",
            "gene_symbol",
            "transcript",
            "hgvs_c",
            "hgvs_p",
            "chromosome",
            "chrom",
            "position",
            "pos",
            "ref",
            "alt",
            "value",
        )
    )
    if not has_wrapped_variant and not has_flat_variant:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "rate_variant requires either a 'variant' object or flat variant fields.",
            details={
                "required_any": [
                    "variant",
                    "gene/transcript/hgvs_c",
                    "chromosome/position/ref/alt",
                ]
            },
        )

    return rate_variant_pipeline(arguments)


async def normalize_variant(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        result = normalize_variant_service(arguments)
    except NormalizationError as exc:
        raise McpToolError(
            exc.code,
            exc.message,
            details={
                "normalization_warnings": exc.warnings,
                "unresolved_fields": exc.unresolved_fields,
                "human_review_required": True,
            },
        ) from exc

    dumped = json.loads(result.model_dump_json())
    return {
        "status": dumped["status"],
        "tool": "normalize_variant",
        "stage": "variant_normalization",
        "input_format": dumped["input_format"],
        "normalized_variant": dumped["normalized_variant"],
        "normalization_warnings": dumped["normalization_warnings"],
        "unresolved_fields": dumped["unresolved_fields"],
        "human_review_required": dumped["human_review_required"],
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "provenance": [],
            "limitations": [
                "SNV/small indel framework only.",
                "No liftover, transcript mapping service, or external normalization API was used.",
            ],
        },
    }


async def query_clinvar(arguments: dict[str, Any]) -> dict[str, Any]:
    query_payload = arguments.get("query")
    variant_payload = arguments.get("variant") or arguments.get("normalized_variant")

    try:
        if isinstance(variant_payload, dict):
            query = ClinVarQuery.from_variant(Variant.model_validate(variant_payload))
        elif isinstance(query_payload, dict):
            query = ClinVarQuery.model_validate(query_payload)
        else:
            query = ClinVarQuery.model_validate(arguments)
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for query_clinvar.",
            details={"errors": exc.errors()},
        ) from exc

    if not query.normalized_keys():
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            (
                "query_clinvar requires one supported query shape: gene+hgvs_c, "
                "gene+hgvs_p, rsID, ClinVar Variation ID, or chromosome+position+ref+alt."
            ),
            details={
                "supported": [
                    ["gene", "hgvs_c"],
                    ["gene", "hgvs_p"],
                    ["rsid"],
                    ["variation_id"],
                    ["chromosome", "position", "ref", "alt"],
                ]
            },
        )

    result = MockClinVarProvider().query(query)
    return {
        "status": "ok",
        "tool": "query_clinvar",
        "stage": "mock_clinvar_provider",
        "clinvar_records": [json.loads(record.model_dump_json()) for record in result.records],
        "candidate_evidence_items": [
            json.loads(item.model_dump_json()) for item in result.candidate_evidence_items
        ],
        "review_flags": [json.loads(flag.model_dump_json()) for flag in result.review_flags],
        "limitations": result.limitations,
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "provenance": [
                {
                    "source": "ClinVar",
                    "version": "mock-clinvar-offline-v1",
                    "offline": True,
                    "query": json.loads(query.model_dump_json(exclude_none=True)),
                }
            ],
            "limitations": result.limitations,
        },
    }


async def query_population_frequency(arguments: dict[str, Any]) -> dict[str, Any]:
    variant_payload = arguments.get("variant")
    if not isinstance(variant_payload, dict):
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "query_population_frequency requires a 'variant' object.",
            details={"required": ["variant"]},
        )

    try:
        variant = Variant.model_validate(variant_payload)
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid variant payload for query_population_frequency.",
            details={"errors": exc.errors()},
        ) from exc

    frequency = MockPopulationFrequencyProvider().query(variant)
    return {
        "status": "ok",
        "tool": "query_population_frequency",
        "stage": "mock_population_frequency_provider",
        "population_frequency": json.loads(frequency.model_dump_json()),
        "evidence_items": [],
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "provenance": [
                {
                    "source": frequency.data_source,
                    "version": frequency.data_version,
                    "offline": True,
                }
            ],
            "limitations": [
                "Offline mock provider only; no external population database was queried.",
                "Population frequency retrieval does not apply ACMG criteria.",
            ],
        },
    }


async def evaluate_pvs1(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        variant = Variant.model_validate(arguments.get("variant"))
        context = GeneDiseaseContext.model_validate(arguments.get("gene_disease_context"))
        transcript_payload = arguments.get("transcript")
        transcript = Transcript.model_validate(transcript_payload) if isinstance(transcript_payload, dict) else None
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for evaluate_pvs1.",
            details={"errors": exc.errors()},
        ) from exc

    result = evaluate_pvs1_service(
        variant=variant,
        transcript=transcript,
        gene_disease_context=context,
    )
    dumped = result.model_dump()
    evidence_item = dumped["evidence_item"]
    return {
        "status": "ok",
        "tool": "evaluate_pvs1",
        "stage": "acmg_pvs1_rules",
        "pvs1": {
            "outcome": dumped["outcome"],
            "reasoning_chain": dumped["reasoning_chain"],
            "downgrade_rationale": dumped["downgrade_rationale"],
            "confidence": dumped["confidence"],
            "requires_review": dumped["requires_review"],
            "predicted_consequence": dumped["predicted_consequence"],
            "nmd_predicted": dumped["nmd_predicted"],
        },
        "evidence_items": [evidence_item] if evidence_item else [],
        "criterion_assessment": (
            {
                "criterion": "PVS1",
                "status": "met",
                "strength": evidence_item["strength"],
                "applied_pvs1_level": dumped["outcome"],
                "rationale": evidence_item["reason"],
                "evidence_refs": [evidence_item["evidence_id"]],
                "requires_human_review": evidence_item["requires_review"],
            }
            if evidence_item
            else {
                "criterion": "PVS1",
                "status": "not_met",
                "strength": "none",
                "applied_pvs1_level": "not_triggered",
                "rationale": "PVS1 was not triggered.",
                "evidence_refs": [],
                "requires_human_review": True,
            }
        ),
        "review_flags": dumped["review_flags"],
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "limitations": [
                "SNV/small indel PVS1 only.",
                "CNV, exon-level deletion, SV, complex rearrangement, and RNA-seq evidence are not evaluated.",
                "Machine-generated ACMG evidence requires qualified human review.",
            ],
        },
    }


async def evaluate_population_rules(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        variant = Variant.model_validate(arguments.get("variant"))
        context = GeneDiseaseContext.model_validate(arguments.get("gene_disease_context"))
        frequency = PopulationFrequency.model_validate(arguments.get("population_frequency"))
        thresholds = population_thresholds_from_options(arguments.get("thresholds"))
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for evaluate_population_rules.",
            details={"errors": exc.errors()},
        ) from exc

    evidence_items = evaluate_population_rules_service(variant, context, frequency, thresholds)
    return {
        "status": "ok",
        "tool": "evaluate_population_rules",
        "stage": "acmg_population_rules",
        "evidence_items": [json.loads(item.model_dump_json()) for item in evidence_items],
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "limitations": [
                "Machine-generated ACMG evidence requires qualified human review.",
                "BA1, BS1, and PM2 thresholds are configurable and should be disease-profile specific.",
            ],
        },
    }


async def evaluate_computational_evidence(arguments: dict[str, Any]) -> dict[str, Any]:
    prediction_payloads = (
        arguments.get("computational_predictions")
        or arguments.get("predictions")
        or arguments.get("evidence_items")
        or []
    )
    if not isinstance(prediction_payloads, list):
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Computational predictions must be provided as a list.",
            details={"field": "computational_predictions"},
        )

    try:
        variant = Variant.model_validate(arguments.get("variant"))
        predictions = [
            ComputationalPrediction.model_validate(prediction) for prediction in prediction_payloads
        ]
        thresholds = computational_thresholds_from_options(arguments.get("thresholds"))
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for evaluate_computational_evidence.",
            details={"errors": exc.errors()},
        ) from exc

    evidence_items, review_flags, summary = evaluate_computational_predictions_service(
        variant=variant,
        predictions=predictions,
        thresholds=thresholds,
    )
    return {
        "status": "ok",
        "tool": "evaluate_computational_evidence",
        "stage": "acmg_computational_rules",
        "evidence_items": [json.loads(item.model_dump_json()) for item in evidence_items],
        "criterion_assessments": [
            {
                "criterion": item.code,
                "status": "met",
                "strength": item.strength,
                "rationale": item.reason,
                "evidence_refs": [item.evidence_id],
                "requires_human_review": item.requires_review,
            }
            for item in evidence_items
        ],
        "review_flags": [json.loads(flag.model_dump_json()) for flag in review_flags],
        "summary": summary,
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "limitations": [
                "SNV/small indel computational evidence only.",
                "PP3 and BP4 are supporting-strength criteria only.",
                "PP3 and BP4 are mutually exclusive in this evaluator.",
                "SpliceAI high delta score can support PP3 as splice-related computational evidence but cannot replace PVS1 or PS3.",
            ],
        },
    }


async def search_literature_evidence(arguments: dict[str, Any]) -> dict[str, Any]:
    variant_payload = arguments.get("variant")
    if not isinstance(variant_payload, dict):
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "search_literature_evidence requires a 'variant' object.",
            details={"required": ["variant"]},
        )

    try:
        variant = Variant.model_validate(variant_payload)
        context_payload = arguments.get("gene_disease_context") or arguments.get("context")
        context = (
            GeneDiseaseContext.model_validate(context_payload)
            if isinstance(context_payload, dict)
            else None
        )
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for search_literature_evidence.",
            details={"errors": exc.errors()},
        ) from exc

    result = extract_literature_evidence_service(variant=variant, context=context)
    return {
        "status": "ok",
        "tool": "search_literature_evidence",
        "stage": "mock_literature_evidence_provider",
        "literature_records": [
            json.loads(record.model_dump_json()) for record in result.literature_records
        ],
        "candidate_evidence_items": [
            json.loads(item.model_dump_json()) for item in result.candidate_evidence_items
        ],
        "evidence_items": [
            json.loads(item.model_dump_json()) for item in result.candidate_evidence_items
        ],
        "extracted_claims": [
            json.loads(claim.model_dump_json()) for claim in result.extracted_claims
        ],
        "review_flags": [json.loads(flag.model_dump_json()) for flag in result.review_flags],
        "limitations": result.limitations,
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "provenance": [
                {
                    "source": record.source.name,
                    "version": record.source.version,
                    "citation": record.citation,
                    "offline": True,
                }
                for record in result.literature_records
            ],
            "limitations": result.limitations,
        },
    }


async def generate_report(arguments: dict[str, Any]) -> dict[str, Any]:
    result_payload = (
        arguments.get("classification_result")
        or arguments.get("result")
        or arguments.get("classification")
    )
    if not isinstance(result_payload, dict):
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "generate_report requires a 'classification_result' object.",
            details={"required": ["classification_result"]},
        )

    try:
        classification_result = ClassificationResult.model_validate(result_payload)
        output_format = ReportFormat(arguments.get("output_format") or arguments.get("format") or "markdown")
        mode = ReportMode(arguments.get("mode") or "detailed")
        language = ReportLanguage(arguments.get("language", "en"))
    except (ValidationError, ValueError) as exc:
        details = {"errors": exc.errors()} if isinstance(exc, ValidationError) else {"error": str(exc)}
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for generate_report.",
            details=details,
        ) from exc

    report = generate_report_service(
        classification_result,
        output_format=output_format,
        mode=mode,
        language=language,
    )
    dumped = json.loads(report.model_dump_json())
    response = {
        "status": "ok",
        "tool": "generate_report",
        "stage": "report_generator",
        "report": dumped,
        "json_summary": dumped["summary"],
        "content": dumped["content"],
        "human_review": {
            "required": True,
            "notice": HUMAN_REVIEW_NOTICE,
        },
        "audit": {
            "input": arguments,
            "retrieval_timestamp": _timestamp(),
            "limitations": [
                "Report generation renders supplied structured results only.",
                "Reports do not recalculate ACMG criteria or resolve evidence conflicts.",
            ],
        },
    }
    if output_format == ReportFormat.JSON:
        response["json_report"] = dumped["content"]
    elif output_format == ReportFormat.PLAIN_TEXT:
        response["plain_text"] = dumped["content"]
    else:
        response["markdown"] = dumped["content"]
    return response


def _variant_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": {
                "type": "object",
                "description": "HGVS or VCF-like variant input. SNV/small indel scope only.",
                "additionalProperties": True,
            },
            "options": {
                "type": "object",
                "additionalProperties": True,
            },
        },
        "additionalProperties": True,
    }


def _generic_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }


def _computational_evidence_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": {
                "type": "object",
                "description": "Normalized SNV/small indel Variant payload.",
                "additionalProperties": True,
            },
            "computational_predictions": {
                "type": "array",
                "description": "Mock ComputationalPrediction records.",
                "items": {"type": "object", "additionalProperties": True},
            },
            "thresholds": {
                "type": "object",
                "description": "Optional configurable PP3/BP4 thresholds.",
                "additionalProperties": True,
            },
        },
        "required": ["variant"],
        "additionalProperties": True,
    }


def _pvs1_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": {
                "type": "object",
                "description": "Normalized SNV/small indel Variant payload.",
                "additionalProperties": True,
            },
            "transcript": {
                "type": "object",
                "description": "Transcript payload used for consequence and clinical relevance assessment.",
                "additionalProperties": True,
            },
            "gene_disease_context": {
                "type": "object",
                "description": "Gene-disease context including LoF mechanism, transcript relevance, last-exon, and NMD data.",
                "additionalProperties": True,
            },
        },
        "required": ["variant", "gene_disease_context"],
        "additionalProperties": True,
    }


def _literature_evidence_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": {
                "type": "object",
                "description": "Normalized SNV/small indel Variant payload.",
                "additionalProperties": True,
            },
            "gene_disease_context": {
                "type": "object",
                "description": "Optional gene-disease and phenotype context for review notes.",
                "additionalProperties": True,
            },
        },
        "required": ["variant"],
        "additionalProperties": True,
    }


def _generate_report_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "classification_result": {
                "type": "object",
                "description": "ClassificationResult payload to render. Criteria are not recalculated.",
                "additionalProperties": True,
            },
            "format": {
                "type": "string",
                "enum": ["markdown", "plain_text", "json"],
                "description": "Output format. Alias: output_format.",
            },
            "output_format": {"type": "string", "enum": ["markdown", "plain_text", "json"]},
            "mode": {
                "type": "string",
                "enum": ["concise", "detailed", "laboratory", "clinician"],
            },
            "language": {
                "type": "string",
                "enum": ["en", "zh"],
                "description": "English is complete. Chinese is reserved for future localization.",
            },
        },
        "required": ["classification_result"],
        "additionalProperties": True,
    }


def _normalize_variant_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": {
                "type": "object",
                "description": "Optional wrapper for HGVS-like or VCF-like variant input.",
                "additionalProperties": True,
            },
            "input_type": {"type": "string", "enum": ["hgvs", "vcf_like", "structured"]},
            "gene": {"type": "string"},
            "gene_symbol": {"type": "string"},
            "transcript": {"type": "string"},
            "transcript_accession": {"type": "string"},
            "hgvs": {"type": "string"},
            "hgvs_c": {"type": "string"},
            "hgvs_p": {"type": "string"},
            "chrom": {"type": "string"},
            "chromosome": {"type": "string"},
            "pos": {"type": "integer", "minimum": 1},
            "position": {"type": "integer", "minimum": 1},
            "ref": {"type": "string"},
            "alt": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ]
            },
            "genome_build": {"type": "string", "enum": ["GRCh37", "GRCh38"]},
            "vcf": {"type": "object", "additionalProperties": True},
        },
        "additionalProperties": True,
    }


def register_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="rate_variant",
            description=(
                "Run the complete offline mock SNV/small indel ACMG pipeline: "
                "normalization, population rules, computational evidence, PVS1, "
                "ClinVar, literature, classification, and report generation."
            ),
            input_schema=_variant_input_schema(),
            handler=rate_variant,
        )
    )
    registry.register(
        ToolDefinition(
            name="normalize_variant",
            description="Normalize phase-1 SNV/small indel HGVS-like or VCF-like input into the standard Variant schema.",
            input_schema=_normalize_variant_input_schema(),
            handler=normalize_variant,
        )
    )
    registry.register(
        ToolDefinition(
            name="query_clinvar",
            description="Offline mock ClinVar record lookup and candidate evidence mapping framework.",
            input_schema=_generic_input_schema(),
            handler=query_clinvar,
        )
    )
    registry.register(
        ToolDefinition(
            name="query_population_frequency",
            description="Offline mock population frequency retrieval interface.",
            input_schema=_generic_input_schema(),
            handler=query_population_frequency,
        )
    )
    registry.register(
        ToolDefinition(
            name="evaluate_pvs1",
            description="Evaluate PVS1 for phase-1 SNV/small indel loss-of-function variants.",
            input_schema=_pvs1_input_schema(),
            handler=evaluate_pvs1,
        )
    )
    registry.register(
        ToolDefinition(
            name="evaluate_population_rules",
            description="Evaluate BA1, BS1, and PM2 from population frequency evidence.",
            input_schema=_generic_input_schema(),
            handler=evaluate_population_rules,
        )
    )
    registry.register(
        ToolDefinition(
            name="evaluate_computational_evidence",
            description="Evaluate PP3/BP4 supporting evidence from computational predictions.",
            input_schema=_computational_evidence_input_schema(),
            handler=evaluate_computational_evidence,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_literature_evidence",
            description=(
                "Search offline mock literature records and extract citation-preserving "
                "candidate ACMG evidence review notes."
            ),
            input_schema=_literature_evidence_input_schema(),
            handler=search_literature_evidence,
        )
    )
    registry.register(
        ToolDefinition(
            name="generate_report",
            description="Render structured JSON, Markdown, or plain-text reports from a ClassificationResult.",
            input_schema=_generate_report_input_schema(),
            handler=generate_report,
        )
    )
