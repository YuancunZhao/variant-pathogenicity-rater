from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Union


ToolHandler = Callable[[dict[str, Any]], Union[Awaitable[dict[str, Any]], dict[str, Any]]]


class McpToolError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        recoverable: bool = True,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable,
        }


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: ToolHandler
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_mcp_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise McpToolError(
                "DUPLICATE_TOOL",
                f"Tool is already registered: {tool.name}",
                details={"tool": tool.name},
                recoverable=False,
            )
        self._tools[tool.name] = tool

    def list_tools(self) -> list[ToolDefinition]:
        return sorted(self._tools.values(), key=lambda tool: tool.name)

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise McpToolError(
                "TOOL_NOT_FOUND",
                f"Tool not found: {name}",
                details={"tool": name},
            ) from exc

    async def call(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        tool = self.get(name)
        result = tool.handler(arguments or {})
        if inspect.isawaitable(result):
            result = await result
        return result


def discover_and_register_tools(registry: ToolRegistry, package_name: str = __name__) -> None:
    package = importlib.import_module(package_name)
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.ispkg:
            continue
        module = importlib.import_module(f"{package.__name__}.{module_info.name}")
        register_tools = getattr(module, "register_tools", None)
        if register_tools is not None:
            register_tools(registry)
