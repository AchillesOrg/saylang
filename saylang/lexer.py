"""Indentation-aware lexer for SayLang."""

from __future__ import annotations

from saylang.errors import SayLexError
from saylang.tokens import Token, TokenType


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _read_string(line: str, pos: int, quote: str, line_no: int) -> tuple[str, int]:
    """Read a quoted string literal starting at `pos` (opening quote)."""
    start_col = pos + 1
    pos += 1
    chars: list[str] = []
    escapes = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}
    while pos < len(line):
        ch = line[pos]
        if ch == "\\":
            pos += 1
            if pos >= len(line):
                raise SayLexError(
                    "Unterminated escape sequence in text literal.",
                    line=line_no,
                    column=start_col,
                    source_line=line,
                )
            esc = line[pos]
            chars.append(escapes.get(esc, esc))
            pos += 1
            continue
        if ch == quote:
            return "".join(chars), pos + 1
        chars.append(ch)
        pos += 1
    raise SayLexError(
        "Unterminated text literal.",
        line=line_no,
        column=start_col,
        source_line=line,
    )


def _starts_with_note_comment(stripped: str) -> bool:
    """Return True if a line begins with a `note` prose comment."""
    lower = stripped.lower()
    if lower == "note":
        return True
    if lower.startswith("note") and len(lower) > 4:
        return lower[4] in (" ", "\t", ":")
    return False


def tokenize(source: str) -> list[Token]:
    """Convert SayLang source text into a stream of indentation-aware tokens."""
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    tokens: list[Token] = []
    indent_stack: list[int] = [0]

    for idx, raw_line in enumerate(lines):
        line_no = idx + 1
        line = raw_line.replace("\t", "    ")
        stripped = line.lstrip(" ")
        if not stripped or stripped.startswith("#") or _starts_with_note_comment(stripped):
            continue

        indent = len(line) - len(stripped)
        if indent > indent_stack[-1]:
            indent_stack.append(indent)
            tokens.append(Token(TokenType.INDENT, indent, line_no, 1))
        elif indent < indent_stack[-1]:
            while indent_stack and indent < indent_stack[-1]:
                indent_stack.pop()
                tokens.append(Token(TokenType.DEDENT, indent, line_no, 1))
            if not indent_stack or indent != indent_stack[-1]:
                raise SayLexError(
                    "Indentation does not match any outer block.",
                    line=line_no,
                    column=1,
                    source_line=line,
                )

        pos = indent
        length = len(line)
        prev_token: Token | None = None

        while pos < length:
            ch = line[pos]
            if ch == " ":
                pos += 1
                continue

            if ch == "#":
                break

            col = pos + 1

            if ch == '"':
                text, end_pos = _read_string(line, pos, '"', line_no)
                raw_inner = line[pos + 1 : end_pos - 1]
                pos = end_pos
                tok = Token(TokenType.STRING, text, line_no, col, raw=raw_inner)
                tokens.append(tok)
                prev_token = tok
                continue

            if ch == "'":
                is_possessive = (
                    prev_token is not None
                    and prev_token.type in (TokenType.WORD, TokenType.RPAREN)
                    and pos > 0
                    and line[pos - 1] != " "
                    and pos + 1 < length
                    and line[pos + 1].lower() == "s"
                    and (pos + 2 == length or not _is_ident_part(line[pos + 2]))
                )
                if is_possessive:
                    tok = Token(TokenType.POSSESSIVE, "'s", line_no, col)
                    tokens.append(tok)
                    prev_token = tok
                    pos += 2
                    continue
                text, pos = _read_string(line, pos, "'", line_no)
                tok = Token(TokenType.STRING, text, line_no, col)
                tokens.append(tok)
                prev_token = tok
                continue

            if ch == "-" and pos + 2 < length and line[pos + 1] == "-" and line[pos + 2].isalnum():
                start = pos
                pos += 2
                while pos < length and (line[pos].isalnum() or line[pos] in ("_", "-")):
                    pos += 1
                tok = Token(TokenType.FLAG, line[start:pos], line_no, col)
                tokens.append(tok)
                prev_token = tok
                continue

            if ch.isdigit():
                start = pos
                has_dot = False
                while pos < length and line[pos].isdigit():
                    pos += 1
                if (
                    pos < length
                    and line[pos] == "."
                    and pos + 1 < length
                    and line[pos + 1].isdigit()
                ):
                    has_dot = True
                    pos += 1
                    while pos < length and line[pos].isdigit():
                        pos += 1
                num_str = line[start:pos]
                val: int | float = float(num_str) if has_dot else int(num_str)
                tok = Token(TokenType.NUMBER, val, line_no, col)
                tokens.append(tok)
                prev_token = tok
                continue

            if ch == ".":
                # Allow optional sentence-ending period before whitespace, comment, or EOL.
                if pos + 1 == length or line[pos + 1] in (" ", "#"):
                    pos += 1
                    continue
                raise SayLexError(
                    "Unexpected '.' outside a decimal number or sentence ending.",
                    line=line_no,
                    column=col,
                    source_line=line,
                )

            if _is_ident_start(ch):
                start = pos
                while pos < length and _is_ident_part(line[pos]):
                    pos += 1
                word = line[start:pos]
                tok = Token(TokenType.WORD, word, line_no, col)
                tokens.append(tok)
                prev_token = tok
                continue

            single_char_tokens = {
                "|": TokenType.PIPE,
                ",": TokenType.COMMA,
                ":": TokenType.COLON,
                "(": TokenType.LPAREN,
                ")": TokenType.RPAREN,
                "+": TokenType.PLUS,
                "-": TokenType.MINUS,
                "*": TokenType.STAR,
                "/": TokenType.SLASH,
            }
            if ch in single_char_tokens:
                tok = Token(single_char_tokens[ch], ch, line_no, col)
                tokens.append(tok)
                prev_token = tok
                pos += 1
                continue

            raise SayLexError(
                f"Unexpected character '{ch}'.",
                line=line_no,
                column=col,
                source_line=line,
            )

        tokens.append(Token(TokenType.NEWLINE, "\n", line_no, length + 1))

    eof_line = len(lines) if lines else 1
    while len(indent_stack) > 1:
        indent_stack.pop()
        tokens.append(Token(TokenType.DEDENT, 0, eof_line, 1))

    tokens.append(Token(TokenType.EOF, "", eof_line, 1))
    return tokens
