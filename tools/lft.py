#!/usr/bin/env python3
"""
LFT - LLM File Tool

A minimal file manipulation tool for LLMs.
Uses exact string matching - no regex, no line numbers for operations.

Usage:
    lft read <file> [start] [end]
    lft find <file> <pattern> [options]
    lft edit <file> <old_string> <new_string>

Use "-" for old_string or new_string to read from stdin.
"""

from __future__ import annotations

import codecs
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

# ==============================================================================
# Constants
# ==============================================================================

MAX_FILE_SIZE_MB = 100
BINARY_CHECK_BYTES = 8192
ENCODING_FALLBACKS = ["utf-8", "utf-8-sig", "utf-16", "latin-1", "cp1252"]

# ==============================================================================
# Exceptions
# ==============================================================================


class LFTError(Exception):
    """Base exception with actionable message."""

    def __init__(self, code: str, message: str, hint: str = ""):
        self.code = code
        self.message = message
        self.hint = hint
        super().__init__(message)


class FileNotFoundError_(LFTError):
    def __init__(self, path: Path):
        super().__init__(
            "FILE_NOT_FOUND",
            f"File not found: {path}",
            "Check the path and try again.",
        )


class BinaryFileError(LFTError):
    def __init__(self, path: Path):
        super().__init__(
            "BINARY_FILE",
            f"File appears to be binary: {path}",
            "This tool only works with text files.",
        )


class FileTooLargeError(LFTError):
    def __init__(self, size: int, limit: int):
        super().__init__(
            "FILE_TOO_LARGE",
            f"File size ({size / 1024 / 1024:.1f} MB) exceeds limit ({limit / 1024 / 1024:.1f} MB)",
            "Use --max-size to increase limit, or use head/tail for large files.",
        )


class NotFoundError(LFTError):
    def __init__(self, old_string: str, context: str = ""):
        super().__init__(
            "NOT_FOUND",
            "The old_string was not found in file",
            "Check whitespace, line endings, and exact text. Did the file change?",
        )
        self.old_string = old_string
        self.context = context


class AmbiguousError(LFTError):
    def __init__(self, count: int, locations: List[int]):
        super().__init__(
            "AMBIGUOUS",
            f"Found {count} occurrences of old_string",
            "Include more surrounding context to make old_string unique.",
        )
        self.count = count
        self.locations = locations


class VerifyError(LFTError):
    def __init__(self, expected: str, actual: str):
        super().__init__(
            "VERIFY_FAILED",
            "File content does not match after write",
            "File may have been modified by another process.",
        )
        self.expected = expected
        self.actual = actual


# ==============================================================================
# Output Functions
# ==============================================================================


def output_success(**kwargs) -> None:
    """Output success result."""
    print("STATUS: SUCCESS")
    for key, value in kwargs.items():
        if value is not None:
            print(f"{key.upper()}: {value}")


def output_error(error: LFTError) -> None:
    """Output error in parseable format."""
    print("STATUS: FAIL")
    print(f"ERROR: {error.code}")
    print(f"MESSAGE: {error.message}")
    if error.hint:
        print(f"HINT: {error.hint}")


def format_line(line_num: int, content: str, marker: str = " ") -> str:
    """Format a line with line number."""
    return f"{marker}{line_num:6d}→{content}"


def format_lines(lines: List[str], start: int = 1, marker: str = " ") -> str:
    """Format multiple lines with line numbers."""
    return "\n".join(format_line(start + i, line, marker) for i, line in enumerate(lines))


# ==============================================================================
# File Utilities
# ==============================================================================


def is_binary(path: Path) -> bool:
    """Check if file appears to be binary."""
    with open(path, "rb") as f:
        data = f.read(BINARY_CHECK_BYTES)
    return b"\x00" in data


def detect_encoding(path: Path) -> str:
    """Detect file encoding with fallbacks."""
    # Check for BOM
    with open(path, "rb") as f:
        initial = f.read(4)

    if initial.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if initial.startswith(codecs.BOM_UTF16_LE) or initial.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"

    # Try encodings
    for encoding in ENCODING_FALLBACKS:
        try:
            with open(path, "r", encoding=encoding) as f:
                f.read()
            return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue

    return "utf-8"


