"""Tests for the built-in `nana` SayLang text editor and syntax highlighter."""

import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from saylang.cli import main
from saylang.nana import NanaBuffer, highlight_saylang_line
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
