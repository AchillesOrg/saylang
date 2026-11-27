"""Deterministic recursive-descent parser for SayLang."""

from __future__ import annotations

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
    IfBranch,
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
from saylang.errors import SayParseError
from saylang.lexer import tokenize
from saylang.tokens import Token, TokenType

_NON_EXPR_START_WORDS = {
    "to",
    "of",
    "with",
    "in",
    "from",
    "as",
    "by",
    "and",
    "or",
    "is",
    "equals",
    "contains",
    "does",
    "starts",
    "ends",
    "plus",
    "minus",
    "times",
    "divided",
    "whole",
    "modulo",
    "mod",
    "then",
}

_UNARY_PHRASE_HEADS = {
    "length",
    "first",
    "last",
    "item",
    "entry",
    "keys",
    "values",
    "uppercase",
    "lowercase",
    "trimmed",
    "words",
    "lines",
    "joined",
    "sorted",
    "reversed",
    "rounded",
    "absolute",
    "square",
    "random",
    "number",
    "text",
    "type",
}

_COLOR_NAMES = {
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "purple",
    "cyan",
    "white",
    "gray",
    "grey",
    "orange",
    "pink",
}

_STYLE_WORDS = {"bold", "dim", "italic", "underline"}

_LIB_COMMANDS = {
    "time",
    "date",
    "ascii",
    "box",
    "center",
    "bar",
    "table",
    "rule",
    "divider",
    "env",
    "sum",
    "min",
    "max",
    "average",
}

_CURRENT_TIME_ATTRS = {
    "time",
    "date",
    "hour",
    "minute",
    "second",
    "year",
    "month",
    "day",
    "weekday",
}

_FLAG_VALUE_STOP_WORDS = {
    "then",
    "otherwise",
    "else",
    "and",
    "or",
    "is",
    "below",
    "centered",
    "centred",
    "colour",
    "color",
    "on",
    "background",
    "bold",
    "dim",
    "italic",
    "underline",
    "in",
    "to",
    "from",
    "by",
    "as",
}


