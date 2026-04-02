#!/usr/bin/env python3
"""
FILE: cli.py
ROLE: CLI Parsing and Command Handling

DESCRIPTION:
    Handles argument parsing and interactive mode command loop.
    Coordinates between all modules for the main interactive session.
"""
from __future__ import annotations

import argparse
import os
import shlex
from typing import Any, Dict, List, Optional

from . import settings, ui
from .chat_runner import run_chat, AgentMode
from .commands import read_command, edit_command
from .memory import ChatHistory


def run_one_shot_mode(
    message: str,
    system_prompt: str,
    custom_history_path: Optional[str],
    llm_client,
    context_limit: int,
    no_history: bool,
    server_think: bool,
) -> None:
    """
    Run one-shot mode (single message, then exit).
    
    Args:
        message: User's message
        system_prompt: System prompt text
        custom_history_path: Custom chat history path (if any)
        llm_client: LLM client instance
        context_limit: Context window size
        no_history: Skip loading previous history
        save_thinking: Save reasoning to history
        server_think: Enable server-side reasoning
    """
    # Create memory handlers
    if custom_history_path:
        chat_history = ChatHistory(filename=custom_history_path)
    else:
        chat_history = ChatHistory()
    
    # Load previous history unless --no-history flag is set
    history: List[Dict[str, Any]] = []
    if not no_history:
        history = chat_history.load()
    
    # One-shot mode: disable markdown rendering for raw output
    # Agent mode is always ON in one-shot mode (no tool confirmation prompts)
    run_chat(
        user_input=message,
        history=history,
        system_prompt=system_prompt,
        llm_client=llm_client,
        agent_mode=AgentMode.ON,
        agent_debug=False,
        server_think=server_think,
        context_limit=context_limit,
        chat_history=chat_history,
        enable_markdown=False
    )


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="CLI Chat with Tool Calling")
    parser.add_argument(
        "message",
        nargs="?",
        help="Optional one-shot message"
    )
    parser.add_argument(
        "--show-reasoning",
        action="store_true",
        help="Show reasoning in output"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock LLM client for testing"
    )
    parser.add_argument(
        "--system-prompt",
        dest="system_prompt",
        type=str,
        help="Override system prompt file path. Chat history will be saved alongside it."
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="Start fresh without loading previous chat history (one-shot mode)"
    )
    return parser.parse_args()


def handle_params_command(parts: List[str]) -> None:
    """Handle parameter commands (/params, /temp, /top_p, etc.)."""
    param_map = {
        "/params": "params",
        "/temp": "temperature",
        "/top_p": "top_p",
        "/top_k": "top_k",
        "/min_p": "min_p"
    }
    
    cmd = parts[0].lower()
    
    if cmd == "/params":
        ui.display_params_table(settings.get_all())
    elif cmd in param_map:
        if len(parts) > 1:
            key = param_map[cmd]
            success, message = settings.update(key, parts[1])
            if success:
                ui.display_status(message)
            else:
                ui.display_error(message)
        else:
            ui.display_error(f"Usage: {cmd} [value]")


def handle_agent_command(parts: List[str], agent_mode: str, agent_debug: bool) -> tuple[str, bool]:
    """
    Handle /agent command.
    
    Returns:
        (updated_agent_mode, updated_agent_debug)
    """
    if len(parts) > 1:
        sub = parts[1].lower()
        if sub == "on":
            agent_mode = AgentMode.ON
            ui.display_status("Agent mode ON")
        elif sub == "off":
            agent_mode = AgentMode.OFF
            ui.display_status("Agent mode OFF")
        elif sub == "debug":
            if len(parts) > 2:
                agent_debug = parts[2].lower() == "on"
                ui.display_status(f"Agent debug: {agent_debug}")
            else:
                ui.display_error("Usage: /agent debug on/off")
        elif sub == "status":
            ui.display_agent_status(
                agent_mode,
                agent_debug,
                settings.get("max_agent_iterations", 10)
            )
        else:
            ui.display_error(f"Unknown agent command: {sub}")
    else:
        ui.display_error("Usage: /agent on|off|debug|status")
    
    return agent_mode, agent_debug


def run_interactive_mode(
    system_prompt: str,
    custom_history_path: Optional[str],
    llm_client,
    context_limit: int,
    show_ui_reasoning: bool,
) -> None:
    """
    Run the interactive chat mode.
    
    Args:
        system_prompt: System prompt text
        custom_history_path: Custom chat history path (if any)
        llm_client: LLM client instance
        context_limit: Context window size
        show_ui_reasoning: Show reasoning in UI
    """
    # Initialize state
    server_think: bool = True
    agent_mode: str = AgentMode.OFF
    agent_debug: bool = False

    # Create memory handlers
    if custom_history_path:
        chat_history = ChatHistory(filename=custom_history_path)
    else:
        chat_history = ChatHistory()

    # Load history
    history: List[Dict[str, Any]] = chat_history.load()
    ui.display_status("Interactive Mode. Type /help for commands.")

    while True:
        t_stat = "ON" if server_think else "OFF"
        a_stat = f" [AGENT-{agent_mode.upper()}]" if agent_mode == AgentMode.ON else ""
        
        try:
            user_input = input(
                f"User [THINK-{t_stat}]{a_stat}: "
            ).strip()
        except EOFError:
            break
        
        if not user_input:
            continue
        
        # Handle commands
        if user_input.startswith("/"):
            try:
                parts = shlex.split(user_input, posix=(os.name == 'posix'))
            except ValueError as e:
                ui.display_error(f"Command error: {e}")
                continue
            
            cmd = parts[0].lower()
            
            # Parameter commands
            if cmd in ["/params", "/temp", "/top_p", "/top_k", "/min_p"]:
                handle_params_command(parts)
                continue
            
            # File reading
            if cmd == "/read":
                read_command(parts, history, chat_history)
                continue

            # Multi-line editor command
            if cmd == "/edit":
                content = edit_command(parts, history, chat_history)
                if content:
                    user_input = content
                    # Edited content should be sent to LLM, skip remaining command checks
                    # Don't continue - let it fall through to run_chat
                else:
                    continue
            elif cmd == "/agent":
                agent_mode, agent_debug = handle_agent_command(parts, agent_mode, agent_debug)
                continue

            # Simple commands (only for actual commands, not edited content)
            elif user_input.lower() == "/help":
                ui.show_help_menu()
            elif user_input.lower() == "/think_on":
                server_think = True
                ui.display_status("Thinking enabled.")
            elif user_input.lower() == "/think_off":
                server_think = False
                ui.display_status("Thinking disabled.")
            elif user_input.lower() == "/clear":
                chat_history.clear()
                history.clear()
                ui.display_status("History cleared.")
            elif user_input.lower() in ["/exit", "/quit"]:
                break
            else:
                ui.display_error(f"Unknown command: {cmd}")
            continue
        
        # Run chat
        try:
            # Interactive mode: enable markdown rendering for beautiful output
            run_chat(
                user_input=user_input,
                history=history,
                system_prompt=system_prompt,
                llm_client=llm_client,
                agent_mode=agent_mode,
                agent_debug=agent_debug,
                server_think=server_think,
                context_limit=context_limit,
                chat_history=chat_history,
                enable_markdown=True
            )
        except Exception as e:
            ui.display_error(f"Chat session failed: {e}")
            print("Press Ctrl+C to exit or restart the session.")
            break
