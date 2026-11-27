"""Tests for SayLang prebuilt stdlib, pipes, flags, layout, and REPL-aware :english."""

import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from saylang.cli import main
from saylang.errors import SayRuntimeError
from saylang.interpreter import run_and_capture
from saylang.repl import SayREPL
from saylang.transpiler import compile_to_python


class TestStdlibPipesFlags(unittest.TestCase):
    def test_exact_four_line_tty_clock_with_and_without_flag(self) -> None:
        src = (
            "import time, ascii\n"
            "print time --12h | ascii --size default\n"
            "if flag -d then print date below time\n"
            "flags: -d\n"
        )
        out_no_flag, _ = run_and_capture(src, cli_args=[])
        lines_no_flag = out_no_flag.splitlines()
        self.assertEqual(len(lines_no_flag), 5)
        self.assertIn("█", out_no_flag)

        out_with_flag, _ = run_and_capture(src, cli_args=["-d"])
        lines_with_flag = out_with_flag.splitlines()
        self.assertEqual(len(lines_with_flag), 6)
        self.assertTrue(lines_with_flag[-1].startswith(" "))

        py_code = compile_to_python(src, standalone=True)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=True
        ) as tmp:
            tmp.write(py_code)
            tmp.flush()
            proc = subprocess.run(
                [sys.executable, tmp.name, "-d"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(len(proc.stdout.splitlines()), 6)
            self.assertTrue(proc.stdout.splitlines()[-1].startswith(" "))

    def test_cli_forwards_flags_and_prints_declared_flag_help(self) -> None:
        clock_path = Path(__file__).resolve().parent.parent / "examples" / "clock.pl"

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main([str(clock_path), "-d"])
        self.assertEqual(rc, 0)
        self.assertEqual(len(buf.getvalue().splitlines()), 6)

        buf_help = io.StringIO()
        with contextlib.redirect_stdout(buf_help):
            rc_help = main(["run", str(clock_path), "--help"])
        self.assertEqual(rc_help, 0)
        self.assertIn("-d", buf_help.getvalue())

    def test_ascii_sizes_box_center_colour_and_user_function_pipes(self) -> None:
        src = (
            "to shout with s\n"
            '    return s plus "!!!"\n'
            'print "12:30" | ascii --size small\n'
            'print "HI" | ascii --size big\n'
            'print "hi" | shout | upper | box\n'
            'print "ok" | colour red\n'
        )
        out, _ = run_and_capture(src)
        self.assertIn("╭", out)
        self.assertIn("HI!!!", out)
        self.assertIn("\x1b[31mok\x1b[0m", out)

        py_code = compile_to_python(src, standalone=True)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", encoding="utf-8", delete=True
        ) as tmp:
            tmp.write(py_code)
            tmp.flush()
            proc = subprocess.run(
                [sys.executable, tmp.name],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(proc.stdout, out)

    def test_auto_import_time_shadowing_and_unknown_import_error(self) -> None:
        out, _ = run_and_capture(
            "print date --iso\n"
            "print type of current hour\n"
            "set time to 42\n"
            "print time\n"
        )
        lines = out.splitlines()
        self.assertRegex(lines[0], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(lines[1], "number")
        self.assertEqual(lines[2], "42")

        with self.assertRaises(SayRuntimeError):
            run_and_capture("import nonexistent_lib\n")

    def test_every_wait_clear_and_inline_if_otherwise(self) -> None:
        src = (
            "clear screen\n"
            "wait 0 seconds\n"
            "set n to 0\n"
            "every 0 seconds\n"
            "    increase n by 1\n"
            "    if n is 2 then stop\n"
            'if n is 2 then print "two" otherwise print "other"\n'
        )
        out, _ = run_and_capture(src)
        self.assertIn("\x1b[2J\x1b[H", out)
        self.assertTrue(out.endswith("two\n"))

    def test_repl_english_passes_context_vars(self) -> None:
        captured_kwargs: dict[str, object] = {}

        def fake_translate(text: str, **kwargs: object) -> object:
            captured_kwargs.update(kwargs)
            from saylang.translator import TranslationResult

            return TranslationResult(say_code="say score", backend="mock")

        inputs = iter(["set score to 7", ":english print score", "quit"])
        out = io.StringIO()

        def fake_input(prompt: str = "") -> str:
            try:
                return next(inputs)
            except StopIteration as exc:
                raise EOFError from exc

        repl = SayREPL(stdout=out, input_fn=fake_input)
        with patch("saylang.repl.translate_english", side_effect=fake_translate):
            self.assertEqual(repl.run(), 0)
        self.assertIn("score", captured_kwargs.get("context_vars", []))  # type: ignore[operator]
        self.assertIn("7\n", out.getvalue())

    def test_interpolation_pos_live_calc_save_load_and_bash_pipes(self) -> None:
        import os
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            prev = os.getcwd()
            os.chdir(tmpdir)
            try:
                src = (
                    'set hero to "Ada"\n'
                    'set m to a map with name as "Ada", score as 42\n'
                    'say "Hi {hero}, {m\'s score} -> {hero | upper}, literal \\{x\\}"\n'
                    "say 'raw {hero}'\n"
                    'save m to "user.json"\n'
                    'set loaded to load "user.json"\n'
                    'say "Loaded {loaded\'s name}:{loaded\'s score}"\n'
                    'make folder "sub"\n'
                    'copy "user.json" to "sub/u2.json"\n'
                    'move "sub/u2.json" to "sub/u3.json"\n'
                    'say glob "sub/*.json"\n'
                    'rm "sub"\n'
                    'set logs to a list of "info ok", "ERROR disk", "info done", "error net"\n'
                    'say logs | grep -i "error" | head 1\n'
                    'say logs | tail 1\n'
                    'say calc "2 + 3 * 4"\n'
                    'say "10 / 2" | calc\n'
                    "with_flags:\n"
                )
                # Strip last dummy label if unused; run clean block:
                src = src.replace("with_flags:\n", "")
                out, _ = run_and_capture(src)
                self.assertIn("Hi Ada, 42 -> ADA, literal {x}", out)
                self.assertIn("raw {hero}", out)
                self.assertIn("Loaded Ada:42", out)
                self.assertIn("u3.json", out)
                self.assertIn("['ERROR disk']".replace("'", '"'), out)
                self.assertIn("error net", out)
                self.assertIn("\n14\n", out)
                self.assertIn("\n5\n", out)
            finally:
                os.chdir(prev)

        # `pos center`, `pos top-right`, `pos 10, 5`, `| pos center`, `date below time`
        with patch("saylang.runtime.shutil.get_terminal_size", return_value=os.terminal_size((80, 24))):
            out_pos, _ = run_and_capture(
                "import time, ascii\n"
                "pos center\n"
                "print time --12h | ascii --size small\n"
                "print date below time\n"
            )
            lines = out_pos.splitlines()
            # Vertically centered for 24 rows (block_h=3 -> top_pad=10 empty lines before clock row 1)
            clock_rows = [ln for ln in lines if "█" in ln]
            self.assertEqual(len(clock_rows), 3)
            clock_indent = len(clock_rows[0]) - len(clock_rows[0].lstrip(" "))
            date_indent = len(lines[-1]) - len(lines[-1].lstrip(" "))
            self.assertGreater(clock_indent, 5)
            self.assertGreaterEqual(date_indent, clock_indent)

            out_xy, _ = run_and_capture('say "Hi" pos 6, 3\n')
            self.assertEqual(out_xy, "\n\n     Hi\n")

            out_pipe_pos, _ = run_and_capture('say "TR" | pos top-right\n')
            self.assertTrue(out_pipe_pos.endswith(" " * 78 + "TR\n"))

            # Non-TTY `time --live` renders 1 frame without hanging
            out_non_tty, _ = run_and_capture("print time --live\n")
            self.assertRegex(out_non_tty.strip(), r"^\d{2}:\d{2}:\d{2}$")

            # Explicit --frames 2 --interval 0 renders 2 frames cleanly
            out_two, _ = run_and_capture("print time --live --interval 0 --frames 2\n")
            self.assertEqual(len(out_two.strip().splitlines()), 2)

            # Reset shutil stub clean
            self.assertIsNotNone(shutil.get_terminal_size)


if __name__ == "__main__":
    unittest.main()
