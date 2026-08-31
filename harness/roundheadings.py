#!/usr/bin/env python3
"""roundheadings.py — ONE definition of "a round entry heading" in the
cumulative record (`state/research-state.md` and its archive).

Round 397 (harness A). Why this module exists:

`state/research-state.md` is the program's cumulative memory, and four
independent tools in this repo parse its `Round N` headings to decide what
the record says. Each one grew its own regex, and as of round 397 no two of
them accepted the same set of headings:

    parser                                pattern                      r396  r302  range
    check_round_recorded.STATE_ENTRY_RE   ^### Round (\\d+) [—-]        BLIND BLIND BLIND
    carryforward_check._HEADING_RE        ^###\\s+Round\\s+(\\d{1,4})\\b   BLIND  ok   BLIND
    swe.toolliveness._STATE_HEAD          ^#{2,3} Round (\\d+)\\b          ok    ok   BLIND
    state_claim_check block-stop          ^#{1,3}\\s                       ok    ok    ok

Nothing on the WRITING side enforces any of them. CLAUDE.md ground rule 4
and the driver prompt both say only "append a round entry"; the canonical
`### Round N — <track> — <date>` shape is a convention that lives nowhere
except inside these regexes. So a round can write a legal, human-legible
entry and have it be simultaneously visible to one tool and invisible to
three — with no error anywhere.

That is not hypothetical. It has fired twice, 94 rounds apart, both times
producing a FALSE "round N was never recorded" gap report:

  * Round 302's entry was written by round 303 as
    `### Round 302 (language C) — Whence v0.14.10 — 2026-08-29`
    (commit `1979708`, 2026-08-29 03:46:34). Round 303's own pre-round
    record check had already flagged 302 (driver.log, 03:44:55). Nine
    minutes later, commit `b2e5425` ("close round 302's record gap")
    rewrote that heading to `### Round 302 — language(C) — 2026-08-29`.
    The DOCUMENT was edited to satisfy the REGEX; no round ever recorded
    that the regex was the thing that was wrong.
  * Round 396's entry is `## Round 396 (language C) — v0.35, decision 44:
    ...`. The same detector flagged it as an unrecorded gap, and that false
    gap became the entire record-gap NOTE injected into round 397's prompt.

The fix for a format contract that nothing enforces is not a stricter
writer — it is a reader that accepts what a reasonable writer produces, and
that SAYS SO when the form drifts. This module is that reader.

Recognised forms (all levels `##` through `#####`):

    ### Round 395 — SWE-loop(D) — 2026-08-31      canonical
    ## Round 396 (language C) — v0.35, ...        non-canonical, recognised
    #### Round 12 detail                          non-canonical, recognised
    ### Rounds 114-126 — driver-level, ...        span heading, recognised

Deliberately NOT recognised:

    ## Round log                          no number follows "Round"
    ## Round log (rounds 1-136)           ditto; the span form requires the
                                          plural "Rounds" to lead the heading
    ### Round 400 — 2026-09-01            read as round 400, NOT the span
                                          400-2026: only the PLURAL "Rounds"
                                          opens a span, so a date directly
                                          after the em dash cannot be
                                          misread as a range endpoint

A span wider than `MAX_SPAN_WIDTH` rounds is refused rather than expanded,
so a hypothetical `### Rounds 1-400 — summary` cannot silently mark four
hundred rounds "recorded" and mask every real gap under it.
"""

import re
import sys

__all__ = [
    "CANONICAL_FORM", "MAX_SPAN_WIDTH", "Heading",
    "SINGLE_RE", "SPAN_RE", "CANONICAL_RE",
    "parse_heading", "headings", "heading_rounds", "nonstandard_headings",
]

CANONICAL_FORM = "### Round N — <track> — <date>"

# A span heading wider than this is refused (see module docstring).
MAX_SPAN_WIDTH = 64

# Levels 2-5. Level 1 is the document title (`# Research State`), never a
# round entry, and admitting it would let a stray `# Round 5` in some other
# document count.
_LEVEL = r"(#{2,5})"

# Singular "Round" + a number. `Round[ \t]+\d` is what keeps `## Round log`
# out: "log" is not a digit.
SINGLE_RE = re.compile(_LEVEL + r"[ \t]*Round[ \t]+(\d{1,4})(?![\d.])")

# Plural "Rounds A-B". Requiring the plural is what makes the span form
# unambiguous against `### Round 400 — 2026-09-01`.
SPAN_RE = re.compile(
    _LEVEL + r"[ \t]*Rounds[ \t]+(\d{1,4})[ \t]*[-‒–—][ \t]*"
    r"(\d{1,4})(?![\d.])")

