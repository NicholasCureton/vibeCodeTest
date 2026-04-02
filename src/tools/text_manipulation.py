#!/usr/bin/env python3
"""
text_manipulation.py - Git-Safe Search and Replace for Code Editing

A robust text manipulation tool designed for LLM-assisted code editing workflows.
Mimics familiar Unix tool behavior (rg, bat, sed) for LLM familiarity.

Features:
    - SEARCH: Pattern matching with ripgrep + whitespace visualization via bat
    - REPLACE: Atomic line replacement using Split-and-Glue algorithm
    - SAFETY: All changes are git-rollback safe

Output Formats (LLM-Training-Compatible):
    - Search matches: `file:line:content` (git grep / rg style)
    - Visualization: `  45 def foo():␊` (bat -A style with whitespace markers)
    - Errors: `fatal: <message>` to stderr (git style)

Example CLI Usage:
    $ text_manipulation search "def process" src/main.py --context 2
    $ text_manipulation replace --lines 45-52 src/main.py --snippet new_code.txt

Example Tool Call (for LLM):
    {
        "command": "search",
        "file_path": "src/main.py",
        "pattern": "def process_data",
        "context": 2
    }

Version: 4.0.0
"""

from __future__ import annotations

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

# Type checking import to avoid circular dependency
if TYPE_CHECKING:
    from ..core import ToolResult


# =============================================================================
# CONSTANTS AND CONFIGURATION
# =============================================================================

#: bat/batcat command name (batcat on Ubuntu, bat on macOS)
BAT_COMMAND: str = "batcat" if shutil.which("batcat") else "bat"

#: ripgrep command name
RG_COMMAND: str = "rg"

#: Default context lines for search (matches rg default behavior)
DEFAULT_CONTEXT_LINES: int = 2

#: File encoding for reading/writing (UTF-8 with error tolerance)
FILE_ENCODING: str = "utf-8"

#: Encoding error handling strategy (preserves invalid bytes safely)
FILE_ENCODING_ERRORS: str = "surrogateescape"

#: Exit codes (following Unix conventions)
EXIT_SUCCESS: int = 0
EXIT_ERROR: int = 1

#: bat flags for whitespace visualization
#: Shows: · (space), → (tab), ␊ (newline)
BAT_VISUALIZE_FLAGS: List[str] = [
    "-A",                      # --show-all: Display all non-printable characters
    "--style=numbers",         # Show line numbers
    "--color=never",           # Disable ANSI colors (LLM can't parse them)
    "--decorations=always",    # Force decorations even in non-TTY
    "--paging=never",          # Disable interactive pager
]

#: ripgrep flags for pattern search
#: Output format: file:line:content (git grep compatible)
RG_FLAGS: List[str] = [
    "-n",                      # --line-number: Show line numbers
    "--color=never",           # Disable ANSI colors
]


# =============================================================================
# ERROR HANDLING
# =============================================================================


class TextManipulationError(Exception):
    """
    Base exception for text manipulation errors.

    All text manipulation errors inherit from this base class.
    Allows catching all tool errors with a single except clause.
    """
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class FileNotFound(TextManipulationError):
    """Raised when a required file does not exist."""
    pass


class PermissionDenied(TextManipulationError):
    """Raised when file access is denied."""
    pass


class InvalidLineRange(TextManipulationError):
    """Raised when line range format is invalid."""
    pass


class ToolNotFoundError(TextManipulationError):
    """Raised when a required external tool is not found."""
    pass


class EncodingError(TextManipulationError):
    """Raised when file encoding cannot be handled."""
    pass


def format_error_message(message: str) -> str:
    """
    Format error message with 'fatal:' prefix for CLI output.

    Args:
        message: Error description.

    Returns:
        Formatted string with 'fatal:' prefix.
    """
    return f"fatal: {message}"


def print_fatal(message: str) -> None:
    """
    Print error message to stderr with 'fatal:' prefix.

    Follows git-style error reporting for consistency.
    Used by CLI commands for error output.

    Args:
        message: Error description (should be concise and actionable).

    Example:
        >>> print_fatal("file 'config.py' not found")
        fatal: file 'config.py' not found
    """
    print(f"fatal: {message}", file=sys.stderr)


def raise_file_not_found(file_path: Path) -> None:
    """Raise FileNotFound error."""
    raise FileNotFound(f"file '{file_path}' not found")


def raise_permission_denied(file_path: Path, operation: str = "access") -> None:
    """Raise PermissionDenied error."""
    raise PermissionDenied(f"permission denied: cannot {operation} '{file_path}'")


def raise_invalid_line_range(range_str: str, reason: str) -> None:
    """Raise InvalidLineRange error."""
    raise InvalidLineRange(f"invalid line range '{range_str}': {reason}")


