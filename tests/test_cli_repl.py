"""Tests for the SayLang CLI and interactive REPL."""

import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from saylang.cli import main
from saylang.repl import SayREPL


class TestCLIAndREPL(unittest.TestCase):
    def test_cli_check_run_compile_ast_english(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = Path(tmpdir) / "sample.pl"
            out_py = Path(tmpdir) / "sample.py"
            src_path.write_text('set x to 2 plus 3\nsay "sum=", x\n', encoding="utf-8")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["check", str(src_path)]), 0)
            self.assertIn("OK:", buf.getvalue())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["run", str(src_path)]), 0)
            self.assertEqual(buf.getvalue(), "sum=5\n")

            # Shorthand: `saylang <file.pl>`
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main([str(src_path)]), 0)
            self.assertEqual(buf.getvalue(), "sum=5\n")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                self.assertEqual(main(["ast", str(src_path)]), 0)
            self.assertIn("Program(", buf.getvalue())

            self.assertEqual(main(["compile", str(src_path), "-o", str(out_py)]), 0)
            self.assertTrue(out_py.is_file())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = main(
                    [
                        "english",
                        "count from 1 to 2 and print each number",
                        "--provider",
                        "offline",
                        "--run",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertIn("for each number from 1 to 2", buf.getvalue())
            self.assertIn("1\n2\n", buf.getvalue())

    def test_cli_syntax_error_returns_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.pl"
            bad.write_text("if true\nsay 1\n", encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                rc = main(["check", str(bad)])
            self.assertEqual(rc, 1)
            self.assertIn("Syntax error", err.getvalue())

    def test_repl_session_multiline_and_commands(self) -> None:
        inputs = iter(
            [
                "set score to 10",
                "if score is greater than 5",
                "    say score",
                "",
                ":vars",
                ":py",
                ":english print hello",
                ":quit",
            ]
        )
        out = io.StringIO()

        def fake_input(prompt: str = "") -> str:
            try:
                return next(inputs)
            except StopIteration as exc:
                raise EOFError from exc

        repl = SayREPL(stdout=out, input_fn=fake_input)
        with patch.dict(os.environ, {}, clear=True):
            rc = repl.run()
        self.assertEqual(rc, 0)
        text = out.getvalue()
        self.assertIn("10\n", text)
        self.assertIn("score = 10", text)
        self.assertIn("if say_is_truthy", text)
        self.assertIn("hello\n", text)


if __name__ == "__main__":
    unittest.main()
