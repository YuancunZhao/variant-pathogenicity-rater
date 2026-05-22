from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools import ToolDefinition, ToolRegistry


async def health_check(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "variant-pathogenicity-rater",
        "stage": "mcp_framework",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "mcp_server": "ok",
            "tool_registry": "ok",
        },
        "warnings": [
            "Internal prototype only; outputs are machine proposals and require qualified human review."
        ],
        "echo": arguments,
    }


def register_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="health_check",
            description="Return MCP server health and framework readiness information.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            handler=health_check,
        )
    )
