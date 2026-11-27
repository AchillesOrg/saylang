# Count word frequencies in a sentence using a map

set sentence to "SayLang makes plain English code clear and readable"
set tokens to words of lowercase of sentence
set counts to an empty map

for each word in tokens
    if counts contains word
        increase entry word of counts by 1
    otherwise
        set entry word of counts to 1

say "Word frequencies:"
for each word and total in counts
    say "  ", word, ": ", total
