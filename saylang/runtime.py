"""Shared runtime helpers used by both the SayLang interpreter and transpiler."""

from __future__ import annotations

from saylang.errors import SayRuntimeError

# --- SAYLANG RUNTIME START ---
import math
import random
import sys
from pathlib import Path

try:
    SayRuntimeError  # type: ignore[used-before-def]
except NameError:

    class SayRuntimeError(Exception):
        """Runtime error raised by standalone compiled SayLang programs."""

        def __init__(
            self,
            message: str,
            line: int = 0,
            column: int = 0,
            source_line: str = "",
        ) -> None:
            super().__init__(message)
            self.message = message
            self.line = line
            self.column = column
            self.source_line = source_line


_ANSI_INITIALIZED = False

_FG_COLORS: dict[str, str] = {
    "black": "30",
    "red": "31",
    "green": "32",
    "yellow": "33",
    "blue": "34",
    "magenta": "35",
    "purple": "35",
    "cyan": "36",
    "white": "37",
    "gray": "90",
    "grey": "90",
    "orange": "38;5;208",
    "pink": "38;5;213",
    "bright black": "90",
    "bright red": "91",
    "bright green": "92",
    "bright yellow": "93",
    "bright blue": "94",
    "bright magenta": "95",
    "bright purple": "95",
    "bright cyan": "96",
    "bright white": "97",
    "bright gray": "37",
    "bright grey": "37",
    "bright orange": "38;5;214",
    "bright pink": "38;5;219",
}

_BG_COLORS: dict[str, str] = {
    "black": "40",
    "red": "41",
    "green": "42",
    "yellow": "43",
    "blue": "44",
    "magenta": "45",
    "purple": "45",
    "cyan": "46",
    "white": "47",
    "gray": "100",
    "grey": "100",
    "orange": "48;5;208",
    "pink": "48;5;213",
    "bright black": "100",
    "bright red": "101",
    "bright green": "102",
    "bright yellow": "103",
    "bright blue": "104",
    "bright magenta": "105",
    "bright purple": "105",
    "bright cyan": "106",
    "bright white": "107",
    "bright gray": "47",
    "bright grey": "47",
    "bright orange": "48;5;214",
    "bright pink": "48;5;219",
}

_TEXT_STYLES: dict[str, str] = {
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
}


def _enable_windows_ansi() -> None:
    """Best-effort enablement of ANSI VT100 escapes on Windows terminals."""
    global _ANSI_INITIALIZED
    if _ANSI_INITIALIZED or sys.platform != "win32":
        _ANSI_INITIALIZED = True
        return
    _ANSI_INITIALIZED = True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def say_style_text(
    text: str,
    color: object = None,
    background: object = None,
    styles: list[str] | None = None,
) -> str:
    """Wrap text in ANSI color and style codes when display modifiers are set."""
    if color is None and background is None and not styles:
        return text

    _enable_windows_ansi()
    codes: list[str] = []

    if styles:
        for style in styles:
            key = str(style).strip().lower()
            if key not in _TEXT_STYLES:
                supported = ", ".join(sorted(_TEXT_STYLES))
                raise SayRuntimeError(
                    f"Unknown text style '{style}'. Supported styles: {supported}."
                )
            codes.append(_TEXT_STYLES[key])

    if color is not None:
        if not isinstance(color, str):
            raise SayRuntimeError(
                f"Color must be text, got {say_type_of(color)}."
            )
        norm_color = " ".join(color.strip().lower().split())
        if norm_color not in _FG_COLORS:
            supported = ", ".join(
                k for k in _FG_COLORS if not k.startswith("bright ")
            )
            raise SayRuntimeError(
                f"Unknown colour '{color}'. Try: {supported} (or 'bright <colour>')."
            )
        codes.append(_FG_COLORS[norm_color])

    if background is not None:
        if not isinstance(background, str):
            raise SayRuntimeError(
                f"Background color must be text, got {say_type_of(background)}."
            )
        norm_bg = " ".join(background.strip().lower().split())
        if norm_bg not in _BG_COLORS:
            supported = ", ".join(
                k for k in _BG_COLORS if not k.startswith("bright ")
            )
            raise SayRuntimeError(
                f"Unknown background colour '{background}'. Try: {supported} (or 'bright <colour>')."
            )
        codes.append(_BG_COLORS[norm_bg])

    if not codes:
        return text
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def _is_number(val: object) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)


