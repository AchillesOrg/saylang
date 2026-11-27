# Managing a list of maps with possessive syntax and error handling

set task1 to a map with title as "Design SayLang syntax", done as true
set task2 to a map with title as "Write example programs", done as false
set task3 to a map with title as "Run the test suite", done as false

set tasks to a list of task1, task2, and task3

for each task in tasks
    if task's done is true
        set status to "done"
    otherwise
        set status to "todo"
    say "- ", task's title, " (", status, ")"

set tasks_left to 0
for each task in tasks
    if not task's done
        increase tasks_left by 1

say "Remaining tasks: ", tasks_left

try
    say item 99 of tasks
if it fails with err
    say "Caught expected error: ", err
