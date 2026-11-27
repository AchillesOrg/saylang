"""Shared runtime helpers used by both the SayLang interpreter and transpiler."""

from __future__ import annotations

from saylang.errors import SayRuntimeError

# --- SAYLANG RUNTIME START ---
import datetime
import json
import math
import os
import random
import re
import shutil
import sys
import time as _time
from pathlib import Path

try:
    SayRuntimeError  # type: ignore[used-before-def]
except NameError:

    class SayRuntimeError(Exception):
        """Runtime error raised by standalone compiled SayLang programs."""

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


_ANSI_INITIALIZED = False
_CLI_ARGS: list[str] | None = None
_LAST_PRINT_WIDTH = 0
_ANSI_STRIP_RE = re.compile(r"\x1b\[[0-9;]*m")

_PREBUILT_LIBS = {
    "time",
    "ascii",
    "color",
    "colour",
    "text",
    "math",
    "sys",
    "flags",
    "tty",
    "tui",
    "ui",
    "json",
    "files",
}

AUTO_LIB_VALUES = {
    "time",
    "date",
    "hour",
    "minute",
    "second",
    "year",
    "month",
    "day",
    "weekday",
    "cwd",
    "os",
    "args",
    "terminal_width",
    "terminal_height",
    "divider",
    "rule",
}

_FG_COLORS: dict[str, str] = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "purple": "35",
    "cyan": "36",
    "white": "37",
    "gray": "90",
    "grey": "90",
    "orange": "38;5;208",
    "pink": "38;5;213",
    "bright black": "90",
    "bright red": "91",
    "bright green": "92",
    "bright yellow": "93",
    "bright blue": "94",
    "bright magenta": "95",
    "bright purple": "95",
    "bright cyan": "96",
    "bright white": "97",
    "bright gray": "37",
    "bright grey": "37",
    "bright orange": "38;5;214",
    "bright pink": "38;5;219",
}

_BG_COLORS: dict[str, str] = {
    "black": "40",
    "red": "41",
    "green": "42",
    "yellow": "43",
    "blue": "44",
    "magenta": "45",
    "purple": "45",
    "cyan": "46",
    "white": "47",
    "gray": "100",
    "grey": "100",
    "orange": "48;5;208",
    "pink": "48;5;213",
    "bright black": "100",
    "bright red": "101",
    "bright green": "102",
    "bright yellow": "103",
    "bright blue": "104",
    "bright magenta": "105",
    "bright purple": "105",
    "bright cyan": "106",
    "bright white": "107",
    "bright gray": "47",
    "bright grey": "47",
    "bright orange": "48;5;214",
    "bright pink": "48;5;219",
}

_TEXT_STYLES: dict[str, str] = {
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
}

_ASCII_FONT_5: dict[str, tuple[str, ...]] = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": (" ██", "  █", "  █", "  █", "███"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ":": (" ", "█", " ", "█", " "),
    "-": ("   ", "   ", "███", "   ", "   "),
    "/": ("  █", "  █", " █ ", "█  ", "█  "),
    ".": (" ", " ", " ", " ", "█"),
    ",": ("  ", "  ", "  ", " █", "█ "),
    "!": ("█", "█", "█", " ", "█"),
    "?": ("███", "  █", " ██", "   ", " █ "),
    " ": ("  ", "  ", "  ", "  ", "  "),
    "A": ("███", "█ █", "███", "█ █", "█ █"),
    "B": ("██ ", "█ █", "██ ", "█ █", "██ "),
    "C": ("███", "█  ", "█  ", "█  ", "███"),
    "D": ("██ ", "█ █", "█ █", "█ █", "██ "),
    "E": ("███", "█  ", "██ ", "█  ", "███"),
    "F": ("███", "█  ", "██ ", "█  ", "█  "),
    "G": ("███", "█  ", "█ █", "█ █", "███"),
    "H": ("█ █", "█ █", "███", "█ █", "█ █"),
    "I": ("███", " █ ", " █ ", " █ ", "███"),
    "J": ("  █", "  █", "  █", "█ █", "███"),
    "K": ("█ █", "█ █", "██ ", "█ █", "█ █"),
    "L": ("█  ", "█  ", "█  ", "█  ", "███"),
    "M": ("█   █", "██ ██", "█ █ █", "█   █", "█   █"),
    "N": ("█  █", "██ █", "█ ██", "█  █", "█  █"),
    "O": ("███", "█ █", "█ █", "█ █", "███"),
    "P": ("███", "█ █", "███", "█  ", "█  "),
    "Q": ("███", "█ █", "█ █", "███", "  █"),
    "R": ("██ ", "█ █", "██ ", "█ █", "█ █"),
    "S": ("███", "█  ", "███", "  █", "███"),
    "T": ("███", " █ ", " █ ", " █ ", " █ "),
    "U": ("█ █", "█ █", "█ █", "█ █", "███"),
    "V": ("█ █", "█ █", "█ █", "█ █", " █ "),
    "W": ("█   █", "█   █", "█ █ █", "██ ██", "█   █"),
    "X": ("█ █", "█ █", " █ ", "█ █", "█ █"),
    "Y": ("█ █", "█ █", " █ ", " █ ", " █ "),
    "Z": ("███", "  █", " █ ", "█  ", "███"),
}

_ASCII_FONT_3: dict[str, tuple[str, ...]] = {
    "0": ("▄▀▄", "█ █", "▀▄▀"),
    "1": ("▄█ ", " █ ", "▄█▄"),
    "2": ("▀▀█", "▄▀ ", "█▄▄"),
    "3": ("▀▀█", " ▀▄", "▄▄▀"),
    "4": ("█ █", "▀▀█", "  █"),
    "5": ("█▀▀", "▀▀▄", "▄▄▀"),
    "6": ("▄▀ ", "█▀▄", "▀▄▀"),
    "7": ("▀▀█", "  █", "  █"),
    "8": ("▄▀▄", "█▀█", "▀▄▀"),
    "9": ("▄▀▄", "▀▀█", " ▄▀"),
    ":": (" ", "▄", "▀"),
    "-": ("  ", "▀▀", "  "),
    " ": (" ", " ", " "),
    "A": ("▄▀▄", "█▀█", "█ █"),
    "P": ("█▀▄", "█▀ ", "█  "),
    "M": ("█▄█", "█▀█", "█ █"),
}