# The historical shape every one of these tools was written against, kept
# so drift can be REPORTED rather than silently normalised away.
CANONICAL_RE = re.compile(r"### Round (\d{1,4}) [—-]")


class Heading(object):
    """One recognised round-entry heading.

    `rounds` is a tuple of every round number the heading accounts for — one
    element for the singular form, `hi - lo + 1` for a span.
    """

    __slots__ = ("text", "level", "rounds", "is_span", "canonical",
                 "path", "line")

    def __init__(self, text, level, rounds, is_span, canonical,
                 path=None, line=None):
        self.text = text
        self.level = level
        self.rounds = tuple(rounds)
        self.is_span = is_span
        self.canonical = canonical
        self.path = path
        self.line = line

    def __repr__(self):
        return ("Heading(rounds=%r, level=%d, span=%r, canonical=%r, %s:%s)"
                % (self.rounds, self.level, self.is_span, self.canonical,
                   self.path, self.line))

    def __eq__(self, other):
        if not isinstance(other, Heading):
            return NotImplemented
        return (self.text, self.level, self.rounds, self.is_span,
                self.canonical) == (other.text, other.level, other.rounds,
                                     other.is_span, other.canonical)

    def as_dict(self):
        return {"text": self.text, "level": self.level,
                "rounds": list(self.rounds), "is_span": self.is_span,
                "canonical": self.canonical, "path": self.path,
                "line": self.line}


def parse_heading(line, path=None, lineno=None):
    """Parse one line. Returns a `Heading`, or None if it is not one.

    A span whose width exceeds `MAX_SPAN_WIDTH`, or whose endpoints run
    backwards, is not a heading — returning None is deliberate: a bogus span
    must not be able to claim rounds it has no business claiming.
    """
    line = line.rstrip("\n")
    m = SPAN_RE.match(line)
    if m:
        lo, hi = int(m.group(2)), int(m.group(3))
        if hi < lo or (hi - lo + 1) > MAX_SPAN_WIDTH:
            return None
        return Heading(line, len(m.group(1)), range(lo, hi + 1), True,
                       False, path, lineno)
    m = SINGLE_RE.match(line)
    if m:
        n = int(m.group(2))
        return Heading(line, len(m.group(1)), (n,), False,
                       CANONICAL_RE.match(line) is not None, path, lineno)
    return None


def headings(text, path=None):
    """Every recognised round heading in `text`, in file order."""
    out = []
    for i, line in enumerate(text.split("\n"), start=1):
        h = parse_heading(line, path, i)
        if h is not None:
            out.append(h)
    return out


def heading_rounds(text):
    """The set of round numbers `text`'s headings account for."""
    out = set()
    for h in headings(text):
        out.update(h.rounds)
    return out


def nonstandard_headings(text, path=None, only_rounds=None):
    """Recognised headings that are NOT in `CANONICAL_FORM`.

    These are not gaps — the round IS recorded. They are reported so format
    drift is visible to the next round instead of being discovered by a
    stricter tool as a phantom missing entry (which is what rounds 303 and
    397 each spent part of a round on).

    `only_rounds`, when given, restricts the report to headings accounting
    for at least one round in that set. Callers pass the rounds they
    actually adjudicate, so an archive's historical span headings — real,
    correct, and permanently non-canonical — do not print on every run
    forever. A permanent unactionable warning is the exact noise the
    escalation registry (round 373) was invented to stop reproducing.
    """
    out = []
    for h in headings(text, path):
        if h.canonical:
            continue
        if only_rounds is not None and not (set(h.rounds) & set(only_rounds)):
            continue
        out.append(h)
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: python3 -m harness.roundheadings FILE [FILE ...]",
              file=sys.stderr)
        return 2
    rc = 0
    for path in argv:
        try:
            with open(path) as f:
                text = f.read()
        except OSError as exc:
            print("%s: %s" % (path, exc), file=sys.stderr)
            rc = 2
            continue
        hs = headings(text, path)
        rounds = set()
        for h in hs:
            rounds.update(h.rounds)
        nonstd = [h for h in hs if not h.canonical]
        print("%s: %d heading(s), %d round(s), %d non-canonical"
              % (path, len(hs), len(rounds), len(nonstd)))
        for h in nonstd:
            print("  %s:%d  %s" % (path, h.line, h.text))
    return rc


if __name__ == "__main__":
    sys.exit(main())
