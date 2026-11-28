"""nana: built-in TUI studio and terminal text editor with SayLang syntax highlighting."""

from __future__ import annotations

import io
import os
import re
import shlex
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from saylang import __version__, runtime
from saylang.bundler import build_standalone_binary, default_output_path
from saylang.errors import SayError
from saylang.interpreter import run_source
from saylang.parser import parse_source

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_BRIGHT_WHITE = "\x1b[1;97m"
_BLACK_BG = "\x1b[40;48;2;0;0;0m"
_BLACK_RESET = "\x1b[0;40;48;2;0;0;0m"
_DEFAULT_BG = "\x1b[49m"
_GRAY = "\x1b[90m"
_STRING_CLR = "\x1b[92m"
_NUMBER_CLR = "\x1b[93m"
_FLAG_CLR = "\x1b[96m"
_PIPE_CLR = "\x1b[1;95m"
_KW_CLR = "\x1b[1;94m"
_OP_CLR = "\x1b[35m"
_LIB_CLR = "\x1b[36m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _parse_mouse_event(key: str) -> tuple[str, int, int] | None:
    """Parse normalized SGR mouse event 'MOUSE:<KIND>:<row>:<col>' (1-based)."""
    if not key.startswith("MOUSE:"):
        return None
    parts = key.split(":")
    if len(parts) != 4:
        return None
    kind = parts[1]
    if kind not in ("CLICK", "WHEEL_UP", "WHEEL_DOWN"):
        return None
    try:
        return (kind, int(parts[2]), int(parts[3]))
    except ValueError:
        return None


def _footer_shortcut_hit(
    footer: str, col: int, mappings: list[tuple[str, str]]
) -> str | None:
    """Map a 1-based terminal column click on a footer bar to its shortcut key."""
    if col < 1:
        return None
    for label, action_key in mappings:
        idx = footer.find(label)
        if idx >= 0:
            start_col = idx + 1
            end_col = start_col + len(label) - 1
            if start_col <= col <= end_col:
                return action_key
    return None


@dataclass(frozen=True)
class NanaTemplate:
    """Starter SayLang template shown in the nana template picker."""

    id: str
    title: str
    description: str
    filename: str
    code: str


NANA_TEMPLATES: tuple[NanaTemplate, ...] = (
    NanaTemplate(
        id="hello",
        title="Hello World",
        description="Variables, comments (# / note), and colored output",
        filename="hello.pl",
        code=(
            "# Welcome to SayLang!\n"
            "note Both # and note work for comments\n\n"
            'set name to "World"\n'
            'say "Hello, ", name, "!" colour green bold\n'
            'say "hello world lol" colour red\n'
        ),
    ),
    NanaTemplate(
        id="clock",
        title="TTY Clock",
        description="4-line big-letter clock with optional -d date flag",
        filename="clock.pl",
        code=(
            "import time, ascii\n"
            "print time --12h | ascii --size default\n"
            "if flag -d then print date below time\n"
            "flags: -d\n"
        ),
    ),
    NanaTemplate(
        id="live_clock",
        title="Live Ticking Clock",
        description="Centered live clock that updates every second with -d date",
        filename="live_clock.pl",
        code=(
            "# Run with -d to show date (Ctrl+C to stop)\n"
            "import time, ascii\n"
            "flags: -d\n\n"
            "pos center\n"
            "print time --12h --live | ascii --size default colour cyan\n"
            "if flag -d then print date below time\n"
        ),
    ),
    NanaTemplate(
        id="mouse_calc",
        title="Mouse TUI Calculator",
        description="Clickable button grid calculator powered by buttons + calc",
        filename="calc.pl",
        code=(
            'set keys to a list of "7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "C", "0", "=", "+", "Q"\n'
            'set screen to ""\n'
            "while true\n"
            '    set btn to buttons "Calc: {screen}" from keys --cols 4\n'
            '    if btn is "" or btn is "Q"\n'
            "        stop\n"
            '    if btn is "C"\n'
            '        set screen to ""\n'
            '    otherwise if btn is "="\n'
            "        try\n"
            '            set screen to "{calc screen}"\n'
            "        if it fails with err\n"
            '            set screen to "Error"\n'
            "    otherwise\n"
            '        set screen to "{screen}{btn}"\n'
            'say "Result: {screen}" | box --title "Calculator"\n'
        ),
    ),
    NanaTemplate(
        id="cli_tool",
        title="CLI Tool with Flags",
        description="Parse custom flags (-v, --name) and print boxed output",
        filename="greet.pl",
        code=(
            "# Try running with flags: --name Ada -v\n"
            "flags: -v, --name\n\n"
            "set person to flag --name\n"
            "if not person\n"
            '    set person to "friend"\n\n'
            'say "Hello, ", person, "!" | box | colour cyan bold\n'
            "if flag -v then say \"Verbose mode enabled\" colour gray\n"
        ),
    ),
    NanaTemplate(
        id="interactive",
        title="Interactive Prompt",
        description="Ask the user a question and branch on their reply",
        filename="quiz.pl",
        code=(
            "# Simple interactive SayLang script\n"
            'set name to ask "What is your name? "\n'
            'set mood to ask "How are you feeling (good/tired)? "\n\n'
            'if lowercase of mood is "good"\n'
            '    say "Awesome, ", name, "!" colour green bold\n'
            "otherwise\n"
            '    say "Take it easy, ", name, "." colour yellow\n'
        ),
    ),
    NanaTemplate(
        id="todo",
        title="Lists, Maps & Errors",
        description="Maps, possessive 's syntax, loops, and try/if it fails",
        filename="tasks.pl",
        code=(
            "# Tasks with maps and possessive fields\n"
            'set t1 to a map with title as "Try nana TUI", done as true\n'
            'set t2 to a map with title as "Ship something cool", done as false\n'
            "set tasks to a list of t1, and t2\n\n"
            "for each task in tasks\n"
            "    if task's done\n"
            '        say "[x] ", task\'s title colour green\n'
            "    otherwise\n"
            '        say "[ ] ", task\'s title colour yellow\n\n'
            "try\n"
            "    say item 99 of tasks\n"
            "if it fails with err\n"
            '    say "Caught: ", err colour red\n'
        ),
    ),
)

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist"}

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
    "save",
    "load",
    "mkdir",
    "rm",
    "delete",
    "cp",
    "copy",
    "mv",
    "move",
    "glob",
    "shell",
    "exec",
    "fetch",
    "pos",
    "position",
    "file",
    "files",
    "exists",
    "json",
    "parse",
    "parse_json",
    "to_json",
    "from_json",
    "choose",
    "buttons",
    "calc",
    "calculate",
    "key",
    "exit",
    "hide",
    "show",
    "cursor",
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
    "bar",
    "progress",
    "table",
    "rule",
    "divider",
    "args",
    "env",
    "terminal",
    "width",
    "height",
    "split",
    "replace",
    "unique",
    "pad",
    "center",
    "middle",
    "top",
    "bottom",
    "left",
    "right",
    "grep",
    "head",
    "tail",
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

