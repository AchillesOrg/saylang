"""Tests for the built-in `nana` TUI studio, templates, file browser, and highlighter."""

import io
import re
import tempfile
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


if __name__ == "__main__":
    unittest.main()
