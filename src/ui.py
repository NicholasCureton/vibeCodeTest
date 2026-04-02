"""
FILE: ui.py
ROLE: Terminal Display

DESCRIPTION:
    Handles all terminal output: colors, formatting, streaming.
"""
from __future__ import annotations

import os
import sys
import io
from typing import Any, Dict, List, Optional


class Colors:
    """ANSI color codes."""
    GREY: str = "\033[90m"
    RED: str = "\033[91m"
    GREEN: str = "\033[92m"
    YELLOW: str = "\033[93m"
    BLUE: str = "\033[94m"
    MAGENTA: str = "\033[95m"
    CYAN: str = "\033[96m"
    WHITE: str = "\033[97m"
    BOLD: str = "\033[1m"
    DIM: str = "\033[2m"
    RESET: str = "\033[0m"


def clear_screen() -> None:
    """Clear terminal screen."""
    if os.name == 'nt':
        os.system('cls')
    else:
        print("\033[H\033[J", end="")


def display_status(text: str) -> None:
    """Display status message in cyan."""
    print(f"{Colors.CYAN}[*] {text}{Colors.RESET}")


def display_error(text: str) -> None:
    """Display error message in red."""
    print(f"{Colors.RED}[!] ERROR: {text}{Colors.RESET}")


def display_warning(text: str) -> None:
    """Display warning message in yellow."""
    print(f"{Colors.YELLOW}[!] {text}{Colors.RESET}")


def display_horizontal_rule(title: str = "", color: str = Colors.RESET) -> None:
    """Display decorative horizontal line."""
    width = 50
    if title:
        side = (width - len(title) - 2) // 2
        print(f"{color}{'=' * side} {title} {'=' * side}{Colors.RESET}")
    else:
        print(f"{color}{'=' * width}{Colors.RESET}")


def display_thinking_separator() -> None:
    """Display thinking section separator."""
    sys.stdout.write(
        f"\n{Colors.GREY}{'='*20} THINKING {'='*20}{Colors.RESET}\n"
    )
    sys.stdout.flush()


# Buffered stdout for smooth streaming
_stdout_buffer = io.TextIOWrapper(
    sys.stdout.buffer,
    encoding=sys.stdout.encoding,
    line_buffering=True
)


def stream_chunk(
    text: str,
    is_reasoning: bool = False,
    has_switched: bool = False
) -> None:
    """
    Stream a chunk of text.

    Args:
        text: Text to display
        is_reasoning: Whether this is reasoning content
        has_switched: Whether we switched from reasoning to content
    """
    if has_switched:
        _stdout_buffer.write(
            f"\n\n{Colors.CYAN}{'=' * 16} ASSISTANT ANSWER {'=' * 16}{Colors.RESET}\n"
        )

    color = Colors.GREY if is_reasoning else Colors.RESET
    _stdout_buffer.write(f"{color}{text}{Colors.RESET}")
    _stdout_buffer.flush()


# =============================================================================
# MARKDOWN STREAMING
# =============================================================================

# Lazy import to avoid circular dependency
_markdown_parser = None


def _get_markdown_parser():
    """Lazy initialization of markdown parser."""
    global _markdown_parser
    if _markdown_parser is None:
        from .core.markdown_stream import create_parser
        _markdown_parser = create_parser()
    return _markdown_parser


def stream_markdown_chunk(
    text: str,
    is_reasoning: bool = False,
    has_switched: bool = False,
    enable_markdown: bool = True
) -> None:
    """
    Stream a chunk of text with optional markdown rendering.

    When enable_markdown is True, parses markdown incrementally and
    renders complete elements. Incomplete elements are buffered until
    they can be properly formatted.

    When enable_markdown is False, streams plain text (fallback mode).

    Args:
        text: Text chunk to display
        is_reasoning: Whether this is reasoning content
        has_switched: Whether we switched from reasoning to content
        enable_markdown: Whether to apply markdown rendering
    """
    if has_switched:
        _stdout_buffer.write(
            f"\n\n{Colors.CYAN}{'=' * 16} ASSISTANT ANSWER {'=' * 16}{Colors.RESET}\n"
        )

    if is_reasoning:
        # Never render markdown in reasoning mode - keep it plain
        _stdout_buffer.write(f"{Colors.GREY}{text}{Colors.RESET}")
    elif enable_markdown:
        # Parse and render markdown incrementally
        parser = _get_markdown_parser()
        rendered = parser.feed(text)
        _stdout_buffer.write(rendered)
    else:
        # Plain text fallback
        _stdout_buffer.write(f"{text}{Colors.RESET}")

    _stdout_buffer.flush()


