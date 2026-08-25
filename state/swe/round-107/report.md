# SWE campaign report

| metric | value |
|---|---|
| mutants | 1056 |
| baseline score | 0.8816 (931 killed / 125 survived, 3722.2 s) |
| timeout recheck flips | 14 of 22 timeouts |
| corrected score | 0.875 (132 survived) |
| corpus killers | 6 of 132 survivors (126 no_killer), 6 verified |
| model kills | 0 of 8 attempted, 5 equivalent claimed, 0 verified, $3.6035, 67 steps |
| review | None claims, None confirmed, tools None, $None, stop=None |
| coverage | whence/interp.py 72.8% (targeted, lower bound); survivors 112 covered / 20 uncovered; killed-on-uncovered 2 of 267 traced; corpus kills 3/112 covered vs 3/20 uncovered |
| repair | 6 attempted: 5 green, 5 exact, 5 localized, 0 green-not-exact, 0 cheated, $0.2923, 44 steps (claude-sonnet-5) |
| tests added | 6 |
| projected final score | 0.8807 |
| live cost | $3.8958 |
