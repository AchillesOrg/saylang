"""Tests for the SayLang recursive-descent parser."""

import unittest

from saylang.ast_nodes import (
    BinaryOp,
    BuiltinExpr,
    CompareOp,
    FieldAccess,
    ForEachStmt,
    ForRangeStmt,
    FuncDefStmt,
    IfStmt,
    ListLiteral,
    Literal,
    MapLiteral,
    RepeatStmt,
    SayStmt,
    SetStmt,
    TryStmt,
    Var,
)
from saylang.errors import SayParseError
from saylang.parser import parse_source


class TestParser(unittest.TestCase):
    def test_operator_precedence(self) -> None:
        prog = parse_source("set x to 2 plus 3 times 4\n")
        stmt = prog.statements[0]
        assert isinstance(stmt, SetStmt)
        assert isinstance(stmt.value, BinaryOp)
        self.assertEqual(stmt.value.op, "+")
        assert isinstance(stmt.value.right, BinaryOp)
        self.assertEqual(stmt.value.right.op, "*")

    def test_power_right_associative(self) -> None:
        prog = parse_source("set x to 2 to the power of 3 to the power of 2\n")
        stmt = prog.statements[0]
        assert isinstance(stmt, SetStmt)
        assert isinstance(stmt.value, BinaryOp)
        self.assertEqual(stmt.value.op, "**")
        assert isinstance(stmt.value.right, BinaryOp)
        self.assertEqual(stmt.value.right.op, "**")

    def test_multiword_comparisons_and_booleans(self) -> None:
        prog = parse_source(
            'if the score is at least 10 and not done\n    say "ok"\n'
        )
        stmt = prog.statements[0]
        assert isinstance(stmt, IfStmt)
        cond = stmt.branches[0].condition
        assert isinstance(cond, BinaryOp)
        self.assertEqual(cond.op, "and")
        assert isinstance(cond.left, CompareOp)
        self.assertEqual(cond.left.op, ">=")

    def test_lists_and_maps_with_oxford_and(self) -> None:
        prog = parse_source(
            'set items to a list of x is 1 and y is 2, "end"\n'
            'set person to a map with name as "Ada", and age as 36\n'
        )
        s0, s1 = prog.statements
        assert isinstance(s0, SetStmt) and isinstance(s0.value, ListLiteral)
        self.assertEqual(len(s0.value.elements), 2)
        assert isinstance(s1, SetStmt) and isinstance(s1.value, MapLiteral)
        self.assertEqual(len(s1.value.pairs), 2)

    def test_repeat_times_vs_multiply_times(self) -> None:
        prog = parse_source("repeat 2 times 3 times with i:\n    say i\n")
        stmt = prog.statements[0]
        assert isinstance(stmt, RepeatStmt)
        self.assertEqual(stmt.var_name, "i")
        assert isinstance(stmt.count, BinaryOp)
        self.assertEqual(stmt.count.op, "*")

    def test_for_each_variants(self) -> None:
        prog = parse_source(
            "for each i from 1 to 10 by 2:\n    say i\n"
            "for each k and v in scores\n    say k\n"
            "for each item in items\n    say item\n"
        )
        self.assertIsInstance(prog.statements[0], ForRangeStmt)
        self.assertIsInstance(prog.statements[1], ForEachStmt)
        self.assertEqual(prog.statements[1].value_var_name, "v")  # type: ignore[attr-defined]
        self.assertIsInstance(prog.statements[2], ForEachStmt)

    def test_function_possessive_and_try(self) -> None:
        prog = parse_source(
            "to greet with first and second:\n"
            "    say first, second\n"
            "try\n"
            "    set x to user's profile's name\n"
            "if it fails with err\n"
            "    say length of err\n"
        )
        fn = prog.statements[0]
        assert isinstance(fn, FuncDefStmt)
        self.assertEqual(fn.params, ["first", "second"])
        tr = prog.statements[1]
        assert isinstance(tr, TryStmt)
        self.assertEqual(tr.error_var, "err")
        assert isinstance(tr.try_body[0], SetStmt)
        assert isinstance(tr.try_body[0].value, FieldAccess)
        assert isinstance(tr.catch_body[0], SayStmt)
        assert isinstance(tr.catch_body[0].values[0], BuiltinExpr)

    def test_sorted_as_variable_or_builtin(self) -> None:
        prog = parse_source(
            "set sorted to true\n"
            "set nums to sorted of a list of 3, 1, 2\n"
            "set nums2 to sorted nums\n"
        )
        self.assertEqual(len(prog.statements), 3)
        assert isinstance(prog.statements[1], SetStmt)
        self.assertIsInstance(prog.statements[1].value, BuiltinExpr)
        assert isinstance(prog.statements[2], SetStmt)
        self.assertIsInstance(prog.statements[2].value, BuiltinExpr)

    def test_colored_say_modifiers_and_variable_colour(self) -> None:
        prog = parse_source(
            'say "hello world lol" colour red\n'
            'say "hi", name color blue bold\n'
            'say "score" in bright green underline\n'
            'say "alert" colour white on red bold\n'
            'say "dyn" colour my_color\n'
            "say colour\n"
        )
        s0, s1, s2, s3, s4, s5 = prog.statements
        assert isinstance(s0, SayStmt)
        assert isinstance(s0.color, Literal)
        self.assertEqual(s0.color.value, "red")

        assert isinstance(s1, SayStmt)
        assert isinstance(s1.color, Literal)
        self.assertEqual(s1.color.value, "blue")
        self.assertEqual(s1.styles, ["bold"])

        assert isinstance(s2, SayStmt)
        assert isinstance(s2.color, Literal)
        self.assertEqual(s2.color.value, "bright green")
        self.assertEqual(s2.styles, ["underline"])

        assert isinstance(s3, SayStmt)
        assert isinstance(s3.color, Literal) and s3.color.value == "white"
        assert isinstance(s3.background, Literal) and s3.background.value == "red"
        self.assertEqual(s3.styles, ["bold"])

        assert isinstance(s4, SayStmt)
        assert isinstance(s4.color, Var) and s4.color.name == "my_color"

        assert isinstance(s5, SayStmt)
        self.assertIsNone(s5.color)
        assert isinstance(s5.values[0], Var) and s5.values[0].name == "colour"

    def test_missing_indent_raises_parse_error(self) -> None:
        with self.assertRaises(SayParseError) as ctx:
            parse_source("if true\nsay 1\n")
        self.assertIn("indented block", ctx.exception.message)

    def test_ergonomic_set_without_to_and_run_statement(self) -> None:
        prog = parse_source('set hello "hi"\nrun say hello\n')
        self.assertEqual(len(prog.statements), 2)
        s0, s1 = prog.statements
        assert isinstance(s0, SetStmt)
        assert isinstance(s0.value, Literal) and s0.value.value == "hi"
        assert isinstance(s1, SayStmt)
        assert isinstance(s1.values[0], Var) and s1.values[0].name == "hello"


if __name__ == "__main__":
    unittest.main()
