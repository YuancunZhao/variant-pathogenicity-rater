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


def _string_array_schema() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


def _open_object_schema(description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "additionalProperties": True}
    if description:
        schema["description"] = description
    return schema


def _audit_trail_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "event_id": {"type": "string"},
            "event_type": {"type": "string"},
            "timestamp": {"type": "string"},
            "actor": {"type": "string"},
            "tool_name": {"type": ["string", "null"]},
            "query": _open_object_schema("Flexible source query snapshot."),
            "source_snapshot": _open_object_schema("Flexible source payload snapshot."),
            "checksum": {"type": ["string", "null"]},
            "notes": _string_array_schema(),
        },
        "required": ["event_id", "event_type"],
        "additionalProperties": False,
    }


def _review_flag_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "code": {"type": "string"},
            "message": {"type": "string"},
            "severity": {"type": "string", "enum": ["info", "warning", "error"]},
            "blocking": {"type": "boolean"},
            "audit_trail": {"type": "array", "items": _audit_trail_schema()},
        },
        "required": ["code", "message"],
        "additionalProperties": False,
    }


def _source_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "version": {"type": ["string", "null"]},
            "url": {"type": ["string", "null"]},
            "database_id": {"type": ["string", "null"]},
            "retrieval_timestamp": {"type": ["string", "null"]},
            "query": _open_object_schema("Flexible provider query metadata."),
            "raw_snapshot_ref": {"type": ["string", "null"]},
            "provenance": {},
        },
        "required": ["name"],
        "additionalProperties": False,
    }


def _transcript_schema(description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "accession": {"type": "string"},
            "version": {"type": ["string", "null"]},
            "gene_symbol": {"type": "string"},
            "hgvs_c": {"type": ["string", "null"]},
            "hgvs_p": {"type": ["string", "null"]},
            "exon": {"type": ["string", "null"]},
            "consequence": {"type": ["string", "null"]},
            "mane_select": {"type": "boolean"},
            "canonical": {"type": "boolean"},
        },
        "required": ["accession", "gene_symbol"],
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def _variant_schema(description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "variant_id": {"type": "string"},
            "genome_build": {"type": "string", "enum": ["GRCh37", "GRCh38"]},
            "variant_type": {
                "type": "string",
                "enum": ["snv", "small_insertion", "small_deletion", "small_delins"],
            },
            "chrom": {"type": "string"},
            "pos": {"type": "integer", "minimum": 1},
            "ref": {"type": "string"},
            "alt": {"type": "string"},
            "gene_symbol": {"type": ["string", "null"]},
            "transcript": {"oneOf": [_transcript_schema(), {"type": "null"}]},
            "hgvs_g": {"type": ["string", "null"]},
            "hgvs_c": {"type": ["string", "null"]},
            "hgvs_p": {"type": ["string", "null"]},
            "zygosity": {
                "type": "string",
                "enum": ["heterozygous", "homozygous", "hemizygous", "unknown"],
            },
            "normalization_warnings": _string_array_schema(),
            "review_flags": {"type": "array", "items": _review_flag_schema()},
            "audit_trail": {"type": "array", "items": _audit_trail_schema()},
        },
        "required": ["variant_id", "genome_build", "variant_type", "chrom", "pos", "ref", "alt"],
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def _last_exon_information_schema() -> dict[str, Any]:
    nullable_bool = {"type": ["boolean", "null"]}
    return {
        "type": "object",
        "properties": {
            "is_in_last_exon": nullable_bool,
            "is_in_penultimate_exon": nullable_bool,
            "exon_number": {"type": ["integer", "null"]},
            "total_exons": {"type": ["integer", "null"]},
            "distance_to_last_exon_junction": {"type": ["integer", "null"]},
            "within_terminal_region": nullable_bool,
            "predicted_to_escape_nmd": nullable_bool,
            "affects_critical_region": nullable_bool,
        },
        "additionalProperties": False,
    }