def _check_int_index(index: object) -> int:
    if isinstance(index, bool) or not isinstance(index, (int, float)):
        raise SayRuntimeError(
            f"Expected a whole number index, got {say_type_of(index)}."
        )
    if isinstance(index, float):
        if not index.is_integer():
            raise SayRuntimeError(f"Index must be a whole number, got {index}.")
        return int(index)
    return index


def say_repr(val: object) -> str:
    """Format a value for display inside a collection."""
    if isinstance(val, str):
        return f'"{val}"'
    return say_to_text(val)


def say_to_text(val: object) -> str:
    """Convert any SayLang value into readable text."""
    if val is None:
        return "nothing"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, float):
        if math.isfinite(val) and val.is_integer():
            return str(int(val))
        return str(val)
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return "[" + ", ".join(say_repr(item) for item in val) + "]"
    if isinstance(val, dict):
        pairs = [f"{k}: {say_repr(v)}" for k, v in val.items()]
        return "{" + ", ".join(pairs) + "}"
    if callable(val):
        name = getattr(val, "name", None) or getattr(val, "__name__", "function")
        return f"<function {name}>"
    return str(val)


def say_to_number(val: object) -> int | float:
    """Convert a number or numeric string into an int or float."""
    if _is_number(val):
        return val  # type: ignore[return-value]
    if isinstance(val, str):
        stripped = val.strip()
        if not stripped:
            raise SayRuntimeError("Cannot convert empty text to a number.")
        try:
            if "." in stripped or "e" in stripped.lower():
                num = float(stripped)
                return int(num) if num.is_integer() and "." not in stripped else num
            return int(stripped)
        except ValueError as exc:
            raise SayRuntimeError(
                f'Cannot convert "{val}" to a number.'
            ) from exc
    raise SayRuntimeError(
        f"Cannot convert {say_type_of(val)} to a number."
    )


def say_type_of(val: object) -> str:
    """Return the SayLang type name of a value."""
    if val is None:
        return "nothing"
    if isinstance(val, bool):
        return "boolean"
    if _is_number(val):
        return "number"
    if isinstance(val, str):
        return "text"
    if isinstance(val, list):
        return "list"
    if isinstance(val, dict):
        return "map"
    if callable(val):
        return "function"
    return type(val).__name__


def say_is_truthy(val: object) -> bool:
    """Return SayLang truthiness of a value."""
    if val is None or val is False:
        return False
    if _is_number(val):
        return val != 0
    if isinstance(val, (str, list, dict)):
        return len(val) > 0
    return True


def say_negate(val: object) -> int | float:
    """Negate a numeric value."""
    if not _is_number(val):
        raise SayRuntimeError(f"Cannot negate {say_type_of(val)}.")
    return -val  # type: ignore[operator]


def say_add(a: object, b: object) -> object:
    """Add two numbers, concatenate lists, or join text."""
    if isinstance(a, str) or isinstance(b, str):
        return say_to_text(a) + say_to_text(b)
    if isinstance(a, list) and isinstance(b, list):
        return a + b
    if _is_number(a) and _is_number(b):
        return a + b  # type: ignore[operator]
    raise SayRuntimeError(
        f"Cannot add {say_type_of(a)} and {say_type_of(b)}."
    )


def say_sub(a: object, b: object) -> int | float:
    """Subtract two numbers."""
    if _is_number(a) and _is_number(b):
        return a - b  # type: ignore[operator]
    raise SayRuntimeError(
        f"Cannot subtract {say_type_of(b)} from {say_type_of(a)}."
    )


def say_mul(a: object, b: object) -> object:
    """Multiply two numbers or repeat text by a whole number."""
    if _is_number(a) and _is_number(b):
        return a * b  # type: ignore[operator]
    if isinstance(a, str) and isinstance(b, int) and not isinstance(b, bool):
        if b < 0:
            raise SayRuntimeError("Cannot repeat text a negative number of times.")
        return a * b
    if isinstance(b, str) and isinstance(a, int) and not isinstance(a, bool):
        if a < 0:
            raise SayRuntimeError("Cannot repeat text a negative number of times.")
        return b * a
    raise SayRuntimeError(
        f"Cannot multiply {say_type_of(a)} and {say_type_of(b)}."
    )


def say_div(a: object, b: object) -> float:
    """Divide two numbers."""
    if not (_is_number(a) and _is_number(b)):
        raise SayRuntimeError(
            f"Cannot divide {say_type_of(a)} by {say_type_of(b)}."
        )
    if b == 0:
        raise SayRuntimeError("Cannot divide by zero.")
    return a / b  # type: ignore[operator]


