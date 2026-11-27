"""nana: built-in terminal text editor with live SayLang syntax highlighting."""

from __future__ import annotations

import io
import os
import re
import shutil
import sys
from pathlib import Path

from saylang import __version__, runtime
from saylang.errors import SayError
from saylang.interpreter import run_source
from saylang.parser import parse_source

_RESET = "\x1b[0m"
_GRAY = "\x1b[90m"
_STRING_CLR = "\x1b[92m"
_NUMBER_CLR = "\x1b[93m"
_FLAG_CLR = "\x1b[96m"
_PIPE_CLR = "\x1b[1;95m"
_KW_CLR = "\x1b[1;94m"
_OP_CLR = "\x1b[35m"
_LIB_CLR = "\x1b[36m"

_KEYWORDS = {
    "import",
    "use",
    "flags",
    "flag",
    "has",
    "say",
    "print",
    "set",
    "let",
    "increase",
    "decrease",
    "if",
    "then",
    "otherwise",
    "else",
    "repeat",
    "times",
    "for",
    "each",
    "from",
    "to",
    "in",
    "by",
    "while",
    "every",
    "wait",
    "sleep",
    "clear",
    "screen",
    "stop",
    "skip",
    "with",
    "return",
    "give",
    "back",
    "try",
    "it",
    "fails",
    "fail",
    "call",
    "run",
    "add",
    "append",
    "remove",
    "write",
    "read",
    "file",
    "ask",
    "below",
    "centered",
    "centred",
    "colour",
    "color",
    "on",
    "background",
    "bold",
    "dim",
    "italic",
    "underline",
}

_OPERATORS = {
    "plus",
    "minus",
    "times",
    "divided",
    "whole",
    "modulo",
    "mod",
    "power",
    "is",
    "not",
    "and",
    "or",
    "equals",
    "equal",
    "contains",
    "contain",
    "does",
    "starts",
    "ends",
    "greater",
    "more",
    "less",
    "least",
    "most",
    "above",
    "under",
    "negative",
    "of",
    "as",
    "the",
    "be",
    "at",
    "current",
}

_LIBS_AND_VALUES = {
    "time",
    "date",
    "ascii",
    "box",
    "center",
    "upper",
    "uppercase",
    "lower",
    "lowercase",
    "trim",
    "trimmed",
    "reverse",
    "reversed",
    "sort",
    "sorted",
    "joined",
    "words",
    "lines",
    "hour",
    "minute",
    "second",
    "seconds",
    "year",
    "month",
    "day",
    "weekday",
    "length",
    "first",
    "last",
    "item",
    "entry",
    "keys",
    "values",
    "true",
    "false",
    "yes",
    "no",
    "nothing",
    "list",
    "map",
    "empty",
    "a",
    "an",
}

_COLOR_HIGHLIGHT: dict[str, str] = {
    "red": "\x1b[91m",
    "green": "\x1b[92m",
    "yellow": "\x1b[93m",
    "blue": "\x1b[94m",
    "magenta": "\x1b[95m",
    "purple": "\x1b[95m",
    "cyan": "\x1b[96m",
    "white": "\x1b[97m",
    "gray": "\x1b[90m",
    "grey": "\x1b[90m",
    "orange": "\x1b[38;5;208m",
    "pink": "\x1b[38;5;213m",
    "bright": "\x1b[1m",
}

_BLOCK_OPENERS = (
    "if ",
    "otherwise",
    "else",
    "repeat ",
    "for each ",
    "while ",
    "every ",
    "to ",
    "try",
)


