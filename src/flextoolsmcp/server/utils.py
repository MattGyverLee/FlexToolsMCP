#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions for MCP server schema generation and validation.

Provides helpers to convert Pydantic models to MCP Tool schemas,
validate input against models, and handle type conversions.
"""

from typing import Type, Any, Dict
from pydantic import BaseModel


def model_to_tool_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """
    Convert a Pydantic model to an MCP Tool inputSchema.

    Args:
        model: A Pydantic BaseModel subclass

    Returns:
        MCP-compatible JSON Schema dict

    Example:
        >>> from server.models import SearchCapabilityInput
        >>> schema = model_to_tool_schema(SearchCapabilityInput)
        >>> # schema is now a proper MCP inputSchema dict
    """
    # Get the JSON schema from Pydantic
    json_schema = model.model_json_schema()

    # Convert to MCP format (remove unnecessary fields)
    result = {
        "type": "object",
        "properties": json_schema.get("properties", {}),
        "required": json_schema.get("required", []),
    }

    # Copy over definitions if they exist (for complex types)
    if "$defs" in json_schema:
        result["$defs"] = json_schema["$defs"]

    return result


def validate_and_parse(model: Type[BaseModel], data: Dict[str, Any]) -> BaseModel:
    """
    Validate input data against a Pydantic model and return parsed instance.

    Args:
        model: A Pydantic BaseModel subclass
        data: Input data dict to validate

    Returns:
        Validated model instance

    Raises:
        ValidationError: If validation fails

    Example:
        >>> from server.models import SearchCapabilityInput
        >>> input_data = {"query": "find entries"}
        >>> validated = validate_and_parse(SearchCapabilityInput, input_data)
        >>> # validated.query is now type-safe and coerced as needed
    """
    return model(**data)


def get_model_description(model: Type[BaseModel]) -> str:
    """
    Extract description from Pydantic model docstring.

    Args:
        model: A Pydantic BaseModel subclass

    Returns:
        Model docstring or empty string
    """
    return (model.__doc__ or "").strip()
