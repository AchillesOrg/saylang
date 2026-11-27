"""Token definitions for the SayLang lexer and parser."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokenType(Enum):
    WORD = auto()
    NUMBER = auto()
    STRING = auto()
    POSSESSIVE = auto()
    FLAG = auto()
    PIPE = auto()
    COMMA = auto()
    COLON = auto()
    LPAREN = auto()
    RPAREN = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    NEWLINE = auto()
    INDENT = auto()
    DEDENT = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    """A single lexical token with 1-based source location."""

    type: TokenType
    value: object
    line: int
    column: int
    raw: str | None = None

    @property
    def lower(self) -> str:
        """Lowercase string form for case-insensitive keyword checks."""
        if isinstance(self.value, str):
            return self.value.lower()
        return ""
