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
    _prompt_bar,
    _read_key,
    _show_overlay,
    _vis_len,
    highlight_saylang_line,
)

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"
_INV = "\x1b[7m"
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
        title="Styled Output & Boxes",
        goal="Print styled text inside a terminal box card",
        explanation=(
            "SayLang needs no parentheses or semicolons.\n"
            "You can pipe any message through `| box --title \"...\"` and\n"
            "colour/style output directly with `colour cyan bold`."
        ),
        example=(
            'set tool to "SayLang"\n'
            'say "Ready with " plus tool | box --title "Status" | colour green bold'
        ),
        challenge=(
            'Set `hero` to `"SayLang"` and print `"Hello, " plus hero plus "!"`\n'
            'piped through `| box --title "Greeting" | colour cyan bold`.'
        ),
        starter=(
            'set hero to "SayLang"\n'
            '# Pipe "Hello, " plus hero plus "!" into | box --title "Greeting" | colour cyan bold\n'
            'say hero\n'
        ),
        solution=(
            'set hero to "SayLang"\n'
            'say "Hello, " plus hero plus "!" | box --title "Greeting" | colour cyan bold\n'
        ),
        hints=(
            'Join text for a pipe with plus: "Hello, " plus hero plus "!"',
            'Add | box --title "Greeting" | colour cyan bold at the end.',
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
        title="Decisions & Pipelines",
        goal="Branch cleanly and transform text with pipes",
        explanation=(
            "Blocks use 4 spaces and natural comparisons like `is at least`.\n"
            "Combine branches with `| upper | box` to build clean CLI badges."
        ),
        example=(
            "if level is at least 10\n"
            '    say "pro" | upper | box colour green\n'
            "otherwise\n"
            '    say "starter" | upper | box colour yellow'
        ),
        challenge=(
            "Read `--score` with `flag --score` (default `80` when not set),\n"
            "convert with `number of`, then print `grade: a` (>= 90),\n"
            "`grade: b` (>= 75), or `grade: c` otherwise piped to `| upper | box`."
        ),
        starter=(
            "flags: --score\n"
            "set raw to flag --score\n"
            "if not raw\n"
            '    set raw to "80"\n'
            "set score to number of raw\n"
            "# Print GRADE: A, GRADE: B, or GRADE: C inside a box\n"
        ),
        solution=(
            "flags: --score\n"
            "set raw to flag --score\n"
            "if not raw\n"
            '    set raw to "80"\n'
            "set score to number of raw\n"
            "if score is at least 90\n"
            '    say "grade: a" | upper | box colour green\n'
            "otherwise if score is at least 75\n"
            '    say "grade: b" | upper | box colour cyan\n'
            "otherwise\n"
            '    say "grade: c" | upper | box colour yellow\n'
        ),
        hints=(
            "Use: if score is at least 90 / otherwise if score is at least 75 / otherwise",
            'Each branch prints say "grade: ..." | upper | box',
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
        title="CLI Flags & Options",
        goal="Build a real command-line tool with -u and --name",
        explanation=(
            "`flags:` declares accepted CLI flags for `--help` and readability.\n"
            "`flag --name` returns the argument value (or `false` if omitted),\n"
            "while `flag -u` returns `true` when `-u` is passed."
        ),
        example=(
            "flags: -v, --user\n"
            'set who to flag --user\n'
            'if flag -v then say "User: ", who'
        ),
        challenge=(
            "Declare `flags: -u, --name`. Default `person` to `\"friend\"`\n"
            'when `--name` is missing. Build `"Hello, " plus person plus "!"`,\n'
            "uppercase it if `flag -u` is set, and print it inside `| box`."
        ),
        starter=(
            "flags: -u, --name\n"
            "set person to flag --name\n"
            "if not person\n"
            '    set person to "friend"\n'
            "# Build msg, apply | upper when flag -u, then say msg | box\n"
        ),
        solution=(
            "flags: -u, --name\n"
            "set person to flag --name\n"
            "if not person\n"
            '    set person to "friend"\n'
            'set msg to "Hello, " plus person plus "!"\n'
            "if flag -u\n"
            "    set msg to msg | upper\n"
            "say msg | box\n"
        ),
        hints=(
            "Update msg inside `if flag -u`: set msg to msg | upper",
            "End with: say msg | box",
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
        track="Real Programs",
        title="Functions & Custom Pipes",
        goal="Write reusable functions and use them in `|` pipelines",
        explanation=(
            "Define functions with `to <name> with <param>` and `give back <val>`.\n"
            "Any function you define can also be used directly as a `|` pipe stage!"
        ),
        example=(
            "to shout with text\n"
            '    give back (text | upper) plus "!!!"\n'
            'say "ship it" | shout'
        ),
        challenge=(
            "Define `to card with title` that returns `title | upper | box --width 20`.\n"
            'Then print `"build passing" | card`.'
        ),
        starter=(
            "# Define `to card with title` returning title | upper | box --width 20\n"
            'say "build passing"\n'
        ),
        solution=(
            "to card with title\n"
            "    give back title | upper | box --width 20\n\n"
            'say "build passing" | card\n'
        ),
        hints=(
            "Inside `to card with title`: give back title | upper | box --width 20",
            'Call it via pipe: say "build passing" | card',
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
        track="Data & CLI",
        title="Lists, Maps & Tables",
        goal="Format structured records into clean terminal tables",
        explanation=(
            "Create records using `a map with key as value` and read fields\n"
            "with possessive syntax (`task's name`). Pipe a list of maps into\n"
            "`| table` to render a crisp Unicode CLI table immediately!"
        ),
        example=(
            'set row1 to a map with name as "API", state as "up"\n'
            'set row2 to a map with name as "DB", state as "up"\n'
            "say a list of row1, and row2 | table"
        ),
        challenge=(
            "Create two task maps with keys `task` and `status`: one with\n"
            '`"Learn SayLang"` / `"done"` and one with `"Ship CLI"` / `"next"`.\n'
            "Print the list piped through `| table`."
        ),
        starter=(
            'set t1 to a map with task as "Learn SayLang", status as "done"\n'
            "# Create t2 and print both as a table\n"
        ),
        solution=(
            'set t1 to a map with task as "Learn SayLang", status as "done"\n'
            'set t2 to a map with task as "Ship CLI", status as "next"\n'
            "set tasks to a list of t1, and t2\n"
            "say tasks | table\n"
        ),
        hints=(
            'Create t2: set t2 to a map with task as "Ship CLI", status as "next"',
            "Print with: say a list of t1, and t2 | table",
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
        track="TUI Building",
        title="Progress Bars & Cards",
        goal="Build clean TUI status meters and aligned panels",
        explanation=(
            "SayLang has built-in TUI widgets: `bar done of total`, `rule --title`,\n"
            "`below`, and `box --title`. Combine them to make rich dashboards."
        ),
        example=(
            'say bar 3 of 4 --width 16 --label "Build" | box --title "CI"'
        ),
        challenge=(
            "Read `--done` (default `3`) and `--total` (default `5`), convert\n"
            "both with `number of`, then print `bar done of total --width 10 --label \"Done\"`\n"
            'inside `| box --title "Progress"`.'
        ),
        starter=(
            "flags: --done, --total\n"
            "set d_raw to flag --done\n"
            "if not d_raw\n"
            '    set d_raw to "3"\n'
            "set t_raw to flag --total\n"
            "if not t_raw\n"
            '    set t_raw to "5"\n'
            "set done_n to number of d_raw\n"
            "set total_n to number of t_raw\n"
            "# Render bar done_n of total_n --width 10 --label \"Done\" | box --title \"Progress\"\n"
        ),
        solution=(
            "flags: --done, --total\n"
            "set d_raw to flag --done\n"
            "if not d_raw\n"
            '    set d_raw to "3"\n'
            "set t_raw to flag --total\n"
            "if not t_raw\n"
            '    set t_raw to "5"\n'
            "set done_n to number of d_raw\n"
            "set total_n to number of t_raw\n"
            'say bar done_n of total_n --width 10 --label "Done" | box --title "Progress"\n'
        ),
        hints=(
            'Syntax: bar done_n of total_n --width 10 --label "Done"',
            'Pipe it into | box --title "Progress"',
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
        track="TUI Building",
        title="Interactive TUI Menus",
        goal="Ask for input and render arrow-key `choose` menus",
        explanation=(
            "`ask` reads user text and `choose \"Prompt\" from <list>` launches an\n"
            "interactive arrow-key selector in a TTY (or clean numbered menu in pipes)."
        ),
        example=(
            'set env_mode to choose "Target:" from a list of "dev", "prod"\n'
            'say "Deploying to " plus env_mode | box'
        ),
        challenge=(
            'Ask `"Project name? "` into `project`, then let the user pick `mode`\n'
            'via `choose "Mode:" from a list of "cli", "tui", and "daemon"`.\n'
            'Print `project plus " -> " plus mode | box`.'
        ),
        starter=(
            'set project to ask "Project name? "\n'
            "# Let the user choose mode from cli, tui, daemon and print a boxed summary\n"
        ),
        solution=(
            'set project to ask "Project name? "\n'
            'set mode to choose "Mode:" from a list of "cli", "tui", and "daemon"\n'
            'say project plus " -> " plus mode | box\n'
        ),
        hints=(
            'Use: set mode to choose "Mode:" from a list of "cli", "tui", and "daemon"',
            'Then: say project plus " -> " plus mode | box',
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
        track="Real Programs",
        title="Files, JSON & Error Recovery",
        goal="Persist structured JSON files safely with try/if it fails",
        explanation=(
            "Real CLI tools save state to disk using `| json` and `write ... to file`,\n"
            "reload it with `read file` + `parse json`, and guard missing files with\n"
            "`file exists` or `try ... if it fails with err`."
        ),
        example=(
            'set cfg to a map with host as "localhost", port as 8080\n'
            'write cfg | json to file "settings.json"\n'
            'set loaded to parse json (read file "settings.json")\n'
            "say loaded's host"
        ),
        challenge=(
            'Save a map `cfg` (`app as "saylang"`, `port as 9000`) as JSON to `"app.json"`.\n'
            'Check `if file exists "app.json"`, read and `parse json` into `data`, and print\n'
            '`"Loaded: ", data\'s app, ":", data\'s port`.\n'
            'Also wrap `read file "missing.json"` in `try / if it fails with err` and print `"Caught missing"`.'
        ),
        starter=(
            'set cfg to a map with app as "saylang", port as 9000\n'
            '# 1. Write cfg | json to file "app.json"\n'
            '# 2. Read and parse json if file exists "app.json"\n'
            '# 3. Try reading "missing.json" and catch the error\n'
        ),
        solution=(
            'set cfg to a map with app as "saylang", port as 9000\n'
            'write cfg | json to file "app.json"\n'
            'if file exists "app.json"\n'
            '    set data to parse json (read file "app.json")\n'
            '    say "Loaded: ", data\'s app, ":", data\'s port\n'
            "try\n"
            '    set x to read file "missing.json"\n'
            "if it fails with err\n"
            '    say "Caught missing"\n'
        ),
        hints=(
            'Write JSON with: write cfg | json to file "app.json"',
            'Parse back with: set data to parse json (read file "app.json")',
        ),
        tests=(
            LessonTest(
                description="Writes JSON, parses fields back, and catches missing file error",
                expect_contains=("Loaded: saylang:9000", "Caught missing"),
                use_temp_dir=True,
            ),
        ),
    ),
    Lesson(
        number=9,
        id="09-tty-clock",
        track="CLI + TUI",
        title="Big-Letter TTY Clock",
        goal="Combine stdlib time, ascii art, below alignment, and flags",
        explanation=(
            "Prebuilt modules (`time`, `ascii`, `color`, `flags`, `tty`) let you compose\n"
            "complete terminal utilities in four readable lines of SayLang."
        ),
        example=(
            "import time, ascii\n"
            "print time --12h | ascii --size default colour cyan\n"
            "if flag -d then print date below time\n"
            "flags: -d"
        ),
        challenge=(
            "Import `time, ascii`, print `time --12h | ascii --size small colour cyan`,\n"
            "and when `flag -d` is passed, print `date below time`.\n"
            "Declare `flags: -d`."
        ),
        starter=(
            "import time, ascii\n"
            "flags: -d\n"
            "# Print big-letter time and optional centered date below it\n"
        ),
        solution=(
            "import time, ascii\n"
            "print time --12h | ascii --size small colour cyan\n"
            "if flag -d then print date below time\n"
            "flags: -d\n"
        ),
        hints=(
            "Use `| ascii --size small` on `time --12h`.",
            "Add: if flag -d then print date below time",
        ),
        tests=(
            LessonTest(
                description="Default run prints big block-letter time",
                expect_contains=("█",),
                expect_ansi=True,
            ),
            LessonTest(
                description="-d flag adds current date below time",
                cli_args=("--size", "small", "-d"),
                expect_contains=("█", "20"),
            ),
        ),
    ),
    Lesson(
        number=10,
        id="10-capstone-cruncher",
        track="Capstone",
        title="Capstone: Number Cruncher CLI",
        goal="Build a fault-tolerant CLI stats cruncher with tables & bars",
        explanation=(
            "Inspired by Kestral Lesson 13! Combine loops, `ask`, `try / if it fails`,\n"
            "lists, maps, math pipes (`| sum`, `| min`, `| max`, `| average`), `| table`,\n"
            "`bar`, and CLI flags into a real data-crunching terminal tool."
        ),
        example=(
            "set nums to a list of 10, 20, 30\n"
            "say nums | sum, nums | min, nums | max, nums | average"
        ),
        challenge=(
            "1. Declare `flags: --compact` and start `set nums to an empty list`.\n"
            '2. Loop with `while true`: ask `"Number (or done): "`; `stop` if trimmed input is `"done"` or `""`.\n'
            '3. Convert input with `try` + `number of` and `add` to `nums`; on error print `"Skipping invalid: ", raw colour red`.\n'
            '4. If `nums` is empty print `"No numbers entered."`.\n'
            "5. Otherwise compute `total` (`| sum`), `low` (`| min`), `high` (`| max`), `avg` (`| average`),\n"
            '   render a table of maps (`metric`, `value`) piped through `| box --title "Number Cruncher"`,\n'
            '   and unless `flag --compact` is set, also print `bar length of nums of 10 --label "Samples"`.'
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
            '        say "Skipping invalid: ", raw colour red\n\n'
            "if length of nums is 0\n"
            '    say "No numbers entered."\n'
            "otherwise\n"
            "    # Build summary maps (metric/value), print table inside box, and sample bar\n"
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
            '        say "Skipping invalid: ", raw colour red\n\n'
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
            'Put metric/value maps in a list and print: report | table | box --title "Number Cruncher"',
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
) -> str:
    """Render the freeCodeCamp-style curriculum map screen."""
    rows = max(rows, 16)
    cols = max(cols, 50)
    sel = max(0, min(selected, len(LESSONS) - 1))

    done_count = len(completed)
    bar = runtime.say_bar(done_count, len(LESSONS), width=20)
    header = f" SAYLANG LEARN · Curriculum ({done_count}/{len(LESSONS)} complete) "
    header_bar = f"{_INV}{header[:cols].ljust(cols)}{_RESET}"
    footer = " ↑/↓ Lesson   Enter Start   1-9 Jump   r Reset Progress   q/Esc Quit "
    footer_bar = f"{_INV}{footer[:cols].ljust(cols)}{_RESET}"

    lines: list[str] = [
        header_bar,
        "",
        f"  {_BOLD}SayLang Interactive Course{_RESET}  {_DIM}{bar} ({done_count}/{len(LESSONS)}){_RESET}",
        f"  {_DIM}Learn by building real CLI tools, JSON workflows & TUI apps{_RESET}",
        "",
    ]

    for idx, lesson in enumerate(LESSONS):
        mark = f"{_GREEN}✓{_RESET}" if lesson.id in completed else f"{_GRAY}○{_RESET}"
        badge = f"[{lesson.track}]"
        raw = f"{lesson.number:>2}. {badge:<15} {lesson.title:<26} {lesson.goal}"
        clipped = raw[: max(cols - 10, 20)]
        if idx == sel:
            lines.append(
                f"  {_INV} ▸ {('✓ ' if lesson.id in completed else '○ ')}{clipped.ljust(max(cols - 10, 20))} {_RESET}"
            )
        else:
            lines.append(f"   {mark} {_BOLD}{lesson.number:>2}.{_RESET} {_CYAN}{badge:<15}{_RESET} {lesson.title:<26} {_DIM}{lesson.goal[:max(cols - 54, 8)]}{_RESET}")

    body_target = rows - 1
    while len(lines) < body_target:
        lines.append("")
    lines = lines[:body_target]
    lines.append(footer_bar)
    return "\x1b[H\x1b[?25l" + "\n".join(f"{ln}\x1b[K" for ln in lines)


def render_learn_workspace(
    lesson: Lesson,
    buf: NanaBuffer,
    test_results: list[TestResult],
    hint_idx: int,
    completed: set[str],
    rows: int,
    cols: int,
) -> str:
    """Render the split-pane freeCodeCamp workspace (Brief/Tests left, Editor right)."""
    rows = max(rows, 14)
    cols = max(cols, 48)
    body_rows = rows - 3

    status_done = " ✓ DONE" if lesson.id in completed else ""
    left_hdr = f" LEARN {lesson.number}/{len(LESSONS)} · {lesson.title}{status_done} "
    right_hdr = f"Ln {buf.row + 1}, Col {buf.col + 1}  SayLang v{__version__} "
    gap = max(cols - len(left_hdr) - len(right_hdr), 1)
    top_bar = f"{_INV}{(left_hdr + ' ' * gap + right_hdr)[:cols].ljust(cols)}{_RESET}"

    ok_syn, syn_msg = buf.check_syntax()
    syn_badge = f"{_GREEN}✓ {syn_msg}{_RESET}" if ok_syn else f"{_RED}✗ {syn_msg}{_RESET}"
    extra = f"  │  {buf.status}" if buf.status else ""
    status_line = f" {syn_badge}{extra}"

    footer_txt = " ^T Check Tests  ^R Run  ^H Hint  ^B Brief  ^L Map  ^E Reset  ^X Exit "
    footer_bar = f"{_INV}{footer_txt[:cols].ljust(cols)}{_RESET}"

    if cols >= 92:
        left_w = max(36, min(46, cols * 44 // 100))
        right_start = left_w + 2  # after "│ "
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
            f" {_DIM}{'─' * min(inner_left, 40)}{_RESET}",
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
                left_lines.append(f" {icon} {t.description[: inner_left - 2]}")
                if not res.passed and res.detail:
                    left_lines.append(f"   {_RED}{res.detail[: inner_left - 3]}{_RESET}")
            else:
                left_lines.append(f" {_GRAY}○{_RESET} {t.description[: inner_left - 2]}")

        out: list[str] = ["\x1b[H", f"{top_bar}\x1b[K\n"]
        for r in range(body_rows):
            l_txt = left_lines[r] if r < len(left_lines) else ""
            l_pad = " " * max(left_w - _vis_len(l_txt), 0)
            line_idx = buf.scroll_y + r
            if line_idx < len(buf.lines):
                raw_code = buf.lines[line_idx][buf.scroll_x : buf.scroll_x + code_w]
                hl = highlight_saylang_line(raw_code)
                lineno = f"{line_idx + 1:>{num_w}}"
                r_txt = f"{_GRAY}{lineno} │ {_RESET}{hl}"
            else:
                r_txt = f"{_GRAY}{'~':>{num_w}} │ {_RESET}"
            out.append(f"{l_txt}{l_pad}{_GRAY}│{_RESET}{r_txt}\x1b[K\n")

        out.append(f"{status_line}\x1b[K\n")
        out.append(f"{footer_bar}\x1b[K")
        cur_r = (buf.row - buf.scroll_y) + 2
        cur_c = left_w + 1 + gutter_w + (buf.col - buf.scroll_x) + 1
        out.append(f"\x1b[{cur_r};{cur_c}H")
        return "".join(out)

    # Narrow stacked editor + goal strip
    gutter_w = max(len(str(len(buf.lines))) + 3, 6)
    code_w = max(cols - gutter_w, 10)
    ed_rows = max(body_rows - 2, 4)
    if buf.row < buf.scroll_y:
        buf.scroll_y = buf.row
    elif buf.row >= buf.scroll_y + ed_rows:
        buf.scroll_y = buf.row - ed_rows + 1
    if buf.col < buf.scroll_x:
        buf.scroll_x = buf.col
    elif buf.col >= buf.scroll_x + code_w:
        buf.scroll_x = buf.col - code_w + 1

    passed_n = sum(1 for r in test_results if r.passed)
    goal_bar = f" Goal: {lesson.goal[:max(cols - 26, 12)]}  [{passed_n}/{len(lesson.tests)}]"
    out_n: list[str] = [
        "\x1b[H",
        f"{top_bar}\x1b[K\n",
        f" {_CYAN}{goal_bar[:cols - 1]}{_RESET}\x1b[K\n",
        f" {_DIM}{'─' * min(cols - 2, 50)}{_RESET}\x1b[K\n",
    ]
    num_w = gutter_w - 3
    for r in range(ed_rows):
        line_idx = buf.scroll_y + r
        if line_idx < len(buf.lines):
            raw_code = buf.lines[line_idx][buf.scroll_x : buf.scroll_x + code_w]
            hl = highlight_saylang_line(raw_code)
            lineno = f"{line_idx + 1:>{num_w}}"
            out_n.append(f"{_GRAY}{lineno} │ {_RESET}{hl}\x1b[K\n")
        else:
            out_n.append(f"{_GRAY}{'~':>{num_w}} │ {_RESET}\x1b[K\n")

    out_n.append(f"{status_line}\x1b[K\n")
    out_n.append(f"{footer_bar}\x1b[K")
    cur_r = (buf.row - buf.scroll_y) + 4
    cur_c = gutter_w + (buf.col - buf.scroll_x) + 1
    out_n.append(f"\x1b[{cur_r};{cur_c}H")
    return "".join(out_n)


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


def _run_lesson_preview(lesson: Lesson, code: str) -> None:
    """Run current lesson code safely and display output overlay."""
    sample = lesson.tests[0] if lesson.tests else None
    cli_args = list(sample.cli_args) if sample else []
    inputs = (
        list(sample.input_lines)
        if sample and sample.input_lines is not None
        else []
    )
    prev_cwd = os.getcwd()
    tmp_ctx = tempfile.TemporaryDirectory() if (sample and sample.use_temp_dir) else None
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
    _show_overlay(f"Run Output · {lesson.title}", body)


def run_learn(
    lesson_num: int | None = None,
    *,
    list_only: bool = False,
    reset: bool = False,
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

    if list_only:
        print(format_curriculum_list(completed))
        return 0

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        print("saylang learn TUI requires an interactive terminal.", file=sys.stderr)
        print(format_curriculum_list(completed), file=sys.stderr)
        return 1

    runtime._enable_windows_ansi()
    old_attrs = None
    if sys.platform != "win32":
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_attrs = termios.tcgetattr(fd)
        tty.setraw(fd)

    try:
        sys.stdout.write("\x1b[?1049h")
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
                sys.stdout.write(render_lesson_map(sel, completed, rows, cols))
                sys.stdout.flush()
                k = _read_key()
                if k == "UP":
                    sel = (sel - 1) % len(LESSONS)
                elif k == "DOWN":
                    sel = (sel + 1) % len(LESSONS)
                elif k in ("\r", "\n"):
                    return sel
                elif k.isdigit() and 1 <= int(k) <= len(LESSONS):
                    return int(k) - 1
                elif k == "r":
                    ans = _prompt_bar("Reset all course progress? (y/n): ")
                    if ans and ans.lower().startswith("y"):
                        completed.clear()
                        drafts.clear()
                        reset_progress()
                elif k in ("ESC", "q", "\x18", "\x03"):
                    return None

        cur_idx: int | None
        if lesson_num is not None:
            if not (1 <= lesson_num <= len(LESSONS)):
                sys.stdout.write("\x1b[?1049l\x1b[?25h\x1b[0m")
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
            buf = NanaBuffer(
                lines=initial_text.rstrip("\n").split("\n") or [""],
                filepath=Path(f"{lesson.id}.pl"),
            )
            results: list[TestResult] = []
            hint_idx = 0

            while True:
                cols, rows = shutil.get_terminal_size((80, 24))
                sys.stdout.write(
                    "\x1b[?25h"
                    + render_learn_workspace(
                        lesson, buf, results, hint_idx, completed, rows, cols
                    )
                )
                sys.stdout.flush()

                key = _read_key()
                buf.status = ""

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
                                "COURSE COMPLETE! All 10 Lessons Passed!",
                                summary + "\n\nYou mastered CLI & TUI building in SayLang!",
                            )
                    else:
                        passed_n = sum(1 for r in results if r.passed)
                        buf.status = f"Tests: {passed_n}/{len(results)} passed"
                    continue

                if key == "\x12":  # Ctrl+R -> Run Live
                    _run_lesson_preview(lesson, buf.text)
                    continue

                if key == "\x08":  # Ctrl+H -> Hint / Solution
                    if hint_idx < len(lesson.hints):
                        hint_idx += 1
                        buf.status = f"Hint {hint_idx}/{len(lesson.hints)} shown"
                    else:
                        _show_overlay(
                            f"Reference Solution · Lesson {lesson.number}",
                            lesson.solution,
                        )
                    continue

                if key == "\x02":  # Ctrl+B -> Brief overlay
                    _show_overlay(
                        f"Lesson {lesson.number} · {lesson.title}",
                        _format_brief_overlay(lesson, results, hint_idx),
                    )
                    continue

                if key == "\x05":  # Ctrl+E -> Reset starter
                    ans = _prompt_bar("Reset code to starter? (y/n): ", buf=buf)
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
                    fname = _prompt_bar("Save to .pl file: ", f"{lesson.id}.pl", buf=buf)
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
        sys.stdout.write("\x1b[?1049l\x1b[?25h\x1b[0m")
        sys.stdout.flush()
        if old_attrs is not None:
            import termios

            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_attrs)
