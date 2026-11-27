"""Human-friendly error types and formatting for SayLang."""

from __future__ import annotations


class SayError(Exception):
    """Base error for lexing, parsing, runtime, and translation failures."""

    kind = "Error"

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        source_line: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line

    def format_pretty(self, filename: str = "<input>") -> str:
        """Render a clean diagnostic with line context and caret."""
        if self.line > 0:
            header = f"{self.kind} in {filename} on line {self.line}"
            if self.column > 0:
                header += f", column {self.column}"
            header += f": {self.message}"
        else:
            header = f"{self.kind}: {self.message}"

        if self.source_line:
            line_num = str(self.line) if self.line > 0 else "?"
            gutter = " " * len(line_num)
            caret_offset = max(self.column - 1, 0)
            caret_line = f"{gutter} | {' ' * caret_offset}^"
            return f"{header}\n{line_num} | {self.source_line}\n{caret_line}"
        return header


class SayLexError(SayError):
    """Raised when the lexer encounters invalid characters or indentation."""

    kind = "Syntax error"


class SayParseError(SayError):
    """Raised when the parser encounters unexpected or incomplete phrasing."""

    kind = "Syntax error"


class SayRuntimeError(SayError):
    """Raised when a SayLang program fails during execution."""

    kind = "Runtime error"


class SayTranslateError(SayError):
    """Raised when loose English cannot be translated into SayLang."""

    kind = "Translation error"
