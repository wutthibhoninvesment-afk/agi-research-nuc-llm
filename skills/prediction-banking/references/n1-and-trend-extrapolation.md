# Extrapolating from n=1: the rate shape and the trend shape

Reference for `skills/prediction-banking/SKILL.md` steps 19 and 20. Split out
of the SKILL body by round 484, which pushed it past skill-lint's 500-line
B001 limit; nothing here is abridged.

Both steps are about a bank betting more than its evidence supports. They are
NOT the same mistake and they have different remedies:

* **Step 19 (round 483) — the RATE shape.** One instance of a CLASS is
  generalised to the class. Remedy: count the class in §0 before betting on
  it in §1.
* **Step 20 (round 484) — the TREND shape.** One prior reading of the SAME
  quantity is extended into a direction. Remedy: bet on the mechanism, not
  the direction — there is no class to count, so step 19's fix does not
  apply.

Step 20 carries a second, independent half about the FORM a line is written
in, which is the only part of either step that makes predictions better
rather than merely safer.

---

19. **A rate extrapolated from ONE observed instance is an n=1 rate line —
    put it in §0 as a question, not in §1 as a bet.** Round 483 banked three
    predictions that were one bet in three costumes (P2 *some real subject is
    volatile under a fixed seed*, P5 *1-3 of the four named instruments are
    cross-seed unstable*, P6 *the control changes a real verdict*). All three
    lost, 0 of 13, and the reason was in the artefact rather than in
    hindsight: none prints a clock to stdout and `sorted(` is pervasive in
    their derivations. The bank had been shown ONE instance of the class —
    round 481's `best_incoming` tie — and predicted the population from it.
    That is `cause-needs-a-denominator` reaching a prediction bank: **the
    instance you were shown is the numerator and nothing was the
    denominator.**

    The tell is syntactic. If a line's written justification is *"this tree
    has one confirmed instance and nobody has ever run the check"*, it is a
    rate with n=1 — not banned, but a question, so it goes in §0 with the
    command that would answer it. Round 483's §0 had six baselines and none
    was "how many of these instruments iterate a set of strings at all",
    which is one grep and would have moved all three lines before freezing.

    Checkable outcome: no §1 line rests on a single prior observation of its
    own class without a §0 row measuring how common the class is.

20. **A trend fitted to one prior observation is a guess with a slope on it —
    and an ENUMERATED prediction is worth more than a directional one,
    because the residual is where the finding is.** Two halves, both from
    round 484 (NUC E), which lost three of fourteen lines to the first and
    made its two best findings out of the second.

    *The trend half.* Step 19 is about extrapolating a RATE across a class.
    This is about extrapolating a DIRECTION for the same quantity: "it got
    worse last round, so it got worse again." Round 484 banked three such
    lines — P5 (journald dropped three boots between the last two captures,
    so it drops at least one more), P11 (`audit --strict` was red last round,
    so it stays red), P12 (round 349 found four false claims, so at least two
    of them reappear). **All three over-predicted**, and P11 was reasoned
    explicitly *from* P5's premise, so one wrong premise took two lines with
    it. Step 19's remedy does not apply: the prior observation is of the same
    quantity, not of a sibling, so there is no class to count.

    The remedy is to **bet on the mechanism, not the direction**. P5 was not
    even wrong about decay — journald really did eat **5h30m of the oldest
    boot's interior** — it was wrong about the coordinate, because "boots
    dropped" and "interior truncated" are two different consequences of one
    process and the bank named only one. Ask *what does the mechanism act on*
    before writing which way the number moves.

    The tell: a §1 line whose justification is *"this got worse last time"*
    with no sentence naming why. And never let two lines share an unstated
    premise — if P11 rests on P5, say so in the bank, so a reader scoring one
    knows the other is not independent evidence.

    *The enumeration half.* Round 484's two best lines were both SPLITs, and
    both were splits because they **listed** rather than gestured. P2 named
    the eight specific files a sweep would delete; seven died and `sar26`
    lived, and that one survivor is the entire round — a receipt that
    outlived its day file by 3.7 seconds because `find -mtime +7` floors to
    whole days while the timer jitters by seventeen seconds. Had P2 said "the
    sweep deletes old files" it would have scored a clean HIT and found
    nothing. P4 named three gate exit codes; two held and the third was red,
    and the red one was a round-478 record gap nobody had noticed.

    So: **prefer the form that can be partly wrong.** A line that enumerates
    n items has n places to be surprised; a line that states a direction has
    one, and a HIT on it teaches nothing. When a bank is scored, treat every
    SPLIT as the most interesting row in the table and write the residual up
    before the hits.

    Checkable outcome: no §1 line rests on a single prior reading of its own
    quantity without a sentence naming the mechanism; lines that depend on
    another line say which; and the scored table marks partial outcomes as
    SPLIT rather than rounding them to HIT or MISS.