def raise_tool_not_found(tool_name: str) -> None:
    """Raise ToolNotFoundError."""
    raise ToolNotFoundError(f"command not found: '{tool_name}' (please install {tool_name})")


# =============================================================================
# FILE I/O OPERATIONS
# =============================================================================


def read_file_lines(file_path: Path) -> List[str]:
    """
    Read file and return all lines with line endings preserved.

    Uses surrogateescape error handling to safely process files with
    mixed or invalid encodings. Falls back to latin-1 if UTF-8 fails.

    Args:
        file_path: Path to file to read.

    Returns:
        List of strings, each including its newline character.

    Raises:
        FileNotFound: If file doesn't exist.
        PermissionDenied: If file cannot be read.
        EncodingError: If file encoding is unsupported.

    Example:
        >>> lines = read_file_lines(Path("src/main.py"))
        >>> lines[0]
        'def main():\\n'
    """
    if not file_path.exists():
        raise_file_not_found(file_path)

    try:
        with open(file_path, "r", encoding=FILE_ENCODING, errors=FILE_ENCODING_ERRORS) as file_handle:
            return file_handle.readlines()
    except UnicodeDecodeError:
        # Fallback for files with completely broken encoding
        try:
            with open(file_path, "r", encoding="latin-1") as file_handle:
                return file_handle.readlines()
        except Exception:
            raise EncodingError(f"cannot read '{file_path}': unsupported encoding (tried UTF-8 and latin-1)")
    except PermissionError:
        raise_permission_denied(file_path, "read")
    except OSError as exc:
        raise EncodingError(f"I/O error reading '{file_path}': {exc}")


def write_file_lines_atomic(file_path: Path, lines: List[str]) -> None:
    """
    Write lines to file atomically using temporary file + rename.

    Prevents file corruption from crashes, power loss, or interrupts.
    Temporary file is created in same directory for atomic rename
    (POSIX atomic rename requires same filesystem).

    Args:
        file_path: Path to target file.
        lines: List of strings to write (each should include newline).

    Raises:
        FileNotFound: If parent directory doesn't exist.
        PermissionDenied: If file cannot be written.
        OSError: If disk error occurs.
    """
    parent_dir = file_path.parent

    if not parent_dir.exists():
        raise_file_not_found(parent_dir)

    temp_fd: Optional[int] = None
    temp_path: Optional[Path] = None

    try:
        # Create temp file in same directory (required for atomic rename)
        temp_fd, temp_path_str = tempfile.mkstemp(
            dir=str(parent_dir),
            prefix=".tmp_edit_",
            suffix=".txt",
        )
        temp_path = Path(temp_path_str)

        # Write content to temp file
        with os.fdopen(temp_fd, "w", encoding=FILE_ENCODING, errors=FILE_ENCODING_ERRORS) as file_handle:
            temp_fd = None  # Context manager now owns the fd
            file_handle.writelines(lines)
            file_handle.flush()
            os.fsync(file_handle.fileno())  # Force data to disk

        # Atomic rename (POSIX-safe on same filesystem)
        os.replace(temp_path, file_path)
        temp_path = None  # Success - no cleanup needed

    except PermissionError:
        raise_permission_denied(file_path, "write")
    except OSError as exc:
        raise OSError(f"disk error writing '{file_path}': {exc}")
    finally:
        # Cleanup temp file on failure
        if temp_fd is not None:
            try:
                os.close(temp_fd)
            except OSError:
                pass  # Already closed or failed
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass  # Already removed


# =============================================================================
# SEARCH COMMAND IMPLEMENTATION
# =============================================================================


