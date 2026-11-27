"""Build a standalone SayLang executable using PyInstaller."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    runtime_file = ROOT / "saylang" / "runtime.py"
    entrypoint = ROOT / "scripts" / "entrypoint.py"
    add_data = f"{runtime_file}{os.pathsep}saylang"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--name",
        "saylang",
        "--clean",
        "--noconfirm",
        "--add-data",
        add_data,
    ]
    ico_file = ROOT / "assets" / "icon.ico"
    if sys.platform == "win32" and ico_file.is_file():
        cmd.extend(["--icon", str(ico_file)])
    try:
        import certifi  # type: ignore[import-not-found]  # noqa: F401

        cmd.extend(["--collect-data", "certifi", "--hidden-import", "certifi"])
    except ImportError:
        pass
    cmd.append(str(entrypoint))
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)

    ext = ".exe" if sys.platform == "win32" else ""
    out_bin = ROOT / "dist" / f"saylang{ext}"
    if not out_bin.is_file():
        raise FileNotFoundError(f"Expected binary not found at {out_bin}")
    print(f"Built standalone binary: {out_bin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
