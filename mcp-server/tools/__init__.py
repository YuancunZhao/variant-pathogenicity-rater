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
        arguments = arguments or {}
        _validate_input_schema(tool.input_schema, arguments, tool.name)
        result = tool.handler(arguments)
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


def _validate_input_schema(schema: dict[str, Any], value: Any, tool_name: str) -> None:
    errors: list[str] = []
    _validate_schema_value(schema, value, "$", errors)
    if errors:
        raise McpToolError(
            "SCHEMA_VALIDATION_ERROR",
            f"Invalid input for tool '{tool_name}'.",
            details={"tool": tool_name, "errors": errors},
        )


def _validate_schema_value(
    schema: dict[str, Any],
    value: Any,
    path: str,
    errors: list[str],
) -> None:
    if "oneOf" in schema:
        if not _matches_any(schema["oneOf"], value, path):
            errors.append(f"{path}: value does not match exactly one allowed schema")
            return
    if "anyOf" in schema:
        if not _matches_any(schema["anyOf"], value, path):
            errors.append(f"{path}: value does not match any allowed schema")

    expected_type = schema.get("type")
    if expected_type is not None and not _type_matches(expected_type, value):
        errors.append(f"{path}: expected {expected_type}")
        return

    allowed_values = schema.get("enum")
    if allowed_values is not None and value not in allowed_values:
        errors.append(f"{path}: expected one of {allowed_values}")
        return

    if expected_type == "object" or isinstance(value, dict):
        if not isinstance(value, dict):
            errors.append(f"{path}: expected object")
            return
        properties = schema.get("properties", {})
        for required_field in schema.get("required", []):
            if required_field not in value:
                errors.append(f"{path}.{required_field}: missing required field")
        additional = schema.get("additionalProperties", True)
        if additional is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: unknown field")
        for key, item in value.items():
            if key in properties:
                _validate_schema_value(properties[key], item, f"{path}.{key}", errors)
            elif isinstance(additional, dict):
                _validate_schema_value(additional, item, f"{path}.{key}", errors)

    if expected_type == "array" or isinstance(value, list):
        if not isinstance(value, list):
            errors.append(f"{path}: expected array")
            return
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_schema_value(item_schema, item, f"{path}[{index}]", errors)


def _matches_any(schemas: list[dict[str, Any]], value: Any, path: str) -> bool:
    matches = 0
    for schema in schemas:
        branch_errors: list[str] = []
        _validate_schema_value(schema, value, path, branch_errors)
        if not branch_errors:
            matches += 1
    return matches > 0


def _type_matches(expected_type: str | list[str], value: Any) -> bool:
    if isinstance(expected_type, list):
        return any(_type_matches(item, value) for item in expected_type)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (isinstance(value, int | float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True
