"""Command-line interface for the SayLang programming language."""

from __future__ import annotations

import argparse
import pprint
import subprocess
import sys
import tempfile
from pathlib import Path

from saylang import __version__
from saylang.ast_nodes import FlagsDeclStmt
from saylang.banner import render_startup_banner
from saylang.errors import SayError
from saylang.interpreter import run_source
from saylang.learn import run_learn
from saylang.nana import run_nana
from saylang.parser import parse_source
from saylang.repl import SayREPL
from saylang.runtime import say_configure_utf8_stdio
from saylang.translator import translate_english
from saylang.transpiler import compile_to_python

_SUBCOMMANDS = {"run", "compile", "check", "ast", "english", "repl", "banner", "nana", "learn"}


def _read_source(path_str: str) -> str:
    path = Path(path_str)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path_str}")
    return path.read_text(encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saylang",
        description="SayLang: a readable, bracket-free plain-English programming language.",
    )
    parser.add_argument(
        "--version", action="version", version=f"saylang {__version__}"
    )

    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run a .pl SayLang source file.")
    p_run.add_argument("file", help="Path to the .pl file")
    p_run.add_argument(
        "script_args", nargs=argparse.REMAINDER, help="Flags forwarded to the script"
    )

    p_compile = sub.add_parser("compile", help="Transpile a .pl file to Python.")
    p_compile.add_argument("file", help="Path to the .pl file")
    p_compile.add_argument(
        "-o", "--output", help="Write compiled Python to this file"
    )
    p_compile.add_argument(
        "--run",
        action="store_true",
        dest="run_compiled",
        help="Execute the compiled Python code after transpiling",
    )

    p_check = sub.add_parser("check", help="Check a .pl file for syntax errors.")
    p_check.add_argument("file", help="Path to the .pl file")

    p_ast = sub.add_parser("ast", help="Print the parsed AST of a .pl file.")
    p_ast.add_argument("file", help="Path to the .pl file")

    p_eng = sub.add_parser(
        "english",
        help="Translate everyday English prose (or a text file) into SayLang.",
    )
    p_eng.add_argument("input", help="English instruction string or path to a text file")
    p_eng.add_argument(
        "--provider",
        default="auto",
        choices=["auto", "offline", "gemini", "openai", "anthropic"],
        help="Translation backend (default: auto)",
    )
    p_eng.add_argument("--model", help="Optional LLM model override")
    p_eng.add_argument("-o", "--output", help="Write translated SayLang code to a file")
    p_eng.add_argument(
        "--run", action="store_true", help="Run the translated SayLang program"
    )
    p_eng.add_argument(
        "--compile",
        action="store_true",
        help="Print compiled Python instead of SayLang",
    )

    p_nana = sub.add_parser(
        "nana", help="Open the built-in SayLang text editor (nana)."
    )
    p_nana.add_argument("file", nargs="?", help="Optional .pl file to edit")

    p_learn = sub.add_parser(
        "learn", help="Start the interactive freeCodeCamp-style SayLang TUI course."
    )
    p_learn.add_argument(
        "lesson", nargs="?", type=int, help="Optional lesson number (1-10) to open"
    )
    p_learn.add_argument(
        "--list", action="store_true", dest="list_only", help="List curriculum and progress"
    )
    p_learn.add_argument(
        "--reset", action="store_true", help="Reset saved course progress"
    )

    sub.add_parser("repl", help="Start the interactive SayLang REPL.")
    sub.add_parser("banner", help="Print the SayLang startup icon banner.")
    return parser


def _print_script_flag_help(file_path: str, source: str) -> bool:
    """If the script declares `flags:`, print flag usage and return True."""
    program = parse_source(source)
    declared: list[str] = []
    for stmt in program.statements:
        if isinstance(stmt, FlagsDeclStmt):
            declared.extend(stmt.flags)
    if not declared:
        return False
    print(f"Usage: saylang {file_path} [{' '.join(declared)}]")
    print("Declared flags:")
    for f in declared:
        print(f"  {f}")
    return True


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    say_configure_utf8_stdio()
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Shorthand: `saylang path/to/file.pl [-d ...]` -> `saylang run path/to/file.pl [-d ...]`
    if raw_args and not raw_args[0].startswith("-") and raw_args[0] not in _SUBCOMMANDS:
        raw_args = ["run", *raw_args]

    # Split forwarded script flags when running `saylang run <file.pl> [script_args...]`
    forwarded_script_args: list[str] = []
    if len(raw_args) >= 2 and raw_args[0] == "run" and not raw_args[1].startswith("-"):
        forwarded_script_args = raw_args[2:]
        raw_args = raw_args[:2]

    parser = _build_parser()
    args = parser.parse_args(raw_args)

    if args.command is None or args.command == "repl":
        return SayREPL().run()

    if args.command == "banner":
        is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        print(render_startup_banner(__version__, color=is_tty))
        return 0

    if args.command == "nana":
        return run_nana(args.file)

    if args.command == "learn":
        return run_learn(args.lesson, list_only=args.list_only, reset=args.reset)

    try:
        if args.command == "run":
            source = _read_source(args.file)
            script_args = forwarded_script_args or list(getattr(args, "script_args", []))
            if any(a in ("-h", "--help") for a in script_args):
                if _print_script_flag_help(args.file, source):
                    return 0
            run_source(source, cli_args=script_args)
            return 0

        if args.command == "check":
            source = _read_source(args.file)
            parse_source(source)
            print(f"OK: {args.file}")
            return 0

        if args.command == "ast":
            source = _read_source(args.file)
            program = parse_source(source)
            print(pprint.pformat(program, width=88))
            return 0

        if args.command == "compile":
            source = _read_source(args.file)
            py_code = compile_to_python(source, standalone=True)
            if args.output:
                Path(args.output).write_text(py_code, encoding="utf-8")
            elif not args.run_compiled:
                sys.stdout.write(py_code)

            if args.run_compiled:
                if args.output:
                    proc = subprocess.run([sys.executable, args.output], check=False)
                    return proc.returncode
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".py", encoding="utf-8", delete=True
                ) as tmp:
                    tmp.write(py_code)
                    tmp.flush()
                    proc = subprocess.run([sys.executable, tmp.name], check=False)
                    return proc.returncode
            return 0

        if args.command == "english":
            candidate_path = Path(args.input)
            eng_text = (
                candidate_path.read_text(encoding="utf-8")
                if candidate_path.is_file()
                else args.input
            )
            res = translate_english(
                eng_text, provider=args.provider, model=args.model
            )
            if args.output:
                Path(args.output).write_text(
                    res.say_code + "\n", encoding="utf-8"
                )
            if args.compile:
                sys.stdout.write(compile_to_python(res.say_code, standalone=True))
            else:
                print(res.say_code)
            if args.run:
                print("--- output ---")
                run_source(res.say_code)
            return 0

    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SayError as err:
        filename = getattr(args, "file", "<input>")
        print(err.format_pretty(filename), file=sys.stderr)
        return 1

    return 0
