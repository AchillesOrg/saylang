"""Standalone native binary bundler for SayLang (.pl) programs."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from saylang.parser import parse_source
from saylang.transpiler import compile_to_python

# Split literals so contiguous markers do not sit directly in Python bytecode constants.
_MAGIC_BEG = b"SAYLANG_" + b"APP_BEG!"
_MAGIC_END = b"SAYLANG_" + b"APP_END!"
_LEN_FMT = "<Q"
_LEN_SIZE = struct.calcsize(_LEN_FMT)
_TAIL_SIZE = _LEN_SIZE + len(_MAGIC_END)
_MIN_TRAILER_SIZE = len(_MAGIC_BEG) + _LEN_SIZE + _TAIL_SIZE
_MIN_EMBED_VERSION = (0, 4, 0)
_VERSION_RE = re.compile(r"saylang\s+(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class EmbeddedApp:
    """Payload embedded inside a standalone compiled SayLang executable."""

    name: str
    source: str


@dataclass(frozen=True)
class BuildResult:
    """Result returned after building a standalone native executable."""

    output_path: Path
    size_bytes: int
    backend: str


def normalize_output_path(path: Path) -> Path:
    """Ensure .exe extension on Windows when not already present."""
    if sys.platform == "win32" and path.suffix.lower() != ".exe":
        return Path(f"{path}.exe")
    return path


def default_output_path(source_path: Path | None) -> Path:
    """Return default compiled binary output path in the working directory."""
    stem = source_path.stem if source_path is not None and source_path.stem else "app"
    return normalize_output_path(Path(stem))


def encode_bundle_trailer(source: str, name: str = "app.pl") -> bytes:
    """Encode a framed UTF-8 JSON payload trailer for appending to a native binary."""
    payload = json.dumps(
        {"v": 1, "name": name or "app.pl", "source": source}, ensure_ascii=False
    ).encode("utf-8")
    len_bytes = struct.pack(_LEN_FMT, len(payload))
    return _MAGIC_BEG + len_bytes + payload + len_bytes + _MAGIC_END


def _find_trailer_span(data: bytes) -> tuple[int, bytes] | None:
    """Return (trailer_start_offset, payload_bytes) if data ends with a valid trailer."""
    total = len(data)
    if total < _MIN_TRAILER_SIZE or not data.endswith(_MAGIC_END):
        return None
    (tail_len,) = struct.unpack_from(_LEN_FMT, data, total - _TAIL_SIZE)
    trailer_size = _MIN_TRAILER_SIZE + tail_len
    if tail_len > total or trailer_size > total:
        return None
    start = total - trailer_size
    if not data.startswith(_MAGIC_BEG, start):
        return None
    (head_len,) = struct.unpack_from(_LEN_FMT, data, start + len(_MAGIC_BEG))
    if head_len != tail_len:
        return None
    payload_start = start + len(_MAGIC_BEG) + _LEN_SIZE
    return start, data[payload_start : payload_start + tail_len]


def _parse_payload(payload: bytes) -> EmbeddedApp | None:
    try:
        obj = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict) or obj.get("v") != 1:
        return None
    src = obj.get("source")
    name = obj.get("name", "app.pl")
    if not isinstance(src, str) or not isinstance(name, str):
        return None
    return EmbeddedApp(name=name, source=src)


def decode_bundle_trailer(data: bytes) -> EmbeddedApp | None:
    """Decode an embedded SayLang app trailer from raw binary bytes."""
    found = _find_trailer_span(data)
    if found is None:
        return None
    return _parse_payload(found[1])


def strip_existing_trailer(data: bytes) -> bytes:
    """Remove any existing embedded trailer from a host binary buffer."""
    found = _find_trailer_span(data)
    if found is None:
        return data
    return data[: found[0]]


def read_embedded_app(exe_path: Path | None = None) -> EmbeddedApp | None:
    """Read an embedded SayLang app trailer from an executable in O(1) tail I/O."""
    target = exe_path if exe_path is not None else Path(sys.executable)
    try:
        size = target.stat().st_size
        if size < _MIN_TRAILER_SIZE:
            return None
        with target.open("rb") as fh:
            fh.seek(size - _TAIL_SIZE)
            tail = fh.read(_TAIL_SIZE)
            if len(tail) != _TAIL_SIZE or not tail.endswith(_MAGIC_END):
                return None
            (tail_len,) = struct.unpack_from(_LEN_FMT, tail, 0)
            trailer_size = _MIN_TRAILER_SIZE + tail_len
            if tail_len > size or trailer_size > size:
                return None
            start = size - trailer_size
            fh.seek(start)
            head_and_payload = fh.read(len(_MAGIC_BEG) + _LEN_SIZE + tail_len)
    except OSError:
        return None

    if len(head_and_payload) != len(_MAGIC_BEG) + _LEN_SIZE + tail_len:
        return None
    if not head_and_payload.startswith(_MAGIC_BEG):
        return None
    (head_len,) = struct.unpack_from(_LEN_FMT, head_and_payload, len(_MAGIC_BEG))
    if head_len != tail_len:
        return None
    return _parse_payload(head_and_payload[len(_MAGIC_BEG) + _LEN_SIZE :])


def _is_native_executable(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        with path.open("rb") as fh:
            head = fh.read(4)
    except OSError:
        return False
    return (
        head in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe", b"\x7fELF")
        or head[:2] == b"MZ"
    )


def _runtime_supports_embedding(path: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    m = _VERSION_RE.search(proc.stdout)
    if not m:
        return False
    ver = tuple(int(p) for p in m.groups())
    return ver >= _MIN_EMBED_VERSION


def find_runtime_binary(override: Path | None = None) -> Path | None:
    """Locate a native standalone saylang runtime binary suitable for self-embedding."""
    if override is not None:
        if not override.is_file():
            raise FileNotFoundError(f"Runtime binary not found: {override}")
        return override

    env_bin = os.environ.get("SAYLANG_RUNTIME_BIN", "").strip()
    if env_bin:
        p = Path(env_bin)
        if p.is_file():
            return p

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        if exe.is_file():
            return exe

    exe_name = "saylang.exe" if sys.platform == "win32" else "saylang"
    candidates: list[Path] = [
        Path(__file__).resolve().parent.parent / "dist" / exe_name,
        Path.home() / ".local" / "bin" / exe_name,
    ]
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidates.append(Path(local_app) / "saylang" / "saylang.exe")

    for cand in candidates:
        if _is_native_executable(cand) and _runtime_supports_embedding(cand):
            return cand
    return None


def _build_with_pyinstaller(source: str, out_path: Path) -> BuildResult:
    py_code = compile_to_python(source, standalone=True)
    with tempfile.TemporaryDirectory(prefix="saylang_build_") as tmpdir:
        tmp = Path(tmpdir)
        entry_py = tmp / "entry.py"
        entry_py.write_text(py_code, encoding="utf-8")
        build_name = out_path.stem or "app"
        dist_dir = tmp / "dist"
        work_dir = tmp / "work"
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--onefile",
            "--clean",
            "--noconfirm",
            "--name",
            build_name,
            "--distpath",
            str(dist_dir),
            "--workpath",
            str(work_dir),
            "--specpath",
            str(tmp),
            str(entry_py),
        ]
        subprocess.run(cmd, check=True)
        built_name = f"{build_name}.exe" if sys.platform == "win32" else build_name
        built = dist_dir / built_name
        if not built.is_file():
            raise FileNotFoundError(f"PyInstaller finished without producing {built}")
        if out_path.parent:
            out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, out_path)
    if sys.platform != "win32":
        os.chmod(out_path, 0o755)
    return BuildResult(
        output_path=out_path,
        size_bytes=out_path.stat().st_size,
        backend="pyinstaller",
    )


def build_standalone_binary(
    source_path: Path | None = None,
    *,
    source: str | None = None,
    name: str | None = None,
    output_path: Path | None = None,
    runtime_binary: Path | None = None,
) -> BuildResult:
    """Compile a SayLang program into a standalone native executable binary."""
    if source is None:
        if source_path is None:
            raise ValueError("Provide either source_path or source text.")
        if not source_path.is_file():
            raise FileNotFoundError(f"File not found: {source_path}")
        src = source_path.read_text(encoding="utf-8")
        app_name = name or source_path.name
    else:
        src = source
        app_name = name or (source_path.name if source_path is not None else "app.pl")

    # Validate syntax before emitting anything.
    parse_source(src)

    out = normalize_output_path(
        output_path if output_path is not None else default_output_path(source_path)
    )

    host_bin = find_runtime_binary(runtime_binary)
    if host_bin is not None:
        try:
            same_file = host_bin.resolve() == out.resolve()
        except OSError:
            same_file = False
        if same_file:
            raise RuntimeError("Output path cannot overwrite the running saylang binary.")

        host_bytes = strip_existing_trailer(host_bin.read_bytes())
        trailer = encode_bundle_trailer(src, name=app_name)
        if out.parent:
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(host_bytes + trailer)
        if sys.platform != "win32":
            os.chmod(out, 0o755)
        return BuildResult(
            output_path=out,
            size_bytes=len(host_bytes) + len(trailer),
            backend="self-embed",
        )

    if importlib.util.find_spec("PyInstaller") is not None:
        return _build_with_pyinstaller(src, out)

    raise RuntimeError(
        "To build standalone binaries, run the installed 'saylang' binary "
        "(from install.sh / install.ps1) or install PyInstaller (pip install pyinstaller)."
    )