class Parser:
    """Recursive-descent parser producing a SayLang AST."""

    def __init__(self, tokens: list[Token], source: str = "") -> None:
        self.tokens = tokens
        self.source_lines = source.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        self.pos = 0
        self._inline_if_depth = 0

    def _source_line(self, line: int) -> str:
        if 1 <= line <= len(self.source_lines):
            return self.source_lines[line - 1]
        return ""

    def _error(self, message: str, tok: Token | None = None) -> SayParseError:
        t = tok or self._peek()
        return SayParseError(
            message,
            line=t.line,
            column=t.column,
            source_line=self._source_line(t.line),
        )

    def _peek(self, offset: int = 0) -> Token:
        idx = self.pos + offset
        if idx >= len(self.tokens):
            return self.tokens[-1]
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self._peek()
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _at_word(self, word: str, offset: int = 0) -> bool:
        tok = self._peek(offset)
        return tok.type == TokenType.WORD and tok.lower == word

    def _at_words(self, *words: str, offset: int = 0) -> bool:
        for i, word in enumerate(words):
            if not self._at_word(word, offset + i):
                return False
        return True

    def _consume_word(self, word: str, message: str | None = None) -> Token:
        if self._at_word(word):
            return self._advance()
        raise self._error(message or f"Expected '{word}'.")

    def _consume_words(self, *words: str) -> None:
        for word in words:
            self._consume_word(word)

    def _consume_ident(self, what: str = "a name") -> Token:
        tok = self._peek()
        if tok.type == TokenType.WORD:
            return self._advance()
        raise self._error(f"Expected {what}.")

    def _skip_newlines(self) -> None:
        while self._peek().type == TokenType.NEWLINE:
            self._advance()

    def _expect_end_of_statement(self) -> None:
        tok = self._peek()
        if tok.type == TokenType.NEWLINE:
            self._advance()
            return
        if tok.type in (TokenType.EOF, TokenType.DEDENT):
            return
        if self._inline_if_depth > 0 and (
            self._at_word("otherwise") or self._at_word("else")
        ):
            return
        raise self._error(
            f"Unexpected '{tok.value}' at the end of the line.", tok
        )

    def _consume_block(self, header: str) -> list[Stmt]:
        if self._peek().type == TokenType.COLON:
            self._advance()
        if self._peek().type == TokenType.NEWLINE:
            self._advance()
        else:
            raise self._error(f"Expected a new line after '{header}'.")

        self._skip_newlines()
        if self._peek().type != TokenType.INDENT:
            raise self._error(f"Expected an indented block after '{header}'.")
        self._advance()

        stmts: list[Stmt] = []
        while self._peek().type not in (TokenType.DEDENT, TokenType.EOF):
            self._skip_newlines()
            if self._peek().type in (TokenType.DEDENT, TokenType.EOF):
                break
            stmts.append(self._parse_statement())

        if self._peek().type == TokenType.DEDENT:
            self._advance()
        return stmts

    def parse(self) -> Program:
        """Parse the full token stream into a Program AST node."""
        self._skip_newlines()
        stmts: list[Stmt] = []
        while self._peek().type != TokenType.EOF:
            self._skip_newlines()
            if self._peek().type == TokenType.EOF:
                break
            stmts.append(self._parse_statement())
        return Program(line=1, column=1, statements=stmts)

    # --- Statements ---

    def _parse_statement(self) -> Stmt:
        tok = self._peek()
        if tok.type == TokenType.WORD:
            w = tok.lower
            if w in ("import", "use"):
                return self._parse_import()
            if w == "flags":
                return self._parse_flags_decl()
            if w == "clear":
                return self._parse_clear()
            if w in ("hide", "show") and self._at_word("cursor", 1):
                self._advance()
                self._advance()
                self._expect_end_of_statement()
                return CursorStmt(
                    line=tok.line, column=tok.column, visible=(w == "show")
                )
            if w == "exit":
                self._advance()
                code_expr: Expr | None = None
                if self._at_word("with"):
                    self._advance()
                    code_expr = self._parse_expr()
                elif self._can_start_expr():
                    code_expr = self._parse_expr()
                self._expect_end_of_statement()
                return ExitStmt(line=tok.line, column=tok.column, code=code_expr)
            if w in ("wait", "sleep"):
                nxt_tok = self._peek(1)
                if w == "wait" and (
                    self._at_words("for", "key", offset=1) or self._at_word("key", 1)
                ):
                    expr = self._parse_expr()
                    self._expect_end_of_statement()
                    return ExprStmt(line=tok.line, column=tok.column, expr=expr)
                return self._parse_wait()
            if w == "every":
                return self._parse_every()
            if w == "set":
                return self._parse_set()
            if w == "let":
                return self._parse_let()
            if w in ("increase", "decrease"):
                return self._parse_change(w)
            if w in ("say", "print"):
                return self._parse_say()
            if w == "if":
                return self._parse_if()
            if w == "repeat":
                return self._parse_repeat()
            if w == "for" and self._at_word("each", 1):
                return self._parse_for_each()
            if w == "while":
                return self._parse_while()
            if w == "to":
                return self._parse_func_def()
            if w == "return" or self._at_words("give", "back"):
                return self._parse_return()
            if w == "stop":
                self._advance()
                self._expect_end_of_statement()
                return StopStmt(line=tok.line, column=tok.column)
            if w == "skip":
                self._advance()
                self._expect_end_of_statement()
                return SkipStmt(line=tok.line, column=tok.column)
            if w == "try":
                return self._parse_try()
            if w == "fail":
                return self._parse_fail()
            if w in ("add", "append"):
                return self._parse_add_or_append()
            if w == "remove":
                return self._parse_remove()
            if w == "write":
                return self._parse_write_file()
            if w == "run":
                next_tok = self._peek(1)
                if next_tok.type == TokenType.WORD and next_tok.lower in {
                    "say",
                    "print",
                    "set",
                    "let",
                    "increase",
                    "decrease",
                    "add",
                    "append",
                    "remove",
                    "write",
                    "clear",
                    "wait",
                    "sleep",
                    "import",
                }:
                    self._advance()
                    return self._parse_statement()
                expr = self._parse_call_expr(start_tok=self._advance())
                self._expect_end_of_statement()
                return ExprStmt(line=tok.line, column=tok.column, expr=expr)

        expr = self._parse_expr()
        self._expect_end_of_statement()
        return ExprStmt(line=tok.line, column=tok.column, expr=expr)

    def _parse_import(self) -> ImportStmt:
        tok = self._advance()
        modules = [str(self._consume_ident("a library name").value)]
        while True:
            if self._peek().type == TokenType.COMMA:
                self._advance()
                if self._at_word("and"):
                    self._advance()
                modules.append(str(self._consume_ident("a library name").value))
            elif self._at_word("and"):
                self._advance()
                modules.append(str(self._consume_ident("a library name").value))
            else:
                break
        self._expect_end_of_statement()
        return ImportStmt(line=tok.line, column=tok.column, modules=modules)

    def _parse_single_flag_name(self) -> str:
        tok = self._peek()
        if tok.type == TokenType.FLAG:
            self._advance()
            return str(tok.value)
        if tok.type == TokenType.MINUS and self._peek(1).type == TokenType.WORD:
            self._advance()
            w = self._advance()
            return f"-{w.value}"
        raise self._error("Expected a flag like '-d' or '--12h'.")

    def _parse_flags_decl(self) -> FlagsDeclStmt:
        tok = self._advance()
        if self._peek().type == TokenType.COLON:
            self._advance()
        flags = [self._parse_single_flag_name()]
        while self._peek().type == TokenType.COMMA or self._at_word("and"):
            if self._peek().type == TokenType.COMMA:
                self._advance()
                if self._at_word("and"):
                    self._advance()
            else:
                self._advance()
            flags.append(self._parse_single_flag_name())
        self._expect_end_of_statement()
        return FlagsDeclStmt(line=tok.line, column=tok.column, flags=flags)

    def _parse_clear(self) -> ClearScreenStmt:
        tok = self._advance()
        if self._at_word("screen"):
            self._advance()
        self._expect_end_of_statement()
        return ClearScreenStmt(line=tok.line, column=tok.column)

    def _parse_wait(self) -> WaitStmt:
        tok = self._advance()
        seconds = self._parse_expr()
        if self._at_word("second") or self._at_word("seconds"):
            self._advance()
        self._expect_end_of_statement()
        return WaitStmt(line=tok.line, column=tok.column, seconds=seconds)

    def _parse_every(self) -> EveryStmt:
        tok = self._advance()
        interval = self._parse_expr()
        if self._at_word("second") or self._at_word("seconds"):
            self._advance()
        body = self._consume_block("every")
        return EveryStmt(
            line=tok.line, column=tok.column, interval=interval, body=body
        )

    def _parse_target(self) -> Expr:
        """Parse an assignment target (var, item X of Y, entry X of Y, or X's Y)."""
        if self._at_word("the"):
            self._advance()

        tok = self._peek()
        if self._at_word("item") and not self._at_word("of", 1):
            self._advance()
            index = self._parse_expr()
            self._consume_word("of", "Expected 'of' after item index.")
            container = self._parse_target()
            return ItemAccess(
                line=tok.line, column=tok.column, container=container, index=index
            )

        if self._at_word("entry") and not self._at_word("of", 1):
            self._advance()
            key = self._parse_expr()
            self._consume_word("of", "Expected 'of' after entry key.")
            mapping = self._parse_target()
            return EntryAccess(
                line=tok.line, column=tok.column, mapping=mapping, key=key
            )

        ident = self._consume_ident("a variable name")
        node: Expr = Var(line=ident.line, column=ident.column, name=str(ident.value))
        while self._peek().type == TokenType.POSSESSIVE:
            poss = self._advance()
            field = self._consume_ident("a field name after 's")
            node = FieldAccess(
                line=poss.line,
                column=poss.column,
                obj=node,
                field=str(field.value),
            )
        return node

    def _parse_set(self) -> SetStmt:
        tok = self._advance()
        target = self._parse_target()
        if self._at_word("to") or self._at_word("be") or self._at_word("as"):
            self._advance()
        elif self._peek().type in (TokenType.NEWLINE, TokenType.EOF, TokenType.DEDENT):
            raise self._error("Expected 'to' and a value in 'set' statement.")
        value = self._parse_expr()
        self._expect_end_of_statement()
        return SetStmt(line=tok.line, column=tok.column, target=target, value=value)

    def _parse_let(self) -> SetStmt:
        tok = self._advance()
        target = self._parse_target()
        if self._at_word("be"):
            self._advance()
        elif self._at_word("equal"):
            self._advance()
            if self._at_word("to"):
                self._advance()
        else:
            raise self._error("Expected 'be' in 'let' statement.")
        value = self._parse_expr()
        self._expect_end_of_statement()
        return SetStmt(line=tok.line, column=tok.column, target=target, value=value)

    def _parse_change(self, op: str) -> ChangeStmt:
        tok = self._advance()
        target = self._parse_target()
        if self._at_word("by"):
            self._advance()
            amount = self._parse_expr()
        else:
            amount = Literal(line=tok.line, column=tok.column, value=1)
        self._expect_end_of_statement()
        return ChangeStmt(
            line=tok.line, column=tok.column, target=target, op=op, amount=amount
        )

    def _parse_comma_list(self) -> list[Expr]:
        """Parse expressions separated by ',' or ', and'."""
        items = [self._parse_expr()]
        while self._peek().type == TokenType.COMMA:
            self._advance()
            if self._at_word("and"):
                self._advance()
            items.append(self._parse_expr())
        return items

    def _is_color_phrase_at(self, offset: int = 0) -> bool:
        tok = self._peek(offset)
        if tok.type != TokenType.WORD:
            return False
        if tok.lower in _COLOR_NAMES:
            return True
        if tok.lower == "bright":
            nxt = self._peek(offset + 1)
            return nxt.type == TokenType.WORD and nxt.lower in _COLOR_NAMES
        return False

    def _parse_color_expr(self) -> Expr:
        tok = self._peek()
        if tok.type == TokenType.WORD and tok.lower == "bright":
            nxt = self._peek(1)
            if nxt.type == TokenType.WORD and nxt.lower in _COLOR_NAMES:
                self._advance()
                self._advance()
                return Literal(
                    line=tok.line,
                    column=tok.column,
                    value=f"bright {nxt.lower}",
                )
        if tok.type == TokenType.WORD and tok.lower in _COLOR_NAMES:
            self._advance()
            return Literal(line=tok.line, column=tok.column, value=tok.lower)
        if tok.type == TokenType.STRING:
            self._advance()
            return Literal(line=tok.line, column=tok.column, value=tok.value)
        return self._parse_primary()

    def _parse_say(self) -> SayStmt:
        tok = self._advance()
        if self._peek().type in (TokenType.NEWLINE, TokenType.EOF, TokenType.DEDENT):
            raise self._error(f"Expected something to say after '{tok.lower}'.", tok)
        values = self._parse_comma_list()
        color: Expr | None = None
        background: Expr | None = None
        styles: list[str] = []
        position: str | None = None
        anchor: str | None = None

        while self._peek().type == TokenType.WORD:
            w = self._peek().lower
            if w in ("colour", "color"):
                self._advance()
                color = self._parse_color_expr()
                continue
            if w == "in":
                if self._peek(1).type == TokenType.WORD and self._peek(1).lower in (
                    "colour",
                    "color",
                ):
                    self._advance()
                    self._advance()
                    color = self._parse_color_expr()
                    continue
                if self._is_color_phrase_at(1):
                    self._advance()
                    color = self._parse_color_expr()
                    continue
                break
            if w == "background":
                self._advance()
                background = self._parse_color_expr()
                continue
            if w == "on" and self._is_color_phrase_at(1):
                self._advance()
                background = self._parse_color_expr()
                continue
            if w in _STYLE_WORDS:
                self._advance()
                if w not in styles:
                    styles.append(w)
                continue
            if w == "below":
                self._advance()
                position = "below"
                nxt = self._peek()
                if nxt.type == TokenType.WORD and nxt.lower not in (
                    _STYLE_WORDS
                    | {"colour", "color", "in", "on", "background", "otherwise", "else"}
                ):
                    anchor = str(self._advance().value)
                continue
            if w in ("centered", "centred"):
                self._advance()
                position = "centered"
                continue
            break

        self._expect_end_of_statement()
        return SayStmt(
            line=tok.line,
            column=tok.column,
            values=values,
            color=color,
            background=background,
            styles=styles,
            position=position,
            anchor=anchor,
        )

    def _parse_if(self) -> IfStmt:
        tok = self._advance()
        cond = self._parse_expr()

        if self._at_word("then"):
            self._advance()
            self._inline_if_depth += 1
            try:
                then_stmt = self._parse_statement()
            finally:
                self._inline_if_depth -= 1
            else_body: list[Stmt] = []
            if self._at_word("otherwise") or self._at_word("else"):
                self._advance()
                if self._at_word("then"):
                    self._advance()
                else_body = [self._parse_statement()]
            return IfStmt(
                line=tok.line,
                column=tok.column,
                branches=[
                    IfBranch(
                        condition=cond,
                        body=[then_stmt],
                        line=tok.line,
                        column=tok.column,
                    )
                ],
                else_body=else_body,
            )

        body = self._consume_block("if")
        branches = [
            IfBranch(
                condition=cond, body=body, line=tok.line, column=tok.column
            )
        ]
        else_body = []

        while True:
            self._skip_newlines()
            if self._at_words("otherwise", "if") or self._at_words("else", "if"):
                b_tok = self._advance()
                self._advance()
                b_cond = self._parse_expr()
                b_body = self._consume_block("otherwise if")
                branches.append(
                    IfBranch(
                        condition=b_cond,
                        body=b_body,
                        line=b_tok.line,
                        column=b_tok.column,
                    )
                )
                continue
            if self._at_word("otherwise") or self._at_word("else"):
                self._advance()
                else_body = self._consume_block("otherwise")
                break
            break

        return IfStmt(
            line=tok.line, column=tok.column, branches=branches, else_body=else_body
        )

    def _parse_repeat(self) -> RepeatStmt:
        tok = self._advance()
        count = self._parse_expr()
        self._consume_word("times", "Expected 'times' after repeat count.")
        var_name: str | None = None
        if self._at_word("with"):
            self._advance()
            var_name = str(self._consume_ident("a loop counter variable").value)
        body = self._consume_block("repeat")
        return RepeatStmt(
            line=tok.line, column=tok.column, count=count, var_name=var_name, body=body
        )

    def _parse_for_each(self) -> Stmt:
        tok = self._advance()  # for
        self._advance()  # each
        var1 = str(self._consume_ident("a loop variable name").value)

        if self._at_word("from"):
            self._advance()
            start = self._parse_expr()
            self._consume_word("to", "Expected 'to' in range loop.")
            end = self._parse_expr()
            step: Expr | None = None
            if self._at_word("by"):
                self._advance()
                step = self._parse_expr()
            body = self._consume_block("for each")
            return ForRangeStmt(
                line=tok.line,
                column=tok.column,
                var_name=var1,
                start=start,
                end=end,
                step=step,
                body=body,
            )

        value_var: str | None = None
        if self._at_word("and"):
            self._advance()
            value_var = str(self._consume_ident("a value variable name").value)

        self._consume_word("in", "Expected 'in' or 'from' in 'for each' loop.")
        iterable = self._parse_expr()
        body = self._consume_block("for each")
        return ForEachStmt(
            line=tok.line,
            column=tok.column,
            var_name=var1,
            value_var_name=value_var,
            iterable=iterable,
            body=body,
        )

    def _parse_while(self) -> WhileStmt:
        tok = self._advance()
        condition = self._parse_expr()
        body = self._consume_block("while")
        return WhileStmt(
            line=tok.line, column=tok.column, condition=condition, body=body
        )

    def _parse_func_def(self) -> FuncDefStmt:
        tok = self._advance()  # to
        name = str(self._consume_ident("a function name").value)
        params: list[str] = []
        if self._at_word("with"):
            self._advance()
            params.append(str(self._consume_ident("a parameter name").value))
            while True:
                if self._peek().type == TokenType.COMMA:
                    self._advance()
                    if self._at_word("and"):
                        self._advance()
                    params.append(
                        str(self._consume_ident("a parameter name").value)
                    )
                elif self._at_word("and"):
                    self._advance()
                    params.append(
                        str(self._consume_ident("a parameter name").value)
                    )
                else:
                    break
        body = self._consume_block(f"to {name}")
        return FuncDefStmt(
            line=tok.line, column=tok.column, name=name, params=params, body=body
        )

    def _parse_return(self) -> ReturnStmt:
        tok = self._advance()
        if tok.lower == "give":
            self._advance()  # back
        if self._peek().type in (TokenType.NEWLINE, TokenType.EOF, TokenType.DEDENT):
            value = None
        else:
            value = self._parse_expr()
        self._expect_end_of_statement()
        return ReturnStmt(line=tok.line, column=tok.column, value=value)

    def _parse_try(self) -> TryStmt:
        tok = self._advance()
        try_body = self._consume_block("try")
        self._skip_newlines()
        if not self._at_words("if", "it", "fails"):
            raise self._error("Expected 'if it fails' after 'try' block.")
        self._consume_words("if", "it", "fails")
        error_var: str | None = None
        if self._at_word("with"):
            self._advance()
            error_var = str(self._consume_ident("an error variable name").value)
        catch_body = self._consume_block("if it fails")
        return TryStmt(
            line=tok.line,
            column=tok.column,
            try_body=try_body,
            error_var=error_var,
            catch_body=catch_body,
        )

    def _parse_fail(self) -> FailStmt:
        tok = self._advance()
        self._consume_word("with", "Expected 'with' after 'fail'.")
        message = self._parse_expr()
        self._expect_end_of_statement()
        return FailStmt(line=tok.line, column=tok.column, message=message)

    def _parse_add_or_append(self) -> Stmt:
        tok = self._advance()
        value = self._parse_expr()
        self._consume_word("to", f"Expected 'to' in '{tok.lower}' statement.")
        if tok.lower == "append" and self._at_word("file"):
            self._advance()
            path = self._parse_expr()
            self._expect_end_of_statement()
            return WriteFileStmt(
                line=tok.line, column=tok.column, content=value, path=path, append=True
            )
        target = self._parse_target()
        self._expect_end_of_statement()
        return AddToStmt(
            line=tok.line, column=tok.column, value=value, target=target
        )

    def _parse_remove(self) -> RemoveStmt:
        tok = self._advance()
        kind = "value"
        if self._at_word("item") and not self._at_word("from", 1):
            self._advance()
            kind = "item"
        elif self._at_word("entry") and not self._at_word("from", 1):
            self._advance()
            kind = "entry"
        item = self._parse_expr()
        if kind in ("item", "entry") and self._at_word("of"):
            self._advance()
        else:
            self._consume_word("from", "Expected 'from' in 'remove' statement.")
        target = self._parse_target()
        self._expect_end_of_statement()
        return RemoveStmt(
            line=tok.line, column=tok.column, kind=kind, item=item, target=target
        )

    def _parse_write_file(self) -> WriteFileStmt:
        tok = self._advance()
        content = self._parse_expr()
        self._consume_words("to", "file")
        path = self._parse_expr()
        self._expect_end_of_statement()
        return WriteFileStmt(
            line=tok.line, column=tok.column, content=content, path=path, append=False
        )

    # --- Expressions ---

    def _parse_flag_options(self) -> dict[str, Expr]:
        """Parse `--flag [value]` options into a dict."""
        options: dict[str, Expr] = {}
        while self._peek().type == TokenType.FLAG:
            flag_tok = self._advance()
            key = str(flag_tok.value).lstrip("-").lower()
            nxt = self._peek()
            if nxt.type in (TokenType.NUMBER, TokenType.STRING):
                self._advance()
                options[key] = Literal(line=nxt.line, column=nxt.column, value=nxt.value)
            elif nxt.type == TokenType.LPAREN:
                options[key] = self._parse_primary()
            elif nxt.type == TokenType.WORD and nxt.lower not in _FLAG_VALUE_STOP_WORDS:
                self._advance()
                low = nxt.lower
                if low in ("true", "yes"):
                    val: object = True
                elif low in ("false", "no"):
                    val = False
                else:
                    val = str(nxt.value)
                options[key] = Literal(line=nxt.line, column=nxt.column, value=val)
            else:
                options[key] = Literal(
                    line=flag_tok.line, column=flag_tok.column, value=True
                )
        return options

    def _parse_expr(self) -> Expr:
        return self._parse_pipe()

    def _parse_pipe(self) -> Expr:
        left = self._parse_or()
        while self._peek().type == TokenType.PIPE:
            pipe_tok = self._advance()
            stage_tok = self._consume_ident("a pipe command name")
            stage_name = str(stage_tok.value)
            stage_lower = stage_name.lower()
            if stage_lower == "parse" and self._at_word("json"):
                self._advance()
                stage_name = "parse_json"
                stage_lower = "parse_json"
            args: list[Expr] = []
            options: dict[str, Expr] = {}

            while self._peek().type not in (
                TokenType.PIPE,
                TokenType.NEWLINE,
                TokenType.EOF,
                TokenType.DEDENT,
                TokenType.COMMA,
                TokenType.RPAREN,
            ):
                nxt = self._peek()
                if nxt.type == TokenType.WORD and nxt.lower in (
                    "then",
                    "otherwise",
                    "else",
                    "below",
                    "centered",
                    "centred",
                ):
                    break
                if (
                    stage_lower not in ("colour", "color")
                    and nxt.type == TokenType.WORD
                    and nxt.lower
                    in (
                        _STYLE_WORDS
                        | {"colour", "color", "in", "on", "background"}
                    )
                ):
                    break

                if nxt.type == TokenType.FLAG:
                    options.update(self._parse_flag_options())
                    continue

                if stage_lower in ("colour", "color"):
                    if nxt.type == TokenType.WORD and nxt.lower in _STYLE_WORDS:
                        self._advance()
                        args.append(
                            Literal(line=nxt.line, column=nxt.column, value=nxt.lower)
                        )
                        continue
                    if nxt.type == TokenType.WORD and nxt.lower in ("on", "background"):
                        self._advance()
                        options["background"] = self._parse_color_expr()
                        continue
                    args.append(self._parse_color_expr())
                    continue

                if nxt.type in (TokenType.STRING, TokenType.NUMBER, TokenType.LPAREN):
                    args.append(self._parse_primary())
                    continue

                if self._at_word("by"):
                    self._advance()
                    options["by"] = self._parse_or()
                    continue

                if self._at_word("of") and stage_lower == "bar":
                    self._advance()
                    options["of"] = self._parse_or()
                    continue

                if self._at_word("with"):
                    self._advance()
                    args.append(self._parse_or())
                    continue

                break

            left = PipeExpr(
                line=pipe_tok.line,
                column=pipe_tok.column,
                left=left,
                stage_name=stage_name,
                args=args,
                options=options,
            )
        return left

    def _parse_or(self) -> Expr:
        left = self._parse_and()
        while self._at_word("or"):
            tok = self._advance()
            right = self._parse_and()
            left = BinaryOp(line=tok.line, column=tok.column, op="or", left=left, right=right)
        return left

    def _parse_and(self) -> Expr:
        left = self._parse_not()
        while self._at_word("and"):
            tok = self._advance()
            right = self._parse_not()
            left = BinaryOp(line=tok.line, column=tok.column, op="and", left=left, right=right)
        return left

    def _parse_not(self) -> Expr:
        if self._at_word("not"):
            tok = self._advance()
            operand = self._parse_not()
            return UnaryOp(line=tok.line, column=tok.column, op="not", operand=operand)
        return self._parse_comparison()

    def _match_comparison_op(self) -> tuple[str, Token] | None:
        tok = self._peek()
        if tok.type != TokenType.WORD:
            return None

        phrases: list[tuple[tuple[str, ...], str]] = [
            (("is", "not", "equal", "to"), "!="),
            (("is", "equal", "to"), "=="),
            (("is", "greater", "than"), ">"),
            (("is", "more", "than"), ">"),
            (("is", "less", "than"), "<"),
            (("is", "at", "least"), ">="),
            (("is", "at", "most"), "<="),
            (("is", "not", "in"), "not_in"),
            (("does", "not", "contain"), "not_contains"),
            (("is", "above"), ">"),
            (("is", "below"), "<"),
            (("is", "under"), "<"),
            (("is", "not"), "!="),
            (("is", "in"), "in"),
            (("starts", "with"), "starts_with"),
            (("ends", "with"), "ends_with"),
            (("equals",), "=="),
            (("contains",), "contains"),
            (("is",), "=="),
        ]
        for words, op in phrases:
            if self._at_words(*words):
                for _ in words:
                    self._advance()
                return op, tok
        return None

    def _parse_comparison(self) -> Expr:
        left = self._parse_additive()
        while True:
            matched = self._match_comparison_op()
            if not matched:
                break
            op, tok = matched
            right = self._parse_additive()
            left = CompareOp(
                line=tok.line, column=tok.column, op=op, left=left, right=right
            )
        return left

    def _parse_additive(self) -> Expr:
        left = self._parse_multiplicative()
        while True:
            tok = self._peek()
            if tok.type == TokenType.PLUS or self._at_word("plus"):
                self._advance()
                right = self._parse_multiplicative()
                left = BinaryOp(
                    line=tok.line, column=tok.column, op="+", left=left, right=right
                )
            elif tok.type == TokenType.MINUS or self._at_word("minus"):
                self._advance()
                right = self._parse_multiplicative()
                left = BinaryOp(
                    line=tok.line, column=tok.column, op="-", left=left, right=right
                )
            else:
                break
        return left

    def _can_follow_repeat_times(self) -> bool:
        """Return True if 'times' is acting as the terminator of `repeat N times`."""
        nxt = self._peek(1)
        if nxt.type in (TokenType.NEWLINE, TokenType.EOF, TokenType.COLON, TokenType.DEDENT):
            return True
        if nxt.type == TokenType.WORD and nxt.lower == "with":
            return True
        return False

    def _parse_multiplicative(self) -> Expr:
        left = self._parse_power()
        while True:
            tok = self._peek()
            if tok.type == TokenType.STAR or (
                self._at_word("times") and not self._can_follow_repeat_times()
            ):
                self._advance()
                right = self._parse_power()
                left = BinaryOp(
                    line=tok.line, column=tok.column, op="*", left=left, right=right
                )
            elif self._at_words("whole", "divided", "by"):
                self._consume_words("whole", "divided", "by")
                right = self._parse_power()
                left = BinaryOp(
                    line=tok.line, column=tok.column, op="//", left=left, right=right
                )
            elif tok.type == TokenType.SLASH or self._at_words("divided", "by"):
                if tok.type == TokenType.SLASH:
                    self._advance()
                else:
                    self._consume_words("divided", "by")
                right = self._parse_power()
                left = BinaryOp(
                    line=tok.line, column=tok.column, op="/", left=left, right=right
                )
            elif self._at_word("modulo") or self._at_word("mod"):
                self._advance()
                right = self._parse_power()
                left = BinaryOp(
                    line=tok.line, column=tok.column, op="%", left=left, right=right
                )
            else:
                break
        return left

    def _parse_power(self) -> Expr:
        left = self._parse_unary()
        if self._at_words("to", "the", "power", "of"):
            tok = self._peek()
            self._consume_words("to", "the", "power", "of")
            right = self._parse_power()
            return BinaryOp(
                line=tok.line, column=tok.column, op="**", left=left, right=right
            )
        return left

    def _can_start_expr(self, offset: int = 0) -> bool:
        tok = self._peek(offset)
        if tok.type in (
            TokenType.NUMBER,
            TokenType.STRING,
            TokenType.LPAREN,
            TokenType.MINUS,
        ):
            return True
        if tok.type == TokenType.WORD:
            return tok.lower not in _NON_EXPR_START_WORDS
        return False

    def _parse_unary(self) -> Expr:
        tok = self._peek()
        if tok.type == TokenType.MINUS or self._at_word("negative"):
            self._advance()
            operand = self._parse_unary()
            return UnaryOp(line=tok.line, column=tok.column, op="neg", operand=operand)

        if self._at_words("has", "flag"):
            self._advance()
            self._advance()
            return FlagExpr(
                line=tok.line, column=tok.column, name=self._parse_single_flag_name()
            )
        if self._at_word("flag") and (
            self._peek(1).type == TokenType.FLAG
            or (
                self._peek(1).type == TokenType.MINUS
                and self._peek(2).type == TokenType.WORD
            )
        ):
            self._advance()
            return FlagExpr(
                line=tok.line, column=tok.column, name=self._parse_single_flag_name()
            )

        if (
            self._at_word("current")
            and self._peek(1).type == TokenType.WORD
            and self._peek(1).lower in _CURRENT_TIME_ATTRS
        ):
            self._advance()
            attr_tok = self._advance()
            options = (
                self._parse_flag_options()
                if self._peek().type == TokenType.FLAG
                else {}
            )
            return LibCallExpr(
                line=tok.line,
                column=tok.column,
                name=attr_tok.lower,
                args=[],
                options=options,
            )

        # Optional leading 'the' before English prefix operations.
        if self._at_word("the") and self._peek(1).lower in _UNARY_PHRASE_HEADS:
            self._advance()
            tok = self._peek()

        if self._at_words("length", "of"):
            self._consume_words("length", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="length", args=[self._parse_unary()]
            )
        if self._at_words("first", "item", "of"):
            self._consume_words("first", "item", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="first_item",
                args=[self._parse_unary()],
            )
        if self._at_words("last", "item", "of"):
            self._consume_words("last", "item", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="last_item",
                args=[self._parse_unary()],
            )
        if self._at_word("item") and self._can_start_expr(1):
            self._advance()
            index = self._parse_expr()
            self._consume_word("of", "Expected 'of' after item index.")
            container = self._parse_unary()
            return ItemAccess(
                line=tok.line, column=tok.column, container=container, index=index
            )
        if self._at_word("entry") and self._can_start_expr(1):
            self._advance()
            key = self._parse_expr()
            self._consume_word("of", "Expected 'of' after entry key.")
            mapping = self._parse_unary()
            return EntryAccess(
                line=tok.line, column=tok.column, mapping=mapping, key=key
            )
        if self._at_words("keys", "of"):
            self._consume_words("keys", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="keys", args=[self._parse_unary()]
            )
        if self._at_words("values", "of"):
            self._consume_words("values", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="values", args=[self._parse_unary()]
            )
        if self._at_words("uppercase", "of"):
            self._consume_words("uppercase", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="uppercase",
                args=[self._parse_unary()],
            )
        if self._at_words("lowercase", "of"):
            self._consume_words("lowercase", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="lowercase",
                args=[self._parse_unary()],
            )
        if self._at_words("words", "of"):
            self._consume_words("words", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="words", args=[self._parse_unary()]
            )
        if self._at_words("lines", "of"):
            self._consume_words("lines", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="lines", args=[self._parse_unary()]
            )
        if self._at_words("absolute", "of"):
            self._consume_words("absolute", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="abs", args=[self._parse_unary()]
            )
        if self._at_words("square", "root", "of"):
            self._consume_words("square", "root", "of")
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="sqrt", args=[self._parse_unary()]
            )
        if self._at_words("number", "of"):
            self._consume_words("number", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="to_number",
                args=[self._parse_unary()],
            )
        if self._at_words("text", "of"):
            self._consume_words("text", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="to_text",
                args=[self._parse_unary()],
            )
        if self._at_words("type", "of"):
            self._consume_words("type", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="type_of",
                args=[self._parse_unary()],
            )
        if self._at_word("joined") and self._can_start_expr(1):
            self._advance()
            items = self._parse_expr()
            self._consume_word("with", "Expected 'with' after list in 'joined'.")
            sep = self._parse_unary()
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="joined", args=[items, sep]
            )
        if self._at_words("random", "number", "from"):
            self._consume_words("random", "number", "from")
            low = self._parse_expr()
            self._consume_word("to", "Expected 'to' in 'random number from ... to ...'.")
            high = self._parse_unary()
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="random_int", args=[low, high]
            )
        if self._at_words("read", "file"):
            self._consume_words("read", "file")
            return ReadFileExpr(
                line=tok.line, column=tok.column, path=self._parse_unary()
            )
        if self._at_words("read", "key") or self._at_words("wait", "for", "key"):
            self._advance()
            self._advance()
            if self._at_word("key"):
                self._advance()
            return ReadKeyExpr(line=tok.line, column=tok.column)
        if self._at_word("choose"):
            self._advance()
            prompt_expr: Expr | None = None
            if self._at_word("from"):
                self._advance()
            else:
                prompt_expr = self._parse_expr()
                self._consume_word("from", "Expected 'from' in 'choose ... from ...'.")
            options_expr = self._parse_unary()
            return ChooseExpr(
                line=tok.line,
                column=tok.column,
                options=options_expr,
                prompt=prompt_expr,
            )
        if self._at_words("file", "exists"):
            self._consume_words("file", "exists")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="file_exists",
                args=[self._parse_unary()],
            )
        if self._at_words("files", "in"):
            self._consume_words("files", "in")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="list_files",
                args=[self._parse_unary()],
            )
        if self._at_words("parse", "json"):
            self._consume_words("parse", "json")
            if self._at_word("of"):
                self._advance()
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="from_json",
                args=[self._parse_unary()],
            )
        if self._at_words("json", "of"):
            self._consume_words("json", "of")
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="to_json",
                args=[self._parse_unary()],
            )
        if self._at_words("terminal", "width"):
            self._consume_words("terminal", "width")
            return LibCallExpr(
                line=tok.line, column=tok.column, name="terminal_width", args=[], options={}
            )
        if self._at_words("terminal", "height"):
            self._consume_words("terminal", "height")
            return LibCallExpr(
                line=tok.line, column=tok.column, name="terminal_height", args=[], options={}
            )
        if self._at_words("progress", "bar") or (
            self._at_word("bar") and self._can_start_expr(1)
        ):
            self._advance()
            if self._at_word("bar"):
                self._advance()
            val_expr = self._parse_additive()
            opts: dict[str, Expr] = {}
            if self._at_word("of"):
                self._advance()
                opts["of"] = self._parse_additive()
            if self._peek().type == TokenType.FLAG:
                opts.update(self._parse_flag_options())
            return LibCallExpr(
                line=tok.line, column=tok.column, name="bar", args=[val_expr], options=opts
            )
        if self._at_word("env") and self._can_start_expr(1):
            self._advance()
            return LibCallExpr(
                line=tok.line,
                column=tok.column,
                name="env",
                args=[self._parse_unary()],
                options={},
            )
        if self._at_word("split") and self._can_start_expr(1):
            self._advance()
            txt_expr = self._parse_expr()
            if self._at_word("by"):
                self._advance()
                sep_expr = self._parse_unary()
                return BuiltinExpr(
                    line=tok.line, column=tok.column, name="split", args=[txt_expr, sep_expr]
                )
            return BuiltinExpr(
                line=tok.line, column=tok.column, name="split", args=[txt_expr]
            )
        if self._at_word("replace") and self._can_start_expr(1):
            self._advance()
            old_expr = self._parse_expr()
            self._consume_word("with", "Expected 'with' in 'replace ... with ... in ...'.")
            new_expr = self._parse_expr()
            self._consume_word("in", "Expected 'in' in 'replace ... with ... in ...'.")
            target_expr = self._parse_unary()
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="replace",
                args=[target_expr, old_expr, new_expr],
            )
        if self._at_words("unique", "of") or (
            self._at_word("unique") and self._can_start_expr(1)
        ):
            self._advance()
            if self._at_word("of"):
                self._advance()
            return BuiltinExpr(
                line=tok.line,
                column=tok.column,
                name="unique",
                args=[self._parse_unary()],
            )
        if self._at_word("ask"):
            self._advance()
            return AskExpr(
                line=tok.line, column=tok.column, prompt=self._parse_unary()
            )

        for optional_of_word, builtin_name in (
            ("trimmed", "trimmed"),
            ("sorted", "sorted"),
            ("reversed", "reversed"),
            ("rounded", "rounded"),
        ):
            if self._at_word(optional_of_word):
                if self._at_word("of", 1):
                    self._advance()
                    self._advance()
                    return BuiltinExpr(
                        line=tok.line,
                        column=tok.column,
                        name=builtin_name,
                        args=[self._parse_unary()],
                    )
                if self._can_start_expr(1):
                    self._advance()
                    return BuiltinExpr(
                        line=tok.line,
                        column=tok.column,
                        name=builtin_name,
                        args=[self._parse_unary()],
                    )

        return self._parse_postfix()

    def _parse_postfix(self) -> Expr:
        expr = self._parse_primary()
        while self._peek().type == TokenType.POSSESSIVE:
            poss = self._advance()
            field = self._consume_ident("a field name after 's")
            expr = FieldAccess(
                line=poss.line,
                column=poss.column,
                obj=expr,
                field=str(field.value),
            )
        return expr

    def _parse_call_expr(self, start_tok: Token | None = None) -> CallExpr:
        tok = start_tok or self._advance()
        name = str(self._consume_ident("a function name").value)
        args: list[Expr] = []
        if self._at_word("with"):
            self._advance()
            args = self._parse_comma_list()
        return CallExpr(line=tok.line, column=tok.column, name=name, args=args)

    def _parse_map_key(self) -> Expr:
        tok = self._peek()
        if tok.type in (TokenType.STRING, TokenType.NUMBER):
            self._advance()
            return Literal(line=tok.line, column=tok.column, value=tok.value)
        if tok.type == TokenType.WORD:
            self._advance()
            return Literal(line=tok.line, column=tok.column, value=str(tok.value))
        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            if self._peek().type != TokenType.RPAREN:
                raise self._error("Expected ')' after map key.")
            self._advance()
            return expr
        raise self._error("Expected a map key (word or text).")

    def _parse_primary(self) -> Expr:
        tok = self._peek()

        if tok.type == TokenType.NUMBER or tok.type == TokenType.STRING:
            self._advance()
            return Literal(line=tok.line, column=tok.column, value=tok.value)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expr()
            if self._peek().type != TokenType.RPAREN:
                raise self._error("Expected matching ')'.")
            self._advance()
            return expr

        if tok.type == TokenType.WORD:
            w = tok.lower
            if w in ("true", "yes"):
                self._advance()
                return Literal(line=tok.line, column=tok.column, value=True)
            if w in ("false", "no"):
                self._advance()
                return Literal(line=tok.line, column=tok.column, value=False)
            if w == "nothing":
                self._advance()
                return Literal(line=tok.line, column=tok.column, value=None)

            if self._at_words("an", "empty", "list") or self._at_words("empty", "list"):
                self._advance()
                if w == "an":
                    self._advance()
                self._advance()
                return ListLiteral(line=tok.line, column=tok.column, elements=[])

            if self._at_words("a", "list", "of"):
                self._consume_words("a", "list", "of")
                elements = self._parse_comma_list()
                return ListLiteral(line=tok.line, column=tok.column, elements=elements)

            if self._at_words("an", "empty", "map") or self._at_words("empty", "map"):
                self._advance()
                if w == "an":
                    self._advance()
                self._advance()
                return MapLiteral(line=tok.line, column=tok.column, pairs=[])

            if self._at_words("a", "map", "with"):
                self._consume_words("a", "map", "with")
                pairs: list[tuple[Expr, Expr]] = []
                while True:
                    key = self._parse_map_key()
                    self._consume_word("as", "Expected 'as' between map key and value.")
                    val = self._parse_expr()
                    pairs.append((key, val))
                    if self._peek().type == TokenType.COMMA:
                        self._advance()
                        if self._at_word("and"):
                            self._advance()
                        continue
                    break
                return MapLiteral(line=tok.line, column=tok.column, pairs=pairs)

            if w == "call":
                return self._parse_call_expr()

            if w in _LIB_COMMANDS and self._peek(1).type == TokenType.FLAG:
                self._advance()
                options = self._parse_flag_options()
                return LibCallExpr(
                    line=tok.line,
                    column=tok.column,
                    name=w,
                    args=[],
                    options=options,
                )

            if w == "the" and self._peek(1).type == TokenType.WORD:
                self._advance()
                ident = self._advance()
                return Var(
                    line=ident.line, column=ident.column, name=str(ident.value)
                )

            self._advance()
            return Var(line=tok.line, column=tok.column, name=str(tok.value))

        raise self._error(f"Unexpected '{tok.value}' in expression.", tok)


def parse_source(source: str) -> Program:
    """Lex and parse SayLang source text into an AST."""
    tokens = tokenize(source)
    return Parser(tokens, source=source).parse()
