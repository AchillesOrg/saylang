"""Standalone binary entrypoint for SayLang."""

import sys

from saylang.runtime import say_configure_utf8_stdio
from saylang.cli import main

if __name__ == "__main__":
    say_configure_utf8_stdio()
    raise SystemExit(main())