def say_floordiv(a: object, b: object) -> int:
    """Integer-divide two numbers."""
    if not (_is_number(a) and _is_number(b)):
        raise SayRuntimeError(
            f"Cannot whole-divide {say_type_of(a)} by {say_type_of(b)}."
        )
    if b == 0:
        raise SayRuntimeError("Cannot divide by zero.")
    return int(a // b)  # type: ignore[operator]


def say_mod(a: object, b: object) -> int | float:
    """Compute modulo of two numbers."""
    if not (_is_number(a) and _is_number(b)):
        raise SayRuntimeError(
            f"Cannot compute modulo of {say_type_of(a)} and {say_type_of(b)}."
        )
    if b == 0:
        raise SayRuntimeError("Cannot take modulo by zero.")
    return a % b  # type: ignore[operator]


def say_pow(a: object, b: object) -> int | float:
    """Raise a number to a power."""
    if _is_number(a) and _is_number(b):
        return a ** b  # type: ignore[operator]
    raise SayRuntimeError(
        f"Cannot raise {say_type_of(a)} to the power of {say_type_of(b)}."
    )


def _say_equals(a: object, b: object) -> bool:
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_say_equals(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if len(a) != len(b) or set(a.keys()) != set(b.keys()):
            return False
        return all(_say_equals(a[k], b[k]) for k in a)
    return a == b


def _say_contains(container: object, needle: object) -> bool:
    if isinstance(container, str):
        if not isinstance(needle, str):
            raise SayRuntimeError(
                f"Cannot check if text contains {say_type_of(needle)}."
            )
        return needle in container
    if isinstance(container, list):
        return any(_say_equals(item, needle) for item in container)
    if isinstance(container, dict):
        return needle in container
    raise SayRuntimeError(
        f"Cannot check if {say_type_of(container)} contains a value."
    )


def say_compare(op: str, a: object, b: object) -> bool:
    """Compare two SayLang values using a named comparison operator."""
    if op == "==":
        return _say_equals(a, b)
    if op == "!=":
        return not _say_equals(a, b)
    if op in (">", "<", ">=", "<="):
        if (_is_number(a) and _is_number(b)) or (
            isinstance(a, str) and isinstance(b, str)
        ):
            if op == ">":
                return a > b  # type: ignore[operator]
            if op == "<":
                return a < b  # type: ignore[operator]
            if op == ">=":
                return a >= b  # type: ignore[operator]
            return a <= b  # type: ignore[operator]
        raise SayRuntimeError(
            f"Cannot compare {say_type_of(a)} and {say_type_of(b)}."
        )
    if op == "contains":
        return _say_contains(a, b)
    if op == "not_contains":
        return not _say_contains(a, b)
    if op == "in":
        return _say_contains(b, a)
    if op == "not_in":
        return not _say_contains(b, a)
    if op == "starts_with":
        if not (isinstance(a, str) and isinstance(b, str)):
            raise SayRuntimeError("starts with requires text values.")
        return a.startswith(b)
    if op == "ends_with":
        if not (isinstance(a, str) and isinstance(b, str)):
            raise SayRuntimeError("ends with requires text values.")
        return a.endswith(b)
    raise SayRuntimeError(f"Unknown comparison operator '{op}'.")


def say_get_item(container: object, index: object) -> object:
    """Get 1-based item from a list or text."""
    idx = _check_int_index(index)
    if not isinstance(container, (list, str)):
        raise SayRuntimeError(
            f"Cannot get an item from {say_type_of(container)}."
        )
    if idx < 1 or idx > len(container):
        raise SayRuntimeError(
            f"Item {idx} is out of range (length is {len(container)})."
        )
    return container[idx - 1]


def say_set_item(container: object, index: object, value: object) -> None:
    """Set 1-based item in a list."""
    idx = _check_int_index(index)
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Cannot update an item in {say_type_of(container)}."
        )
    if idx < 1 or idx > len(container):
        raise SayRuntimeError(
            f"Item {idx} is out of range (length is {len(container)})."
        )
    container[idx - 1] = value


def say_first_item(container: object) -> object:
    """Return the first item of a list or character of text."""
    if not isinstance(container, (list, str)):
        raise SayRuntimeError(
            f"Cannot get the first item of {say_type_of(container)}."
        )
    if len(container) == 0:
        raise SayRuntimeError("Cannot get the first item of an empty collection.")
    return container[0]


def say_last_item(container: object) -> object:
    """Return the last item of a list or character of text."""
    if not isinstance(container, (list, str)):
        raise SayRuntimeError(
            f"Cannot get the last item of {say_type_of(container)}."
        )
    if len(container) == 0:
        raise SayRuntimeError("Cannot get the last item of an empty collection.")
    return container[-1]


def say_get_entry(mapping: object, key: object) -> object:
    """Look up a key in a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Cannot get an entry from {say_type_of(mapping)}."
        )
    if key not in mapping:
        raise SayRuntimeError(f"Map has no entry named '{say_to_text(key)}'.")
    return mapping[key]


def say_set_entry(mapping: object, key: object, value: object) -> None:
    """Set a key in a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Cannot set an entry on {say_type_of(mapping)}."
        )
    mapping[key] = value


