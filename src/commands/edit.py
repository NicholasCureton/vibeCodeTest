#!/usr/bin/env python3
"""
FILE: commands/edit.py
ROLE: /edit Command Implementation

DESCRIPTION:
    Opens a text editor for multi-line input.
    Supports custom editor from settings or command argument.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

from .. import settings, ui


def edit_command(
    parts: List[str],
    history: List[Dict[str, Any]],
    chat_history
) -> None:
    """
    Execute /edit command.

    Opens a text editor for multi-line input, then saves the content
    to chat history.

    Args:
        parts: Command parts from shlex.split (includes '/edit')
        history: Conversation history list
        chat_history: ChatHistory instance for saving

    Returns:
        The edited content if successful, None otherwise
    """
    try:
        # Determine editor: command arg > settings.json > fallback
        editor = settings.get("editor", "vim")
        if len(parts) > 1:
            editor = parts[1].lower()

        # Validate editor exists
        if not shutil.which(editor):
            ui.display_error(
                f"Editor '{editor}' not found. "
                f"Set a valid editor in settings.json or use: /edit vim (or /edit nano)"
            )
            return None

        # Create temp file for editing
        temp_fd: int
        temp_path: str
        try:
            temp_fd, temp_path = tempfile.mkstemp(
                suffix=".txt",
                prefix="chat_edit_",
            )
            os.close(temp_fd)  # Close fd, will open normally
        except OSError as e:
            ui.display_error(f"Could not create temp file: {e}")
            return None

        # Save placeholder to history BEFORE opening editor (power outage safety)
        placeholder = f"[Multi-line input via /edit in {editor}]"
        history.append({"role": "user", "content": placeholder})
        try:
            chat_history.save("user", placeholder)
        except IOError as e:
            # Rollback: remove placeholder if save fails
            history.pop()
            ui.display_error(f"Could not save history: {e}")
            return None

        try:
            # Open editor (BLOCKS until editor exits)
            subprocess.run([editor, temp_path])

            # Read edited content
            with open(temp_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if content:
                # Replace placeholder with actual content
                history[-1]["content"] = content
                chat_history.save("user", content)
                ui.display_status(
                    f"Multi-line input loaded ({len(content)} chars from {editor})"
                )
                return content
            else:
                # Empty file - remove placeholder
                if history:  # Safety check
                    history.pop()
                ui.display_status("Edit cancelled (empty file)")
                return None

        except subprocess.SubprocessError as e:
            if history:
                history.pop()
            ui.display_error(f"Editor error: {e}")
            return None
        except OSError as e:
            if history:
                history.pop()
            ui.display_error(f"Could not read editor output: {e}")
            return None
        except Exception as e:
            if history:
                history.pop()
            ui.display_error(f"Unexpected error: {type(e).__name__}: {e}")
            return None
        finally:
            # Cleanup temp file
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass  # Temp file cleanup failure is not critical

    except Exception as e:
        # Catch-all for any unexpected errors
        ui.display_error(f"Critical error in /edit: {type(e).__name__}: {e}")
        return None
