"""Pygments-based syntax highlighter with diff line background coloring."""
from __future__ import annotations

from PyQt6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtWidgets import QApplication
from pygments import lex
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_style_by_name

_DIFF_BG_DARK: dict[str, QColor] = {
    "added":   QColor("#24522d"),
    "removed": QColor("#5a2525"),
    "context": QColor("#272822"),
}

_DIFF_BG_LIGHT: dict[str, QColor] = {
    "added":   QColor("#cfe8d2"),
    "removed": QColor("#f0c9c9"),
    "context": QColor("#f7f7f7"),
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

    def _diff_bg(self, diff_type: str) -> QColor:
        app = QApplication.instance()
        base = app.palette().base().color() if app is not None else QColor("#272822")
        colors = _DIFF_BG_DARK if base.lightness() < 128 else _DIFF_BG_LIGHT
        return colors.get(diff_type, colors["context"])

    def highlightBlock(self, text: str) -> None:  # called by Qt
        block_num = self.currentBlock().blockNumber()
        diff_type = self._line_types.get(block_num, "context")
        bg = self._diff_bg(diff_type)

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
