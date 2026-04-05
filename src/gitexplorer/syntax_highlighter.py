"""Pygments-based syntax highlighter with diff line background coloring."""
from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from pygments import lex
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_style_by_name

# Dark-theme diff background colors
DIFF_BG: dict[str, QColor] = {
    "added":   QColor("#1c3320"),
    "removed": QColor("#3b1c1c"),
    "context": QColor("#272822"),
}

_STYLE = get_style_by_name("monokai")


class DiffHighlighter(QSyntaxHighlighter):
    """Applies Pygments syntax colors + per-line diff background."""

    def __init__(self, document, filename: str = "") -> None:
        super().__init__(document)
        self._line_types: dict[int, str] = {}
        # {line_idx: [(col_start, length, color_hex_or_None, bold)]}
        self._spans: dict[int, list[tuple[int, int, str | None, bool]]] = {}

        try:
            self._lexer = get_lexer_for_filename(filename)
        except Exception:
            self._lexer = TextLexer()

    def update_content(self, text: str, line_types: dict[int, str] | None = None) -> None:
        """Pre-compute token spans from *text*, then trigger a rehighlight."""
        self._line_types = line_types or {}
        self._spans = {}

        line_idx = col = 0

        try:
            tokens = list(lex(text, self._lexer))
        except Exception:
            tokens = []

        for ttype, value in tokens:
            # Walk up the token hierarchy until style_for_token succeeds;
            # newer Pygments versions can raise KeyError for unknown subtypes.
            t = ttype
            s: dict = {}
            while t is not None:
                try:
                    s = _STYLE.style_for_token(t)
                    break
                except KeyError:
                    t = t.parent
            color: str | None = s.get("color")  # hex without '#', or None
            bold: bool = bool(s.get("bold", False))

            parts = value.split("\n")
            for p_idx, part in enumerate(parts):
                if part and (color or bold):
                    self._spans.setdefault(line_idx, []).append(
                        (col, len(part), color, bold)
                    )
                if p_idx < len(parts) - 1:
                    line_idx += 1
                    col = 0
                else:
                    col += len(part)

        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # called by Qt
        block_num = self.currentBlock().blockNumber()
        diff_type = self._line_types.get(block_num, "context")
        bg = DIFF_BG.get(diff_type, DIFF_BG["context"])

        # Background for the whole line
        base = QTextCharFormat()
        base.setBackground(bg)
        self.setFormat(0, len(text), base)

        # Syntax token colors (preserve diff background)
        for col_start, length, color_hex, bold in self._spans.get(block_num, []):
            end = min(col_start + length, len(text))
            if col_start >= end:
                continue
            fmt = QTextCharFormat()
            fmt.setBackground(bg)
            if color_hex:
                fmt.setForeground(QColor(f"#{color_hex}"))
            if bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            self.setFormat(col_start, end - col_start, fmt)
