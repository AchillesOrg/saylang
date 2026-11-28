# Interactive clickable Mouse TUI Calculator (click buttons or press keys, Q to quit)
set keys to a list of "7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "C", "0", "=", "+", "Q"
set screen to ""
while true
    set btn to buttons "Calc: {screen}" from keys --cols 4
    if btn is "" or btn is "Q"
        stop
    if btn is "C"
        set screen to ""
    otherwise if btn is "="
        try
            set screen to "{calc screen}"
        if it fails with err
            set screen to "Error"
    otherwise
        set screen to "{screen}{btn}"
say "Result: {screen}" | box --title "Calculator"
