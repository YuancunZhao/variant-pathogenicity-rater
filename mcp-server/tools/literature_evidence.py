from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from tools import McpToolError, ToolDefinition, ToolRegistry

SRC_DIR = Path(__file__).resolve().parents[2] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_pathogenicity_rater.literature_agent import (  # noqa: E402
    LiteratureAgentInput,
    LiteratureSearchInput,
    assess_literature_evidence as assess_literature_evidence_service,
    create_reviewed_evidence_drafts as create_reviewed_evidence_drafts_service,
    search_and_summarize_literature as search_and_summarize_literature_service,
)


async def assess_literature_evidence(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        request = LiteratureAgentInput.model_validate(arguments)
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for assess_literature_evidence.",
            details={"errors": exc.errors()},
        ) from exc

    try:
        result = assess_literature_evidence_service(request)
    except Exception as exc:
        return {
            "status": "degraded",
            "tool": "assess_literature_evidence",
            "stage": "acmg_literature_evidence_agent",
            "literature_evidence_assessments": [],
            "suggested_evidence": [],
            "review_questions": [
                "Could the literature evidence be manually reviewed outside the tool?"
            ],
            "citations": [],
            "limitations": [
                "Literature evidence assessment failed safely.",
                "No suggested evidence was applied or used for classification.",
            ],
            "provenance": {
                "error_type": exc.__class__.__name__,
                "online_search_requested": request.use_online_search,
            },
            "human_review": {
                "required": True,
                "notice": "Suggested literature evidence is not automatically applied to ACMG classification.",
            },
        }

    dumped = json.loads(result.model_dump_json())
    return {
        "status": "ok",
        "tool": "assess_literature_evidence",
        "stage": "acmg_literature_evidence_agent",
        **dumped,
        "applied_evidence": [],
        "final_classification_changed": False,
        "human_review": {
            "required": True,
            "notice": "Suggested literature evidence is not automatically applied to ACMG classification.",
        },
    }


async def create_reviewed_evidence_draft(arguments: dict[str, Any]) -> dict[str, Any]:
    payload = arguments.get("literature_assessment_json", arguments)
    result = create_reviewed_evidence_drafts_service(payload)
    return {
        **result,
        "tool": "create_reviewed_evidence_draft",
        "applied_evidence": [],
        "final_classification_changed": False,
    }


async def search_and_summarize_literature(arguments: dict[str, Any]) -> dict[str, Any]:
    try:
        request = LiteratureSearchInput.model_validate(arguments)
    except ValidationError as exc:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            "Invalid payload for search_and_summarize_literature.",
            details={"errors": exc.errors()},
        ) from exc

    try:
        result = search_and_summarize_literature_service(request)
    except Exception as exc:
        return {
            "status": "degraded",
            "tool": "search_and_summarize_literature",
            "stage": "general_literature_search_and_summary",
            "literature_search_results": [],
            "literature_summary": "Literature search failed safely.",
            "criterion_summaries": [],
            "suggested_evidence": [],
            "evidence_items": [],
            "review_questions": [
                "Could the literature records be manually reviewed outside the tool?"
            ],
            "blocking_flags": [],
            "duplicate_groups": [],
            "limitations": [
                f"Literature search failed safely: {exc.__class__.__name__}: {exc}",
                "No literature evidence was applied or used for classification.",
            ],
            "reviewed_evidence_drafts": [],
            "applied_evidence": [],
            "final_classification_changed": False,
            "human_review": {
                "required": True,
                "notice": "Literature search output is suggested evidence only.",
            },
        }
    dumped = json.loads(result.model_dump_json())
    return {
        **dumped,
        "tool": "search_and_summarize_literature",
        "applied_evidence": [],
        "final_classification_changed": False,
    }


def register_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="assess_literature_evidence",
            description=(
                "Assess literature records for candidate ACMG evidence suggestions. "
                "Offline by default; never applies evidence or changes classification."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "gene": {"type": "string"},
                    "variant": {"type": "string"},
                    "transcript": {"type": ["string", "null"]},
                    "disease": {"type": ["string", "null"]},
                    "inheritance": {"type": ["string", "null"]},
                    "phenotype": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                    "literature_records": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "pmids": {"type": "array", "items": {"type": "string"}},
                    "search_query": {"type": ["string", "null"]},
                    "use_online_search": {"type": "boolean"},
                },
                "required": ["gene", "variant"],
                "additionalProperties": False,
            },
            handler=assess_literature_evidence,
            metadata={"stage": "acmg_literature_evidence_agent"},
        )
    )
    registry.register(
        ToolDefinition(
            name="create_reviewed_evidence_draft",
            description=(
                "Convert assess_literature_evidence suggested output into manual "
                "reviewed_evidence draft templates. Never applies evidence or changes "
                "classification."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "literature_assessment_json": {
                        "type": "object",
                        "description": "Full assess_literature_evidence JSON result.",
                        "additionalProperties": True,
                    }
                },
                "required": ["literature_assessment_json"],
                "additionalProperties": False,
            },
            handler=create_reviewed_evidence_draft,
            metadata={"stage": "literature_suggested_to_reviewed_draft"},
        )
    )
    registry.register(
        ToolDefinition(
            name="search_and_summarize_literature",
            description=(
                "Search, deduplicate, and summarize literature records into candidate-only "
                "ACMG suggested evidence and reviewed draft templates. Offline by default; "
                "never applies evidence or changes classification."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "gene": {"type": "string"},
                    "variant": {"type": "string"},
                    "transcript": {"type": ["string", "null"]},
                    "disease": {"type": ["string", "null"]},
                    "inheritance": {"type": ["string", "null"]},
                    "phenotype": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                            {"type": "null"},
                        ]
                    },
                    "criteria": {"type": "array", "items": {"type": "string"}},
                    "literature_records": {
                        "type": "array",
                        "items": {"type": "object", "additionalProperties": True},
                    },
                    "pmids": {"type": "array", "items": {"type": "string"}},
                    "search_query": {"type": ["string", "null"]},
                    "variant_aliases": {"type": "array", "items": {"type": "string"}},
                    "use_online_pubmed": {"type": "boolean"},
                    "use_online_litvar": {"type": "boolean"},
                    "use_online_search": {"type": "boolean"},
                },
                "required": ["gene", "variant"],
                "additionalProperties": False,
            },
            handler=search_and_summarize_literature,
            metadata={"stage": "general_literature_search_and_summary"},
        )
    )
