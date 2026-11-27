"""Transpiler from SayLang AST to readable standalone Python 3 source code."""

from __future__ import annotations

import keyword
import sys
from pathlib import Path

from saylang.ast_nodes import (
    AddToStmt,
    AskExpr,
    BinaryOp,
    BuiltinExpr,
    CallExpr,
    ChangeStmt,
    CompareOp,
    EntryAccess,
    Expr,
    ExprStmt,
    FailStmt,
    FieldAccess,
    ForEachStmt,
    ForRangeStmt,
    FuncDefStmt,
    IfStmt,
    ItemAccess,
    ListLiteral,
    Literal,
    MapLiteral,
    Program,
    ReadFileExpr,
    RemoveStmt,
    RepeatStmt,
    ReturnStmt,
    SayStmt,
    SetStmt,
    SkipStmt,
    Stmt,
    StopStmt,
    TryStmt,
    UnaryOp,
    Var,
    WhileStmt,
    WriteFileStmt,
)
from saylang.parser import parse_source

_START_MARKER = "# --- SAYLANG RUNTIME START ---"
_END_MARKER = "# --- SAYLANG RUNTIME END ---"

_RESERVED_PY_NAMES = {
    "print",
    "input",
    "list",
    "dict",
    "set",
    "str",
    "int",
    "float",
    "bool",
    "len",
    "type",
    "range",
    "open",
    "id",
    "min",
    "max",
    "sum",
    "abs",
    "round",
    "sorted",
    "reversed",
    "math",
    "random",
    "sys",
    "Path",
    "SayRuntimeError",
    "Exception",
}

_BUILTIN_MAP = {
    "length": "say_length",
    "first_item": "say_first_item",
    "last_item": "say_last_item",
    "keys": "say_keys",
    "values": "say_values",
    "uppercase": "say_uppercase",
    "lowercase": "say_lowercase",
    "trimmed": "say_trimmed",
    "words": "say_words",
    "lines": "say_lines",
    "joined": "say_joined",
    "sorted": "say_sorted",
    "reversed": "say_reversed",
    "rounded": "say_rounded",
    "abs": "say_abs",
    "sqrt": "say_sqrt",
    "random_int": "say_random_int",
    "to_number": "say_to_number",
    "to_text": "say_to_text",
    "type_of": "say_type_of",
}

_BINOP_MAP = {
    "+": "say_add",
    "-": "say_sub",
    "*": "say_mul",
    "/": "say_div",
    "//": "say_floordiv",
    "%": "say_mod",
    "**": "say_pow",
}


def _find_runtime_path() -> Path:
    direct = Path(__file__).with_name("runtime.py")
    if direct.is_file():
        return direct
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = Path(meipass) / "saylang" / "runtime.py"
        if bundled.is_file():
            return bundled
    return direct


def _extract_runtime_block() -> str:
    text = _find_runtime_path().read_text(encoding="utf-8")
    start = text.index(_START_MARKER)
    end = text.index(_END_MARKER) + len(_END_MARKER)
    return text[start:end].strip()


def _py_name(name: str) -> str:
    if (
        keyword.iskeyword(name)
        or name in _RESERVED_PY_NAMES
        or name.startswith("say_")
        or name.startswith("_say_")
        or name.startswith("_v_")
    ):
        return f"_v_{name}"
    return name


