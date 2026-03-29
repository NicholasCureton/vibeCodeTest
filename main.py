#!/usr/bin/env python3
"""
FILE: main.py
ROLE: Entry Point

DESCRIPTION:
    Main entry point for the CLI chat application.
    Wires together all modules and handles user interaction.

USAGE:
    python main.py                                # Interactive mode
    python main.py "message"                      # One-shot mode (loads history)
    python main.py "message" --no-history         # One-shot fresh start
    python main.py --mock                         # Use mock LLM (testing)
    python main.py --system-prompt prompts/coder.md   # Custom system prompt
    python main.py "task" --system-prompt /path/to/researcher.md  # Sub-agent mode

CHAT HISTORY:
    When --system-prompt is used, chat history is saved alongside the prompt:
        /path/to/coder_system_prompt.md → /path/to/coder_chat_history.jsonl
        /path/to/researcher.md → /path/to/researcher_chat_history.jsonl
    
    One-shot mode loads previous history by default. Use --no-history to start fresh.
    History includes: user/assistant/tool messages, reasoning_content, tool_calls.
"""
from __future__ import annotations

import sys
import argparse
import shlex
import os
import glob
from typing import Any, Dict, List, Optional

# Import modules
import settings
import ui

from llm import LLMClient, MockLLMClient
from llm.types import StreamingTimeoutError
from tools import execute, get_schemas, build_tool_result_message
from memory import ChatHistory, ProjectState
from core import DEFAULT_SYSTEM_PROMPT

try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False
    readline = None


# =============================================================================
# TAB COMPLETION FOR /read
# =============================================================================

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


# Setup readline tab completion
if READLINE_AVAILABLE:
    # Handle macOS libedit vs Linux readline
    if readline.__doc__ and 'libedit' in readline.__doc__:
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
    readline.set_completer(path_completer)
    readline.set_completer_delims(' \t\n;')


# =============================================================================
# AGENT MODE
# =============================================================================

class AgentMode:
    OFF: str = "off"
    ON: str = "on"


# =============================================================================
# SYSTEM PROMPT LOADING
# =============================================================================

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


def load_system_prompt(prompt_path: Optional[str] = None) -> tuple[str, Optional[str]]:
    """
    Load system prompt from file or use default.
    
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

    return DEFAULT_SYSTEM_PROMPT, None


# =============================================================================
# FILE READING
# =============================================================================

def read_files_for_context(filepaths: List[str]) -> tuple[str, List[str]]:
    """
    Read files for context injection.

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


# =============================================================================
# CHAT EXECUTION
# =============================================================================

