#!/usr/bin/env python3
"""
FILE: commands/read.py
ROLE: /read Command Implementation

DESCRIPTION:
    Reads files and injects their content into chat history.
    Supports tab completion for file paths.
"""
from __future__ import annotations

import glob
import os
from typing import List, Optional, Tuple

from .. import settings, ui

# Readline import for tab completion
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False
    readline = None


def path_completer(text: str, state: int) -> Optional[str]:
    """
    Tab completion for file paths after /read command.

    Args:
        text: Current text being completed
        state: Index of match to return

    Returns:
        Matching path or None
    """
    if not READLINE_AVAILABLE:
        return None

    line = readline.get_line_buffer()
    if line.startswith("/read "):
        expanded_path = os.path.expanduser(text)
        matches = glob.glob(expanded_path + '*')
        # Add trailing slash for directories
        results = [m + os.sep if os.path.isdir(m) else m for m in matches]
        try:
            return results[state]
        except IndexError:
            return None
    return None


def setup_tab_completion() -> None:
    """Setup readline tab completion for /read command."""
    if READLINE_AVAILABLE:
        # Handle macOS libedit vs Linux readline
        if readline.__doc__ and 'libedit' in readline.__doc__:
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
        readline.set_completer(path_completer)
        readline.set_completer_delims(' \t\n;')


def read_files_for_context(filepaths: List[str]) -> Tuple[str, List[str]]:
    """
    Read files for context injection.

    Args:
        filepaths: List of file paths to read

    Returns:
        (combined_content, warnings)
    """
    TEXT_EXTENSIONS = {
        '.py', '.js', '.ts', '.java', '.c', '.cpp', '.h', '.hpp', '.cs',
        '.go', '.rs', '.rb', '.php', '.swift', '.kt', '.md', '.txt',
        '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.sh', '.bash',
    }

    combined = []
    warnings = []
    max_size = settings.get("max_file_size", 10485760)

    for path in filepaths:
        path = os.path.expanduser(path)

        if not os.path.exists(path):
            warnings.append(f"File not found: {path}")
            continue

        if os.path.isdir(path):
            warnings.append(f"Skipping directory: {path}")
            continue

        ext = os.path.splitext(path.lower())[1]
        if ext not in TEXT_EXTENSIONS and ext != '':
            warnings.append(f"Skipping binary file: {path}")
            continue

        size = os.path.getsize(path)
        if size > max_size:
            warnings.append(f"File too large ({size // 1024 // 1024}MB): {path}")
            continue

        try:
            with open(path, "r", encoding="utf-8", errors="strict") as f:
                content = f.read()
                if content.strip():
                    filename = os.path.basename(path)
                    combined.append(f"\n[FILE: {filename}]\n{content}\n[END {filename}]")
        except UnicodeDecodeError:
            warnings.append(f"Could not decode as UTF-8: {path}")
        except IOError as e:
            warnings.append(f"Could not read {path}: {e}")

    return "\n".join(combined), warnings


def read_command(
    parts: List[str],
    history: List[dict],
    chat_history
) -> None:
    """
    Execute /read command.

    Reads specified files and adds their content to chat history.

    Args:
        parts: Command parts from shlex.split (includes '/read')
        history: Conversation history list
        chat_history: ChatHistory instance for saving
    """
    if len(parts) > 1:
        content, warnings = read_files_for_context(parts[1:])
        for warning in warnings:
            ui.display_warning(warning)
        if content.strip():
            history.append({"role": "user", "content": content})
            chat_history.save("user", content)
            ui.display_status(f"Loaded {len(parts) - 1} file(s).")
    else:
        ui.display_error("Usage: /read <file1> <file2> ...")
