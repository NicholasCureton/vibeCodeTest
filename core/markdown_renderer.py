#!/usr/bin/env python3
"""
Beautiful Markdown Renderer v2 - Clean code blocks and grid tables.
Displays markdown files with syntax highlighting in the terminal.
"""

import re
import sys
from pathlib import Path

# =============================================================================
# COLOR CONFIGURATION
# =============================================================================
COLOR_RESET = "\033[0m"
COLOR_BOLD = "\033[1m"
COLOR_DIM = "\033[2m"
COLOR_ITALIC = "\033[3m"
COLOR_UNDERLINE = "\033[4m"

# Foreground colors
COLOR_BLACK = "\033[30m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_BLUE = "\033[34m"
COLOR_MAGENTA = "\033[35m"
COLOR_CYAN = "\033[36m"
COLOR_WHITE = "\033[37m"

COLOR_BRIGHT_BLACK = "\033[90m"
COLOR_BRIGHT_RED = "\033[91m"
COLOR_BRIGHT_GREEN = "\033[92m"
COLOR_BRIGHT_YELLOW = "\033[93m"
COLOR_BRIGHT_BLUE = "\033[94m"
COLOR_BRIGHT_MAGENTA = "\033[95m"
COLOR_BRIGHT_CYAN = "\033[96m"
COLOR_BRIGHT_WHITE = "\033[97m"

# Background colors
BG_BLACK = "\033[40m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_BLUE = "\033[44m"
BG_MAGENTA = "\033[45m"
BG_CYAN = "\033[46m"
BG_WHITE = "\033[47m"

# =============================================================================
# STYLE CONFIGURATION
# =============================================================================
HEADER_COLOR = COLOR_BRIGHT_CYAN
HEADER_BG = ""
HEADER_BOLD = COLOR_BOLD

H1_COLOR = COLOR_BRIGHT_WHITE
H2_COLOR = COLOR_BRIGHT_CYAN
H3_COLOR = COLOR_BRIGHT_BLUE
H4_COLOR = COLOR_BRIGHT_MAGENTA
H5_COLOR = COLOR_BRIGHT_GREEN
H6_COLOR = COLOR_BRIGHT_YELLOW

CODE_BLOCK_FG = COLOR_BRIGHT_WHITE
INLINE_CODE_FG = COLOR_BRIGHT_YELLOW
INLINE_CODE_BG = BG_BLACK

BOLD_COLOR = COLOR_BOLD
ITALIC_COLOR = COLOR_ITALIC
LINK_COLOR = COLOR_BRIGHT_BLUE
LINK_URL_COLOR = COLOR_DIM
QUOTE_COLOR = COLOR_BRIGHT_GREEN
LIST_BULLET_COLOR = COLOR_BRIGHT_MAGENTA
HORIZONTAL_RULE = COLOR_DIM + "─" * 60 + COLOR_RESET

# Table colors
TABLE_BORDER_COLOR = COLOR_DIM
TABLE_HEADER_COLOR = COLOR_BOLD + COLOR_BRIGHT_WHITE

# Table padding - single space on each side of content
TABLE_PAD = 1

# =============================================================================


class MarkdownRenderer:
    """Render markdown text with ANSI colors."""

    def __init__(self):
        self.in_code_block = False
        self.code_block_content = []
        self.code_block_lang = ""

    def render_header(self, line: str) -> str:
        """Render markdown headers with colors."""
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if not match:
            return line

        level = len(match.group(1))
        text = match.group(2)

        colors = {
            1: H1_COLOR,
            2: H2_COLOR,
            3: H3_COLOR,
            4: H4_COLOR,
            5: H5_COLOR,
            6: H6_COLOR,
        }

        color = colors.get(level, COLOR_WHITE)
        prefix = f"{COLOR_BOLD}{color}{'#' * level}"
        suffix = f"{COLOR_RESET}"

        return f"{prefix} {text}{suffix}"

    def render_inline_code(self, text: str) -> str:
        """Render inline code spans."""
        def replace_code(match):
            code = match.group(1)
            return f"{COLOR_BOLD}{INLINE_CODE_BG}{INLINE_CODE_FG}`{code}`{COLOR_RESET}"

        return re.sub(r'`([^`]+)`', replace_code, text)

    def render_bold(self, text: str) -> str:
        """Render bold text."""
        def replace_bold(match):
            content = match.group(1)
            return f"{COLOR_BOLD}{content}{COLOR_RESET}"

        # Match **text** or __text__
        text = re.sub(r'\*\*([^*]+)\*\*', replace_bold, text)
        text = re.sub(r'__([^_]+)__', replace_bold, text)
        return text

    def render_italic(self, text: str) -> str:
        """Render italic text."""
        def replace_italic(match):
            content = match.group(1)
            return f"{ITALIC_COLOR}{content}{COLOR_RESET}"

        # Match *text* or _text_ (but not ** or __)
        text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', replace_italic, text)
        text = re.sub(r'(?<!_)_([^_]+)_(?!_)', replace_italic, text)
        return text

    def render_links(self, text: str) -> str:
        """Render markdown links."""
        def replace_link(match):
            link_text = match.group(1)
            url = match.group(2)
            return f"{LINK_COLOR}{link_text}{COLOR_RESET}{COLOR_DIM}({url}){COLOR_RESET}"

        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', replace_link, text)

    def render_strikethrough(self, text: str) -> str:
        """Render strikethrough text."""
        def replace_strike(match):
            content = match.group(1)
            return f"{COLOR_DIM}~~{content}~~{COLOR_RESET}"

        return re.sub(r'~~([^~]+)~~', replace_strike, text)

    def render_inline(self, text: str) -> str:
        """Apply all inline formatting."""
        text = self.render_inline_code(text)
        text = self.render_bold(text)
        text = self.render_italic(text)
        text = self.render_links(text)
        text = self.render_strikethrough(text)
        return text

    def render_code_block(self, lines: list) -> list:
        """Render a fenced code block without frames or line numbers."""
        result = []
        lang = self.code_block_lang

        # Add blank line before code block
        result.append('')

        # Language hint (optional, subtle)
        if lang:
            result.append(f"{COLOR_DIM}# {lang}{COLOR_RESET}")

        # Code content without frames or line numbers
        for line in self.code_block_content:
            highlighted = self.syntax_highlight(line, lang)
            result.append(highlighted)

        # Add blank line after code block
        result.append('')

        return result

    def syntax_highlight(self, line: str, lang: str) -> str:
        """Apply basic syntax highlighting based on language."""
        if not line:
            return line

        original_line = line

        # Python highlighting
        if lang in ('python', 'py'):
            # Keywords
            line = re.sub(r'\b(def|class|if|else|elif|for|while|return|import|from|with|try|except|finally|lambda|yield|global|nonlocal|pass|break|continue|and|or|not|in|is|True|False|None|async|await|raise|assert)\b',
                         f"{COLOR_BRIGHT_MAGENTA}\\1{COLOR_RESET}", line)
            # Numbers
            line = re.sub(r'\b(\d+)\b', f"{COLOR_BRIGHT_RED}\\1{COLOR_RESET}", line)
            # Comments
            line = re.sub(r'(#.+)$', f"{COLOR_DIM}\\1{COLOR_RESET}", line)
            # Strings
            line = re.sub(r'(\'[^\']*\'|"[^"]*")', f"{COLOR_GREEN}\\1{COLOR_RESET}", line)
            # Function calls
            line = re.sub(r'\b([a-zA-Z_]\w*)\s*(?=\()', f"{COLOR_BRIGHT_CYAN}\\1{COLOR_RESET}", line)

        # JavaScript/TypeScript highlighting
        elif lang in ('javascript', 'js', 'typescript', 'ts'):
            # Keywords
            line = re.sub(r'\b(const|let|var|function|return|if|else|for|while|class|import|from|export|default|async|await|try|catch|finally|throw|new|this|typeof|instanceof|extends|implements|interface|type|enum|switch|case|break|continue|do|void|null|undefined|true|false)\b',
                         f"{COLOR_BRIGHT_MAGENTA}\\1{COLOR_RESET}", line)
            # Numbers
            line = re.sub(r'\b(\d+)\b', f"{COLOR_BRIGHT_RED}\\1{COLOR_RESET}", line)
            # Comments
            line = re.sub(r'(//.+)$', f"{COLOR_DIM}\\1{COLOR_RESET}", line)
            # Strings
            line = re.sub(r'(\'[^\']*\'|"[^"]*"|`[^`]*`)', f"{COLOR_GREEN}\\1{COLOR_RESET}", line)
            # Function calls
            line = re.sub(r'\b([a-zA-Z_]\w*)\s*(?=\()', f"{COLOR_BRIGHT_CYAN}\\1{COLOR_RESET}", line)

        # Bash/Shell highlighting
        elif lang in ('bash', 'sh', 'shell', 'zsh'):
            # Commands
            line = re.sub(r'^\s*(cd|ls|cat|echo|grep|find|rm|cp|mv|mkdir|chmod|chown|ps|kill|top|htop|ssh|scp|rsync|git|npm|pip|python|node|docker|kubectl|curl|wget)\b',
                         f"{COLOR_BRIGHT_CYAN}\\1{COLOR_RESET}", line)
            # Variables
            line = re.sub(r'(\$[a-zA-Z_]\w*|\$\{[^}]+\})', f"{COLOR_BRIGHT_YELLOW}\\1{COLOR_RESET}", line)
            # Comments
            line = re.sub(r'(#.+)$', f"{COLOR_DIM}\\1{COLOR_RESET}", line)
            # Strings
            line = re.sub(r'(\'[^\']*\'|"[^"]*")', f"{COLOR_GREEN}\\1{COLOR_RESET}", line)

        # JSON highlighting
        elif lang in ('json',):
            # Keys
            line = re.sub(r'"([^"]+)":', f"{COLOR_BRIGHT_CYAN}\\1{COLOR_RESET}:", line)
            # Strings
            line = re.sub(r': "([^"]*)"', f': {COLOR_GREEN}"\\1"{COLOR_RESET}', line)
            # Numbers
            line = re.sub(r': (\d+)', f': {COLOR_BRIGHT_RED}\\1{COLOR_RESET}', line)
            # Booleans
            line = re.sub(r'\b(true|false)\b', f"{COLOR_BRIGHT_MAGENTA}\\1{COLOR_RESET}", line)
            # Null
            line = re.sub(r'\b(null)\b', f"{COLOR_DIM}\\1{COLOR_RESET}", line)

        # YAML highlighting
        elif lang in ('yaml', 'yml'):
            # Keys
            line = re.sub(r'^(\s*)([a-zA-Z_][\w-]*):', f'\\1{COLOR_BRIGHT_CYAN}\\2{COLOR_RESET}:', line)
            # Comments
            line = re.sub(r'(#.+)$', f"{COLOR_DIM}\\1{COLOR_RESET}", line)
            # Strings
            line = re.sub(r': "([^"]*)"', f': {COLOR_GREEN}"\\1"{COLOR_RESET}', line)
            line = re.sub(r": '([^']*)'", f": {COLOR_GREEN}'\\1'{COLOR_RESET}", line)

        # Generic highlighting for other languages
        else:
            # Highlight numbers
            line = re.sub(r'\b(\d+)\b', f"{COLOR_BRIGHT_RED}\\1{COLOR_RESET}", line)
            # Highlight strings
            line = re.sub(r'(\'[^\']*\'|"[^"]*")', f"{COLOR_GREEN}\\1{COLOR_RESET}", line)
            # Highlight comments
            line = re.sub(r'(//.+|/.*/|#.+)$', f"{COLOR_DIM}\\1{COLOR_RESET}", line)

        return f"{CODE_BLOCK_FG}{line}{COLOR_RESET}"

    def render_blockquote(self, line: str) -> str:
        """Render blockquote lines."""
        content = line.lstrip('>').lstrip()
        content = self.render_inline(content)
        return f"{QUOTE_COLOR}│ {content}{COLOR_RESET}"

    def render_list_item(self, line: str, ordered: bool = False) -> str:
        """Render list items."""
        if ordered:
            match = re.match(r'^(\d+)\.\s+(.+)$', line)
            if match:
                num = match.group(1)
                content = match.group(2)
                content = self.render_inline(content)
                return f"{LIST_BULLET_COLOR}{num}.{COLOR_RESET} {content}"
        else:
            match = re.match(r'^[-*+]\s+(.+)$', line)
            if match:
                content = match.group(1)
                content = self.render_inline(content)
                return f"{LIST_BULLET_COLOR}•{COLOR_RESET} {content}"
        return line

    def parse_table(self, lines: list) -> list:
        """Parse markdown table and return as grid table."""
        if len(lines) < 2:
            return lines

        header_line = lines[0].strip()
        separator_line = lines[1].strip()

        if not re.match(r'^\|.*\|$', header_line):
            return lines
        if not re.match(r'^[\|\-:\s]+$', separator_line):
            return lines

        # Parse header
        headers = [h.strip() for h in header_line.split('|')[1:-1]]
        num_cols = len(headers)

        # Parse alignments (not used - all left aligned now)
        alignments = []
        align_parts = separator_line.split('|')[1:-1]
        for part in align_parts:
            part = part.strip()
            if part.startswith(':') and part.endswith(':'):
                alignments.append('center')
            elif part.endswith(':'):
                alignments.append('right')
            else:
                alignments.append('left')

        # Parse data rows
        data_rows = []
        remaining_lines = []
        for line in lines[2:]:
            if line.strip().startswith('|') and re.match(r'^\|.*\|$', line.strip()):
                cells = [c.strip() for c in line.split('|')[1:-1]]
                while len(cells) < num_cols:
                    cells.append('')
                data_rows.append(cells[:num_cols])
            else:
                remaining_lines.append(line)
                break

        # Calculate column widths: max_content + TABLE_PAD + TABLE_PAD
        col_widths = []
        for i in range(num_cols):
            max_width = len(headers[i])
            for row in data_rows:
                if i < len(row):
                    clean_cell = re.sub(r'\033\[[0-9;]*m', '', row[i])
                    max_width = max(max_width, len(clean_cell))
            col_widths.append(max_width + TABLE_PAD + TABLE_PAD)

        # Build borders
        top_border = '┌' + '┬'.join('─' * w for w in col_widths) + '┐'
        mid_border = '├' + '┼'.join('─' * w for w in col_widths) + '┤'
        bot_border = '└' + '┴'.join('─' * w for w in col_widths) + '┘'

        result = []
        result.append(f"{TABLE_BORDER_COLOR}{top_border}{COLOR_RESET}")

        # Header row: │ <pad>content<pad> │ <pad>content<pad> │
        header_cells = []
        for i, h in enumerate(headers):
            cell = ' ' * TABLE_PAD + h + ' ' * (col_widths[i] - len(h) - TABLE_PAD)
            header_cells.append(f"{TABLE_HEADER_COLOR}{cell}{COLOR_RESET}")
        result.append(f"{COLOR_DIM}│{COLOR_RESET}" + f"{COLOR_DIM}│{COLOR_RESET}".join(header_cells) + f"{COLOR_DIM}│{COLOR_RESET}")

        result.append(f"{TABLE_BORDER_COLOR}{mid_border}{COLOR_RESET}")

        # Data rows
        for row in data_rows:
            row_cells = []
            for i, cell in enumerate(row):
                clean_len = len(re.sub(r'\033\[[0-9;]*m', '', cell))
                padded = ' ' * TABLE_PAD + cell + ' ' * (col_widths[i] - clean_len - TABLE_PAD)
                row_cells.append(padded)
            result.append(f"{COLOR_DIM}│{COLOR_RESET}" + f"{COLOR_DIM}│{COLOR_RESET}".join(row_cells) + f"{COLOR_DIM}│{COLOR_RESET}")

        result.append(f"{TABLE_BORDER_COLOR}{bot_border}{COLOR_RESET}")

        return result + remaining_lines

    def render(self, markdown_text: str) -> str:
        """Render the entire markdown text."""
        lines = markdown_text.split('\n')
        result = []
        self.in_code_block = False
        self.code_block_content = []
        self.code_block_lang = ""

        i = 0
        while i < len(lines):
            line = lines[i]

            # Handle fenced code blocks
            if line.strip().startswith('```'):
                if not self.in_code_block:
                    # Start code block
                    self.in_code_block = True
                    self.code_block_lang = line.strip()[3:].strip()
                    self.code_block_content = []
                else:
                    # End code block
                    self.in_code_block = False
                    result.extend(self.render_code_block(lines))
                    self.code_block_content = []
                    self.code_block_lang = ""
                i += 1
                continue

            if self.in_code_block:
                self.code_block_content.append(line)
                i += 1
                continue

            # Check for table
            if line.strip().startswith('|') and i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.strip().startswith('|') or re.match(r'^[\|\-:\s]+$', next_line.strip()):
                    table_lines = self.parse_table(lines[i:])
                    # Check if table was actually parsed
                    if table_lines != lines[i:]:
                        result.extend(table_lines)
                        # Skip processed table lines
                        processed = 2 + len([l for l in lines[i+2:] if l.strip().startswith('|') and re.match(r'^\|.*\|$', l.strip())])
                        i += processed
                        continue

            # Horizontal rule
            if re.match(r'^(-{3,}|\*{3,}|_{3,})$', line.strip()):
                result.append(HORIZONTAL_RULE)
                i += 1
                continue

            # Headers
            if line.startswith('#'):
                result.append(self.render_header(line))
                i += 1
                continue

            # Blockquotes
            if line.startswith('>'):
                result.append(self.render_blockquote(line))
                i += 1
                continue

            # Ordered lists
            if re.match(r'^\d+\.\s+', line):
                result.append(self.render_list_item(line, ordered=True))
                i += 1
                continue

            # Unordered lists
            if re.match(r'^[-*+]\s+', line):
                result.append(self.render_list_item(line, ordered=False))
                i += 1
                continue

            # Empty lines
            if not line.strip():
                result.append('')
                i += 1
                continue

            # Regular paragraphs with inline formatting
            result.append(self.render_inline(line))
            i += 1

        # Handle unclosed code block
        if self.in_code_block and self.code_block_content:
            result.extend(self.render_code_block(lines))

        return '\n'.join(result)


def render_markdown_file(filepath: str) -> None:
    """Render a markdown file with colors."""
    path = Path(filepath)

    if not path.exists():
        print(f"{COLOR_BRIGHT_RED}Error: File '{filepath}' not found.{COLOR_RESET}")
        sys.exit(1)

    content = path.read_text(encoding='utf-8')
    renderer = MarkdownRenderer()
    rendered = renderer.render(content)
    print(rendered)


def main():
    if len(sys.argv) < 2:
        # Demo mode with sample markdown
        sample = """# Beautiful Markdown Renderer v2

## Clean Code Blocks

Code blocks now have **no frames, no line numbers**, just clean syntax highlighting:

```python
def greet(name: str) -> str:
    # Greet someone with style
    return f"Hello, {name}!"

# Example usage
message = greet("World")
print(message)
```

## Grid Tables

Tables are now rendered as beautiful grid tables:

| Feature | Status | Priority |
|:--------|:------:|---------:|
| Headers | ✅ | High |
| Code blocks | ✅ | High |
| Tables | ✅ | Medium |
| Lists | ✅ | Low |

### Inline Code

Don't forget about `inline code` and **bold** or *italic* text!

---

Enjoy the clean rendering! 🎉
"""
        renderer = MarkdownRenderer()
        print(renderer.render(sample))
    else:
        filepath = sys.argv[1]
        render_markdown_file(filepath)


if __name__ == "__main__":
    main()
