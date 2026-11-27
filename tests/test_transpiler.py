"""Tests for the SayLang-to-Python transpiler and interpreter parity."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from saylang.interpreter import run_and_capture
from saylang.transpiler import compile_to_python

_EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _run_compiled_python(say_source: str) -> str:
    py_code = compile_to_python(say_source, standalone=True)
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
        return proc.stdout


class TestTranspiler(unittest.TestCase):
    def test_all_examples_match_interpreter_output(self) -> None:
        example_files = sorted(_EXAMPLES_DIR.glob("*.pl"))
        self.assertGreaterEqual(len(example_files), 5)
        for path in example_files:
            with self.subTest(example=path.name):
                src = path.read_text(encoding="utf-8")
                if path.name in ("live_clock.pl", "clock.pl"):
                    py_code = compile_to_python(src, standalone=True)
                    self.assertIn("say_lib_call", py_code)
                    continue
                interp_out, _ = run_and_capture(src)
                compiled_out = _run_compiled_python(src)
                self.assertEqual(compiled_out, interp_out)

    def test_python_keywords_and_builtins_as_saylang_names(self) -> None:
        src = (
            'set class to "math"\n'
            "set from to 10\n"
            "set list to a list of 1, 2, 3\n"
            "to len with items\n"
            "    return length of items\n"
            'say class, " ", from, " ", call len with list\n'
        )
        interp_out, _ = run_and_capture(src)
        compiled_out = _run_compiled_python(src)
        self.assertEqual(compiled_out, "math 10 3\n")
        self.assertEqual(compiled_out, interp_out)

    def test_colored_say_and_complex_parity(self) -> None:
        src = (
            'say "hello world lol" colour red bold\n'
            'set hue to "cyan"\n'
            'say "dynamic" color hue on black underline\n'
            "set cart to a list of 10, 20\n"
            "add 30 to cart\n"
            "increase item 1 of cart by 5\n"
            "remove 20 from cart\n"
            'say joined cart with ", "\n'
            "try\n"
            "    say 1 divided by 0\n"
            "if it fails with err\n"
            '    say "caught: ", err\n'
            "set box to a map with count as 1\n"
            "increase box's count by 4\n"
            "say box's count\n"
        )
        interp_out, _ = run_and_capture(src)
        compiled_out = _run_compiled_python(src)
        self.assertEqual(compiled_out, interp_out)


if __name__ == "__main__":
    unittest.main()