def say_get_field(obj: object, field: str) -> object:
    """Access a named field on a map via possessive syntax (x's y)."""
    if not isinstance(obj, dict):
        raise SayRuntimeError(
            f"Cannot access field '{field}' on {say_type_of(obj)}."
        )
    if field not in obj:
        raise SayRuntimeError(f"Map has no field named '{field}'.")
    return obj[field]


def say_set_field(obj: object, field: str, value: object) -> None:
    """Set a named field on a map via possessive syntax."""
    if not isinstance(obj, dict):
        raise SayRuntimeError(
            f"Cannot set field '{field}' on {say_type_of(obj)}."
        )
    obj[field] = value


def say_add_to(container: object, value: object) -> None:
    """Append a value to a list."""
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Can only add items to a list, not {say_type_of(container)}."
        )
    container.append(value)


def say_remove_value(container: object, value: object) -> None:
    """Remove the first matching value from a list."""
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Can only remove values from a list, not {say_type_of(container)}."
        )
    for idx, item in enumerate(container):
        if _say_equals(item, value):
            container.pop(idx)
            return
    raise SayRuntimeError(
        f"Value {say_repr(value)} was not found in the list."
    )


def say_remove_item(container: object, index: object) -> None:
    """Remove a 1-based item index from a list."""
    idx = _check_int_index(index)
    if not isinstance(container, list):
        raise SayRuntimeError(
            f"Can only remove items from a list, not {say_type_of(container)}."
        )
    if idx < 1 or idx > len(container):
        raise SayRuntimeError(
            f"Item {idx} is out of range (length is {len(container)})."
        )
    container.pop(idx - 1)


def say_remove_entry(mapping: object, key: object) -> None:
    """Remove a key from a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Can only remove entries from a map, not {say_type_of(mapping)}."
        )
    if key not in mapping:
        raise SayRuntimeError(f"Map has no entry named '{say_to_text(key)}'.")
    del mapping[key]


def say_range(start: object, end: object, step: object = None) -> list[int | float]:
    """Generate an inclusive range from start to end."""
    if not (_is_number(start) and _is_number(end)):
        raise SayRuntimeError("Range start and end must be numbers.")
    s = start
    e = end
    if step is None:
        st: int | float = 1 if s <= e else -1  # type: ignore[operator]
    else:
        if not _is_number(step):
            raise SayRuntimeError("Range step must be a number.")
        st = step  # type: ignore[assignment]
        if st == 0:
            raise SayRuntimeError("Range step cannot be zero.")

    if isinstance(s, int) and isinstance(e, int) and isinstance(st, int):
        stop = e + 1 if st > 0 else e - 1
        return list(range(s, stop, st))

    results: list[int | float] = []
    cur = float(s)  # type: ignore[arg-type]
    limit = float(e)  # type: ignore[arg-type]
    step_f = float(st)
    if step_f > 0:
        while cur <= limit + 1e-9:
            results.append(int(cur) if cur.is_integer() else cur)
            cur += step_f
    else:
        while cur >= limit - 1e-9:
            results.append(int(cur) if cur.is_integer() else cur)
            cur += step_f
    return results


def say_iter(iterable: object) -> list[object]:
    """Return a list of items to iterate over cleanly."""
    if isinstance(iterable, list):
        return list(iterable)
    if isinstance(iterable, str):
        return list(iterable)
    if isinstance(iterable, dict):
        return list(iterable.keys())
    raise SayRuntimeError(
        f"Cannot iterate over {say_type_of(iterable)}."
    )


def say_iter_pairs(mapping: object) -> list[tuple[object, object]]:
    """Return key/value pairs from a map."""
    if not isinstance(mapping, dict):
        raise SayRuntimeError(
            f"Expected a map for key and value iteration, got {say_type_of(mapping)}."
        )
    return list(mapping.items())


def say_length(val: object) -> int:
    """Return the length of text, list, or map."""
    if isinstance(val, (str, list, dict)):
        return len(val)
    raise SayRuntimeError(f"Cannot get the length of {say_type_of(val)}.")


def say_keys(val: object) -> list[object]:
    """Return the keys of a map as a list."""
    if not isinstance(val, dict):
        raise SayRuntimeError(f"Cannot get keys of {say_type_of(val)}.")
    return list(val.keys())


def say_values(val: object) -> list[object]:
    """Return the values of a map as a list."""
    if not isinstance(val, dict):
        raise SayRuntimeError(f"Cannot get values of {say_type_of(val)}.")
    return list(val.values())


def say_uppercase(val: object) -> str:
    """Return uppercase text."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot uppercase {say_type_of(val)}.")
    return val.upper()


