"""
FILE: tools/registry.py
ROLE: Tool Registry (Dynamic Tool Management)

DESCRIPTION:
    Central registry for all tools. Tools register themselves at import time.
    This allows adding new tools by simply creating a new file in tools/

DESIGN PATTERN:
    - Registry Pattern: Tools register themselves
    - Dynamic dispatch: Execute any tool by name
    - Schema generation: Auto-generate OpenAI tool schemas

USAGE:
    # Register a tool (usually done in tool file)
    register_tool(
        name="my_tool",
        function=my_handler,
        schema={...},        # OpenAI tool schema
        description="..."    # Human-readable description
    )

    # Execute a tool
    result = execute("my_tool", {"arg": "value"})

    # Get all schemas for LLM
    schemas = get_schemas()
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Union

from core import ToolResult


# =============================================================================
# REGISTRY DATA STRUCTURE
# =============================================================================

class ToolRegistry:
    """
    Central registry for all tools.

    Stores tool metadata including:
    - Execution function
    - OpenAI schema
    - Description
    - Timeout settings
    """

    _tools: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register(
        cls,
        name: str,
        function: Callable,
        schema: Dict[str, Any],
        description: str = "",
        timeout: int = 60
    ) -> None:
        """
        Register a tool.

        Args:
            name: Unique tool name
            function: Handler function (returns ToolResult)
            schema: OpenAI-format tool schema
            description: Human-readable description
            timeout: Default timeout in seconds
        """
        cls._tools[name] = {
            "function": function,
            "schema": schema,
            "description": description,
            "timeout": timeout
        }

    @classmethod
    def get(cls, name: str) -> Optional[Dict[str, Any]]:
        """Get tool by name."""
        return cls._tools.get(name)

    @classmethod
    def exists(cls, name: str) -> bool:
        """Check if tool exists."""
        return name in cls._tools

    @classmethod
    def list_all(cls) -> Dict[str, str]:
        """List all tools with descriptions."""
        return {
            name: info["description"]
            for name, info in cls._tools.items()
        }

    @classmethod
    def get_schemas(cls) -> List[Dict[str, Any]]:
        """Get all tool schemas for LLM."""
        return [info["schema"] for info in cls._tools.values()]


# =============================================================================
# PUBLIC API FUNCTIONS
# =============================================================================

def register_tool(
    name: str,
    function: Callable,
    schema: Dict[str, Any],
    description: str = "",
    timeout: int = 60
) -> None:
    """
    Register a tool in the registry.

    Args:
        name: Unique tool name
        function: Handler function that returns ToolResult
        schema: OpenAI-format tool schema
        description: Human-readable description
        timeout: Default timeout in seconds

    Example:
        register_tool(
            name="echo",
            function=echo_handler,
            schema={
                "type": "function",
                "function": {
                    "name": "echo",
                    "parameters": {...}
                }
            },
            description="Echo the input text"
        )
    """
    ToolRegistry.register(name, function, schema, description, timeout)


def execute(
    name: str,
    arguments: Union[str, Dict[str, Any]],
    timeout: Optional[int] = None
) -> ToolResult:
    """
    Execute a tool by name.

    Args:
        name: Tool name
        arguments: Tool arguments (JSON string or dict)
        timeout: Override timeout (uses tool default if None)

    Returns:
        ToolResult with success status, output, and error info

    Raises:
        ValueError: If tool doesn't exist
    """
    tool = ToolRegistry.get(name)
    if not tool:
        return ToolResult(
            success=False,
            output="",
            error=f"Unknown tool: {name}",
            exit_code=-1
        )

    # Parse arguments if string
    if isinstance(arguments, str):
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
    else:
        args = arguments or {}

    # Get timeout
    exec_timeout = timeout if timeout is not None else tool["timeout"]

    # Execute
    try:
        return tool["function"](**args, timeout=exec_timeout)
    except TypeError:
        # Function doesn't accept timeout
        return tool["function"](**args)
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Tool execution error: {str(e)}",
            exit_code=-1
        )


def get_schemas() -> List[Dict[str, Any]]:
    """
    Get all tool schemas in OpenAI format.

    Returns:
        List of tool schemas for passing to LLM
    """
    return ToolRegistry.get_schemas()


def list_tools() -> Dict[str, str]:
    """
    List all available tools with descriptions.

    Returns:
        Dict mapping tool names to descriptions
    """
    return ToolRegistry.list_all()


def tool_exists(name: str) -> bool:
    """
    Check if a tool is registered.

    Args:
        name: Tool name

    Returns:
        True if tool exists
    """
    return ToolRegistry.exists(name)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def parse_tool_arguments(arguments_json: str) -> Dict[str, Any]:
    """
    Parse JSON arguments string to dict.

    Args:
        arguments_json: JSON string of arguments

    Returns:
        Parsed dict, or empty dict on error
    """
    if not arguments_json:
        return {}
    try:
        return json.loads(arguments_json)
    except json.JSONDecodeError:
        return {}


def build_tool_result_message(
    tool_call_id: str,
    result: str
) -> Dict[str, Any]:
    """
    Build a tool role message for conversation history.

    Args:
        tool_call_id: ID from the tool call
        result: Tool execution result

    Returns:
        Message dict in OpenAI format
    """
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": result
    }


def build_assistant_tool_message(
    tool_calls: List[Dict[str, Any]],
    content: str = ""
) -> Dict[str, Any]:
    """
    Build an assistant message with tool calls.

    Args:
        tool_calls: List of tool calls
        content: Optional content

    Returns:
        Message dict in OpenAI format
    """
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls
    }
