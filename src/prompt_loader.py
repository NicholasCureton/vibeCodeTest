#!/usr/bin/env python3
"""
FILE: prompt_loader.py
ROLE: System Prompt Loading

DESCRIPTION:
    Loads system prompts from files or uses defaults.
    Derives chat history paths from prompt paths.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

from . import settings
from .core import DEFAULT_SYSTEM_PROMPT


def derive_chat_history_path(prompt_path: str) -> str:
    """
    Derive chat history filename from system prompt path.

    Rules:
        - Same directory as system prompt file
        - Strip .md extension
        - Strip _system_prompt suffix if present
        - Append _chat_history.jsonl

    Examples:
        /path/to/coder_system_prompt.md → /path/to/coder_chat_history.jsonl
        /path/to/researcher.md → /path/to/researcher_chat_history.jsonl
        prompts/main_agent.md → prompts/main_agent_chat_history.jsonl

    Args:
        prompt_path: Path to system prompt file

    Returns:
        Derived chat history path
    """
    expanded = os.path.expanduser(prompt_path)
    directory = os.path.dirname(expanded)
    filename = os.path.basename(expanded)

    # Remove .md extension
    if filename.endswith(".md"):
        base_name = filename[:-3]
    else:
        base_name = filename

    # Remove _system_prompt suffix if present
    if base_name.endswith("_system_prompt"):
        base_name = base_name[:-14]

    # Build new filename
    history_filename = f"{base_name}_chat_history.jsonl"

    if directory:
        return os.path.join(directory, history_filename)
    else:
        return history_filename


def load_system_prompt(prompt_path: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Load system prompt from file or use default.

    Priority order:
        1. Command line --system-prompt argument
        2. Settings file system_prompt_path
        3. Default location (prompts/main_agent.md)
        4. Built-in DEFAULT_SYSTEM_PROMPT

    Args:
        prompt_path: Optional path to prompt file (overrides settings)

    Returns:
        (system_prompt_string, chat_history_path or None)
        chat_history_path is only set when prompt_path is provided via CLI
    """
    chat_history_path = None

    # Priority 1: Command line --system-prompt argument
    if prompt_path:
        expanded = os.path.expanduser(prompt_path)
        if os.path.exists(expanded):
            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # Derive chat history path from prompt path
                chat_history_path = derive_chat_history_path(prompt_path)
                return content, chat_history_path
            except IOError as e:
                print(f"[system_prompt] Could not read {expanded}: {e}")
        else:
            print(f"[system_prompt] Prompt file not found: {expanded}")

    # Priority 2: Settings file system_prompt_path
    custom_path = settings.get("system_prompt_path", "")
    if custom_path:
        expanded = os.path.expanduser(custom_path)
        if os.path.exists(expanded):
            try:
                with open(expanded, "r", encoding="utf-8") as f:
                    return f.read().strip(), None
            except IOError as e:
                print(f"[system_prompt] Could not read {expanded}: {e}")

    # Priority 3: Default location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_path = os.path.join(script_dir, "prompts", "main_agent.md")
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                return f.read().strip(), None
        except IOError:
            pass

    # Priority 4: Built-in default
    return DEFAULT_SYSTEM_PROMPT, None