def say_configure_utf8_stdio() -> None:
    """Reconfigure standard output and error streams to UTF-8 on Windows/pipes."""
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _enable_windows_ansi() -> None:
    """Best-effort enablement of ANSI VT100 escapes and UTF-8 on Windows terminals."""
    global _ANSI_INITIALIZED
    say_configure_utf8_stdio()
    if _ANSI_INITIALIZED or sys.platform != "win32":
        _ANSI_INITIALIZED = True
        return
    _ANSI_INITIALIZED = True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def say_set_cli_args(args: list[str]) -> None:
    """Store CLI arguments forwarded to the SayLang program."""
    global _CLI_ARGS
    _CLI_ARGS = list(args)


def say_cli_args() -> list[str]:
    """Return forwarded CLI arguments as a list of strings."""
    return list(sys.argv[1:] if _CLI_ARGS is None else _CLI_ARGS)


def say_get_flag(name: str) -> object:
    """Read a CLI flag (`-d`, `--12h`, `--size`) from program arguments."""
    args = sys.argv[1:] if _CLI_ARGS is None else _CLI_ARGS
    prefix = f"{name}="
    for idx, arg in enumerate(args):
        if arg == name:
            if idx + 1 < len(args) and not args[idx + 1].startswith("-"):
                return args[idx + 1]
            return True
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return False


def say_import_modules(names: list[str]) -> None:
    """Validate prebuilt SayLang library imports."""
    for mod in names:
        key = mod.strip().lower()
        if key not in _PREBUILT_LIBS:
            available = ", ".join(sorted(_PREBUILT_LIBS))
            raise SayRuntimeError(
                f"Unknown prebuilt library '{mod}'. Available libraries: {available}."
            )


def say_clear_screen(stdout: object = None) -> None:
    """Clear the terminal screen."""
    _enable_windows_ansi()
    out = stdout if stdout is not None else sys.stdout
    out.write("\x1b[2J\x1b[H")  # type: ignore[attr-defined]
    flush = getattr(out, "flush", None)
    if callable(flush):
        flush()


def say_sleep(seconds: object) -> None:
    """Pause execution for `seconds`."""
    if not _is_number(seconds):
        raise SayRuntimeError(
            f"Wait duration must be a number, got {say_type_of(seconds)}."
        )
    if float(seconds) < 0:  # type: ignore[arg-type]
        raise SayRuntimeError("Wait duration cannot be negative.")
    _time.sleep(float(seconds))  # type: ignore[arg-type]


def _visible_width(text: str) -> int:
    clean = _ANSI_STRIP_RE.sub("", text)
    lines = clean.splitlines()
    return max((len(line) for line in lines), default=0)


def say_record_print(text: str) -> None:
    """Record the visible width of the most recently printed block."""
    global _LAST_PRINT_WIDTH
    _LAST_PRINT_WIDTH = _visible_width(text)


def say_format_layout(text: str, position: str | None = None) -> str:
    """Align text `below` the previous block or `centered` in the terminal."""
    if position is None:
        return text
    lines = text.splitlines()
    if not lines:
        return text
    if position == "below":
        target = _LAST_PRINT_WIDTH
        if target <= _visible_width(text):
            return text
    elif position == "centered":
        target = shutil.get_terminal_size((80, 24)).columns
    else:
        return text

    padded: list[str] = []
    for line in lines:
        vis = _visible_width(line)
        if vis < target:
            left_pad = (target - vis) // 2
            padded.append((" " * left_pad) + line)
        else:
            padded.append(line)
    return "\n".join(padded)


def say_ascii_art(value: object, size: object = "default") -> str:
    """Render text as multi-line big block letters."""
    text = say_to_text(value)
    size_key = str(size).strip().lower()
    if size_key not in ("small", "default", "big"):
        raise SayRuntimeError(
            f"Unknown ascii --size '{size}'. Choose: small, default, big."
        )

    upper = text.upper()
    if size_key == "small":
        rows = ["", "", ""]
        for ch in upper:
            glyph = _ASCII_FONT_3.get(ch)
            if glyph is None:
                fallback = _ASCII_FONT_5.get(ch, ("  ", "  ", "  ", "  ", "  "))
                glyph = (fallback[0], fallback[2], fallback[4])
            for r in range(3):
                rows[r] += glyph[r] + " "
        return "\n".join(row.rstrip() for row in rows)

    rows5 = ["", "", "", "", ""]
    for ch in upper:
        glyph5 = _ASCII_FONT_5.get(ch, ("  ", "  ", "  ", "  ", "  "))
        for r in range(5):
            rows5[r] += glyph5[r] + " "
    lines5 = [row.rstrip() for row in rows5]

    if size_key == "default":
        return "\n".join(lines5)

    # big: 2x wider + 7 rows tall
    widened = ["".join(ch * 2 for ch in line) for line in lines5]
    return "\n".join(
        [
            widened[0],
            widened[0],
            widened[1],
            widened[2],
            widened[3],
            widened[4],
            widened[4],
        ]
    )


def say_cursor(visible: bool, stdout: object = None) -> None:
    """Show or hide the terminal cursor."""
    _enable_windows_ansi()
    out = stdout if stdout is not None else sys.stdout
    out.write("\x1b[?25h" if visible else "\x1b[?25l")  # type: ignore[attr-defined]
    flush = getattr(out, "flush", None)
    if callable(flush):
        flush()


def say_box(value: object, title: object = None, width: object = None) -> str:
    """Wrap text in a clean rounded Unicode border box."""
    lines = say_to_text(value).splitlines() or [""]
    inner_w = max(_visible_width(line) for line in lines)
    if width is not None and _is_number(width):
        inner_w = max(inner_w, int(width))  # type: ignore[arg-type]
    if title is not None:
        title_str = f" {say_to_text(title)} "
        inner_w = max(inner_w, len(title_str))
        top = "╭" + title_str + "─" * max(inner_w + 2 - len(title_str), 0) + "╮"
    else:
        top = "╭" + "─" * (inner_w + 2) + "╮"
    bottom = "╰" + "─" * (inner_w + 2) + "╯"
    body = [f"│ {line}{' ' * max(inner_w - _visible_width(line), 0)} │" for line in lines]
    return "\n".join([top, *body, bottom])