def run_ripgrep_search(
    pattern: str,
    file_path: Path,
    context_lines: int
) -> Tuple[List[str], int]:
    """
    Search file using ripgrep with line numbers and context.

    Args:
        pattern: Search pattern (regex supported).
        file_path: Path to file to search.
        context_lines: Number of context lines before/after matches.

    Returns:
        Tuple of (match_lines, exit_code):
            - exit_code 0: Matches found
            - exit_code 1: No matches (not an error)
            - exit_code 2+: Actual error

    Raises:
        ToolNotFoundError: If rg not found.

    Example:
        >>> lines, code = run_ripgrep_search("def main", Path("src.py"), 2)
        >>> lines[0]
        '10:def main():'
    """
    if not shutil.which(RG_COMMAND):
        raise ToolNotFoundError(f"ripgrep not found (please install rg)")

    cmd = [RG_COMMAND] + RG_FLAGS + [f"-C{context_lines}", pattern, str(file_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            return result.stdout.splitlines(), EXIT_SUCCESS
        elif result.returncode == 1:
            return [], 1  # No matches - not an error
        elif result.returncode == 2:
            # rg returns 2 for errors like permission denied
            raise PermissionDenied(f"rg error: {result.stderr.strip()}")
        else:
            raise TextManipulationError(f"rg error (exit code {result.returncode}): {result.stderr.strip()}")
    except subprocess.SubprocessError as exc:
        raise TextManipulationError(f"subprocess error running rg: {exc}")


def run_git_grep_search(pattern: str, file_path: Path) -> Tuple[List[str], int]:
    """
    Search file using git grep (fallback when rg unavailable).

    Note: Only works inside git repositories.

    Args:
        pattern: Search pattern.
        file_path: Path to file to search.

    Returns:
        Tuple of (match_lines, exit_code).

    Raises:
        ToolNotFoundError: If git not found.
        TextManipulationError: If git grep fails.
    """
    if not shutil.which("git"):
        raise ToolNotFoundError("git not found (please install git)")

    cmd = ["git", "grep", "-n", pattern, str(file_path)]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            return result.stdout.splitlines(), EXIT_SUCCESS
        elif result.returncode == 1:
            return [], 1  # No matches
        elif result.returncode == 128:
            # git returns 128 for fatal errors (not in repo, etc.)
            raise TextManipulationError(f"git grep error: {result.stderr.strip()}")
        else:
            raise TextManipulationError(f"git grep error (exit code {result.returncode}): {result.stderr.strip()}")
    except subprocess.SubprocessError as exc:
        raise TextManipulationError(f"subprocess error running git grep: {exc}")


def run_python_search(
    pattern: str,
    file_path: Path,
    context_lines: int
) -> Tuple[List[str], int]:
    """
    Fallback search using Python string matching (no regex).

    Slower and less feature-rich than rg/git grep.
    Only used when both rg and git are unavailable.

    Args:
        pattern: Search pattern (literal string, no regex).
        file_path: Path to file to search.
        context_lines: Number of context lines before/after matches.

    Returns:
        Tuple of (match_lines, exit_code).
    """
    lines = read_file_lines(file_path)
    matches: List[str] = []

    for idx, line in enumerate(lines):
        if pattern in line:
            start_idx = max(0, idx - context_lines)
            end_idx = min(len(lines), idx + context_lines + 1)

            for j in range(start_idx, end_idx):
                separator = ":" if j == idx else "-"
                matches.append(f"{j + 1}{separator}{lines[j].rstrip()}")

    return matches, EXIT_SUCCESS if matches else 1


def run_bat_visualize(
    file_path: Path,
    line_start: int,
    line_end: int
) -> List[str]:
    """
    Visualize file content with whitespace markers using bat.

    Shows hidden characters that often cause bugs:
        · (middle dot) = space
        → (right arrow) = tab
        ␊ (newline symbol) = line feed

    Args:
        file_path: Path to file to visualize.
        line_start: First line to show (1-indexed).
        line_end: Last line to show (1-indexed).

    Returns:
        List of visualized lines with whitespace markers.

    Raises:
        ToolNotFoundError: If bat not found.
        TextManipulationError: If bat fails.
    """
    if not shutil.which(BAT_COMMAND):
        raise ToolNotFoundError(f"'{BAT_COMMAND}' not found (please install bat or batcat)")

    cmd = (
        [BAT_COMMAND]
        + BAT_VISUALIZE_FLAGS
        + [f"--line-range={line_start}:{line_end}", str(file_path)]
    )

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode == 0:
            # Normalize tab visualization to arrow (→) for LLM-friendliness
            # batcat 0.24+ uses ├──┤ for tabs, but → is more common in training data
            lines = result.stdout.splitlines()
            return [line.replace('├──┤', '→') for line in lines]
        else:
            raise TextManipulationError(f"bat error: {result.stderr.strip()}")
    except subprocess.SubprocessError as exc:
        raise TextManipulationError(f"subprocess error running bat: {exc}")


def extract_line_range_from_matches(match_lines: List[str]) -> Tuple[int, int]:
    """
    Extract min and max line numbers from ripgrep-style output.

    Parses lines like "45:content" or "45-context" to find the range.

    Args:
        match_lines: List of rg/git grep output lines.

    Returns:
        Tuple of (min_line, max_line). Returns (1, 1) if no lines parsed.

    Example:
        >>> lines = ["45:def foo():", "46-    pass", "50:def bar():"]
        >>> extract_line_range_from_matches(lines)
        (45, 50)
    """
    min_line: float = float('inf')
    max_line: int = 0

    for line in match_lines:
        # Extract leading number before : or -
        num_str = ""
        for char in line:
            if char.isdigit():
                num_str += char
            elif char in (":", "-"):
                break
            else:
                break

        if num_str:
            num = int(num_str)
            min_line = min(min_line, num)
            max_line = max(max_line, num)

    start_line = max(1, int(min_line)) if min_line != float('inf') else 1
    end_line = int(max_line) if max_line > 0 else 1

    return start_line, end_line


def execute_search(args: argparse.Namespace) -> int:
    """
    Execute search command: find pattern and display with visualization.

    Output format (LLM-friendly, matches training data):
        === MATCHES ===
        file.py:45:def foo():
        file.py:46-    pass

        === VISUALIZATION ===
          45 def foo():␊
          46     pass␊

    Args:
        args: Parsed arguments with pattern, file, context.

    Returns:
        Exit code (0 for success or no matches, 1 for errors).
    """
    file_path = Path(args.file)

    try:
        if not file_path.exists():
            raise_file_not_found(file_path)

        # Select best available search tool
        if shutil.which(RG_COMMAND):
            match_lines, _ = run_ripgrep_search(args.pattern, file_path, args.context)
        elif shutil.which("git"):
            match_lines, _ = run_git_grep_search(args.pattern, file_path)
        else:
            match_lines, _ = run_python_search(args.pattern, file_path, args.context)

        # Handle no matches (not an error)
        if not match_lines:
            print(f"No matches found for '{args.pattern}' in {file_path}")
            return EXIT_SUCCESS

        # Read file for visualization
        all_lines = read_file_lines(file_path)
        total_lines = len(all_lines)

        # Calculate visualization range
        vis_start, vis_end = extract_line_range_from_matches(match_lines)
        vis_start = int(max(1, vis_start - args.context))
        vis_end = int(min(total_lines, vis_end + args.context))

        # Get batcat output with whitespace markers for the visible range
        vis_lines = run_bat_visualize(file_path, vis_start, vis_end)

        # Print file path once (token-efficient)
        print(f"{file_path}:")

        # Build a map of line number to batcat-formatted content (with whitespace markers)
        bat_lines = {}
        for bat_line in vis_lines:
            # Parse batcat output: "   42 content␊"
            stripped = bat_line.lstrip()
            parts = stripped.split(' ', 1)
            if len(parts) >= 1:
                try:
                    line_num = int(parts[0])
                    content = parts[1] if len(parts) > 1 else ""
                    bat_lines[line_num] = content
                except ValueError:
                    pass

        # Print matches with whitespace markers
        for line in match_lines:
            # Extract line number from rg output
            if ":" in line:
                line_num_str, _ = line.split(":", 1)
                separator = ":"
            elif "-" in line and not line.startswith("-"):
                line_num_str, _ = line.split("-", 1)
                separator = "-"
            else:
                continue

            try:
                line_num = int(line_num_str)
                # Use batcat-formatted content if available, otherwise use rg content
                if line_num in bat_lines:
                    print(f"{line_num}{separator}{bat_lines[line_num]}")
                else:
                    # Fallback: just add newline marker
                    content = line.split(separator, 1)[1] if separator in line else ""
                    print(f"{line_num}{separator}{content}␊")
            except ValueError:
                continue

        return EXIT_SUCCESS

    except TextManipulationError as exc:
        print_fatal(exc.message)
        return EXIT_ERROR


# =============================================================================
# REPLACE COMMAND IMPLEMENTATION
# =============================================================================


def parse_line_range(range_str: str) -> Tuple[int, int]:
    """
    Parse line range string like "45-52" into (start, end) tuple.

    Lines are 1-indexed (consistent with sed, awk, git, editors).

    Args:
        range_str: Range string in format "START-END".

    Returns:
        Tuple of (start_line, end_line) as 1-indexed integers.

    Raises:
        InvalidLineRange: If format invalid, non-integer, non-contiguous, or start > end.

    Example:
        >>> parse_line_range("45-52")
        (45, 52)
        >>> parse_line_range("  1  -  10  ")
        (1, 10)
    """
    # Check for non-contiguous ranges (commas) BEFORE splitting on dash
    if "," in range_str:
        raise_invalid_line_range(
            range_str,
            "non-contiguous line ranges are not supported. "
            "Use a single continuous range like '1-5'. "
            "To edit multiple non-contiguous lines, make separate tool calls."
        )

    parts = range_str.strip().split("-")

    if len(parts) != 2:
        raise_invalid_line_range(
            range_str,
            "expected format: START-END (e.g., 45-52). "
            "Only continuous line ranges are supported."
        )

    try:
        start = int(parts[0].strip())
        end = int(parts[1].strip())
    except ValueError as exc:
        raise_invalid_line_range(range_str, f"line numbers must be integers: {exc}")

    if start < 1:
        raise_invalid_line_range(range_str, "lines are 1-indexed (starting at 1)")
    if start > end:
        raise_invalid_line_range(
            range_str,
            f"start ({start}) > end ({end}). Line numbers must be in ascending order."
        )

    return start, end


def execute_replace(args: argparse.Namespace) -> int:
    """
    Execute replace command: replace lines START-END with snippet content.

    Algorithm (Split-and-Glue):
        1. Read original file: [line1, line2, ..., lineN]
        2. Split: top = lines[:start-1], bottom = lines[end:]
        3. Read snippet: [new1, new2, ...]
        4. Glue: result = top + snippet + bottom
        5. Write atomically via temp file + rename

    This is like `sed 'START,ENDd'` + inserting snippet, but safer.

    Args:
        args: Parsed arguments with lines, file, snippet.

    Returns:
        Exit code (0 for success, 1 for errors).
    """
    file_path = Path(args.file)
    snippet_path = Path(args.snippet)

    try:
        # Validate input files exist
        if not file_path.exists():
            raise_file_not_found(file_path)
        if not snippet_path.exists():
            raise_file_not_found(snippet_path)

        # Parse and validate line range
        start_line, end_line = parse_line_range(args.lines)

        # Read original file
        old_lines = read_file_lines(file_path)
        total_old_lines = len(old_lines)

        # Validate range is within file bounds
        if end_line > total_old_lines:
            raise_invalid_line_range(
                args.lines,
                f"range {start_line}-{end_line} out of bounds (file has {total_old_lines} lines)"
            )

        # Read snippet content
        new_content = read_file_lines(snippet_path)

        # Split-and-Glue algorithm
        # Note: Python is 0-indexed, but user lines are 1-indexed
        top = old_lines[: start_line - 1]    # Lines before replacement
        middle = new_content                  # New content to insert
        bottom = old_lines[end_line:]         # Lines after replacement

        result = top + middle + bottom
        total_new_lines = len(result)

        # Atomic write to prevent corruption
        write_file_lines_atomic(file_path, result)

        # Success message (git-style: minimal, actionable)
        print(f"Replaced lines {start_line}-{end_line} in {file_path}")
        print(f"(was {total_old_lines} lines, now {total_new_lines} lines)")
        print(f"Run: git diff {file_path}")

        return EXIT_SUCCESS

    except TextManipulationError as exc:
        print_fatal(exc.message)
        return EXIT_ERROR


# =============================================================================
# CLI ARGUMENT PARSER
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """
    Create CLI argument parser with search and replace subcommands.

    Returns:
        Configured ArgumentParser ready for parsing.

    Example:
        >>> parser = create_parser()
        >>> args = parser.parse_args(["search", "def main", "src.py"])
    """
    parser = argparse.ArgumentParser(
        prog="text_manipulation",
        description="Git-safe text manipulation for code editing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
=============================================================================
EXAMPLES
=============================================================================

# Search for a function definition with 3 lines of context
$ text_manipulation search "def process_data" src/main.py --context 3

# Replace lines 45-52 with content from a snippet file
$ text_manipulation replace --lines 45-52 src/main.py --snippet new_code.txt

=============================================================================
TYPICAL WORKFLOW
=============================================================================

1. SEARCH to find line numbers:
   $ text_manipulation search "old_function" src/main.py

2. CREATE snippet file with replacement content:
   $ echo "def new_function():..." > /tmp/fix.txt

3. REPLACE the specific lines:
   $ text_manipulation replace --lines 45-50 src/main.py --snippet /tmp/fix.txt

4. REVIEW changes:
   $ git diff src/main.py

5. COMMIT if good, or ROLLBACK if wrong:
   $ git add src/main.py && git commit -m "refactor: use new_function"
   # OR if wrong:
   $ git restore src/main.py

=============================================================================
OUTPUT FORMAT
=============================================================================

Search output matches ripgrep/git grep format (LLM training data compatible):
    === MATCHES ===
    file.py:45:def foo():
    file.py:46-    return x + 1

    === VISUALIZATION ===
      45 def foo():␊
      46     return x + 1␊

Where: · = space, → = tab, ␊ = newline

=============================================================================
SAFETY NOTES
=============================================================================

- Always commit before replacing: git add . && git commit -m "backup"
- Use git restore to rollback: git restore file.py
- All writes are atomic (temp file + rename)
- No --dry-run option needed (use git diff to preview)
"""
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        help="Available commands"
    )

    # -------------------------------------------------------------------------
    # SEARCH SUBCOMMAND
    # -------------------------------------------------------------------------
    search_parser = subparsers.add_parser(
        "search",
        help="Search for pattern with whitespace visualization",
        description="Search file for pattern and show matches with line numbers and whitespace markers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  $ text_manipulation search "def main" src/main.py
  $ text_manipulation search "TODO" . --context 5
"""
    )
    search_parser.add_argument(
        "pattern",
        type=str,
        help="Search pattern (regular expression supported)"
    )
    search_parser.add_argument(
        "file",
        type=str,
        help="File to search"
    )
    search_parser.add_argument(
        "-c", "--context",
        type=int,
        default=DEFAULT_CONTEXT_LINES,
        metavar="N",
        help=f"Lines of context around matches (default: {DEFAULT_CONTEXT_LINES})"
    )

    # -------------------------------------------------------------------------
    # REPLACE SUBCOMMAND
    # -------------------------------------------------------------------------
    replace_parser = subparsers.add_parser(
        "replace",
        help="Replace line range with snippet file content",
        description="Safely replace lines using atomic write. Use git to rollback if needed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  $ text_manipulation replace --lines 45-52 src/main.py --snippet fix.txt
  $ text_manipulation replace -l 1-10 config.py -n new_config.txt
"""
    )
    replace_parser.add_argument(
        "--lines", "-l",
        type=str,
        required=True,
        metavar="START-END",
        help="Line range to replace (format: START-END, e.g., 45-52)"
    )
    replace_parser.add_argument(
        "file",
        type=str,
        help="File to modify"
    )
    replace_parser.add_argument(
        "--snippet", "-n",
        type=str,
        required=True,
        metavar="FILE",
        help="File containing replacement content (each line replaces one line)"
    )

    return parser


# =============================================================================
# TOOL REGISTRATION (for LLM tool calling)
# =============================================================================


def _execute_search_replace(
    command: str,
    file_path: Optional[str] = None,
    pattern: Optional[str] = None,
    lines_range: Optional[str] = None,
    snippet_path: Optional[str] = None,
    context: Any = DEFAULT_CONTEXT_LINES,  # Use Any to accept int, float, or None
    timeout: Optional[int] = None  # Accepted for registry compatibility (not used)
) -> "ToolResult":
    """
    Tool handler for LLM tool calls (direct function invocation).

    This function is registered as the 'search_replace' tool and called
    directly by the LLM framework (no subprocess overhead).

    Args:
        command: Operation type - 'search' or 'replace'.
        file_path: Path to target file.
        pattern: Search pattern (required for 'search' command).
        lines_range: Line range "START-END" (required for 'replace' command).
        snippet_path: Path to snippet file (required for 'replace' command).
        context: Context lines for search (default: 2). Accepts int or float.
        timeout: Timeout in seconds (accepted for registry compatibility, not used).

    Returns:
        ToolResult with success status, output, and error info.

    Example (LLM tool call):
        # Search for a function
        result = _execute_search_replace(
            command="search",
            file_path="src/main.py",
            pattern="def process_data"
        )

        # Replace lines
        result = _execute_search_replace(
            command="replace",
            file_path="src/main.py",
            lines_range="45-52",
            snippet_path="/tmp/fix.txt"
        )
    """
    # Import here to avoid circular dependency at module load time
    from ..core import ToolResult

    # -------------------------------------------------------------------------
    # TYPE COERCION - Handle LLM passing floats instead of ints
    # -------------------------------------------------------------------------

    # Coerce context to int (LLMs sometimes pass 2.0 instead of 2 via JSON)
    if context is None:
        context = DEFAULT_CONTEXT_LINES
    else:
        try:
            context = int(context)
            # Ensure non-negative (negative context doesn't make sense)
            if context < 0:
                context = DEFAULT_CONTEXT_LINES
        except (ValueError, TypeError):
            context = DEFAULT_CONTEXT_LINES

    # -------------------------------------------------------------------------
    # VALIDATE COMMAND
    # -------------------------------------------------------------------------
    if command not in ("search", "replace"):
        return ToolResult(
            success=False,
            output="",
            error=f"invalid command '{command}': must be 'search' or 'replace'",
            exit_code=EXIT_ERROR
        )

    # -------------------------------------------------------------------------
    # SEARCH EXECUTION
    # -------------------------------------------------------------------------
    if command == "search":
        if not file_path:
            return ToolResult(
                success=False,
                output="",
                error="missing required argument: 'file_path'",
                exit_code=EXIT_ERROR
            )
        if not pattern:
            return ToolResult(
                success=False,
                output="",
                error="missing required argument: 'pattern'",
                exit_code=EXIT_ERROR
            )

        # Capture stdout and stderr to return as ToolResult output/error
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            class _SearchArgs:
                """Namespace mock for search command."""
                def __init__(self) -> None:
                    self.pattern = pattern
                    self.file = file_path
                    self.context = context

            exit_code = execute_search(_SearchArgs())
            stdout_output = sys.stdout.getvalue()
            stderr_output = sys.stderr.getvalue()
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            if exit_code == EXIT_SUCCESS:
                return ToolResult(
                    success=True,
                    output=stdout_output,
                    error="",
                    exit_code=exit_code
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=stderr_output.strip() if stderr_output.strip() else "search failed",
                    exit_code=exit_code
                )
        except TextManipulationError as exc:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            return ToolResult(
                success=False,
                output="",
                error=exc.message,
                exit_code=EXIT_ERROR
            )
        except Exception as exc:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            return ToolResult(
                success=False,
                output="",
                error=f"unexpected error: {type(exc).__name__}: {exc}",
                exit_code=EXIT_ERROR
            )

    # -------------------------------------------------------------------------
    # REPLACE EXECUTION
    # -------------------------------------------------------------------------
    if command == "replace":
        if not file_path:
            return ToolResult(
                success=False,
                output="",
                error="missing required argument: 'file_path'",
                exit_code=EXIT_ERROR
            )
        if not lines_range:
            return ToolResult(
                success=False,
                output="",
                error="missing required argument: 'lines_range' (format: 'START-END')",
                exit_code=EXIT_ERROR
            )
        if not snippet_path:
            return ToolResult(
                success=False,
                output="",
                error="missing required argument: 'snippet_path'",
                exit_code=EXIT_ERROR
            )

        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            class _ReplaceArgs:
                """Namespace mock for replace command."""
                def __init__(self) -> None:
                    self.lines = lines_range
                    self.file = file_path
                    self.snippet = snippet_path

            exit_code = execute_replace(_ReplaceArgs())
            stdout_output = sys.stdout.getvalue()
            stderr_output = sys.stderr.getvalue()
            sys.stdout = old_stdout
            sys.stderr = old_stderr

            if exit_code == EXIT_SUCCESS:
                return ToolResult(
                    success=True,
                    output=stdout_output,
                    error="",
                    exit_code=exit_code
                )
            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=stderr_output.strip() if stderr_output.strip() else "replace failed",
                    exit_code=exit_code
                )
        except TextManipulationError as exc:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            return ToolResult(
                success=False,
                output="",
                error=exc.message,
                exit_code=EXIT_ERROR
            )
        except Exception as exc:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            return ToolResult(
                success=False,
                output="",
                error=f"unexpected error: {type(exc).__name__}: {exc}",
                exit_code=EXIT_ERROR
            )

    # Should not reach here
    return ToolResult(
        success=False,
        output="",
        error="unknown command",
        exit_code=EXIT_ERROR
    )


def _get_tool_schema() -> Dict[str, Any]:
    """
    Return OpenAI-compatible tool schema with detailed LLM instructions.

    The description includes a mini-tutorial to guide the LLM on correct usage.
    This is critical for local LLMs that may not have seen this tool before.

    Returns:
        Tool schema dict for OpenAI function calling format.
    """
    return {
        "type": "function",
        "function": {
            "name": "search_replace",
            "description": """Git-safe text manipulation tool for code editing.

=== MINI TUTORIAL FOR LLM ===

This tool has TWO operations: SEARCH and REPLACE. You MUST set 'command' first.

┌─────────────────────────────────────────────────────────────────────────────┐
│ OPERATION 1: SEARCH (find patterns with line numbers)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ Use when you need to find where code is located before editing.             │
│                                                                             │
│ ⚠️  PATTERN MATCHING - IMPORTANT:                                           │
│   • ALWAYS prefer SIMPLE text patterns (e.g., "def hello")                  │
│   • Regex is SUPPORTED but RARELY NEEDED - avoid unless necessary           │
│   • Simple search works 95% of the time - use regex only as last resort     │
│                                                                             │
│   ✅ GOOD (simple): "def process_data", "TODO", "import os"                 │
│   ❌ AVOID (regex hell): "def\\s+\\w+\\(", "^import.*os$", complex patterns │
│                                                                             │
│   When to use regex: Only when you NEED anchors (^, $) or wildcards (., *) │
│   Example regex that works: "^TODO", "error$", "colou?red"                  │
│                                                                             │
│ Required arguments:                                                         │
│   - command: "search"                                                       │
│   - file_path: path to file (e.g., "src/main.py")                           │
│   - pattern: text pattern to find (simple string, e.g., "def process_data") │
│                                                                             │
│ Optional arguments:                                                         │
│   - context: lines of context around matches (default: 2)                   │
│                                                                             │
│ Example tool calls:                                                         │
│   ✅ Simple search (preferred):                                             │
│   {                                                                         │
│     "command": "search",                                                    │
│     "file_path": "src/main.py",                                             │
│     "pattern": "def old_function"                                           │
│   }                                                                         │
│                                                                             │
│   ⚠️  Regex search (only if simple fails):                                  │
│   {                                                                         │
│     "command": "search",                                                    │
│     "file_path": "src/main.py",                                             │
│     "pattern": "^TODO"  // Finds TODO at line start only                    │
│   }                                                                         │
│                                                                             │
│ Output format (like `rg -n` + `bat -A`):                                    │
│   /tmp/file.txt:                                                            │
│   45:def old_function():␊                                                   │
│   46-    return x + 1␊                                                      │
│                                                                             │
│ Whitespace markers: · = space, → = tab, ␊ = newline                         │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ OPERATION 2: REPLACE (replace specific line ranges)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Use when you know exact line numbers to replace.                            │
│                                                                             │
│ Required arguments:                                                         │
│   - command: "replace"                                                      │
│   - file_path: path to file (e.g., "src/main.py")                           │
│   - lines_range: "START-END" format, 1-indexed (e.g., "45-52")              │
│   - snippet_path: path to file with replacement content                     │
│                                                                             │
│ Example tool call:                                                          │
│   {                                                                         │
│     "command": "replace",                                                   │
│     "file_path": "src/main.py",                                             │
│     "lines_range": "45-52",                                                 │
│     "snippet_path": "/tmp/new_code.txt"                                     │
│   }                                                                         │
│                                                                             │
│ IMPORTANT: snippet_path must be an EXISTING file. Create it first using     │
│ execute_bash: echo "new code" > /tmp/new_code.txt                           │
│                                                                             │
│ Output:                                                                     │
│   Replaced lines 45-52 in src/main.py                                       │
│   (was 200 lines, now 195 lines)                                            │
│   Run: git diff src/main.py                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

=== TYPICAL WORKFLOW ===

1. SEARCH to find line numbers of code to change
2. CREATE snippet file with new code (using execute_bash)
3. REPLACE using the line numbers from step 1
4. REVIEW with: execute_bash("git diff src/main.py")
5. COMMIT if good, or git restore if wrong

=== COMMON ERRORS ===

- "file not found": Check file_path is correct (relative to project root)
- "line range out of bounds": File has fewer lines than your range
- "snippet file not found": Create the snippet file first with execute_bash
- "invalid line range": Use format "START-END" (e.g., "45-52", not "45:52")

=== SAFETY NOTES ===

- All changes are git-rollback safe: use `git restore file.py` to undo
- Writes are atomic (won't corrupt file on crash)
- No --dry-run: use `git diff` to preview before committing
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": ["search", "replace"],
                        "description": (
                            "Operation type. MUST be set first.\n"
                            "- 'search': Find patterns with line numbers\n"
                            "- 'replace': Replace specific line ranges"
                        )
                    },
                    "file_path": {
                        "type": "string",
                        "description": (
                            "Path to target file (relative to project root).\n"
                            "Example: 'src/main.py', 'config/settings.json'"
                        )
                    },
                    "pattern": {
                        "type": "string",
                        "description": (
                            "Regex pattern to search for.\n"
                            "Required when command='search'.\n"
                            "Example: 'def old_function', 'TODO.*deprecated'"
                        )
                    },
                    "lines_range": {
                        "type": "string",
                        "description": (
                            "Line range to replace in 'START-END' format (1-indexed).\n"
                            "Required when command='replace'.\n"
                            "Example: '45-52' (replaces lines 45 through 52)"
                        )
                    },
                    "snippet_path": {
                        "type": "string",
                        "description": (
                            "Path to file containing replacement content.\n"
                            "Required when command='replace'.\n"
                            "MUST create this file first using execute_bash.\n"
                            "Example: '/tmp/new_code.txt'"
                        )
                    },
                    "context": {
                        "type": "integer",
                        "description": (
                            "Number of context lines before/after matches.\n"
                            "Only used when command='search'.\n"
                            "Default: 2"
                        ),
                        "default": DEFAULT_CONTEXT_LINES
                    }
                },
                "required": ["command"],
                "additionalProperties": False
            }
        }
    }


# Auto-register tool when module is imported
try:
    from .registry import register_tool

    register_tool(
        name="search_replace",
        function=_execute_search_replace,
        schema=_get_tool_schema(),
        description="Git-safe search and replace for code editing (uses rg + bat internally)."
    )
except ImportError:
    # Running as standalone CLI script - skip registration
    pass


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def main() -> None:
    """
    CLI entry point.

    Parses arguments and dispatches to appropriate command handler.
    """
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "search":
        sys.exit(execute_search(args))
    elif args.command == "replace":
        sys.exit(execute_replace(args))
    else:
        parser.print_help()
        sys.exit(EXIT_ERROR)


if __name__ == "__main__":
    main()