def highlight_saylang_line(line: str) -> str:
    """Apply SayLang ANSI syntax highlighting to one line, preserving all chars."""
    stripped = line.lstrip(" \t")
    low_stripped = stripped.lower()
    if low_stripped == "note" or (
        low_stripped.startswith("note") and len(low_stripped) > 4 and low_stripped[4] in (" ", "\t", ":")
    ):
        return f"{_GRAY}{line}{_RESET}"

    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]

        if ch == "#":
            out.append(f"{_GRAY}{line[i:]}{_RESET}")
            break

        if ch in ('"', "'"):
            # Possessive 's
            if (
                ch == "'"
                and i > 0
                and (line[i - 1].isalnum() or line[i - 1] == "_")
                and i + 1 < n
                and line[i + 1].lower() == "s"
                and (i + 2 == n or not (line[i + 2].isalnum() or line[i + 2] == "_"))
            ):
                out.append(f"{_PIPE_CLR}'s{_RESET}")
                i += 2
                continue
            quote = ch
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == quote:
                    j += 1
                    break
                j += 1
            out.append(f"{_STRING_CLR}{line[i:j]}{_RESET}")
            i = j
            continue

        if ch == "|":
            out.append(f"{_PIPE_CLR}|{_RESET}")
            i += 1
            continue

        if ch == "-" and i + 1 < n and (
            (line[i + 1] == "-" and i + 2 < n and line[i + 2].isalnum())
            or (line[i + 1].isalpha() and (i == 0 or line[i - 1].isspace()))
        ):
            j = i + 1
            while j < n and (line[j].isalnum() or line[j] in ("_", "-")):
                j += 1
            out.append(f"{_FLAG_CLR}{line[i:j]}{_RESET}")
            i = j
            continue

        if ch.isdigit() and (i == 0 or not (line[i - 1].isalnum() or line[i - 1] == "_")):
            j = i
            while j < n and line[j].isdigit():
                j += 1
            if j < n and line[j] == "." and j + 1 < n and line[j + 1].isdigit():
                j += 1
                while j < n and line[j].isdigit():
                    j += 1
            out.append(f"{_NUMBER_CLR}{line[i:j]}{_RESET}")
            i = j
            continue

        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (line[j].isalnum() or line[j] == "_"):
                j += 1
            word = line[i:j]
            low = word.lower()
            if low in _COLOR_HIGHLIGHT:
                out.append(f"{_COLOR_HIGHLIGHT[low]}{word}{_RESET}")
            elif low in _KEYWORDS:
                out.append(f"{_KW_CLR}{word}{_RESET}")
            elif low in _OPERATORS:
                out.append(f"{_OP_CLR}{word}{_RESET}")
            elif low in _LIBS_AND_VALUES:
                out.append(f"{_LIB_CLR}{word}{_RESET}")
            else:
                out.append(word)
            i = j
            continue

        out.append(ch)
        i += 1

    return "".join(out)


