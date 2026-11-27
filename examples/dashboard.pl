# Terminal dashboard showcasing bars, tables, JSON, and boxed layout
import ascii, tui, json

set tasks to a list of (a map with task as "Lexer & Parser", status as "done"), (a map with task as "nana TUI", status as "done"), and (a map with task as "learn Course", status as "ready")

say "SAYLANG" | ascii --size small colour cyan bold
say rule --title "Release Dashboard"
say tasks | table colour white
say ""
say bar 3 of 3 --width 24 --label "Build" colour green
say "Snapshot: ", (a map with version as "0.3.0", status as "green") | json --compact | box --title "Metadata"