def say_bar(
    value: object,
    total: object = 100,
    width: object = 20,
    label: object = None,
) -> str:
    """Render a clean Unicode progress bar (`[████████░░] 80%`)."""
    if not _is_number(value):
        raise SayRuntimeError(
            f"Progress bar value must be a number, got {say_type_of(value)}."
        )
    tot_num = 100.0 if total is None else float(total)  # type: ignore[arg-type]
    if total is not None and not _is_number(total):
        raise SayRuntimeError(
            f"Progress bar total must be a number, got {say_type_of(total)}."
        )
    if tot_num <= 0:
        raise SayRuntimeError("Progress bar total must be greater than zero.")
    bar_w = int(width) if width is not None and _is_number(width) else 20  # type: ignore[arg-type]
    bar_w = max(bar_w, 4)

    ratio = max(0.0, min(1.0, float(value) / tot_num))  # type: ignore[arg-type]
    filled = int(round(ratio * bar_w))
    pct = int(round(ratio * 100))
    bar_str = f"[{'█' * filled}{'░' * (bar_w - filled)}] {pct}%"
    if label is not None and str(label):
        return f"{say_to_text(label)} {bar_str}"
    return bar_str


def say_rule(width: object = None, title: object = None) -> str:
    """Render a crisp terminal horizontal rule / divider."""
    term_w = shutil.get_terminal_size((80, 24)).columns
    w = int(width) if width is not None and _is_number(width) else min(term_w, 48)  # type: ignore[arg-type]
    w = max(w, 6)
    if title is None or not str(title):
        return "─" * w
    t = f" {say_to_text(title)} "
    if len(t) >= w:
        return t
    left = (w - len(t)) // 2
    right = w - len(t) - left
    return f"{'─' * left}{t}{'─' * right}"


def say_table(rows: object) -> str:
    """Render a list of maps or lists as a rounded Unicode terminal table."""
    if not isinstance(rows, list):
        raise SayRuntimeError(
            f"Table expects a list of rows, got {say_type_of(rows)}."
        )
    if not rows:
        return "(empty table)"

    headers: list[str] = []
    str_rows: list[list[str]] = []

    if all(isinstance(r, dict) for r in rows):
        seen: set[object] = set()
        raw_keys: list[object] = []
        for r in rows:
            for k in r:  # type: ignore[union-attr]
                if k not in seen:
                    seen.add(k)
                    raw_keys.append(k)
        headers = [say_to_text(k) for k in raw_keys]
        for r in rows:
            str_rows.append(
                [say_to_text(r.get(k, "")) for k in raw_keys]  # type: ignore[union-attr]
            )
    elif all(isinstance(r, list) for r in rows):
        col_count = max(len(r) for r in rows)  # type: ignore[arg-type]
        if col_count == 0:
            return "(empty table)"
        headers = [f"Col {i + 1}" for i in range(col_count)]
        for r in rows:
            padded = [say_to_text(r[i]) if i < len(r) else "" for i in range(col_count)]  # type: ignore[index, arg-type]
            str_rows.append(padded)
    else:
        headers = ["Value"]
        str_rows = [[say_to_text(r)] for r in rows]

    widths = [len(h) for h in headers]
    for r in str_rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], _visible_width(cell))

    def fmt_row(cells: list[str]) -> str:
        parts = [
            f" {c}{' ' * max(widths[i] - _visible_width(c), 0)} "
            for i, c in enumerate(cells)
        ]
        return "│" + "│".join(parts) + "│"

    top = "╭" + "┬".join("─" * (w + 2) for w in widths) + "╮"
    mid = "├" + "┼".join("─" * (w + 2) for w in widths) + "┤"
    bot = "╰" + "┴".join("─" * (w + 2) for w in widths) + "╯"
    lines = [top, fmt_row(headers), mid, *(fmt_row(r) for r in str_rows), bot]
    return "\n".join(lines)


def say_to_json(val: object, pretty: bool = True) -> str:
    """Serialize a SayLang value to JSON text."""
    try:
        return json.dumps(val, indent=2 if pretty else None, ensure_ascii=False)
    except TypeError as exc:
        raise SayRuntimeError(f"Cannot convert value to JSON: {exc}") from exc


