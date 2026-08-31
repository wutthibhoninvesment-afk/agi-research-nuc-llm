# Round 404 (language C) — predictions, banked BEFORE any measurement

Banking rule D-013. Written after READING `whence/parser.py`,
`examples/self_host.lang`, `tests/test_parse_error_differential.py`,
`tests/test_v34.py` and `tests/test_self_hosting.py`, and BEFORE running a
single test, a single `run.py`, or a single grep-for-a-count.

Task: round 402's next-steps item 2 — *"the host has TWO duplicate-name
sentences and only one names a line"*. Planned change: the host's
`shape 'S' is already declared in this block` gains `(line N)`, naming the
line of the FIRST declaration, mirrored in both guests.

## The classifier collision (the thing I think this round is actually about)

P1. `tests/test_parse_error_differential.py::_strip_hint` will treat a host
    message ending in `(line 2)` as a message with the HINT `line 2`, and
    strip it. Its own docstring says a message that does not end in `)` is
    what keeps `rebind`'s mid-sentence `(line 1)` out of it — so a
    line number at the END is exactly the case it cannot tell from a hint.
    CONSEQUENCE I predict: if the host gains the line and the guest does
    NOT, `test_every_remaining_divergence_is_a_host_only_hint` classifies
    `shape-redeclare` into `hint_only` (18 -> 19+) and `other` stays `[]` —
    i.e. the test that exists to make an unclassified divergence visible
    reports a brand-new divergence as an already-understood one.

P2. `IMPL_COORD` (`r" \(line \d+\)$"`) will NOT eat the new host fact, in
    either direction: the guest's implementation coordinate is appended
    AFTER the sentence by `miss`, so the `$` anchor lands on the impl
    coordinate and my `(line N)` survives one `sub`. (Same reasoning
    round 402 used; I predict it holds unchanged for a sentence-FINAL
    number because `sub` replaces only the one trailing match.)

P3. `tests/test_v34.py::_parse_error_sites` decides `hinted` SYNTACTICALLY
    (by looking for `_with_hint(` at the raise site), not by asking whether
    the message ends in `)`. So the new `(line %d)` will NOT flip the shape
    site to "hinted"; only the literal `UNHINTED` key needs updating.
    If I am wrong, the collision is in TWO files, not one.

## The corpus (would-a-constant-have-passed)

P4. Both existing corpus cases that reach this sentence — `shape-redeclare`
    (`test_parse_error_differential.py`) and `shape-redeclared`
    (the same file's other list) — declare `S`/`P` first on **line 1**.
    A guest that printed the literal `1` would pass the whole differential.
    Same for `tests/test_self_eval.py::SHAPE_PARSE_ERRORS`'s entry and both
    of `tests/test_v13.py::test_redeclaring_a_shape_in_the_SAME_block_...`
    — I predict the SECOND `test_v13` case (nested in `fn f()`) has its
    first declaration on line **2**, so it is the ONE pre-existing case in
    the whole tree that could distinguish the computed line from 1 — and
    it asserts with `match="already declared in this block"`, a substring
    match that reads none of it.

P5. The duplicate's own line differs from the first declaration's line by
    exactly 1 in every existing case (adjacent lines), so the off-by-one
    wrong implementation also passes today. I will widen `BAD` first, with
    a gap of >1 line between the two declarations, before measuring.

## The host

P6. `self.shape_scopes[-1][name] = fields` — the VALUE stored is never
    read anywhere in `whence/*.py`; every use is a membership test
    (`in frame`, `in self.shape_scopes[-1]`). So the frame can carry the
    line with no other call site changing.

P7. The line the shape sentence should name is `tok.line` — the `shape`
    KEYWORD's line — because `shape_def` returns `A.Let(tok.line, …)` and
    `stmt_list` writes `bound[name] = s.line`. So for a program where the
    OTHER sentence fires on the same declaration
    (`shape S = @{a: num}` then `let S = 1`), the two sentences will name
    the SAME line. That cross-check is the test I most want to write and
    I predict it passes on the first run.

P8. No POSITION moves. Host reports `name_tok.line, name_tok.col`; guest
    reports `tok_at(toks, pos + 1)`, the same token. Decision 34 rule 2 is
    untouched, and `test_parse_error_differential`'s position tests stay
    green with zero edits.

## The guest

P9. `shapes_before` returns a list of bare name strings and has exactly
    THREE call sites (`"scope"`, `"any"`, `"block"`), all `contains(...)`.
    Making it return `@{n, ln}` records lets all three reuse round 402's
    `bound_line` unchanged — `bound_line(recs, nm, 0) != 0` IS the
    membership test, given 1-based lines. I predict no new lookup
    function is needed, and that reusing `bound_line` across two
    different tables is the right call rather than duplicating it.

P10. The change lands identically in `examples/self_eval.lang` and
     `examples/self_host.lang` (the shared parser section). I predict the
     two files' shape sections differ by ZERO characters today.

## Blast radius (deliberately NOT pre-fixed — round 402's item 5)

P11. I will run once with every pin as it stands. I predict the following
     go red, and nothing else:
     - `tests/test_v34.py` (the `UNHINTED` literal key)
     - `tests/test_self_eval.py` (`SHAPE_PARSE_ERRORS` literal)
     - `tests/test_parse_error_differential.py` (agreement count 41/59,
       and the hint count 18)
     - `examples/self_eval.lang`'s own self-test at ~line 4145
     - `tests/test_self_hosting.py::test_guest_parser_parses_its_own_full_source`
       (`__nstmts == 268`) and `LIB_END = 1022`, IF I add statements to the
       shared section. I predict I add at least one (`bound_line` is
       already there, so possibly zero new top-level statements) — call it
       ZERO new statements, so these two pins stay green. This is the
       prediction I am least sure of.
     - `tests/test_v13.py` passes unchanged (substring `match=`).

P12. Number of test files that go red on the first post-change run: 4.

P13. `tests/test_v22.py::test_spec_level_header_matches_the_highest_version_
     section` goes red the moment I add `## v0.38` and stays red until I
     bump the header line. It is the one pin I will fix without measuring,
     because it exists to be fixed.

## The runs

P14. whence fast tier before the change: 1872 passed, 3 skipped,
     81 deselected (round 402's number, unchanged since — round 403 only
     touched `harness/` and one `test_v24.py` pin, and that pin was in the
     SLOW tier, so the fast-tier number should be exactly 1872).
     I predict this is WRONG by a small amount and that round 403's
     `test_v24.py` fix moved it.

P15. The full whence tier, run in the live tree at the END with edits
     complete: ~19:25 +/- 3 min if the box is quiet, and I predict
     `procreap scan` finds ZERO orphans at the start of this round.

P16. Total new tests in `tests/test_v38.py`: 12-18.