class NanaBuffer:
    """In-memory text buffer and renderer for the `nana` editor."""

    def __init__(
        self,
        lines: list[str] | None = None,
        filepath: Path | None = None,
    ) -> None:
        self.lines: list[str] = lines if lines else [""]
        self.filepath = filepath
        self.row = 0
        self.col = 0
        self.scroll_y = 0
        self.scroll_x = 0
        self.modified = False
        self.cut_buffer: str | None = None
        self.status = ""

    @classmethod
    def from_file(cls, path_str: str | None) -> "NanaBuffer":
        if not path_str:
            return cls(lines=[""], filepath=None)
        path = Path(path_str)
        if path.is_file():
            raw = path.read_text(encoding="utf-8").replace("\r\n", "\n")
            lines = raw.split("\n")
            if len(lines) > 1 and lines[-1] == "":
                lines.pop()
            return cls(lines=lines or [""], filepath=path)
        buf = cls(lines=[""], filepath=path)
        buf.status = f"New file: {path}"
        return buf

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def _clamp_col(self) -> None:
        self.col = max(0, min(self.col, len(self.lines[self.row])))

    def insert_char(self, ch: str) -> None:
        line = self.lines[self.row]
        self.lines[self.row] = line[: self.col] + ch + line[self.col :]
        self.col += len(ch)
        self.modified = True

    def insert_tab(self) -> None:
        self.insert_char("    ")

    def insert_newline(self) -> None:
        line = self.lines[self.row]
        before = line[: self.col]
        after = line[self.col :]
        indent_len = len(before) - len(before.lstrip(" "))
        indent = " " * indent_len
        trimmed = before.strip().lower()
        if trimmed.endswith(":") or (
            any(trimmed.startswith(p) for p in _BLOCK_OPENERS)
            and " then " not in f" {trimmed} "
        ):
            indent += "    "
        self.lines[self.row] = before
        self.lines.insert(self.row + 1, indent + after)
        self.row += 1
        self.col = len(indent)
        self.modified = True

    def backspace(self) -> None:
        if self.col > 0:
            line = self.lines[self.row]
            self.lines[self.row] = line[: self.col - 1] + line[self.col :]
            self.col -= 1
            self.modified = True
        elif self.row > 0:
            prev = self.lines[self.row - 1]
            cur = self.lines.pop(self.row)
            self.row -= 1
            self.col = len(prev)
            self.lines[self.row] = prev + cur
            self.modified = True

    def delete(self) -> None:
        line = self.lines[self.row]
        if self.col < len(line):
            self.lines[self.row] = line[: self.col] + line[self.col + 1 :]
            self.modified = True
        elif self.row + 1 < len(self.lines):
            nxt = self.lines.pop(self.row + 1)
            self.lines[self.row] = line + nxt
            self.modified = True

    def move_left(self) -> None:
        if self.col > 0:
            self.col -= 1
        elif self.row > 0:
            self.row -= 1
            self.col = len(self.lines[self.row])

    def move_right(self) -> None:
        if self.col < len(self.lines[self.row]):
            self.col += 1
        elif self.row + 1 < len(self.lines):
            self.row += 1
            self.col = 0

    def move_up(self) -> None:
        if self.row > 0:
            self.row -= 1
            self._clamp_col()

    def move_down(self) -> None:
        if self.row + 1 < len(self.lines):
            self.row += 1
            self._clamp_col()

    def move_home(self) -> None:
        self.col = 0

    def move_end(self) -> None:
        self.col = len(self.lines[self.row])

    def cut_line(self) -> None:
        self.cut_buffer = self.lines[self.row]
        if len(self.lines) == 1:
            self.lines[0] = ""
            self.col = 0
        else:
            self.lines.pop(self.row)
            if self.row >= len(self.lines):
                self.row = len(self.lines) - 1
            self._clamp_col()
        self.modified = True
        self.status = "Cut line"

    def paste_line(self) -> None:
        if self.cut_buffer is None:
            return
        self.lines.insert(self.row, self.cut_buffer)
        self.row += 1
        self._clamp_col()
        self.modified = True
        self.status = "Pasted line"

    def check_syntax(self) -> tuple[bool, str]:
        if not self.text.strip():
            return True, "Ready"
        try:
            parse_source(self.text)
            return True, "Syntax OK"
        except SayError as err:
            loc = f"Line {err.line}: " if err.line > 0 else ""
            return False, f"{loc}{err.message}"

    def save(self, path: Path | None = None) -> Path:
        target = path or self.filepath
        if target is None:
            raise ValueError("No filename specified.")
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        content = self.text
        if content and not content.endswith("\n"):
            content += "\n"
        target.write_text(content, encoding="utf-8")
        self.filepath = target
        self.modified = False
        self.status = f"Saved {target}"
        return target

    def render_frame(self, rows: int, cols: int) -> str:
        """Render full terminal frame with syntax highlighting and cursor placement."""
        rows = max(rows, 8)
        cols = max(cols, 40)
        body_rows = rows - 3
        gutter_w = max(len(str(len(self.lines))) + 3, 6)
        code_w = max(cols - gutter_w, 10)

        if self.row < self.scroll_y:
            self.scroll_y = self.row
        elif self.row >= self.scroll_y + body_rows:
            self.scroll_y = self.row - body_rows + 1

        if self.col < self.scroll_x:
            self.scroll_x = self.col
        elif self.col >= self.scroll_x + code_w:
            self.scroll_x = self.col - code_w + 1

        name = str(self.filepath) if self.filepath else "[untitled.pl]"
        mod_tag = " [modified]" if self.modified else ""
        left_hdr = f" NANA  {name}{mod_tag}"
        right_hdr = f"Ln {self.row + 1}, Col {self.col + 1}  Saylang v{__version__} "
        gap = max(cols - len(left_hdr) - len(right_hdr), 1)
        header = (left_hdr + " " * gap + right_hdr)[:cols].ljust(cols)

        out: list[str] = ["\x1b[H", f"\x1b[7m{header}{_RESET}\x1b[K\n"]

        num_w = gutter_w - 3
        for vis_r in range(body_rows):
            line_idx = self.scroll_y + vis_r
            if line_idx < len(self.lines):
                raw_line = self.lines[line_idx]
                sliced = raw_line[self.scroll_x : self.scroll_x + code_w]
                hl = highlight_saylang_line(sliced)
                lineno = f"{line_idx + 1:>{num_w}}"
                out.append(f"{_GRAY}{lineno} │ {_RESET}{hl}\x1b[K\n")
            else:
                out.append(f"{_GRAY}{'~':>{num_w}} │ {_RESET}\x1b[K\n")

        ok, syn_msg = self.check_syntax()
        syn_badge = (
            f"\x1b[92m✓ {syn_msg}{_RESET}"
            if ok
            else f"\x1b[91m✗ {syn_msg}{_RESET}"
        )
        extra = f"  │  {self.status}" if self.status else ""
        status_line = f" {syn_badge}{extra}"
        out.append(f"{status_line}\x1b[K\n")

        footer = " ^S Save   ^R Run   ^K Cut   ^U Paste   ^G Help   ^X Exit "
        out.append(f"\x1b[7m{footer[:cols].ljust(cols)}{_RESET}\x1b[K")

        cur_r = (self.row - self.scroll_y) + 2
        cur_c = gutter_w + (self.col - self.scroll_x) + 1
        out.append(f"\x1b[{cur_r};{cur_c}H")
        return "".join(out)


