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
    assess_literature_evidence as assess_literature_evidence_service,
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