def _gene_disease_context_schema(description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "gene_symbol": {"type": "string"},
            "gene": {"type": "string"},
            "disease_name": {"type": "string"},
            "disease": {"type": "string"},
            "disease_id": {"type": ["string", "null"]},
            "inheritance_mode": {"type": ["string", "null"]},
            "inheritance": {"type": ["string", "null"]},
            "disease_prevalence": {"type": ["number", "null"]},
            "population_ancestry": {"type": ["string", "null"]},
            "phenotype_terms": _string_array_schema(),
            "transcript": {"oneOf": [_transcript_schema(), {"type": "null"}]},
            "lof_is_known_mechanism": {"type": ["boolean", "null"]},
            "transcript_is_biologically_relevant": {"type": ["boolean", "null"]},
            "last_exon_information": {"oneOf": [_last_exon_information_schema(), {"type": "null"}]},
            "nmd_prediction_available": {"type": "boolean"},
            "nmd_predicted": {"type": ["boolean", "null"]},
            "source": {"type": ["string", "null"]},
            "audit_trail": {"type": "array", "items": _audit_trail_schema()},
        },
        "anyOf": [
            {"required": ["gene_symbol", "disease_name"]},
            {"required": ["gene", "disease"]},
            {"required": ["gene_symbol", "disease"]},
            {"required": ["gene", "disease_name"]},
        ],
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def _normalization_properties() -> dict[str, Any]:
    return {
        "input_type": {"type": "string", "enum": ["hgvs", "vcf_like", "structured"]},
        "format": {"type": "string", "enum": ["hgvs", "vcf_like", "structured"]},
        "gene": {"type": "string"},
        "gene_symbol": {"type": "string"},
        "transcript": {"type": "string"},
        "transcript_accession": {"type": "string"},
        "hgvs": {"type": "string"},
        "value": {"type": "string"},
        "hgvs_g": {"type": "string"},
        "hgvs_c": {"type": "string"},
        "hgvs_p": {"type": "string"},
        "chrom": {"type": "string"},
        "chromosome": {"type": "string"},
        "pos": {"type": "integer", "minimum": 1},
        "position": {"type": "integer", "minimum": 1},
        "ref": {"type": "string"},
        "alt": {"oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]},
        "genome_build": {"type": "string", "enum": ["GRCh37", "GRCh38"]},
    }


def _normalization_payload_schema(description: str | None = None) -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": _normalization_properties(),
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def _clinvar_query_properties() -> dict[str, Any]:
    return {
        "gene": {"type": ["string", "null"]},
        "gene_symbol": {"type": ["string", "null"]},
        "hgvs_c": {"type": ["string", "null"]},
        "hgvs_p": {"type": ["string", "null"]},
        "rsid": {"type": ["string", "null"]},
        "rsID": {"type": ["string", "null"]},
        "variation_id": {"type": ["string", "null"]},
        "clinvar_variation_id": {"type": ["string", "null"]},
        "variationID": {"type": ["string", "null"]},
        "chromosome": {"type": ["string", "null"]},
        "chrom": {"type": ["string", "null"]},
        "position": {"type": ["integer", "null"]},
        "pos": {"type": ["integer", "null"]},
        "ref": {"type": ["string", "null"]},
        "alt": {"type": ["string", "null"]},
        "genome_build": {"type": ["string", "null"]},
        "condition": {"type": ["string", "null"]},
    }


def _clinvar_query_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": _clinvar_query_properties(),
        "additionalProperties": False,
    }


def _population_frequency_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "source": {"oneOf": [_source_schema(), {"type": "null"}]},
            "overall_af": {"type": ["number", "null"]},
            "max_pop_af": {"type": ["number", "null"]},
            "population_name": {"type": "string"},
            "allele_count": {"type": ["integer", "null"]},
            "allele_number": {"type": ["integer", "null"]},
            "homozygote_count": {"type": ["integer", "null"]},
            "hemizygote_count": {"type": ["integer", "null"]},
            "data_source": {"type": "string"},
            "filter_status": {"type": ["string", "null"]},
            "data_version": {"type": ["string", "null"]},
            "is_absent": {"type": "boolean"},
            "faf95": {"type": ["number", "null"]},
            "filtering_af": {"type": ["number", "null"]},
            "genome_build": {"type": ["string", "null"]},
            "dataset_version": {"type": ["string", "null"]},
            "coverage_quality": {"type": ["string", "null"]},
            "population_match": {"type": ["boolean", "null"]},
            "limitations": _string_array_schema(),
        },
        "required": ["population_name", "data_source"],
        "additionalProperties": False,
    }


