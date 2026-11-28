"""SayLang: a readable, bracket-free plain-English programming language."""

from saylang.banner import render_startup_banner
from saylang.errors import (
    SayError,
    SayLexError,
    SayParseError,
    SayRuntimeError,
    SayTranslateError,
)
from saylang.interpreter import Interpreter, run_program, run_source
from saylang.lexer import tokenize
from saylang.parser import parse_source
from saylang.translator import TranslationResult, translate_english
from saylang.transpiler import compile_to_python

__all__ = [
    "Interpreter",
    "SayError",
    "SayLexError",
    "SayParseError",
    "SayRuntimeError",
    "SayTranslateError",
    "TranslationResult",
    "compile_to_python",
    "parse_source",
    "render_startup_banner",
    "run_program",
    "run_source",
    "tokenize",
    "translate_english",
]

__version__ = "0.3.4"
