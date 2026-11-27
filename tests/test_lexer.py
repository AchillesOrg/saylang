"""Tests for the SayLang indentation-aware lexer."""

import unittest

from saylang.errors import SayLexError
from saylang.lexer import tokenize
from saylang.tokens import TokenType


class TestLexer(unittest.TestCase):
    def test_indentation_and_dedentation(self) -> None:
        src = "if true\n    say 1\n    if false\n        say 2\nsay 3\n"
        types = [t.type for t in tokenize(src)]
        self.assertEqual(
            types,
            [
                TokenType.WORD,
                TokenType.WORD,
                TokenType.NEWLINE,
                TokenType.INDENT,
                TokenType.WORD,
                TokenType.NUMBER,
                TokenType.NEWLINE,
                TokenType.WORD,
                TokenType.WORD,
                TokenType.NEWLINE,
                TokenType.INDENT,
                TokenType.WORD,
                TokenType.NUMBER,
                TokenType.NEWLINE,
                TokenType.DEDENT,
                TokenType.DEDENT,
                TokenType.WORD,
                TokenType.NUMBER,
                TokenType.NEWLINE,
                TokenType.EOF,
            ],
        )

    def test_hash_and_note_comments_ignored(self) -> None:
        src = (
            "\n"
            "# full line hash comment\n"
            "note this is a prose comment\n"
            "note: with colon too\n"
            "  # indented hash comment\n"
            "set notebook to 42 # inline comment\n"
        )
        tokens = tokenize(src)
        words = [t.value for t in tokens if t.type == TokenType.WORD]
        self.assertEqual(words, ["set", "notebook", "to"])
        nums = [t.value for t in tokens if t.type == TokenType.NUMBER]
        self.assertEqual(nums, [42])

    def test_possessive_vs_single_quoted_strings(self) -> None:
        src = "say user's name\nsay 'hello world'\n"
        tokens = tokenize(src)
        self.assertIn(TokenType.POSSESSIVE, [t.type for t in tokens])
        strings = [t.value for t in tokens if t.type == TokenType.STRING]
        self.assertEqual(strings, ["hello world"])

    def test_numbers_and_optional_trailing_period(self) -> None:
        src = "set pi to 3.14.\nset count to 7.\n"
        tokens = tokenize(src)
        nums = [t.value for t in tokens if t.type == TokenType.NUMBER]
        self.assertEqual(nums, [3.14, 7])

    def test_mismatched_dedent_raises_lex_error(self) -> None:
        src = "if true\n    say 1\n  say 2\n"
        with self.assertRaises(SayLexError) as ctx:
            tokenize(src)
        self.assertEqual(ctx.exception.line, 3)

    def test_unterminated_string_raises_lex_error(self) -> None:
        with self.assertRaises(SayLexError):
            tokenize('say "oops')

    def test_unexpected_symbol_raises_lex_error(self) -> None:
        with self.assertRaises(SayLexError):
            tokenize("set x to [1, 2]")


if __name__ == "__main__":
    unittest.main()