def _splice_prediction_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "source": _source_schema(),
            "DS_AG": {"type": ["number", "null"]},
            "DS_AL": {"type": ["number", "null"]},
            "DS_DG": {"type": ["number", "null"]},
            "DS_DL": {"type": ["number", "null"]},
            "max_delta_score": {"type": "number"},
            "predicted_consequence": {"type": "string"},
            "affected_gene": {"type": "string"},
            "transcript": {"type": ["string", "null"]},
            "source_version": {"type": ["string", "null"]},
            "genome_build": {"type": ["string", "null"]},
            "provenance": {},
            "candidate_only": {"type": "boolean"},
            "limitations": _string_array_schema(),
        },
        "required": ["source", "max_delta_score", "predicted_consequence", "affected_gene"],
        "additionalProperties": False,
    }


def _computational_prediction_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "source": _source_schema(),
            "method": {"type": "string"},
            "score": {"type": ["number", "null"]},
            "prediction": {"type": "string"},
            "threshold": {"type": ["number", "null"]},
            "transcript": {"type": ["string", "null"]},
            "candidate_only": {"type": "boolean"},
            "limitations": _string_array_schema(),
            "splice_prediction": {"oneOf": [_splice_prediction_schema(), {"type": "null"}]},
        },
        "required": ["source", "method", "prediction"],
        "additionalProperties": False,
    }


def _computational_thresholds_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Optional configurable PP3/BP4 thresholds.",
        "properties": {
            "min_pathogenic_supporting_tools": {"type": "integer"},
            "min_benign_supporting_tools": {"type": "integer"},
            "revel_pathogenic": {"type": "number"},
            "revel_benign": {"type": "number"},
            "cadd_pathogenic": {"type": "number"},
            "cadd_benign": {"type": "number"},
            "sift_pathogenic": {"type": "number"},
            "sift_benign": {"type": "number"},
            "polyphen2_pathogenic": {"type": "number"},
            "polyphen2_benign": {"type": "number"},
            "spliceai_pathogenic": {"type": "number"},
            "spliceai_benign": {"type": "number"},
        },
        "additionalProperties": False,
    }


def _evidence_code_values() -> list[str]:
    return [
        "PVS1", "PS1", "PS2", "PS3", "PS4", "PM1", "PM2", "PM3",
        "PM4", "PM5", "PM6", "PP1", "PP2", "PP3", "PP4", "PP5",
        "BA1", "BS1", "BS2", "BS3", "BS4", "BP1", "BP2", "BP3",
        "BP4", "BP5", "BP6", "BP7",
    ]


def _evidence_item_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "evidence_id": {"type": "string"},
            "code": {"type": "string", "enum": _evidence_code_values()},
            "strength": {
                "type": "string",
                "enum": ["stand_alone", "very_strong", "strong", "moderate", "supporting", "none"],
            },
            "direction": {
                "type": "string",
                "enum": ["pathogenic", "benign", "neutral", "conflicting"],
            },
            "reason": {"type": "string"},
            "source": _source_schema(),
            "confidence": {"type": "number"},
            "requires_review": {"type": "boolean"},
            "triggered_by": _string_array_schema(),
            "supporting_data": _open_object_schema("Flexible evidence-specific supporting data."),
            "audit_trail": {"type": "array", "items": _audit_trail_schema()},
            "review_flags": {"type": "array", "items": _review_flag_schema()},
        },
        "required": ["evidence_id", "code", "strength", "direction", "reason", "source", "confidence"],
        "additionalProperties": False,
    }


