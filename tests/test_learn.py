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
        self.assertGreaterEqual(len(LESSONS), 12)
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
                self.assertIn("1/12 completed", buf.getvalue())
                self.assertIn("[✓]  1.", buf.getvalue())

        lesson = LESSONS[0]
        ebuf = NanaBuffer(lines=lesson.starter.splitlines())
        res = evaluate_lesson(lesson, lesson.starter)
        wide = render_learn_workspace(lesson, ebuf, res, 1, set(), 28, 100, bg_mode="mica")
        self.assertNotIn("\n", wide)
        self.assertNotIn("\x1b[7m", wide)
        self.assertIn("\x1b[49m", wide)
        self.assertIn("Challenge:", wide)
        self.assertIn("Hint:", wide)

        narrow = render_learn_workspace(lesson, ebuf, res, 0, set(), 14, 48, bg_mode="black")
        self.assertNotIn("\n", narrow)
        self.assertNotIn("\x1b[7m", narrow)
        self.assertIn("\x1b[40;48;2;0;0;0m", narrow)
        self.assertIn("Goal:", narrow)

        cmap = render_lesson_map(0, {"01-styled-cards"}, 24, 90, bg_mode="mica")
        self.assertNotIn("\n", cmap)
        self.assertIn("SayLang Interactive Course", cmap)
        self.assertIn("8%", format_curriculum_list({"01-styled-cards"}))

    @unittest.skipIf(sys.platform == "win32", "POSIX PTY end-to-end test")
    def test_learn_pty_arrow_keys_and_mouse_support(self) -> None:
        import fcntl
        import pty
        import re
        import select
        import struct
        import termios
        import time

        ansi_re = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
        master_fd, slave_fd = pty.openpty()
        fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
        with tempfile.TemporaryDirectory() as home_dir:
            env = dict(os.environ, SAYLANG_HOME=home_dir)
            proc = subprocess.Popen(
                [sys.executable, "-m", "saylang", "learn"],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=env,
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
                raw_init, plain_init = drain_until_plain("SayLang Interactive Course")
                self.assertIn(b"\x1b[?1006h", raw_init)
                self.assertIn("SayLang Interactive Course", plain_init)

                # Down arrow in map moves selection cleanly without exiting
                os.write(master_fd, b"\x1b[B")
                _, plain_down = drain_until_plain("▌ ○  2.")
                self.assertIsNone(proc.poll(), "learn exited prematurely on Down arrow")
                self.assertIn("▌ ○  2.", plain_down)

                # SGR mouse wheel down -> moves to lesson 3
                os.write(master_fd, b"\x1b[<65;20;8M")
                _, plain_wheel = drain_until_plain("▌ ○  3.")
                self.assertIsNone(proc.poll())
                self.assertIn("▌ ○  3.", plain_wheel)

                # SGR click lesson 1 row (row 7) -> opens Lesson 1 workspace
                os.write(master_fd, b"\x1b[<0;20;7M\x1b[<0;20;7m")
                _, plain_ws = drain_until_plain("LEARN 1/12")
                self.assertIn("LEARN 1/12", plain_ws)

                # Arrow key burst inside Lesson 1 editor must move cursor, NOT insert [D/[A/[B/[C
                os.write(master_fd, b"\x1b[D\x1b[A\x1b[B\x1b[C\x1b[B\x1b[C")
                _, plain_burst = drain_until_plain("Ln 3, Col 2")
                self.assertNotIn("[D", plain_burst)
                self.assertNotIn("[A", plain_burst)
                self.assertNotIn("[C", plain_burst)
                self.assertNotIn("│ [B", plain_burst)
                self.assertIn('1 │ set hero to "SayLang"', plain_burst)
                self.assertIn("Ln 3, Col 2", plain_burst)

                # Mouse click on line 3 col 5 in wide workspace (code_start_col = 46+1+6+1 = 54 -> col 58, row 5)
                os.write(master_fd, b"\x1b[<0;58;5M\x1b[<0;58;5m")
                _, plain_click = drain_until_plain("Ln 3, Col 5")
                self.assertIn("Ln 3, Col 5", plain_click)

                # Clean exit with Ctrl+X
                os.write(master_fd, b"\x18")
                rc, tail = wait_exit()
                self.assertEqual(rc, 0)
                self.assertIn(b"\x1b[?1006l", tail)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=2.0)
                os.close(master_fd)

    @unittest.skipIf(sys.platform == "win32", "POSIX PTY end-to-end test")
    def test_mouse_tui_calculator_and_live_centered_clock_pty(self) -> None:
        import fcntl
        import pty
        import re
        import select
        import struct
        import termios
        import time

        ansi_re = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

        # 1. Mouse TUI Calculator (real SGR mouse clicks on centered 4-col grid)
        with tempfile.TemporaryDirectory() as pty_tmp:
            calc_file = Path(pty_tmp) / "calc.pl"
            calc_file.write_text(LESSONS[10].solution, encoding="utf-8")
            mfd, sfd = pty.openpty()
            fcntl.ioctl(sfd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 110, 0, 0))
            proc = subprocess.Popen(
                [sys.executable, "-m", "saylang", str(calc_file)],
                stdin=sfd,
                stdout=sfd,
                stderr=sfd,
                cwd=str(Path(__file__).resolve().parent.parent),
                close_fds=True,
            )
            os.close(sfd)

            def drain_until_plain(fd: int, marker: str, timeout_s: float = 2.0) -> tuple[bytes, str]:
                buf = bytearray()
                dl = time.monotonic() + timeout_s
                while time.monotonic() < dl:
                    if select.select([fd], [], [], 0.04)[0]:
                        try:
                            d = os.read(fd, 4096)
                            if d:
                                buf.extend(d)
                        except OSError:
                            break
                    plain = ansi_re.sub("", buf.decode("utf-8", errors="replace"))
                    if marker in plain:
                        return bytes(buf), plain
                return bytes(buf), ansi_re.sub("", buf.decode("utf-8", errors="replace"))

            try:
                raw0, p0 = drain_until_plain(mfd, "[ Q ]")
                self.assertIn(b"\x1b[?1006h", raw0)
                self.assertIn("Calc:", p0)

                for label, col, row, expect in [
                    ("7", 46, 13, "Calc: 7"),
                    ("+", 64, 16, "Calc: 7+"),
                    ("5", 52, 14, "Calc: 7+5"),
                    ("=", 58, 16, "Calc: 12"),
                ]:
                    os.write(mfd, f"\x1b[<0;{col};{row}M\x1b[<0;{col};{row}m".encode())
                    _, px = drain_until_plain(mfd, expect)
                    self.assertIn(expect, px, f"Mouse click on {label} did not update {expect}")

                os.write(mfd, b"\x1b[<0;46;17M\x1b[<0;46;17m")  # Click "Q"
                _, pend = drain_until_plain(mfd, "Result: 12")
                self.assertIn("Result: 12", pend)
                rc = proc.wait(timeout=3.0)
                self.assertEqual(rc, 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=2.0)
                os.close(mfd)

            # 2. Live centered clock (`pos center` + `time --live`)
            clock_file = Path(pty_tmp) / "clock.pl"
            clock_file.write_text(
                "import time, ascii\n"
                "pos center\n"
                "print time --12h --live --interval 0.05 --frames 2 | ascii --size small colour cyan\n"
                "print date below time\n",
                encoding="utf-8",
            )
            mfd2, sfd2 = pty.openpty()
            fcntl.ioctl(sfd2, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            proc2 = subprocess.Popen(
                [sys.executable, "-m", "saylang", str(clock_file)],
                stdin=sfd2,
                stdout=sfd2,
                stderr=sfd2,
                cwd=str(Path(__file__).resolve().parent.parent),
                close_fds=True,
            )
            os.close(sfd2)
            raw_out = bytearray()
            try:
                dl = time.monotonic() + 3.0
                while time.monotonic() < dl:
                    if select.select([mfd2], [], [], 0.05)[0]:
                        try:
                            d = os.read(mfd2, 4096)
                            if d:
                                raw_out.extend(d)
                        except OSError:
                            pass
                    if proc2.poll() is not None:
                        break
                rc2 = proc2.wait(timeout=2.0)
                self.assertEqual(rc2, 0)
                txt = bytes(raw_out).decode("utf-8", errors="replace")
                self.assertIn("\x1b[?25l", txt)
                self.assertIn("\x1b[2J\x1b[H", txt)
                self.assertIn("█", txt)
                self.assertIn("\x1b[?25h", txt)
            finally:
                if proc2.poll() is None:
                    proc2.kill()
                    proc2.wait(timeout=2.0)
                os.close(mfd2)


if __name__ == "__main__":
    unittest.main()
