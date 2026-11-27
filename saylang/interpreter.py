"""Tree-walking interpreter for SayLang."""

from __future__ import annotations

import io
import sys
from collections.abc import Callable
from typing import TextIO

from saylang import runtime
from saylang.ast_nodes import (
    AddToStmt,
    AskExpr,
    BinaryOp,
    BuiltinExpr,
    CallExpr,
    ChangeStmt,
    ClearScreenStmt,
    CompareOp,
    EntryAccess,
    EveryStmt,
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
from saylang.errors import SayRuntimeError
from saylang.parser import parse_source


class _ReturnSignal(Exception):
    def __init__(self, value: object) -> None:
        self.value = value


class _StopSignal(Exception):
    pass


class _SkipSignal(Exception):
    pass


class SayFunction:
    """First-class SayLang function closure."""

    def __init__(
        self, name: str, params: list[str], body: list[Stmt], env: Environment
    ) -> None:
        self.name = name
        self.params = params
        self.body = body
        self.env = env

    def __repr__(self) -> str:
        return f"<function {self.name}>"


class Environment:
    """Lexical variable scope."""

    def __init__(self, parent: Environment | None = None) -> None:
        self.parent = parent
        self.values: dict[str, object] = {}

    def get(self, name: str) -> object | None:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise KeyError(name)

    def set(self, name: str, value: object) -> None:
        self.values[name] = value


_BUILTIN_FUNCS: dict[str, Callable[..., object]] = {
    "length": runtime.say_length,
    "first_item": runtime.say_first_item,
    "last_item": runtime.say_last_item,
    "keys": runtime.say_keys,
    "values": runtime.say_values,
    "uppercase": runtime.say_uppercase,
    "lowercase": runtime.say_lowercase,
    "trimmed": runtime.say_trimmed,
    "words": runtime.say_words,
    "lines": runtime.say_lines,
    "joined": runtime.say_joined,
    "sorted": runtime.say_sorted,
    "reversed": runtime.say_reversed,
    "rounded": runtime.say_rounded,
    "abs": runtime.say_abs,
    "sqrt": runtime.say_sqrt,
    "random_int": runtime.say_random_int,
    "to_number": runtime.say_to_number,
    "to_text": runtime.say_to_text,
    "type_of": runtime.say_type_of,
}


class Interpreter:
    """Executes SayLang AST nodes."""

    def __init__(
        self,
        source: str = "",
        stdout: TextIO | None = None,
        input_fn: Callable[[str], str] | None = None,
        cli_args: list[str] | None = None,
    ) -> None:
        self.source_lines = (
            source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            if source
            else []
        )
        self.stdout = stdout if stdout is not None else sys.stdout
        self.input_fn = input_fn if input_fn is not None else input
        if cli_args is not None:
            runtime.say_set_cli_args(cli_args)
        self.global_env = Environment()
        self.env = self.global_env

    def _source_line(self, line: int) -> str:
        if 1 <= line <= len(self.source_lines):
            return self.source_lines[line - 1]
        return ""

    def _attach_loc(self, exc: SayRuntimeError, line: int, column: int) -> SayRuntimeError:
        if exc.line == 0:
            exc.line = line
            exc.column = column
            exc.source_line = self._source_line(line)
        return exc

    def _error(self, message: str, line: int, column: int) -> SayRuntimeError:
        return SayRuntimeError(
            message, line=line, column=column, source_line=self._source_line(line)
        )

    def run(self, program: Program, source: str | None = None) -> object:
        """Execute a Program AST in the interpreter's current environment."""
        if source is not None:
            self.source_lines = (
                source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
            )
        last_val: object = None
        for stmt in program.statements:
            try:
                last_val = self._exec_stmt(stmt, self.env)
            except _ReturnSignal as sig:
                raise self._error(
                    "'return' can only be used inside a function.",
                    stmt.line,
                    stmt.column,
                ) from sig
            except _StopSignal as sig:
                raise self._error(
                    "'stop' can only be used inside a loop.", stmt.line, stmt.column
                ) from sig
            except _SkipSignal as sig:
                raise self._error(
                    "'skip' can only be used inside a loop.", stmt.line, stmt.column
                ) from sig
        return last_val

    def _exec_block(self, stmts: list[Stmt], env: Environment) -> None:
        for stmt in stmts:
            self._exec_stmt(stmt, env)

    def _assign_target(
        self, target: Expr, value: object, env: Environment
    ) -> None:
        if isinstance(target, Var):
            env.set(target.name, value)
            return
        if isinstance(target, FieldAccess):
            obj = self._eval_expr(target.obj, env)
            try:
                runtime.say_set_field(obj, target.field, value)
            except SayRuntimeError as exc:
                raise self._attach_loc(exc, target.line, target.column) from exc
            return
        if isinstance(target, ItemAccess):
            container = self._eval_expr(target.container, env)
            index = self._eval_expr(target.index, env)
            try:
                runtime.say_set_item(container, index, value)
            except SayRuntimeError as exc:
                raise self._attach_loc(exc, target.line, target.column) from exc
            return
        if isinstance(target, EntryAccess):
            mapping = self._eval_expr(target.mapping, env)
            key = self._eval_expr(target.key, env)
            try:
                runtime.say_set_entry(mapping, key, value)
            except SayRuntimeError as exc:
                raise self._attach_loc(exc, target.line, target.column) from exc
            return
        raise self._error("Cannot assign to this target.", target.line, target.column)

    def _read_target_for_update(self, target: Expr, env: Environment) -> object:
        if isinstance(target, Var):
            if target.name not in env.values:
                raise self._error(
                    f"Variable '{target.name}' is not defined yet.",
                    target.line,
                    target.column,
                )
            return env.values[target.name]
        return self._eval_expr(target, env)

    def _exec_stmt(self, stmt: Stmt, env: Environment) -> object:
        try:
            if isinstance(stmt, ImportStmt):
                runtime.say_import_modules(stmt.modules)
                return None

            if isinstance(stmt, FlagsDeclStmt):
                return None

            if isinstance(stmt, ClearScreenStmt):
                runtime.say_clear_screen(self.stdout)
                return None

            if isinstance(stmt, WaitStmt):
                secs = self._eval_expr(stmt.seconds, env)
                runtime.say_sleep(secs)
                return None

            if isinstance(stmt, EveryStmt):
                interval = self._eval_expr(stmt.interval, env)
                try:
                    while True:
                        try:
                            self._exec_block(stmt.body, env)
                        except _SkipSignal:
                            pass
                        except _StopSignal:
                            break
                        runtime.say_sleep(interval)
                except KeyboardInterrupt:
                    return None
                return None

            if isinstance(stmt, SetStmt):
                val = self._eval_expr(stmt.value, env)
                self._assign_target(stmt.target, val, env)
                return None

            if isinstance(stmt, ChangeStmt):
                current = self._read_target_for_update(stmt.target, env)
                amount = self._eval_expr(stmt.amount, env)
                if stmt.op == "increase":
                    updated = runtime.say_add(current, amount)
                else:
                    updated = runtime.say_sub(current, amount)
                self._assign_target(stmt.target, updated, env)
                return None

            if isinstance(stmt, SayStmt):
                parts = [
                    runtime.say_to_text(self._eval_expr(v, env))
                    for v in stmt.values
                ]
                text = "".join(parts)
                if stmt.position is not None:
                    text = runtime.say_format_layout(text, stmt.position)
                runtime.say_record_print(text)
                if stmt.color is not None or stmt.background is not None or stmt.styles:
                    color_val = (
                        self._eval_expr(stmt.color, env)
                        if stmt.color is not None
                        else None
                    )
                    bg_val = (
                        self._eval_expr(stmt.background, env)
                        if stmt.background is not None
                        else None
                    )
                    text = runtime.say_style_text(
                        text, color=color_val, background=bg_val, styles=stmt.styles
                    )
                self.stdout.write(text + "\n")
                return None

            if isinstance(stmt, IfStmt):
                for branch in stmt.branches:
                    cond = self._eval_expr(branch.condition, env)
                    if runtime.say_is_truthy(cond):
                        self._exec_block(branch.body, env)
                        return None
                if stmt.else_body:
                    self._exec_block(stmt.else_body, env)
                return None

            if isinstance(stmt, RepeatStmt):
                count_val = self._eval_expr(stmt.count, env)
                if isinstance(count_val, bool) or not isinstance(
                    count_val, (int, float)
                ):
                    raise self._error(
                        f"Repeat count must be a number, got {runtime.say_type_of(count_val)}.",
                        stmt.line,
                        stmt.column,
                    )
                if isinstance(count_val, float) and not count_val.is_integer():
                    raise self._error(
                        f"Repeat count must be a whole number, got {count_val}.",
                        stmt.line,
                        stmt.column,
                    )
                n = int(count_val)
                if n < 0:
                    raise self._error(
                        "Repeat count cannot be negative.", stmt.line, stmt.column
                    )
                for idx in range(1, n + 1):
                    if stmt.var_name is not None:
                        env.set(stmt.var_name, idx)
                    try:
                        self._exec_block(stmt.body, env)
                    except _SkipSignal:
                        continue
                    except _StopSignal:
                        break
                return None

            if isinstance(stmt, ForRangeStmt):
                start = self._eval_expr(stmt.start, env)
                end = self._eval_expr(stmt.end, env)
                step = self._eval_expr(stmt.step, env) if stmt.step else None
                for val in runtime.say_range(start, end, step):
                    env.set(stmt.var_name, val)
                    try:
                        self._exec_block(stmt.body, env)
                    except _SkipSignal:
                        continue
                    except _StopSignal:
                        break
                return None

            if isinstance(stmt, ForEachStmt):
                iterable = self._eval_expr(stmt.iterable, env)
                if stmt.value_var_name is not None:
                    for k, v in runtime.say_iter_pairs(iterable):
                        env.set(stmt.var_name, k)
                        env.set(stmt.value_var_name, v)
                        try:
                            self._exec_block(stmt.body, env)
                        except _SkipSignal:
                            continue
                        except _StopSignal:
                            break
                else:
                    for item in runtime.say_iter(iterable):
                        env.set(stmt.var_name, item)
                        try:
                            self._exec_block(stmt.body, env)
                        except _SkipSignal:
                            continue
                        except _StopSignal:
                            break
                return None

            if isinstance(stmt, WhileStmt):
                while runtime.say_is_truthy(self._eval_expr(stmt.condition, env)):
                    try:
                        self._exec_block(stmt.body, env)
                    except _SkipSignal:
                        continue
                    except _StopSignal:
                        break
                return None

            if isinstance(stmt, FuncDefStmt):
                fn = SayFunction(stmt.name, stmt.params, stmt.body, env)
                env.set(stmt.name, fn)
                return None

            if isinstance(stmt, ReturnStmt):
                val = self._eval_expr(stmt.value, env) if stmt.value else None
                raise _ReturnSignal(val)

            if isinstance(stmt, StopStmt):
                raise _StopSignal()

            if isinstance(stmt, SkipStmt):
                raise _SkipSignal()

            if isinstance(stmt, TryStmt):
                try:
                    self._exec_block(stmt.try_body, env)
                except SayRuntimeError as err:
                    if stmt.error_var is not None:
                        env.set(stmt.error_var, err.message)
                    self._exec_block(stmt.catch_body, env)
                return None

            if isinstance(stmt, FailStmt):
                msg = runtime.say_to_text(self._eval_expr(stmt.message, env))
                raise self._error(msg, stmt.line, stmt.column)

            if isinstance(stmt, AddToStmt):
                val = self._eval_expr(stmt.value, env)
                target = self._eval_expr(stmt.target, env)
                runtime.say_add_to(target, val)
                return None

            if isinstance(stmt, RemoveStmt):
                item = self._eval_expr(stmt.item, env)
                target = self._eval_expr(stmt.target, env)
                if stmt.kind == "item":
                    runtime.say_remove_item(target, item)
                elif stmt.kind == "entry":
                    runtime.say_remove_entry(target, item)
                else:
                    runtime.say_remove_value(target, item)
                return None

            if isinstance(stmt, WriteFileStmt):
                content = self._eval_expr(stmt.content, env)
                path = self._eval_expr(stmt.path, env)
                if stmt.append:
                    runtime.say_append_file(path, content)
                else:
                    runtime.say_write_file(path, content)
                return None

            if isinstance(stmt, ExprStmt):
                return self._eval_expr(stmt.expr, env)

            raise self._error(
                f"Unsupported statement: {type(stmt).__name__}",
                stmt.line,
                stmt.column,
            )
        except SayRuntimeError as exc:
            raise self._attach_loc(exc, stmt.line, stmt.column) from exc

    def _invoke_say_function(
        self, fn: SayFunction, arg_vals: list[object], line: int, column: int
    ) -> object:
        if len(arg_vals) != len(fn.params):
            raise self._error(
                f"Function '{fn.name}' expects {len(fn.params)} argument(s), got {len(arg_vals)}.",
                line,
                column,
            )
        local_env = Environment(parent=fn.env)
        for p, v in zip(fn.params, arg_vals):
            local_env.set(p, v)
        try:
            self._exec_block(fn.body, local_env)
        except _ReturnSignal as sig:
            return sig.value
        except _StopSignal as sig:
            raise self._error(
                "'stop' cannot cross a function boundary.", line, column
            ) from sig
        except _SkipSignal as sig:
            raise self._error(
                "'skip' cannot cross a function boundary.", line, column
            ) from sig
        return None

    def _call_function(
        self, name: str, arg_vals: list[object], env: Environment, line: int, column: int
    ) -> object:
        try:
            fn = env.get(name)
        except KeyError as exc:
            raise self._error(f"Function '{name}' is not defined.", line, column) from exc
        if not isinstance(fn, SayFunction):
            raise self._error(
                f"'{name}' is a {runtime.say_type_of(fn)}, not a function.",
                line,
                column,
            )
        return self._invoke_say_function(fn, arg_vals, line, column)

    def _eval_expr(self, expr: Expr, env: Environment) -> object:
        try:
            if isinstance(expr, Literal):
                return expr.value

            if isinstance(expr, Var):
                try:
                    return env.get(expr.name)
                except KeyError as exc:
                    if expr.name.lower() in runtime.AUTO_LIB_VALUES:
                        return runtime.say_lib_call(expr.name.lower(), [], {})
                    raise self._error(
                        f'Variable \'{expr.name}\' is not defined. If you meant text, wrap it in quotes like "{expr.name}".',
                        expr.line,
                        expr.column,
                    ) from exc

            if isinstance(expr, FlagExpr):
                return runtime.say_get_flag(expr.name)

            if isinstance(expr, LibCallExpr):
                args = [self._eval_expr(a, env) for a in expr.args]
                opts = {k: self._eval_expr(v, env) for k, v in expr.options.items()}
                return runtime.say_lib_call(expr.name, args, opts)

            if isinstance(expr, PipeExpr):
                left_val = self._eval_expr(expr.left, env)
                args = [self._eval_expr(a, env) for a in expr.args]
                opts = {k: self._eval_expr(v, env) for k, v in expr.options.items()}
                user_fn: Callable[..., object] | None = None
                try:
                    maybe_fn = env.get(expr.stage_name)
                    if isinstance(maybe_fn, SayFunction):
                        user_fn = lambda *call_args: self._invoke_say_function(
                            maybe_fn, list(call_args), expr.line, expr.column
                        )
                except KeyError:
                    pass
                return runtime.say_pipe(
                    left_val, expr.stage_name, args, opts, user_fn=user_fn
                )

            if isinstance(expr, ListLiteral):
                return [self._eval_expr(el, env) for el in expr.elements]

            if isinstance(expr, MapLiteral):
                result: dict[object, object] = {}
                for k_expr, v_expr in expr.pairs:
                    k = self._eval_expr(k_expr, env)
                    v = self._eval_expr(v_expr, env)
                    result[k] = v
                return result

            if isinstance(expr, UnaryOp):
                operand = self._eval_expr(expr.operand, env)
                if expr.op == "neg":
                    return runtime.say_negate(operand)
                if expr.op == "not":
                    return not runtime.say_is_truthy(operand)
                raise self._error(
                    f"Unknown unary operator '{expr.op}'.", expr.line, expr.column
                )

            if isinstance(expr, BinaryOp):
                if expr.op == "and":
                    left = self._eval_expr(expr.left, env)
                    if not runtime.say_is_truthy(left):
                        return left
                    return self._eval_expr(expr.right, env)
                if expr.op == "or":
                    left = self._eval_expr(expr.left, env)
                    if runtime.say_is_truthy(left):
                        return left
                    return self._eval_expr(expr.right, env)

                left = self._eval_expr(expr.left, env)
                right = self._eval_expr(expr.right, env)
                if expr.op == "+":
                    return runtime.say_add(left, right)
                if expr.op == "-":
                    return runtime.say_sub(left, right)
                if expr.op == "*":
                    return runtime.say_mul(left, right)
                if expr.op == "/":
                    return runtime.say_div(left, right)
                if expr.op == "//":
                    return runtime.say_floordiv(left, right)
                if expr.op == "%":
                    return runtime.say_mod(left, right)
                if expr.op == "**":
                    return runtime.say_pow(left, right)
                raise self._error(
                    f"Unknown binary operator '{expr.op}'.", expr.line, expr.column
                )

            if isinstance(expr, CompareOp):
                left = self._eval_expr(expr.left, env)
                right = self._eval_expr(expr.right, env)
                return runtime.say_compare(expr.op, left, right)

            if isinstance(expr, CallExpr):
                arg_vals = [self._eval_expr(a, env) for a in expr.args]
                return self._call_function(
                    expr.name, arg_vals, env, expr.line, expr.column
                )

            if isinstance(expr, FieldAccess):
                obj = self._eval_expr(expr.obj, env)
                return runtime.say_get_field(obj, expr.field)

            if isinstance(expr, ItemAccess):
                container = self._eval_expr(expr.container, env)
                index = self._eval_expr(expr.index, env)
                return runtime.say_get_item(container, index)

            if isinstance(expr, EntryAccess):
                mapping = self._eval_expr(expr.mapping, env)
                key = self._eval_expr(expr.key, env)
                return runtime.say_get_entry(mapping, key)

            if isinstance(expr, BuiltinExpr):
                fn = _BUILTIN_FUNCS.get(expr.name)
                if fn is None:
                    raise self._error(
                        f"Unknown built-in '{expr.name}'.", expr.line, expr.column
                    )
                arg_vals = [self._eval_expr(a, env) for a in expr.args]
                return fn(*arg_vals)

            if isinstance(expr, AskExpr):
                prompt = runtime.say_to_text(self._eval_expr(expr.prompt, env))
                return self.input_fn(prompt)

            if isinstance(expr, ReadFileExpr):
                path = self._eval_expr(expr.path, env)
                return runtime.say_read_file(path)

            raise self._error(
                f"Unsupported expression: {type(expr).__name__}",
                expr.line,
                expr.column,
            )
        except SayRuntimeError as exc:
            raise self._attach_loc(exc, expr.line, expr.column) from exc


def run_program(
    program: Program,
    *,
    source: str = "",
    stdout: TextIO | None = None,
    input_fn: Callable[[str], str] | None = None,
    cli_args: list[str] | None = None,
) -> object:
    """Execute a parsed SayLang Program AST."""
    return Interpreter(
        source=source, stdout=stdout, input_fn=input_fn, cli_args=cli_args
    ).run(program)


def run_source(
    source: str,
    *,
    stdout: TextIO | None = None,
    input_fn: Callable[[str], str] | None = None,
    cli_args: list[str] | None = None,
) -> object:
    """Parse and execute SayLang source code."""
    program = parse_source(source)
    return run_program(
        program, source=source, stdout=stdout, input_fn=input_fn, cli_args=cli_args
    )


def run_and_capture(
    source: str,
    *,
    input_lines: list[str] | None = None,
    cli_args: list[str] | None = None,
) -> tuple[str, object]:
    """Convenience helper returning (captured_stdout, last_value)."""
    buf = io.StringIO()
    inputs = iter(input_lines or [])

    def _fake_input(prompt: str = "") -> str:
        if prompt:
            buf.write(prompt)
        try:
            return next(inputs)
        except StopIteration:
            return ""

    val = run_source(
        source,
        stdout=buf,
        input_fn=_fake_input if input_lines is not None else None,
        cli_args=cli_args if cli_args is not None else [],
    )
    return buf.getvalue(), val