def read_file(path: Path) -> Tuple[str, str]:
    """Read file and return (content, encoding)."""
    encoding = detect_encoding(path)
    with open(path, "r", encoding=encoding) as f:
        content = f.read()
    return content, encoding


def write_file(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content to file atomically."""
    # Write to temp file first
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".lft_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(temp_path, path)
    except Exception:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def verify_content(path: Path, expected: str, encoding: str) -> None:
    """Verify file content matches expected."""
    actual, _ = read_file(path)
    if actual != expected:
        raise VerifyError(expected, actual)


# ==============================================================================
# Commands
# ==============================================================================


def cmd_read(path: Path, start: int = 1, end: int = -1) -> int:
    """
    Read file with line numbers.

    Output shows exact content with line numbers for reference.
    LLM can copy text directly from output for use in edit.
    """
    try:
        # Validate path
        if not path.exists():
            raise FileNotFoundError_(path)

        if is_binary(path):
            raise BinaryFileError(path)

        # Check size
        size = path.stat().st_size
        max_bytes = int(MAX_FILE_SIZE_MB * 1024 * 1024)
        if size > max_bytes:
            raise FileTooLargeError(size, max_bytes)

        # Read
        content, encoding = read_file(path)

        if not content:
            output_success(file=path, lines="0", encoding=encoding, size="0 bytes")
            print()
            print("=== CONTENT ===")
            print("(empty file)")
            return 0

        lines = content.splitlines()
        total_lines = len(lines)

        # Determine range
        start_idx = max(0, start - 1)
        end_idx = total_lines if end == -1 else min(end, total_lines)

        selected = lines[start_idx:end_idx]
        actual_start = start_idx + 1
        actual_end = end_idx

        # Output
        output_success(
            file=path,
            lines=f"{actual_start}-{actual_end} of {total_lines}",
            encoding=encoding,
            size=f"{size} bytes",
        )
        print()
        print("=== CONTENT ===")
        print(format_lines(selected, actual_start))

        return 0

    except LFTError as e:
        output_error(e)
        return 1
    except PermissionError:
        output_error(LFTError("PERMISSION_DENIED", f"Permission denied: {path}"))
        return 1
    except Exception as e:
        output_error(LFTError("UNKNOWN", str(e)))
        return 1


def cmd_edit(
    path: Path,
    old_string: str,
    new_string: str,
    backup: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Edit file using exact string matching.

    Finds old_string exactly (no regex, no interpretation).
    Must match exactly once.
    Replaces with new_string.
    Verifies by reading back.
    """
    try:
        # Validate path
        if not path.exists():
            raise FileNotFoundError_(path)

        if is_binary(path):
            raise BinaryFileError(path)

        # Check size
        size = path.stat().st_size
        max_bytes = int(MAX_FILE_SIZE_MB * 1024 * 1024)
        if size > max_bytes:
            raise FileTooLargeError(size, max_bytes)

        # Read
        content, encoding = read_file(path)

        # Validate old_string is not empty
        if not old_string:
            raise LFTError(
                "INVALID_INPUT",
                "old_string cannot be empty",
                "Provide the exact text you want to replace.",
            )

        # Count occurrences
        count = content.count(old_string)

        if count == 0:
            # Not found - show what we searched for
            print("STATUS: FAIL")
            print("ERROR: NOT_FOUND")
            print("MESSAGE: The old_string was not found in file")
            print()
            print("--- SEARCHED FOR ---")
            for line in old_string.split("\n"):
                print(f"  {line}")
            print()
            print("HINT: The exact text was not found. Check:")
            print("  - Whitespace (spaces vs tabs)")
            print("  - Line endings (LF vs CRLF)")
            print("  - Did the file change since you read it?")
            return 1

        if count > 1:
            # Ambiguous - show where matches are
            locations = []
            for i, line in enumerate(content.splitlines(), 1):
                if old_string in line or (old_string.startswith("\n") and i > 1):
                    locations.append(i)

            print("STATUS: FAIL")
            print(f"ERROR: AMBIGUOUS")
            print(f"MESSAGE: Found {count} occurrences of old_string")
            print()
            print("OCCURRENCES:")
            for loc in locations[:10]:  # Show first 10
                print(f"  Line {loc}")
            if len(locations) > 10:
                print(f"  ... and {len(locations) - 10} more")
            print()
            print("HINT: Include more surrounding context to make old_string unique.")
            return 1

        # Exactly one match - proceed
        new_content = content.replace(old_string, new_string, 1)

        # Dry run
        if dry_run:
            print("STATUS: DRY_RUN")
            print(f"FILE: {path}")
            print()
            print("--- OLD ---")
            for line in old_string.split("\n"):
                print(f"  {line}")
            print()
            print("+++ NEW +++")
            for line in new_string.split("\n"):
                print(f"  {line}")
            print()
            print("=== WOULD APPLY ===")
            print(f"Replace 1 occurrence in {path}")
            return 0

        # Create backup if requested
        backup_path = None
        if backup:
            backup_path = path.with_suffix(path.suffix + ".bak")
            counter = 1
            while backup_path.exists():
                backup_path = path.with_suffix(f"{path.suffix}.bak.{counter}")
                counter += 1
            shutil.copy2(path, backup_path)

        # Write
        write_file(path, new_content, encoding)

        # Verify
        verify_content(path, new_content, encoding)

        # Find where the change is for output
        new_lines = new_content.splitlines()
        old_lines_str = old_string.split("\n")

        # Find line number where change occurred
        change_line = 1
        before_content = content.split(old_string)[0]
        change_line = before_content.count("\n") + 1

        # Output success
        print("STATUS: SUCCESS")
        print(f"FILE: {path}")
        print("ACTION: Replaced 1 occurrence")
        if backup_path:
            print(f"BACKUP: {backup_path}")
        print()

        print("--- OLD ---")
        for line in old_string.split("\n"):
            print(f"  {line}")
        print()

        print("+++ NEW +++")
        for line in new_string.split("\n"):
            print(f"  {line}")
        print()

        # Show context around change
        print("=== VERIFIED (read back from file) ===")
        context_start = max(1, change_line - 2)
        context_end = min(len(new_lines), change_line + len(new_string.split("\n")) + 1)
        print(f"Lines {context_start}-{context_end}:")
        print(format_lines(new_lines[context_start - 1 : context_end], context_start))

        return 0

    except LFTError as e:
        output_error(e)
        return 1
    except PermissionError:
        output_error(LFTError("PERMISSION_DENIED", f"Permission denied: {path}"))
        return 1
    except Exception as e:
        output_error(LFTError("UNKNOWN", str(e)))
        return 1


def cmd_find(
    path: Path,
    pattern: str,
    use_regex: bool = False,
    context: int = 0,
    ignore_case: bool = False,
    count_only: bool = False,
) -> int:
    """
    Find pattern in file and return line numbers.

    This is a DISCOVERY tool - for finding, not editing.
    Returns line numbers so LLM can read that area to copy exact text.
    """
    try:
        # Validate path
        if not path.exists():
            raise FileNotFoundError_(path)

        if is_binary(path):
            raise BinaryFileError(path)

        # Check size
        size = path.stat().st_size
        max_bytes = int(MAX_FILE_SIZE_MB * 1024 * 1024)
        if size > max_bytes:
            raise FileTooLargeError(size, max_bytes)

        # Read
        content, encoding = read_file(path)
        lines = content.splitlines()

        # Validate pattern
        if not pattern:
            raise LFTError(
                "INVALID_INPUT",
                "Pattern cannot be empty",
                "Provide a pattern to search for.",
            )

        # Compile pattern
        flags = re.IGNORECASE if ignore_case else 0
        if use_regex:
            try:
                compiled = re.compile(pattern, flags)
            except re.error as e:
                raise LFTError(
                    "INVALID_PATTERN",
                    f"Invalid regex: {e}",
                    "Fix the regex syntax or use --literal for literal search.",
                )
        else:
            # Literal search - escape the pattern
            compiled = re.compile(re.escape(pattern), flags)

        # Find matches
        matches = []  # List of (line_num, line_content, match_start, match_end)
        for i, line in enumerate(lines):
            for match in compiled.finditer(line):
                matches.append((i + 1, line, match.start(), match.end()))

        # Handle no matches
        if not matches:
            print("STATUS: FAIL")
            print("ERROR: NOT_FOUND")
            print(f"MESSAGE: Pattern not found: {pattern}")
            print()
            print("HINT: The pattern was not found. Try:")
            print("  - Check spelling")
            print("  - Use --ignore-case for case-insensitive search")
            print("  - Use --regex for pattern matching")
            return 1

        # Count only mode
        if count_only:
            output_success(file=path, matches=len(matches))
            return 0

        # Get unique line numbers
        match_lines = list(set(m[0] for m in matches))
        match_lines.sort()

        # Output
        output_success(
            file=path,
            matches=len(matches),
            lines_with_matches=len(match_lines),
        )
        print()

        # Show matches with context
        if context > 0:
            # Collect all lines to show (with context)
            show_lines = set()
            for line_num in match_lines:
                for i in range(max(1, line_num - context), min(len(lines) + 1, line_num + context + 1)):
                    show_lines.add(i)
            show_lines = sorted(show_lines)

            print("=== MATCHES WITH CONTEXT ===")
            last_shown = 0
            for line_num in show_lines:
                # Add separator for gaps
                if last_shown and line_num > last_shown + 1:
                    print("...")
                last_shown = line_num

                marker = ">" if line_num in match_lines else " "
                print(format_line(line_num, lines[line_num - 1], marker))
        else:
            # Show only matching lines
            print("=== MATCHES ===")
            for line_num, line_content, match_start, match_end in matches[:100]:  # Limit output
                # Highlight the match
                highlighted = f"{line_content[:match_start]}<<{line_content[match_start:match_end]}>>{line_content[match_end:]}"
                print(format_line(line_num, highlighted, ">"))

            if len(matches) > 100:
                print(f"... and {len(matches) - 100} more matches")

        # Summary
        print()
        print("=== LINE NUMBERS ===")
        if len(match_lines) <= 20:
            print(f"Found at lines: {', '.join(map(str, match_lines))}")
        else:
            print(f"Found at lines: {', '.join(map(str, match_lines[:20]))} ... and {len(match_lines) - 20} more")
        print()
        print("HINT: Use 'lft read <file> <start> <end>' to see content around these lines.")

        return 0

    except LFTError as e:
        output_error(e)
        return 1
    except PermissionError:
        output_error(LFTError("PERMISSION_DENIED", f"Permission denied: {path}"))
        return 1
    except Exception as e:
        output_error(LFTError("UNKNOWN", str(e)))
        return 1


def cmd_info(path: Path) -> int:
    """
    Show file information and quick preview.

    This is a UTILITY command - for quick overview without reading full file.
    Shows metadata and a preview of the first few lines.
    """
    try:
        # Validate path
        if not path.exists():
            raise FileNotFoundError_(path)

        # Get basic stats
        stat = path.stat()
        size = stat.st_size

        # Check if binary
        if is_binary(path):
            output_success(
                file=path,
                size=f"{size} bytes",
                type="binary",
                writable=os.access(path, os.W_OK),
            )
            return 0

        # Check size limit
        max_bytes = int(MAX_FILE_SIZE_MB * 1024 * 1024)
        if size > max_bytes:
            # Show info anyway but warn
            print("STATUS: SUCCESS")
            print(f"FILE: {path}")
            print(f"SIZE: {size} bytes ({size / 1024 / 1024:.1f} MB)")
            print("TYPE: text (large file)")
            print(f"WARNING: File exceeds {MAX_FILE_SIZE_MB}MB limit")
            print("HINT: Use --max-size to increase limit")
            return 0

        # Read for detailed info
        content, encoding = read_file(path)
        lines = content.splitlines()

        # Calculate stats
        total_chars = len(content)
        total_words = len(content.split())
        total_lines = len(lines)

        # Detect line ending
        line_ending = "LF"
        if "\r\n" in content:
            line_ending = "CRLF"
        elif "\r" in content:
            line_ending = "CR"

        # Calculate average line length
        avg_line_len = sum(len(line) for line in lines) / len(lines) if lines else 0
        max_line_len = max((len(line) for line in lines), default=0)

        # Check permissions
        writable = os.access(path, os.W_OK)

        # Output
        output_success(
            file=path,
            size=f"{size} bytes",
            lines=total_lines,
            chars=total_chars,
            words=total_words,
            encoding=encoding,
            line_ending=line_ending,
            writable="yes" if writable else "no",
        )
        print()

        # Show preview
        if lines:
            preview_lines = min(5, len(lines))
            print(f"=== PREVIEW (first {preview_lines} lines) ===")
            print(format_lines(lines[:preview_lines], 1))
            if len(lines) > 5:
                print(f"... ({len(lines) - 5} more lines)")
        else:
            print("=== CONTENT ===")
            print("(empty file)")

        return 0

    except LFTError as e:
        output_error(e)
        return 1
    except PermissionError:
        output_error(LFTError("PERMISSION_DENIED", f"Permission denied: {path}"))
        return 1
    except Exception as e:
        output_error(LFTError("UNKNOWN", str(e)))
        return 1


def cmd_write(
    path: Path,
    content: str,
    backup: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Write content to file (create or overwrite).

    This is for creating new files or complete rewrites.
    For editing existing files, use the edit command instead.
    """
    try:
        existing = path.exists()

        # Check if existing file is binary
        if existing and is_binary(path):
            raise BinaryFileError(path)

        # Check parent directory exists
        if not existing and not path.parent.exists():
            raise LFTError(
                "DIRECTORY_NOT_FOUND",
                f"Parent directory does not exist: {path.parent}",
                "Create the directory first, or use a different path.",
            )

        # Check permissions
        if existing and not os.access(path, os.W_OK):
            raise LFTError(
                "PERMISSION_DENIED",
                f"No write permission: {path}",
                "Check file permissions.",
            )
        if not existing and not os.access(path.parent, os.W_OK):
            raise LFTError(
                "PERMISSION_DENIED",
                f"No write permission for directory: {path.parent}",
                "Check directory permissions.",
            )

        # Detect encoding for existing file, or use utf-8 for new
        if existing:
            encoding = detect_encoding(path)
        else:
            encoding = "utf-8"

        # Dry run
        if dry_run:
            print("STATUS: DRY_RUN")
            print(f"FILE: {path}")
            print(f"ACTION: {'Overwrite' if existing else 'Create'}")
            print(f"SIZE: {len(content)} characters")
            print()
            print("=== WOULD WRITE ===")
            lines = content.split("\n") if content else []
            if lines:
                print(format_lines(lines[:10], 1))
                if len(lines) > 10:
                    print(f"... ({len(lines) - 10} more lines)")
            else:
                print("(empty)")
            return 0

        # Create backup if requested and file exists
        backup_path = None
        if backup and existing:
            backup_path = path.with_suffix(path.suffix + ".bak")
            counter = 1
            while backup_path.exists():
                backup_path = path.with_suffix(f"{path.suffix}.bak.{counter}")
                counter += 1
            shutil.copy2(path, backup_path)

        # Write
        write_file(path, content, encoding)

        # Verify
        verify_content(path, content, encoding)

        # Output
        print("STATUS: SUCCESS")
        print(f"FILE: {path}")
        print(f"ACTION: {'Overwritten' if existing else 'Created'}")
        print(f"SIZE: {len(content)} characters")
        if backup_path:
            print(f"BACKUP: {backup_path}")
        print()

        # Show what was written
        lines = content.split("\n") if content else []
        print("=== WRITTEN ===")
        if lines:
            print(format_lines(lines[:10], 1))
            if len(lines) > 10:
                print(f"... ({len(lines) - 10} more lines)")
        else:
            print("(empty file)")

        return 0

    except LFTError as e:
        output_error(e)
        return 1
    except PermissionError:
        output_error(LFTError("PERMISSION_DENIED", f"Permission denied: {path}"))
        return 1
    except Exception as e:
        output_error(LFTError("UNKNOWN", str(e)))
        return 1


def parse_multiedit(content: str) -> List[Tuple[str, str]]:
    """
    Parse multiedit content into list of (old_string, new_string) tuples.
    
    Format:
    OLD:
    text to find
    NEW:
    replacement text
    OLD:
    another text
    NEW:
    another replacement
    """
    edits = []
    lines = content.split("\n")
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.upper() == "OLD:":
            # Collect old_string lines until NEW:
            old_lines = []
            i += 1
            while i < len(lines) and lines[i].strip().upper() != "NEW:":
                old_lines.append(lines[i])
                i += 1
            old_string = "\n".join(old_lines)
            
            # Skip NEW: line
            if i < len(lines) and lines[i].strip().upper() == "NEW:":
                i += 1
            
            # Collect new_string lines until next OLD: or end
            new_lines = []
            while i < len(lines):
                if lines[i].strip().upper() == "OLD:":
                    break
                new_lines.append(lines[i])
                i += 1
            new_string = "\n".join(new_lines)
            
            # Remove trailing newline from new_string if old_string doesn't have one
            if not old_string.endswith("\n") and new_string.endswith("\n"):
                new_string = new_string[:-1]
            
            edits.append((old_string, new_string))
        else:
            i += 1
    
    return edits


def cmd_multiedit(
    path: Path,
    edits_content: str,
    backup: bool = False,
    dry_run: bool = False,
) -> int:
    """
    Apply multiple edits atomically.
    
    All edits are validated before any are applied.
    If any edit fails validation, none are applied.
    All edits succeed or none are applied.
    """
    try:
        # Validate path
        if not path.exists():
            raise FileNotFoundError_(path)
        
        if is_binary(path):
            raise BinaryFileError(path)
        
        # Check size
        size = path.stat().st_size
        max_bytes = int(MAX_FILE_SIZE_MB * 1024 * 1024)
        if size > max_bytes:
            raise FileTooLargeError(size, max_bytes)
        
        # Parse edits
        edits = parse_multiedit(edits_content)
        
        if not edits:
            raise LFTError(
                "NO_EDITS",
                "No valid edits found in input",
                "Use format:\nOLD:\ntext to find\nNEW:\nreplacement text",
            )
        
        # Read original content
        content, encoding = read_file(path)
        original_content = content
        
        # Validation phase - check all edits without applying
        validation_errors = []
        validated_edits = []
        
        for i, (old_string, new_string) in enumerate(edits):
            if not old_string:
                validation_errors.append(f"Edit {i + 1}: old_string is empty")
                continue
            
            count = content.count(old_string)
            
            if count == 0:
                validation_errors.append(f"Edit {i + 1}: old_string not found")
            elif count > 1:
                validation_errors.append(f"Edit {i + 1}: old_string found {count} times (ambiguous)")
            else:
                validated_edits.append((old_string, new_string, i + 1))
                # Update content for next validation (simulate)
                content = content.replace(old_string, new_string, 1)
        
        # If any validation errors, report and abort
        if validation_errors:
            print("STATUS: FAIL")
            print("ERROR: VALIDATION_FAILED")
            print(f"MESSAGE: {len(validation_errors)} edit(s) failed validation")
            print()
            print("=== VALIDATION ERRORS ===")
            for err in validation_errors:
                print(f"  - {err}")
            print()
            print("HINT: Fix validation errors. No changes were made.")
            return 1
        
        # Dry run
        if dry_run:
            print("STATUS: DRY_RUN")
            print(f"FILE: {path}")
            print(f"EDITS: {len(validated_edits)}")
            print()
            print("=== WOULD APPLY ===")
            for old_string, new_string, edit_num in validated_edits:
                print(f"EDIT {edit_num}:")
                print("  OLD:")
                for line in old_string.split("\n")[:5]:
                    print(f"    {line}")
                if len(old_string.split("\n")) > 5:
                    print(f"    ... ({len(old_string.split('\n')) - 5} more lines)")
                print("  NEW:")
                for line in new_string.split("\n")[:5]:
                    print(f"    {line}")
                if len(new_string.split("\n")) > 5:
                    print(f"    ... ({len(new_string.split('\n')) - 5} more lines)")
                print()
            return 0
        
        # Create backup if requested
        backup_path = None
        if backup:
            backup_path = path.with_suffix(path.suffix + ".bak")
            counter = 1
            while backup_path.exists():
                backup_path = path.with_suffix(f"{path.suffix}.bak.{counter}")
                counter += 1
            shutil.copy2(path, backup_path)
        
        # Apply all edits
        new_content = original_content
        applied_edits = []
        
        for old_string, new_string, edit_num in validated_edits:
            new_content = new_content.replace(old_string, new_string, 1)
            applied_edits.append((old_string, new_string, edit_num))
        
        # Write
        write_file(path, new_content, encoding)
        
        # Verify
        verify_content(path, new_content, encoding)
        
        # Output
        print("STATUS: SUCCESS")
        print(f"FILE: {path}")
        print(f"EDITS: {len(applied_edits)} applied")
        if backup_path:
            print(f"BACKUP: {backup_path}")
        print()
        
        print("=== APPLIED EDITS ===")
        for old_string, new_string, edit_num in applied_edits:
            print(f"\nEDIT {edit_num}:")
            print("  --- OLD ---")
            for line in old_string.split("\n")[:3]:
                print(f"    {line}")
            if len(old_string.split("\n")) > 3:
                print(f"    ... ({len(old_string.split('\n')) - 3} more lines)")
            print("  +++ NEW +++")
            for line in new_string.split("\n")[:3]:
                print(f"    {line}")
            if len(new_string.split("\n")) > 3:
                print(f"    ... ({len(new_string.split('\n')) - 3} more lines)")
        
        print()
        print("=== VERIFIED ===")
        new_lines = new_content.splitlines()
        print(f"File now has {len(new_lines)} lines")
        print("All changes confirmed.")
        
        return 0
    
    except LFTError as e:
        output_error(e)
        return 1
    except PermissionError:
        output_error(LFTError("PERMISSION_DENIED", f"Permission denied: {path}"))
        return 1
    except Exception as e:
        output_error(LFTError("UNKNOWN", str(e)))
        return 1


# ==============================================================================
# CLI
# ==============================================================================


def read_stdin() -> str:
    """Read content from stdin."""
    if sys.stdin.isatty():
        raise LFTError(
            "NO_STDIN",
            "Stdin requested (-) but no input provided",
            "Pipe content: echo 'text' | lft edit file - 'new'",
        )
    return sys.stdin.read()


def create_parser() -> "argparse.ArgumentParser":
    import argparse

    parser = argparse.ArgumentParser(
        prog="lft",
        description="LLM File Tool - File manipulation using exact string matching",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  read <file> [start] [end]
      Read file with line numbers.
      Line numbers are for reference only, not for operations.

  find <file> <pattern> [options]
      Find pattern in file, return line numbers.
      Options: --regex, --context N, --ignore-case, --count

  edit <file> <old_string> <new_string>
      Replace exact string with new string.
      old_string must match exactly once.
      Use - to read from stdin for multi-line content.

  write <file> <content>
      Write content to file (create or overwrite).
      Use - to read content from stdin.

  multiedit <file>
      Apply multiple edits atomically.
      Reads edit operations from stdin.
      All edits validated before any are applied.

  info <file>
      Show file information and preview.
      Quick overview without reading full file.

Examples:
  lft info app.py
  lft read app.py
  lft read app.py 10 20
  lft find app.py "def hello"
  lft find app.py "import" --context 2
  lft find app.py "class.*Test" --regex
  lft write new_file.py "def main(): pass"
  lft write new_file.py - << 'EOF'
  def main():
      print("hello")
  EOF
  lft multiedit app.py - << 'EOF'
  OLD:
  old text 1
  NEW:
  new text 1
  OLD:
  old text 2
  NEW:
  new text 2
  EOF
  lft edit app.py "old text" "new text"
  lft edit app.py - "new text" << 'EOF'
  old line 1
  old line 2
  EOF
  lft --backup edit app.py "old" "new"
  lft --dry-run edit app.py "old" "new"

Output:
  Every command returns STATUS: SUCCESS or STATUS: FAIL.
  Edit shows OLD, NEW, and VERIFIED sections.
  Always check VERIFIED section to confirm changes.
        """,
    )

    # Global options
    parser.add_argument("--backup", action="store_true", help="Create .bak file before editing")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without modifying")
    parser.add_argument(
        "--max-size",
        type=float,
        default=MAX_FILE_SIZE_MB,
        help=f"Max file size in MB (default: {MAX_FILE_SIZE_MB})",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # read
    read_p = subparsers.add_parser("read", help="Read file with line numbers")
    read_p.add_argument("file", type=Path, help="File to read")
    read_p.add_argument("start", nargs="?", type=int, default=1, help="Start line (default: 1)")
    read_p.add_argument("end", nargs="?", type=int, default=-1, help="End line, -1 for end")

    # find
    find_p = subparsers.add_parser("find", help="Find pattern and return line numbers")
    find_p.add_argument("file", type=Path, help="File to search")
    find_p.add_argument("pattern", help="Pattern to find")
    find_p.add_argument("--regex", "-r", action="store_true", help="Pattern is regex")
    find_p.add_argument("--context", "-c", type=int, default=0, help="Show N lines of context")
    find_p.add_argument("--ignore-case", "-i", action="store_true", help="Case insensitive")
    find_p.add_argument("--count", action="store_true", help="Only show match count")

    # info
    info_p = subparsers.add_parser("info", help="Show file information and preview")
    info_p.add_argument("file", type=Path, help="File to analyze")

    # write
    write_p = subparsers.add_parser("write", help="Write content to file")
    write_p.add_argument("file", type=Path, help="File to write")
    write_p.add_argument("content", nargs="?", default="-", help="Content to write (use - for stdin)")

    # multiedit
    multiedit_p = subparsers.add_parser("multiedit", help="Apply multiple edits atomically")
    multiedit_p.add_argument("file", type=Path, help="File to edit")

    # edit
    edit_p = subparsers.add_parser("edit", help="Edit file with exact string matching")
    edit_p.add_argument("file", type=Path, help="File to edit")
    edit_p.add_argument("old_string", help="Exact text to find (use - for stdin)")
    edit_p.add_argument("new_string", help="Replacement text (use - for stdin)")

    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Update max size if specified
    global MAX_FILE_SIZE_MB
    if hasattr(args, "max_size"):
        MAX_FILE_SIZE_MB = args.max_size

    # Get flags
    backup = getattr(args, "backup", False)
    dry_run = getattr(args, "dry_run", False)

    if args.command == "read":
        return cmd_read(args.file, args.start, args.end)

    elif args.command == "find":
        return cmd_find(
            args.file,
            args.pattern,
            use_regex=args.regex,
            context=args.context,
            ignore_case=args.ignore_case,
            count_only=args.count,
        )

    elif args.command == "info":
        return cmd_info(args.file)

    elif args.command == "write":
        # Handle stdin
        content = args.content
        if content == "-":
            content = read_stdin()
        return cmd_write(args.file, content, backup, dry_run)

    elif args.command == "multiedit":
        edits_content = read_stdin()
        return cmd_multiedit(args.file, edits_content, backup, dry_run)

    elif args.command == "edit":
        # Handle stdin
        old_string = args.old_string
        new_string = args.new_string

        if old_string == "-":
            old_string = read_stdin()
        if new_string == "-":
            new_string = read_stdin()

        return cmd_edit(args.file, old_string, new_string, backup, dry_run)

    else:
        output_error(LFTError("UNKNOWN_COMMAND", f"Unknown command: {args.command}"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
