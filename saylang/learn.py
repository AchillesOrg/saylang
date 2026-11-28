"""freeCodeCamp-style interactive TUI course for learning SayLang (`saylang learn`)."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from saylang import __version__, runtime
from saylang.errors import SayError
from saylang.interpreter import run_and_capture
from saylang.nana import (
    NanaBuffer,
    _clip_ansi,
    _compose_screen,
    _enter_raw_tty,
    _footer_shortcut_hit,
    _leave_raw_tty,
    _parse_mouse_event,
    _prompt_bar,
    _read_key,
    _run_interactive_source,
    _show_overlay,
    _vis_len,
    highlight_saylang_line,
    load_bg_mode,
    save_bg_mode,
)

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_BRIGHT_WHITE = "\x1b[1;97m"
_GRAY = "\x1b[90m"
_GREEN = "\x1b[92m"
_RED = "\x1b[91m"
_CYAN = "\x1b[96m"
_YELLOW = "\x1b[93m"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


@dataclass(frozen=True)
class LessonTest:
    """Automated verification case for a SayLang interactive lesson."""

    description: str
    cli_args: tuple[str, ...] = ()
    input_lines: tuple[str, ...] | None = None
    expect_contains: tuple[str, ...] = ()
    expect_not_contains: tuple[str, ...] = ()
    expect_exact: str | None = None
    expect_ansi: bool = False
    use_temp_dir: bool = False


@dataclass(frozen=True)
class Lesson:
    """Single interactive SayLang lesson in `saylang learn`."""

    number: int
    id: str
    track: str
    title: str
    goal: str
    explanation: str
    example: str
    challenge: str
    starter: str
    solution: str
    hints: tuple[str, ...]
    tests: tuple[LessonTest, ...]


@dataclass(frozen=True)
class TestResult:
    """Outcome of running one LessonTest."""

    description: str
    passed: bool
    detail: str = ""


LESSONS: tuple[Lesson, ...] = (
    Lesson(
        number=1,
        id="01-styled-cards",
        track="Basics",
        title="Boxes & Colour",
        goal="Put words inside a colourful box on screen",
        explanation=(
            "Save any word with `set hero to \"...\"` and drop it into any double-quoted text with `{hero}`.\n"
            "Use `|` (a pipe) to pass that message into `box` and `colour cyan bold`."
        ),
        example=(
            'set tool to "SayLang"\n'
            'say "Ready with {tool}" | box --title "Status" | colour green bold'
        ),
        challenge=(
            'Save `"SayLang"` in `hero`, then print `"Hello, {hero}!"`\n'
            'inside `| box --title "Greeting" | colour cyan bold`.'
        ),
        starter=(
            'set hero to "SayLang"\n'
            '# Change the line below to say "Hello, {hero}!" inside a cyan bold box titled "Greeting"\n'
            'say hero\n'
        ),
        solution=(
            'set hero to "SayLang"\n'
            'say "Hello, {hero}!" | box --title "Greeting" | colour cyan bold\n'
        ),
        hints=(
            'Use "{hero}" inside double quotes: say "Hello, {hero}!"',
            'Add | box --title "Greeting" | colour cyan bold to the end of the line.',
        ),
        tests=(
            LessonTest(
                description="Output contains Greeting box title and Hello, SayLang!",
                expect_contains=("Greeting", "Hello, SayLang!", "╭", "╰"),
                expect_ansi=True,
            ),
        ),
    ),
    Lesson(
        number=2,
        id="02-decisions-pipes",
        track="Basics",
        title="If & Otherwise",
        goal="Choose what to print based on a number",
        explanation=(
            "Make choices in plain English with `if score is at least 90` and `otherwise`.\n"
            "Indent the steps underneath by 4 spaces so SayLang knows they belong inside."
        ),
        example=(
            "if level is at least 10\n"
            '    say "pro" | upper | box colour green\n'
            "otherwise\n"
            '    say "starter" | upper | box colour yellow'
        ),
        challenge=(
            "Read `--score` (or use `80` as the backup), convert it to a number,\n"
            "then print `\"grade: a\"` (90+), `\"grade: b\"` (75+), or `\"grade: c\"`\n"
            "in uppercase inside a box (`| upper | box`)."
        ),
        starter=(
            "flags: --score\n"
            "set score to number of (flag --score or 80)\n"
            "# Check score and print GRADE: A, GRADE: B, or GRADE: C in a box\n"
        ),
        solution=(
            "flags: --score\n"
            "set score to number of (flag --score or 80)\n"
            "if score is at least 90\n"
            '    say "grade: a" | upper | box colour green\n'
            "otherwise if score is at least 75\n"
            '    say "grade: b" | upper | box colour cyan\n'
            "otherwise\n"
            '    say "grade: c" | upper | box colour yellow\n'
        ),
        hints=(
            "Start with: if score is at least 90",
            'Inside each branch write: say "grade: ..." | upper | box',
        ),
        tests=(
            LessonTest(
                description="Default score (80) outputs GRADE: B in a box",
                expect_contains=("GRADE: B", "╭"),
            ),
            LessonTest(
                description="--score 95 outputs GRADE: A",
                cli_args=("--score", "95"),
                expect_contains=("GRADE: A",),
            ),
            LessonTest(
                description="--score 50 outputs GRADE: C",
                cli_args=("--score", "50"),
                expect_contains=("GRADE: C",),
            ),
        ),
    ),
    Lesson(
        number=3,
        id="03-cli-flags",
        track="CLI Tools",
        title="Command Options (-u, --name)",
        goal="Let users customize your tool from the terminal",
        explanation=(
            "`flags: -u, --name` lets your script accept options like `--name Ada -u`.\n"
            "Use `flag --name or \"friend\"` to grab the text (with a fallback if omitted),\n"
            "and `if flag -u` to check if an option was turned on."
        ),
        example=(
            "flags: -v, --user\n"
            'set who to flag --user or "guest"\n'
            'if flag -v then say "Hi, {who}!"'
        ),
        challenge=(
            "Declare `flags: -u, --name`. Use `\"friend\"` when `--name` is missing.\n"
            'Build `"Hello, {person}!"`, make it ALL CAPS when `-u` is passed,\n'
            "and print it inside `| box`."
        ),
        starter=(
            "flags: -u, --name\n"
            'set person to flag --name or "friend"\n'
            'set msg to "Hello, {person}!"\n'
            "# Uppercase msg when flag -u is passed, then print msg | box\n"
        ),
        solution=(
            "flags: -u, --name\n"
            'set person to flag --name or "friend"\n'
            'set msg to "Hello, {person}!"\n'
            "if flag -u\n"
            "    set msg to msg | upper\n"
            "say msg | box\n"
        ),
        hints=(
            "Add: if flag -u  ->  set msg to msg | upper",
            "Print at the end: say msg | box",
        ),
        tests=(
            LessonTest(
                description="No flags greets friend",
                expect_contains=("Hello, friend!", "╭"),
            ),
            LessonTest(
                description="--name Ada greets Ada",
                cli_args=("--name", "Ada"),
                expect_contains=("Hello, Ada!",),
            ),
            LessonTest(
                description="--name Ada -u outputs HELLO, ADA!",
                cli_args=("--name", "Ada", "-u"),
                expect_contains=("HELLO, ADA!",),
            ),
        ),
    ),
    Lesson(
        number=4,
        id="04-functions-pipes",
        track="Shortcuts",
        title="Make Your Own Shortcut",
        goal="Create a reusable action and use it after |",
        explanation=(
            "Save steps you repeat into your own command with `to <name> with <word>`\n"
            "and send back the finished result using `give back`.\n"
            "Once made, you can use it anywhere after `|`, just like `| upper`!"
        ),
        example=(
            "to shout with words\n"
            '    give back "{words | upper}!!!"\n\n'
            'say "ship it" | shout'
        ),
        challenge=(
            "Make your own shortcut `to card with title` that gives back\n"
            '`title | upper | box --width 20`.\n'
            'Then print `"build passing" | card`.'
        ),
        starter=(
            "# Make a shortcut named `card` taking `title`, then print \"build passing\" | card\n"
            'say "build passing"\n'
        ),
        solution=(
            "to card with title\n"
            "    give back title | upper | box --width 20\n\n"
            'say "build passing" | card\n'
        ),
        hints=(
            "Write: to card with title",
            "Indented 4 spaces inside: give back title | upper | box --width 20",
        ),
        tests=(
            LessonTest(
                description="Prints BUILD PASSING inside a 20+ wide box",
                expect_contains=("BUILD PASSING", "╭──────────────────────╮"),
            ),
        ),
    ),
    Lesson(
        number=5,
        id="05-lists-maps-tables",
        track="Tables & Data",
        title="Lists & Tables",
        goal="Organize items into a neat terminal table",
        explanation=(
            "Group named details into a card with `a map with task as \"...\", status as \"...\"`.\n"
            "Put cards together with `a list of ...` and send them into `| table`\n"
            "to draw neat rows and columns automatically!"
        ),
        example=(
            'set row1 to a map with name as "API", state as "up"\n'
            'set row2 to a map with name as "DB", state as "up"\n'
            "say a list of row1, and row2 | table"
        ),
        challenge=(
            "Make two task cards (`t1` and `t2`) with `task` and `status`:\n"
            '`"Learn SayLang"` / `"done"` and `"Ship CLI"` / `"next"`.\n'
            "Put both in a list and print them through `| table`."
        ),
        starter=(
            'set t1 to a map with task as "Learn SayLang", status as "done"\n'
            "# Make t2, put both in a list, and print with | table\n"
        ),
        solution=(
            'set t1 to a map with task as "Learn SayLang", status as "done"\n'
            'set t2 to a map with task as "Ship CLI", status as "next"\n'
            "set tasks to a list of t1, and t2\n"
            "say tasks | table\n"
        ),
        hints=(
            'Make t2: set t2 to a map with task as "Ship CLI", status as "next"',
            "Print: say a list of t1, and t2 | table",
        ),
        tests=(
            LessonTest(
                description="Renders table headers and both task rows",
                expect_contains=("task", "status", "Learn SayLang", "done", "Ship CLI", "next", "┬"),
            ),
        ),
    ),
    Lesson(
        number=6,
        id="06-progress-tui",
        track="TUI Apps",
        title="Progress Bars",
        goal="Show live progress gauges in the terminal",
        explanation=(
            "Draw a ready-made progress meter with `bar done of total --width 10 --label \"...\"`.\n"
            "Pipe it into `| box --title \"...\"` for a clean status card."
        ),
        example=(
            'say bar 3 of 4 --width 16 --label "Build" | box --title "CI"'
        ),
        challenge=(
            "Read `--done` (default `3`) and `--total` (default `5`), turn them\n"
            'into numbers, and print `bar done of total --width 10 --label "Done"`\n'
            'inside `| box --title "Progress"`.'
        ),
        starter=(
            "flags: --done, --total\n"
            "set done_n to number of (flag --done or 3)\n"
            "set total_n to number of (flag --total or 5)\n"
            "# Print bar done_n of total_n --width 10 --label \"Done\" | box --title \"Progress\"\n"
        ),
        solution=(
            "flags: --done, --total\n"
            "set done_n to number of (flag --done or 3)\n"
            "set total_n to number of (flag --total or 5)\n"
            'say bar done_n of total_n --width 10 --label "Done" | box --title "Progress"\n'
        ),
        hints=(
            'Write: bar done_n of total_n --width 10 --label "Done"',
            'Add | box --title "Progress" on the same line.',
        ),
        tests=(
            LessonTest(
                description="Default 3 of 5 shows 60% inside Progress box",
                expect_contains=("Progress", "Done", "60%", "██████░░░░"),
            ),
            LessonTest(
                description="--done 4 --total 4 shows 100%",
                cli_args=("--done", "4", "--total", "4"),
                expect_contains=("100%", "██████████"),
            ),
        ),
    ),
    Lesson(
        number=7,
        id="07-interactive-menus",
        track="TUI Apps",
        title="Menus You Can Pick",
        goal="Ask a question and show an arrow/mouse menu",
        explanation=(
            "`ask` lets someone type an answer, and `choose \"Pick:\" from <list>` pops up\n"
            "a menu they can move through with arrow keys or mouse wheel."
        ),
        example=(
            'set target to choose "Target:" from a list of "dev", "prod"\n'
            'say "Going to {target}" | box'
        ),
        challenge=(
            'Ask `"Project name? "` and save it in `project`.\n'
            'Then let the user pick `mode` using `choose "Mode:" from a list of "cli", "tui", and "daemon"`.\n'
            'Print `"{project} -> {mode}" | box`.'
        ),
        starter=(
            'set project to ask "Project name? "\n'
            "# Pick mode from cli, tui, daemon and print \"{project} -> {mode}\" | box\n"
        ),
        solution=(
            'set project to ask "Project name? "\n'
            'set mode to choose "Mode:" from a list of "cli", "tui", and "daemon"\n'
            'say "{project} -> {mode}" | box\n'
        ),
        hints=(
            'Use: set mode to choose "Mode:" from a list of "cli", "tui", and "daemon"',
            'Then: say "{project} -> {mode}" | box',
        ),
        tests=(
            LessonTest(
                description="Selecting option 2 picks tui cleanly",
                input_lines=("pulse", "2"),
                expect_contains=("pulse -> tui", "╭"),
            ),
            LessonTest(
                description="Typing option name daemon selects daemon",
                input_lines=("watch", "daemon"),
                expect_contains=("watch -> daemon",),
            ),
        ),
    ),
    Lesson(
        number=8,
        id="08-files-json-errors",
        track="Files & Safety",
        title="Save, Load & Mistakes",
        goal="Save info to disk, load it back, and catch missing files",
        explanation=(
            "Save any card or list to a file with `save data to \"app.json\"`, and load it\n"
            "right back with `load \"app.json\"`. Read a saved field with `data's app`.\n"
            "When a file might be missing, wrap it in `try` / `if it fails with err` so your app never crashes."
        ),
        example=(
            'set cfg to a map with host as "localhost", port as 8080\n'
            'save cfg to "settings.json"\n'
            'set loaded to load "settings.json"\n'
            "say loaded's host"
        ),
        challenge=(
            'Save `cfg` (`app as "saylang"`, `port as 9000`) to `"app.json"` using `save`.\n'
            'If `file exists "app.json"`, `load "app.json"` into `data` and print `"Loaded: {data\'s app}:{data\'s port}"`.\n'
            'Then try reading `"missing.json"` inside `try / if it fails with err` and print `"Caught missing"`.'
        ),
        starter=(
            'set cfg to a map with app as "saylang", port as 9000\n'
            '# 1. Save cfg to "app.json"\n'
            '# 2. If file exists "app.json", load it into data and print "Loaded: {data\'s app}:{data\'s port}"\n'
            '# 3. Try reading "missing.json" and catch the error\n'
        ),
        solution=(
            'set cfg to a map with app as "saylang", port as 9000\n'
            'save cfg to "app.json"\n'
            'if file exists "app.json"\n'
            '    set data to load "app.json"\n'
            '    say "Loaded: {data\'s app}:{data\'s port}"\n'
            "try\n"
            '    set x to read "missing.json"\n'
            "if it fails with err\n"
            '    say "Caught missing"\n'
        ),
        hints=(
            'Save with: save cfg to "app.json"  and load with: set data to load "app.json"',
            'Handle missing files with: try / set x to read "missing.json" / if it fails with err / say "Caught missing"',
        ),
        tests=(
            LessonTest(
                description="Saves & loads JSON cleanly and catches missing file",
                expect_contains=("Loaded: saylang:9000", "Caught missing"),
                use_temp_dir=True,
            ),
        ),
    ),
    Lesson(
        number=9,
        id="09-tty-clock",
        track="TUI Apps",
        title="Live Centered Clock",
        goal="Put a live big-letter clock dead center on your screen",
        explanation=(
            "`pos center` puts your clock in the middle of the screen (you can also use\n"
            "`top-left`, `top-right`, `bottom`, or `10, 5`). Adding `--live` to `time`\n"
            "keeps it ticking smoothly every second without flicker!"
        ),
        example=(
            "import time, ascii\n"
            "flags: -d\n"
            "pos center\n"
            "print time --12h --live | ascii --size default colour cyan\n"
            "if flag -d then print date below time"
        ),
        challenge=(
            "Import `time, ascii`, set `pos center`, and print\n"
            "`time --12h --live | ascii --size small colour cyan`.\n"
            "When `flag -d` is passed, `print date below time`."
        ),
        starter=(
            "import time, ascii\n"
            "flags: -d\n"
            "# Center on screen and print a live small-ascii cyan clock (+ date below when -d)\n"
        ),
        solution=(
            "import time, ascii\n"
            "pos center\n"
            "print time --12h --live | ascii --size small colour cyan\n"
            "if flag -d then print date below time\n"
            "flags: -d\n"
        ),
        hints=(
            "Put `pos center` on its own line before printing time.",
            "Print: print time --12h --live | ascii --size small colour cyan",
        ),
        tests=(
            LessonTest(
                description="Default run draws centered block-letter clock",
                expect_contains=("█",),
                expect_ansi=True,
            ),
            LessonTest(
                description="-d flag adds today's date centered under the clock",
                cli_args=("-d",),
                expect_contains=("█", "20"),
            ),
        ),
    ),
    Lesson(
        number=10,
        id="10-cli-calculator",
        track="Calculators",
        title="CLI Calculator",
        goal="Build an interactive terminal calculator in plain English",
        explanation=(
            "Ask for two numbers and an operation (`+`, `-`, `*`, `/`), check division\n"
            "by zero with an `if`, and print the finished answer inside a box."
        ),
        example=(
            'set a to number of (ask "First number: ")\n'
            'set b to number of (ask "Second number: ")\n'
            'say "{a} + {b} = {a + b}" | box'
        ),
        challenge=(
            'Ask `"First number: "` into `a` (`number of`), `"Operation (+, -, *, /): "` into `op`,\n'
            'and `"Second number: "` into `b` (`number of`).\n'
            'Compute `ans` for `+`, `-`, `*`, `/` (if dividing by `0`, print `"Cannot divide by zero."` in red);\n'
            'otherwise print `"{a} {op} {b} = {ans}" | box --title "Calculator"`.'
        ),
        starter=(
            'set a to number of (ask "First number: ")\n'
            'set op to trimmed of (ask "Operation (+, -, *, /): ")\n'
            'set b to number of (ask "Second number: ")\n'
            "# Calculate ans and print \"{a} {op} {b} = {ans}\" | box --title \"Calculator\"\n"
        ),
        solution=(
            'set a to number of (ask "First number: ")\n'
            'set op to trimmed of (ask "Operation (+, -, *, /): ")\n'
            'set b to number of (ask "Second number: ")\n'
            'if op is "+" or op is "plus"\n'
            "    set ans to a + b\n"
            '    say "{a} + {b} = {ans}" | box --title "Calculator"\n'
            'otherwise if op is "-" or op is "minus"\n'
            "    set ans to a - b\n"
            '    say "{a} - {b} = {ans}" | box --title "Calculator"\n'
            'otherwise if op is "*" or op is "times"\n'
            "    set ans to a * b\n"
            '    say "{a} * {b} = {ans}" | box --title "Calculator"\n'
            'otherwise if op is "/"\n'
            "    if b is 0\n"
            '        say "Cannot divide by zero." colour red\n'
            "    otherwise\n"
            "        set ans to a / b\n"
            '        say "{a} / {b} = {ans}" | box --title "Calculator"\n'
            "otherwise\n"
            '    say "Unknown operation: {op}" colour red\n'
        ),
        hints=(
            'Handle each op cleanly: if op is "+"  ->  set ans to a + b',
            'When op is "/", check `if b is 0` before computing `a / b`.',
        ),
        tests=(
            LessonTest(
                description="Adds 12 + 8 to 20 inside Calculator box",
                input_lines=("12", "+", "8"),
                expect_contains=("Calculator", "12 + 8 = 20"),
            ),
            LessonTest(
                description="Multiplies 6 * 7 to 42",
                input_lines=("6", "*", "7"),
                expect_contains=("6 * 7 = 42",),
            ),
            LessonTest(
                description="Guards divide by zero safely",
                input_lines=("9", "/", "0"),
                expect_contains=("Cannot divide by zero.",),
            ),
        ),
    ),
    Lesson(
        number=11,
        id="11-mouse-tui-calc",
        track="Calculators",
        title="Mouse TUI Calculator",
        goal="Build a clickable button calculator with mouse support",
        explanation=(
            "`buttons \"Calc: {screen}\" from keys --cols 4` draws a clickable 4-column button grid\n"
            "in the middle of your terminal! Use `calc screen` to safely solve the typed math\n"
            "(and `try / if it fails` to show `\"Error\"` if someone divides by zero)."
        ),
        example=(
            'set keys to a list of "1", "2", "+", "=", "Q"\n'
            'set pick to buttons "Tap a key:" from keys --cols 3\n'
            'say "You clicked {pick}"'
        ),
        challenge=(
            'The clickable loop is ready — press Ctrl+R to try clicking buttons right now!\n'
            'Next, add an `otherwise if btn is "="` branch that sets `screen` to `"{calc screen}"`\n'
            'inside `try / if it fails with err` (showing `"Error"` if someone divides by zero).'
        ),
        starter=(
            'set keys to a list of "7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "C", "0", "=", "+", "Q"\n'
            'set screen to ""\n'
            "while true\n"
            '    set btn to buttons "Calc: {screen}" from keys --cols 4\n'
            '    if btn is "" or btn is "Q"\n'
            "        stop\n"
            '    if btn is "C"\n'
            '        set screen to ""\n'
            "    otherwise\n"
            '        # Add an `otherwise if btn is "="` branch using `try` + `set screen to "{calc screen}"`\n'
            '        set screen to "{screen}{btn}"\n'
            'say "Result: {screen}" | box --title "Calculator"\n'
        ),
        solution=(
            'set keys to a list of "7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "C", "0", "=", "+", "Q"\n'
            'set screen to ""\n'
            "while true\n"
            '    set btn to buttons "Calc: {screen}" from keys --cols 4\n'
            '    if btn is "" or btn is "Q"\n'
            "        stop\n"
            '    if btn is "C"\n'
            '        set screen to ""\n'
            '    otherwise if btn is "="\n'
            "        try\n"
            '            set screen to "{calc screen}"\n'
            "        if it fails with err\n"
            '            set screen to "Error"\n'
            "    otherwise\n"
            '        set screen to "{screen}{btn}"\n'
            'say "Result: {screen}" | box --title "Calculator"\n'
        ),
        hints=(
            'Ask for clicks inside the loop: set btn to buttons "Calc: {screen}" from keys --cols 4',
            'Solve on "=" with: try -> set screen to "{calc screen}" -> if it fails with err -> set screen to "Error"',
        ),
        tests=(
            LessonTest(
                description="Clicking 7, +, 5, =, Q computes 12",
                input_lines=("7", "+", "5", "=", "Q"),
                expect_contains=("Result: 12", "Calculator"),
            ),
            LessonTest(
                description="Clicking 1, /, 0, =, Q catches zero division as Error",
                input_lines=("1", "/", "0", "=", "Q"),
                expect_contains=("Result: Error",),
            ),
        ),
    ),
    Lesson(
        number=12,
        id="12-capstone-cruncher",
        track="Final Project",
        title="Number Cruncher Tool",
        goal="Put loops, errors, tables & bars together in one app",
        explanation=(
            "Inspired by Kestral's final challenge! Let the user enter numbers one by one,\n"
            "skip bad entries safely with `try / if it fails`, and show the finished stats\n"
            "in a summary table and bar."
        ),
        example=(
            "set nums to a list of 10, 20, 30\n"
            "say nums | sum, nums | min, nums | max, nums | average"
        ),
        challenge=(
            "1. Declare `flags: --compact` and start `set nums to an empty list`.\n"
            '2. Loop with `while true`: ask `"Number (or done): "`; `stop` on `"done"` or `""`.\n'
            '3. Turn input into a number with `try` + `number of` and `add` to `nums`; on mistake print `"Skipping invalid: {raw}" colour red`.\n'
            '4. If `nums` is empty print `"No numbers entered."`.\n'
            "5. Otherwise find `total` (`| sum`), `low` (`| min`), `high` (`| max`), `avg` (`| average`),\n"
            '   make a table of `metric` / `value` cards piped to `| table | box --title "Number Cruncher"`,\n'
            '   and unless `flag --compact` is set, also print `bar length of nums of 10 --width 10 --label "Samples"`.'
        ),
        starter=(
            "flags: --compact\n"
            "set nums to an empty list\n"
            "while true\n"
            '    set raw to trimmed of (ask "Number (or done): ")\n'
            '    if raw is "done" or raw is ""\n'
            "        stop\n"
            "    try\n"
            "        set n to number of raw\n"
            "        add n to nums\n"
            "    if it fails with err\n"
            '        say "Skipping invalid: {raw}" colour red\n\n'
            "if length of nums is 0\n"
            '    say "No numbers entered."\n'
            "otherwise\n"
            "    # Build metric/value summary table inside Number Cruncher box + Samples bar\n"
        ),
        solution=(
            "flags: --compact\n"
            "set nums to an empty list\n"
            "while true\n"
            '    set raw to trimmed of (ask "Number (or done): ")\n'
            '    if raw is "done" or raw is ""\n'
            "        stop\n"
            "    try\n"
            "        set n to number of raw\n"
            "        add n to nums\n"
            "    if it fails with err\n"
            '        say "Skipping invalid: {raw}" colour red\n\n'
            "if length of nums is 0\n"
            '    say "No numbers entered."\n'
            "otherwise\n"
            "    set total to nums | sum\n"
            "    set low to nums | min\n"
            "    set high to nums | max\n"
            "    set avg to nums | average\n"
            '    set r1 to a map with metric as "count", value as length of nums\n'
            '    set r2 to a map with metric as "sum", value as total\n'
            '    set r3 to a map with metric as "min", value as low\n'
            '    set r4 to a map with metric as "max", value as high\n'
            '    set r5 to a map with metric as "avg", value as avg\n'
            "    set report to a list of r1, r2, r3, r4, and r5\n"
            '    say report | table | box --title "Number Cruncher" colour cyan\n'
            "    if not flag --compact\n"
            '        say bar length of nums of 10 --width 10 --label "Samples"\n'
        ),
        hints=(
            "Compute stats with: nums | sum, nums | min, nums | max, nums | average",
            'Put metric/value cards in a list and print: report | table | box --title "Number Cruncher"',
        ),
        tests=(
            LessonTest(
                description="Computes count, sum, min, max, avg and prints summary box + Samples bar",
                input_lines=("10", "20", "30", "done"),
                expect_contains=("Number Cruncher", "count", "60", "10", "30", "20", "Samples"),
            ),
            LessonTest(
                description="Skips invalid entries gracefully without crashing",
                input_lines=("10", "oops", "20", "done"),
                expect_contains=("Skipping invalid: oops", "30", "15"),
            ),
            LessonTest(
                description="--compact hides the Samples progress bar",
                cli_args=("--compact",),
                input_lines=("5", "15", "done"),
                expect_contains=("Number Cruncher", "20", "10"),
                expect_not_contains=("Samples",),
            ),
            LessonTest(
                description="Handles empty input cleanly",
                input_lines=("done",),
                expect_contains=("No numbers entered.",),
            ),
        ),
    ),
)


def progress_file_path() -> Path:
    """Return path to persisted `saylang learn` progress file."""
    override = os.environ.get("SAYLANG_HOME")
    base = Path(override) if override else (Path.home() / ".saylang")
    return base / "learn_progress.json"


def load_progress() -> dict[str, object]:
    """Load persisted course progress and code drafts."""
    path = progress_file_path()
    default: dict[str, object] = {"completed": [], "drafts": {}, "current": 1}
    if not path.is_file():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "completed": list(data.get("completed", [])),
                "drafts": dict(data.get("drafts", {})),
                "current": int(data.get("current", 1)),
            }
    except Exception:
        pass
    return default


def save_progress(data: dict[str, object]) -> None:
    """Persist course progress and drafts to disk."""
    path = progress_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def reset_progress() -> None:
    """Remove persisted course progress if present."""
    path = progress_file_path()
    if path.is_file():
        path.unlink()


def evaluate_lesson(lesson: Lesson, source: str) -> list[TestResult]:
    """Run all automated tests for a lesson against `source`."""
    results: list[TestResult] = []
    for case in lesson.tests:
        prev_cwd = os.getcwd()
        tmp_dir_ctx = tempfile.TemporaryDirectory() if case.use_temp_dir else None
        try:
            if tmp_dir_ctx is not None:
                os.chdir(tmp_dir_ctx.name)
            try:
                raw_out, _val = run_and_capture(
                    source,
                    input_lines=list(case.input_lines)
                    if case.input_lines is not None
                    else [],
                    cli_args=list(case.cli_args),
                )
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 0
                if code != 0:
                    results.append(
                        TestResult(
                            case.description,
                            False,
                            f"Program exited with non-zero status {code}",
                        )
                    )
                    continue
                raw_out = ""
            except SayError as err:
                results.append(TestResult(case.description, False, err.message))
                continue

            clean_out = _ANSI_RE.sub("", raw_out)
            if case.expect_exact is not None and clean_out.strip() != case.expect_exact.strip():
                results.append(
                    TestResult(
                        case.description,
                        False,
                        f"Expected exact output {case.expect_exact!r}, got {clean_out!r}",
                    )
                )
                continue

            missing = [needle for needle in case.expect_contains if needle not in clean_out]
            if missing:
                results.append(
                    TestResult(
                        case.description,
                        False,
                        f"Missing {missing[0]!r} in output",
                    )
                )
                continue

            forbidden = [needle for needle in case.expect_not_contains if needle in clean_out]
            if forbidden:
                results.append(
                    TestResult(
                        case.description,
                        False,
                        f"Unexpected {forbidden[0]!r} in output",
                    )
                )
                continue

            if case.expect_ansi and "\x1b[" not in raw_out:
                results.append(
                    TestResult(
                        case.description,
                        False,
                        "Expected ANSI colour/style output",
                    )
                )
                continue

            results.append(TestResult(case.description, True, "PASS"))
        finally:
            os.chdir(prev_cwd)
            if tmp_dir_ctx is not None:
                tmp_dir_ctx.cleanup()
    return results


def _wrap_text(text: str, width: int) -> list[str]:
    width = max(width, 16)
    lines: list[str] = []
    for para in text.splitlines():
        if not para.strip():
            lines.append("")
            continue
        words = para.split(" ")
        cur = ""
        for w in words:
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= width:
                cur += " " + w
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    return lines


def format_curriculum_list(completed: set[str] | None = None) -> str:
    """Format a plain-text summary of all SayLang interactive lessons."""
    done = completed or set()
    pct = int(round((len(done) / len(LESSONS)) * 100)) if LESSONS else 0
    lines = [
        f"SayLang Interactive Course ({len(done)}/{len(LESSONS)} completed — {pct}%)",
        runtime.say_bar(len(done), len(LESSONS), width=24, label="Progress"),
        "",
    ]
    for lesson in LESSONS:
        mark = "✓" if lesson.id in done else " "
        lines.append(
            f"  [{mark}] {lesson.number:>2}. [{lesson.track:<13}] {lesson.title} — {lesson.goal}"
        )
    lines.append("")
    lines.append("Run `saylang learn` (or `saylang learn <n>`) to start in your terminal.")
    return "\n".join(lines)


def render_lesson_map(
    selected: int,
    completed: set[str],
    rows: int,
    cols: int,
    bg_mode: str = "mica",
) -> str:
    """Render adaptive minimal freeCodeCamp-style curriculum map (Mica or Black)."""
    rows = max(rows, 10)
    cols = max(cols, 36)
    sel = max(0, min(selected, len(LESSONS) - 1))

    done_count = len(completed)
    bar = runtime.say_bar(done_count, len(LESSONS), width=20)
    bg_tag = "mica" if bg_mode == "mica" else "black"
    right_hdr = f"{done_count}/{len(LESSONS)} complete · {bg_tag} "
    gap_top = max(cols - 16 - len(right_hdr), 1)
    header_bar = f" {_BOLD}SAYLANG LEARN{_RESET}{' ' * gap_top}{_GRAY}{right_hdr}{_RESET}"
    hairline = f"{_GRAY}{'─' * cols}{_RESET}"
    footer_bar = f" {_DIM}↑/↓ Lesson   Enter Start   1-9 Jump   t Surface   r Reset   Esc/q Quit{_RESET}"

    panel_w = min(cols - 4, 88) if cols >= 60 else cols - 2
    margin = " " * max((cols - panel_w) // 2, 1)

    lines: list[str] = [header_bar, hairline]
    if rows >= 17:
        lines.append("")
        lines.append(f"{margin}{_BOLD}SayLang Interactive Course{_RESET}  {_GRAY}{bar}{_RESET}")
        lines.append(f"{margin}{_GRAY}Learn by building real terminal apps in plain English{_RESET}")
        lines.append("")
    else:
        lines.append(f"{margin}{_BOLD}Curriculum{_RESET} {_GRAY}{bar}{_RESET}")

    list_cap = max(rows - 2 - len(lines), 2)
    scroll = max(0, sel - list_cap + 1)
    for idx in range(scroll, min(len(LESSONS), scroll + list_cap)):
        lesson = LESSONS[idx]
        mark = f"{_GREEN}✓{_RESET}" if lesson.id in completed else f"{_GRAY}○{_RESET}"
        badge = f"[{lesson.track}]"
        goal_w = max(panel_w - 50, 8)
        if idx == sel:
            if panel_w >= 62:
                lines.append(
                    f"{margin}{_BRIGHT_WHITE}▌ {mark} {lesson.number:>2}. {_CYAN}{badge:<15}{_RESET} {_BRIGHT_WHITE}{lesson.title[:25]:<25}{_RESET} \x1b[37m{lesson.goal[:goal_w]}{_RESET}"
                )
            else:
                lines.append(
                    f"{margin}{_BRIGHT_WHITE}▌ {mark} {lesson.number:>2}. {lesson.title}{_RESET}"
                )
        else:
            if panel_w >= 62:
                lines.append(
                    f"{margin}  {mark} {_GRAY}{lesson.number:>2}.{_RESET} {_CYAN}{badge:<15}{_RESET} \x1b[37m{lesson.title[:25]:<25}{_RESET} {_GRAY}{lesson.goal[:goal_w]}{_RESET}"
                )
            else:
                lines.append(f"{margin}  {mark} {_GRAY}{lesson.number:>2}.{_RESET} \x1b[37m{lesson.title}{_RESET}")

    body_target = rows - 2
    while len(lines) < body_target:
        lines.append("")
    lines = lines[:body_target]
    lines.extend([hairline, footer_bar])
    return _compose_screen(lines, rows, cols, bg_mode=bg_mode)


def render_learn_workspace(
    lesson: Lesson,
    buf: NanaBuffer,
    test_results: list[TestResult],
    hint_idx: int,
    completed: set[str],
    rows: int,
    cols: int,
    bg_mode: str = "mica",
) -> str:
    """Render adaptive split-pane freeCodeCamp workspace with hairline chrome."""
    rows = max(rows, 10)
    cols = max(cols, 36)
    body_rows = rows - 4

    status_done = " ✓" if lesson.id in completed else ""
    right_hdr = f"Ln {buf.row + 1}, Col {buf.col + 1} · v{__version__} "
    max_left = max(cols - len(right_hdr) - 4, 10)
    left_plain = f" LEARN {lesson.number}/{len(LESSONS)} · {lesson.title}{status_done}"[:max_left]
    gap = max(cols - len(left_plain) - len(right_hdr), 1)
    top_bar = f" {_BOLD}LEARN {lesson.number}/{len(LESSONS)}{_RESET} {_GRAY}· {lesson.title[:max(max_left - 12, 8)]}{status_done}{_RESET}{' ' * gap}{_GRAY}{right_hdr}{_RESET}"
    hairline = f"{_GRAY}{'─' * cols}{_RESET}"

    ok_syn, syn_msg = buf.check_syntax()
    syn_badge = f"{_GREEN}✓ {syn_msg}{_RESET}" if ok_syn else f"{_RED}✗ {syn_msg}{_RESET}"
    extra = f"  │  {buf.status}" if buf.status else ""
    status_line = f" {syn_badge}{extra}"

    footer_txt = " ^T Tests  ^R Run  ^H Hint  ^B Brief  ^L Map  ^E Reset  ^X Exit "
    footer_bar = f"{_DIM}{footer_txt[:cols]}{_RESET}"

    if cols >= 92:
        left_w = max(36, min(52, cols * 42 // 100))
        right_start = left_w + 1
        ed_total_w = max(cols - right_start, 24)
        gutter_w = max(len(str(len(buf.lines))) + 3, 6)
        code_w = max(ed_total_w - gutter_w, 12)
        num_w = gutter_w - 3

        if buf.row < buf.scroll_y:
            buf.scroll_y = buf.row
        elif buf.row >= buf.scroll_y + body_rows:
            buf.scroll_y = buf.row - body_rows + 1
        if buf.col < buf.scroll_x:
            buf.scroll_x = buf.col
        elif buf.col >= buf.scroll_x + code_w:
            buf.scroll_x = buf.col - code_w + 1

        inner_left = left_w - 2
        left_lines: list[str] = [
            f" {_BOLD}{_CYAN}[{lesson.track}] {lesson.title}{_RESET}",
            f" {_GRAY}{'─' * min(inner_left, 46)}{_RESET}",
        ]
        for ln in _wrap_text(lesson.explanation, inner_left):
            left_lines.append(f" {ln}")
        left_lines.append("")
        left_lines.append(f" {_BOLD}Challenge:{_RESET}")
        for ln in _wrap_text(lesson.challenge, inner_left):
            left_lines.append(f" {_YELLOW}{ln}{_RESET}")
        left_lines.append("")
        left_lines.append(f" {_BOLD}Example:{_RESET}")
        for ex_ln in lesson.example.splitlines():
            left_lines.append(" " + highlight_saylang_line(ex_ln[:inner_left]))
        left_lines.append("")
        if hint_idx > 0 and lesson.hints:
            left_lines.append(f" {_BOLD}Hint:{_RESET}")
            shown_hint = lesson.hints[min(hint_idx - 1, len(lesson.hints) - 1)]
            for hln in _wrap_text(shown_hint, inner_left):
                left_lines.append(f" {_CYAN}{hln}{_RESET}")
            left_lines.append("")
        left_lines.append(f" {_BOLD}Tests (^T):{_RESET}")
        for idx, t in enumerate(lesson.tests):
            if idx < len(test_results):
                res = test_results[idx]
                icon = f"{_GREEN}✓{_RESET}" if res.passed else f"{_RED}✗{_RESET}"
                left_lines.append(f" {icon} {t.description[: max(inner_left - 2, 8)]}")
                if not res.passed and res.detail:
                    left_lines.append(f"   {_RED}{res.detail[: max(inner_left - 3, 8)]}{_RESET}")
            else:
                left_lines.append(f" {_GRAY}○{_RESET} {t.description[: max(inner_left - 2, 8)]}")

        screen: list[str] = [top_bar, hairline]
        for r in range(body_rows):
            l_txt = _clip_ansi(left_lines[r], left_w) if r < len(left_lines) else ""
            l_pad = " " * max(left_w - _vis_len(l_txt), 0)
            line_idx = buf.scroll_y + r
            if line_idx < len(buf.lines):
                raw_code = buf.lines[line_idx][buf.scroll_x : buf.scroll_x + code_w]
                hl = highlight_saylang_line(raw_code)
                lineno = f"{line_idx + 1:>{num_w}}"
                r_txt = f"{_GRAY}{lineno} │ {_RESET}{hl}"
            else:
                r_txt = f"{_GRAY}{'~':>{num_w}} │ {_RESET}"
            screen.append(f"{l_txt}{l_pad}{_GRAY}│{_RESET}{r_txt}")

        screen.append(status_line)
        screen.append(footer_bar)
        cur_r = (buf.row - buf.scroll_y) + 3
        cur_c = left_w + 1 + gutter_w + (buf.col - buf.scroll_x) + 1
        return _compose_screen(screen, rows, cols, cursor=(cur_r, cur_c), bg_mode=bg_mode)

    gutter_w = max(len(str(len(buf.lines))) + 3, 6)
    code_w = max(cols - gutter_w, 10)
    ed_rows = max(body_rows - 2, 3)
    if buf.row < buf.scroll_y:
        buf.scroll_y = buf.row
    elif buf.row >= buf.scroll_y + ed_rows:
        buf.scroll_y = buf.row - ed_rows + 1
    if buf.col < buf.scroll_x:
        buf.scroll_x = buf.col
    elif buf.col >= buf.scroll_x + code_w:
        buf.scroll_x = buf.col - code_w + 1

    passed_n = sum(1 for r in test_results if r.passed)
    goal_bar = f" Goal: {lesson.goal[:max(cols - 26, 10)]}  [{passed_n}/{len(lesson.tests)}]"
    screen_n: list[str] = [
        top_bar,
        hairline,
        f" {_CYAN}{goal_bar[:max(cols - 2, 8)]}{_RESET}",
        f" {_GRAY}{'─' * min(max(cols - 2, 6), 50)}{_RESET}",
    ]
    num_w = gutter_w - 3
    for r in range(ed_rows):
        line_idx = buf.scroll_y + r
        if line_idx < len(buf.lines):
            raw_code = buf.lines[line_idx][buf.scroll_x : buf.scroll_x + code_w]
            hl = highlight_saylang_line(raw_code)
            lineno = f"{line_idx + 1:>{num_w}}"
            screen_n.append(f"{_GRAY}{lineno} │ {_RESET}{hl}")
        else:
            screen_n.append(f"{_GRAY}{'~':>{num_w}} │ {_RESET}")

    screen_n.append(status_line)
    screen_n.append(footer_bar)
    cur_r = (buf.row - buf.scroll_y) + 5
    cur_c = gutter_w + (buf.col - buf.scroll_x) + 1
    return _compose_screen(screen_n, rows, cols, cursor=(cur_r, cur_c), bg_mode=bg_mode)


def _format_brief_overlay(lesson: Lesson, results: list[TestResult], hint_idx: int) -> str:
    parts = [
        f"[{lesson.track}] Lesson {lesson.number}: {lesson.title}",
        "",
        lesson.explanation,
        "",
        "Challenge:",
        lesson.challenge,
        "",
        "Example:",
        lesson.example,
        "",
        "Tests:",
    ]
    for idx, t in enumerate(lesson.tests):
        if idx < len(results):
            mark = "PASS" if results[idx].passed else f"FAIL ({results[idx].detail})"
            parts.append(f"  [{'x' if results[idx].passed else ' '}] {t.description} -> {mark}")
        else:
            parts.append(f"  [ ] {t.description}")
    if hint_idx > 0 and lesson.hints:
        parts.extend(["", "Hints:"])
        for h in lesson.hints[:hint_idx]:
            parts.append(f"  * {h}")
    return "\n".join(parts)


def _run_lesson_preview(
    lesson: Lesson,
    code: str,
    *,
    bg_mode: str = "mica",
    tty_state: list[object] | None = None,
) -> None:
    """Run current lesson code interactively in the terminal (or capture offline)."""
    sample = lesson.tests[0] if lesson.tests else None
    cli_args = list(sample.cli_args) if sample else []
    tmp_ctx = tempfile.TemporaryDirectory() if (sample and sample.use_temp_dir) else None
    if tty_state is not None:
        try:
            _run_interactive_source(
                code,
                title=lesson.title,
                filename=f"{lesson.id}.pl",
                cli_args=cli_args,
                tty_state=tty_state,
                cwd=tmp_ctx.name if tmp_ctx is not None else None,
            )
        finally:
            if tmp_ctx is not None:
                tmp_ctx.cleanup()
        return

    inputs = (
        list(sample.input_lines)
        if sample and sample.input_lines is not None
        else []
    )
    prev_cwd = os.getcwd()
    try:
        if tmp_ctx is not None:
            os.chdir(tmp_ctx.name)
        try:
            out, _ = run_and_capture(code, input_lines=inputs, cli_args=cli_args)
            body = out or "(finished with no output)"
        except SystemExit as exc:
            body = f"(exited with code {exc.code})"
        except SayError as err:
            body = err.format_pretty(f"{lesson.id}.pl")
    finally:
        os.chdir(prev_cwd)
        if tmp_ctx is not None:
            tmp_ctx.cleanup()
    _show_overlay(f"Run Output · {lesson.title}", body, bg_mode=bg_mode)


_LEGACY_STARTERS: dict[str, str] = {
    "11-mouse-tui-calc": (
        'set keys to a list of "7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "C", "0", "=", "+", "Q"\n'
        'set screen to ""\n'
        "# Loop clickable `buttons \"Calc: {screen}\" from keys --cols 4` until \"Q\" or \"\"\n"
        'say "Result: {screen}" | box --title "Calculator"'
    ),
}


def run_learn(
    lesson_num: int | None = None,
    *,
    list_only: bool = False,
    reset: bool = False,
    bg: str | None = None,
    _managed_tty: bool = False,
    _tty_state: list[object] | None = None,
) -> int:
    """Launch the freeCodeCamp-style `saylang learn` TUI course."""
    runtime.say_configure_utf8_stdio()
    if reset:
        reset_progress()
        if list_only:
            print("Course progress reset.")
            print(format_curriculum_list(set()))
            return 0

    progress = load_progress()
    completed: set[str] = {str(x) for x in progress.get("completed", [])}  # type: ignore[union-attr]
    drafts: dict[str, str] = {
        str(k): str(v) for k, v in dict(progress.get("drafts", {})).items()  # type: ignore[arg-type]
    }
    bg_state = [save_bg_mode(bg) if bg else load_bg_mode()]

    if list_only:
        print(format_curriculum_list(completed))
        return 0

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("saylang learn TUI requires an interactive terminal.", file=sys.stderr)
        print(format_curriculum_list(completed), file=sys.stderr)
        return 1

    runtime._enable_windows_ansi()
    tty_state = (
        _tty_state
        if _tty_state is not None
        else [None if _managed_tty else _enter_raw_tty()]
    )

    try:
        if not _managed_tty:
            sys.stdout.write("\x1b[?1049h\x1b[?1000h\x1b[?1006h")
            sys.stdout.flush()

        def save_state(cur_num: int, buf: NanaBuffer | None = None, lesson: Lesson | None = None) -> None:
            if buf is not None and lesson is not None:
                drafts[lesson.id] = buf.text
            save_progress(
                {
                    "completed": sorted(completed),
                    "drafts": drafts,
                    "current": cur_num,
                }
            )

        def pick_lesson_from_map(initial_sel: int) -> int | None:
            sel = max(0, min(initial_sel, len(LESSONS) - 1))
            while True:
                cols, rows = shutil.get_terminal_size((80, 24))
                rows_e = max(rows, 10)
                sys.stdout.write(
                    render_lesson_map(sel, completed, rows, cols, bg_mode=bg_state[0])
                )
                sys.stdout.flush()
                k = _read_key()
                if not k or k == "RESIZE":
                    continue
                mouse = _parse_mouse_event(k)
                if mouse is not None:
                    mkind, m_row, _m_col = mouse
                    if mkind == "WHEEL_UP":
                        sel = (sel - 1) % len(LESSONS)
                        continue
                    if mkind == "WHEEL_DOWN":
                        sel = (sel + 1) % len(LESSONS)
                        continue
                    first_row = 7 if rows_e >= 17 else 4
                    list_cap = max(rows_e - 2 - (first_row - 1), 2)
                    scroll = max(0, sel - list_cap + 1)
                    if 0 <= m_row - first_row < list_cap:
                        idx = scroll + (m_row - first_row)
                        if 0 <= idx < len(LESSONS):
                            return idx
                    continue
                if k == "t":
                    bg_state[0] = save_bg_mode("black" if bg_state[0] == "mica" else "mica")
                    continue
                if k == "UP":
                    sel = (sel - 1) % len(LESSONS)
                elif k == "DOWN":
                    sel = (sel + 1) % len(LESSONS)
                elif k in ("\r", "\n"):
                    return sel
                elif k.isdigit() and 1 <= int(k) <= len(LESSONS):
                    return int(k) - 1
                elif k == "r":
                    ans = _prompt_bar(
                        "Reset all course progress? (y/n): ", bg_mode=bg_state[0]
                    )
                    if ans and ans.lower().startswith("y"):
                        completed.clear()
                        drafts.clear()
                        reset_progress()
                elif k in ("ESC", "q", "\x18", "\x03"):
                    return None

        cur_idx: int | None
        if lesson_num is not None:
            if not (1 <= lesson_num <= len(LESSONS)):
                if not _managed_tty:
                    sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[?1049l\x1b[?25h\x1b[0m")
                    sys.stdout.flush()
                print(
                    f"Lesson {lesson_num} does not exist. Choose 1..{len(LESSONS)}.",
                    file=sys.stderr,
                )
                return 1
            cur_idx = lesson_num - 1
        else:
            default_idx = max(0, min(int(progress.get("current", 1)) - 1, len(LESSONS) - 1))  # type: ignore[arg-type]
            cur_idx = pick_lesson_from_map(default_idx)
            if cur_idx is None:
                return 0

        while cur_idx is not None:
            lesson = LESSONS[cur_idx]
            initial_text = drafts.get(lesson.id, lesson.starter)
            legacy_starter = _LEGACY_STARTERS.get(lesson.id)
            if legacy_starter is not None and initial_text.strip() == legacy_starter:
                initial_text = lesson.starter
            buf = NanaBuffer(
                lines=initial_text.rstrip("\n").split("\n") or [""],
                filepath=Path(f"{lesson.id}.pl"),
            )
            results: list[TestResult] = []
            hint_idx = 0

            while True:
                cols, rows = shutil.get_terminal_size((80, 24))
                rows_e = max(rows, 10)
                cols_e = max(cols, 36)
                sys.stdout.write(
                    render_learn_workspace(
                        lesson,
                        buf,
                        results,
                        hint_idx,
                        completed,
                        rows,
                        cols,
                        bg_mode=bg_state[0],
                    )
                )
                sys.stdout.flush()

                key = _read_key()
                if not key or key == "RESIZE":
                    continue
                buf.status = ""

                mouse = _parse_mouse_event(key)
                if mouse is not None:
                    mkind, m_row, m_col = mouse
                    body_rows = rows_e - 4
                    gutter_w = max(len(str(len(buf.lines))) + 3, 6)
                    if cols_e >= 92:
                        left_w = max(36, min(52, cols_e * 42 // 100))
                        code_start_row = 3
                        ed_rows = body_rows
                        code_start_col = left_w + 1 + gutter_w + 1
                        editor_min_col = left_w + 2
                    else:
                        code_start_row = 5
                        ed_rows = max(body_rows - 2, 3)
                        code_start_col = gutter_w + 1
                        editor_min_col = 1

                    if mkind == "WHEEL_UP":
                        if buf.scroll_y > 0:
                            buf.scroll_y = max(0, buf.scroll_y - 3)
                            if buf.row >= buf.scroll_y + ed_rows:
                                buf.row = buf.scroll_y + ed_rows - 1
                        else:
                            buf.row = max(0, buf.row - 3)
                        buf._clamp_col()
                        continue
                    if mkind == "WHEEL_DOWN":
                        max_sy = max(0, len(buf.lines) - ed_rows)
                        if buf.scroll_y < max_sy:
                            buf.scroll_y = min(max_sy, buf.scroll_y + 3)
                            if buf.row < buf.scroll_y:
                                buf.row = buf.scroll_y
                        else:
                            buf.row = min(len(buf.lines) - 1, buf.row + 3)
                        buf._clamp_col()
                        continue
                    if m_row == rows_e:
                        footer_txt = " ^T Tests  ^R Run  ^H Hint  ^B Brief  ^L Map  ^E Reset  ^X Exit "
                        mapped = _footer_shortcut_hit(
                            footer_txt[:cols_e],
                            m_col,
                            [
                                ("^T Tests", "\x14"),
                                ("^R Run", "\x12"),
                                ("^H Hint", "\x08"),
                                ("^B Brief", "\x02"),
                                ("^L Map", "\x0c"),
                                ("^E Reset", "\x05"),
                                ("^X Exit", "\x18"),
                            ],
                        )
                        if mapped is not None:
                            key = mapped
                        else:
                            continue
                    elif m_col >= editor_min_col and code_start_row <= m_row < code_start_row + ed_rows:
                        target_row = min(
                            max(0, buf.scroll_y + (m_row - code_start_row)),
                            len(buf.lines) - 1,
                        )
                        target_col = min(
                            max(0, buf.scroll_x + max(0, m_col - code_start_col)),
                            len(buf.lines[target_row]),
                        )
                        buf.row = target_row
                        buf.col = target_col
                        continue
                    else:
                        continue

                if key in ("\x18", "\x11", "\x03"):  # Ctrl+X / Ctrl+Q / Ctrl+C
                    save_state(lesson.number, buf, lesson)
                    return 0

                if key == "\x0c":  # Ctrl+L -> Curriculum map
                    save_state(lesson.number, buf, lesson)
                    picked = pick_lesson_from_map(cur_idx)
                    if picked is None:
                        return 0
                    cur_idx = picked
                    break

                if key == "\x0e":  # Ctrl+N -> Next lesson
                    save_state(lesson.number, buf, lesson)
                    if cur_idx + 1 < len(LESSONS):
                        cur_idx += 1
                    else:
                        _show_overlay(
                            "Course Complete!",
                            "You reached the end of SayLang Learn!\nPress Ctrl+L to review any lesson.",
                        )
                    break

                if key == "\x14":  # Ctrl+T -> Check Tests
                    results = evaluate_lesson(lesson, buf.text)
                    save_state(lesson.number, buf, lesson)
                    if all(r.passed for r in results):
                        completed.add(lesson.id)
                        save_state(lesson.number, buf, lesson)
                        summary = "\n".join(f"✓ {r.description}" for r in results)
                        if cur_idx + 1 < len(LESSONS):
                            _show_overlay(
                                f"PASS! Lesson {lesson.number} Complete",
                                summary
                                + f"\n\nPress any key to continue to Lesson {lesson.number + 1} "
                                "(or Ctrl+L in workspace for menu)...",
                            )
                            cur_idx += 1
                            break
                        else:
                            _show_overlay(
                                f"COURSE COMPLETE! All {len(LESSONS)} Lessons Passed!",
                                summary + "\n\nYou mastered CLI & TUI building in SayLang!",
                                bg_mode=bg_state[0],
                            )
                    else:
                        passed_n = sum(1 for r in results if r.passed)
                        buf.status = f"Tests: {passed_n}/{len(results)} passed"
                    continue

                if key == "\x12":  # Ctrl+R -> Run Live
                    _run_lesson_preview(
                        lesson, buf.text, bg_mode=bg_state[0], tty_state=tty_state
                    )
                    continue

                if key == "\x08":  # Ctrl+H -> Hint / Solution
                    if hint_idx < len(lesson.hints):
                        hint_idx += 1
                        buf.status = f"Hint {hint_idx}/{len(lesson.hints)} shown"
                    else:
                        _show_overlay(
                            f"Reference Solution · Lesson {lesson.number}",
                            lesson.solution,
                            bg_mode=bg_state[0],
                        )
                    continue

                if key == "\x02":  # Ctrl+B -> Brief overlay
                    _show_overlay(
                        f"Lesson {lesson.number} · {lesson.title}",
                        _format_brief_overlay(lesson, results, hint_idx),
                        bg_mode=bg_state[0],
                    )
                    continue

                if key == "\x05":  # Ctrl+E -> Reset starter
                    ans = _prompt_bar(
                        "Reset code to starter? (y/n): ", buf=buf, bg_mode=bg_state[0]
                    )
                    if ans and ans.lower().startswith("y"):
                        buf = NanaBuffer(
                            lines=lesson.starter.rstrip("\n").split("\n") or [""],
                            filepath=Path(f"{lesson.id}.pl"),
                        )
                        results = []
                        hint_idx = 0
                        drafts.pop(lesson.id, None)
                        save_state(lesson.number, buf, lesson)
                        buf.status = "Reset to starter"
                    continue

                if key == "\x13":  # Ctrl+S -> Save/export .pl file
                    fname = _prompt_bar(
                        "Save to .pl file: ", f"{lesson.id}.pl", buf=buf, bg_mode=bg_state[0]
                    )
                    if fname:
                        buf.save(Path(fname))
                        buf.filepath = Path(f"{lesson.id}.pl")
                    continue

                if key == "\x0b":
                    buf.cut_line()
                elif key == "\x15":
                    buf.paste_line()
                elif key == "UP":
                    buf.move_up()
                elif key == "DOWN":
                    buf.move_down()
                elif key == "LEFT":
                    buf.move_left()
                elif key == "RIGHT":
                    buf.move_right()
                elif key == "HOME":
                    buf.move_home()
                elif key == "END":
                    buf.move_end()
                elif key == "DELETE":
                    buf.delete()
                elif key == "\x7f":
                    buf.backspace()
                elif key in ("\r", "\n"):
                    buf.insert_newline()
                elif key == "\t":
                    buf.insert_tab()
                elif len(key) == 1 and key.isprintable():
                    buf.insert_char(key)

        return 0
    finally:
        if not _managed_tty:
            sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[?1049l\x1b[?25h\x1b[0m")
            sys.stdout.flush()
            _leave_raw_tty(tty_state[0])
