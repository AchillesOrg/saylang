# SayLang

**SayLang** (`saylang`, `.pl`) is a readable, bracket-free plain-English programming language implemented in Python (zero external runtime dependencies) and packaged as standalone **macOS** and **Windows** apps.

Repository: https://github.com/AchillesOrg/saylang

## Install

**macOS:**
```sh
curl -fsSL https://raw.githubusercontent.com/AchillesOrg/saylang/main/install.sh | sh
```

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/AchillesOrg/saylang/main/install.ps1 | iex
```

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
saylang examples/fizzbuzz.pl
saylang compile examples/fibonacci.pl --run
saylang english "print hello world lol in red" --run
saylang repl
```

*(If running directly from the repo without installing, replace `saylang` with `python3 -m saylang`.)*

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

- `saylang run <file.pl>` (or `saylang <file.pl>`) — execute a SayLang program
- `saylang compile <file.pl> [-o out.py] [--run]` — transpile to standalone Python 3
- `saylang check <file.pl>` — check syntax without running
- `saylang ast <file.pl>` — print the parsed AST
- `saylang english "<instructions>" [--provider auto|offline|gemini|openai|anthropic] [--run] [--compile]` — translate loose English into SayLang
- `saylang repl` — start the interactive REPL

## REPL Commands

Inside `saylang repl`:
- `:help` — show quick reference
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
