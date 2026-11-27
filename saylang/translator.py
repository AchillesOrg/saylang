"""Natural-English to SayLang translator (offline rules + pluggable LLM APIs)."""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from saylang.ast_nodes import (
    ForEachStmt,
    ForRangeStmt,
    FuncDefStmt,
    Program,
    RepeatStmt,
    SayStmt,
    SetStmt,
    Var,
)
from saylang.errors import SayError, SayTranslateError
from saylang.parser import parse_source
from saylang.runtime import AUTO_LIB_VALUES

_SAYLANG_GRAMMAR_GUIDE = """You translate everyday English instructions into SayLang (.pl), a deterministic plain-English programming language.

Rules of SayLang:
- Indentation (4 spaces) defines blocks. Trailing ':' on headers is optional.
- No curly braces, square brackets, semicolons, or '!=' / '&&' / '||'.
- Comments: `# comment` or `note comment`
- Variables: `set name to value` or `let name be value`
- Mutation: `increase x by 5`, `decrease x by 1`
- Output: `say "Hello, ", name` or `print "Hello, ", name`
- Colored/styled output: `say "hello world lol" colour red`, `say "OK" color green bold`, `say "Alert" colour white on red underline`
- Prebuilt auto-imported libraries (`time`, `ascii`, `color`, `text`, `math`, `sys`, `flags`, `tty`):
  - `import time, ascii` (optional — libraries also auto-import)
  - `time`, `time --12h`, `date`, `date --iso`, `hour`, `minute`, `second`, `weekday`
  - Pipes: `print time --12h | ascii --size default`, `say "hi" | box | colour cyan`
  - Layout: `print date below time`, `say "Title" centered`, `clear screen`, `wait 1 second`, `every 1 second`
- CLI script flags: `flags: -d`, `if flag -d then print date below time`
- Input: `set name to ask "What is your name? "`
- Conditionals: `if ...`, `otherwise if ...`, `otherwise` (or inline `if ... then ...`)
- Comparisons: `is`, `is not`, `is greater than`, `is less than`, `is at least`, `is at most`, `contains`, `does not contain`, `is in`, `starts with`, `ends with`
- Logic: `and`, `or`, `not`
- Math: `plus`, `minus`, `times`, `divided by`, `whole divided by`, `modulo`, `to the power of`, `negative`
- Loops:
  - `repeat 5 times` (or `repeat 5 times with i`)
  - `for each i from 1 to 10` (optional `by 2`)
  - `for each item in items`
  - `for each key and value in my_map`
  - `while count is less than 10`
  - `stop` (break), `skip` (continue)
- Lists & Maps:
  - `an empty list` or `a list of 1, 2, 3`
  - `add x to my_list`, `remove item 1 from my_list`, `remove "a" from my_list`
  - `item 1 of my_list`, `first item of my_list`, `last item of my_list`, `length of my_list`
  - `an empty map` or `a map with name as "Ada", age as 36`
  - `user's name` (or `entry "name" of user`)
- Functions:
  - `to add with a and b` ... `return a plus b`
  - `call add with 2, 3`
- Errors:
  - `try` ... `if it fails with err` ...
  - `fail with "message"`
- Files:
  - `write text to file "out.txt"`, `append text to file "out.txt"`, `read file "out.txt"`

Never reference undefined variables: use built-in `time`/`hour`/`minute`/`date` for clock queries, or initialize variables first, and `say`/`print` the result so the snippet runs cleanly.
Output ONLY valid SayLang source code. Do not include markdown fences or explanations."""

_KNOWN_COLORS_PATTERN = (
    r"(?:bright\s+)?(?:black|red|green|yellow|blue|magenta|purple|cyan|white|gray|grey|orange|pink)"
)


