"""Tests for `saylang learn` TUI course and CLI/TUI language primitives."""

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from saylang.cli import main
from saylang.interpreter import run_and_capture
from saylang.learn import (
    LESSONS,
    evaluate_lesson,
    format_curriculum_list,
    load_progress,
    render_learn_workspace,
    render_lesson_map,
    save_progress,
)
from saylang.nana import NanaBuffer
from saylang.transpiler import compile_to_python


class TestLearnAndCliTuiPrimitives(unittest.TestCase):
    def test_all_lesson_solutions_pass_and_starters_fail(self) -> None:
        self.assertGreaterEqual(len(LESSONS), 10)
        for lesson in LESSONS:
            sol_results = evaluate_lesson(lesson, lesson.solution)
            self.assertTrue(sol_results, f"Lesson {lesson.id} has no tests")
            for res in sol_results:
                self.assertTrue(
                    res.passed,
                    f"Lesson {lesson.id} solution failed '{res.description}': {res.detail}",
                )

            starter_results = evaluate_lesson(lesson, lesson.starter)
            self.assertFalse(
                all(r.passed for r in starter_results),
                f"Lesson {lesson.id} starter already passes all tests",
            )

    def test_cli_tui_language_features_interpreter_and_transpiler(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            prev_cwd = os.getcwd()
            os.chdir(tmpdir)
            try:
                src = (
                    'set rows to a list of (a map with name as "cli", pct as 100)\n'
                    'say bar 3 of 4 --width 8 --label "Build"\n'
                    "say rows | table\n"
                    'say rule --width 12 --title "Go"\n'
                    'write rows | json --compact to file "out.json"\n'
                    'if file exists "out.json"\n'
                    '    set parsed to parse json (read file "out.json")\n'
                    "    set first_row to first item of parsed\n"
                    "    say first_row's name\n"
                    'say split "a,b,c" by ","\n'
                    'say replace "hi world" with "saylang" in "hi world"\n'
                    "say unique of (a list of 1, 1, 2)\n"
                    'say "ok" | box --width 10\n'
                    "say files in \".\"\n"
                )
                out, _ = run_and_capture(src)
                self.assertIn("Build [██████░░] 75%", out)
                self.assertIn("╭──────┬─────╮", out)
                self.assertIn("Go", out)
                self.assertIn("[\"a\", \"b\", \"c\"]", out)
                self.assertIn("[1, 2]", out)
                self.assertIn("out.json", out)

                py_code = compile_to_python(
                    'set m to a map with ok as true\n'
                    'say bar 2 of 4 --width 8\n'
                    'say m | json --compact\n'
                    'say ("a,b" | split ",") | unique\n',
                    standalone=True,
                )
                script_file = Path(tmpdir) / "prog.py"
                script_file.write_text(py_code, encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, str(script_file)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                )
                self.assertIn("50%", proc.stdout)
                self.assertIn('{"ok": true}', proc.stdout)
                self.assertIn('["a", "b"]', proc.stdout)
            finally:
                os.chdir(prev_cwd)

    def test_choose_and_read_key_and_exit_and_cursor(self) -> None:
        src = (
            "hide cursor\n"
            'set pick to choose "Env:" from a list of "dev", "prod"\n'
            "set k to read key\n"
            "show cursor\n"
            'say pick, ":", k\n'
            "exit with 0\n"
        )
        with self.assertRaises(SystemExit) as ctx:
            out_buf = io.StringIO()
            inputs = iter(["2", "up"])
            from saylang.interpreter import run_source

            run_source(
                src,
                stdout=out_buf,
                input_fn=lambda _p="": next(inputs),
            )
        self.assertEqual(ctx.exception.code, 0)
        out = out_buf.getvalue()
        self.assertIn("\x1b[?25l", out)
        self.assertIn("\x1b[?25h", out)
        self.assertIn("prod:up", out)

    def test_learn_progress_persistence_and_screens(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"SAYLANG_HOME": tmpdir}):
                save_progress({"completed": ["01-styled-cards"], "drafts": {"02-decisions-pipes": 'say "hi"'}, "current": 2})
                loaded = load_progress()
                self.assertEqual(loaded["completed"], ["01-styled-cards"])
                self.assertEqual(loaded["current"], 2)

                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.assertEqual(main(["learn", "--list"]), 0)
                self.assertIn("1/10 completed", buf.getvalue())
                self.assertIn("[✓]  1.", buf.getvalue())

        lesson = LESSONS[0]
        ebuf = NanaBuffer(lines=lesson.starter.splitlines())
        res = evaluate_lesson(lesson, lesson.starter)
        wide = render_learn_workspace(lesson, ebuf, res, 1, set(), 28, 100)
        self.assertIn("Challenge:", wide)
        self.assertIn("Hint:", wide)
        narrow = render_learn_workspace(lesson, ebuf, res, 0, set(), 20, 60)
        self.assertIn("Goal:", narrow)
        cmap = render_lesson_map(0, {"01-styled-cards"}, 24, 90)
        self.assertIn("SayLang Interactive Course", cmap)
        self.assertIn("10%", format_curriculum_list({"01-styled-cards"}))


if __name__ == "__main__":
    unittest.main()