def say_from_json(text: object) -> object:
    """Parse JSON text into SayLang values."""
    if not isinstance(text, str):
        raise SayRuntimeError(f"parse json expects text, got {say_type_of(text)}.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise SayRuntimeError(f"Invalid JSON: {exc.msg}") from exc


def say_file_exists(path: object) -> bool:
    """Return True if a file or directory exists at `path`."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    return Path(path).exists()


def say_list_files(dirpath: object = ".") -> list[str]:
    """Return sorted file/entry names inside `dirpath`."""
    if not isinstance(dirpath, str):
        raise SayRuntimeError("Directory path must be text.")
    target = Path(dirpath)
    if not target.is_dir():
        raise SayRuntimeError(f"Directory not found: '{dirpath}'.")
    return sorted(p.name for p in target.iterdir())


def say_split(text: object, sep: object = None) -> list[str]:
    """Split text into a list using an optional separator."""
    if not isinstance(text, str):
        raise SayRuntimeError(f"Cannot split {say_type_of(text)}.")
    if sep is None:
        return text.split()
    if not isinstance(sep, str):
        raise SayRuntimeError("Split separator must be text.")
    if sep == "":
        return list(text)
    return text.split(sep)


def say_replace(text: object, old: object, new: object) -> str:
    """Replace occurrences of `old` with `new` in `text`."""
    if not isinstance(text, str):
        raise SayRuntimeError(f"Cannot replace in {say_type_of(text)}.")
    if not isinstance(old, str) or not isinstance(new, str):
        raise SayRuntimeError("replace expects text arguments.")
    return text.replace(old, new)


def say_unique(items: object) -> list[object]:
    """Return a copy of `items` with duplicates removed while preserving order."""
    if not isinstance(items, list):
        raise SayRuntimeError(f"Cannot deduplicate {say_type_of(items)}.")
    out: list[object] = []
    for item in items:
        if not any(_say_equals(existing, item) for existing in out):
            out.append(item)
    return out


def say_pad(text: object, width: object = 10, align: object = "left") -> str:
    """Pad text to a minimum visible width."""
    s = say_to_text(text)
    if not _is_number(width):
        raise SayRuntimeError("Pad width must be a number.")
    w = max(int(width), 0)  # type: ignore[arg-type]
    gap = max(w - _visible_width(s), 0)
    mode = str(align).strip().lower()
    if mode == "right":
        return (" " * gap) + s
    if mode in ("center", "centre"):
        left = gap // 2
        return (" " * left) + s + (" " * (gap - left))
    return s + (" " * gap)


def say_read_key(input_fn: object = None) -> str:
    """Read a single keypress (`up`, `down`, `left`, `right`, `enter`, `esc`, or char)."""
    if input_fn is not None or not (sys.stdin.isatty() and sys.stdout.isatty()):
        fn = input_fn if callable(input_fn) else input
        raw = str(fn(""))
        norm = raw.strip().lower()
        if norm in ("", "enter", "return"):
            return "enter"
        if norm in ("up", "down", "left", "right", "esc", "space", "backspace"):
            return norm
        return raw[0] if raw else "enter"

    if sys.platform == "win32":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {"H": "up", "P": "down", "K": "left", "M": "right"}.get(code, "")
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x1b":
            return "esc"
        if ch == " ":
            return "space"
        if ch in ("\x7f", "\x08"):
            return "backspace"
        return ch

    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch_b = os.read(fd, 1)
        ch = ch_b.decode("utf-8", errors="replace")
        if ch == "\x1b":
            if select.select([fd], [], [], 0.05)[0]:
                nxt = os.read(fd, 1).decode("utf-8", errors="replace")
                if nxt in ("[", "O") and select.select([fd], [], [], 0.05)[0]:
                    code = os.read(fd, 1).decode("utf-8", errors="replace")
                    return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(
                        code, "esc"
                    )
            return "esc"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == " ":
            return "space"
        if ch in ("\x7f", "\x08"):
            return "backspace"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def say_choose(
    options: object,
    prompt: object = None,
    input_fn: object = None,
    stdout: object = None,
) -> object:
    """Present an interactive arrow-key chooser (or numbered prompt when piped)."""
    if not isinstance(options, list) or not options:
        raise SayRuntimeError("choose expects a non-empty list of options.")
    out = stdout if stdout is not None else sys.stdout
    title = say_to_text(prompt) if prompt is not None else "Choose an option:"

    if input_fn is None and sys.stdin.isatty() and sys.stdout.isatty():
        _enable_windows_ansi()
        labels = [say_to_text(opt) for opt in options]
        sel = 0
        out.write(title + "\n\x1b[?25l")  # type: ignore[attr-defined]
        first = True
        try:
            while True:
                if not first:
                    out.write(f"\x1b[{len(labels)}A")  # type: ignore[attr-defined]
                first = False
                for idx, lbl in enumerate(labels):
                    if idx == sel:
                        out.write(f"\r\x1b[K  \x1b[7m ▸ {idx + 1}. {lbl} \x1b[0m\n")  # type: ignore[attr-defined]
                    else:
                        out.write(f"\r\x1b[K     {idx + 1}. {lbl}\n")  # type: ignore[attr-defined]
                flush = getattr(out, "flush", None)
                if callable(flush):
                    flush()
                k = say_read_key()
                if k == "up":
                    sel = (sel - 1) % len(labels)
                elif k == "down":
                    sel = (sel + 1) % len(labels)
                elif k == "enter":
                    return options[sel]
                elif k.isdigit() and 1 <= int(k) <= len(labels):
                    return options[int(k) - 1]
                elif k == "esc":
                    return options[sel]
        finally:
            out.write("\x1b[?25h")  # type: ignore[attr-defined]
            flush = getattr(out, "flush", None)
            if callable(flush):
                flush()

    out.write(title + "\n")  # type: ignore[attr-defined]
    for idx, opt in enumerate(options, start=1):
        out.write(f"  {idx}. {say_to_text(opt)}\n")  # type: ignore[attr-defined]
    flush = getattr(out, "flush", None)
    if callable(flush):
        flush()
    fn = input_fn if callable(input_fn) else input
    raw = str(fn("> ")).strip()
    if not raw:
        return options[0]
    if raw.isdigit():
        num = int(raw)
        if 1 <= num <= len(options):
            return options[num - 1]
    for opt in options:
        if say_to_text(opt).strip().lower() == raw.lower():
            return opt
    raise SayRuntimeError(
        f"Invalid choice '{raw}'. Enter a number from 1 to {len(options)}."
    )


def say_center(value: object, width: object = None) -> str:
    """Center text horizontally."""
    target = (
        int(width)
        if width is not None and _is_number(width)
        else shutil.get_terminal_size((80, 24)).columns
    )
    lines = say_to_text(value).splitlines() or [""]
    out: list[str] = []
    for line in lines:
        vis = _visible_width(line)
        pad = max((target - vis) // 2, 0)
        out.append((" " * pad) + line)
    return "\n".join(out)


def _flag_enabled(options: dict[str, object], *keys: str) -> bool:
    for key in keys:
        if key in options and say_is_truthy(options[key]):
            return True
    return False


def say_lib_time(options: dict[str, object] | None = None) -> str:
    """Return formatted current local time."""
    opts = options or {}
    now = datetime.datetime.now()
    if "format" in opts and isinstance(opts["format"], str):
        return now.strftime(opts["format"])
    no_sec = _flag_enabled(opts, "no-seconds", "short")
    if _flag_enabled(opts, "12h", "12"):
        return now.strftime("%I:%M %p" if no_sec else "%I:%M:%S %p")
    return now.strftime("%H:%M" if no_sec else "%H:%M:%S")


def say_lib_date(options: dict[str, object] | None = None) -> str:
    """Return formatted current local date."""
    opts = options or {}
    now = datetime.datetime.now()
    if "format" in opts and isinstance(opts["format"], str):
        return now.strftime(opts["format"])
    if _flag_enabled(opts, "iso"):
        return now.strftime("%Y-%m-%d")
    if _flag_enabled(opts, "short"):
        return now.strftime("%d/%m/%Y")
    if _flag_enabled(opts, "long"):
        return now.strftime("%A, %B %d, %Y")
    return now.strftime("%a, %b %d %Y")


def say_lib_call(
    name: str,
    args: list[object] | None = None,
    options: dict[str, object] | None = None,
) -> object:
    """Invoke a prebuilt SayLang standard library command."""
    key = name.strip().lower()
    arg_list = args or []
    opts = options or {}
    now = datetime.datetime.now()

    if key == "time":
        return say_lib_time(opts)
    if key == "date":
        return say_lib_date(opts)
    if key == "hour":
        return now.hour
    if key == "minute":
        return now.minute
    if key == "second":
        return now.second
    if key == "year":
        return now.year
    if key == "month":
        return now.month
    if key == "day":
        return now.day
    if key == "weekday":
        return now.strftime("%A")
    if key == "cwd":
        return os.getcwd()
    if key == "os":
        return sys.platform
    if key == "args":
        return say_cli_args()
    if key in ("terminal_width", "width"):
        return shutil.get_terminal_size((80, 24)).columns
    if key in ("terminal_height", "height"):
        return shutil.get_terminal_size((80, 24)).lines
    if key in ("rule", "divider"):
        return say_rule(opts.get("width"), opts.get("title") or (arg_list[0] if arg_list else None))
    if key == "bar":
        val = arg_list[0] if arg_list else 0
        total = opts.get("of", opts.get("max", 100))
        return say_bar(val, total=total, width=opts.get("width", 20), label=opts.get("label"))
    if key == "table":
        val = arg_list[0] if arg_list else []
        return say_table(val)
    if key == "env":
        if not arg_list:
            raise SayRuntimeError("env expects a variable name.")
        return os.environ.get(say_to_text(arg_list[0]), "")
    if key == "ascii":
        val = arg_list[0] if arg_list else ""
        return say_ascii_art(val, opts.get("size", "default"))
    if key == "box":
        val = arg_list[0] if arg_list else ""
        return say_box(val, opts.get("title"), opts.get("width"))
    if key == "center":
        val = arg_list[0] if arg_list else ""
        return say_center(val, opts.get("width"))
    if key in ("sum", "min", "max", "average"):
        items = arg_list[0] if len(arg_list) == 1 and isinstance(arg_list[0], list) else arg_list
        if not isinstance(items, list) or not items:
            raise SayRuntimeError(f"{key} expects a non-empty list of numbers.")
        if key == "sum":
            return sum(items)  # type: ignore[arg-type]
        if key == "min":
            return min(items)  # type: ignore[type-var]
        if key == "max":
            return max(items)  # type: ignore[type-var]
        return sum(items) / len(items)  # type: ignore[arg-type]

    raise SayRuntimeError(f"Unknown standard library command '{name}'.")


def say_pipe(
    value: object,
    stage_name: str,
    args: list[object] | None = None,
    options: dict[str, object] | None = None,
    user_fn: object = None,
) -> object:
    """Apply a `|` pipe stage to a value."""
    if callable(user_fn):
        return user_fn(value, *(args or []))

    key = stage_name.strip().lower()
    arg_list = args or []
    opts = options or {}

    if key == "ascii":
        return say_ascii_art(value, opts.get("size", "default"))
    if key == "bar":
        total = opts.get("of", opts.get("max", 100))
        return say_bar(value, total=total, width=opts.get("width", 20), label=opts.get("label"))
    if key == "table":
        return say_table(value)
    if key == "box":
        title = arg_list[0] if arg_list else opts.get("title")
        return say_box(value, title, opts.get("width"))
    if key in ("json", "to_json"):
        return say_to_json(value, pretty=not _flag_enabled(opts, "compact"))
    if key in ("from_json", "parse_json", "parse json"):
        return say_from_json(value)
    if key == "split":
        sep = arg_list[0] if arg_list else opts.get("by")
        return say_split(value, sep)
    if key == "replace":
        if len(arg_list) < 2:
            raise SayRuntimeError("replace expects two arguments: old and new text.")
        return say_replace(value, arg_list[0], arg_list[1])
    if key == "unique":
        return say_unique(value)
    if key == "pad":
        w = arg_list[0] if arg_list else opts.get("width", 10)
        align = opts.get("align", "left")
        return say_pad(value, w, align)
    if key in ("center", "centred", "centered"):
        width = arg_list[0] if arg_list else opts.get("width")
        return say_center(value, width)
    if key in ("colour", "color"):
        color = arg_list[0] if arg_list else opts.get("colour") or opts.get("color")
        bg = opts.get("on") or opts.get("background")
        styles = [str(s) for s in arg_list[1:]] if len(arg_list) > 1 else None
        return say_style_text(say_to_text(value), color=color, background=bg, styles=styles)
    if key in ("upper", "uppercase"):
        return say_uppercase(say_to_text(value))
    if key in ("lower", "lowercase"):
        return say_lowercase(say_to_text(value))
    if key in ("trim", "trimmed"):
        return say_trimmed(say_to_text(value))
    if key in ("reverse", "reversed"):
        return say_reversed(value)
    if key in ("sort", "sorted"):
        return say_sorted(value)
    if key in ("length", "count"):
        return say_length(value)
    if key == "words":
        return say_words(say_to_text(value))
    if key == "lines":
        return say_lines(say_to_text(value))
    if key in ("join", "joined"):
        sep = arg_list[0] if arg_list else opts.get("with", ", ")
        return say_joined(value, sep)
    if key in ("sum", "min", "max", "average"):
        return say_lib_call(key, [value], opts)

    raise SayRuntimeError(f"Unknown pipe stage '{stage_name}'.")


def say_style_text(
    text: str,
    color: object = None,
    background: object = None,
    styles: list[str] | None = None,
) -> str:
    """Wrap text in ANSI color and style codes when display modifiers are set."""
    if color is None and background is None and not styles:
        return text

    _enable_windows_ansi()
    codes: list[str] = []

    if styles:
        for style in styles:
            key = str(style).strip().lower()
            if key not in _TEXT_STYLES:
                supported = ", ".join(sorted(_TEXT_STYLES))
                raise SayRuntimeError(
                    f"Unknown text style '{style}'. Supported styles: {supported}."
                )
            codes.append(_TEXT_STYLES[key])

    if color is not None:
        if not isinstance(color, str):
            raise SayRuntimeError(
                f"Color must be text, got {say_type_of(color)}."
            )
        norm_color = " ".join(color.strip().lower().split())
        if norm_color not in _FG_COLORS:
            supported = ", ".join(
                k for k in _FG_COLORS if not k.startswith("bright ")
            )
            raise SayRuntimeError(
                f"Unknown colour '{color}'. Try: {supported} (or 'bright <colour>')."
            )
        codes.append(_FG_COLORS[norm_color])

    if background is not None:
        if not isinstance(background, str):
            raise SayRuntimeError(
                f"Background color must be text, got {say_type_of(background)}."
            )
        norm_bg = " ".join(background.strip().lower().split())
        if norm_bg not in _BG_COLORS:
            supported = ", ".join(
                k for k in _BG_COLORS if not k.startswith("bright ")
            )
            raise SayRuntimeError(
                f"Unknown background colour '{background}'. Try: {supported} (or 'bright <colour>')."
            )
        codes.append(_BG_COLORS[norm_bg])

    if not codes:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _is_number(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _check_int_index(index: object) -> int:
    if isinstance(index, bool) or not isinstance(index, (int, float)):
        raise SayRuntimeError(
            f"Expected a whole number index, got {say_type_of(index)}."
        )
    if isinstance(index, float):
        if not index.is_integer():
            raise SayRuntimeError(f"Index must be a whole number, got {index}.")
        return int(index)
    return index


def say_repr(val: object) -> str:
    """Format a value for display inside a collection."""
    if isinstance(val, str):
        return f'"{val}"'
    return say_to_text(val)


def say_to_text(val: object) -> str:
    """Convert any SayLang value into readable text."""
    if val is None:
        return "nothing"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        if math.isfinite(val) and val.is_integer():
            return str(int(val))
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "[" + ", ".join(say_repr(item) for item in val) + "]"
    if isinstance(val, dict):
        pairs = [f"{k}: {say_repr(v)}" for k, v in val.items()]
        return "{" + ", ".join(pairs) + "}"
    if callable(val):
        name = getattr(val, "name", None) or getattr(val, "__name__", "function")
        return f"<function {name}>"
    return str(val)


def say_to_number(val: object) -> int | float:
    """Convert a number or numeric string into an int or float."""
    if _is_number(val):
        return val  # type: ignore[return-value]
    if isinstance(val, str):
        stripped = val.strip()
        if not stripped:
            raise SayRuntimeError("Cannot convert empty text to a number.")
        try:
            if "." in stripped or "e" in stripped.lower():
                num = float(stripped)
                return int(num) if num.is_integer() and "." not in stripped else num
            return int(stripped)
        except ValueError as exc:
            raise SayRuntimeError(
                f'Cannot convert "{val}" to a number.'
            ) from exc
    raise SayRuntimeError(
        f"Cannot convert {say_type_of(val)} to a number."
    )


def say_type_of(val: object) -> str:
    """Return the SayLang type name of a value."""
    if val is None:
        return "nothing"
    if isinstance(val, bool):
        return "boolean"
    if _is_number(val):
        return "number"
    if isinstance(val, str):
        return "text"
    if isinstance(val, list):
        return "list"
    if isinstance(val, dict):
        return "map"
    if callable(val):
        return "function"
    return type(val).__name__


def say_is_truthy(val: object) -> bool:
    """Return SayLang truthiness of a value."""
    if val is None or val is False:
        return False
    if _is_number(val):
        return val != 0
    if isinstance(val, (str, list, dict)):
        return len(val) > 0
    return True


def say_negate(val: object) -> int | float:
    """Negate a numeric value."""
    if not _is_number(val):
        raise SayRuntimeError(f"Cannot negate {say_type_of(val)}.")
    return -val  # type: ignore[operator]


def say_add(a: object, b: object) -> object:
    """Add two numbers, concatenate lists, or join text."""
    if isinstance(a, str) or isinstance(b, str):
        return say_to_text(a) + say_to_text(b)
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if _is_number(a) and _is_number(b):
        return a + b  # type: ignore[operator]
    raise SayRuntimeError(
        f"Cannot add {say_type_of(a)} and {say_type_of(b)}."
    )


def say_sub(a: object, b: object) -> int | float:
    """Subtract two numbers."""
    if _is_number(a) and _is_number(b):
        return a - b  # type: ignore[operator]
    raise SayRuntimeError(
        f"Cannot subtract {say_type_of(b)} from {say_type_of(a)}."
    )


def say_mul(a: object, b: object) -> object:
    """Multiply two numbers or repeat text by a whole number."""
    if _is_number(a) and _is_number(b):
        return a * b  # type: ignore[operator]
    if isinstance(a, str) and isinstance(b, int) and not isinstance(b, bool):
        if b < 0:
            raise SayRuntimeError("Cannot repeat text a negative number of times.")
        return a * b
    if isinstance(b, str) and isinstance(a, int) and not isinstance(a, bool):
        if a < 0:
            raise SayRuntimeError("Cannot repeat text a negative number of times.")
        return b * a
    raise SayRuntimeError(
        f"Cannot multiply {say_type_of(a)} and {say_type_of(b)}."
    )


def say_div(a: object, b: object) -> float:
    """Divide two numbers."""
    if not (_is_number(a) and _is_number(b)):
        raise SayRuntimeError(
            f"Cannot divide {say_type_of(a)} by {say_type_of(b)}."
        )
    if b == 0:
        raise SayRuntimeError("Cannot divide by zero.")
    return a / b  # type: ignore[operator]


def say_floordiv(a: object, b: object) -> int:
    """Integer-divide two numbers."""
    if not (_is_number(a) and _is_number(b)):
        raise SayRuntimeError(
            f"Cannot whole-divide {say_type_of(a)} by {say_type_of(b)}."
        )
    if b == 0:
        raise SayRuntimeError("Cannot divide by zero.")
    return int(a // b)  # type: ignore[operator]


def say_mod(a: object, b: object) -> int | float:
    """Compute modulo of two numbers."""
    if not (_is_number(a) and _is_number(b)):
        raise SayRuntimeError(
            f"Cannot compute modulo of {say_type_of(a)} and {say_type_of(b)}."
        )
    if b == 0:
        raise SayRuntimeError("Cannot take modulo by zero.")
    return a % b  # type: ignore[operator]


def say_pow(a: object, b: object) -> int | float:
    """Raise a number to a power."""
    if _is_number(a) and _is_number(b):
        return a ** b  # type: ignore[operator]
    raise SayRuntimeError(
        f"Cannot raise {say_type_of(a)} to the power of {say_type_of(b)}."
    )


def _say_equals(a: object, b: object) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_say_equals(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) != len(b) or set(a.keys()) != set(b.keys()):
            return False
        return all(_say_equals(a[k], b[k]) for k in a)
    return a == b


def _say_contains(container: object, needle: object) -> bool:
    if isinstance(container, str):
        if not isinstance(needle, str):
            raise SayRuntimeError(
                f"Cannot check if text contains {say_type_of(needle)}."
            )
        return needle in container
    if isinstance(container, list):
        return any(_say_equals(item, needle) for item in container)
    if isinstance(container, dict):
        return needle in container
    raise SayRuntimeError(
        f"Cannot check if {say_type_of(container)} contains a value."
    )


def say_compare(op: str, a: object, b: object) -> bool:
    """Compare two SayLang values using a named comparison operator."""
    if op == "==":
        return _say_equals(a, b)
    if op == "!=":
        return not _say_equals(a, b)
    if op in (">", "<", ">=", "<="):
        if (_is_number(a) and _is_number(b)) or (
            isinstance(a, str) and isinstance(b, str)
        ):
            if op == ">":
                return a > b  # type: ignore[operator]
            if op == "<":
                return a < b  # type: ignore[operator]
            if op == ">=":
                return a >= b  # type: ignore[operator]
            return a <= b  # type: ignore[operator]
        raise SayRuntimeError(
            f"Cannot compare {say_type_of(a)} and {say_type_of(b)}."
        )
    if op == "contains":
        return _say_contains(a, b)
    if op == "not_contains":
        return not _say_contains(a, b)
    if op == "in":
        return _say_contains(b, a)
    if op == "not_in":
        return not _say_contains(b, a)
    if op == "starts_with":
        if not (isinstance(a, str) and isinstance(b, str)):
            raise SayRuntimeError("starts with requires text values.")
        return a.startswith(b)
    if op == "ends_with":
        if not (isinstance(a, str) and isinstance(b, str)):
            raise SayRuntimeError("ends with requires text values.")
        return a.endswith(b)
    raise SayRuntimeError(f"Unknown comparison operator '{op}'.")


def say_get_item(container: object, index: object) -> object:
    """Get 1-based item from a list or text."""
    idx = _check_int_index(index)
    if not isinstance(container, (list, str)):
        raise SayRuntimeError(
            f"Cannot get an item from {say_type_of(container)}."
        )
    if idx < 1 or idx > len(container):
        raise SayRuntimeError(
            f"Item {idx} is out of range (length is {len(container)})."
        )
    return container[idx - 1]


def say_set_item(container: object, index: object, value: object) -> None:
    """Set 1-based item in a list."""
    idx = _check_int_index(index)
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Cannot update an item in {say_type_of(container)}."
        )
    if idx < 1 or idx > len(container):
        raise SayRuntimeError(
            f"Item {idx} is out of range (length is {len(container)})."
        )
    container[idx - 1] = value


def say_first_item(container: object) -> object:
    """Return the first item of a list or character of text."""
    if not isinstance(container, (list, str)):
        raise SayRuntimeError(
            f"Cannot get the first item of {say_type_of(container)}."
        )
    if len(container) == 0:
        raise SayRuntimeError("Cannot get the first item of an empty collection.")
    return container[0]


def say_last_item(container: object) -> object:
    """Return the last item of a list or character of text."""
    if not isinstance(container, (list, str)):
        raise SayRuntimeError(
            f"Cannot get the last item of {say_type_of(container)}."
        )
    if len(container) == 0:
        raise SayRuntimeError("Cannot get the last item of an empty collection.")
    return container[-1]


def say_get_entry(mapping: object, key: object) -> object:
    """Look up a key in a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Cannot get an entry from {say_type_of(mapping)}."
        )
    if key not in mapping:
        raise SayRuntimeError(f"Map has no entry named '{say_to_text(key)}'.")
    return mapping[key]