_CHEAT_SHEET = """SayLang Plain-English Reference
───────────────────────────────
Comments     # note on its own line  |  note prose comment
Variables    set score to 10         |  say "Score: {score}"
Math         plus  minus  times  divided by  |  calc "2 + 3 * 4"
Output       say "hi" colour red bold
             print time --12h --live | ascii --size default
Layout       pos center  |  pos top-right  |  pos 10, 5
             print date below time  |  | box --title "Card"
Menus        choose "Mode:" from keys  |  buttons from keys --cols 4
Files/Bash   save cfg to "a.json"  |  load "a.json"  |  shell "ls"
             lines | grep "err" | head 5  |  fetch "https://..."
Flags        flags: -d, --name   |  set who to flag --name or "friend"
Shortcuts    to add with a, b    |  "hi" | shout
Errors       try ... if it fails with err ...

nana Shortcuts
──────────────
Ctrl+S  Save      Ctrl+R  Run buffer    Ctrl+B  Build binary
Ctrl+P  TUI Menu  Ctrl+K  Cut line      Ctrl+U  Paste line
Ctrl+G  Help      Ctrl+X  Exit"""


def _vis_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


def _config_file_path() -> Path:
    override = os.environ.get("SAYLANG_HOME")
    base = Path(override) if override else (Path.home() / ".saylang")
    return base / "nana.json"


def load_bg_mode() -> str:
    """Load persisted nana surface background mode (`mica` or `black`)."""
    import json

    path = _config_file_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mode = str(data.get("bg_mode", "mica")).strip().lower()
            if mode in ("mica", "black"):
                return mode
        except Exception:
            pass
    return "mica"


def save_bg_mode(mode: str) -> str:
    """Persist `mica` or `black` background preference."""
    import json

    norm = "black" if str(mode).strip().lower() == "black" else "mica"
    path = _config_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"bg_mode": norm}, indent=2) + "\n", encoding="utf-8")
    return norm


def _clip_ansi(text: str, max_width: int) -> str:
    """Clip a possibly ANSI-styled line to at most `max_width` visible columns."""
    if max_width <= 0:
        return ""
    out: list[str] = []
    vis = 0
    saw_ansi = False
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\x1b":
            m = _ANSI_RE.match(text, i)
            if m:
                out.append(m.group(0))
                saw_ansi = True
                i = m.end()
                continue
        if vis >= max_width:
            break
        ch = text[i]
        if ch in ("\r", "\n"):
            i += 1
            continue
        out.append(ch)
        vis += 1
        i += 1
    if saw_ansi:
        out.append(_RESET)
    return "".join(out)


def _compose_screen(
    lines: list[str],
    rows: int,
    cols: int,
    *,
    cursor: tuple[int, int] | None = None,
    bg_mode: str = "mica",
) -> str:
    """Render an exact `rows x cols` frame with explicit row positioning and Mica/Black surface."""
    rows = max(rows, 1)
    cols = max(cols, 1)
    use_black = str(bg_mode).strip().lower() == "black"
    parts: list[str] = ["\x1b[?2026h"]
    for idx in range(rows):
        raw = lines[idx] if idx < len(lines) else ""
        clipped = _clip_ansi(raw, cols)
        if use_black:
            styled = clipped.replace(_RESET, _BLACK_RESET)
            pad_n = max(cols - _vis_len(clipped), 0)
            parts.append(f"\x1b[{idx + 1};1H{_BLACK_BG}{styled}{' ' * pad_n}{_BLACK_BG}\x1b[K")
        else:
            parts.append(f"\x1b[{idx + 1};1H{_DEFAULT_BG}{clipped}{_DEFAULT_BG}\x1b[K")
    if cursor is not None:
        cr = max(1, min(cursor[0], rows))
        cc = max(1, min(cursor[1], cols))
        parts.append(f"\x1b[?25h\x1b[{cr};{cc}H")
    else:
        parts.append("\x1b[?25l")
    parts.append("\x1b[?2026l")
    return "".join(parts)


_SIGWINCH_FLAG = False


def _on_sigwinch(_signum: int, _frame: object) -> None:
    global _SIGWINCH_FLAG
    _SIGWINCH_FLAG = True


def _enter_raw_tty() -> object:
    """Configure non-canonical keyboard input while preserving POSIX OPOST output."""
    if sys.platform == "win32":
        return None
    import signal
    import termios

    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    new_attrs = termios.tcgetattr(fd)
    new_attrs[0] &= ~(termios.IXON | termios.ICRNL | termios.ISTRIP | termios.INPCK)
    new_attrs[2] |= termios.CS8
    new_attrs[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN)
    new_attrs[6][termios.VMIN] = 0
    new_attrs[6][termios.VTIME] = 1
    termios.tcsetattr(fd, termios.TCSADRAIN, new_attrs)
    prev_sig = None
    if hasattr(signal, "SIGWINCH"):
        prev_sig = signal.signal(signal.SIGWINCH, _on_sigwinch)
    return (old_attrs, prev_sig)


def _leave_raw_tty(saved: object) -> None:
    """Restore saved terminal attributes and SIGWINCH handler."""
    if saved is None or sys.platform == "win32":
        return
    import signal
    import termios

    old_attrs, prev_sig = saved  # type: ignore[misc]
    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
    if prev_sig is not None and hasattr(signal, "SIGWINCH"):
        signal.signal(signal.SIGWINCH, prev_sig)


