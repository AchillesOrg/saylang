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
    ChooseExpr,
    ClearScreenStmt,
    CompareOp,
    CursorStmt,
    EntryAccess,
    EveryStmt,
    ExitStmt,
    Expr,
    ExprStmt,
    FailStmt,
    FieldAccess,
    FlagExpr,
    FlagsDeclStmt,
    ForEachStmt,
    ForRangeStmt,
    FuncDefStmt,
    IfStmt,
    ImportStmt,
    ItemAccess,
    LibCallExpr,
    ListLiteral,
    Literal,
    MapLiteral,
    PipeExpr,
    Program,
    ReadFileExpr,
    ReadKeyExpr,
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
    WaitStmt,
    WhileStmt,
    WriteFileStmt,
)
from saylang.parser import parse_source
from saylang.runtime import AUTO_LIB_VALUES

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
    "datetime",
    "json",
    "math",
    "os",
    "random",
    "re",
    "shutil",
    "sys",
    "_time",
    "Path",
    "AUTO_LIB_VALUES",
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
    "file_exists": "say_file_exists",
    "list_files": "say_list_files",
    "from_json": "say_from_json",
    "to_json": "say_to_json",
    "split": "say_split",
    "replace": "say_replace",
    "unique": "say_unique",
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


def _collect_defined_names(stmts: list[Stmt]) -> tuple[set[str], set[str]]:
    """Collect (all_bound_var_names, user_function_names) across the AST."""
    bound: set[str] = set()
    funcs: set[str] = set()

    def walk(body: list[Stmt]) -> None:
        for s in body:
            if isinstance(s, SetStmt) and isinstance(s.target, Var):
                bound.add(s.target.name)
            elif isinstance(s, FuncDefStmt):
                bound.add(s.name)
                funcs.add(s.name)
                bound.update(s.params)
                walk(s.body)
            elif isinstance(s, RepeatStmt):
                if s.var_name:
                    bound.add(s.var_name)
                walk(s.body)
            elif isinstance(s, ForRangeStmt):
                bound.add(s.var_name)
                walk(s.body)
            elif isinstance(s, ForEachStmt):
                bound.add(s.var_name)
                if s.value_var_name:
                    bound.add(s.value_var_name)
                walk(s.body)
            elif isinstance(s, WhileStmt):
                walk(s.body)
            elif isinstance(s, EveryStmt):
                walk(s.body)
            elif isinstance(s, IfStmt):
                for br in s.branches:
                    walk(br.body)
                walk(s.else_body)
            elif isinstance(s, TryStmt):
                if s.error_var:
                    bound.add(s.error_var)
                walk(s.try_body)
                walk(s.catch_body)

    walk(stmts)
    return bound, funcs


class PythonTranspiler:
    """Emit standalone Python 3 code matching SayLang interpreter semantics."""

    def __init__(self, standalone: bool = True) -> None:
        self.standalone = standalone
        self._lines: list[str] = []
        self._indent = 0
        self._tmp_counter = 0
        self._bound_names: set[str] = set()
        self._func_names: set[str] = set()

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
        self._bound_names, self._func_names = _collect_defined_names(
            program.statements
        )

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
        self._emit("say_configure_utf8_stdio()")
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
        if isinstance(stmt, ImportStmt):
            self._emit(f"say_import_modules({stmt.modules!r})")
            return

        if isinstance(stmt, FlagsDeclStmt):
            self._emit(f"# flags: {', '.join(stmt.flags)}")
            return

        if isinstance(stmt, ClearScreenStmt):
            self._emit("say_clear_screen()")
            return

        if isinstance(stmt, CursorStmt):
            self._emit(f"say_cursor({stmt.visible!r})")
            return

        if isinstance(stmt, ExitStmt):
            code = f"int({self._emit_expr(stmt.code)})" if stmt.code is not None else "0"
            self._emit(f"raise SystemExit({code})")
            return

        if isinstance(stmt, WaitStmt):
            self._emit(f"say_sleep({self._emit_expr(stmt.seconds)})")
            return

        if isinstance(stmt, EveryStmt):
            interval_var = self._fresh("_interval")
            self._emit(f"{interval_var} = {self._emit_expr(stmt.interval)}")
            self._emit("try:")
            self._indent += 1
            self._emit("while True:")
            self._emit_block(stmt.body)
            self._indent += 1
            self._emit(f"say_sleep({interval_var})")
            self._indent -= 2
            self._emit("except KeyboardInterrupt:")
            self._indent += 1
            self._emit("pass")
            self._indent -= 1
            return

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

            txt_var = self._fresh("_txt")
            self._emit(f"{txt_var} = {text_expr}")
            if stmt.position is not None:
                self._emit(
                    f"{txt_var} = say_format_layout({txt_var}, {stmt.position!r})"
                )
            self._emit(f"say_record_print({txt_var})")

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
                self._emit(
                    f"print(say_style_text({txt_var}, color={color_code}, "
                    f"background={bg_code}, styles={styles_code}))"
                )
            else:
                self._emit(f"print({txt_var})")
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
            if (
                expr.name.lower() in AUTO_LIB_VALUES
                and expr.name not in self._bound_names
            ):
                return f"say_lib_call({expr.name.lower()!r}, [], {{}})"
            return _py_name(expr.name)

        if isinstance(expr, FlagExpr):
            return f"say_get_flag({expr.name!r})"

        if isinstance(expr, LibCallExpr):
            args = ", ".join(self._emit_expr(a) for a in expr.args)
            opts = ", ".join(
                f"{k!r}: {self._emit_expr(v)}" for k, v in expr.options.items()
            )
            return f"say_lib_call({expr.name!r}, [{args}], {{{opts}}})"

        if isinstance(expr, PipeExpr):
            left_code = self._emit_expr(expr.left)
            args = ", ".join(self._emit_expr(a) for a in expr.args)
            opts = ", ".join(
                f"{k!r}: {self._emit_expr(v)}" for k, v in expr.options.items()
            )
            user_fn = (
                _py_name(expr.stage_name)
                if expr.stage_name in self._func_names
                else "None"
            )
            return (
                f"say_pipe({left_code}, {expr.stage_name!r}, "
                f"[{args}], {{{opts}}}, user_fn={user_fn})"
            )

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

        if isinstance(expr, ReadKeyExpr):
            return "say_read_key()"

        if isinstance(expr, ChooseExpr):
            opts = self._emit_expr(expr.options)
            prompt = (
                self._emit_expr(expr.prompt) if expr.prompt is not None else "None"
            )
            return f"say_choose({opts}, prompt={prompt})"

        if isinstance(expr, ReadFileExpr):
            return f"say_read_file({self._emit_expr(expr.path)})"

        raise ValueError(f"Unsupported expression: {type(expr).__name__}")


def compile_to_python(source: str, *, standalone: bool = True) -> str:
    """Parse SayLang source code and transpile it to Python 3."""
    program = parse_source(source)
    return PythonTranspiler(standalone=standalone).transpile(program)