def say_set_entry(mapping: object, key: object, value: object) -> None:
    """Set a key in a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Cannot set an entry on {say_type_of(mapping)}."
        )
    mapping[key] = value


def say_get_field(obj: object, field: str) -> object:
    """Access a named field on a map via possessive syntax (x's y)."""
    if not isinstance(obj, dict):
        raise SayRuntimeError(
            f"Cannot access field '{field}' on {say_type_of(obj)}."
        )
    if field not in obj:
        raise SayRuntimeError(f"Map has no field named '{field}'.")
    return obj[field]


def say_set_field(obj: object, field: str, value: object) -> None:
    """Set a named field on a map via possessive syntax."""
    if not isinstance(obj, dict):
        raise SayRuntimeError(
            f"Cannot set field '{field}' on {say_type_of(obj)}."
        )
    obj[field] = value


def say_add_to(container: object, value: object) -> None:
    """Append a value to a list."""
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Can only add items to a list, not {say_type_of(container)}."
        )
    container.append(value)


def say_remove_value(container: object, value: object) -> None:
    """Remove the first matching value from a list."""
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Can only remove values from a list, not {say_type_of(container)}."
        )
    for idx, item in enumerate(container):
        if _say_equals(item, value):
            container.pop(idx)
            return
    raise SayRuntimeError(
        f"Value {say_repr(value)} was not found in the list."
    )


