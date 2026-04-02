#!/usr/bin/env python3
"""
FILE: core/markdown_stream.py
ROLE: Line-Buffered Markdown Parser for Streaming Output

DESCRIPTION:
    Simple line-buffered markdown parser for streaming LLM output.
    Buffers complete lines, then renders markdown elements that can be
    safely parsed at line boundaries.

    Supported:
    - Headers: # ## ### etc (rendered when line completes)
    - Code blocks: ```lang ... ``` (buffered until block completes)
    - Tables: | col | col | (buffered until table completes)
    - Inline: **bold**, *italic*, `code`, [link]() (rendered immediately)

    Falls back to plain text if parsing fails.

USAGE:
    parser = MarkdownStreamParser()
    for token in llm_stream:
        rendered = parser.feed(token)
        print(rendered, end="")
    parser.finalize()  # Flush any remaining buffers
"""
from __future__ import annotations

import re
from typing import Optional, List


# =============================================================================
# COLOR CONFIGURATION
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"

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


# =============================================================================
# CONFIGURATION
# =============================================================================

class ParserConfig:
    """Parser configuration."""
    def __init__(
        self,
        enable_tables: bool = True,
        enable_code_blocks: bool = True,
        enable_headers: bool = True,
        enable_inline: bool = True,
        table_pad: int = 1,
    ):
        self.enable_tables = enable_tables
        self.enable_code_blocks = enable_code_blocks
        self.enable_headers = enable_headers
        self.enable_inline = enable_inline
        self.table_pad = table_pad


# =============================================================================
# STREAMING MARKDOWN PARSER
# =============================================================================