@dataclass
class TranslationResult:
    """Result of translating everyday English into SayLang source code."""

    say_code: str
    backend: str
    notes: list[str] = field(default_factory=list)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def _detect_provider(provider: str, api_key: str | None) -> tuple[str, str | None]:
    p = provider.lower().strip()
    if p == "offline":
        return "offline", None
    if p == "gemini":
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise SayTranslateError(
                "Gemini translation requested, but GEMINI_API_KEY is not set."
            )
        return "gemini", key
    if p == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SayTranslateError(
                "OpenAI translation requested, but OPENAI_API_KEY is not set."
            )
        return "openai", key
    if p == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SayTranslateError(
                "Anthropic translation requested, but ANTHROPIC_API_KEY is not set."
            )
        return "anthropic", key
    if p == "auto":
        if os.environ.get("GEMINI_API_KEY"):
            return "gemini", os.environ["GEMINI_API_KEY"]
        if os.environ.get("OPENAI_API_KEY"):
            return "openai", os.environ["OPENAI_API_KEY"]
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic", os.environ["ANTHROPIC_API_KEY"]
        return "offline", None
    raise SayTranslateError(
        f"Unknown translation provider '{provider}'. Use auto, offline, gemini, openai, or anthropic."
    )


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSL context with fallback CA bundles for standalone binaries."""
    env_cert = os.environ.get("SSL_CERT_FILE")
    if env_cert and Path(env_cert).is_file():
        return ssl.create_default_context(cafile=env_cert)

    try:
        import certifi  # type: ignore[import-not-found]

        certifi_ca = certifi.where()
        if certifi_ca and Path(certifi_ca).is_file():
            return ssl.create_default_context(cafile=certifi_ca)
    except ImportError:
        pass

    default_ca = ssl.get_default_verify_paths().cafile
    if default_ca and Path(default_ca).is_file():
        return ssl.create_default_context(cafile=default_ca)

    for candidate in (
        "/etc/ssl/cert.pem",
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/opt/homebrew/etc/openssl@3/cert.pem",
        "/opt/homebrew/etc/openssl@4/cert.pem",
    ):
        if Path(candidate).is_file():
            return ssl.create_default_context(cafile=candidate)

    return ssl.create_default_context()


_GEMINI_FALLBACK_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-flash-latest",
)


def _extract_api_error_message(body: str) -> str:
    """Extract a clean single-line error message from JSON API responses."""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"]).strip()
            if parsed.get("message"):
                return str(parsed["message"]).strip()
    except (json.JSONDecodeError, TypeError):
        pass
    collapsed = " ".join(body.split())
    return collapsed[:200] if collapsed else "Unknown API error"


def _http_post_json(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    *,
    timeout: int = 15,
) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    ssl_ctx = _build_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_ctx) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        clean_msg = _extract_api_error_message(err_body)
        err = SayTranslateError(f"LLM API returned HTTP {exc.code}: {clean_msg}")
        err.retryable = exc.code in (404, 408, 429, 500, 502, 503, 504)  # type: ignore[attr-defined]
        raise err from exc
    except (TimeoutError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", exc)
        err = SayTranslateError(f"Could not reach LLM API: {reason}")
        err.retryable = True  # type: ignore[attr-defined]
        raise err from exc
    except json.JSONDecodeError as exc:
        raise SayTranslateError("Invalid JSON response from LLM API.") from exc


def _call_llm(
    backend: str, api_key: str, model: str | None, prompt: str
) -> str:
    if backend == "gemini":
        candidates_models = (model,) if model else _GEMINI_FALLBACK_MODELS
        payload = {
            "systemInstruction": {"parts": [{"text": _SAYLANG_GRAMMAR_GUIDE}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        last_err: SayTranslateError | None = None
        for chosen in candidates_models:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{chosen}:generateContent?key={api_key}"
            )
            try:
                resp = _http_post_json(url, payload, {})
            except SayTranslateError as exc:
                last_err = exc
                if getattr(exc, "retryable", False):
                    continue
                raise
            try:
                candidates = resp["candidates"]  # type: ignore[index]
                parts = candidates[0]["content"]["parts"]
                return "".join(str(p.get("text", "")) for p in parts)
            except (KeyError, IndexError, TypeError) as exc:
                raise SayTranslateError(
                    "Unexpected response structure from Gemini API."
                ) from exc
        assert last_err is not None
        raise last_err

    if backend == "openai":
        chosen = model or "gpt-4o-mini"
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": chosen,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": _SAYLANG_GRAMMAR_GUIDE},
                {"role": "user", "content": prompt},
            ],
        }
        resp = _http_post_json(
            url, payload, {"Authorization": f"Bearer {api_key}"}
        )
        try:
            choices = resp["choices"]  # type: ignore[index]
            return str(choices[0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise SayTranslateError(
                "Unexpected response structure from OpenAI API."
            ) from exc

    if backend == "anthropic":
        chosen = model or "claude-3-5-haiku-latest"
        url = "https://api.anthropic.com/v1/messages"
        payload = {
            "model": chosen,
            "max_tokens": 2048,
            "temperature": 0.1,
            "system": _SAYLANG_GRAMMAR_GUIDE,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = _http_post_json(
            url,
            payload,
            {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        try:
            content = resp["content"]  # type: ignore[index]
            return "".join(
                str(block.get("text", ""))
                for block in content
                if block.get("type") == "text"
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise SayTranslateError(
                "Unexpected response structure from Anthropic API."
            ) from exc

    raise SayTranslateError(f"Unsupported LLM backend '{backend}'.")


# --- Offline rule-based translator ---


def _protect_quotes(text: str) -> tuple[str, list[str]]:
    """Replace quoted string literals with placeholders."""
    strings: list[str] = []
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ('"', "'"):
            if (
                ch == "'"
                and i > 0
                and (text[i - 1].isalnum() or text[i - 1] == "_")
                and i + 1 < n
                and text[i + 1].lower() == "s"
                and (i + 2 == n or not (text[i + 2].isalnum() or text[i + 2] == "_"))
            ):
                out.append(ch)
                i += 1
                continue
            quote = ch
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                j += 1
            placeholder = f"__STR_{len(strings)}__"
            strings.append(text[i:j])
            out.append(placeholder)
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out), strings


def _restore_quotes(text: str, strings: list[str]) -> str:
    for idx, val in enumerate(strings):
        text = text.replace(f"__STR_{idx}__", val)
    return text


def _normalize_expr(expr: str, strings: list[str]) -> str:
    """Normalize everyday English operator synonyms into SayLang syntax."""
    s = expr.strip()
    replacements = [
        (r"\bis\s+bigger\s+than\b", "is greater than"),
        (r"\bis\s+larger\s+than\b", "is greater than"),
        (r"\bis\s+higher\s+than\b", "is greater than"),
        (r"\bis\s+smaller\s+than\b", "is less than"),
        (r"\bdoes\s+not\s+equal\b", "is not equal to"),
        (r"\bdoesn't\s+equal\b", "is not equal to"),
        (r"\bisn't\s+equal\s+to\b", "is not equal to"),
        (r"\bisn't\b", "is not"),
        (r"\bare\s+not\b", "is not"),
        (r"\baren't\b", "is not"),
        (r"\bmultiplied\s+by\b", "times"),
        (r"\badded\s+to\b", "plus"),
        (r"\bsubtracted\s+by\b", "minus"),
        (r"\bdivided\s+with\b", "divided by"),
        (r"\bis\s+equal\s+to\b", "is equal to"),
        (r"\ba\s+new\s+list\s+of\b", "a list of"),
        (r"\ba\s+new\s+empty\s+list\b", "an empty list"),
        (r"\ba\s+new\s+empty\s+map\b", "an empty map"),
    ]
    for pattern, repl in replacements:
        s = re.sub(pattern, repl, s, flags=re.IGNORECASE)
    return _restore_quotes(s, strings)


def _is_valid_say_expr(expr_text: str) -> bool:
    try:
        parse_source(f"say {expr_text}")
        return True
    except SayError:
        return False


def _format_say_arg(
    raw_arg: str, strings: list[str], defined_vars: set[str]
) -> str:
    norm = _normalize_expr(raw_arg, strings).strip()
    if (
        re.fullmatch(r"[A-Za-z_]\w*", norm)
        and norm.lower() not in ("true", "false", "yes", "no", "nothing")
        and norm.lower() not in AUTO_LIB_VALUES
        and norm not in defined_vars
    ):
        return f'"{norm}"'
    if _is_valid_say_expr(norm):
        return norm
    escaped = norm.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _extract_say_modifiers(raw_arg: str) -> tuple[str, list[str]]:
    """Peel trailing display modifiers (color/background/styles) from a say phrase."""
    text = raw_arg.strip()
    mods: list[str] = []

    while True:
        m_style = re.match(
            r"^(.*\S)\s+(bold|dim|italic|underline)$",
            text,
            flags=re.IGNORECASE,
        )
        if m_style:
            text = m_style.group(1).strip()
            mods.insert(0, m_style.group(2).lower())
            continue

        m_bg = re.match(
            rf"^(.*\S)\s+(?:on|background)\s+({_KNOWN_COLORS_PATTERN})$",
            text,
            flags=re.IGNORECASE,
        )
        if m_bg:
            text = m_bg.group(1).strip()
            mods.insert(0, f"on {' '.join(m_bg.group(2).lower().split())}")
            continue

        m_fg = re.match(
            rf"^(.*\S)\s+(?:(?:in\s+)?(?:colou?r)|in)\s+({_KNOWN_COLORS_PATTERN})$",
            text,
            flags=re.IGNORECASE,
        )
        if m_fg:
            text = m_fg.group(1).strip()
            mods.insert(0, f"colour {' '.join(m_fg.group(2).lower().split())}")
            continue

        break

    return text, mods


def _record_defined_vars(program: Program, defined_vars: set[str]) -> None:
    for stmt in program.statements:
        if isinstance(stmt, SetStmt) and isinstance(stmt.target, Var):
            defined_vars.add(stmt.target.name)
        elif isinstance(stmt, FuncDefStmt):
            defined_vars.add(stmt.name)
            defined_vars.update(stmt.params)
        elif isinstance(stmt, (ForEachStmt, ForRangeStmt)):
            defined_vars.add(stmt.var_name)
            if isinstance(stmt, ForEachStmt) and stmt.value_var_name:
                defined_vars.add(stmt.value_var_name)
        elif isinstance(stmt, RepeatStmt) and stmt.var_name:
            defined_vars.add(stmt.var_name)


def _is_unquoted_undefined_say(prog: Program, defined_vars: set[str]) -> bool:
    if len(prog.statements) != 1 or not isinstance(prog.statements[0], SayStmt):
        return False
    say_stmt = prog.statements[0]
    if len(say_stmt.values) != 1 or not isinstance(say_stmt.values[0], Var):
        return False
    name = say_stmt.values[0].name
    return name not in defined_vars and name.lower() not in AUTO_LIB_VALUES


def _translate_single_clause(
    clause: str,
    strings: list[str],
    indent: str,
    defined_vars: set[str],
) -> list[str]:
    """Translate a single natural-English clause into one or more SayLang lines."""
    raw = clause.strip().rstrip(".")
    if not raw:
        return []

    restored_raw = _restore_quotes(raw, strings)

    m_add_num = re.match(
        r"^add\s+(\d+(?:\.\d+)?)\s+to\s+([A-Za-z_]\w*)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m_add_num:
        return [f"{indent}increase {m_add_num.group(2)} by {m_add_num.group(1)}"]

    try:
        prog = parse_source(restored_raw)
        if not _is_unquoted_undefined_say(prog, defined_vars):
            _record_defined_vars(prog, defined_vars)
            return [f"{indent}{restored_raw}"]
    except SayError:
        pass

    norm_full = _normalize_expr(raw, strings)
    try:
        prog = parse_source(norm_full)
        if not _is_unquoted_undefined_say(prog, defined_vars):
            _record_defined_vars(prog, defined_vars)
            return [f"{indent}{norm_full}"]
    except SayError:
        pass

    if raw.startswith("#") or raw.lower().startswith("note"):
        return [f"{indent}{restored_raw}"]

    m = re.match(
        r"^(?:define|create|make)\s+(?:a\s+)?function\s+(?:called\s+)?([A-Za-z_]\w*)"
        r"(?:\s+(?:that\s+takes|taking|with(?:\s+parameters?)?)\s+(.+?))?"
        r"(?:\s+(?:and\s+)?(?:returns?|that\s+returns?|gives?\s+back)\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        fn_name, params_raw, ret_raw = m.group(1), m.group(2), m.group(3)
        defined_vars.add(fn_name)
        header = f"{indent}to {fn_name}"
        if params_raw:
            cleaned_params = re.sub(
                r"\s*,\s*|\s+and\s+", " and ", params_raw.strip(), flags=re.IGNORECASE
            )
            for pname in re.findall(r"[A-Za-z_]\w*", cleaned_params):
                if pname.lower() != "and":
                    defined_vars.add(pname)
            header += f" with {cleaned_params}"
        lines = [header]
        if ret_raw:
            lines.append(
                f"{indent}    return {_normalize_expr(ret_raw, strings)}"
            )
        return lines

    m = re.match(
        r"^count\s+(?:up\s+|down\s+)?from\s+(.+?)\s+to\s+(.+?)"
        r"(?:\s+by\s+(.+?))?"
        r"(?:\s*(?:,|and|then)\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        start_s = _normalize_expr(m.group(1), strings)
        end_s = _normalize_expr(m.group(2), strings)
        step_s = _normalize_expr(m.group(3), strings) if m.group(3) else None
        action_s = m.group(4)

        var_name = "number"
        defined_vars.add(var_name)
        body_lines: list[str]
        if action_s:
            act_clean = re.sub(
                r"\b(?:each|every|the)\s+number\b",
                var_name,
                action_s.strip(),
                flags=re.IGNORECASE,
            )
            body_lines = _translate_single_clause(
                act_clean, strings, indent + "    ", defined_vars
            )
        else:
            body_lines = [f"{indent}    say {var_name}"]

        header = f"{indent}for each {var_name} from {start_s} to {end_s}"
        if step_s:
            header += f" by {step_s}"
        return [header, *body_lines]

    m = re.match(
        r"^(?:repeat|loop|do(?:\s+this)?)\s+(.+?)\s+times\b"
        r"(?:\s*(?::|,|\band\b|\bthen\b)\s*(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        cnt = _normalize_expr(m.group(1), strings)
        action_s = m.group(2)
        lines = [f"{indent}repeat {cnt} times"]
        if action_s:
            lines.extend(
                _translate_single_clause(
                    action_s, strings, indent + "    ", defined_vars
                )
            )
        return lines

    m = re.match(
        r"^(?:for\s+each|for\s+every|loop\s+over)\s+([A-Za-z_]\w*)\s+in\s+(.+?)"
        r"(?:\s*(?::|,|\bthen\b|\band\b)\s*(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        var_name = m.group(1)
        defined_vars.add(var_name)
        iterable = _normalize_expr(m.group(2), strings)
        action_s = m.group(3)
        if not action_s:
            inline_m = re.match(
                r"^(.+?)\s+((?:print|say|display|output|show|increase|decrease|set)\b.+)$",
                m.group(2).strip(),
                flags=re.IGNORECASE,
            )
            if inline_m:
                iterable = _normalize_expr(inline_m.group(1), strings)
                action_s = inline_m.group(2)
        lines = [f"{indent}for each {var_name} in {iterable}"]
        if action_s:
            lines.extend(
                _translate_single_clause(
                    action_s, strings, indent + "    ", defined_vars
                )
            )
        return lines

    m = re.match(
        r"^(?:otherwise\s+if|else\s+if|elif)\s+(.+?)(?:\s*:\s*|\s+then\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        cond = _normalize_expr(m.group(1), strings)
        lines = [f"{indent}otherwise if {cond}"]
        if m.group(2):
            lines.extend(
                _translate_single_clause(
                    m.group(2), strings, indent + "    ", defined_vars
                )
            )
        return lines

    m = re.match(
        r"^if\s+(.+?)\s*(?:,\s*then|\bthen)\s+(.+?)(?:\s*(?:,|;)?\s*(?:otherwise|else)\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        cond = _normalize_expr(m.group(1), strings)
        then_part = m.group(2)
        else_part = m.group(3)
        lines = [f"{indent}if {cond}"]
        lines.extend(
            _translate_single_clause(
                then_part, strings, indent + "    ", defined_vars
            )
        )
        if else_part:
            lines.append(f"{indent}otherwise")
            lines.extend(
                _translate_single_clause(
                    else_part, strings, indent + "    ", defined_vars
                )
            )
        return lines

    m = re.match(r"^if\s+(.+?):?$", raw, flags=re.IGNORECASE)
    if m and (raw.endswith(":") or "," not in raw):
        cond = _normalize_expr(m.group(1), strings)
        return [f"{indent}if {cond}"]

    if raw.lower().rstrip(":") in ("otherwise", "else"):
        return [f"{indent}otherwise"]

    m = re.match(
        r"^while\s+(.+?)(?:\s*:\s*|\s+(?:then|do)\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        cond = _normalize_expr(m.group(1), strings)
        lines = [f"{indent}while {cond}"]
        if m.group(2):
            lines.extend(
                _translate_single_clause(
                    m.group(2), strings, indent + "    ", defined_vars
                )
            )
        return lines

    m = re.match(
        r"^(?:create|make|define|initialize)\s+(?:a\s+)?(?:new\s+)?(?:variable\s+)?(?:called\s+)?"
        r"([A-Za-z_]\w*)\s+(?:equal\s+to|equals|to|as|be|with\s+value|=)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        defined_vars.add(m.group(1))
        return [
            f"{indent}set {m.group(1)} to {_normalize_expr(m.group(2), strings)}"
        ]

    m = re.match(
        r"^store\s+(.+?)\s+(?:in|into)\s+(?:variable\s+)?([A-Za-z_]\w*)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        defined_vars.add(m.group(2))
        return [
            f"{indent}set {m.group(2)} to {_normalize_expr(m.group(1), strings)}"
        ]

    m = re.match(r"^([A-Za-z_]\w*)\s*=\s*(.+)$", raw)
    if m:
        defined_vars.add(m.group(1))
        return [
            f"{indent}set {m.group(1)} to {_normalize_expr(m.group(2), strings)}"
        ]

    m = re.match(
        r"^(?:increment|raise)\s+([A-Za-z_]\w*)(?:\s+by\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        amt = _normalize_expr(m.group(2), strings) if m.group(2) else "1"
        return [f"{indent}increase {m.group(1)} by {amt}"]

    m = re.match(
        r"^(?:decrement|lower)\s+([A-Za-z_]\w*)(?:\s+by\s+(.+))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        amt = _normalize_expr(m.group(2), strings) if m.group(2) else "1"
        return [f"{indent}decrease {m.group(1)} by {amt}"]

    m = re.match(
        r"^subtract\s+(.+?)\s+from\s+([A-Za-z_]\w*)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        return [
            f"{indent}decrease {m.group(2)} by {_normalize_expr(m.group(1), strings)}"
        ]

    m = re.match(
        r"^(?:print(?:\s+out)?|display|output|show|say)\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if m:
        body_part, mods = _extract_say_modifiers(m.group(1))
        arg_text = _format_say_arg(body_part, strings, defined_vars)
        suffix = (" " + " ".join(mods)) if mods else ""
        return [f"{indent}say {arg_text}{suffix}"]

    m = re.match(r"^(?:returns?|give\s+back)\s+(.+)$", raw, flags=re.IGNORECASE)
    if m:
        return [f"{indent}return {_normalize_expr(m.group(1), strings)}"]

    raise SayTranslateError(
        f'Could not translate "{restored_raw}" offline. '
        "Rephrase using clearer SayLang/English structure, or set GEMINI_API_KEY, "
        "OPENAI_API_KEY, or ANTHROPIC_API_KEY for full AI-assisted translation."
    )


def _translate_offline(text: str) -> str:
    """Deterministically translate everyday English lines/sentences into SayLang."""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out_lines: list[str] = []
    defined_vars: set[str] = set()

    for line in raw_lines:
        if not line.strip():
            continue
        indent_len = len(line) - len(line.lstrip(" "))
        indent = " " * indent_len
        body = line.strip()
        protected, strings = _protect_quotes(body)

        parts = [
            p.strip()
            for p in re.split(r"(?<=\S)[.;]\s+", protected)
            if p.strip()
        ]
        for part in parts:
            out_lines.extend(
                _translate_single_clause(part, strings, indent, defined_vars)
            )

    result = "\n".join(out_lines).strip()
    if not result:
        raise SayTranslateError("No instructions found to translate.")

    parse_source(result)
    return result


def translate_english(
    text: str,
    *,
    provider: str = "auto",
    model: str | None = None,
    api_key: str | None = None,
    max_retries: int = 2,
    context_vars: list[str] | None = None,
) -> TranslationResult:
    """Translate loose everyday English into validated SayLang source code."""
    backend, resolved_key = _detect_provider(provider, api_key)
    if backend == "offline":
        say_code = _translate_offline(text)
        return TranslationResult(
            say_code=say_code,
            backend="offline",
            notes=["Translated with built-in offline English rules."],
        )

    assert resolved_key is not None
    notes: list[str] = []
    ctx_note = (
        f"\n\nCurrently defined variables in this session: {', '.join(context_vars)}"
        if context_vars
        else ""
    )
    prompt = (
        f"Translate the following instructions into SayLang:{ctx_note}\n\n{text.strip()}"
    )
    last_error: SayError | None = None

    for attempt in range(max_retries + 1):
        try:
            raw_reply = _call_llm(backend, resolved_key, model, prompt)
        except SayTranslateError as err:
            if provider == "auto" and getattr(err, "retryable", False):
                try:
                    offline_code = _translate_offline(text)
                    return TranslationResult(
                        say_code=offline_code,
                        backend="offline",
                        notes=[f"LLM unavailable ({err.message}); fell back to offline rules."],
                    )
                except SayTranslateError:
                    raise SayTranslateError(
                        f"{err.message} (Tip: use :english --offline for simpler built-in commands.)"
                    ) from err
            raise
        candidate = _strip_code_fences(raw_reply)
        try:
            parse_source(candidate)
            if attempt > 0:
                notes.append(
                    f"Self-corrected SayLang syntax after {attempt} retry(ies)."
                )
            return TranslationResult(
                say_code=candidate, backend=backend, notes=notes
            )
        except SayError as err:
            last_error = err
            prompt = (
                f"Your previous SayLang code had a syntax error:\n"
                f"{err.format_pretty()}\n\n"
                f"Previous code:\n{candidate}\n\n"
                f"Original English request:\n{text.strip()}\n\n"
                "Fix the syntax error and output ONLY valid SayLang code."
            )

    raise SayTranslateError(
        f"LLM ({backend}) produced invalid SayLang code after {max_retries + 1} attempts: "
        f"{last_error.message if last_error else 'unknown error'}"
    )