class PythonTranspiler:
    """Emit standalone Python 3 code matching SayLang interpreter semantics."""

    def __init__(self, standalone: bool = True) -> None:
        self.standalone = standalone
        self._lines: list[str] = []
        self._indent = 0
        self._tmp_counter = 0

    def _emit(self, line: str = "") -> None:
        if line:
            self._lines.append("    " * self._indent + line)
        else:
            self._lines.append("")

    def _fresh(self, prefix: str = "_tmp") -> str:
        self._tmp_counter += 1
        return f"{prefix}_{self._tmp_counter}"

    def transpile(self, program: Program) -> str:
        """Compile a Program AST into a Python 3 source string."""
        self._lines = []
        self._indent = 0
        self._tmp_counter = 0

        self._emit('"""Compiled from SayLang source."""')
        self._emit()
        if self.standalone:
            self._lines.append(_extract_runtime_block())
            self._emit()
        else:
            self._emit("from saylang.runtime import *")
            self._emit("from saylang.errors import SayRuntimeError")
            self._emit()

        self._emit("# --- COMPILED SAYLANG PROGRAM ---")
        if not program.statements:
            self._emit("pass")
        else:
            for stmt in program.statements:
                self._emit_stmt(stmt)

        return "\n".join(self._lines).rstrip() + "\n"

    def _emit_block(self, stmts: list[Stmt]) -> None:
        self._indent += 1
        if not stmts:
            self._emit("pass")
        else:
            for stmt in stmts:
                self._emit_stmt(stmt)
        self._indent -= 1

    def _emit_assign(self, target: Expr, value_expr: str) -> None:
        if isinstance(target, Var):
            self._emit(f"{_py_name(target.name)} = {value_expr}")
            return
        if isinstance(target, FieldAccess):
            obj_code = self._emit_expr(target.obj)
            self._emit(
                f"say_set_field({obj_code}, {target.field!r}, {value_expr})"
            )
            return
        if isinstance(target, ItemAccess):
            cont_code = self._emit_expr(target.container)
            idx_code = self._emit_expr(target.index)
            self._emit(f"say_set_item({cont_code}, {idx_code}, {value_expr})")
            return
        if isinstance(target, EntryAccess):
            map_code = self._emit_expr(target.mapping)
            key_code = self._emit_expr(target.key)
            self._emit(f"say_set_entry({map_code}, {key_code}, {value_expr})")
            return
        raise ValueError(f"Unsupported assignment target: {type(target).__name__}")

    def _emit_stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, SetStmt):
            self._emit_assign(stmt.target, self._emit_expr(stmt.value))
            return

        if isinstance(stmt, ChangeStmt):
            op_fn = "say_add" if stmt.op == "increase" else "say_sub"
            amt_code = self._emit_expr(stmt.amount)
            if isinstance(stmt.target, Var):
                vname = _py_name(stmt.target.name)
                self._emit(f"{vname} = {op_fn}({vname}, {amt_code})")
                return
            if isinstance(stmt.target, FieldAccess):
                obj_var = self._fresh("_obj")
                self._emit(f"{obj_var} = {self._emit_expr(stmt.target.obj)}")
                self._emit(
                    f"say_set_field({obj_var}, {stmt.target.field!r}, "
                    f"{op_fn}(say_get_field({obj_var}, {stmt.target.field!r}), {amt_code}))"
                )
                return
            if isinstance(stmt.target, ItemAccess):
                cont_var = self._fresh("_cont")
                idx_var = self._fresh("_idx")
                self._emit(f"{cont_var} = {self._emit_expr(stmt.target.container)}")
                self._emit(f"{idx_var} = {self._emit_expr(stmt.target.index)}")
                self._emit(
                    f"say_set_item({cont_var}, {idx_var}, "
                    f"{op_fn}(say_get_item({cont_var}, {idx_var}), {amt_code}))"
                )
                return
            if isinstance(stmt.target, EntryAccess):
                map_var = self._fresh("_map")
                key_var = self._fresh("_key")
                self._emit(f"{map_var} = {self._emit_expr(stmt.target.mapping)}")
                self._emit(f"{key_var} = {self._emit_expr(stmt.target.key)}")
                self._emit(
                    f"say_set_entry({map_var}, {key_var}, "
                    f"{op_fn}(say_get_entry({map_var}, {key_var}), {amt_code}))"
                )
                return

        if isinstance(stmt, SayStmt):
            if len(stmt.values) == 1:
                text_expr = f"say_to_text({self._emit_expr(stmt.values[0])})"
            else:
                parts = ", ".join(
                    f"say_to_text({self._emit_expr(v)})" for v in stmt.values
                )
                text_expr = f"''.join([{parts}])"

            if stmt.color is not None or stmt.background is not None or stmt.styles:
                color_code = (
                    self._emit_expr(stmt.color) if stmt.color is not None else "None"
                )
                bg_code = (
                    self._emit_expr(stmt.background)
                    if stmt.background is not None
                    else "None"
                )
                styles_code = repr(stmt.styles)
                text_expr = (
                    f"say_style_text({text_expr}, color={color_code}, "
                    f"background={bg_code}, styles={styles_code})"
                )
            self._emit(f"print({text_expr})")
            return

        if isinstance(stmt, IfStmt):
            first = stmt.branches[0]
            self._emit(f"if say_is_truthy({self._emit_expr(first.condition)}):")
            self._emit_block(first.body)
            for branch in stmt.branches[1:]:
                self._emit(
                    f"elif say_is_truthy({self._emit_expr(branch.condition)}):"
                )
                self._emit_block(branch.body)
            if stmt.else_body:
                self._emit("else:")
                self._emit_block(stmt.else_body)
            return

        if isinstance(stmt, RepeatStmt):
            cnt_var = self._fresh("_count")
            loop_var = _py_name(stmt.var_name) if stmt.var_name else self._fresh("_i")
            self._emit(f"{cnt_var} = {self._emit_expr(stmt.count)}")
            self._emit(
                f"if isinstance({cnt_var}, bool) or not isinstance({cnt_var}, (int, float)):"
            )
            self._indent += 1
            self._emit(
                f"raise SayRuntimeError(f'Repeat count must be a number, got {{say_type_of({cnt_var})}}.')"
            )
            self._indent -= 1
            self._emit(
                f"if isinstance({cnt_var}, float) and not {cnt_var}.is_integer():"
            )
            self._indent += 1
            self._emit(
                f"raise SayRuntimeError(f'Repeat count must be a whole number, got {{{cnt_var}}}.')"
            )
            self._indent -= 1
            self._emit(f"if int({cnt_var}) < 0:")
            self._indent += 1
            self._emit("raise SayRuntimeError('Repeat count cannot be negative.')")
            self._indent -= 1
            self._emit(f"for {loop_var} in range(1, int({cnt_var}) + 1):")
            self._emit_block(stmt.body)
            return

        if isinstance(stmt, ForRangeStmt):
            vname = _py_name(stmt.var_name)
            start_code = self._emit_expr(stmt.start)
            end_code = self._emit_expr(stmt.end)
            step_code = self._emit_expr(stmt.step) if stmt.step else "None"
            self._emit(
                f"for {vname} in say_range({start_code}, {end_code}, {step_code}):"
            )
            self._emit_block(stmt.body)
            return

        if isinstance(stmt, ForEachStmt):
            it_code = self._emit_expr(stmt.iterable)
            if stmt.value_var_name is not None:
                k_name = _py_name(stmt.var_name)
                v_name = _py_name(stmt.value_var_name)
                self._emit(
                    f"for {k_name}, {v_name} in say_iter_pairs({it_code}):"
                )
            else:
                vname = _py_name(stmt.var_name)
                self._emit(f"for {vname} in say_iter({it_code}):")
            self._emit_block(stmt.body)
            return

        if isinstance(stmt, WhileStmt):
            self._emit(f"while say_is_truthy({self._emit_expr(stmt.condition)}):")
            self._emit_block(stmt.body)
            return

        if isinstance(stmt, FuncDefStmt):
            params = ", ".join(_py_name(p) for p in stmt.params)
            self._emit(f"def {_py_name(stmt.name)}({params}):")
            self._emit_block(stmt.body)
            return

        if isinstance(stmt, ReturnStmt):
            if stmt.value is None:
                self._emit("return None")
            else:
                self._emit(f"return {self._emit_expr(stmt.value)}")
            return

        if isinstance(stmt, StopStmt):
            self._emit("break")
            return

        if isinstance(stmt, SkipStmt):
            self._emit("continue")
            return

        if isinstance(stmt, TryStmt):
            err_tmp = self._fresh("_err")
            self._emit("try:")
            self._emit_block(stmt.try_body)
            self._emit(f"except SayRuntimeError as {err_tmp}:")
            self._indent += 1
            if stmt.error_var is not None:
                self._emit(f"{_py_name(stmt.error_var)} = str({err_tmp})")
            if not stmt.catch_body:
                self._emit("pass")
            else:
                for c_stmt in stmt.catch_body:
                    self._emit_stmt(c_stmt)
            self._indent -= 1
            return

        if isinstance(stmt, FailStmt):
            msg_code = self._emit_expr(stmt.message)
            self._emit(f"raise SayRuntimeError(say_to_text({msg_code}))")
            return

        if isinstance(stmt, AddToStmt):
            val_code = self._emit_expr(stmt.value)
            target_code = self._emit_expr(stmt.target)
            self._emit(f"say_add_to({target_code}, {val_code})")
            return

        if isinstance(stmt, RemoveStmt):
            item_code = self._emit_expr(stmt.item)
            target_code = self._emit_expr(stmt.target)
            fn = {
                "item": "say_remove_item",
                "entry": "say_remove_entry",
                "value": "say_remove_value",
            }[stmt.kind]
            self._emit(f"{fn}({target_code}, {item_code})")
            return

        if isinstance(stmt, WriteFileStmt):
            content_code = self._emit_expr(stmt.content)
            path_code = self._emit_expr(stmt.path)
            fn = "say_append_file" if stmt.append else "say_write_file"
            self._emit(f"{fn}({path_code}, {content_code})")
            return

        if isinstance(stmt, ExprStmt):
            self._emit(self._emit_expr(stmt.expr))
            return

        raise ValueError(f"Unsupported statement: {type(stmt).__name__}")

    def _emit_expr(self, expr: Expr) -> str:
        if isinstance(expr, Literal):
            return repr(expr.value)

        if isinstance(expr, Var):
            return _py_name(expr.name)

        if isinstance(expr, ListLiteral):
            items = ", ".join(self._emit_expr(el) for el in expr.elements)
            return f"[{items}]"

        if isinstance(expr, MapLiteral):
            pairs = ", ".join(
                f"{self._emit_expr(k)}: {self._emit_expr(v)}"
                for k, v in expr.pairs
            )
            return f"{{{pairs}}}"

        if isinstance(expr, UnaryOp):
            operand = self._emit_expr(expr.operand)
            if expr.op == "neg":
                return f"say_negate({operand})"
            if expr.op == "not":
                return f"(not say_is_truthy({operand}))"
            raise ValueError(f"Unknown unary op: {expr.op}")

        if isinstance(expr, BinaryOp):
            left = self._emit_expr(expr.left)
            right = self._emit_expr(expr.right)
            if expr.op == "and":
                return (
                    f"(lambda _l: {right} if say_is_truthy(_l) else _l)({left})"
                )
            if expr.op == "or":
                return (
                    f"(lambda _l: _l if say_is_truthy(_l) else {right})({left})"
                )
            fn = _BINOP_MAP[expr.op]
            return f"{fn}({left}, {right})"

        if isinstance(expr, CompareOp):
            left = self._emit_expr(expr.left)
            right = self._emit_expr(expr.right)
            return f"say_compare({expr.op!r}, {left}, {right})"

        if isinstance(expr, CallExpr):
            args = ", ".join(self._emit_expr(a) for a in expr.args)
            return f"{_py_name(expr.name)}({args})"

        if isinstance(expr, FieldAccess):
            return f"say_get_field({self._emit_expr(expr.obj)}, {expr.field!r})"

        if isinstance(expr, ItemAccess):
            return (
                f"say_get_item({self._emit_expr(expr.container)}, "
                f"{self._emit_expr(expr.index)})"
            )

        if isinstance(expr, EntryAccess):
            return (
                f"say_get_entry({self._emit_expr(expr.mapping)}, "
                f"{self._emit_expr(expr.key)})"
            )

        if isinstance(expr, BuiltinExpr):
            fn = _BUILTIN_MAP[expr.name]
            args = ", ".join(self._emit_expr(a) for a in expr.args)
            return f"{fn}({args})"

        if isinstance(expr, AskExpr):
            return f"input(say_to_text({self._emit_expr(expr.prompt)}))"

        if isinstance(expr, ReadFileExpr):
            return f"say_read_file({self._emit_expr(expr.path)})"

        raise ValueError(f"Unsupported expression: {type(expr).__name__}")


def compile_to_python(source: str, *, standalone: bool = True) -> str:
    """Parse SayLang source code and transpile it to Python 3."""
    program = parse_source(source)
    return PythonTranspiler(standalone=standalone).transpile(program)
