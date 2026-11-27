# Live ticking TTY clock (run with: saylang examples/live_clock.pl -d)
import time, ascii

every 1 second
    clear screen
    print time --12h | ascii --size default colour cyan
    if flag -d then print date below time

flags: -d
