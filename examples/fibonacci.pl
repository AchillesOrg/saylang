# Generate Fibonacci numbers using a SayLang function and a list

to fib with n
    if n is at most 1
        return n
    set prev to 0
    set curr to 1
    for each step from 2 to n
        set next_val to prev plus curr
        set prev to curr
        set curr to next_val
    return curr

set sequence to an empty list
for each i from 0 to 10
    set value to call fib with i
    add value to sequence

say "First 11 Fibonacci numbers: ", joined sequence with ", "
