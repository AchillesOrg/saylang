"""Command-line interface for the SayLang programming language."""

from __future__ import annotations

import argparse
import pprint
import subprocess
import sys
import tempfile
from pathlib import Path

from saylang import __version__
from saylang.banner import render_startup_banner
from saylang.errors import SayError
from saylang.interpreter import run_source
from saylang.parser import parse_source
from saylang.repl import SayREPL
from saylang.translator import translate_english
from saylang.transpiler import compile_to_python

_SUBCOMMANDS = {"run", "compile", "check", "ast", "english", "repl", "banner"}


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

    sub.add_parser("repl", help="Start the interactive SayLang REPL.")
    sub.add_parser("banner", help="Print the SayLang startup icon banner.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    raw_args = list(sys.argv[1:] if argv is None else argv)

    # Shorthand: `saylang path/to/file.pl` -> `saylang run path/to/file.pl`
    if raw_args and not raw_args[0].startswith("-") and raw_args[0] not in _SUBCOMMANDS:
        raw_args = ["run", *raw_args]

    parser = _build_parser()
    args = parser.parse_args(raw_args)

    if args.command is None or args.command == "repl":
        return SayREPL().run()

    if args.command == "banner":
        is_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
        print(render_startup_banner(__version__, color=is_tty))
        return 0

    try:
        if args.command == "run":
            source = _read_source(args.file)
            run_source(source)
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

    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SayError as err:
        filename = getattr(args, "file", "<input>")
        print(err.format_pretty(filename), file=sys.stderr)
        return 1

    return 0
