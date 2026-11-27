"""Interactive multiline REPL for SayLang."""

from __future__ import annotations

import pprint
import sys
from collections.abc import Callable
from typing import TextIO

from saylang import __version__
from saylang.errors import SayError
from saylang.interpreter import Interpreter
from saylang.parser import parse_source
from saylang.translator import translate_english
from saylang.transpiler import compile_to_python

_BLOCK_OPENERS = (
    "if ",
    "otherwise",
    "else",
    "repeat ",
    "for each ",
    "while ",
    "to ",
    "try",
)


def _opens_block(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    lower = s.lower()
    if lower.endswith(":"):
        return True
    if lower == "try" or lower.startswith("try:"):
        return True
    return any(lower.startswith(prefix) for prefix in _BLOCK_OPENERS)


_HELP_TEXT = """SayLang REPL commands:
  :help             Show this help message
  :vars             List defined variables and functions
  :py               Show compiled Python for the last snippet
  :ast              Show parsed AST for the last snippet
  :english <text>   Translate everyday English to SayLang and run it
  :reset            Clear all variables and functions
  :quit             Exit the REPL

Multi-line blocks (if, repeat, for each, while, to, try):
  Indent block bodies with spaces, then press Enter on a blank line to run."""


class SayREPL:
    """Interactive read-eval-print loop for SayLang."""

    def __init__(
        self,
        *,
        stdout: TextIO | None = None,
        input_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.stdout = stdout if stdout is not None else sys.stdout
        self.input_fn = input_fn if input_fn is not None else input
        self.interpreter = Interpreter(stdout=self.stdout, input_fn=self.input_fn)
        self.last_source: str = ""

    def _write(self, text: str) -> None:
        self.stdout.write(text + "\n")

    def _run_snippet(self, source: str) -> None:
        program = parse_source(source)
        self.last_source = source
        self.interpreter.run(program, source=source)

    def _handle_command(self, line: str) -> bool:
        """Handle a ':' REPL command. Return False to quit."""
        cmd, _, arg = line.strip().partition(" ")
        cmd_lower = cmd.lower()

        if cmd_lower in (":quit", ":exit", ":q"):
            return False
        if cmd_lower in (":help", ":h"):
            self._write(_HELP_TEXT)
            return True
        if cmd_lower == ":reset":
            self.interpreter = Interpreter(stdout=self.stdout, input_fn=self.input_fn)
            self.last_source = ""
            self._write("Workspace reset.")
            return True
        if cmd_lower == ":vars":
            if not self.interpreter.global_env.values:
                self._write("(no variables defined)")
            else:
                for name, val in self.interpreter.global_env.values.items():
                    self._write(f"  {name} = {val!r}")
            return True
        if cmd_lower == ":py":
            if not self.last_source:
                self._write("Nothing has been run yet.")
            else:
                self._write(compile_to_python(self.last_source, standalone=False))
            return True
        if cmd_lower == ":ast":
            if not self.last_source:
                self._write("Nothing has been run yet.")
            else:
                prog = parse_source(self.last_source)
                self._write(pprint.pformat(prog, width=88))
            return True
        if cmd_lower == ":english":
            if not arg.strip():
                self._write("Usage: :english <everyday english instruction>")
                return True
            try:
                res = translate_english(arg.strip())
                self._write(f"[saylang ({res.backend})]")
                for pline in res.say_code.splitlines():
                    self._write(f"  {pline}")
                self._run_snippet(res.say_code)
            except SayError as err:
                self._write(err.format_pretty("<english>"))
            return True

        self._write(f"Unknown command '{cmd}'. Type :help for commands.")
        return True

    def run(self) -> int:
        """Run the interactive REPL loop until exit or EOF."""
        try:
            import readline  # noqa: F401
        except ImportError:
            pass

        self._write(f"SayLang {__version__} — type :help for commands, :quit to exit.")
        buffer: list[str] = []
        in_block = False

        while True:
            prompt = "... " if in_block else "saylang> "
            try:
                line = self.input_fn(prompt)
            except EOFError:
                if buffer:
                    try:
                        self._run_snippet("\n".join(buffer))
                    except SayError as err:
                        self._write(err.format_pretty("<repl>"))
                self._write("")
                return 0
            except KeyboardInterrupt:
                self._write("")
                buffer.clear()
                in_block = False
                continue

            if not in_block:
                if not line.strip():
                    continue
                if line.lstrip().startswith(":"):
                    if not self._handle_command(line):
                        return 0
                    continue
                if _opens_block(line):
                    buffer = [line]
                    in_block = True
                    continue
                try:
                    self._run_snippet(line)
                except SayError as err:
                    self._write(err.format_pretty("<repl>"))
                continue

            if not line.strip():
                snippet = "\n".join(buffer)
                buffer.clear()
                in_block = False
                try:
                    self._run_snippet(snippet)
                except SayError as err:
                    self._write(err.format_pretty("<repl>"))
            else:
                buffer.append(line)
