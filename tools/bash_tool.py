"""
FILE: tools/bash_tool.py
ROLE: Bash Command Execution Tool

DESCRIPTION:
    Executes bash commands in the terminal.
    Self-registers on import.

SECURITY NOTE:
    This tool runs commands with the same permissions as the Python process.
    In production, consider sandboxing or whitelisting commands.
"""
from __future__ import annotations

import subprocess
from typing import Any, Dict

from core import ToolResult
from tools.registry import register_tool


# =============================================================================
# SECURITY: DANGEROUS COMMAND PATTERNS
# =============================================================================

# Patterns that should be blocked or require extra confirmation
DANGEROUS_PATTERNS = [
    "rm -rf /",
    "rm -rf /*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){:|:&};:",  # Fork bomb
    "chmod -R 000 /",
    "chown -R",
]


def is_command_safe(command: str) -> tuple[bool, str]:
    """
    Check if a command contains dangerous patterns.

    Args:
        command: The bash command to check

    Returns:
        Tuple of (is_safe, reason_if_unsafe)
    """
    command_lower = command.lower()

    for pattern in DANGEROUS_PATTERNS:
        if pattern in command_lower:
            return False, f"Command contains dangerous pattern: {pattern}"

    return True, ""


# =============================================================================
# TOOL SCHEMA (OpenAI format)
# =============================================================================

BASH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "execute_bash",
        "description": (
            "Execute a bash command in the terminal. "
            "Use this for file operations, system commands, "
            "and any shell tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute"
                }
            },
            "required": ["command"]
        }
    }
}


# =============================================================================
# HANDLER FUNCTION
# =============================================================================

def execute_bash(command: str, timeout: int = 60) -> ToolResult:
    """
    Execute a bash command in the terminal.

    Args:
        command: The bash command to execute
        timeout: Maximum execution time in seconds

    Returns:
        ToolResult with success status, output, and exit code
    """
    if not command or not command.strip():
        return ToolResult(
            success=False,
            output="",
            error="Empty command",
            exit_code=-1
        )

    # Security check: block dangerous commands
    is_safe, reason = is_command_safe(command)
    if not is_safe:
        return ToolResult(
            success=False,
            output="",
            error=f"Command blocked for security: {reason}",
            exit_code=-1
        )

    try:
        process = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = process.stdout
        if process.stderr:
            output += "\n" + process.stderr

        return ToolResult(
            success=process.returncode == 0,
            output=output.strip() if output.strip() else "(no output)",
            exit_code=process.returncode
        )

    except subprocess.TimeoutExpired:
        return ToolResult(
            success=False,
            output="",
            error=f"Command timed out after {timeout} seconds",
            exit_code=-1
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"Execution error: {str(e)}",
            exit_code=-1
        )


# =============================================================================
# SELF-REGISTRATION
# =============================================================================

# This runs when the module is imported
register_tool(
    name="execute_bash",
    function=execute_bash,
    schema=BASH_TOOL_SCHEMA,
    description="Execute bash commands in the terminal",
    timeout=60
)
