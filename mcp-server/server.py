from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from config import ServerConfig
from tools import McpToolError, ToolRegistry, discover_and_register_tools

JSONRPC_VERSION = "2.0"
MCP_PROTOCOL_VERSION = "2024-11-05"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        details = getattr(record, "details", None)
        if details is not None:
            payload["details"] = details
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def build_registry(config: ServerConfig | None = None) -> ToolRegistry:
    config = config or ServerConfig.from_env()
    registry = ToolRegistry()
    discover_and_register_tools(registry, config.tools_package)
    if not config.enable_health_tool:
        registry._tools.pop("health_check", None)
    return registry


class McpServer:
    def __init__(self, config: ServerConfig, registry: ToolRegistry) -> None:
        self.config = config
        self.registry = registry
        self.logger = logging.getLogger(__name__)

    async def serve_stdio(self) -> None:
        self.logger.info(
            "MCP server started",
            extra={"details": {"transport": "stdio", "server": self.config.server_name}},
        )
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if line == "":
                break
            if not line.strip():
                continue
            response = await self.handle_message(line)
            if response is not None:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                await asyncio.to_thread(sys.stdout.flush)

    async def handle_message(self, raw_message: str) -> dict[str, Any] | list[dict[str, Any]] | None:
        try:
            payload = json.loads(raw_message)
            if isinstance(payload, list):
                return [response for response in [await self.handle_request(item) for item in payload] if response]
            return await self.handle_request(payload)
        except Exception as exc:
            self.logger.exception("Failed to handle JSON-RPC message")
            return self.error_response(None, exc)

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        try:
            if method == "initialize":
                result = self.initialize()
            elif method == "notifications/initialized":
                return None
            elif method == "tools/list":
                result = self.list_tools()
            elif method == "tools/call":
                result = await self.call_tool(params)
            else:
                raise McpToolError(
                    "METHOD_NOT_FOUND",
                    f"Unsupported MCP method: {method}",
                    details={"method": method},
                )
            return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}
        except Exception as exc:
            details = {"method": method}
            if isinstance(exc, McpToolError):
                details["error"] = exc.to_dict()
                self.logger.warning("MCP request failed", extra={"details": details})
            else:
                self.logger.exception("MCP request failed", extra={"details": details})
            return self.error_response(request_id, exc)

    def initialize(self) -> dict[str, Any]:
        return {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": self.config.server_name,
                "version": self.config.server_version,
            },
        }

    def list_tools(self) -> dict[str, Any]:
        return {"tools": [tool.to_mcp_tool() for tool in self.registry.list_tools()]}

    async def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = params.get("name")
        if not isinstance(tool_name, str):
            raise McpToolError(
                "SCHEMA_VALIDATION_ERROR",
                "tools/call requires a string 'name'.",
                details={"params": params},
            )

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise McpToolError(
                "SCHEMA_VALIDATION_ERROR",
                "tools/call 'arguments' must be an object.",
                details={"tool": tool_name},
            )

        result = await self.registry.call(tool_name, arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": False,
        }

    def error_response(self, request_id: Any, exc: BaseException) -> dict[str, Any]:
        if isinstance(exc, McpToolError):
            error_data = exc.to_dict()
            message = exc.message
        else:
            error_data = {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Unexpected MCP server error.",
                "details": {"type": exc.__class__.__name__},
                "recoverable": False,
            }
            message = error_data["message"]
        return {
            "jsonrpc": JSONRPC_VERSION,
            "id": request_id,
            "error": {
                "code": -32603,
                "message": message,
                "data": error_data,
            },
        }


async def main() -> None:
    config = ServerConfig.from_env()
    configure_logging(config.log_level)
    registry = build_registry(config)
    await McpServer(config, registry).serve_stdio()


if __name__ == "__main__":
    asyncio.run(main())
