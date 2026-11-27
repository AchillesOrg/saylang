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
from saylang.errors import SayError
from saylang.interpreter import run_source
from saylang.parser import parse_source

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_INV = "\x1b[7m"
_GRAY = "\x1b[90m"
_STRING_CLR = "\x1b[92m"
_NUMBER_CLR = "\x1b[93m"
_FLAG_CLR = "\x1b[96m"
_PIPE_CLR = "\x1b[1;95m"
_KW_CLR = "\x1b[1;94m"
_OP_CLR = "\x1b[35m"
_LIB_CLR = "\x1b[36m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


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
        description="Updates every second with clear screen and -d flag",
        filename="live_clock.pl",
        code=(
            "# Run with -d to show date (Ctrl+C to stop)\n"
            "import time, ascii\n\n"
            "every 1 second\n"
            "    clear screen\n"
            "    print time --12h | ascii --size default colour cyan\n"
            "    if flag -d then print date below time\n\n"
            "flags: -d\n"
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
    "file",
    "files",
    "exists",
    "json",
    "parse",
    "parse_json",
    "to_json",
    "from_json",
    "choose",
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

_CHEAT_SHEET = """SayLang Quick Reference
───────────────────────
Comments     # inline or full-line   |   note prose comment
Variables    set score to 10         |   set name "Ada"
Math         plus  minus  times  divided by  modulo
Output       say "hi" colour red bold
             print time --12h | ascii --size default
Layout       print date below time   |   say "Hi" centered
             clear screen  |  wait 1 second  |  every 1 second
Flags        flags: -d, --name       |   if flag -d then ...
Loops        for each i from 1 to 5  |   repeat 3 times
Functions    to add with a and b     |   call add with 2, 3
Errors       try ... if it fails with err ...

nana Shortcuts
──────────────
Ctrl+S  Save      Ctrl+R  Run buffer    Ctrl+P  TUI Menu
Ctrl+K  Cut line  Ctrl+U  Paste line    Ctrl+G  Help
Ctrl+X  Exit"""


def _vis_len(text: str) -> int:
    return len(_ANSI_RE.sub("", text))


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

        out: list[str] = ["\x1b[H", f"{_INV}{header}{_RESET}\x1b[K\n"]

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

        footer = " ^S Save   ^R Run   ^P Menu   ^K Cut   ^U Paste   ^G Help   ^X Exit "
        out.append(f"{_INV}{footer[:cols].ljust(cols)}{_RESET}\x1b[K")

        cur_r = (self.row - self.scroll_y) + 2
        cur_c = gutter_w + (self.col - self.scroll_x) + 1
        out.append(f"\x1b[{cur_r};{cur_c}H")
        return "".join(out)


def _welcome_items(has_active_buffer: bool) -> list[tuple[str, str, str]]:
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
    items.extend(
        [
            ("learn", "Learn SayLang", "Interactive freeCodeCamp-style TUI course"),
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
) -> str:
    """Render the monochrome B&W `nana` welcome/launcher TUI screen."""
    rows = max(rows, 14)
    cols = max(cols, 44)
    items = _welcome_items(has_active_buffer)
    sel = max(0, min(selected, len(items) - 1))

    header = f" NANA · Saylang Studio v{__version__} "
    header_bar = f"{_INV}{header[:cols].ljust(cols)}{_RESET}"
    footer = " ↑/↓ Move   Enter Select   1-9 Quick Pick   Esc/q Quit "
    footer_bar = f"{_INV}{footer[:cols].ljust(cols)}{_RESET}"

    card = [
        f"  {_BOLD}╭─────────────╮{_RESET}   {_BOLD}NANA{_RESET}  {_DIM}Saylang v{__version__}{_RESET}",
        f"  {_BOLD}│ ╭─╮ ╭─╮ ╷ ╷ │{_RESET}   {_DIM}plain-english editor · .pl{_RESET}",
        f"  {_BOLD}│ ╰─╮ ├─┤ ╰┬╯ │{_RESET}   {_DIM}live syntax highlighting & runner{_RESET}",
        f"  {_BOLD}│ ╰─╯ ╵ ╵  ╵  │{_RESET}",
        f"  {_BOLD}╰─────────────╯{_RESET}",
    ]

    lines: list[str] = [header_bar, ""]
    lines.extend(card)
    lines.append("")

    for idx, (_key, title, desc) in enumerate(items):
        num = idx + 1
        raw_label = f"  {num}. {title:<21} {desc}"
        clipped = raw_label[: max(cols - 4, 20)]
        if idx == sel:
            row_str = f"  {_INV} ▸ {clipped.strip().ljust(max(cols - 8, 18))} {_RESET}"
        else:
            row_str = f"    {_BOLD}{num}. {title:<21}{_RESET} {_DIM}{desc}{_RESET}"
        lines.append(row_str)

    body_target = rows - 1
    while len(lines) < body_target:
        lines.append("")
    lines = lines[:body_target]
    lines.append(footer_bar)

    frame = "\x1b[H\x1b[?25l" + "\n".join(f"{ln}\x1b[K" for ln in lines)
    return frame


def render_template_picker(selected: int, rows: int, cols: int) -> str:
    """Render the template selector with live syntax-highlighted preview."""
    rows = max(rows, 14)
    cols = max(cols, 44)
    sel = max(0, min(selected, len(NANA_TEMPLATES) - 1))
    tpl = NANA_TEMPLATES[sel]

    header = " NANA · Start from Template "
    header_bar = f"{_INV}{header[:cols].ljust(cols)}{_RESET}"
    footer = " ↑/↓ Choose Template   Enter Open in Editor   Esc Back "
    footer_bar = f"{_INV}{footer[:cols].ljust(cols)}{_RESET}"

    body_rows = rows - 2
    preview_lines = tpl.code.rstrip("\n").split("\n")

    if cols >= 72:
        left_w = min(34, cols // 2 - 2)
        right_w = max(cols - left_w - 4, 20)
        out_rows: list[str] = [header_bar]

        left_col: list[str] = ["", f" {_BOLD}Templates{_RESET}", ""]
        for idx, item in enumerate(NANA_TEMPLATES):
            label = f"{idx + 1}. {item.title}"[: max(left_w - 4, 10)]
            if idx == sel:
                left_col.append(f" {_INV} ▸ {label.ljust(max(left_w - 5, 10))} {_RESET}")
            else:
                left_col.append(f"   {label}")
        left_col.extend(["", f" {_DIM}{tpl.description[:left_w - 2]}{_RESET}"])

        right_col: list[str] = [
            "",
            f" {_BOLD}Preview: {tpl.filename}{_RESET}",
            f" {_DIM}{'─' * min(right_w - 2, 42)}{_RESET}",
        ]
        for pline in preview_lines:
            right_col.append(" " + highlight_saylang_line(pline[: max(right_w - 2, 8)]))

        for r in range(body_rows):
            l_txt = left_col[r] if r < len(left_col) else ""
            r_txt = right_col[r] if r < len(right_col) else ""
            pad = " " * max(left_w - _vis_len(l_txt), 0)
            out_rows.append(f"{l_txt}{pad}{_GRAY}│{_RESET}{r_txt}")
        out_rows.append(footer_bar)
        return "\x1b[H\x1b[?25l" + "\n".join(f"{ln}\x1b[K" for ln in out_rows)

    # Narrow stacked view
    out_narrow: list[str] = [header_bar, ""]
    for idx, item in enumerate(NANA_TEMPLATES):
        label = f"{idx + 1}. {item.title}"
        if idx == sel:
            out_narrow.append(f" {_INV} ▸ {label} {_RESET}")
        else:
            out_narrow.append(f"   {label}")
    out_narrow.extend(["", f" {_BOLD}Preview ({tpl.filename}):{_RESET}"])
    for pline in preview_lines[: max(body_rows - len(out_narrow), 2)]:
        out_narrow.append(" " + highlight_saylang_line(pline[: max(cols - 2, 10)]))
    while len(out_narrow) < rows - 1:
        out_narrow.append("")
    out_narrow = out_narrow[: rows - 1]
    out_narrow.append(footer_bar)
    return "\x1b[H\x1b[?25l" + "\n".join(f"{ln}\x1b[K" for ln in out_narrow)


def render_file_picker(
    files: list[Path],
    selected: int,
    rows: int,
    cols: int,
    root: Path | None = None,
) -> str:
    """Render `.pl` file browser with live syntax-highlighted preview."""
    rows = max(rows, 14)
    cols = max(cols, 44)
    base = (root or Path.cwd()).resolve()
    total = len(files) + 1  # last entry = custom path
    sel = max(0, min(selected, total - 1))

    header = f" NANA · Open .pl File ({base.name}) "
    header_bar = f"{_INV}{header[:cols].ljust(cols)}{_RESET}"
    footer = " ↑/↓ Select   Enter Open   / Type Path   Esc Back "
    footer_bar = f"{_INV}{footer[:cols].ljust(cols)}{_RESET}"

    body_rows = rows - 2
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
                chosen.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")[:25]
            )
        except OSError as exc:
            preview_lines = [f"(Cannot read file: {exc})"]

    left_w = min(36, cols // 2 - 2) if cols >= 72 else cols
    list_rows_cap = max(body_rows - 4, 4)
    scroll = max(0, sel - list_rows_cap + 1)

    if cols >= 72:
        right_w = max(cols - left_w - 4, 20)
        left_col: list[str] = ["", f" {_BOLD}.pl Files{_RESET}", ""]
        for idx in range(scroll, min(len(labels), scroll + list_rows_cap)):
            lbl = labels[idx][: max(left_w - 5, 8)]
            if idx == sel:
                left_col.append(f" {_INV} ▸ {lbl.ljust(max(left_w - 5, 8))} {_RESET}")
            else:
                left_col.append(f"   {lbl}")

        right_col: list[str] = [
            "",
            f" {_BOLD}Preview: {preview_title}{_RESET}",
            f" {_DIM}{'─' * min(right_w - 2, 42)}{_RESET}",
        ]
        for pline in preview_lines:
            right_col.append(" " + highlight_saylang_line(pline[: max(right_w - 2, 8)]))

        out_rows = [header_bar]
        for r in range(body_rows):
            l_txt = left_col[r] if r < len(left_col) else ""
            r_txt = right_col[r] if r < len(right_col) else ""
            pad = " " * max(left_w - _vis_len(l_txt), 0)
            out_rows.append(f"{l_txt}{pad}{_GRAY}│{_RESET}{r_txt}")
        out_rows.append(footer_bar)
        return "\x1b[H\x1b[?25l" + "\n".join(f"{ln}\x1b[K" for ln in out_rows)

    out_narrow = [header_bar, ""]
    for idx in range(scroll, min(len(labels), scroll + list_rows_cap)):
        lbl = labels[idx][: max(cols - 6, 10)]
        if idx == sel:
            out_narrow.append(f" {_INV} ▸ {lbl} {_RESET}")
        else:
            out_narrow.append(f"   {lbl}")
    while len(out_narrow) < rows - 1:
        out_narrow.append("")
    out_narrow = out_narrow[: rows - 1]
    out_narrow.append(footer_bar)
    return "\x1b[H\x1b[?25l" + "\n".join(f"{ln}\x1b[K" for ln in out_narrow)


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


def _prompt_bar(
    label: str, default: str = "", *, buf: NanaBuffer | None = None
) -> str | None:
    """Inline single-line prompt on the bottom status line."""
    val = default
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        if buf is not None:
            buf.status = ""
            sys.stdout.write(buf.render_frame(rows, cols))
        prompt_row = rows - 1 if buf is not None else rows
        prompt_col = min(len(label) + len(val) + 2, cols)
        sys.stdout.write(
            f"\x1b[{prompt_row};1H\x1b[?25h{_INV} {label}{val} {_RESET}\x1b[K"
            f"\x1b[{prompt_row};{prompt_col + 1}H"
        )
        sys.stdout.flush()
        key = _read_key()
        if key in ("\r", "\n"):
            return val.strip()
        if key in ("ESC", "\x03"):
            return None
        if key in ("\x7f", "\x08"):
            val = val[:-1]
        elif len(key) == 1 and key.isprintable():
            val += key


def _show_overlay(title: str, body: str) -> None:
    """Display output or help overlay inside the alternate screen."""
    cols, rows = shutil.get_terminal_size((80, 24))
    sys.stdout.write("\x1b[H\x1b[2J\x1b[?25l")
    sys.stdout.write(f"{_INV} {title.ljust(max(cols - 1, 1))}{_RESET}\n\n")
    lines = body.splitlines() or ["(no output)"]
    for line in lines[: max(rows - 5, 1)]:
        sys.stdout.write(line + "\n")
    sys.stdout.write(
        f"\n\x1b[{rows};1H{_INV} Press any key to return to nana... {_RESET}"
    )
    sys.stdout.flush()
    _read_key()


def _run_buffer(buf: NanaBuffer, cli_args: list[str] | None = None) -> None:
    out_buf = io.StringIO()
    try:
        run_source(buf.text, stdout=out_buf, cli_args=cli_args)
        output = out_buf.getvalue() or "(finished with no output)"
    except SayError as err:
        output = err.format_pretty(str(buf.filepath) if buf.filepath else "<nana>")
    _show_overlay("Run Output (SayLang)", output)


def _select_template_tui() -> NanaBuffer | None:
    sel = 0
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        sys.stdout.write(render_template_picker(sel, rows, cols))
        sys.stdout.flush()
        key = _read_key()
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


def _select_file_tui() -> NanaBuffer | None:
    root = Path.cwd().resolve()
    files = discover_pl_files(root)
    sel = 0
    total = len(files) + 1
    while True:
        cols, rows = shutil.get_terminal_size((80, 24))
        sys.stdout.write(render_file_picker(files, sel, rows, cols, root))
        sys.stdout.flush()
        key = _read_key()
        if key == "UP":
            sel = (sel - 1) % total
        elif key == "DOWN":
            sel = (sel + 1) % total
        elif key == "/":
            custom = _prompt_bar("Open file path: ")
            if custom:
                return NanaBuffer.from_file(custom)
        elif key in ("\r", "\n"):
            if sel < len(files):
                return NanaBuffer.from_file(str(files[sel]))
            custom = _prompt_bar("Open file path: ")
            if custom:
                return NanaBuffer.from_file(custom)
        elif key in ("ESC", "q", "\x03"):
            return None


def _run_menu_tui(active_buf: NanaBuffer | None) -> tuple[str, NanaBuffer | None]:
    """Show the main nana launcher/menu TUI. Returns ('edit', buf) or ('quit', None)."""
    sel = 0
    while True:
        items = _welcome_items(active_buf is not None)
        sel = max(0, min(sel, len(items) - 1))
        cols, rows = shutil.get_terminal_size((80, 24))
        sys.stdout.write(
            render_welcome_menu(sel, rows, cols, has_active_buffer=active_buf is not None)
        )
        sys.stdout.flush()
        key = _read_key()

        chosen_action: str | None = None
        if key == "UP":
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
            fname = _prompt_bar("New file name (Enter for untitled): ")
            if fname is None:
                continue
            buf = NanaBuffer(lines=[""], filepath=Path(fname) if fname else None)
            return ("edit", buf)
        if chosen_action == "template":
            buf = _select_template_tui()
            if buf is not None:
                return ("edit", buf)
        if chosen_action == "open":
            buf = _select_file_tui()
            if buf is not None:
                return ("edit", buf)
        if chosen_action == "run_flags" and active_buf is not None:
            raw_flags = _prompt_bar("Flags (e.g. -d): ")
            if raw_flags is not None:
                try:
                    parsed_flags = shlex.split(raw_flags)
                except ValueError:
                    parsed_flags = raw_flags.split()
                _run_buffer(active_buf, cli_args=parsed_flags)
                return ("edit", active_buf)
        if chosen_action == "learn":
            from saylang.learn import run_learn

            run_learn()
        if chosen_action == "cheat":
            _show_overlay("SayLang Cheat Sheet", _CHEAT_SHEET)
        if chosen_action == "quit":
            if active_buf is not None and active_buf.modified:
                ans = _prompt_bar("Unsaved changes — save before quit? (y/n/c): ")
                if ans is None or ans.lower().startswith("c"):
                    continue
                if ans.lower().startswith("y"):
                    if active_buf.filepath is None:
                        fname = _prompt_bar("Save as: ", "untitled.pl")
                        if not fname:
                            continue
                        active_buf.save(Path(fname))
                    else:
                        active_buf.save()
            return ("quit", None)


def run_nana(filepath: str | None = None) -> int:
    """Launch the interactive `nana` SayLang TUI studio & editor."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("nana requires an interactive terminal.", file=sys.stderr)
        return 1

    runtime._enable_windows_ansi()
    buf: NanaBuffer | None = NanaBuffer.from_file(filepath) if filepath else None

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

        if buf is None:
            action, buf = _run_menu_tui(None)
            if action == "quit" or buf is None:
                return 0

        while True:
            cols, rows = shutil.get_terminal_size((80, 24))
            sys.stdout.write("\x1b[?25h" + buf.render_frame(rows, cols))
            sys.stdout.flush()

            key = _read_key()
            buf.status = ""

            if key == "\x10":  # Ctrl+P -> TUI Menu
                action, next_buf = _run_menu_tui(buf)
                if action == "quit":
                    return 0
                if next_buf is not None:
                    buf = next_buf
                continue

            if key in ("\x18", "\x11"):  # Ctrl+X or Ctrl+Q
                if buf.modified:
                    ans = _prompt_bar("Save modified buffer? (y/n/c): ", buf=buf)
                    if ans is None or ans.lower().startswith("c"):
                        continue
                    if ans.lower().startswith("y"):
                        if buf.filepath is None:
                            fname = _prompt_bar("File name to save: ", "untitled.pl", buf=buf)
                            if not fname:
                                continue
                            buf.save(Path(fname))
                        else:
                            buf.save()
                return 0

            if key in ("\x13", "\x0f"):  # Ctrl+S or Ctrl+O
                if buf.filepath is None:
                    fname = _prompt_bar("Save as: ", "untitled.pl", buf=buf)
                    if fname:
                        buf.save(Path(fname))
                else:
                    buf.save()
                continue

            if key == "\x12":  # Ctrl+R Run
                _run_buffer(buf)
                continue

            if key == "\x07":  # Ctrl+G Help
                _show_overlay("SayLang & nana Help", _CHEAT_SHEET)
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
        sys.stdout.write("\x1b[?1049l\x1b[?25h\x1b[0m")
        sys.stdout.flush()
        if old_attrs is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
