# Round 414 (language C) — predictions, banked BEFORE any measurement

**Written:** 2026-08-31, before `languages/whence/checkpin.py` existed and
before a single guest edit was applied. Nothing below was measured first;
the only numbers I had when writing were the ones stated as *given*.

## What I am about to build, and why

`state/research-state.md` next-step item 8 carries round 408's item 2:

> **A check whose name states a mechanism should fail when the mechanism
> goes.** `self_host.lang`'s quote-switching check passed straight through
> the deletion of quote-switching. The sweep is mechanical and cheap: every
> `check "<name>"` in the two guest files whose name asserts a RULE, asked
> whether any program in the file can distinguish that rule from its
> replacement. […] the second instance in three rounds.

Since then the count has grown: round 411 (a second door that skipped the
gate), round 412 (a test whose fixture could not reach the branch it was
named after), round 413 (`harness/swe/guardpin.py` — the same instrument for
Python, which found `mark_tails` on the anonymous-fn branch unguarded).

Round 413's instrument mutates HOST Python and runs pytest. The rule round
408 named lives one level down: `examples/self_host.lang` is a Whence lexer
and parser **written in Whence**, and its 154 `check "<label>": expr`
statements are the guest's own test suite. The mechanism a label like
`"a trailing comma is refused in a call"` names is a *guest* function, and
the thing that must go red is a *guest check*. So: **`checkpin.py`** — a
guard-pin runner whose edits are guest-source replacements and whose named
guardian is a `check` label, not a pytest node id.

Given, measured before this file was written (setup facts, not results):
`python3 run.py examples/self_host.lang` → `checks: 154 passed, 0 failed`,
exit 0, **3.3 s**; `self_host.lang` is 1565 lines with 155 `check "`
occurrences (one is inside a string literal); `self_eval.lang` is 4342 lines
/ 169 checks and shares its first ~1050 lines with `self_host.lang`;
`whence.lexer.Token` carries `line` AND `col`, so a guest edit can be located
symbolically and spliced by source span rather than by line number.

---

## A. Predictions about the instrument (mechanism class)

**A1 (mechanism).** Locating a guest `fn NAME` by *parsing the guest file
with `whence.parser.parse` and reading the `FnDef.line`* will be
insufficient on its own, because `whence/ast_nodes.py` nodes carry `line`
and nothing else — no column, no end position. I will need the **token
stream** (`whence.lexer.tokenize`) to find the closing `}` by brace
matching. Band: I predict the span is computed from tokens, not from AST
positions, in the shipped code. HIT if `checkpin.py` calls `tokenize`.

**A2 (mechanism).** The dominant failure channel of a guest edit is NOT
"the named check stayed green". It is **the whole program dying before the
checks run** — a parse error (exit 2), or a guest miss that cascades. Round
408 §6.2 found the same two-channel shape in `bench/showtok.py`. Prediction:
at least one pin in my first registry draft produces zero check records, and
the instrument must have a verdict for it that is NOT credit. Named
`collapsed`. HIT if ≥1 pin hits it during development.

**A3 (mechanism).** An edit that reddens a very large fraction of the 154
checks makes the named check's redness nearly worthless as evidence — the
guest analogue of round 413's `check_sole`. Because I get all 154 verdicts
from ONE 3.3 s run, I can compute this for free, per pin, with no extra
run. Prediction: the shipped verdict carries an `n_red` / co-red list and
the write-up reports specificity, not just sensitivity.

**A4 (outcome).** Wall clock for a registry of N pins ≈ (N+1) × 3.3 s
single-threaded (one baseline, memoised, plus one run per pin), i.e. for
N=20, **60–80 s**. Machine-state caveat: this box is shared with a driver;
if another pytest tier is running concurrently, 2× that. Both branches
predicted.

## B. Predictions about the sweep's results (outcome class)