def say_remove_item(container: object, index: object) -> None:
    """Remove a 1-based item index from a list."""
    idx = _check_int_index(index)
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Can only remove items from a list, not {say_type_of(container)}."
        )
    if idx < 1 or idx > len(container):
        raise SayRuntimeError(
            f"Item {idx} is out of range (length is {len(container)})."
        )
    container.pop(idx - 1)


def say_remove_entry(mapping: object, key: object) -> None:
    """Remove a key from a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Can only remove entries from a map, not {say_type_of(mapping)}."
        )
    if key not in mapping:
        raise SayRuntimeError(f"Map has no entry named '{say_to_text(key)}'.")
    del mapping[key]


def say_range(start: object, end: object, step: object = None) -> list[int | float]:
    """Generate an inclusive range from start to end."""
    if not (_is_number(start) and _is_number(end)):
        raise SayRuntimeError("Range start and end must be numbers.")
    s = start
    e = end
    if step is None:
        st: int | float = 1 if s <= e else -1  # type: ignore[operator]
    else:
        if not _is_number(step):
            raise SayRuntimeError("Range step must be a number.")
        st = step  # type: ignore[assignment]
        if st == 0:
            raise SayRuntimeError("Range step cannot be zero.")

    if isinstance(s, int) and isinstance(e, int) and isinstance(st, int):
        stop = e + 1 if st > 0 else e - 1
        return list(range(s, stop, st))

    results: list[int | float] = []
    cur = float(s)  # type: ignore[arg-type]
    limit = float(e)  # type: ignore[arg-type]
    step_f = float(st)
    if step_f > 0:
        while cur <= limit + 1e-9:
            results.append(int(cur) if cur.is_integer() else cur)
            cur += step_f
    else:
        while cur >= limit - 1e-9:
            results.append(int(cur) if cur.is_integer() else cur)
            cur += step_f
    return results


def say_iter(iterable: object) -> list[object]:
    """Return a list of items to iterate over cleanly."""
    if isinstance(iterable, list):
        return list(iterable)
    if isinstance(iterable, str):
        return list(iterable)
    if isinstance(iterable, dict):
        return list(iterable.keys())
    raise SayRuntimeError(
        f"Cannot iterate over {say_type_of(iterable)}."
    )


def say_iter_pairs(mapping: object) -> list[tuple[object, object]]:
    """Return key/value pairs from a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Expected a map for key and value iteration, got {say_type_of(mapping)}."
        )
    return list(mapping.items())