def _classification_result_schema(description: str | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "result_id": {"type": "string"},
            "variant": _variant_schema(),
            "final_classification": {
                "type": "string",
                "enum": ["pathogenic", "likely_pathogenic", "vus", "likely_benign", "benign"],
            },
            "evidence_items": {"type": "array", "items": _evidence_item_schema()},
            "applied_combination_rule": {"type": ["string", "null"]},
            "pathogenic_evidence_summary": _string_array_schema(),
            "benign_evidence_summary": _string_array_schema(),
            "conflicting_evidence": _string_array_schema(),
            "limitations": _string_array_schema(),
            "confidence": {"type": "number"},
            "human_review_required": {"type": "boolean"},
            "report_text": {"type": "string"},
            "review_flags": {"type": "array", "items": _review_flag_schema()},
            "audit_trail": {"type": "array", "items": _audit_trail_schema()},
        },
        "required": ["result_id", "variant", "final_classification", "confidence", "report_text"],
        "additionalProperties": False,
    }
    if description:
        schema["description"] = description
    return schema


def _data_sources_override_schema() -> dict[str, Any]:
    source_override = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["mock", "online", "disabled"]},
            "timeout_seconds": {"type": "number"},
            "cache_enabled": {"type": "boolean"},
            "endpoint": {"type": ["string", "null"]},
            "api_key_env": {"type": ["string", "null"]},
            "fixture_path": {"type": ["string", "null"]},
        },
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "clinvar": source_override,
            "population": source_override,
            "computational": source_override,
            "literature": source_override,
        },
        "additionalProperties": False,
    }


def _pipeline_options_schema() -> dict[str, Any]:
    population_fixture = _population_frequency_schema()
    population_fixture = {
        **population_fixture,
        "description": "Single mock population fixture. Must include variant_id.",
        "properties": {**population_fixture["properties"], "variant_id": {"type": "string"}},
        "required": ["variant_id", "population_name", "data_source"],
    }
    return {
        "type": "object",
        "description": "Designated flexible wrapper for mock fixtures and per-run options.",
        "properties": {
            "mock_mode": {"type": "boolean"},
            "include_population": {"type": "boolean"},
            "include_computational": {"type": "boolean"},
            "include_clinvar": {"type": "boolean"},
            "include_literature": {"type": "boolean"},
            "data_sources": _data_sources_override_schema(),
            "population_frequency": population_fixture,
            "population_thresholds": {
                "type": "object",
                "properties": {
                    "disease_specific": {"type": "boolean"},
                    "penetrance_provided": {"type": "boolean"},
                    "ba1_af_threshold": {"type": "number"},
                    "bs1_af_threshold": {"type": "number"},
                    "pm2_af_threshold": {"type": "number"},
                    "min_allele_number": {"type": "integer"},
                    "high_confidence": {"type": "number"},
                    "missing_context_confidence_penalty": {"type": "number"},
                    "warning_confidence_penalty": {"type": "number"},
                    "founder_populations": _string_array_schema(),
                },
                "additionalProperties": False,
            },
            "computational_predictions": {"type": "array", "items": _computational_prediction_schema()},
            "computational_thresholds": _computational_thresholds_schema(),
            "clinvar_records": {
                "type": "array",
                "items": _open_object_schema("Flexible mock ClinVar raw record."),
            },
            "literature_records": {
                "type": "array",
                "items": _open_object_schema("Flexible mock literature raw record."),
            },
            "mock_supplemental_evidence_items": {"type": "array", "items": _evidence_item_schema()},
            "supplemental_evidence_items": {"type": "array", "items": _evidence_item_schema()},
            "gene_disease_context": _gene_disease_context_schema(),
        },
        "additionalProperties": False,
    }


