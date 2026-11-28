<p align="center">
  <img src="assets/banner.png" alt="Saylang" width="760">
</p>

# SayLang

**SayLang** (`saylang`, `.pl`) is a readable, bracket-free plain-English programming language implemented in Python (zero external runtime dependencies) and packaged as standalone **macOS** and **Windows** apps.

Repository: https://github.com/AchillesOrg/saylang

## Install

The default installers resolve the latest published release on every run. To install a specific version, choose a tag from [GitHub Releases](https://github.com/AchillesOrg/saylang/releases) and pass it to the installer.

**macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/AchillesOrg/saylang/main/install.sh | sh
```

For a specific release:
```sh
curl -fsSL https://raw.githubusercontent.com/AchillesOrg/saylang/main/install.sh | sh -s -- --version v0.3.2
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/AchillesOrg/saylang/main/install.ps1 | iex
```

For a specific release:
```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AchillesOrg/saylang/main/install.ps1))) -Version v0.3.2
```

Both installers accept version numbers with or without the `v` prefix. You can also set `SAYLANG_VERSION` as a default for scripted installs. Pass `latest` explicitly to override that setting.

**Python / From Source:**
```sh
pip install git+https://github.com/AchillesOrg/saylang.git
```

**Build Standalone App Locally (macOS or Windows):**
```sh
pip install pyinstaller
python3 scripts/build_app.py
```

## Quickstart

```sh
saylang run examples/hello.pl
saylang build examples/clock.pl -o clock   # make a standalone runnable binary
saylang compile examples/clock.pl --bin    # same: make a standalone binary
saylang examples/clock.pl -d
saylang examples/fizzbuzz.pl
saylang compile examples/fibonacci.pl --run
saylang english "print hello world lol in red" --run
saylang nana examples/clock.pl
saylang repl
```

*(If running directly from the repo without installing, replace `saylang` with `python3 -m saylang`.)*

## Prebuilt Libraries, CLI & TUI Primitives

Built-in libraries (`time`, `ascii`, `tui`, `json`, `files`, `color`, `text`, `math`, `sys`, `flags`, `tty`) work with explicit `import` or auto-imported out of the box:

```text
import time, ascii
pos center
print time --12h --live | ascii --size default colour cyan
if flag -d then print date below time
flags: -d
```

Build CLI tools, clickable mouse TUIs, and bash-style scripts rapidly:

```text
# String placeholders, positioning, clickable mouse buttons, calc, tables & files
set name to "Ada"
say "Hello, {name}!" | box --title "Hi" pos top-right

set keys to a list of "7", "8", "+", "=", "Q"
set btn to buttons "Tap key:" from keys --cols 3
say calc "12 + 3 * 4"

save data to "config.json"
set cfg to load "config.json"
say shell "git status -s" | grep "M " | head 5
```

Run `saylang examples/dashboard.pl` or `saylang examples/clock.pl -d`, or center a live clock directly with `pos center` + `time --12h --live`.

## Interactive Course (`saylang learn`)

Learn SayLang in plain, zero-jargon English inside a freeCodeCamp-style split-pane terminal TUI with **12 hands-on lessons**, including **CLI Calculator**, **Mouse TUI Calculator**, **Live Centered Clock**, and **Number Cruncher**:

```sh
saylang learn            # open curriculum map & split-pane coding TUI
saylang learn 11         # jump directly to Mouse TUI Calculator
saylang learn --list     # show all 12 lessons & completion progress
```

Also works directly inside the REPL (`:learn` or `learn`) and from `nana`'s welcome menu.

## Built-in `nana` TUI Editor

Launch the interactive `nana` TUI studio (with New File, Starter Templates + live preview, `.pl` File Browser, Run with Flags, Cheat Sheet, live syntax highlighting, smart auto-indent, and in-editor `Ctrl+R` runner):

```sh
saylang nana
saylang nana clock.pl
```

Or type `nana` (or `nana clock.pl`) directly inside the `saylang` REPL.
- `Ctrl+S` Save · `Ctrl+R` Run · `Ctrl+B` Build binary · `Ctrl+P` TUI Menu · `Ctrl+K` Cut · `Ctrl+U` Paste · `Ctrl+G` Help · `Ctrl+X` Exit

## Syntax Cheat Sheet

```text
# Comments work with `#` (full-line or inline)
note And `note` works for prose comments too!

set score to 10
increase score by 5
decrease score by 2

# Simple colored and styled output
say "hello world lol" colour red
say "Score: ", score in bright green bold
say "ALERT" color white on red underline

if score is greater than 10
    say "Great job!" colour cyan
otherwise if score is 10
    say "Right on target."
otherwise
    say "Keep going."

for each n from 1 to 5
    say n

set fruits to a list of "apple", "banana", and "cherry"
add "date" to fruits
say "First: ", first item of fruits
say "Joined: ", joined fruits with ", "

set user to a map with name as "Ada", role as "engineer"
say user's name, " is an ", user's role

to greet with person
    say "Hello, ", person, "!" colour green

call greet with user's name

try
    say item 99 of fruits
if it fails with error
    say "Oops: ", error colour yellow
```

### Key Rules
- **File extension**: `.pl`
- **Blocks** use 4-space indentation (trailing `:` on headers is optional).
- **Comments** start with `#` (full-line or inline) or `note`.
- **Colored & styled `say`**: add `colour <name>` / `color <name>` / `in <name>`, optional `on <bg>` / `background <bg>`, and `bold`, `dim`, `italic`, or `underline` (colors: `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `purple`, `cyan`, `white`, `gray`/`grey`, `orange`, `pink`, plus `bright <color>`).
- **1-based indexing**: `item 1 of my_list` is the first element.
- **`say`** joins comma-separated expressions directly without inserting extra spaces.
- **No hard-to-type symbols required**: use `plus`, `minus`, `times`, `divided by`, `modulo`, `is`, `is not`, `is greater than`, `and`, `or`, `not`.

## CLI Commands

- `saylang learn [n | --list | --reset]` — launch the interactive freeCodeCamp-style TUI course
- `saylang nana [file.pl]` — launch the built-in `nana` TUI studio & editor
- `saylang run <file.pl>` (or `saylang <file.pl>`) — execute a SayLang program
- `saylang build <file.pl> [-o <out>] [--run]` — turn a SayLang program into a standalone native binary
- `saylang compile <file.pl> [--bin] [-o <out>] [--run]` — compile to a standalone binary (`--bin`) or Python 3 file
- `saylang check <file.pl>` — check syntax without running
- `saylang ast <file.pl>` — print the parsed AST
- `saylang english "<instructions>" [--provider auto|offline|gemini|openai|anthropic] [--run] [--compile]` — translate loose English into SayLang
- `saylang repl` — start the interactive REPL

## REPL Commands

Inside `saylang repl`:
- `:help` — show quick reference
- `:learn [n]` — open the interactive SayLang TUI course
- `:nana [file.pl]` — open the built-in `nana` editor
- `:vars` — show current variables and functions
- `:py` — show compiled Python for the last snippet
- `:ast` — show the parsed AST for the last snippet
- `:english <prompt>` — translate everyday English to SayLang and run it
- `:reset` — clear workspace state
- `:quit` — exit

## LLM-Assisted Translation (Optional)

With no API keys set, `saylang english` uses the deterministic offline rule-based translator. To enable free-form LLM translation with automatic syntax-check retries, export one of:

```sh
export GEMINI_API_KEY="..."
# or OPENAI_API_KEY="..."
# or ANTHROPIC_API_KEY="..."
```

## Running Tests

```sh
python3 -m unittest discover -s tests -v
```
