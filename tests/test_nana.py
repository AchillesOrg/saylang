"""Tests for the built-in `nana` TUI studio, templates, file browser, and highlighter."""

import io
import os
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from saylang.cli import main
from saylang.nana import (
    NANA_TEMPLATES,
    NanaBuffer,
    discover_pl_files,
    highlight_saylang_line,
    load_bg_mode,
    render_file_picker,
    render_template_picker,
    render_welcome_menu,
    save_bg_mode,
)
from saylang.parser import parse_source
from saylang.repl import SayREPL

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


class TestNanaEditor(unittest.TestCase):
    def test_syntax_highlighter_preserves_exact_characters_and_colors(self) -> None:
        samples = [
            "# a hash comment",
            "note a prose comment",
            "import time, ascii",
            "print time --12h | ascii --size default colour red",
            "if flag -d then print date below time # inline note",
            "set user's score to 42",
            'say "hello world lol" colour cyan bold',
        ]
        for line in samples:
            highlighted = highlight_saylang_line(line)
            self.assertEqual(_ANSI_RE.sub("", highlighted), line)
            self.assertIn("\x1b[", highlighted)

    def test_all_builtin_templates_parse_cleanly_and_load_into_buffer(self) -> None:
        self.assertGreaterEqual(len(NANA_TEMPLATES), 5)
        for tpl in NANA_TEMPLATES:
            with self.subTest(template=tpl.id):
                parse_source(tpl.code)
                buf = NanaBuffer.from_template(tpl)
                self.assertTrue(buf.modified)
                self.assertEqual(buf.filepath, Path(tpl.filename))
                ok, msg = buf.check_syntax()
                self.assertTrue(ok, msg)

    def test_discover_pl_files_skips_ignored_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "a.pl").write_text('say "a"\n', encoding="utf-8")
            (root / "sub").mkdir()
            (root / "sub" / "b.pl").write_text('say "b"\n', encoding="utf-8")
            (root / ".git").mkdir()
            (root / ".git" / "ignored.pl").write_text('say "no"\n', encoding="utf-8")
            (root / "__pycache__").mkdir()
            (root / "__pycache__" / "ignored2.pl").write_text('say "no"\n', encoding="utf-8")

            found = discover_pl_files(root)
            rel = [str(p.relative_to(root.resolve())) for p in found]
            self.assertEqual(rel, ["a.pl", str(Path("sub") / "b.pl")])

    def test_tui_screens_render_cleanly_wide_and_narrow(self) -> None:
        examples_dir = Path(__file__).resolve().parent.parent / "examples"
        files = discover_pl_files(examples_dir)
        row_split_re = re.compile(r"\x1b\[(\d+);1H([^\x1b]*(?:\x1b\[[0-9;]*[mK])*)")
        full_ansi_re = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

        def assert_adaptive_frame(frame: str, rows: int, cols: int) -> None:
            self.assertNotIn("\n", frame)
            self.assertNotIn("\x1b[7m", frame)
            for r in range(1, rows + 1):
                token = f"\x1b[{r};1H"
                self.assertIn(token, frame, f"Missing row positioning {token}")
                start = frame.index(token) + len(token)
                end = frame.find("\x1b[K", start)
                self.assertGreater(end, start - 1)
                vis = full_ansi_re.sub("", frame[start:end])
                self.assertLessEqual(len(vis), cols)

        for bg_mode in ("mica", "black"):
            for rows, cols in ((12, 42), (24, 80), (45, 160)):
                welcome = render_welcome_menu(
                    1, rows, cols, has_active_buffer=False, bg_mode=bg_mode
                )
                assert_adaptive_frame(welcome, rows, cols)
                self.assertIn("New File", welcome)
                self.assertIn("Start from Template", welcome)
                self.assertIn("Open File", welcome)
                if bg_mode == "black":
                    self.assertIn("\x1b[40;48;2;0;0;0m", welcome)
                else:
                    self.assertIn("\x1b[49m", welcome)

                welcome_active = render_welcome_menu(
                    0, rows, cols, has_active_buffer=True, bg_mode=bg_mode
                )
                assert_adaptive_frame(welcome_active, rows, cols)
                self.assertIn("Resume Editor", welcome_active)

                tpl_screen = render_template_picker(1, rows, cols, bg_mode=bg_mode)
                assert_adaptive_frame(tpl_screen, rows, cols)
                self.assertIn("TTY Clock", tpl_screen)

                file_screen = render_file_picker(
                    files, 0, rows, cols, root=examples_dir, bg_mode=bg_mode
                )
                assert_adaptive_frame(file_screen, rows, cols)
                self.assertIn(".pl", file_screen)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"SAYLANG_HOME": tmpdir}):
                self.assertEqual(load_bg_mode(), "mica")
                save_bg_mode("black")
                self.assertEqual(load_bg_mode(), "black")
                save_bg_mode("mica")
                self.assertEqual(load_bg_mode(), "mica")

    def test_buffer_editing_auto_indent_cut_paste_and_save(self) -> None:
        buf = NanaBuffer()
        for ch in "if flag -d":
            buf.insert_char(ch)
        buf.insert_newline()
        self.assertEqual(buf.row, 1)
        self.assertEqual(buf.col, 4)
        self.assertEqual(buf.lines[1], "    ")

        for ch in 'say "hi"':
            buf.insert_char(ch)
        ok, msg = buf.check_syntax()
        self.assertTrue(ok, msg)

        buf.cut_line()
        self.assertEqual(buf.cut_buffer, '    say "hi"')
        buf.paste_line()
        self.assertIn('    say "hi"', buf.lines)

        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "demo.pl"
            buf.save(target)
            self.assertFalse(buf.modified)
            loaded = NanaBuffer.from_file(str(target))
            self.assertEqual(loaded.text, buf.text)

    def test_buffer_syntax_error_and_render_frame(self) -> None:
        buf = NanaBuffer(lines=["set x to [broken]"])
        ok, msg = buf.check_syntax()
        self.assertFalse(ok)
        self.assertIn("Line 1:", msg)

        frame = buf.render_frame(rows=20, cols=80)
        self.assertIn("NANA", frame)
        self.assertIn("^S Save", frame)
        self.assertIn("^P Menu", frame)
        self.assertIn("^R Run", frame)

    def test_cli_and_repl_launch_nana(self) -> None:
        with patch("saylang.cli.run_nana", return_value=0) as mock_cli_nana:
            self.assertEqual(main(["nana", "demo.pl"]), 0)
            mock_cli_nana.assert_called_once_with("demo.pl")

        inputs = iter(["nana clock.pl", ":nana", "quit"])
        out = io.StringIO()

        def fake_input(prompt: str = "") -> str:
            try:
                return next(inputs)
            except StopIteration as exc:
                raise EOFError from exc

        repl = SayREPL(stdout=out, input_fn=fake_input)
        with patch("saylang.repl.run_nana", return_value=0) as mock_repl_nana:
            self.assertEqual(repl.run(), 0)
            self.assertEqual(mock_repl_nana.call_count, 2)
            mock_repl_nana.assert_any_call("clock.pl")
            mock_repl_nana.assert_any_call(None)

    @unittest.skipIf(sys.platform == "win32", "POSIX PTY end-to-end test")
    def test_nana_pty_arrow_keys_and_mouse_support(self) -> None:
        import fcntl
        import pty
        import re
        import struct
        import termios

        ansi_re = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
        master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        proc = subprocess.Popen(
            [sys.executable, "-m", "saylang", "nana"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(Path(__file__).resolve().parent.parent),
            close_fds=True,
        )
        os.close(slave_fd)

        def drain(wait_s: float = 0.2) -> bytes:
            chunks: list[bytes] = []
            deadline = time.monotonic() + wait_s
            while time.monotonic() < deadline:
                r, _, _ = select.select([master_fd], [], [], 0.03)
                if r:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            chunks.append(data)
                    except OSError:
                        break
            return b"".join(chunks)

        def drain_until_plain(marker: str, timeout_s: float = 2.0) -> tuple[bytes, str]:
            buf = bytearray()
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                r, _, _ = select.select([master_fd], [], [], 0.04)
                if r:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            buf.extend(data)
                    except OSError:
                        break
                plain = ansi_re.sub("", buf.decode("utf-8", errors="replace"))
                if marker in plain:
                    return bytes(buf), plain
            plain = ansi_re.sub("", buf.decode("utf-8", errors="replace"))
            return bytes(buf), plain

        def wait_exit(timeout_s: float = 3.0) -> tuple[int | None, bytes]:
            buf = bytearray()
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                r, _, _ = select.select([master_fd], [], [], 0.05)
                if r:
                    try:
                        data = os.read(master_fd, 4096)
                        if data:
                            buf.extend(data)
                    except OSError:
                        pass
                if proc.poll() is not None:
                    buf.extend(drain(0.05))
                    return proc.returncode, bytes(buf)
            return proc.poll(), bytes(buf)

        try:
            raw_init, plain_init = drain_until_plain("1. New File")
            self.assertIn(b"\x1b[?1006h", raw_init)
            self.assertIn("New File", plain_init)

            # CSI Down arrow & SS3 Down arrow — must NOT exit!
            os.write(master_fd, b"\x1b[B")
            _, plain_csi = drain_until_plain("▌ 2. Start from Template")
            self.assertIsNone(proc.poll(), "nana exited prematurely on CSI Down arrow")
            self.assertIn("▌ 2. Start from Template", plain_csi)

            os.write(master_fd, b"\x1bOB")
            _, plain_ss3 = drain_until_plain("▌ 3. Open File")
            self.assertIsNone(proc.poll(), "nana exited prematurely on SS3 Down arrow")
            self.assertIn("▌ 3. Open File", plain_ss3)

            os.write(master_fd, b"\x1b[A")
            _, plain_up = drain_until_plain("▌ 2. Start from Template")
            self.assertIsNone(proc.poll())
            self.assertIn("▌ 2. Start from Template", plain_up)

            # SGR mouse wheel down -> moves selection down without exiting
            os.write(master_fd, b"\x1b[<65;20;10M")
            _, plain_wheel = drain_until_plain("▌ 3. Open File")
            self.assertIsNone(proc.poll())
            self.assertIn("▌ 3. Open File", plain_wheel)

            # SGR mouse click on item 1 ("1. New File" at row 10) -> opens New File prompt
            os.write(master_fd, b"\x1b[<0;20;10M\x1b[<0;20;10m")
            _, plain_prompt = drain_until_plain("New file name")
            self.assertIn("New file name", plain_prompt)
            os.write(master_fd, b"\r")
            _, plain_ed = drain_until_plain("Ln 1, Col 1")
            self.assertIn("Ln 1, Col 1", plain_ed)

            # Quit cleanly with Ctrl+X
            os.write(master_fd, b"\x18")
            rc, tail = wait_exit()
            self.assertEqual(rc, 0)
            self.assertIn(b"\x1b[?1006l", tail)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2.0)
            os.close(master_fd)

    def test_parse_mouse_event_helper(self) -> None:
        from saylang.nana import _footer_shortcut_hit, _parse_mouse_event

        self.assertEqual(_parse_mouse_event("MOUSE:CLICK:12:34"), ("CLICK", 12, 34))
        self.assertEqual(_parse_mouse_event("MOUSE:WHEEL_UP:5:8"), ("WHEEL_UP", 5, 8))
        self.assertEqual(
            _parse_mouse_event("MOUSE:WHEEL_DOWN:5:8"), ("WHEEL_DOWN", 5, 8)
        )
        self.assertIsNone(_parse_mouse_event("UP"))
        self.assertEqual(
            _footer_shortcut_hit(
                " ^S Save   ^R Run   ^X Exit ",
                13,
                [("^S Save", "\x13"), ("^R Run", "\x12"), ("^X Exit", "\x18")],
            ),
            "\x12",
        )


if __name__ == "__main__":
    unittest.main()
