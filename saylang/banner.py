"""Codex-CLI-style monochrome B&W startup icon and banner for the SayLang CLI."""

from __future__ import annotations

import sys

from saylang import runtime

_UNICODE_TEST_CHARS = "╭─╮│╰╯╷╵┬├┤·"


def _supports_unicode(stream_encoding: str | None = None) -> bool:
    enc = stream_encoding or getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        _UNICODE_TEST_CHARS.encode(enc)
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def render_startup_banner(
    version: str,
    *,
    color: bool = True,
    unicode_ok: bool | None = None,
) -> str:
    """Render the SayLang monochrome B&W startup card with mini squircle icon."""
    if color:
        runtime._enable_windows_ansi()

    use_unicode = _supports_unicode() if unicode_ok is None else unicode_ok

    def dim(text: str) -> str:
        return f"\x1b[2m{text}\x1b[0m" if color else text

    def bold(text: str) -> str:
        return f"\x1b[1m{text}\x1b[0m" if color else text

    if use_unicode:
        icon_rows = [
            "╭─────────────╮",
            "│ ╭─╮ ╭─╮ ╷ ╷ │",
            "│ │   │ │ │ │ │",
            "│ ╰─╮ ├─┤ ╰┬╯ │",
            "│   │ │ │  │  │",
            "│ ╰─╯ ╵ ╵  ╵  │",
            "╰─────────────╯",
        ]
        right_rows = [
            ("", ""),
            (f"Saylang  v{version}", "bold"),
            ("plain-english · .pl", "dim"),
            ("", ""),
            (":help  :english  :nana", "dim"),
            (":vars  :py       :quit", "dim"),
            ("", ""),
        ]
        inner_width = 48
        lines = [dim("╭" + "─" * inner_width + "╮")]
        for icon_raw, (right_raw, style) in zip(icon_rows, right_rows):
            icon_styled = bold(icon_raw)
            if style == "bold":
                right_styled = bold(right_raw)
            elif style == "dim":
                right_styled = dim(right_raw)
            else:
                right_styled = right_raw
            vis_len = 2 + len(icon_raw) + 3 + len(right_raw)
            pad = " " * max(inner_width - vis_len, 1)
            lines.append(
                f"{dim('│')}  {icon_styled}   {right_styled}{pad}{dim('│')}"
            )
        lines.append(dim("╰" + "─" * inner_width + "╯"))
        return "\n".join(lines)

    icon_rows_ascii = [
        "+-------------+",
        "|  SAY  LANG  |",
        "|   [ SAY ]   |",
        "|  plain .pl  |",
        "+-------------+",
    ]
    right_rows_ascii = [
        ("", ""),
        (f"Saylang  v{version}", "bold"),
        ("plain-english .pl", "dim"),
        (":help  :english  :py  :quit", "dim"),
        ("", ""),
    ]
    inner_width = 50
    lines = [dim("+" + "-" * inner_width + "+")]
    for icon_raw, (right_raw, style) in zip(icon_rows_ascii, right_rows_ascii):
        icon_styled = bold(icon_raw)
        if style == "bold":
            right_styled = bold(right_raw)
        elif style == "dim":
            right_styled = dim(right_raw)
        else:
            right_styled = right_raw
        vis_len = 2 + len(icon_raw) + 3 + len(right_raw)
        pad = " " * max(inner_width - vis_len, 1)
        lines.append(
            f"{dim('|')}  {icon_styled}   {right_styled}{pad}{dim('|')}"
        )
    lines.append(dim("+" + "-" * inner_width + "+"))
    return "\n".join(lines)
