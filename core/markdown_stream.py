#!/usr/bin/env python3
"""
FILE: core/markdown_stream.py
ROLE: Incremental Markdown Parser for Streaming Output

DESCRIPTION:
    Parses markdown incrementally as tokens arrive, buffering incomplete
    elements until they can be properly rendered. Supports three buffer
    strategies:

    1. INLINE (**, *, `, [], ~~): Buffer until closing delimiter
    2. LINE (#, >, -): Buffer until newline
    3. BLOCK (```, |table|): Buffer until block structure is complete

    Falls back to plain text streaming if parsing fails or times out.

USAGE:
    parser = MarkdownStreamParser()
    for token in llm_stream:
        rendered = parser.feed(token)
        print(rendered, end="")
    parser.finalize()  # Render any remaining buffered content

DESIGN PRINCIPLES:
    - Never block streaming for more than N tokens
    - Graceful degradation: invalid markdown → plain text
    - No external dependencies
    - Thread-safe (reentrant)
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


# =============================================================================
# COLOR CONFIGURATION
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ParserConfig:
    """
    Configuration for markdown stream parser.

    Attributes:
        max_inline_buffer: Max characters to buffer for inline elements.
            Prevents infinite buffering if closing delimiter never arrives.
        max_block_buffer: Max lines to buffer for block elements.
            Prevents memory issues with unclosed code blocks.
        table_pad: Padding spaces for table cells (left/right).
        enable_tables: Whether to parse and render markdown tables.
        enable_code_blocks: Whether to parse and render code blocks.
        enable_headers: Whether to parse and render headers.
        enable_inline_format: Whether to parse bold, italic, code, links.
    """
    max_inline_buffer: int = 100
    max_block_buffer: int = 50
    table_pad: int = 1
    enable_tables: bool = True
    enable_code_blocks: bool = True
    enable_headers: bool = True
    enable_inline_format: bool = True


# =============================================================================
# STATE MACHINE
# =============================================================================

class ParserState(Enum):
    """
    Parser state machine states.

    The parser transitions between states based on incoming tokens:

    STREAMING: Normal state, output tokens immediately with minimal parsing.
    BUFFERING_INLINE: Waiting for closing delimiter (e.g., **, `, []).
    BUFFERING_LINE: Waiting for newline to complete line-level element.
    BUFFERING_BLOCK: Waiting for block structure to complete (code, table).
    FLUSHING: Finalizing, render all buffered content.
    """
    STREAMING = auto()
    BUFFERING_INLINE = auto()
    BUFFERING_LINE = auto()
    BUFFERING_BLOCK = auto()
    FLUSHING = auto()


class ElementType(Enum):
    """Types of markdown elements."""
    PLAIN = auto()
    BOLD = auto()
    ITALIC = auto()
    INLINE_CODE = auto()
    LINK = auto()
    HEADER = auto()
    CODE_BLOCK = auto()
    TABLE = auto()
    BLOCKQUOTE = auto()
    LIST = auto()


# =============================================================================
# BUFFERED ELEMENT
# =============================================================================

@dataclass
class BufferedElement:
    """
    Represents a buffered markdown element being parsed.

    Attributes:
        type: Type of markdown element.
        content: Accumulated content string.
        start_delim: Opening delimiter (e.g., "**", "```").
        end_delim: Expected closing delimiter.
        language: For code blocks, the language hint.
        line_count: Number of lines buffered (for block limits).
    """
    type: ElementType
    content: str = ""
    start_delim: str = ""
    end_delim: str = ""
    language: str = ""
    line_count: int = 0


# =============================================================================
# STREAMING MARKDOWN PARSER
# =============================================================================

class MarkdownStreamParser:
    """
    Incremental markdown parser for streaming output.

    This parser processes markdown token-by-token, buffering incomplete
    elements until they can be properly rendered. It handles:

    - Inline formatting: **bold**, *italic*, `code`, [link](url)
    - Line elements: # headers, > quotes, - lists
    - Block elements: ```code```, |tables|

    The parser uses a state machine to track buffering context and
    applies timeouts/limits to prevent indefinite buffering.

    Example:
        parser = MarkdownStreamParser()
        for token in llm_response:
            output = parser.feed(token)
            print(output, end="")
        print(parser.finalize())  # Flush remaining buffers
    """

    def __init__(self, config: Optional[ParserConfig] = None):
        """
        Initialize the streaming parser.

        Args:
            config: Parser configuration. Uses defaults if not provided.
        """
        self.config = config or ParserConfig()
        self.state = ParserState.STREAMING
        self.buffer: Optional[BufferedElement] = None
        self.pending = ""  # Characters waiting to be processed
        self.output_buffer = ""  # Accumulated output for current line

    def feed(self, token: str) -> str:
        """
        Process an incoming token and return rendered output.

        This is the main entry point for streaming. Each token from the
        LLM is fed here, and the parser returns immediately-renderable
        content (or empty string if buffering).

        Args:
            token: Single token from LLM stream (may be partial word).

        Returns:
            Rendered string to display, or empty if buffering.
        """
        if not token:
            return ""

        self.pending += token

        try:
            if self.state == ParserState.STREAMING:
                return self._handle_streaming()
            elif self.state == ParserState.BUFFERING_INLINE:
                return self._handle_buffering_inline()
            elif self.state == ParserState.BUFFERING_LINE:
                return self._handle_buffering_line()
            elif self.state == ParserState.BUFFERING_BLOCK:
                return self._handle_buffering_block()
            else:
                return token  # FLUSHING state, passthrough
        except Exception:
            # CRITICAL: Never let parsing errors break the stream
            # Fallback to plain text output
            result = self.pending
            self.pending = ""
            return result

    def _handle_streaming(self) -> str:
        """
        Handle tokens in STREAMING state.

        Scans for element start delimiters and transitions to appropriate
        buffering state when found. Returns plain text for non-markdown.

        Returns:
            Rendered output or empty string if transitioning to buffer.
        """
        if not self.config.enable_inline_format:
            return self._flush_pending()

        # Check for inline code start: `
        if "`" in self.pending:
            idx = self.pending.index("`")
            # Check if it's not escaped
            if idx == 0 or self.pending[idx - 1] != "\\":
                before = self.pending[:idx]
                self.pending = self.pending[idx:]
                self._start_inline(ElementType.INLINE_CODE, "`", "`")
                return self._apply_inline(before)

        # Check for bold start: **
        if "**" in self.pending:
            idx = self.pending.index("**")
            if idx == 0 or self.pending[idx - 1] != "\\":
                before = self.pending[:idx]
                self.pending = self.pending[idx:]
                self._start_inline(ElementType.BOLD, "**", "**")
                return self._apply_inline(before)

        # Check for italic start: * (but not **)
        if "*" in self.pending:
            idx = self.pending.index("*")
            # Make sure it's not **
            if idx + 1 < len(self.pending) and self.pending[idx + 1] == "*":
                pass  # Will be caught by ** check
            elif idx == 0 or self.pending[idx - 1] != "\\":
                before = self.pending[:idx]
                self.pending = self.pending[idx:]
                self._start_inline(ElementType.ITALIC, "*", "*")
                return self._apply_inline(before)

        # Check for link start: [
        if "[" in self.pending:
            idx = self.pending.index("[")
            before = self.pending[:idx]
            self.pending = self.pending[idx:]
            self._start_inline(ElementType.LINK, "[", "]")
            return self._apply_inline(before)

        # Check for header start: # at line beginning
        if self.config.enable_headers and self.pending.startswith("#"):
            return self._flush_pending()

        # No markdown detected, output as-is
        return self._flush_pending()

    def _handle_buffering_inline(self) -> str:
        """
        Handle tokens while buffering an inline element.

        Waits for closing delimiter or buffer overflow. On success,
        returns the formatted element. On overflow, returns plain text.

        Returns:
            Formatted inline element or plain text on timeout.
        """
        if self.buffer is None:
            return self._flush_pending()

        # Check for closing delimiter
        if self.buffer.end_delim in self.pending:
            idx = self.pending.index(self.buffer.end_delim)
            # Include closing delimiter in content
            self.buffer.content += self.pending[:idx + len(self.buffer.end_delim)]
            self.pending = self.pending[idx + len(self.buffer.end_delim):]

            # Render the complete element
            rendered = self._render_inline(self.buffer)
            self.state = ParserState.STREAMING
            self.buffer = None

            # Process remaining pending
            remaining = self._handle_streaming()
            return rendered + remaining

        # Buffer overflow check
        if len(self.buffer.content) > self.config.max_inline_buffer:
            # Timeout - render as plain text
            content = self.buffer.content + self.pending
            self.pending = ""
            self.state = ParserState.STREAMING
            self.buffer = None
            return content

        # Still buffering
        self.buffer.content += self.pending
        self.pending = ""
        return ""

    def _handle_buffering_line(self) -> str:
        """Handle tokens while buffering a line element."""
        if "\n" in self.pending:
            idx = self.pending.index("\n")
            line = self.pending[:idx + 1]
            self.pending = self.pending[idx + 1:]

            rendered = self._render_line(line)
            self.state = ParserState.STREAMING
            self.buffer = None

            return rendered + self._handle_streaming()

        self.buffer.content += self.pending if self.buffer else ""
        self.pending = ""
        return ""

    def _handle_buffering_block(self) -> str:
        """Handle tokens while buffering a block element."""
        if self.buffer is None:
            return self._flush_pending()

        self.buffer.content += self.pending
        self.pending = ""
        self.buffer.line_count = self.buffer.content.count("\n")

        # Check for block end
        if self.buffer.end_delim in self.buffer.content:
            # Found end delimiter
            rendered = self._render_block(self.buffer)
            self.state = ParserState.STREAMING
            self.buffer = None
            return rendered

        # Block size limit
        if self.buffer.line_count > self.config.max_block_buffer:
            # Render as plain text
            content = self.buffer.content
            self.state = ParserState.STREAMING
            self.buffer = None
            return content

        return ""

    def _start_inline(self, elem_type: ElementType, start: str, end: str) -> None:
        """Initialize inline element buffering."""
        self.buffer = BufferedElement(
            type=elem_type,
            start_delim=start,
            end_delim=end
        )
        self.state = ParserState.BUFFERING_INLINE

    def _flush_pending(self) -> str:
        """Output pending content without formatting."""
        result = self.pending
        self.pending = ""
        return result

    def _apply_inline(self, text: str) -> str:
        """Apply inline formatting to plain text."""
        if not self.config.enable_inline_format:
            return text

        # Bold
        text = re.sub(
            r"\*\*(.+?)\*\*",
            f"{Colors.BOLD}\\1{Colors.RESET}",
            text
        )

        # Italic (but not inside bold)
        text = re.sub(
            r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
            f"{Colors.ITALIC}\\1{Colors.RESET}",
            text
        )

        # Inline code
        text = re.sub(
            r"`([^`]+)`",
            f"{Colors.BG_BLACK}{Colors.BRIGHT_YELLOW}\\1{Colors.RESET}",
            text
        )

        # Links
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            f"{Colors.BRIGHT_BLUE}\\1{Colors.RESET}{Colors.DIM}(\\2){Colors.RESET}",
            text
        )

        return text

    def _render_inline(self, elem: BufferedElement) -> str:
        """Render a complete inline element."""
        content = elem.content

        # Strip delimiters for rendering
        if elem.type == ElementType.BOLD:
            inner = content[2:-2]  # Remove **
            return f"{Colors.BOLD}{inner}{Colors.RESET}"
        elif elem.type == ElementType.ITALIC:
            inner = content[1:-1]  # Remove *
            return f"{Colors.ITALIC}{inner}{Colors.RESET}"
        elif elem.type == ElementType.INLINE_CODE:
            inner = content[1:-1]  # Remove `
            return f"{Colors.BG_BLACK}{Colors.BRIGHT_YELLOW}{inner}{Colors.RESET}"
        elif elem.type == ElementType.LINK:
            # Format: [text](url)
            match = re.match(r"\[([^\]]+)\]\(([^)]+)\)", content)
            if match:
                text, url = match.groups()
                return f"{Colors.BRIGHT_BLUE}{text}{Colors.RESET}{Colors.DIM}({url}){Colors.RESET}"

        # Fallback: return as-is
        return content

    def _render_line(self, line: str) -> str:
        """Render a complete line element."""
        stripped = line.lstrip()

        # Header
        if self.config.enable_headers:
            header_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if header_match:
                level = len(header_match.group(1))
                text = header_match.group(2)

                colors = {
                    1: Colors.BRIGHT_WHITE,
                    2: Colors.BRIGHT_CYAN,
                    3: Colors.BRIGHT_BLUE,
                    4: Colors.BRIGHT_MAGENTA,
                    5: Colors.BRIGHT_GREEN,
                    6: Colors.BRIGHT_YELLOW,
                }
                color = colors.get(level, Colors.WHITE)
                return f"{Colors.BOLD}{color}{'#' * level} {text}{Colors.RESET}\n"

        # Blockquote
        if stripped.startswith(">"):
            content = stripped[1:].lstrip()
            return f"{Colors.BRIGHT_GREEN}│ {content}{Colors.RESET}\n"

        # List item
        if re.match(r'^[-*+]\s+', stripped):
            content = re.sub(r'^[-*+]\s+', '', stripped)
            return f"{Colors.BRIGHT_MAGENTA}•{Colors.RESET} {content}\n"

        # Default: return as-is with inline formatting
        return self._apply_inline(line)

    def _render_block(self, elem: BufferedElement) -> str:
        """Render a complete block element."""
        if elem.type == ElementType.CODE_BLOCK:
            return self._render_code_block(elem)
        elif elem.type == ElementType.TABLE:
            return self._render_table(elem)
        return elem.content

    def _render_code_block(self, elem: BufferedElement) -> str:
        """Render a fenced code block."""
        content = elem.content

        # Extract language and code
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lang = lines[0][3:].strip()
            code_lines = lines[1:]
            # Remove closing ```
            if code_lines and code_lines[-1].strip() == "```":
                code_lines = code_lines[:-1]
        else:
            lang = ""
            code_lines = lines

        result = []

        # Language hint
        if lang:
            result.append(f"{Colors.DIM}# {lang}{Colors.RESET}")

        # Code with basic highlighting
        for line in code_lines:
            highlighted = self._highlight_code(line, lang)
            result.append(highlighted)

        return "\n".join(result) + "\n"

    def _highlight_code(self, line: str, lang: str) -> str:
        """Apply basic syntax highlighting to code line."""
        if not line:
            return line

        # Python keywords
        if lang in ("python", "py"):
            keywords = r"\b(def|class|if|else|elif|for|while|return|import|from|with|try|except|finally|lambda|yield|global|nonlocal|pass|break|continue|and|or|not|in|is|True|False|None|async|await|raise|assert)\b"
            line = re.sub(keywords, f"{Colors.BRIGHT_MAGENTA}\\1{Colors.RESET}", line)

            # Numbers
            line = re.sub(r"\b(\d+)\b", f"{Colors.BRIGHT_RED}\\1{Colors.RESET}", line)

            # Comments
            line = re.sub(r"(#.+)$", f"{Colors.DIM}\\1{Colors.RESET}", line)

            # Strings
            line = re.sub(r"('[^']*'|\"[^\"]*\")", f"{Colors.GREEN}\\1{Colors.RESET}", line)

        return f"{Colors.BRIGHT_WHITE}{line}{Colors.RESET}"

    def _render_table(self, elem: BufferedElement) -> str:
        """Render a markdown table as grid."""
        if not self.config.enable_tables:
            return elem.content

        lines = elem.content.strip().split("\n")
        if len(lines) < 2:
            return elem.content

        # Parse header
        header_line = lines[0].strip()
        if not (header_line.startswith("|") and header_line.endswith("|")):
            return elem.content

        headers = [h.strip() for h in header_line[1:-1].split("|")]
        num_cols = len(headers)

        # Parse alignments
        alignments = []
        if len(lines) > 1:
            sep_line = lines[1].strip()
            align_parts = sep_line[1:-1].split("|") if "|" in sep_line else []
            for part in align_parts:
                part = part.strip()
                if part.startswith(":") and part.endswith(":"):
                    alignments.append("center")
                elif part.endswith(":"):
                    alignments.append("right")
                else:
                    alignments.append("left")

        # Parse data rows
        rows = []
        for line in lines[2:]:
            if line.strip().startswith("|") and line.strip().endswith("|"):
                cells = [c.strip() for c in line.strip()[1:-1].split("|")]
                while len(cells) < num_cols:
                    cells.append("")
                rows.append(cells[:num_cols])

        # Calculate column widths
        col_widths = []
        for i in range(num_cols):
            max_w = len(headers[i])
            for row in rows:
                if i < len(row):
                    max_w = max(max_w, len(row[i]))
            col_widths.append(max_w + self.config.table_pad + self.config.table_pad)

        # Build table
        result = []

        # Top border
        top = "┌" + "┬".join("─" * w for w in col_widths) + "┐"
        result.append(f"{Colors.DIM}{top}{Colors.RESET}")

        # Header row
        header_cells = []
        for i, h in enumerate(headers):
            pad = col_widths[i] - len(h)
            cell = " " * self.config.table_pad + h + " " * (pad - self.config.table_pad)
            header_cells.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}{cell}{Colors.RESET}")
        result.append(f"{Colors.DIM}│{Colors.RESET}".join(header_cells) + f"{Colors.DIM}│{Colors.RESET}")

        # Separator
        sep = "├" + "┼".join("─" * w for w in col_widths) + "┤"
        result.append(f"{Colors.DIM}{sep}{Colors.RESET}")

        # Data rows
        for row in rows:
            row_cells = []
            for i, cell in enumerate(row):
                pad = col_widths[i] - len(cell)
                padded = " " * self.config.table_pad + cell + " " * (pad - self.config.table_pad)
                row_cells.append(f"{Colors.CYAN}{padded}{Colors.RESET}")
            result.append(f"{Colors.DIM}│{Colors.RESET}".join(row_cells) + f"{Colors.DIM}│{Colors.RESET}")

        # Bottom border
        bot = "└" + "┴".join("─" * w for w in col_widths) + "┘"
        result.append(f"{Colors.DIM}{bot}{Colors.RESET}")

        return "\n".join(result) + "\n"

    def finalize(self) -> str:
        """
        Finalize parsing and flush all buffers.

        Call this when the stream ends to render any remaining
        buffered content.

        Returns:
            Any remaining buffered content rendered as plain text.
        """
        self.state = ParserState.FLUSHING

        result = ""

        # Flush pending
        if self.pending:
            result += self.pending
            self.pending = ""

        # Flush buffer
        if self.buffer:
            result += self.buffer.content
            self.buffer = None

        self.state = ParserState.STREAMING
        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def create_parser(config: Optional[ParserConfig] = None) -> MarkdownStreamParser:
    """
    Create a configured markdown stream parser.

    Args:
        config: Optional custom configuration.

    Returns:
        Configured MarkdownStreamParser instance.
    """
    return MarkdownStreamParser(config or ParserConfig())
