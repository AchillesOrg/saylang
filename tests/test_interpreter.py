"""Tests for the SayLang tree-walking interpreter."""

import tempfile
import unittest
from pathlib import Path

from saylang.errors import SayRuntimeError
from saylang.interpreter import run_and_capture


class TestInterpreter(unittest.TestCase):
    def test_arithmetic_and_text_coercion(self) -> None:
        src = (
            "set a to 10\n"
            "set b to 3\n"
            "say a plus b\n"
            "say a minus b\n"
            "say a times b\n"
            "say 10 divided by 2\n"
            "say a whole divided by b\n"
            "say a modulo b\n"
            "say 2 to the power of 4\n"
            'say "Score: " plus a\n'
            "say negative 5\n"
        )
        out, _ = run_and_capture(src)
        self.assertEqual(
            out.splitlines(),
            ["13", "7", "30", "5", "3", "1", "16", "Score: 10", "-5"],
        )

    def test_boolean_and_comparison_operators(self) -> None:
        src = (
            "set items to a list of 1, 2, 3\n"
            "say 1 is true\n"
            "say true is yes\n"
            "say false is no\n"
            "say 2 is in items\n"
            "say 9 is not in items\n"
            'say "hello" starts with "he"\n'
            'say "hello" ends with "lo"\n'
            'say "hello" contains "ell"\n'
            'say "hello" does not contain "xyz"\n'
        )
        out, _ = run_and_capture(src)
        self.assertEqual(
            out.splitlines(),
            ["false", "true", "true", "true", "true", "true", "true", "true", "true"],
        )

    def test_loops_stop_and_skip(self) -> None:
        src = (
            "for each i from 1 to 6\n"
            "    if i is 2\n"
            "        skip\n"
            "    if i is 5\n"
            "        stop\n"
            "    say i\n"
            "for each down from 3 to 1\n"
            "    say down\n"
            "set x to 0\n"
            "while x is less than 3\n"
            "    increase x\n"
            "say x\n"
        )
        out, _ = run_and_capture(src)
        self.assertEqual(out.splitlines(), ["1", "3", "4", "3", "2", "1", "3"])

    def test_functions_recursion_and_closures(self) -> None:
        src = (
            "to fact with n\n"
            "    if n is at most 1\n"
            "        return 1\n"
            "    set sub to call fact with n minus 1\n"
            "    give back n times sub\n"
            "\n"
            "set base to 100\n"
            "to add_base with x\n"
            "    return base plus x\n"
            "\n"
            "say call fact with 5\n"
            "say call add_base with 7\n"
        )
        out, _ = run_and_capture(src)
        self.assertEqual(out.splitlines(), ["120", "107"])

    def test_lists_maps_and_1_based_indexing(self) -> None:
        src = (
            "set nums to a list of 30, 10, 20\n"
            "say first item of nums\n"
            "say last item of nums\n"
            "say item 2 of nums\n"
            "set item 2 of nums to 99\n"
            "add 40 to nums\n"
            "remove item 1 of nums\n"
            'say joined sorted nums with "-"\n'
            'set user to a map with name as "Ada", score as 10\n'
            "increase user's score by 5\n"
            'set user\'s role to "admin"\n'
            'say user\'s name, ":", user\'s score, ":", user\'s role\n'
            'remove entry "role" from user\n'
            "say length of keys of user\n"
        )
        out, _ = run_and_capture(src)
        self.assertEqual(
            out.splitlines(),
            ["30", "20", "10", "20-40-99", "Ada:15:admin", "2"],
        )

    def test_colored_and_styled_say_output(self) -> None:
        src = (
            'say "hello world lol" colour red\n'
            'say "hi" color blue bold\n'
            'say "ok" in bright green underline\n'
            'set c to "cyan"\n'
            'say "dyn" colour c on black\n'
            'say "plain"\n'
        )
        out, _ = run_and_capture(src)
        self.assertEqual(
            out.splitlines(),
            [
                "\x1b[31mhello world lol\x1b[0m",
                "\x1b[1;34mhi\x1b[0m",
                "\x1b[4;92mok\x1b[0m",
                "\x1b[36;40mdyn\x1b[0m",
                "plain",
            ],
        )

        with self.assertRaises(SayRuntimeError):
            run_and_capture('say "oops" colour "ultraviolet"\n')

    def test_builtins_ask_and_file_io(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fpath = Path(tmpdir) / "notes.txt"
            src = (
                f'write "  Hello SayLang  " to file "{fpath}"\n'
                f'append "\\nSecond Line" to file "{fpath}"\n'
                f'set raw to read file "{fpath}"\n'
                "set lines_list to lines of raw\n"
                "say trimmed first item of lines_list\n"
                'say uppercase of "abc", " ", lowercase of "XYZ"\n'
                'say square root of 9, " ", absolute of negative 4, " ", rounded 3.6\n'
                'say number of "42" plus 1\n'
                "say type of a list of 1\n"
                'set ans to ask "Name? "\n'
                'say "Hi ", ans\n'
            )
            out, _ = run_and_capture(src, input_lines=["Grace"])
            self.assertEqual(
                out.splitlines(),
                ["Hello SayLang", "ABC xyz", "3 4 4", "43", "list", "Name? Hi Grace"],
            )

    def test_try_fail_and_runtime_errors(self) -> None:
        src = (
            "try\n"
            '    fail with "custom boom"\n'
            "if it fails with msg\n"
            "    say msg\n"
        )
        out, _ = run_and_capture(src)
        self.assertEqual(out.splitlines(), ["custom boom"])

        with self.assertRaises(SayRuntimeError):
            run_and_capture("say 10 divided by 0\n")

        with self.assertRaises(SayRuntimeError) as ctx:
            run_and_capture("set hello to hi\n")
        self.assertIn("wrap it in quotes", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
