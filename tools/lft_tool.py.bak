"""
FILE: tools/lft_tool.py
ROLE: File Operations Tool (Using Original LFT)

DESCRIPTION:
    Wrapper for the original LFT.py - a powerful file manipulation tool.
    Uses exact string matching with atomic writes, encoding detection,
    binary file detection, and detailed error messages.

OPERATIONS:
    - read: Read file with line numbers (encoding-aware)
    - write: Create or overwrite file (atomic, with backup option)
    - edit: Replace exact text (must match exactly once)
    - find: Search for text/regex in file
    - info: Get file metadata and preview
    - multiedit: Apply multiple edits atomically

FEATURES (from original LFT):
    - Multi-encoding support (UTF-8, UTF-16, Latin-1, etc.)
    - Binary file detection
    - Atomic writes with verification
    - Backup file creation
    - Dry-run mode
    - Detailed error messages with hints
"""
from __future__ import annotations

import io
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional

from core import ToolResult
from tools.registry import register_tool
from tools import lft  # Original LFT module


# =============================================================================
# TOOL SCHEMA (OpenAI format) - Matches original LFT capabilities
# =============================================================================

LFT_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lft",
        "description": (
            "Powerful file operations with exact string matching. "
            "Commands: read (show file with line numbers), "
            "edit (replace exact text - must match once), "
            "find (search pattern), "
            "write (create/overwrite file), "
            "info (file metadata + preview), "
            "multiedit (multiple atomic edits). "
            "ALWAYS read file first before editing to get exact text. "
            "Supports multiple encodings, atomic writes, and binary detection."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["read", "edit", "find", "write", "info", "multiedit"],
                    "description": "The file operation to perform"
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the file"
                },
                "old_string": {
                    "type": "string",
                    "description": "For edit: exact text to replace (must match exactly once)"
                },
                "new_string": {
                    "type": "string",
                    "description": "For edit/write: the replacement or new content"
                },
                "pattern": {
                    "type": "string",
                    "description": "For find: text pattern to search for"
                },
                "start_line": {
                    "type": "integer",
                    "description": "For read: starting line number (default: 1)"
                },
                "end_line": {
                    "type": "integer",
                    "description": "For read: ending line number, -1 for end of file"
                },
                "use_regex": {
                    "type": "boolean",
                    "description": "For find: use regex pattern (default: false)"
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "For find: case-insensitive search (default: false)"
                },
                "context": {
                    "type": "integer",
                    "description": "For find: show N lines of context around matches"
                },
                "backup": {
                    "type": "boolean",
                    "description": "Create .bak file before editing (default: false)"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview changes without modifying (default: false)"
                },
                "multiedit_content": {
                    "type": "string",
                    "description": "For multiedit: edit operations in OLD/NEW format"
                }
            },
            "required": ["command", "file_path"]
        }
    }
}


# =============================================================================
# HANDLER FUNCTION
# =============================================================================

def execute_lft(
    command: str,
    file_path: str,
    old_string: str = "",
    new_string: str = "",
    pattern: str = "",
    start_line: int = 1,
    end_line: int = -1,
    use_regex: bool = False,
    ignore_case: bool = False,
    context: int = 0,
    backup: bool = False,
    dry_run: bool = False,
    multiedit_content: str = "",
    timeout: int = 30
) -> ToolResult:
    """
    Execute LFT file operations using the original LFT module.

    Args:
        command: Operation to perform (read, edit, find, write, info, multiedit)
        file_path: Path to the file
        old_string: Text to replace (for edit)
        new_string: Replacement text or content to write
        pattern: Search pattern (for find)
        start_line: Starting line for read
        end_line: Ending line for read (-1 for end)
        use_regex: Use regex for find
        ignore_case: Case-insensitive find
        context: Context lines for find
        backup: Create backup before editing
        dry_run: Preview without modifying
        multiedit_content: Multiedit operations
        timeout: Not used for file operations

    Returns:
        ToolResult with success status and output
    """
    try:
        path = Path(file_path).expanduser()

        # Capture LFT output (it prints to stdout)
        old_stdout = sys.stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            if command == "read":
                exit_code = lft.cmd_read(path, start_line, end_line)

            elif command == "edit":
                if not old_string:
                    raise ValueError("old_string is required for edit command")
                if not new_string and new_string != "":
                    raise ValueError("new_string is required for edit command")
                exit_code = lft.cmd_edit(
                    path,
                    old_string,
                    new_string,
                    backup=backup,
                    dry_run=dry_run
                )

            elif command == "find":
                if not pattern:
                    raise ValueError("pattern is required for find command")
                exit_code = lft.cmd_find(
                    path,
                    pattern,
                    use_regex=use_regex,
                    context=context,
                    ignore_case=ignore_case
                )

            elif command == "write":
                exit_code = lft.cmd_write(
                    path,
                    new_string,
                    backup=backup,
                    dry_run=dry_run
                )

            elif command == "info":
                exit_code = lft.cmd_info(path)

            elif command == "multiedit":
                if not multiedit_content:
                    raise ValueError("multiedit_content is required for multiedit command")
                exit_code = lft.cmd_multiedit(
                    path,
                    multiedit_content,
                    backup=backup,
                    dry_run=dry_run
                )

            else:
                raise ValueError(f"Unknown LFT command: {command}")

        finally:
            sys.stdout = old_stdout

        output = captured_output.getvalue()

        return ToolResult(
            success=(exit_code == 0),
            output=output,
            exit_code=exit_code
        )

    except lft.LFTError as e:
        return ToolResult(
            success=False,
            output="",
            error=f"{e.code}: {e.message}\n{e.hint}",
            exit_code=1
        )
    except ValueError as e:
        return ToolResult(
            success=False,
            output="",
            error=str(e),
            exit_code=-1
        )
    except Exception as e:
        return ToolResult(
            success=False,
            output="",
            error=f"LFT error: {str(e)}",
            exit_code=-1
        )


# =============================================================================
# SELF-REGISTRATION
# =============================================================================

register_tool(
    name="lft",
    function=execute_lft,
    schema=LFT_TOOL_SCHEMA,
    description="Powerful file operations (read, write, edit, find, info, multiedit)",
    timeout=30
)