def say_length(val: object) -> int:
    """Return the length of text, list, or map."""
    if isinstance(val, (str, list, dict)):
        return len(val)
    raise SayRuntimeError(f"Cannot get the length of {say_type_of(val)}.")


def say_keys(val: object) -> list[object]:
    """Return the keys of a map as a list."""
    if not isinstance(val, dict):
        raise SayRuntimeError(f"Cannot get keys of {say_type_of(val)}.")
    return list(val.keys())


def say_values(val: object) -> list[object]:
    """Return the values of a map as a list."""
    if not isinstance(val, dict):
        raise SayRuntimeError(f"Cannot get values of {say_type_of(val)}.")
    return list(val.values())


def say_uppercase(val: object) -> str:
    """Return uppercase text."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot uppercase {say_type_of(val)}.")
    return val.upper()


def say_lowercase(val: object) -> str:
    """Return lowercase text."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot lowercase {say_type_of(val)}.")
    return val.lower()


def say_trimmed(val: object) -> str:
    """Trim leading and trailing whitespace from text."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot trim {say_type_of(val)}.")
    return val.strip()


def say_words(val: object) -> list[str]:
    """Split text into whitespace-delimited words."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot split {say_type_of(val)} into words.")
    return val.split()


def say_lines(val: object) -> list[str]:
    """Split text into lines."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot split {say_type_of(val)} into lines.")
    return val.splitlines()


def say_joined(items: object, sep: object) -> str:
    """Join a list into text using separator."""
    if not isinstance(items, list):
        raise SayRuntimeError(f"Cannot join {say_type_of(items)}.")
    if not isinstance(sep, str):
        raise SayRuntimeError("Join separator must be text.")
    return sep.join(say_to_text(item) for item in items)


def say_sorted(items: object) -> list[object]:
    """Return a sorted copy of a list."""
    if not isinstance(items, list):
        raise SayRuntimeError(f"Cannot sort {say_type_of(items)}.")
    try:
        return sorted(items)
    except TypeError as exc:
        raise SayRuntimeError("Cannot sort items of incompatible types.") from exc


def say_reversed(val: object) -> object:
    """Return a reversed copy of a list or text."""
    if isinstance(val, list):
        return list(reversed(val))
    if isinstance(val, str):
        return val[::-1]
    raise SayRuntimeError(f"Cannot reverse {say_type_of(val)}.")


def say_rounded(val: object) -> int:
    """Round a number to the nearest integer."""
    if not _is_number(val):
        raise SayRuntimeError(f"Cannot round {say_type_of(val)}.")
    return round(val)  # type: ignore[arg-type]


def say_abs(val: object) -> int | float:
    """Return the absolute value of a number."""
    if not _is_number(val):
        raise SayRuntimeError(
            f"Cannot compute absolute value of {say_type_of(val)}."
        )
    return abs(val)  # type: ignore[arg-type]


def say_sqrt(val: object) -> float:
    """Return the square root of a non-negative number."""
    if not _is_number(val):
        raise SayRuntimeError(
            f"Cannot compute square root of {say_type_of(val)}."
        )
    if val < 0:  # type: ignore[operator]
        raise SayRuntimeError("Cannot compute square root of a negative number.")
    return math.sqrt(val)  # type: ignore[arg-type]


def say_random_int(low: object, high: object) -> int:
    """Return a random integer between low and high inclusive."""
    if isinstance(low, bool) or isinstance(high, bool):
        raise SayRuntimeError("Random range bounds must be whole numbers.")
    if not (isinstance(low, int) and isinstance(high, int)):
        raise SayRuntimeError("Random range bounds must be whole numbers.")
    if low > high:
        raise SayRuntimeError(
            f"Random range is backwards: {low} is greater than {high}."
        )
    return random.randint(low, high)


def say_read_file(path: object) -> str:
    """Read UTF-8 text from a file."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SayRuntimeError(f"Could not read file '{path}': {exc}") from exc


def say_write_file(path: object, content: object) -> None:
    """Write text to a file, creating parent directories if needed."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    try:
        target = Path(path)
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(say_to_text(content), encoding="utf-8")
    except OSError as exc:
        raise SayRuntimeError(f"Could not write file '{path}': {exc}") from exc


def say_append_file(path: object, content: object) -> None:
    """Append text to a file."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    try:
        target = Path(path)
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(say_to_text(content))
    except OSError as exc:
        raise SayRuntimeError(f"Could not append to file '{path}': {exc}") from exc


# --- SAYLANG RUNTIME END ---