def say_lowercase(val: object) -> str:
    """Return lowercase text."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot lowercase {say_type_of(val)}.")
    return val.lower()


def say_trimmed(val: object) -> str:
    """Trim leading and trailing whitespace from text."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot trim {say_type_of(val)}.")
    return val.strip()


def say_words(val: object) -> list[str]:
    """Split text into whitespace-delimited words."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot split {say_type_of(val)} into words.")
    return val.split()


def say_lines(val: object) -> list[str]:
    """Split text into lines."""
    if not isinstance(val, str):
        raise SayRuntimeError(f"Cannot split {say_type_of(val)} into lines.")
    return val.splitlines()


def say_joined(items: object, sep: object) -> str:
    """Join a list into text using separator."""
    if not isinstance(items, list):
        raise SayRuntimeError(f"Cannot join {say_type_of(items)}.")
    if not isinstance(sep, str):
        raise SayRuntimeError("Join separator must be text.")
    return sep.join(say_to_text(item) for item in items)


def say_sorted(items: object) -> list[object]:
    """Return a sorted copy of a list."""
    if not isinstance(items, list):
        raise SayRuntimeError(f"Cannot sort {say_type_of(items)}.")
    try:
        return sorted(items)
    except TypeError as exc:
        raise SayRuntimeError("Cannot sort items of incompatible types.") from exc


def say_reversed(val: object) -> object:
    """Return a reversed copy of a list or text."""
    if isinstance(val, list):
        return list(reversed(val))
    if isinstance(val, str):
        return val[::-1]
    raise SayRuntimeError(f"Cannot reverse {say_type_of(val)}.")


def say_rounded(val: object) -> int:
    """Round a number to the nearest integer."""
    if not _is_number(val):
        raise SayRuntimeError(f"Cannot round {say_type_of(val)}.")
    return round(val)  # type: ignore[arg-type]


def say_abs(val: object) -> int | float:
    """Return the absolute value of a number."""
    if not _is_number(val):
        raise SayRuntimeError(
            f"Cannot compute absolute value of {say_type_of(val)}."
        )
    return abs(val)  # type: ignore[arg-type]


def say_sqrt(val: object) -> float:
    """Return the square root of a non-negative number."""
    if not _is_number(val):
        raise SayRuntimeError(
            f"Cannot compute square root of {say_type_of(val)}."
        )
    if val < 0:  # type: ignore[operator]
        raise SayRuntimeError("Cannot compute square root of a negative number.")
    return math.sqrt(val)  # type: ignore[arg-type]


def say_random_int(low: object, high: object) -> int:
    """Return a random integer between low and high inclusive."""
    if isinstance(low, bool) or isinstance(high, bool):
        raise SayRuntimeError("Random range bounds must be whole numbers.")
    if not (isinstance(low, int) and isinstance(high, int)):
        raise SayRuntimeError("Random range bounds must be whole numbers.")
    if low > high:
        raise SayRuntimeError(
            f"Random range is backwards: {low} is greater than {high}."
        )
    return random.randint(low, high)


def say_read_file(path: object) -> str:
    """Read UTF-8 text from a file."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise SayRuntimeError(f"Could not read file '{path}': {exc}") from exc


def say_write_file(path: object, content: object) -> None:
    """Write text to a file, creating parent directories if needed."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    try:
        target = Path(path)
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(say_to_text(content), encoding="utf-8")
    except OSError as exc:
        raise SayRuntimeError(f"Could not write file '{path}': {exc}") from exc


def say_append_file(path: object, content: object) -> None:
    """Append text to a file."""
    if not isinstance(path, str):
        raise SayRuntimeError("File path must be text.")
    try:
        target = Path(path)
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            fh.write(say_to_text(content))
    except OSError as exc:
        raise SayRuntimeError(f"Could not append to file '{path}': {exc}") from exc


# --- SAYLANG RUNTIME END ---
