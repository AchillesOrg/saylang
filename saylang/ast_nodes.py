"""AST node definitions for SayLang."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    line: int
    column: int


@dataclass
class Program(Node):
    statements: list[Stmt]


class Stmt(Node):
    """Base class for statement nodes."""


class Expr(Node):
    """Base class for expression nodes."""


# --- Statements ---


@dataclass
class ImportStmt(Stmt):
    modules: list[str]


@dataclass
class FlagsDeclStmt(Stmt):
    flags: list[str]


@dataclass
class ClearScreenStmt(Stmt):
    pass


@dataclass
class WaitStmt(Stmt):
    seconds: Expr


@dataclass
class EveryStmt(Stmt):
    interval: Expr
    body: list[Stmt]


@dataclass
class SetStmt(Stmt):
    target: Expr
    value: Expr


@dataclass
class ChangeStmt(Stmt):
    target: Expr
    op: str  # "increase" or "decrease"
    amount: Expr


@dataclass
class SayStmt(Stmt):
    values: list[Expr]
    color: Expr | None = None
    background: Expr | None = None
    styles: list[str] = field(default_factory=list)
    position: str | None = None
    anchor: str | None = None
    pos_anchor: Expr | None = None
    pos_x: Expr | None = None
    pos_y: Expr | None = None


@dataclass
class PositionStmt(Stmt):
    anchor: Expr | None = None
    x: Expr | None = None
    y: Expr | None = None


@dataclass
class FileOpStmt(Stmt):
    op: str  # "save" | "mkdir" | "delete" | "copy" | "move"
    args: list[Expr]


@dataclass
class IfBranch:
    condition: Expr
    body: list[Stmt]
    line: int
    column: int


@dataclass
class IfStmt(Stmt):
    branches: list[IfBranch]
    else_body: list[Stmt]


@dataclass
class RepeatStmt(Stmt):
    count: Expr
    var_name: str | None
    body: list[Stmt]


@dataclass
class ForEachStmt(Stmt):
    var_name: str
    value_var_name: str | None
    iterable: Expr
    body: list[Stmt]


@dataclass
class ForRangeStmt(Stmt):
    var_name: str
    start: Expr
    end: Expr
    step: Expr | None
    body: list[Stmt]


@dataclass
class WhileStmt(Stmt):
    condition: Expr
    body: list[Stmt]


@dataclass
class FuncDefStmt(Stmt):
    name: str
    params: list[str]
    body: list[Stmt]


@dataclass
class ReturnStmt(Stmt):
    value: Expr | None


@dataclass
class StopStmt(Stmt):
    pass


@dataclass
class SkipStmt(Stmt):
    pass


@dataclass
class TryStmt(Stmt):
    try_body: list[Stmt]
    error_var: str | None
    catch_body: list[Stmt]


@dataclass
class FailStmt(Stmt):
    message: Expr


@dataclass
class AddToStmt(Stmt):
    value: Expr
    target: Expr


@dataclass
class RemoveStmt(Stmt):
    kind: str  # "value" | "item" | "entry"
    item: Expr
    target: Expr


@dataclass
class WriteFileStmt(Stmt):
    content: Expr
    path: Expr
    append: bool


@dataclass
class CursorStmt(Stmt):
    visible: bool


@dataclass
class ExitStmt(Stmt):
    code: Expr | None = None


@dataclass
class ExprStmt(Stmt):
    expr: Expr


# --- Expressions ---


@dataclass
class Literal(Expr):
    value: object


@dataclass
class Var(Expr):
    name: str


@dataclass
class ListLiteral(Expr):
    elements: list[Expr]


@dataclass
class MapLiteral(Expr):
    pairs: list[tuple[Expr, Expr]]


@dataclass
class UnaryOp(Expr):
    op: str  # "neg", "not"
    operand: Expr


@dataclass
class BinaryOp(Expr):
    op: str  # "+", "-", "*", "/", "//", "%", "**", "and", "or"
    left: Expr
    right: Expr


@dataclass
class CompareOp(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass
class CallExpr(Expr):
    name: str
    args: list[Expr]


@dataclass
class FlagExpr(Expr):
    name: str


@dataclass
class LibCallExpr(Expr):
    name: str
    args: list[Expr]
    options: dict[str, Expr]


@dataclass
class PipeExpr(Expr):
    left: Expr
    stage_name: str
    args: list[Expr]
    options: dict[str, Expr]


@dataclass
class FieldAccess(Expr):
    obj: Expr
    field: str


@dataclass
class ItemAccess(Expr):
    container: Expr
    index: Expr


@dataclass
class EntryAccess(Expr):
    mapping: Expr
    key: Expr


@dataclass
class BuiltinExpr(Expr):
    name: str
    args: list[Expr]


@dataclass
class AskExpr(Expr):
    prompt: Expr


@dataclass
class ReadFileExpr(Expr):
    path: Expr


@dataclass
class ReadKeyExpr(Expr):
    pass


@dataclass
class ChooseExpr(Expr):
    options: Expr
    prompt: Expr | None = None


@dataclass
class ButtonsExpr(Expr):
    options: Expr
    prompt: Expr | None = None
    cols: Expr | None = None


@dataclass
class InterpolatedString(Expr):
    parts: list[Expr]


def find_live_time_options(stmt: Stmt) -> dict[str, Expr] | None:
    """Return `time --live` option dict if `stmt` prints a live-updating clock."""
    if not isinstance(stmt, SayStmt):
        return None

    def walk(node: object) -> dict[str, Expr] | None:
        if (
            isinstance(node, LibCallExpr)
            and node.name.lower() == "time"
            and "live" in node.options
        ):
            return node.options
        if isinstance(node, PipeExpr):
            found = walk(node.left)
            if found is not None:
                return found
            for arg in node.args:
                found = walk(arg)
                if found is not None:
                    return found
        elif isinstance(node, InterpolatedString):
            for part in node.parts:
                found = walk(part)
                if found is not None:
                    return found
        elif isinstance(node, BinaryOp):
            return walk(node.left) or walk(node.right)
        elif isinstance(node, UnaryOp):
            return walk(node.operand)
        elif isinstance(node, (BuiltinExpr, CallExpr)):
            for arg in node.args:
                found = walk(arg)
                if found is not None:
                    return found
        return None

    for val in stmt.values:
        res = walk(val)
        if res is not None:
            return res
    return None