def finalize_markdown_stream() -> str:
    """
    Finalize markdown streaming and flush buffers.

    Call this after the LLM stream ends to render any remaining
    buffered markdown content.

    Returns:
        Any remaining buffered content (should be empty if all rendered).
    """
    global _markdown_parser
    if _markdown_parser is not None:
        remaining = _markdown_parser.finalize()
        _markdown_parser = None  # Reset for next conversation turn
        return remaining
    return ""


def reset_markdown_parser() -> None:
    """
    Reset the markdown parser without finalizing.

    Use this to abort markdown rendering mid-stream (e.g., user interrupt).
    """
    global _markdown_parser
    if _markdown_parser is not None:
        _markdown_parser.finalize()
        _markdown_parser = None


def display_tool_call(
    tool_name: str,
    tool_args: Dict[str, Any],
    output: str,
    success: bool,
    exit_code: int = 0,
    debug: bool = False
) -> None:
    """
    Display tool execution result.

    Args:
        tool_name: Name of the tool
        tool_args: Arguments passed to tool
        output: Tool output
        success: Whether tool succeeded
        exit_code: Tool exit code
        debug: Whether to show full output
    """
    # Get display command
    if tool_name == "execute_bash":
        display_cmd = tool_args.get("command", "")[:60]
    elif tool_name == "crawl_web":
        display_cmd = tool_args.get("url", "")[:60]
    elif tool_name == "file":
        display_cmd = f"{tool_args.get('command', '')} {tool_args.get('file_path', '')}"[:60]
    elif tool_name == "search_internet":
        display_cmd = f"search: {tool_args.get('query', '')}"[:60]
    else:
        display_cmd = str(tool_args)[:60]

    if len(display_cmd) > 60:
        display_cmd = display_cmd[:60] + "..."

    status_icon = f"{Colors.GREEN}✓{Colors.RESET}" if success else f"{Colors.RED}✗{Colors.RESET}"

    if debug:
        print(f"{Colors.MAGENTA}[Tool: {tool_name}]{Colors.RESET} {display_cmd}")
        display_horizontal_rule("OUTPUT", Colors.GREY)
        if output.strip():
            for i, line in enumerate(output.split('\n'), 1):
                print(f"{Colors.GREY}{i:4d}│{Colors.RESET} {line}")
        else:
            print(f"{Colors.GREY}(no output){Colors.RESET}")
        display_horizontal_rule("", Colors.GREY)
        print(f"{status_icon} Exit code: {exit_code}")
    else:
        # Truncate output for non-debug
        single_line = output.replace('\n', ' ').replace('\r', '')
        if len(single_line) > 2000:
            truncated = single_line[:2000] + "..."
        else:
            truncated = single_line

        if success:
            print(f"{Colors.MAGENTA}[Tool: {tool_name}]{Colors.RESET} {display_cmd}")
            print(f"    {Colors.GREY}→ {truncated}{Colors.RESET}")
        else:
            print(f"{Colors.RED}[Tool: {tool_name}] FAILED{Colors.RESET} {display_cmd}")
            print(f"    {Colors.RED}→ {truncated[:300]}{Colors.RESET}")


def display_stats(
    total_tokens: int,
    tokens_per_second: float,
    context_limit: Optional[int] = None
) -> None:
    """Display token statistics."""
    parts: List[str] = []

    if context_limit is not None and context_limit > 0:
        parts.append(f"{total_tokens}/{context_limit}")
    else:
        parts.append(str(total_tokens))

    parts.append(f"{tokens_per_second:.1f} t/s")

    print(Colors.GREY + "[" + " │ ".join(parts) + "]" + Colors.RESET)