class MarkdownStreamParser:
    """
    Line-buffered markdown parser for streaming output.

    Strategy:
    1. Apply inline formatting immediately (**, *, `, [])
    2. Buffer lines for block elements (# headers, > quotes)
    3. Buffer complete blocks for tables and code fences

    This ensures we never block streaming for more than one line,
    while still rendering most markdown elements correctly.
    """

    def __init__(self, config: Optional[ParserConfig] = None):
        """Initialize parser with optional configuration."""
        self.config = config or ParserConfig()
        self.line_buffer = ""
        self.code_block_buffer: List[str] = []
        self.table_buffer: List[str] = []
        self.in_code_block = False
        self.code_block_lang = ""
        self.possible_table = False

    def feed(self, token: str) -> str:
        """
        Process a token and return rendered output.

        Args:
            token: Text token from LLM stream

        Returns:
            Rendered text to display
        """
        if not token:
            return ""

        result = ""
        self.line_buffer += token

        # Process complete lines
        while "\n" in self.line_buffer:
            line, self.line_buffer = self.line_buffer.split("\n", 1)
            line += "\n"
            result += self._process_line(line)

        return result

    def _process_line(self, line: str) -> str:
        """Process a complete line of markdown."""
        stripped = line.rstrip("\n")

        # Check for code block start/end
        if self.config.enable_code_blocks:
            if stripped.startswith("```"):
                if not self.in_code_block:
                    self.in_code_block = True
                    self.code_block_lang = stripped[3:].strip()
                    self.code_block_buffer = []
                    return ""  # Buffer until block completes
                else:
                    # End of code block
                    self.in_code_block = False
                    rendered = self._render_code_block()
                    self.code_block_buffer = []
                    self.code_block_lang = ""
                    return rendered

            if self.in_code_block:
                self.code_block_buffer.append(stripped)
                return ""  # Buffer code lines

        # Check for table start
        if self.config.enable_tables and not self.in_code_block:
            if stripped.startswith("|") and stripped.endswith("|"):
                if not self.possible_table:
                    self.possible_table = True
                    self.table_buffer = [stripped]
                    return ""  # Buffer first table line
                else:
                    # Check if this is separator line
                    if len(self.table_buffer) == 1:
                        if re.match(r'^\|[\s\-:|]+\|$', stripped):
                            self.table_buffer.append(stripped)
                            return ""  # Buffer separator
                        else:
                            # Not a table, flush buffered line
                            result = self._render_line(self.table_buffer[0] + "\n")
                            self.table_buffer = [stripped]
                            self.possible_table = True
                            return result
                    else:
                        # Data row
                        self.table_buffer.append(stripped)
                        return ""  # Keep buffering table
            else:
                # Non-table line - flush table buffer
                if self.possible_table and self.table_buffer:
                    result = self._render_table()
                    self.table_buffer = []
                    self.possible_table = False
                    return result + self._render_line(line)

        # Regular line
        return self._render_line(line)

    def _render_line(self, line: str) -> str:
        """Render a single line with inline formatting."""
        if not self.config.enable_inline:
            return line

        # Check for header - remove # symbols, just show colored text
        if self.config.enable_headers:
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                level = len(header_match.group(1))
                text = header_match.group(2).rstrip()

                colors = {
                    1: Colors.BRIGHT_WHITE,
                    2: Colors.BRIGHT_CYAN,
                    3: Colors.BRIGHT_BLUE,
                    4: Colors.BRIGHT_MAGENTA,
                    5: Colors.BRIGHT_GREEN,
                    6: Colors.BRIGHT_YELLOW,
                }
                color = colors.get(level, Colors.WHITE)
                # No # symbols - just colored bold text
                return f"{Colors.BOLD}{color}{self._apply_inline(text)}{Colors.RESET}\n"

        # Check for blockquote
        if line.lstrip().startswith(">"):
            content = line.lstrip()
            if content.startswith(">"):
                content = content[1:].lstrip()
            return f"{Colors.BRIGHT_GREEN}│ {self._apply_inline(content)}{Colors.RESET}\n"

        # Check for list item
        list_match = re.match(r'^(\s*)[-*+]\s+(.+)$', line)
        if list_match:
            indent = list_match.group(1)
            content = list_match.group(2)
            return f"{indent}{Colors.BRIGHT_MAGENTA}•{Colors.RESET} {self._apply_inline(content)}\n"

        # Default: apply inline formatting only
        return self._apply_inline(line)

    def _apply_inline(self, text: str) -> str:
        """Apply inline markdown formatting."""
        if not text:
            return text

        # Inline code first (to avoid processing markdown inside code)
        text = re.sub(
            r'`([^`]+)`',
            f'{Colors.BG_BLACK}{Colors.BRIGHT_YELLOW}\\1{Colors.RESET}',
            text
        )

        # Bold
        text = re.sub(
            r'\*\*(.+?)\*\*',
            f'{Colors.BOLD}\\1{Colors.RESET}',
            text
        )

        # Italic (single *)
        text = re.sub(
            r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)',
            f'{Colors.ITALIC}\\1{Colors.RESET}',
            text
        )

        # Links
        text = re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            f'{Colors.BRIGHT_BLUE}\\1{Colors.RESET}{Colors.DIM}(\\2){Colors.RESET}',
            text
        )

        # Strikethrough
        text = re.sub(
            r'~~(.+?)~~',
            f'{Colors.DIM}~~\\1~~{Colors.RESET}',
            text
        )

        return text

    def _render_code_block(self) -> str:
        """Render buffered code block."""
        if not self.code_block_buffer:
            return ""

        result = []
        lang = self.code_block_lang

        # Language hint
        if lang:
            result.append(f"{Colors.DIM}# {lang}{Colors.RESET}")

        # Code with basic highlighting
        for line in self.code_block_buffer:
            highlighted = self._highlight_code(line, lang)
            result.append(f"{Colors.BRIGHT_WHITE}{highlighted}{Colors.RESET}")

        return "\n".join(result) + "\n"

    def _highlight_code(self, line: str, lang: str) -> str:
        """Apply basic syntax highlighting."""
        if not line:
            return line

        # Python
        if lang in ("python", "py"):
            keywords = r'\b(def|class|if|else|elif|for|while|return|import|from|with|try|except|finally|lambda|yield|global|nonlocal|pass|break|continue|and|or|not|in|is|True|False|None|async|await|raise|assert)\b'
            line = re.sub(keywords, f'{Colors.BRIGHT_MAGENTA}\\1{Colors.RESET}', line)
            line = re.sub(r'\b(\d+)\b', f'{Colors.BRIGHT_RED}\\1{Colors.RESET}', line)
            line = re.sub(r'(#.+)$', f'{Colors.DIM}\\1{Colors.RESET}', line)
            line = re.sub(r"('[^']*'|\"[^\"]*\")", f'{Colors.GREEN}\\1{Colors.RESET}', line)

        # JavaScript
        elif lang in ("javascript", "js"):
            keywords = r'\b(const|let|var|function|return|if|else|for|while|class|import|from|export|default|async|await|try|catch|finally|throw|new|this|typeof|instanceof)\b'
            line = re.sub(keywords, f'{Colors.BRIGHT_MAGENTA}\\1{Colors.RESET}', line)
            line = re.sub(r'\b(\d+)\b', f'{Colors.BRIGHT_RED}\\1{Colors.RESET}', line)
            line = re.sub(r'(//.+)$', f'{Colors.DIM}\\1{Colors.RESET}', line)
            line = re.sub(r"('[^']*'|\"[^\"]*\"|`[^`]*`)", f'{Colors.GREEN}\\1{Colors.RESET}', line)

        return line

    def _render_table(self) -> str:
        """Render buffered table as grid."""
        if len(self.table_buffer) < 2:
            # Not a valid table, return as plain text
            return "\n".join(self.table_buffer) + "\n" if self.table_buffer else ""

        lines = self.table_buffer
        header_line = lines[0]
        sep_line = lines[1]
        data_lines = lines[2:]

        # Parse headers
        headers = [h.strip() for h in header_line[1:-1].split("|")]
        num_cols = len(headers)

        # Parse alignments
        alignments = []
        sep_parts = sep_line[1:-1].split("|")
        for part in sep_parts:
            part = part.strip()
            if part.startswith(":") and part.endswith(":"):
                alignments.append("center")
            elif part.endswith(":"):
                alignments.append("right")
            else:
                alignments.append("left")

        # Parse data rows
        rows = []
        for line in data_lines:
            cells = [c.strip() for c in line[1:-1].split("|")]
            while len(cells) < num_cols:
                cells.append("")
            rows.append(cells[:num_cols])

        # Calculate column widths: max_content + 2*pad
        col_widths = []
        for i in range(num_cols):
            max_w = len(headers[i])
            for row in rows:
                if i < len(row):
                    max_w = max(max_w, len(row[i]))
            col_widths.append(max_w + 2 * self.config.table_pad)

        # Build table
        result = []

        # Top border
        top = "┌" + "┬".join("─" * w for w in col_widths) + "┐"
        result.append(f"{Colors.DIM}{top}{Colors.RESET}")

        # Header row: │ <pad>content<pad_to_fill> │
        header_cells = []
        for i, h in enumerate(headers):
            # Left pad + content + right pad to fill
            cell = " " * self.config.table_pad + h + " " * (col_widths[i] - len(h) - self.config.table_pad)
            header_cells.append(f"{Colors.BOLD}{Colors.BRIGHT_WHITE}{cell}{Colors.RESET}")
        result.append(f"{Colors.DIM}│{Colors.RESET}" + f"{Colors.DIM}│{Colors.RESET}".join(header_cells) + f"{Colors.DIM}│{Colors.RESET}")

        # Separator
        sep = "├" + "┼".join("─" * w for w in col_widths) + "┤"
        result.append(f"{Colors.DIM}{sep}{Colors.RESET}")

        # Data rows
        for row in rows:
            row_cells = []
            for i, cell in enumerate(row):
                # Same padding formula for data cells
                padded = " " * self.config.table_pad + cell + " " * (col_widths[i] - len(cell) - self.config.table_pad)
                row_cells.append(f"{Colors.CYAN}{padded}{Colors.RESET}")
            result.append(f"{Colors.DIM}│{Colors.RESET}" + f"{Colors.DIM}│{Colors.RESET}".join(row_cells) + f"{Colors.DIM}│{Colors.RESET}")

        # Bottom border
        bot = "└" + "┴".join("─" * w for w in col_widths) + "┘"
        result.append(f"{Colors.DIM}{bot}{Colors.RESET}")

        return "\n".join(result) + "\n"

    def finalize(self) -> str:
        """
        Finalize parsing and flush all buffers.

        Returns:
            Any remaining buffered content
        """
        result = ""

        # Flush line buffer
        if self.line_buffer:
            result += self._process_line(self.line_buffer)
            self.line_buffer = ""

        # Flush code block
        if self.in_code_block:
            result += self._render_code_block()
            self.in_code_block = False
            self.code_block_buffer = []

        # Flush table
        if self.possible_table and self.table_buffer:
            result += self._render_table()
            self.table_buffer = []
            self.possible_table = False

        return result


def create_parser(config: Optional[ParserConfig] = None) -> MarkdownStreamParser:
    """Create a configured markdown stream parser."""
    return MarkdownStreamParser(config or ParserConfig())