def highlight_saylang_line(line: str) -> str:
    """Apply SayLang ANSI syntax highlighting to one line, preserving all chars."""
    stripped = line.lstrip(" \t")
    low_stripped = stripped.lower()
    if low_stripped == "note" or (
        low_stripped.startswith("note")
        and len(low_stripped) > 4
        and low_stripped[4] in (" ", "\t", ":")
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


def discover_pl_files(root: Path | None = None, limit: int = 40) -> list[Path]:
    """Find `.pl` SayLang scripts up to depth 3 under `root`."""
    base = (root or Path.cwd()).resolve()
    found: list[Path] = []
    if not base.is_dir():
        return found

    for dirpath, dirnames, filenames in os.walk(base):
        cur = Path(dirpath)
        rel_parts = cur.relative_to(base).parts if cur != base else ()
        dirnames[:] = sorted(
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        )
        if len(rel_parts) >= 3:
            dirnames[:] = []
        for fname in sorted(filenames):
            if fname.endswith(".pl"):
                found.append(cur / fname)
                if len(found) >= limit:
                    return sorted(found, key=lambda p: str(p.relative_to(base)))
    return sorted(found, key=lambda p: str(p.relative_to(base)))


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

    @classmethod
    def from_template(cls, tpl: NanaTemplate) -> "NanaBuffer":
        lines = tpl.code.rstrip("\n").split("\n")
        buf = cls(lines=lines or [""], filepath=Path(tpl.filename))
        buf.modified = True
        buf.status = f"Template: {tpl.title}"
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

    def render_frame(self, rows: int, cols: int, *, bg_mode: str = "mica") -> str:
        """Render full adaptive terminal frame with quiet hairline chrome."""
        rows = max(rows, 8)
        cols = max(cols, 36)
        body_rows = rows - 4
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
        mod_tag = " *" if self.modified else ""
        right_hdr = f"Ln {self.row + 1}, Col {self.col + 1} · v{__version__} "
        max_left = max(cols - len(right_hdr) - 4, 10)
        left_plain = f" NANA · {name}{mod_tag}"[:max_left]
        gap = max(cols - len(left_plain) - len(right_hdr), 1)
        header = f" {_BOLD}NANA{_RESET} {_GRAY}· {name[:max(max_left - 8, 6)]}{mod_tag}{_RESET}{' ' * gap}{_GRAY}{right_hdr}{_RESET}"

        screen_lines: list[str] = [
            header,
            f"{_GRAY}{'─' * cols}{_RESET}",
        ]

        num_w = gutter_w - 3
        for vis_r in range(body_rows):
            line_idx = self.scroll_y + vis_r
            if line_idx < len(self.lines):
                raw_line = self.lines[line_idx]
                sliced = raw_line[self.scroll_x : self.scroll_x + code_w]
                hl = highlight_saylang_line(sliced)
                lineno = f"{line_idx + 1:>{num_w}}"
                screen_lines.append(f"{_GRAY}{lineno} │ {_RESET}{hl}")
            else:
                screen_lines.append(f"{_GRAY}{'~':>{num_w}} │ {_RESET}")

        ok, syn_msg = self.check_syntax()
        syn_badge = (
            f"\x1b[92m✓ {syn_msg}{_RESET}"
            if ok
            else f"\x1b[91m✗ {syn_msg}{_RESET}"
        )
        extra = f"  │  {self.status}" if self.status else ""
        screen_lines.append(f" {syn_badge}{extra}")

        footer = " ^S Save   ^R Run   ^B Build   ^P Menu   ^K Cut   ^U Paste   ^G Help   ^X Exit "
        screen_lines.append(f"{_DIM}{footer[:cols]}{_RESET}")

        cur_r = (self.row - self.scroll_y) + 3
        cur_c = gutter_w + (self.col - self.scroll_x) + 1
        return _compose_screen(
            screen_lines, rows, cols, cursor=(cur_r, cur_c), bg_mode=bg_mode
        )


def _welcome_items(
    has_active_buffer: bool, bg_mode: str = "mica"
) -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    if has_active_buffer:
        items.append(("resume", "Resume Editor", "Return to your open SayLang buffer"))
    items.extend(
        [
            ("new", "New File", "Start a blank .pl SayLang script"),
            ("template", "Start from Template", "TTY clock, CLI flags, prompts & more"),
            ("open", "Open File", "Browse .pl scripts in the current folder"),
        ]
    )
    if has_active_buffer:
        items.append(("run_flags", "Run with Flags", "Run current buffer with CLI flags (e.g. -d)"))
    bg_label = "Mica (Transparent)" if bg_mode == "mica" else "Black (#000000)"
    items.extend(
        [
            ("learn", "Learn SayLang", "Interactive freeCodeCamp-style TUI course"),
            ("bg", f"Surface: {bg_label}", "Switch transparent Mica vs pure Black [t]"),
            ("cheat", "SayLang Cheat Sheet", "Syntax, colours, pipes & stdlib reference"),
            ("quit", "Quit", "Exit nana"),
        ]
    )
    return items


def render_welcome_menu(
    selected: int,
    rows: int,
    cols: int,
    has_active_buffer: bool = False,
    bg_mode: str = "mica",
) -> str:
    """Render adaptive minimal B&W `nana` welcome/launcher TUI (Mica or Black surface)."""
    rows = max(rows, 10)
    cols = max(cols, 36)
    items = _welcome_items(has_active_buffer, bg_mode=bg_mode)
    sel = max(0, min(selected, len(items) - 1))

    bg_tag = "mica" if bg_mode == "mica" else "black"
    right_top = f"Saylang v{__version__} · {bg_tag} "
    gap_top = max(cols - 16 - len(right_top), 1)
    header_bar = f" {_BOLD}NANA{_RESET} {_GRAY}· studio{_RESET}{' ' * gap_top}{_GRAY}{right_top}{_RESET}"
    hairline = f"{_GRAY}{'─' * cols}{_RESET}"
    footer_bar = f" {_DIM}↑/↓ Move   Enter/Click Select   1-9 Quick Pick   t Surface   Esc/q Quit{_RESET}"

    panel_w = min(cols - 4, 74) if cols >= 56 else cols - 2
    left_margin = " " * max((cols - panel_w) // 2, 1)

    content: list[str] = []
    if rows >= 18:
        if rows >= 22:
            content.append("")
        card = [
            f"{_BOLD}╭─────────────╮{_RESET}   {_BOLD}NANA{_RESET}  {_GRAY}Saylang v{__version__}{_RESET}",
            f"{_BOLD}│ ╭─╮ ╭─╮ ╷ ╷ │{_RESET}   {_GRAY}plain-english editor · .pl{_RESET}",
            f"{_BOLD}│ ╰─╮ ├─┤ ╰┬╯ │{_RESET}   {_GRAY}adaptive tui · {bg_tag} surface{_RESET}",
            f"{_BOLD}│ ╰─╯ ╵ ╵  ╵  │{_RESET}",
            f"{_BOLD}╰─────────────╯{_RESET}",
        ]
        for c_ln in card:
            content.append(f"{left_margin}{c_ln}")
        content.append("")
    else:
        content.append(f"{left_margin}{_BOLD}NANA · Saylang v{__version__}{_RESET}")
        content.append("")

    avail_rows = max(rows - 4 - len(content), 3)
    scroll = 0
    if sel >= avail_rows:
        scroll = sel - avail_rows + 1

    title_w = min(28, max(panel_w - 8, 12))
    show_desc = panel_w >= 54
    for idx in range(scroll, min(len(items), scroll + avail_rows)):
        _key, title, desc = items[idx]
        num = idx + 1
        t_txt = title[:title_w].ljust(title_w)
        if show_desc:
            d_w = max(panel_w - title_w - 8, 8)
            d_txt = desc[:d_w]
        else:
            d_txt = ""
        if idx == sel:
            if d_txt:
                content.append(
                    f"{left_margin}{_BRIGHT_WHITE}▌ {num}. {t_txt}{_RESET} \x1b[37m{d_txt}{_RESET}"
                )
            else:
                content.append(f"{left_margin}{_BRIGHT_WHITE}▌ {num}. {title[:max(panel_w - 6, 8)]}{_RESET}")
        else:
            if d_txt:
                content.append(
                    f"{left_margin}  {_GRAY}{num}.{_RESET} \x1b[37m{t_txt}{_RESET} {_GRAY}{d_txt}{_RESET}"
                )
            else:
                content.append(f"{left_margin}  {_GRAY}{num}.{_RESET} \x1b[37m{title[:max(panel_w - 6, 8)]}{_RESET}")

    body_target = rows - 2
    lines: list[str] = [header_bar, hairline, *content]
    while len(lines) < body_target:
        lines.append("")
    lines = lines[:body_target]
    lines.append(hairline)
    lines.append(footer_bar)
    return _compose_screen(lines, rows, cols, bg_mode=bg_mode)


def render_template_picker(
    selected: int, rows: int, cols: int, bg_mode: str = "mica"
) -> str:
    """Render adaptive template selector with live syntax-highlighted preview."""
    rows = max(rows, 10)
    cols = max(cols, 36)
    sel = max(0, min(selected, len(NANA_TEMPLATES) - 1))
    tpl = NANA_TEMPLATES[sel]

    header_bar = f" {_BOLD}NANA{_RESET} {_GRAY}· Start from Template{_RESET}"
    hairline = f"{_GRAY}{'─' * cols}{_RESET}"
    footer_bar = f" {_DIM}↑/↓ Choose Template   Enter Open in Editor   t Surface   Esc Back{_RESET}"

    body_rows = rows - 4
    preview_lines = tpl.code.rstrip("\n").split("\n")

    if cols >= 72:
        left_w = max(26, min(40, cols * 36 // 100))
        right_w = max(cols - left_w - 2, 20)
        cap = max(body_rows - 5, 3)
        scroll = max(0, sel - cap + 1)

        left_col: list[str] = ["", f" {_BOLD}Templates{_RESET}", ""]
        for idx in range(scroll, min(len(NANA_TEMPLATES), scroll + cap)):
            item = NANA_TEMPLATES[idx]
            label = f"{idx + 1}. {item.title}"[: max(left_w - 5, 10)]
            if idx == sel:
                left_col.append(f" {_BRIGHT_WHITE}▌ {label}{_RESET}")
            else:
                left_col.append(f"   \x1b[37m{label}{_RESET}")
        left_col.extend(["", f" {_GRAY}{tpl.description[:max(left_w - 2, 10)]}{_RESET}"])

        right_col: list[str] = [
            "",
            f" {_BOLD}Preview: {tpl.filename}{_RESET}",
            f" {_GRAY}{'─' * min(right_w - 2, 46)}{_RESET}",
        ]
        for pline in preview_lines:
            right_col.append(" " + highlight_saylang_line(pline[: max(right_w - 2, 8)]))

        screen_lines: list[str] = [header_bar, hairline]
        for r in range(body_rows):
            l_txt = _clip_ansi(left_col[r], left_w) if r < len(left_col) else ""
            r_txt = _clip_ansi(right_col[r], right_w) if r < len(right_col) else ""
            pad = " " * max(left_w - _vis_len(l_txt), 0)
            screen_lines.append(f"{l_txt}{pad}{_GRAY}│{_RESET}{r_txt}")
        screen_lines.extend([hairline, footer_bar])
        return _compose_screen(screen_lines, rows, cols, bg_mode=bg_mode)

    out_narrow: list[str] = [header_bar, hairline]
    list_cap = max(min(len(NANA_TEMPLATES), body_rows // 2), 2)
    scroll = max(0, sel - list_cap + 1)
    for idx in range(scroll, min(len(NANA_TEMPLATES), scroll + list_cap)):
        item = NANA_TEMPLATES[idx]
        label = f"{idx + 1}. {item.title}"[: max(cols - 6, 10)]
        if idx == sel:
            out_narrow.append(f" {_BRIGHT_WHITE}▌ {label}{_RESET}")
        else:
            out_narrow.append(f"   \x1b[37m{label}{_RESET}")
    if len(out_narrow) + 3 < rows - 2:
        out_narrow.extend(["", f" {_BOLD}Preview ({tpl.filename}):{_RESET}"])
        for pline in preview_lines[: max(rows - 2 - len(out_narrow), 1)]:
            out_narrow.append(" " + highlight_saylang_line(pline[: max(cols - 2, 10)]))
    while len(out_narrow) < rows - 2:
        out_narrow.append("")
    out_narrow = out_narrow[: rows - 2]
    out_narrow.extend([hairline, footer_bar])
    return _compose_screen(out_narrow, rows, cols, bg_mode=bg_mode)


def render_file_picker(
    files: list[Path],
    selected: int,
    rows: int,
    cols: int,
    root: Path | None = None,
    bg_mode: str = "mica",
) -> str:
    """Render adaptive `.pl` file browser with live syntax-highlighted preview."""
    rows = max(rows, 10)
    cols = max(cols, 36)
    base = (root or Path.cwd()).resolve()
    total = len(files) + 1
    sel = max(0, min(selected, total - 1))

    header_bar = f" {_BOLD}NANA{_RESET} {_GRAY}· Open .pl File ({base.name}){_RESET}"
    hairline = f"{_GRAY}{'─' * cols}{_RESET}"
    footer_bar = f" {_DIM}↑/↓ Select   Enter Open   / Type Path   t Surface   Esc Back{_RESET}"

    body_rows = rows - 4
    labels: list[str] = []
    for p in files:
        try:
            labels.append(str(p.relative_to(base)))
        except ValueError:
            labels.append(str(p))
    labels.append("[Type custom path...]")

    preview_title = "Custom Path"
    preview_lines: list[str] = ["Press Enter or '/' to type any file path."]
    if sel < len(files):
        chosen = files[sel]
        preview_title = labels[sel]
        try:
            preview_lines = (
                chosen.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")[: max(body_rows, 25)]
            )
        except OSError as exc:
            preview_lines = [f"(Cannot read file: {exc})"]

    list_cap = max(body_rows - 4, 3)
    scroll = max(0, sel - list_cap + 1)

    if cols >= 72:
        left_w = max(26, min(40, cols * 36 // 100))
        right_w = max(cols - left_w - 2, 20)
        left_col: list[str] = ["", f" {_BOLD}.pl Files{_RESET}", ""]
        for idx in range(scroll, min(len(labels), scroll + list_cap)):
            lbl = labels[idx][: max(left_w - 5, 8)]
            if idx == sel:
                left_col.append(f" {_BRIGHT_WHITE}▌ {lbl}{_RESET}")
            else:
                left_col.append(f"   \x1b[37m{lbl}{_RESET}")

        right_col: list[str] = [
            "",
            f" {_BOLD}Preview: {preview_title}{_RESET}",
            f" {_GRAY}{'─' * min(right_w - 2, 46)}{_RESET}",
        ]
        for pline in preview_lines:
            right_col.append(" " + highlight_saylang_line(pline[: max(right_w - 2, 8)]))

        screen_lines = [header_bar, hairline]
        for r in range(body_rows):
            l_txt = _clip_ansi(left_col[r], left_w) if r < len(left_col) else ""
            r_txt = _clip_ansi(right_col[r], right_w) if r < len(right_col) else ""
            pad = " " * max(left_w - _vis_len(l_txt), 0)
            screen_lines.append(f"{l_txt}{pad}{_GRAY}│{_RESET}{r_txt}")
        screen_lines.extend([hairline, footer_bar])
        return _compose_screen(screen_lines, rows, cols, bg_mode=bg_mode)

    out_narrow = [header_bar, hairline]
    for idx in range(scroll, min(len(labels), scroll + list_cap)):
        lbl = labels[idx][: max(cols - 6, 10)]
        if idx == sel:
            out_narrow.append(f" {_BRIGHT_WHITE}▌ {lbl}{_RESET}")
        else:
            out_narrow.append(f"   \x1b[37m{lbl}{_RESET}")
    while len(out_narrow) < rows - 2:
        out_narrow.append("")
    out_narrow = out_narrow[: rows - 2]
    out_narrow.extend([hairline, footer_bar])
    return _compose_screen(out_narrow, rows, cols, bg_mode=bg_mode)


def _read_key() -> str:
    """Read a single logical keypress or 'RESIZE' across POSIX and Windows terminals."""
    global _SIGWINCH_FLAG
    last_size = shutil.get_terminal_size((80, 24))

    if sys.platform == "win32":
        import msvcrt
        import time

        while True:
            cur_size = shutil.get_terminal_size((80, 24))
            if cur_size != last_size:
                return "RESIZE"
            if msvcrt.kbhit():
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
            time.sleep(0.05)

    import codecs
    import select

    fd = sys.stdin.fileno()
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    def read_fd_char() -> str:
        while True:
            raw_b = os.read(fd, 1)
            if not raw_b:
                return ""
            decoded = decoder.decode(raw_b, final=False)
            if decoded:
                return decoded

    while True:
        if _SIGWINCH_FLAG:
            _SIGWINCH_FLAG = False
            return "RESIZE"
        cur_size = shutil.get_terminal_size((80, 24))
        if cur_size != last_size:
            return "RESIZE"
        try:
            ready, _, _ = select.select([fd], [], [], 0.12)
        except InterruptedError:
            _SIGWINCH_FLAG = False
            return "RESIZE"
        if not ready:
            continue
        ch = read_fd_char()
        if not ch:
            continue
        if ch == "\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                nxt = read_fd_char()
                if nxt == "[":
                    seq = ""
                    while select.select([fd], [], [], 0.05)[0]:
                        c = read_fd_char()
                        if not c:
                            break
                        seq += c
                        if c.isalpha() or c == "~":
                            break
                    if seq == "M":
                        for _ in range(3):
                            if select.select([fd], [], [], 0.05)[0]:
                                read_fd_char()
                        return ""
                    if seq.startswith("<") and len(seq) >= 5 and seq[-1] in ("M", "m"):
                        body = seq[1:-1].split(";")
                        if len(body) == 3:
                            try:
                                btn = int(body[0])
                                col_m = int(body[1])
                                row_m = int(body[2])
                            except ValueError:
                                return ""
                            if seq[-1] == "m":
                                return ""
                            if (btn & 64) != 0:
                                wheel = btn & 3
                                if wheel == 0:
                                    return f"MOUSE:WHEEL_UP:{row_m}:{col_m}"
                                if wheel == 1:
                                    return f"MOUSE:WHEEL_DOWN:{row_m}:{col_m}"
                                return ""
                            if (btn & 32) == 0 and (btn & 3) == 0:
                                return f"MOUSE:CLICK:{row_m}:{col_m}"
                        return ""
                    exact = {
                        "A": "UP",
                        "B": "DOWN",
                        "C": "RIGHT",
                        "D": "LEFT",
                        "H": "HOME",
                        "F": "END",
                        "1~": "HOME",
                        "4~": "END",
                        "3~": "DELETE",
                    }.get(seq)
                    if exact:
                        return exact
                    if seq and seq[-1] in ("A", "B", "C", "D", "H", "F"):
                        return {
                            "A": "UP",
                            "B": "DOWN",
                            "C": "RIGHT",
                            "D": "LEFT",
                            "H": "HOME",
                            "F": "END",
                        }[seq[-1]]
                    return ""
                if nxt == "O":
                    code = read_fd_char() if select.select([fd], [], [], 0.05)[0] else ""
                    return {
                        "A": "UP",
                        "B": "DOWN",
                        "C": "RIGHT",
                        "D": "LEFT",
                        "H": "HOME",
                        "F": "END",
                    }.get(code, "")
                return ""
            return "ESC"
        return ch


def _prompt_bar(
    label: str,
    default: str = "",
    *,
    buf: NanaBuffer | None = None,
    bg_mode: str = "mica",
) -> str | None:
    """Inline single-line prompt on the bottom status line."""
    val = default
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        if buf is not None:
            buf.status = ""
            sys.stdout.write(buf.render_frame(rows, cols, bg_mode=bg_mode))
        prompt_row = rows - 1 if buf is not None else rows
        raw_prompt = f" ▸ {label}{val}"
        clipped = _clip_ansi(raw_prompt, cols)
        prompt_col = min(_vis_len(clipped) + 1, cols)
        bg = _BLACK_BG if bg_mode == "black" else _DEFAULT_BG
        sys.stdout.write(
            f"\x1b[{prompt_row};1H{bg}{_BRIGHT_WHITE}{clipped.ljust(cols)}{_RESET}{bg}\x1b[K"
            f"\x1b[?25h\x1b[{prompt_row};{prompt_col}H"
        )
        sys.stdout.flush()
        key = _read_key()
        if not key or key == "RESIZE" or key.startswith("MOUSE:"):
            continue
        if key in ("\r", "\n"):
            return val.strip()
        if key in ("ESC", "\x03"):
            return None
        if key in ("\x7f", "\x08"):
            val = val[:-1]
        elif len(key) == 1 and key.isprintable():
            val += key


def _show_overlay(title: str, body: str, *, bg_mode: str = "mica") -> None:
    """Display scrollable adaptive overlay inside the alternate screen."""
    lines = body.splitlines() or ["(no output)"]
    scroll = 0
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        body_cap = max(rows - 5, 1)
        max_scroll = max(len(lines) - body_cap, 0)
        scroll = max(0, min(scroll, max_scroll))

        hairline = f"{_GRAY}{'─' * cols}{_RESET}"
        screen: list[str] = [
            f" {_BOLD}{title[:max(cols - 2, 1)]}{_RESET}",
            hairline,
        ]
        for ln in lines[scroll : scroll + body_cap]:
            screen.append(" " + ln)
        while len(screen) < rows - 2:
            screen.append("")
        hint = (
            " ↑/↓ Scroll   Click/Any key to return... "
            if max_scroll > 0
            else " Click or press any key to return... "
        )
        screen.extend([hairline, f" {_DIM}{hint}{_RESET}"])
        sys.stdout.write(_compose_screen(screen, rows, cols, bg_mode=bg_mode))
        sys.stdout.flush()
        k = _read_key()
        if not k or k == "RESIZE":
            continue
        mouse = _parse_mouse_event(k)
        if mouse is not None:
            mkind, _mr, _mc = mouse
            if mkind == "WHEEL_UP":
                if max_scroll > 0:
                    scroll = max(scroll - 3, 0)
                continue
            if mkind == "WHEEL_DOWN":
                if max_scroll > 0:
                    scroll = min(scroll + 3, max_scroll)
                continue
            return
        if k == "UP" and max_scroll > 0:
            scroll = max(scroll - 1, 0)
            continue
        if k == "DOWN" and max_scroll > 0:
            scroll = min(scroll + 1, max_scroll)
            continue
        return


def _run_interactive_source(
    code: str,
    *,
    title: str,
    filename: str,
    cli_args: list[str] | None,
    tty_state: list[object],
    cwd: str | None = None,
) -> None:
    """Temporarily leave the TUI and execute SayLang code interactively in the real terminal."""
    sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[?1049l\x1b[?25h\x1b[0m")
    sys.stdout.flush()
    _leave_raw_tty(tty_state[0])
    tty_state[0] = None
    if sys.platform != "win32":
        try:
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        except Exception:
            pass

    prev_cwd = os.getcwd()
    try:
        if cwd is not None:
            os.chdir(cwd)
        sys.stdout.write(
            f"\x1b[2J\x1b[H\x1b[1;96m▶ Running {title}\x1b[0m  \x1b[90m(Ctrl+C to stop)\x1b[0m\n"
            f"\x1b[90m{'─' * 50}\x1b[0m\n"
        )
        sys.stdout.flush()
        try:
            run_source(code, stdout=sys.stdout, input_fn=input, cli_args=cli_args or [])
        except KeyboardInterrupt:
            sys.stdout.write("\n\x1b[90m(stopped)\x1b[0m\n")
        except SystemExit as exc:
            if exc.code not in (None, 0):
                sys.stdout.write(f"\n\x1b[90m(exited with code {exc.code})\x1b[0m\n")
        except SayError as err:
            sys.stdout.write(f"\n\x1b[91m{err.format_pretty(filename)}\x1b[0m\n")
    finally:
        if cwd is not None:
            os.chdir(prev_cwd)
        sys.stdout.write(
            f"\x1b[?1006l\x1b[?1000l\x1b[?25h\x1b[0m\n\x1b[90m{'─' * 50}\n"
            "Press any key to return to editor...\x1b[0m"
        )
        sys.stdout.flush()
        tty_state[0] = _enter_raw_tty()
        while True:
            k = _read_key()
            if k and k != "RESIZE":
                break
        sys.stdout.write("\x1b[?1049h\x1b[?1000h\x1b[?1006h\x1b[?25h")
        sys.stdout.flush()


def _run_buffer(
    buf: NanaBuffer,
    cli_args: list[str] | None = None,
    *,
    bg_mode: str = "mica",
    tty_state: list[object] | None = None,
) -> None:
    if tty_state is not None:
        fname = str(buf.filepath) if buf.filepath else "<nana>"
        title = buf.filepath.name if buf.filepath else "SayLang Buffer"
        _run_interactive_source(
            buf.text,
            title=title,
            filename=fname,
            cli_args=cli_args,
            tty_state=tty_state,
        )
        return
    out_buf = io.StringIO()
    try:
        run_source(buf.text, stdout=out_buf, cli_args=cli_args)
        output = out_buf.getvalue() or "(finished with no output)"
    except SayError as err:
        output = err.format_pretty(str(buf.filepath) if buf.filepath else "<nana>")
    _show_overlay("Run Output (SayLang)", output, bg_mode=bg_mode)


def _select_template_tui(bg_state: list[str]) -> NanaBuffer | None:
    sel = 0
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        rows_e = max(rows, 10)
        cols_e = max(cols, 36)
        sys.stdout.write(render_template_picker(sel, rows, cols, bg_mode=bg_state[0]))
        sys.stdout.flush()
        key = _read_key()
        if not key or key == "RESIZE":
            continue
        mouse = _parse_mouse_event(key)
        if mouse is not None:
            mkind, m_row, m_col = mouse
            if mkind == "WHEEL_UP":
                sel = (sel - 1) % len(NANA_TEMPLATES)
                continue
            if mkind == "WHEEL_DOWN":
                sel = (sel + 1) % len(NANA_TEMPLATES)
                continue
            body_rows = rows_e - 4
            if cols_e >= 72:
                left_w = max(26, min(40, cols_e * 36 // 100))
                cap = max(body_rows - 5, 3)
                first_row = 6
                in_col = m_col <= left_w
            else:
                cap = max(min(len(NANA_TEMPLATES), body_rows // 2), 2)
                first_row = 3
                in_col = True
            scroll = max(0, sel - cap + 1)
            if in_col and 0 <= m_row - first_row < cap:
                idx = scroll + (m_row - first_row)
                if 0 <= idx < len(NANA_TEMPLATES):
                    if idx == sel:
                        return NanaBuffer.from_template(NANA_TEMPLATES[idx])
                    sel = idx
            continue
        if key == "t":
            bg_state[0] = save_bg_mode("black" if bg_state[0] == "mica" else "mica")
            continue
        if key == "UP":
            sel = (sel - 1) % len(NANA_TEMPLATES)
        elif key == "DOWN":
            sel = (sel + 1) % len(NANA_TEMPLATES)
        elif key in ("\r", "\n"):
            return NanaBuffer.from_template(NANA_TEMPLATES[sel])
        elif key.isdigit() and 1 <= int(key) <= len(NANA_TEMPLATES):
            return NanaBuffer.from_template(NANA_TEMPLATES[int(key) - 1])
        elif key in ("ESC", "q", "\x03"):
            return None


def _select_file_tui(bg_state: list[str]) -> NanaBuffer | None:
    root = Path.cwd().resolve()
    files = discover_pl_files(root)
    sel = 0
    total = len(files) + 1
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        rows_e = max(rows, 10)
        cols_e = max(cols, 36)
        sys.stdout.write(
            render_file_picker(files, sel, rows, cols, root, bg_mode=bg_state[0])
        )
        sys.stdout.flush()
        key = _read_key()
        if not key or key == "RESIZE":
            continue
        mouse = _parse_mouse_event(key)
        if mouse is not None:
            mkind, m_row, m_col = mouse
            if mkind == "WHEEL_UP":
                sel = (sel - 1) % total
                continue
            if mkind == "WHEEL_DOWN":
                sel = (sel + 1) % total
                continue
            body_rows = rows_e - 4
            cap = max(body_rows - 4, 3)
            if cols_e >= 72:
                left_w = max(26, min(40, cols_e * 36 // 100))
                first_row = 6
                in_col = m_col <= left_w
            else:
                first_row = 3
                in_col = True
            scroll = max(0, sel - cap + 1)
            if in_col and 0 <= m_row - first_row < cap:
                idx = scroll + (m_row - first_row)
                if 0 <= idx < total:
                    if idx == sel:
                        if idx < len(files):
                            return NanaBuffer.from_file(str(files[idx]))
                        custom = _prompt_bar("Open file path: ", bg_mode=bg_state[0])
                        if custom:
                            return NanaBuffer.from_file(custom)
                    else:
                        sel = idx
            continue
        if key == "t":
            bg_state[0] = save_bg_mode("black" if bg_state[0] == "mica" else "mica")
            continue
        if key == "UP":
            sel = (sel - 1) % total
        elif key == "DOWN":
            sel = (sel + 1) % total
        elif key == "/":
            custom = _prompt_bar("Open file path: ", bg_mode=bg_state[0])
            if custom:
                return NanaBuffer.from_file(custom)
        elif key in ("\r", "\n"):
            if sel < len(files):
                return NanaBuffer.from_file(str(files[sel]))
            custom = _prompt_bar("Open file path: ", bg_mode=bg_state[0])
            if custom:
                return NanaBuffer.from_file(custom)
        elif key in ("ESC", "q", "\x03"):
            return None


def _run_menu_tui(
    active_buf: NanaBuffer | None,
    bg_state: list[str],
    tty_state: list[object] | None = None,
) -> tuple[str, NanaBuffer | None]:
    """Show the main nana launcher/menu TUI. Returns ('edit', buf) or ('quit', None)."""
    sel = 0
    while True:
        items = _welcome_items(active_buf is not None, bg_mode=bg_state[0])
        sel = max(0, min(sel, len(items) - 1))
        cols, rows = shutil.get_terminal_size((80, 24))
        rows_e = max(rows, 10)
        sys.stdout.write(
            render_welcome_menu(
                sel,
                rows,
                cols,
                has_active_buffer=active_buf is not None,
                bg_mode=bg_state[0],
            )
        )
        sys.stdout.flush()
        key = _read_key()
        if not key or key == "RESIZE":
            continue
        if key == "t":
            bg_state[0] = save_bg_mode("black" if bg_state[0] == "mica" else "mica")
            continue

        chosen_action: str | None = None
        mouse = _parse_mouse_event(key)
        if mouse is not None:
            mkind, m_row, _m_col = mouse
            if mkind == "WHEEL_UP":
                sel = (sel - 1) % len(items)
                continue
            if mkind == "WHEEL_DOWN":
                sel = (sel + 1) % len(items)
                continue
            first_item_row = 10 if rows_e >= 22 else (9 if rows_e >= 18 else 5)
            avail_rows = max(rows_e - 4 - (first_item_row - 3), 3)
            scroll = sel - avail_rows + 1 if sel >= avail_rows else 0
            if 0 <= m_row - first_item_row < avail_rows:
                idx = scroll + (m_row - first_item_row)
                if 0 <= idx < len(items):
                    sel = idx
                    chosen_action = items[idx][0]
            if chosen_action is None:
                continue
        elif key == "UP":
            sel = (sel - 1) % len(items)
        elif key == "DOWN":
            sel = (sel + 1) % len(items)
        elif key in ("\r", "\n"):
            chosen_action = items[sel][0]
        elif key.isdigit() and 1 <= int(key) <= len(items):
            chosen_action = items[int(key) - 1][0]
        elif key in ("ESC", "q", "\x18", "\x03"):
            if active_buf is not None:
                return ("edit", active_buf)
            return ("quit", None)

        if chosen_action == "resume" and active_buf is not None:
            return ("edit", active_buf)
        if chosen_action == "new":
            fname = _prompt_bar(
                "New file name (Enter for untitled): ", bg_mode=bg_state[0]
            )
            if fname is None:
                continue
            buf = NanaBuffer(lines=[""], filepath=Path(fname) if fname else None)
            return ("edit", buf)
        if chosen_action == "template":
            buf = _select_template_tui(bg_state)
            if buf is not None:
                return ("edit", buf)
        if chosen_action == "open":
            buf = _select_file_tui(bg_state)
            if buf is not None:
                return ("edit", buf)
        if chosen_action == "run_flags" and active_buf is not None:
            raw_flags = _prompt_bar("Flags (e.g. -d): ", bg_mode=bg_state[0])
            if raw_flags is not None:
                try:
                    parsed_flags = shlex.split(raw_flags)
                except ValueError:
                    parsed_flags = raw_flags.split()
                _run_buffer(
                    active_buf,
                    cli_args=parsed_flags,
                    bg_mode=bg_state[0],
                    tty_state=tty_state,
                )
                return ("edit", active_buf)
        if chosen_action == "learn":
            from saylang.learn import run_learn

            run_learn(bg=bg_state[0], _managed_tty=True, _tty_state=tty_state)
            bg_state[0] = load_bg_mode()
        if chosen_action == "bg":
            bg_state[0] = save_bg_mode("black" if bg_state[0] == "mica" else "mica")
        if chosen_action == "cheat":
            _show_overlay("SayLang Cheat Sheet", _CHEAT_SHEET, bg_mode=bg_state[0])
        if chosen_action == "quit":
            if active_buf is not None and active_buf.modified:
                ans = _prompt_bar(
                    "Unsaved changes — save before quit? (y/n/c): ",
                    bg_mode=bg_state[0],
                )
                if ans is None or ans.lower().startswith("c"):
                    continue
                if ans.lower().startswith("y"):
                    if active_buf.filepath is None:
                        fname = _prompt_bar(
                            "Save as: ", "untitled.pl", bg_mode=bg_state[0]
                        )
                        if not fname:
                            continue
                        active_buf.save(Path(fname))
                    else:
                        active_buf.save()
            return ("quit", None)


def run_nana(filepath: str | None = None, *, bg: str | None = None) -> int:
    """Launch the interactive `nana` SayLang TUI studio & editor."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("nana requires an interactive terminal.", file=sys.stderr)
        return 1

    runtime._enable_windows_ansi()
    bg_state = [save_bg_mode(bg) if bg else load_bg_mode()]
    buf: NanaBuffer | None = NanaBuffer.from_file(filepath) if filepath else None
    tty_state: list[object] = [_enter_raw_tty()]

    try:
        sys.stdout.write("\x1b[?1049h\x1b[?1000h\x1b[?1006h\x1b[?25h")
        sys.stdout.flush()

        if buf is None:
            action, buf = _run_menu_tui(None, bg_state, tty_state)
            if action == "quit" or buf is None:
                return 0

        while True:
            cols, rows = shutil.get_terminal_size((80, 24))
            rows_e = max(rows, 8)
            cols_e = max(cols, 36)
            sys.stdout.write(buf.render_frame(rows, cols, bg_mode=bg_state[0]))
            sys.stdout.flush()

            key = _read_key()
            if not key or key == "RESIZE":
                continue
            buf.status = ""

            mouse = _parse_mouse_event(key)
            if mouse is not None:
                mkind, m_row, m_col = mouse
                body_rows = rows_e - 4
                gutter_w = max(len(str(len(buf.lines))) + 3, 6)
                if mkind == "WHEEL_UP":
                    if buf.scroll_y > 0:
                        buf.scroll_y = max(0, buf.scroll_y - 3)
                        if buf.row >= buf.scroll_y + body_rows:
                            buf.row = buf.scroll_y + body_rows - 1
                    else:
                        buf.row = max(0, buf.row - 3)
                    buf._clamp_col()
                    continue
                if mkind == "WHEEL_DOWN":
                    max_sy = max(0, len(buf.lines) - body_rows)
                    if buf.scroll_y < max_sy:
                        buf.scroll_y = min(max_sy, buf.scroll_y + 3)
                        if buf.row < buf.scroll_y:
                            buf.row = buf.scroll_y
                    else:
                        buf.row = min(len(buf.lines) - 1, buf.row + 3)
                    buf._clamp_col()
                    continue
                if m_row == rows_e:
                    footer = " ^S Save   ^R Run   ^B Build   ^P Menu   ^K Cut   ^U Paste   ^G Help   ^X Exit "
                    mapped = _footer_shortcut_hit(
                        footer[:cols_e],
                        m_col,
                        [
                            ("^S Save", "\x13"),
                            ("^R Run", "\x12"),
                            ("^B Build", "\x02"),
                            ("^P Menu", "\x10"),
                            ("^K Cut", "\x0b"),
                            ("^U Paste", "\x15"),
                            ("^G Help", "\x07"),
                            ("^X Exit", "\x18"),
                        ],
                    )
                    if mapped is not None:
                        key = mapped
                    else:
                        continue
                elif 3 <= m_row <= 2 + body_rows:
                    target_row = min(
                        max(0, buf.scroll_y + (m_row - 3)), len(buf.lines) - 1
                    )
                    target_col = min(
                        max(0, buf.scroll_x + max(0, m_col - (gutter_w + 1))),
                        len(buf.lines[target_row]),
                    )
                    buf.row = target_row
                    buf.col = target_col
                    continue
                else:
                    continue

            if key == "\x10":  # Ctrl+P -> TUI Menu
                action, next_buf = _run_menu_tui(buf, bg_state, tty_state)
                if action == "quit":
                    return 0
                if next_buf is not None:
                    buf = next_buf
                continue

            if key in ("\x18", "\x11"):  # Ctrl+X or Ctrl+Q
                if buf.modified:
                    ans = _prompt_bar(
                        "Save modified buffer? (y/n/c): ",
                        buf=buf,
                        bg_mode=bg_state[0],
                    )
                    if ans is None or ans.lower().startswith("c"):
                        continue
                    if ans.lower().startswith("y"):
                        if buf.filepath is None:
                            fname = _prompt_bar(
                                "File name to save: ",
                                "untitled.pl",
                                buf=buf,
                                bg_mode=bg_state[0],
                            )
                            if not fname:
                                continue
                            buf.save(Path(fname))
                        else:
                            buf.save()
                return 0

            if key in ("\x13", "\x0f"):  # Ctrl+S or Ctrl+O
                if buf.filepath is None:
                    fname = _prompt_bar(
                        "Save as: ", "untitled.pl", buf=buf, bg_mode=bg_state[0]
                    )
                    if fname:
                        buf.save(Path(fname))
                else:
                    buf.save()
                continue

            if key == "\x12":  # Ctrl+R Run
                _run_buffer(buf, bg_mode=bg_state[0], tty_state=tty_state)
                continue

            if key == "\x02":  # Ctrl+B Build Binary
                def_out = default_output_path(buf.filepath)
                target = _prompt_bar(
                    "Build binary as: ",
                    str(def_out),
                    buf=buf,
                    bg_mode=bg_state[0],
                )
                if target:
                    try:
                        res = build_standalone_binary(
                            source=buf.text(),
                            name=buf.filepath.name if buf.filepath else "app.pl",
                            output_path=Path(target),
                        )
                        buf.status = f"Built binary: {res.output_path}"
                    except (SayError, RuntimeError, OSError) as exc:
                        buf.status = f"Build failed: {exc}"
                continue

            if key == "\x07":  # Ctrl+G Help
                _show_overlay("SayLang & nana Help", _CHEAT_SHEET, bg_mode=bg_state[0])
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
        sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[?1049l\x1b[?25h\x1b[0m")
        sys.stdout.flush()
        _leave_raw_tty(tty_state[0])