def display_startup_banner(context_limit: int) -> None:
    """Display startup banner."""
    clear_screen()
    display_status("--- Session Started ---")

    if context_limit == 8192:
        print(f"{Colors.YELLOW}[!] Context: Using default (8192 tokens).{Colors.RESET}")
    else:
        print(
            f"{Colors.CYAN}[i] Server Context Limit: "
            f"{context_limit} tokens detected.{Colors.RESET}"
        )

    print(f"{Colors.GREY}Type /help for commands or /read to load files.{Colors.RESET}\n")


def show_help_menu() -> None:
    """Display help menu."""
    commands = [
        ("/help", "Show this menu"),
        ("/read <file1> <file2>", "Load files into context"),
        ("/edit [vim|nano]", "Multi-line input via editor (default: vim)"),
        ("/params", "Show all sampling parameters"),
        ("/temp <N>", "Set temperature (0.0-2.0)"),
        ("/top_p <N>", "Set top_p (0.0-1.0)"),
        ("/top_k <N>", "Set top_k (0-200)"),
        ("/min_p <N>", "Set min_p (0.0-1.0)"),
        ("/repeat_penalty <N>", "Set repeat_penalty (1.0-2.0)"),
        ("/presence_penalty <N>", "Set presence_penalty (-2.0 to 2.0)"),
        ("/think_on", "Enable reasoning mode"),
        ("/think_off", "Disable reasoning mode (no reasoning content)"),
        ("/agent on", "Enable agent mode (auto tool execution)"),
        ("/agent off", "Disable agent mode (Y/n confirmation)"),
        ("/agent debug on/off", "Toggle debug output for tools"),
        ("/agent status", "Show agent status"),
        ("/clear", "Clear conversation history"),
        ("/exit or /quit", "Exit program"),
    ]
    display_horizontal_rule("HELP MENU", Colors.CYAN)
    for cmd, desc in commands:
        print(f" {Colors.GREEN}{cmd:<28}{Colors.RESET} {desc}")
    display_horizontal_rule("", Colors.CYAN)


def display_agent_status(mode: str, debug: bool, max_iterations: int) -> None:
    """Display agent status."""
    mode_str = f"{Colors.GREEN}ON{Colors.RESET}" if mode == "on" else f"{Colors.YELLOW}OFF{Colors.RESET}"
    debug_str = f"{Colors.CYAN}ON{Colors.RESET}" if debug else f"{Colors.GREY}OFF{Colors.RESET}"

    display_horizontal_rule("AGENT STATUS", Colors.CYAN)
    print(f"  Mode:           {mode_str}")
    print(f"  Debug:          {debug_str}")
    print(f"  Max Iterations: {max_iterations}")
    display_horizontal_rule("", Colors.CYAN)


def display_params_table(params: Dict[str, Any]) -> None:
    """Display parameters table."""
    display_horizontal_rule("LIVE PARAMETERS", Colors.YELLOW)
    for k, v in params.items():
        print(f" {Colors.CYAN}{k:<20}{Colors.RESET}: {v}")
    display_horizontal_rule("", Colors.YELLOW)


def prompt_tool_confirmation(cmd: str) -> str:
    """Prompt for tool execution confirmation."""
    print(f"\n{Colors.YELLOW}Execute? [Y/n]: {cmd}{Colors.RESET}")
    return input("> ")


def display_interrupted() -> None:
    """Display interrupted message."""
    print(f"\n{Colors.YELLOW}[!] Generation Interrupted by User.{Colors.RESET}")


def display_closed_by_user() -> None:
    """Display closed message."""
    print(f"\n\n{Colors.YELLOW}[!] Closed by user.{Colors.RESET}")


def display_skipped() -> None:
    """Display skipped message."""
    print("Tool execution skipped by user. STOP and Wait for instructions. DO NOT PROCEED.\n")