def _read_key() -> str:
    """Read a single logical keypress across POSIX and Windows terminals."""
    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {
                "H": "UP",
                "P": "DOWN",
                "K": "LEFT",
                "M": "RIGHT",
                "G": "HOME",
                "O": "END",
                "S": "DELETE",
            }.get(code, "")
        return ch

    import select

    ch = sys.stdin.read(1)
    if ch == "\x1b":
        if select.select([sys.stdin], [], [], 0.03)[0]:
            nxt = sys.stdin.read(1)
            if nxt == "[":
                seq = ""
                while select.select([sys.stdin], [], [], 0.03)[0]:
                    c = sys.stdin.read(1)
                    seq += c
                    if c.isalpha() or c == "~":
                        break
                return {
                    "A": "UP",
                    "B": "DOWN",
                    "C": "RIGHT",
                    "D": "LEFT",
                    "H": "HOME",
                    "F": "END",
                    "1~": "HOME",
                    "4~": "END",
                    "3~": "DELETE",
                }.get(seq, "")
        return "ESC"
    return ch


def _prompt_bar(buf: NanaBuffer, label: str, default: str = "") -> str | None:
    """Inline single-line prompt on the status bar."""
    val = default
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        buf.status = f"{label}{val}"
        sys.stdout.write(buf.render_frame(rows, cols))
        prompt_col = min(len(label) + len(val) + 2, cols)
        sys.stdout.write(f"\x1b[{rows - 1};1H\x1b[7m {label}{val} \x1b[0m\x1b[K\x1b[{rows - 1};{prompt_col + 1}H")
        sys.stdout.flush()
        key = _read_key()
        if key in ("\r", "\n"):
            buf.status = ""
            return val.strip()
        if key in ("ESC", "\x03"):
            buf.status = "Cancelled"
            return None
        if key in ("\x7f", "\x08"):
            val = val[:-1]
        elif len(key) == 1 and key.isprintable():
            val += key