def run_chat(
    user_input: str,
    history: List[Dict[str, Any]],
    system_prompt: str,
    llm_client,
    agent_mode: str,
    agent_debug: bool,
    server_think: bool,
    save_thinking: bool,
    context_limit: int,
    chat_history: ChatHistory,
    enable_markdown: bool = True,
) -> None:
    """
    Execute a chat turn.

    Handles the full loop: send to LLM, handle tool calls, return response.

    Args:
        user_input: User's message
        history: Conversation history
        system_prompt: System prompt text
        llm_client: LLM client instance
        agent_mode: Agent mode setting
        agent_debug: Debug mode for tools
        server_think: Enable server-side reasoning
        save_thinking: Save reasoning to history
        context_limit: Context window size
        chat_history: Chat history handler
        enable_markdown: Enable markdown rendering (interactive mode only)
    """
    max_iterations = settings.get("max_agent_iterations", 10)
    params = settings.get_params()

    history.append({"role": "user", "content": user_input})
    chat_history.save("user", user_input)

    tool_id_counter = 0
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        messages = [{"role": "system", "content": system_prompt}] + history
        prompt_tokens = llm_client.get_token_count(messages)

        try:
            chunks = llm_client.call(
                messages=messages,
                params=params,
                tools=get_schemas(),
                server_think=server_think,
                stream=True
            )
        except StreamingTimeoutError as e:
            ui.display_error(str(e))
            return
        except Exception as e:
            ui.display_error(f"LLM error: {e}")
            return

        if chunks is None:
            ui.display_error("Failed to connect to LLM")
            return

        # Process streaming response
        full_content = ""
        full_reasoning = ""
        tool_calls: List[Dict[str, Any]] = []
        finish_reason = "stop"
        first_content = True
        currently_thinking = False
        completion_tokens = 0
        tokens_per_second = 0.0

        ui.display_assistant_label()

        try:
            for chunk in chunks:
                choices = chunk.get("choices", [])
                if not choices:
                    continue

                choice = choices[0]
                delta = choice.get("delta", {})

                fr = choice.get("finish_reason")
                if fr is not None:
                    finish_reason = fr

                timings = chunk.get("timings", {})
                if timings:
                    completion_tokens = timings.get("predicted_n", 0)
                    tokens_per_second = timings.get("predicted_per_second", 0.0)

                # Handle reasoning content
                if "reasoning_content" in delta:
                    text = delta["reasoning_content"]
                    if text:
                        full_reasoning += text
                        if not currently_thinking:
                            currently_thinking = True
                            ui.display_thinking_separator()
                        # Never render markdown in reasoning mode
                        ui.stream_chunk(text, is_reasoning=True)

                # Handle main content
                elif "content" in delta:
                    text = delta["content"]
                    if text:
                        full_content += text
                        switched = currently_thinking or first_content
                        if currently_thinking:
                            currently_thinking = False
                        if first_content:
                            first_content = False
                        # Use markdown streaming for interactive mode
                        ui.stream_markdown_chunk(
                            text,
                            is_reasoning=False,
                            has_switched=switched,
                            enable_markdown=enable_markdown
                        )

                # Handle tool calls
                if "tool_calls" in delta:
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        while len(tool_calls) <= idx:
                            tool_calls.append({
                                "id": f"call_{tool_id_counter}",
                                "type": "function",
                                "function": {"name": "", "arguments": ""}
                            })
                            tool_id_counter += 1

                        if "id" in tc_delta:
                            tool_calls[idx]["id"] = tc_delta["id"]
                        if "type" in tc_delta:
                            tool_calls[idx]["type"] = tc_delta["type"]
                        if "function" in tc_delta:
                            func = tc_delta["function"]
                            if "name" in func:
                                tool_calls[idx]["function"]["name"] += func["name"]
                            if "arguments" in func:
                                tool_calls[idx]["function"]["arguments"] += func["arguments"]

        except KeyboardInterrupt:
            ui.display_interrupted()
            # Reset markdown parser to clear any buffers
            ui.reset_markdown_parser()
            if full_content.strip() or (save_thinking and full_reasoning.strip()):
                chat_history.save("assistant", full_content, full_reasoning if save_thinking else None)
                history.append({
                    "role": "assistant",
                    "content": full_content,
                    "reasoning_content": full_reasoning
                })
            return

        # Finalize markdown streaming - flush any remaining buffers
        if enable_markdown:
            remaining = ui.finalize_markdown_stream()
            if remaining:
                # Should be empty, but print just in case
                print(remaining, end="")

        print()

        # Display stats
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens > 0:
            ui.display_stats(total_tokens, tokens_per_second, context_limit)

        # Handle finish
        if finish_reason == "stop":
            if full_content.strip() or (save_thinking and full_reasoning.strip()):
                chat_history.save("assistant", full_content, full_reasoning if save_thinking else None)
                history.append({
                    "role": "assistant",
                    "content": full_content,
                    "reasoning_content": full_reasoning
                })
            return

        # Handle tool calls
        if finish_reason == "tool_calls" and tool_calls:
            chat_history.save(
                role="assistant",
                content=full_content,
                reasoning=full_reasoning if save_thinking else None,
                tool_calls=tool_calls
            )
            history.append({
                "role": "assistant",
                "content": full_content,
                "reasoning_content": full_reasoning,
                "tool_calls": tool_calls
            })

            # Execute each tool
            for tool_call in tool_calls:
                tool_call_id = tool_call.get("id", "")
                function = tool_call.get("function", {})
                tool_name = function.get("name", "")
                arguments_json = function.get("arguments", "{}")

                import json
                try:
                    args = json.loads(arguments_json)
                except json.JSONDecodeError:
                    args = {}

                # Confirmation (if not in agent mode)
                if agent_mode == AgentMode.OFF:
                    cmd = args.get("command", str(args)) if tool_name == "execute_bash" else str(args)
                    confirm = ui.prompt_tool_confirmation(cmd)
                    if confirm != "Y":
                        ui.display_skipped()
                        skip_msg = build_tool_result_message(
                            tool_call_id=tool_call_id,
                            result="Tool execution skipped by user. STOP and Wait for instructions. DO NOT PROCEED."
                        )
                        chat_history.save(
                            role="tool",
                            content="Tool execution skipped by user. STOP and Wait for instructions. DO NOT PROCEED.",
                            tool_call_id=tool_call_id
                        )
                        history.append(skip_msg)
                        continue

                # Execute tool
                result = execute(
                    tool_name,
                    arguments_json,
                    timeout=settings.get("bash_timeout", 60)
                )

                print()
                ui.display_tool_call(
                    tool_name=tool_name,
                    tool_args=args,
                    output=result.output if result.output else result.error or "(no output)",
                    success=result.success,
                    exit_code=result.exit_code,
                    debug=agent_debug
                )
                print()

                # Build result message
                tool_content = result.output
                if not result.success and result.error:
                    tool_content = f"ERROR: {result.error}\n\nOutput: {result.output}"

                tool_result_msg = build_tool_result_message(
                    tool_call_id=tool_call_id,
                    result=tool_content
                )

                chat_history.save(
                    role="tool",
                    content=tool_content,
                    tool_call_id=tool_call_id
                )
                history.append(tool_result_msg)

            continue

        ui.display_error(f"Unknown finish_reason: {finish_reason}")
        return

    ui.display_warning(f"Reached max iterations ({max_iterations}). Stopping.")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main() -> None:
    """Main entry point."""
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
    args = parser.parse_args()

    is_one_shot: bool = bool(args.message)
    save_thinking: bool = False
    server_think: bool = True
    show_ui_reasoning: bool = args.show_reasoning
    # One-shot mode auto-enables agent mode (no tool confirmation prompts)
    agent_mode: str = AgentMode.ON if is_one_shot else AgentMode.OFF
    agent_debug: bool = False

    # Create LLM client
    if args.mock:
        llm_client = MockLLMClient()
    else:
        llm_client = LLMClient(
            server_url=settings.get("server_url", "http://localhost:8080"),
            stream_timeout=settings.get("stream_timeout", 120),
            model_name=settings.get("model_name", "model.gguf")
        )

    system_prompt, custom_history_path = load_system_prompt(args.system_prompt)
    history: List[Dict[str, Any]] = []
    context_limit = llm_client.get_context_limit()

    # Create memory handlers
    # Use custom chat history path if --system-prompt was provided
    if custom_history_path:
        chat_history = ChatHistory(filename=custom_history_path)
    else:
        chat_history = ChatHistory()
    project_state = ProjectState()

    if not is_one_shot:
        ui.display_startup_banner(context_limit)

    try:
        if is_one_shot:
            if args.message:
                # Load previous history unless --no-history flag is set
                if not args.no_history:
                    history = chat_history.load()
                # One-shot mode: disable markdown rendering for raw output
                run_chat(
                    user_input=args.message,
                    history=history,
                    system_prompt=system_prompt,
                    llm_client=llm_client,
                    agent_mode=agent_mode,
                    agent_debug=agent_debug,
                    server_think=server_think,
                    save_thinking=save_thinking,
                    context_limit=context_limit,
                    chat_history=chat_history,
                    enable_markdown=False
                )
            return

        # Interactive mode
        history = chat_history.load()
        ui.display_status("Interactive Mode. Type /help for commands.")

        while True:
            t_stat = "ON" if server_think else "OFF"
            a_stat = f" [AGENT-{agent_mode.upper()}]" if agent_mode == AgentMode.ON else ""
            s_stat = " [SAVE-ON]" if save_thinking else ""

            try:
                user_input = input(
                    f"User [THINK-{t_stat}]{a_stat}{s_stat}: "
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
                    if cmd == "/params":
                        ui.display_params_table(settings.get_all())
                    else:
                        param_map = {
                            "/temp": "temperature",
                            "/top_p": "top_p",
                            "/top_k": "top_k",
                            "/min_p": "min_p"
                        }
                        if len(parts) > 1:
                            key = param_map[cmd]
                            success, message = settings.update(key, parts[1])
                            if success:
                                ui.display_status(message)
                            else:
                                ui.display_error(message)
                        else:
                            ui.display_error(f"Usage: {cmd} [value]")
                    continue

                # File reading
                if cmd == "/read":
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
                    continue

                # Agent commands
                if cmd == "/agent":
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
                    continue

                # Simple commands
                if user_input.lower() == "/help":
                    ui.show_help_menu()
                elif user_input.lower() == "/think_on":
                    server_think = True
                    ui.display_status("Thinking enabled.")
                elif user_input.lower() == "/think_off":
                    server_think = False
                    ui.display_status("Thinking disabled.")
                elif "/save_thinking" in user_input.lower():
                    save_thinking = "on" in user_input.lower()
                    ui.display_status(f"Save reasoning: {save_thinking}")
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
                    save_thinking=save_thinking,
                    context_limit=context_limit,
                    chat_history=chat_history,
                    enable_markdown=True
                )
            except Exception as e:
                ui.display_error(f"Chat session failed: {e}")
                print("Press Ctrl+C to exit or restart the session.")
                break

    except KeyboardInterrupt:
        ui.display_closed_by_user()
        sys.exit(0)


if __name__ == "__main__":
    main()