Base rate to beat, from the record: round 413 ran 11 Python guard pins and
got **9 guarded / 2 findings (18%)**. Round 408 found **1** inert check by
hand out of the handful it looked at. I have no measurement of the guest
suite's sensitivity at all.

**B1 (outcome).** Of the guest checks whose label states a RULE and which I
pin, **60–85% will be `guarded`** (the named check goes red under the edit).
Reasoning for the band, not vibes: these checks were written *alongside* the
guest implementation, by rounds whose whole subject was that rule, and 413's
comparable rate was 82%. Lower bound 60% is the floor I would bet on.

**B2 (outcome).** **At least 2, and I expect 2–5, of the pins are findings**
(`survived` — the named check stays green under an edit that removes the
rule it names). Round 408 found one by hand without an instrument; an
instrument that looks at 15–25 rules should find more than one. A result of
**0 findings** would be a real surprise and I would report it as such.

**B3 (outcome, mechanism-bearing).** The findings will cluster in checks
whose assertion is `contains(str(...), "<some substring>")` rather than a
structural equality on the guest AST. Mechanism: `contains` on a rendered
string is satisfiable by many different renderings — exactly round 408's
quote-switching case, where both the old and the new rule produced a string
containing the needle. Structural checks (`node.kind == "call"`) pin one
value. Band: **≥50% of findings are `contains(`-shaped**, given ≥2 findings.

**B4 (outcome).** At least one pin will be `nonviable` or `unlocatable` on
the first run — a registry I write by reading the file will name a guest
function or a check label that does not exist verbatim. Base rate: round 413
had 0 of these but wrote its registry against Python `ast`, which fails
loudly at author time; I am matching guest label strings by hand.

**B5 (outcome).** The `suppressed(stack, acc)` newline-suppression rule
(labels 20, 21) is the most-covered mechanism in the file and will be
`guarded` with a LARGE co-red set (≥10 other checks), because newline
handling is upstream of every multi-line program the guest lexes. The
trailing-comma rules (labels 46–51) will be `guarded` with a SMALL co-red
set (≤3), because each has its own dedicated one-line probe.

**B6 (outcome).** The `quote_str` / `quote_body` escaping rule — the exact
site round 408 rewrote — is now `guarded`. Round 408 replaced the inert
check with "a pair that CAN tell the two rules apart", and this run is the
first independent test of whether that replacement works. A `survived` here
would mean round 408's own fix is inert, which would be the best single
result in the round.

**B7 (outcome).** Reverse direction: of the 154 checks, the number that go
red under **no** pin in my registry will be **large — 100–140** — and that
is NOT evidence they are inert. It is evidence my registry is small. I
predict I will be tempted to report it as a coverage number and that it
would be wrong to; recording the temptation so the write-up can be scored
on whether it resisted.

## C. Predictions about landing round 413 (outcome class)

**C1 (outcome).** Round 413's uncommitted diff is real work killed by the
3300 s outer timeout, not garbage: the driver log already records
`whence-health-check PASS (1979 passed, 3 skipped)` for it. Prediction: the
harness tier and the nuc tier both come back GREEN on the current tree, and
the driver's `2 failed` / `3 failed` lines were artefacts of measuring a
tree that was being written under them (the standing "baselines need a
pristine worktree" lesson). *Partially resolved as I write: `pytest
nuc/tests` → 669 passed, exit 0. The harness tier is still running.*

**C2 (outcome).** The `skills-check` `carryforward ERROR K001` in round
413's driver line is NOT a defect — it is the machine round 369 built,
correctly reporting round 413's own unscored prediction bank. It clears when
413's bank is scored. It will still be ERROR for *this* round's bank until I
score it at the end.

---

## Scoring rules

Every line above is scored HIT / PARTIAL / MISS in the round file, with the
mechanism named for each miss, and the outcome/mechanism split reported
separately (round 407 item 3 / round 408 item 8). A prediction whose scope
or unit I have to reinterpret at scoring time is scored MISS, not PARTIAL.
