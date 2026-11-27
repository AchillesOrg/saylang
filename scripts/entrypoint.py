"""Standalone binary entrypoint for SayLang."""

import sys

from saylang.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