def _variant_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "anyOf": [
            {"required": ["variant"]},
            {"required": ["hgvs_c"]},
            {"required": ["hgvs"]},
            {"required": ["value"]},
            {"required": ["chrom", "pos", "ref", "alt"]},
            {"required": ["chromosome", "position", "ref", "alt"]},
        ],
        "properties": {
            **_normalization_properties(),
            "variant": _normalization_payload_schema(
                "HGVS or VCF-like variant input. SNV/small indel scope only."
            ),
            "gene_disease_context": _gene_disease_context_schema(),
            "context": _gene_disease_context_schema(),
            "disease": {"type": "string"},
            "inheritance": {"type": ["string", "null"]},
            "phenotype": _string_array_schema(),
            "phenotype_terms": _string_array_schema(),
            "options": _pipeline_options_schema(),
        },
        "additionalProperties": False,
    }


def _query_clinvar_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "query": _clinvar_query_schema(),
            "variant": _variant_schema(),
            "normalized_variant": _variant_schema(),
            **_clinvar_query_properties(),
        },
        "additionalProperties": False,
    }


def _population_frequency_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"variant": _variant_schema()},
        "required": ["variant"],
        "additionalProperties": False,
    }


def _population_rules_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": _variant_schema(),
            "gene_disease_context": _gene_disease_context_schema(),
            "population_frequency": _population_frequency_schema(),
            "thresholds": _pipeline_options_schema()["properties"]["population_thresholds"],
        },
        "required": ["variant", "gene_disease_context", "population_frequency"],
        "additionalProperties": False,
    }


def _computational_evidence_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": _variant_schema("Normalized SNV/small indel Variant payload."),
            "computational_predictions": {
                "type": "array",
                "description": "Mock ComputationalPrediction records.",
                "items": _computational_prediction_schema(),
            },
            "predictions": {"type": "array", "items": _computational_prediction_schema()},
            "evidence_items": {"type": "array", "items": _computational_prediction_schema()},
            "thresholds": _computational_thresholds_schema(),
        },
        "required": ["variant"],
        "additionalProperties": False,
    }


def _pvs1_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": _variant_schema("Normalized SNV/small indel Variant payload."),
            "transcript": _transcript_schema(
                "Transcript payload used for consequence and clinical relevance assessment."
            ),
            "gene_disease_context": _gene_disease_context_schema(
                "Gene-disease context including LoF mechanism, transcript relevance, last-exon, and NMD data."
            ),
        },
        "required": ["variant", "gene_disease_context"],
        "additionalProperties": False,
    }


def _literature_evidence_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "variant": _variant_schema("Normalized SNV/small indel Variant payload."),
            "gene_disease_context": _gene_disease_context_schema(
                "Optional gene-disease and phenotype context for review notes."
            ),
            "context": _gene_disease_context_schema(
                "Alias for gene_disease_context."
            ),
        },
        "required": ["variant"],
        "additionalProperties": False,
    }


def _generate_report_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "classification_result": _classification_result_schema(
                "ClassificationResult payload to render. Criteria are not recalculated."
            ),
            "result": _classification_result_schema("Alias for classification_result."),
            "classification": _classification_result_schema("Alias for classification_result."),
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
        "anyOf": [
            {"required": ["classification_result"]},
            {"required": ["result"]},
            {"required": ["classification"]},
        ],
        "additionalProperties": False,
    }


def _normalize_variant_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "anyOf": [
            {"required": ["variant"]},
            {"required": ["hgvs_c"]},
            {"required": ["hgvs"]},
            {"required": ["value"]},
            {"required": ["chrom", "pos", "ref", "alt"]},
            {"required": ["chromosome", "position", "ref", "alt"]},
            {"required": ["vcf"]},
        ],
        "properties": {
            "variant": _normalization_payload_schema(
                "Optional wrapper for HGVS-like or VCF-like variant input."
            ),
            **_normalization_properties(),
            "vcf": _normalization_payload_schema("VCF-like variant object."),
        },
        "additionalProperties": False,
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
            input_schema=_query_clinvar_input_schema(),
            handler=query_clinvar,
        )
    )
    registry.register(
        ToolDefinition(
            name="query_population_frequency",
            description="Offline mock population frequency retrieval interface.",
            input_schema=_population_frequency_input_schema(),
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
            input_schema=_population_rules_input_schema(),
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