def _show_overlay(title: str, body: str) -> None:
    """Display output or help overlay inside the alternate screen."""
    cols, rows = shutil.get_terminal_size((80, 24))
    sys.stdout.write("\x1b[H\x1b[2J")
    sys.stdout.write(f"\x1b[7m {title.ljust(max(cols - 1, 1))}{_RESET}\n\n")
    lines = body.splitlines() or ["(no output)"]
    for line in lines[: max(rows - 5, 1)]:
        sys.stdout.write(line + "\n")
    sys.stdout.write(f"\n\x1b[{rows};1H\x1b[7m Press any key to return to nana... {_RESET}")
    sys.stdout.flush()
    _read_key()


def run_nana(filepath: str | None = None) -> int:
    """Launch the interactive `nana` SayLang editor."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("nana requires an interactive terminal.", file=sys.stderr)
        return 1

    runtime._enable_windows_ansi()
    buf = NanaBuffer.from_file(filepath)

    old_attrs = None
    if sys.platform != "win32":
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        tty.setraw(fd)

    try:
        sys.stdout.write("\x1b[?1049h\x1b[?25h")
        sys.stdout.flush()

        while True:
            cols, rows = shutil.get_terminal_size((80, 24))
            sys.stdout.write(buf.render_frame(rows, cols))
            sys.stdout.flush()

            key = _read_key()
            buf.status = ""

            if key in ("\x18", "\x11"):  # Ctrl+X or Ctrl+Q
                if buf.modified:
                    ans = _prompt_bar(buf, "Save modified buffer? (y/n/c): ")
                    if ans is None or ans.lower().startswith("c"):
                        continue
                    if ans.lower().startswith("y"):
                        if buf.filepath is None:
                            fname = _prompt_bar(buf, "File name to save: ", "untitled.pl")
                            if not fname:
                                continue
                            buf.save(Path(fname))
                        else:
                            buf.save()
                return 0

            if key in ("\x13", "\x0f"):  # Ctrl+S or Ctrl+O
                if buf.filepath is None:
                    fname = _prompt_bar(buf, "Save as: ", "untitled.pl")
                    if fname:
                        buf.save(Path(fname))
                else:
                    buf.save()
                continue

            if key == "\x12":  # Ctrl+R Run
                out_buf = io.StringIO()
                try:
                    run_source(buf.text, stdout=out_buf)
                    output = out_buf.getvalue() or "(finished with no output)"
                except SayError as err:
                    output = err.format_pretty(
                        str(buf.filepath) if buf.filepath else "<nana>"
                    )
                _show_overlay("Run Output (SayLang)", output)
                continue

            if key == "\x07":  # Ctrl+G Help
                help_text = (
                    "nana — Built-in SayLang Editor\n\n"
                    "  Ctrl+S / Ctrl+O   Save file\n"
                    "  Ctrl+R            Run current buffer in SayLang\n"
                    "  Ctrl+K            Cut current line\n"
                    "  Ctrl+U            Paste cut line\n"
                    "  Ctrl+G            Show this help\n"
                    "  Ctrl+X / Ctrl+Q   Exit nana\n"
                    "  Tab               Insert 4 spaces\n"
                    "  Enter             Newline with smart auto-indent\n"
                )
                _show_overlay("nana Help", help_text)
                continue

            if key == "\x0b":  # Ctrl+K
                buf.cut_line()
                continue
            if key == "\x15":  # Ctrl+U
                buf.paste_line()
                continue

            if key == "UP":
                buf.move_up()
            elif key == "DOWN":
                buf.move_down()
            elif key == "LEFT":
                buf.move_left()
            elif key == "RIGHT":
                buf.move_right()
            elif key == "HOME":
                buf.move_home()
            elif key == "END":
                buf.move_end()
            elif key == "DELETE":
                buf.delete()
            elif key in ("\x7f", "\x08"):
                buf.backspace()
            elif key in ("\r", "\n"):
                buf.insert_newline()
            elif key == "\t":
                buf.insert_tab()
            elif len(key) == 1 and key.isprintable():
                buf.insert_char(key)

    finally:
        sys.stdout.write("\x1b[?1049l\x1b[0m")
        sys.stdout.flush()
        if old_attrs is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
