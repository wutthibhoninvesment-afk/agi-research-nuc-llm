#!/usr/bin/env python3
"""carryforward_check.py — an obligation with a FILE ON DISK that no round
ever discharged.

Why this exists
---------------
Round 365 opened its next-steps list with an item it ranked above everything
else, owned by "harness(A) or skills(B)", and four rounds went by:

    when a round is interrupted and a later round reconciles its CODE,
    reconcile its CONCLUSIONS too. […] `check_round_recorded.py` checks
    whether a round LANDED; nothing checks whether its findings reached the
    next-steps list.

"Findings" in general is not mechanizable — it is a judgement about prose.
But the class has one sub-shape that is entirely mechanical, and it is the
sub-shape that actually bit this program, five times:

    round 23   `state/round-023-predictions.md`. P1-P6 "roll to next D round
               (29)"; round 29 scored its own and round 101's, never round
               23's. Rolled forward once and dropped.
    round 132  `state/round-132-predictions.md`, banked, no knowledge file.
    round 145  P1-P5 unscored for THIRTY rounds (research-state.md line 67).
               Eventually discharged.
    round 362  `state/whence/round-362/PREDICTIONS.md`, killed by the outer
               timeout. Round 363 recorded the debt in round 362's entry and
               called it "carried as a next step for language(C)". It appears
               in NO subsequent next-steps block (364, 365, 367) and two
               language(C) rounds (366, 368) ran without touching it.
    round 368  `state/whence/round-368/PREDICTIONS.md`, 9 predictions, killed
               at 2765 s. Round 369 landed its code and did not score it.

A PREDICTIONS bank is the right anchor for this class because the obligation
is not a matter of interpretation: **CLAUDE.md rule D-013 is banked policy** —
"write PREDICTIONS before measuring, then score misses honestly" — so a bank
with no scoring is an unmet, named, dated obligation with a path.

A DECLARED ledger, not a prose classifier
-----------------------------------------
The first version of this file inferred "was this scored?" by pattern-
matching research-state.md and `knowledge/`. Hand-checking its 13 findings
against the corpus found 5 of them wrong, in both directions, from four
independent causes:

  * round 366 scored its bank as "P4/P5/P6 hit" and a case-sensitive
    `HIT|MISS` called it unscored.
  * round 141 discharged three inherited banks in ONE sentence — "round 123
    3 HIT/1 MISS; round 129 8 HIT/…; round 135 6 HIT/…" — which no
    possessive-form pattern reaches.
  * round 145's section quotes round 139's scoring, and round 349's quotes
    round 352's, so a round's own section is not evidence about that round.
  * round 139's discharge line scores four predictions and calls a fifth
    "unscorable" — one negation word vetoing four real verdicts.

Every one of those was fixable, and fixing them one at a time is exactly the
over-fitting this corpus warns about. The structural answer is the idiom the
repo already uses for every other unenumerable obligation —
`known-standing-dirty-paths.json`, `known-record-gaps.json`,
`known-unprobed-skills.json`: **stop inferring, and make the corpus
declare.** `state/prediction-bank-ledger.json` records, per bank, where it
was scored and the sentence that did it.

The prose scanner is kept, demoted to `--suggest`: it proposes ledger entries
for banks that have none, and it is the ROT detector for entries claiming
`unscored`. It is never the authority.

The ledger is RE-DERIVED, not trusted. `claim_check.py` (round 339) and
`state_claim_check.py` (round 351) both exist because a written claim nobody
re-executes goes stale silently; a ledger of scorings is a document of
exactly that kind. So every `scored` entry names a file and a quote, and
K002 re-reads the file.

Findings
--------
`K001` (ERROR)  a bank on disk with NO ledger entry. The round that banked it
                owes the entry; nobody else knows what it predicted.
`K002` (ERROR)  a ledger entry claiming `scored` whose quote is no longer at
                the cited path — the claim cannot be re-derived.
`K003` (ERROR)  ledger rot: an entry naming a bank that does not exist, an
                entry missing a required field, or an `unscored` entry the
                scanner now finds scoring evidence for. Same rule as
                `case_coverage.py`'s P005 — an acknowledgement that outlives
                its debt is a mute button.
`K005` (ERROR)  a `scored` entry whose quote occurs MORE THAN ONCE in the
                file `where` names. Present twice is not located once: a
                re-derivation cannot say which occurrence is the scoring
                line, so the entry cannot be checked, only matched.
`K006` (ERROR)  a `scored` entry whose quote ALSO satisfies K002 against a
                round scope the entry has nothing to do with — the anchor
                does not locate, see below.
`K004` (WARN)   an `unscored` entry owed for a full rotation (6 rounds) or
                more, or a `scored` entry with a `remainder` — predictions
                the discharge left out. Never sets the exit code: round
                363's rule, that a check which goes FAIL for a debt the
                program decided to carry gets ignored and then uninstalled.
                The count rides in the summary line, which is the line the
                driver logs.

Matching is not locating (round 465)
------------------------------------
K002 asks `quote in body`. A substring that is PRESENT proves the sentence
exists in that file; it does not prove the file is where the scoring
happened. The property the ledger actually needs is that the anchor can
FAIL when the coordinate is wrong — so the test is a SUBSTITUTION on the
`where` field, not a judgement about the quote's prose:

    would K002 still pass if `where` named some OTHER round's artefact?

If yes, the entry could have mis-named its file and nothing here would say
so. That is not hypothetical: round 464 found round 462's entry quoting
`state/research-state.md`'s wording while naming the knowledge file, and
K002 caught it ONLY because that exact sentence was absent from the
knowledge file. Had the quote been `## 8. Predictions, scored` — which nine
other rounds' files also carry — the wrong `where` would have passed.

The candidate coordinates are ROUND SCOPES, not files: each
`knowledge/round-NNN-*.md`, and each round's own section of
research-state(+archive). File-level substitution would be meaningless for
the 18 entries whose `where` IS `state/research-state.md` or its archive —
those files contain every round, so every quote in the corpus "appears" in
them. The unit has to be the smallest thing the coordinate identifies.

Priced before shipping, over the 139 scored entries at round 465's HEAD:

    quote absent from `where`   (K002, live rule)      0
    quote occurs 2+ times       (K005)                 1   round 421
    quote passes a FOREIGN scope (K006)                6   15, 369, 371,
                                                           378, 419, 421
    quote shorter than 40 chars (the proxy)           53

Those are the numbers BEFORE the repair. Re-running `--audit-quotes` now
reports 0/0/0 and **47** short, because six of the six repairs replaced a
short anchor with a longer slice — the proxy's own count moved as a side
effect of fixing something the proxy was not measuring.

Round 464's next step proposed a minimum LENGTH for the second shape. The
pricing says length is the wrong instrument: it reports 53 entries to reach
6, and at HEAD every one of the 6 is short — so the floor is 8.8x
false-positive inflation buying no extra recall. All six were repairable by
quoting a stronger sentence out of the same file, so both codes ship as
ERRORs against a backlog of zero rather than as warnings against a backlog
nobody would clear (round 363's rule cuts the other way when the debt is
six entries and an afternoon).

Three of the six are section headings (`## 8. Predictions, scored` and
friends) matched in 11, 9 and 1 foreign scopes — generic by construction.
The other three are scoring tallies matched in exactly ONE foreign scope
each, and two of those foreign scopes are round 464's own knowledge file,
which quoted them WHILE DIAGNOSING THIS DEFECT. Writing about a weak anchor
weakens it. That is not a flaw in the rule — a file carrying the exact
sentence really is a file the entry could have mis-named — but it means the
repair is to make the quote MORE SPECIFIC, never to widen the rule, and it
means prose about this checker should paste OLD quotes, not live ones.

`remainder` vs `note` (round 375)
---------------------------------
`remainder` means OUTSTANDING PREDICTIONS and nothing else, and K004 reads
its PRESENCE. Two entries used it for narrative instead — rounds 373 and
374, whose remainders both open with the words "None outstanding" — so the
check reported two partial discharges that the record itself denies, 2 of
the 11 warnings in the count the driver logs.

The fix is a second field, `note`, for prose that is not a debt; it is NOT
a scan for "None outstanding". Round 369 built this ledger precisely
because a prose classifier got 5 of 13 verdicts wrong in both directions,
and its conclusion was *stop inferring, make the corpus declare*. A regex
that decides whether a `remainder` really means debt would re-introduce
the thing the ledger replaced.

The same reasoning is why there is no check that a `remainder`-free
discharge actually names every `Pn` in its bank, which is the guard that
would make `note` safe against misuse. Scoring sections across 50 banks
use at least four incompatible idioms (`| P1 | … | **HIT** |`,
`**P1 MISS**`, `P4/P5/P6 hit`, one sentence discharging three banks), and
a scanner over them would be exactly round 369's 5-of-13 classifier
wearing a different hat. The honest position: `note` is a DECLARATION, its
accuracy rests on the round that writes it, and the reviewable artifact is
that both fields are visible side by side in one file.

Usage:
    python3 carryforward_check.py [--repo-root DIR]
    python3 carryforward_check.py --list          # the whole ledger
    python3 carryforward_check.py --suggest       # propose missing entries
    python3 carryforward_check.py --json OUT
Exit: 0 = no ERRORs, 1 = at least one ERROR, 2 = usage/IO problem.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))

if DEFAULT_REPO_ROOT not in sys.path:
    sys.path.insert(0, DEFAULT_REPO_ROOT)
try:
    from harness import roundheadings as _roundheadings
except ImportError:
    # Same promoted-copy case `check_round_recorded` documents: this skill
    # may be copied somewhere without the harness/ package. The fallback
    # below keeps `_HEADING_RE` for section KEYS — which is the pattern that
    # produced round 302's and round 396's false gaps, so it degrades into a
    # wrong answer, not a missing column — but keeps the level-based section
    # BOUNDARY, which needs nothing from harness.
    _roundheadings = None

LEDGER_FILE = os.path.join("state", "prediction-bank-ledger.json")

# One full track rotation (CLAUDE.md ground rule 6 is mod 6). A debt younger
# than this has not yet had a turn of its owning track come round.
ROTATION = 6

REQUIRED_SCORED = ("bank", "status", "scored_by", "where", "quote")
REQUIRED_UNSCORED = ("bank", "status", "owner", "why")

# --------------------------------------------------------------------------
# Bank discovery — a REPO-WIDE FILENAME SWEEP, not a list of known locations,
# and that is the most important design decision in this file.
#
# The first draft enumerated four globs under `state/` — the four conventions
# visible from `state/` — and silently missed `nuc/predictions-e-round358.md`,
# the NUC-integration(E) track's own convention, which made rounds 340, 352,
# 358 and 364 read as having no bank at all. An obligation NOBODY REGISTERED
# cannot be enumerated from a list of the places you already know about; that
# is the same reasoning error the obligation itself is made of.
#
# Six conventions are live at round 369:
#   state/round-NNN-predictions.md              (rounds 17-145, 345, 346, 363)
#   state/<track>/round-NNN/PREDICTIONS.md      (harness/swe/whence/skills)
#   state/trigger-eval/round-NNN-predictions.md (gitignored, see below)
#   nuc/predictions-e-roundNNN.md               (NUC-integration E)
#   nuc/predictions-eN.md                       (mission-scoped, NO round)
#   state/round-NNN/PREDICTIONS.md              (accepted, none on disk yet)
#
# Reading the WORKTREE and not `git ls-files` is deliberate:
# `state/trigger-eval/` is gitignored, and the obligation belongs to the
# ROUND, not to the file's tracked-ness.
# --------------------------------------------------------------------------
BANK_NAME_RE = re.compile(r"prediction", re.IGNORECASE)
# ROUND 513. The sweep above was made repo-wide because enumerating the
# DIRECTORIES you already know about cannot find an obligation nobody
# registered. It kept enumerating the EXTENSIONS: `.md`, and every one of the
# six conventions listed above is `.md`. Round 512 banked in
# `state/whence/round-512/predictions.json` -- a seventh convention -- so
# `find_banks` returned nothing for round 512, and K003 reported the entry as
# naming "nothing" while the file it names sat on disk. Same reasoning error,
# one attribute down.
BANK_SUFFIXES = (".md", ".json")
BANK_ROUND_RE = re.compile(r"round[-_ ]?(\d{1,4})", re.IGNORECASE)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "research-env",
             "__pycache__", "site-packages", ".mypy_cache", ".pytest_cache",
             "whence_lang.egg-info"}
# Not every prediction-shaped filename is a bank. `knowledge/round-187-…-
# prediction-partial-score.md` is a knowledge FILE about scoring, and reading
# it as a bank would invent an obligation nobody took on.
SKIP_TOP = {"knowledge"}


def find_banks(root):
    """({round: [rel path, …]}, [rel path with no round number, …]).

    Unnumbered banks are returned separately rather than dropped: they are
    real D-013 artifacts (`nuc/predictions-e1.md` is mission-scoped, not
    round-scoped) and this checker cannot tie them to a round, so it says so
    instead of pretending they do not exist.
    """
    banks, unnumbered = {}, []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir.split(os.sep)[0] in SKIP_TOP:
            dirnames[:] = []
            continue
        for name in filenames:
            if not name.endswith(BANK_SUFFIXES) or not BANK_NAME_RE.search(name):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, name))
            # The LEDGER is the register of banks, not a bank. Its name
            # matches `prediction` and it is now an admitted suffix, so it
            # has to be named out explicitly -- otherwise widening the sweep
            # invents one unnumbered obligation out of the file that tracks
            # them.
            if rel == LEDGER_FILE:
                continue
            # The round number lives in the FILENAME for three conventions and
            # in the DIRECTORY for two, so match the whole relative path.
            m = BANK_ROUND_RE.search(rel)
            if m:
                banks.setdefault(int(m.group(1)), []).append(rel)
            else:
                unnumbered.append(rel)
    for n in banks:
        banks[n].sort()
    return banks, sorted(unnumbered)


# --------------------------------------------------------------------------
# The prose scanner. NOT the authority — see the module docstring. It powers
# `--suggest` and it is the rot detector for `unscored` ledger entries.
#
# Every pattern was taken from text this corpus actually contains (a
# frequency count over research-state.md + knowledge/ at round 369), not
# invented.
# --------------------------------------------------------------------------
SCORE_PATTERNS = (
    # Case-INSENSITIVE on the verdict word, anchored on an uppercase `P<n>`.
    # Round 366 scored its bank as "P4/P5/P6 hit" and a case-sensitive
    # `HIT|MISS` read that as an unscored bank.
    ("pn_verdict", re.compile(r"\bP\d{1,2}\b[^\n]{0,80}?\b(HIT|MISS)\b",
                              re.IGNORECASE)),
    ("tally", re.compile(
        r"\b\d{1,2}\s+HITs?\b[^\n]{0,14}?\b\d{1,2}\s+MISS(?:ES)?\b",
        re.IGNORECASE)),
    ("outcome_table", re.compile(r"\|\s*outcome\s*\|", re.IGNORECASE)),
    ("scored_phrase", re.compile(
        r"\b(?:predictions?\s+scored|scored[^\n]{0,60}?predictions?|"
        r"predictions?[^\n]{0,60}?\bscored\b)\b", re.IGNORECASE)),
)

# A sentence using the scoring vocabulary to say scoring did NOT happen. This
# corpus does that on purpose and often — it is how a round records an
# inherited debt — so without this the scanner reads its own bug reports as
# evidence the bug was fixed.
NEGATION_RE = re.compile(
    r"\b(never\s+scored|never\s+got\s+scored|not\s+scored|unscored|"
    r"unscorable|without\s+scoring|no\s+scoring|before\s+scoring|"
    r"died\s+before[^\n]{0,30}scor|nobody\s+scored|left\s+unscored)\b",
    re.IGNORECASE)

# A POINTER to a scoring is not a scoring. `NEGATION_RE` gives this scanner a
# vocabulary for "was NOT scored"; it had none for "is scored OVER THERE",
# and the two fail in opposite directions. Round 492's knowledge file opens
# with
#
#     (`state/whence/round-492/predictions.md`). Scored in §10.
#
# and then ends at `## 9. Tests and gates`. There is no §10, no HIT and no
# MISS anywhere in the file, and no later round scored the bank. The
# `scored_phrase` pattern matched the promise, `_names_round` was satisfied
# by the bank path on the same line, and `--suggest` duly proposed a
# `"status": "scored"` ledger entry quoting the sentence that promises the
# section that was never written (round 495). Accepting that proposal would
# have closed K001 for round 492 while D-013's second half stayed undone —
# the ledger laundering the debt it exists to expose.
#
# So: a scoring-shaped line that cites a LOCATION and carries no verdict of
# its own is evidence only if the location resolves.
POINTER_RE = re.compile(
    r"\b(?:scored|scoring|see|below|above)\b[^\n]{0,30}?"
    r"(?:§\s*(\d{1,3})\b|\bsection\s+(\d{1,3})\b)",
    re.IGNORECASE)

# A verdict ON the line settles it: whatever else the line says, a line that
# reports an outcome IS a scoring. Round 490's tally line is
# `**13 HIT / 1 MISS / 2 OPEN-KEPT of 15** (P14 in §10).` — a real scoring
# that also happens to point at a section. Without this guard the pointer
# rule would throw away a scoring for mentioning where the rest of it is.
VERDICT_ON_LINE_RE = re.compile(
    r"\b(HIT|MISS(?:ES)?|PARTIAL|HALF|KEPT|VOID|KEPT\+HIT)\b")


def unkept_pointer(line, text):
    """The section number `line` points at, when `text` has no such heading.

    None — meaning "do not veto this candidate" — if the line carries its own
    verdict, is not a pointer at all, or points somewhere that resolves.

    Resolution is against the TEXT the candidate came from, not against a
    named file, because that is all `score_evidence` is given. The bias is
    deliberate and it is the safe one: a heading that resolves by accident
    (a `## 10.` belonging to some other document inside a wide
    `cross_round_scope` paragraph join) merely restores the pre-495
    behaviour of accepting the pointer, whereas resolving too strictly would
    discard real scorings. A false ACCEPT costs nothing that was not already
    being paid; a false REJECT would lose evidence.
    """
    if VERDICT_ON_LINE_RE.search(line):
        return None
    m = POINTER_RE.search(line)
    if not m:
        return None
    num = m.group(1) or m.group(2)
    if re.search(r"^#{1,6}\s+%s[.)\s]" % re.escape(num), text, re.MULTILINE):
        return None
    return num


# The negation window is a CHARACTER span around the match, not the whole
# line. Round 139's discharge line scores four predictions HIT and calls a
# fifth "still unscorable" 250 characters later; a whole-line veto threw away
# four real verdicts for one word about a different prediction.
NEG_WINDOW = 150

# A round's own section routinely quotes ANOTHER round's scoring — "Round
# 352's P14 is heading for a MISS", "Scored `state/round-139-predictions.md`
# …". Only an ATTRIBUTIVE reference (a possessive over a prediction, or a
# bank path) actually credits the verdict to that round; a bare mention does
# not, and rejecting on bare mentions threw away real table rows.
# ROUND 489 widened the possessive alternative. It required the noun after
# `round NNN's` to be `P<n>` or `prediction`, so
#
#     "author); round 473's 17-row bank, scored **10 HIT / 6 MISS / 1"
#
# — the FIRST scoring-shaped line in round 479's own scope — read as
# UNATTRIBUTED, and `scan` handed it to K003 as evidence that round 479's
# own bank had been scored. K003's verdict was right (round 485 did score
# it, in a different file) and its evidence was about a different round
# entirely. Two qualifier words and a synonym were the whole gap: this
# corpus writes "round N's 17-row bank" as readily as "round N's
# predictions". Up to three qualifier tokens are allowed before the noun,
# and `bank` is a noun.
FOREIGN_ATTRIB_RE = re.compile(
    r"round[-\s]?0*(\d{1,4})(?:'|’)s\s+(?:\*\*)?"
    r"(?:[\w.%-]+\s+){0,3}(?:P\d|predictions?\b|bank\b)"
    r"|round-0*(\d{1,4})-predictions"
    r"|round-0*(\d{1,4})/PREDICTIONS"
    r"|predictions-e-round0*(\d{1,4})",
    re.IGNORECASE)

# Deliberately WIDER than FOREIGN_ATTRIB_RE: every round number a line
# mentions, however it mentions it. The audit (`--audit-evidence`) uses this
# and the attribution filter uses that, because an evidence auditor that
# shares its detector's filter can only ever agree with it — round 489's
# finding, and the same shape as `skills/suppressor-shares-the-detector-shape`.
_ROUND_MENTION_RE = re.compile(r"round[-\s]?0*(\d{1,4})\b", re.IGNORECASE)


def credited_rounds(line):
    """Rounds `line` ATTRIBUTES its verdict to (possessive or bank path)."""
    return {int(next(g for g in m.groups() if g))
            for m in FOREIGN_ATTRIB_RE.finditer(line)}


def mentioned_rounds(line):
    """Every round `line` names at all. A superset of `credited_rounds`."""
    return {int(m.group(1)) for m in _ROUND_MENTION_RE.finditer(line)}


def _attributable(line, n):
    """False if `line` credits its verdict to a round other than `n`."""
    named = credited_rounds(line)
    return not named or n in named


# In a markdown scoring table the FIRST cell is the subject and the verdict
# is the object: `| P7 | <what was predicted> | **HIT** |`. The subject is a
# prediction id, and a prediction id belongs to whoever owns the TABLE — a
# fact the row itself never states. So a round number appearing in a
# DESCRIPTION cell is being talked about, not scored.
#
# `cross_round_scope` joins paragraphs from every prose file and throws the
# document coordinate away, so by the time a line reaches `_names_round` there
# is nothing left that could say which round's table it came out of. Round
# 495 hit this the moment the pointer rule above stopped masking it:
# round 493's own §8 row
#
#     | P7 | the five census reds are round 492's own artefacts in the corpus | **HIT** … |
#
# is round 493 scoring round 493's P7, and `scan` offered it as proof that
# round 492's bank had been scored. `credited_rounds` does not catch it —
# round 489 widened that regex to `round N's <up to 3 qualifiers> P<n>/
# predictions/bank` and the noun here is `artefacts`.
#
# Every one of the six rows this vetoes corpus-wide (rounds 23, 125, 137,
# 340, 401, 492 — checked by hand at round 495, the whole population whose
# ONLY evidence is the cross-round path AND a table row) is that same shape.
#
# The veto's direction is the fail-safe one for a DEBT tracker: vetoing can
# only make `scan` find LESS evidence, so an `unscored` entry stays
# `unscored` and the debt stays visible. The error it prevents — K003
# declaring a debt already discharged on a row about somebody else — deletes
# the debt silently.
_TABLE_ROW_PID_RE = re.compile(r"^\s*\|\s*\*{0,2}(P\d{1,2}[a-z]?)\*{0,2}\s*\|")


def row_subject_is_a_pid(line):
    """True if `line` is a table row whose FIRST cell is a prediction id."""
    return bool(_TABLE_ROW_PID_RE.match(line))


def _names_round(line, n, bank_paths):
    """True if `line` itself names round `n` (or one of its banks).

    Cross-round evidence needs this. The paragraph filter has to be WIDE —
    round 141 discharged three inherited banks in one sentence, which no
    possessive-only pattern reaches — and a wide paragraph filter is only
    safe if the LINE carrying the verdict is the line naming the round.
    """
    if any(bp in line for bp in bank_paths):
        return True
    return re.search(r"round[-\s]?0*%d\b" % n, line, re.IGNORECASE) is not None


def raw_candidates(text):
    """(kind, line, negated) for EVERY scoring-shaped match in `text`.

    Split out of `score_evidence` (round 489) for one reason: a detector
    that returns the first surviving match reports a verdict AND an
    evidence line, and nothing could see the candidates it skipped or the
    filter that skipped them. `--audit-evidence` reads this.
    """
    for kind, pat in SCORE_PATTERNS:
        for m in pat.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            end = line_end if line_end != -1 else len(text)
            negated = bool(NEGATION_RE.search(
                text[max(0, m.start() - NEG_WINDOW):m.end() + NEG_WINDOW]))
            yield kind, text[line_start:end], negated


def score_evidence(text, n=None, require_named=None):
    """(kind, matched_line) for the strongest scoring signal, else None."""
    for kind, line, negated in raw_candidates(text):
        if negated:
            continue
        if unkept_pointer(line, text):
            continue
        if n is not None and not _attributable(line, n):
            continue
        if require_named is not None:
            # CROSS-ROUND path only. A round's own table row IS its own
            # scoring, so this veto must never reach `own_scope`.
            if row_subject_is_a_pid(line):
                continue
            if not _names_round(line, n, require_named):
                continue
        return kind, line.strip()[:200]
    return None


# The historical, strict pattern. Round 449 demoted it from "the definition
# of a round entry" to the fallback used only when harness/ is not
# importable, for the reason `harness/roundheadings.py` gives: it rejects
# legal entries. Kept as a name because the tests pin what it does and does
# not match.
_HEADING_RE = re.compile(r"^###\s+Round\s+(\d{1,4})\b", re.MULTILINE)

_ANY_HEADING_RE = re.compile(r"^(#{1,6})\s")


def _marks(text):
    """(line_index, level, round_or_None, is_span) for every md heading.

    `round_or_None` is the round a SINGULAR heading opens a section for.
    Span headings (`### Rounds 114-126 — did not run`) are boundaries but
    not keys: assigning one block of prose to thirteen rounds would make
    each of them look like it had an entry of its own.
    """
    out = []
    for i, line in enumerate(text.splitlines(keepends=True)):
        m = _ANY_HEADING_RE.match(line)
        if not m:
            continue
        level, raw = len(m.group(1)), line.rstrip("\n")
        if _roundheadings is None:
            hit = _HEADING_RE.match(raw)
            out.append((i, level, int(hit.group(1)) if hit else None, False))
        else:
            h = _roundheadings.parse_heading(raw)
            out.append((i, level,
                        None if h is None or h.is_span else h.rounds[0],
                        bool(h is not None and h.is_span)))
    return out


def round_sections(text):
    """{round: the prose that round's own entry owns}.

    A round number can head more than one section across the two prose files
    (a reconciling round amends an earlier entry); sections are concatenated
    rather than overwritten so no evidence is lost.

    Round 449 (SWE-loop D) changed two things here, both measured against
    the live record before and after:

    1. **Which headings open a section** — `harness.roundheadings`, not this
       module's own `^###\\s+Round\\s+N` regex. That regex was one of the
       four independent heading parsers round 397 catalogued, and the only
       one still carrying its own pattern 52 rounds later. It is blind to
       `## Round 448 (NUC-integration E) — …`, the shape round 448 actually
       wrote, and to the archive's four span headings. Live cost measured at
       round 449's HEAD: 22 rounds across the two prose files had no section
       at all (448 plus 21 archived rounds), and round 448's entry was not
       dropped but ABSORBED — its whole 138-line entry was served as part of
       round 447's `own_scope`.

    2. **Where a section ENDS** — at the next heading of level <= this
       heading's own, not at the next ROUND heading. `## Next steps (as of
       round N)` is not a round heading, so under the old rule every round
       entry that preceded a next-steps stack swallowed the whole stack.
       Measured at the same HEAD: **67 of 260** live sections (26%) carried
       a foreign level-<=3 heading, 135 next-steps blocks were attributed to
       a round that did not write them, round 388's section swallowed 22
       headings, and **26.7%** of all the text this function attributed to
       some round belonged to another one.

    The two defects are wildly different sizes and the SMALL one is the one
    that changed an answer: correcting the boundary alone moved 488 KB of
    prose and flipped zero verdicts, while correcting the drift alone moved
    no text at all and flipped exactly one (round 448's own scoring, which
    `--suggest` would otherwise have proposed as `unscored`). Extent is not
    impact; both numbers are in `state/swe/round-449/`.
    """
    lines = text.splitlines(keepends=True)
    marks = _marks(text)
    out = {}
    for j, (i, level, n, _span) in enumerate(marks):
        if n is None:
            continue
        end = len(lines)
        for k in range(j + 1, len(marks)):
            if marks[k][1] <= level:
                end = marks[k][0]
                break
        out[n] = out.get(n, "") + "".join(lines[i:end])
    return out


def read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


class Corpus(object):
    """The prose a scoring can live in, read once."""

    PROSE = (os.path.join("state", "research-state.md"),
             os.path.join("state", "research-state-archive.md"))

    def __init__(self, root):
        self.root = root
        self.sections = {}
        for rel in self.PROSE:
            for n, sec in round_sections(read(os.path.join(root, rel))).items():
                self.sections[n] = self.sections.get(n, "") + sec
        self.knowledge = {}
        for name in sorted(os.listdir(os.path.join(root, "knowledge"))
                           if os.path.isdir(os.path.join(root, "knowledge"))
                           else []):
            m = BANK_ROUND_RE.match(name)
            if m and name.endswith(".md"):
                self.knowledge.setdefault(int(m.group(1)), []).append(
                    os.path.join("knowledge", name))
        self._scopes = None
        self.all_prose = "\n".join(
            [read(os.path.join(root, p)) for p in self.PROSE]
            + [read(os.path.join(root, p))
               for paths in self.knowledge.values() for p in paths])

    def round_scopes(self):
        """[(round, coordinate label, text)] — every text a `where` could
        name, attributed to the round that owns it.

        This is the candidate set for the K006 substitution: one entry per
        thing a ledger coordinate can point AT. A knowledge file is owned by
        the round in its filename; a research-state section is owned by the
        round whose heading opens it (`round_sections`, which round 449
        taught to end a section at the next heading of level <= its own, so
        a next-steps stack is not attributed to the round above it).

        Cached: `findings` walks it once per scored entry.
        """
        if self._scopes is None:
            out = []
            for n, paths in sorted(self.knowledge.items()):
                for rel in paths:
                    out.append((n, rel, read(os.path.join(self.root, rel))))
            for n, sec in sorted(self.sections.items()):
                out.append((n, "%s §round %d" % (self.PROSE[0], n), sec))
            self._scopes = out
        return self._scopes

    def foreign_scopes(self, quote, own):
        """Coordinates OUTSIDE `own` whose text also satisfies K002.

        Each one is a `where` the entry could have carried instead without
        this checker noticing — which is the whole question K002 does not
        ask.
        """
        return [label for n, label, text in self.round_scopes()
                if n not in own and quote in text]

    def own_scope(self, n):
        parts = []
        if n in self.sections:
            parts.append(self.sections[n])
        for rel in self.knowledge.get(n, []):
            parts.append(read(os.path.join(self.root, rel)))
        return "\n".join(parts)

    def cross_round_scope(self, n, bank_paths):
        """Paragraphs anywhere in the prose that name round n. WIDE on
        purpose; the narrowing happens at the line level (`_names_round`)."""
        alts = [re.escape(bp) for bp in bank_paths] + [r"round[-\s]?0*%d\b" % n]
        pat = re.compile("(?:%s)" % "|".join(alts), re.IGNORECASE)
        return "\n\n".join(p for p in re.split(r"\n\s*\n", self.all_prose)
                           if pat.search(p))


def scan(corpus, n, bank_paths):
    """(kind, line, where) for scoring evidence about round n, else None."""
    ev = score_evidence(corpus.own_scope(n), n)
    if ev:
        return ev[0], ev[1], "own"
    ev = score_evidence(corpus.cross_round_scope(n, bank_paths), n,
                        require_named=bank_paths)
    return (ev[0], ev[1], "later") if ev else None


def load_ledger(root):
    path = os.path.join(root, LEDGER_FILE)
    if not os.path.exists(path):
        return {}, "absent"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh).get("banks", {}), None
    except (OSError, ValueError) as exc:
        return {}, str(exc)


def findings(root, corpus, banks, ledger, err, latest_round):
    out = []
    if err == "absent":
        out.append(("K003", LEDGER_FILE, "the ledger does not exist; every "
                                         "bank on disk is unaccounted for"))
    elif err:
        out.append(("K003", LEDGER_FILE, "unreadable: %s" % err))

    entries = {}
    for key, val in ledger.items():
        try:
            entries[int(key)] = val
        except (TypeError, ValueError):
            out.append(("K003", LEDGER_FILE,
                        "entry key %r is not a round number" % key))

    for n, e in sorted(entries.items()):
        if not isinstance(e, dict) or e.get("status") not in ("scored",
                                                              "unscored"):
            out.append(("K003", LEDGER_FILE,
                        "round %d: `status` must be 'scored' or 'unscored'" % n))
            continue
        need = REQUIRED_SCORED if e["status"] == "scored" else REQUIRED_UNSCORED
        missing = [f for f in need if not e.get(f)]
        if missing:
            out.append(("K003", LEDGER_FILE, "round %d: missing %s"
                        % (n, ", ".join(missing))))
            continue
        for field in ("remainder", "note"):
            if field in e and not str(e[field]).strip():
                out.append(("K003", LEDGER_FILE,
                            "round %d: `%s` is present but empty. An empty "
                            "`remainder` warns for a debt it does not name; "
                            "delete the field or say what is outstanding."
                            % (n, field)))
        if n not in banks:
            # ROUND 513. This branch used to say "no bank on disk at all --
            # the entry names nothing" for BOTH of the two cases below, and
            # for round 512 that sentence was false: the entry named
            # `state/whence/round-512/predictions.json`, the file existed,
            # and the only thing that was missing was the sweep's ability to
            # see it. A negative verdict computed on a FILTERED view
            # (`banks`, everything `find_banks` admits) must be re-tested
            # against the RAW thing the entry names before it is worded as a
            # fact about the disk -- one `os.path.exists`. The two cases need
            # opposite repairs, in different files.
            named = os.path.join(root, e["bank"])
            if os.path.exists(named):
                out.append(("K003", LEDGER_FILE,
                            "round %d: `bank` is %s, which EXISTS on disk, "
                            "yet the sweep found no bank for this round. The "
                            "LEDGER is right and `find_banks` is wrong — fix "
                            "the sweep's predicate (name shape, suffix, "
                            "skipped directory), not this entry"
                            % (n, e["bank"])))
            else:
                out.append(("K003", LEDGER_FILE,
                            "round %d: no bank on disk at all — `bank` is %s "
                            "and nothing is there, and the sweep found no "
                            "bank for this round either" % (n, e["bank"])))
            continue
        if e["bank"] not in banks[n]:
            out.append(("K003", LEDGER_FILE,
                        "round %d: `bank` is %s, but the bank(s) on disk are %s"
                        % (n, e["bank"], ", ".join(banks[n]))))
            continue
        if e["status"] == "scored":
            # Re-derive, do not trust. This is `claim_check`'s rule applied to
            # a ledger of claims about scorings.
            body = read(os.path.join(root, e["where"]))
            if not body:
                out.append(("K002", LEDGER_FILE,
                            "round %d: `where` %s is missing or empty"
                            % (n, e["where"])))
            elif e["quote"] not in body:
                # "no longer in" was an assertion about history this
                # check cannot make from one read. Round 484's anchor was
                # never in the file it cited — `git show` on both commits
                # that ever touched it finds 0 occurrences — so the message
                # named the wrong repair for four rounds (round 489).
                out.append(("K002", LEDGER_FILE,
                            "round %d: the cited sentence is not in %s — the "
                            "scoring claim cannot be re-derived. Check "
                            "whether it ever was (`git log -S`) before "
                            "assuming the file drifted"
                            % (n, e["where"])))
            else:
                # Present. Now the two questions presence does not answer:
                # is it present ONCE, and would it have been present
                # somewhere the entry does not name? See "Matching is not
                # locating" in the module docstring.
                occ = body.count(e["quote"])
                if occ > 1:
                    out.append(("K005", LEDGER_FILE,
                                "round %d: the cited sentence occurs %d times "
                                "in %s — a re-derivation cannot tell which "
                                "occurrence is the scoring line. Quote more "
                                "of it, or quote the line that is unique."
                                % (n, occ, e["where"])))
                own = {n}
                try:
                    own.add(int(e["scored_by"]))
                except (TypeError, ValueError):
                    pass
                foreign = corpus.foreign_scopes(e["quote"], own)
                if foreign:
                    out.append(("K006", LEDGER_FILE,
                                "round %d: the cited sentence also satisfies "
                                "K002 against %d scope(s) this entry has "
                                "nothing to do with (%s%s) — so `where` could "
                                "have named one of those instead and nothing "
                                "here would say so. The anchor matches; it "
                                "does not locate."
                                % (n, len(foreign), ", ".join(foreign[:3]),
                                   ", …" if len(foreign) > 3 else "")))
            # A discharge that left predictions out is a PARTIAL discharge.
            # Rounds 17 and 29 each have one: the sentence that scored them
            # names the predictions it did NOT reach, and no later round ever
            # did. A warning, not an error — the bank was engaged, and this
            # corpus's rule is that a check going FAIL for a debt the program
            # decided to carry gets ignored and then uninstalled.
            #
            # `remainder` is OUTSTANDING PREDICTIONS. Narrative that is not
            # a debt belongs in `note` (round 375); see the module
            # docstring for why this is a declared field and not a scan.
            if e.get("remainder"):
                out.append(("K004", LEDGER_FILE,
                            "round %d: partially discharged by round %s — %s"
                            % (n, e["scored_by"], e["remainder"][:150])))
        else:
            hit = scan(corpus, n, banks[n])
            if hit:
                # ROUND 489: publish the evidence's ATTRIBUTION beside the
                # verdict. K003 carried round 479 for four rounds with a
                # correct verdict and an evidence line about round 473's
                # bank; the next reader's only safe move is to read the
                # line, and nothing told them to. `mentioned_rounds` is
                # wider than the `_attributable` filter on purpose — an
                # evidence auditor that shares the detector's predicate can
                # only ever agree with it.
                named = mentioned_rounds(hit[1])
                others = sorted(named - {n})
                caveat = ""
                if others and n not in named:
                    caveat = (" — CAVEAT: that line names round(s) %s and "
                              "never round %d, so it may be this round's "
                              "scope discussing SOMEBODY ELSE's bank. Read "
                              "it before flipping the status."
                              % (", ".join(str(x) for x in others), n))
                out.append(("K003", LEDGER_FILE,
                            "round %d: recorded `unscored`, but a scoring now "
                            "reads as present (%s/%s: %s) — an acknowledgement "
                            "that outlives its debt is a mute button%s"
                            % (n, hit[2], hit[0], hit[1][:90], caveat)))
                continue
            age = latest_round - n
            if age >= ROTATION:
                out.append(("K004", LEDGER_FILE,
                            "round %d: owed for %d rounds (owner %s) — older "
                            "than one full rotation, so its owning track has "
                            "had a turn" % (n, age, e["owner"])))

    for n in sorted(banks):
        if n not in entries:
            out.append(("K001", banks[n][0],
                        "round %d banked predictions and %s has no entry for "
                        "it — nobody can tell whether D-013's second half was "
                        "ever done" % (n, LEDGER_FILE)))
    return out


def quote_audit(root, corpus, ledger):
    """[(round, len, occurrences in `where`, [foreign coordinates])] .

    The pricing behind K005/K006, kept runnable so the next round does not
    have to take round 465's three numbers on faith — this program's own
    rule (`skills/carried-claim-rot`), and round 464 published `54 of 138
    quotes are under 40 characters` one commit before its OWN repair
    lengthened one of them to 50.
    """
    rows = []
    for key in sorted(ledger, key=lambda k: int(k) if str(k).isdigit() else 0):
        e = ledger[key]
        if not isinstance(e, dict) or e.get("status") != "scored":
            continue
        if not e.get("quote") or not e.get("where"):
            continue
        n = int(key)
        body = read(os.path.join(root, e["where"]))
        own = {n}
        try:
            own.add(int(e["scored_by"]))
        except (TypeError, ValueError):
            pass
        rows.append((n, len(e["quote"]), body.count(e["quote"]),
                     corpus.foreign_scopes(e["quote"], own)))
    return rows


# A line worth proposing as a replacement anchor. Deliberately NOT a
# classifier for "is this the scoring sentence" — round 369 deleted one of
# those. It is a filter for "could this line be a scoring line at all",
# and every candidate it prints is then checked for the two properties the
# codes actually test.
_SCORING_LINE_RE = re.compile(r"\b(HIT|MISS|PARTIAL|scored|predictions?)\b",
                              re.IGNORECASE)


def requote(root, corpus, ledger, n):
    """Candidate anchors for round n's entry: unique in `where`, foreign-free.

    Ranked longest-first, because the failure this repairs is an anchor with
    too little information in it. Prints, never writes: which sentence is
    THE scoring line is the ledger author's judgement, and a script that
    picked one would be the prose classifier this checker exists instead of.
    """
    e = ledger.get(str(n))
    if not isinstance(e, dict) or e.get("status") != "scored":
        return []
    body = read(os.path.join(root, e["where"]))
    own = {n}
    try:
        own.add(int(e["scored_by"]))
    except (TypeError, ValueError):
        pass
    seen, out = set(), []
    for raw in body.splitlines():
        line = raw.strip()
        if len(line) < 40 or line in seen or not _SCORING_LINE_RE.search(line):
            continue
        seen.add(line)
        if body.count(line) != 1:
            continue
        if corpus.foreign_scopes(line, own):
            continue
        out.append(line)
    out.sort(key=len, reverse=True)
    return out


# --------------------------------------------------------------------------
# `--enter` (round 501, skills B). The generator behind the recurrence.
#
# K001 has gone red six times and been closed six times, and every closure was
# a skills(B) round hand-writing ledger entries for banks OTHER rounds left.
# The arithmetic is the whole story: banks arrive at ~1 per round, entries are
# written at ~1 per ROTATION, and the rotation is six. So the steady state is
# a red check with a monotonically growing error count, closed on the sixth
# round and reopened on the seventh. Rounds 473, 480, 487 and 494 each wrote
# that diagnosis down in prose; nothing was ever built from it.
#
# What was missing was not the will. It was that writing an entry by hand is
# a four-code job -- the quote must be PRESENT in `where` (K002), present
# exactly ONCE (K005), matched by no other round's scope (K006), and it must
# be a scoring rather than a promise of one (round 495's POINTER_RE) -- and a
# round that has just spent its budget on its own track will not do a
# four-code job for bookkeeping. So it is done by whoever runs this checker,
# which is skills(B), one round in six.
#
# `--enter NNN` does the four-code job. It is deliberately NOT `--suggest`:
#
#   `--suggest` runs `scan`, which is the PROSE CLASSIFIER round 369 demoted
#   for getting 5 of 13 verdicts wrong. It emits `"where": "?"` and
#   `"scored_by": null` -- an entry nobody can write without doing the work
#   again -- and round 495 showed it will happily propose `scored` for round
#   492, whose knowledge file promises `Scored in §10.` and has no §10.
#
#   `--enter` runs the checker's OWN ERROR CODES FORWARDS. A line is a
#   candidate anchor only if it would survive K002, K005, K006 and the
#   pointer rule, and only if it carries a literal verdict of its own. When
#   no line does, it proposes `unscored` and says what it searched for. It
#   cannot launder a bank, because the property it tests IS the property the
#   ledger is checked on.
#
# Scope, stated so it is not mistaken for more: `--enter` proposes a
# SELF-scoring entry -- round n's bank, scored by round n, in round n's own
# knowledge file. That is 146 of the 173 entries this ledger already holds.
# A cross-round discharge (round 371 scoring round 23's bank) is a judgement
# about somebody else's work and stays a hand job with `--suggest` beside it.
# --------------------------------------------------------------------------

# The floor round 464 proposed and round 465 priced. It is a PROXY for "this
# anchor carries enough information to locate", not a finding in itself --
# 47 live entries are under it and are fine. Used here as a generator-side
# filter, where being conservative costs nothing but a longer quote.
MIN_ANCHOR = 40


def anchor_candidates(corpus, body, n, own=None):
    """Lines in `body` that would survive this checker as round n's anchor.

    Every filter is one of the module's own findings, run forwards:

        len >= MIN_ANCHOR       the K005/K006 proxy (round 464/465)
        VERDICT_ON_LINE_RE      a scoring, not a promise of one (round 495)
        not NEGATION_RE         "P4 was never scored" is not a scoring
        not unkept_pointer      a pointer to a section that does not exist
        _attributable           the line does not credit some other round
        body.count(line) == 1   K005: present twice is not located once
        no foreign_scopes       K006: `where` could not have been wrong

    Ranked longest-first for the same reason `requote` is: the failure being
    prevented is an anchor with too little information in it.

    Differs from `requote`'s filter in ONE clause and it is the load-bearing
    one. `requote` accepts `_SCORING_LINE_RE` -- the vocabulary of scoring,
    including the word `predictions` -- because a human is choosing from its
    output and can see that `**Predictions banked before measuring:**` is a
    header. Nothing chooses from this list, so it demands a VERDICT.
    """
    own = set(own or {n})
    seen, out = set(), []
    for raw in body.splitlines():
        line = raw.strip()
        if line in seen:
            continue
        seen.add(line)
        if len(line) < MIN_ANCHOR:
            continue
        if not VERDICT_ON_LINE_RE.search(line):
            continue
        if NEGATION_RE.search(line):
            continue
        if unkept_pointer(line, body):
            continue
        if not _attributable(line, n):
            continue
        if body.count(line) != 1:
            continue
        if corpus.foreign_scopes(line, own):
            continue
        out.append(line)
    out.sort(key=len, reverse=True)
    return out


def enter(root, corpus, banks, ledger, n, entered_by=None, owner=None,
          note=None):
    """(entry_or_None, diagnosis) — a derived ledger entry for round n.

    `entry` is a dict ready to drop into `banks`, or None when there is no
    bank on disk to write one for. The diagnosis carries everything the
    proposal was derived FROM, so a reader can disagree with it without
    re-running anything: which files were searched, how many candidates each
    yielded, and which clause the verdict turned on.

    NEVER guesses an owner. An `unscored` entry with no owner is a K003 the
    moment it lands, so the CLI refuses to write one -- naming who owes the
    scoring is a judgement and this function will not make it up.
    """
    diag = {"round": n, "bank": None, "already_in_ledger": str(n) in ledger,
            "where_tried": [], "candidates": {}, "verdict": None,
            "chose": None}
    if n not in banks:
        diag["verdict"] = "no-bank"
        return None, diag
    diag["bank"] = banks[n][0]

    chosen = None
    for rel in corpus.knowledge.get(n, []):
        body = read(os.path.join(root, rel))
        cands = anchor_candidates(corpus, body, n)
        diag["where_tried"].append(rel)
        diag["candidates"][rel] = cands
        if cands and chosen is None:
            chosen = (rel, cands[0])

    if chosen is None:
        diag["verdict"] = ("unscored/no-knowledge-file"
                           if not diag["where_tried"]
                           else "unscored/no-anchor")
        searched = (", ".join(diag["where_tried"])
                    if diag["where_tried"]
                    else "no knowledge/round-%d-*.md exists" % n)
        why = ("`carryforward_check.py --enter %d` searched %s and found no "
               "line that carries its own HIT/MISS/PARTIAL verdict, is >= %d "
               "characters, occurs exactly once in its file, and is matched "
               "by no other round's scope. A promise of a scoring is not a "
               "scoring (round 495): if this round did score its bank, the "
               "scoring is somewhere this generator does not look -- say "
               "where, and write the entry by hand."
               % (n, searched, MIN_ANCHOR))
        entry = {"bank": diag["bank"], "status": "unscored",
                 "owner": owner or "", "why": why}
        if note:
            entry["note"] = note
        return entry, diag

    rel, quote = chosen
    diag["verdict"] = "scored"
    diag["chose"] = rel
    entry = {"bank": diag["bank"], "status": "scored", "scored_by": n,
             "where": rel, "quote": quote}
    if entered_by is not None and entered_by != n:
        entry["entered_by"] = entered_by
    if note:
        entry["note"] = note
    return entry, diag


def write_entry(root, n, entry, force=False):
    """Append `entry` to the ledger, byte-stably. Returns an error or None.

    The serialisation is pinned to what the file on disk already is --
    `json.dumps(doc, indent=1) + "\\n"`, `ensure_ascii` left at its default
    True. Verified before this was written: re-serialising the untouched
    ledger that way reproduces it byte for byte, while `indent=2` or
    `ensure_ascii=False` rewrites every one of its ~3000 lines and buries a
    three-entry addition in a whole-file reformat. That is a mistake this
    program has already made once and recorded.
    """
    path = os.path.join(root, LEDGER_FILE)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        return "ledger unreadable: %s" % exc
    doc.setdefault("banks", {})
    if str(n) in doc["banks"] and not force:
        return ("round %d already has an entry; refusing to overwrite it "
                "(pass --force if you mean to replace it)" % n)
    if entry.get("status") == "unscored" and not entry.get("owner"):
        return ("refusing to write an `unscored` entry with no owner -- it "
                "would be a K003 the moment it lands. Pass --owner TRACK.")
    doc["banks"][str(n)] = entry
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1) + "\n")
    return None


# --------------------------------------------------------------------------
# `--staged-check` (round 501). The generator above is useless if nothing
# asks for it, and asking is what has failed.
#
# The practice is NOT unknown. Rounds 493, 494, 496 and 497 each wrote their
# own ledger entry inside their own round's commit and said so in the entry
# ("registered here at the END of the round, scored"). Rounds 498, 499 and
# 500 did not. That is a ~50% compliance rate on a rule that is already
# written down, and one miss is enough: the check then stays red until the
# next skills(B) round, which is up to five rounds later, and the error
# count grows by one per round in the meantime. Six closures, six reopenings.
#
# More prose will not move a 50% rate. The one place the AUTHOR is still
# present is commit time -- round 499's finding, made about a different
# check (W001, opened seven times by seven rounds that never saw it) and
# true of this one for the same reason: the health checks run after the
# agent process exits and write to logs/, which is not in git.
#
# TRIGGER, and why it is the knowledge file and not the bank. A bank is
# committed EARLY, before measuring, and at that moment the ledger entry
# cannot exist yet -- warning there would cry wolf on the one round doing
# D-013 correctly. The knowledge file is the END-OF-ROUND artefact. When it
# is in the commit, the round has scored, and the entry is one command away.
#
# COST is the whole reason this does not just call `findings()`. A full run
# builds `Corpus`, which reads state/research-state.md, its archive and
# every knowledge/*.md: 1.9 s measured. This path reads the ledger JSON and
# walks the staged list, and nothing else.
# --------------------------------------------------------------------------

_KNOWLEDGE_ROUND_RE = re.compile(r"^knowledge/round-(\d{1,4})\b")


def staged_paths(root):
    """The paths this commit would land, or [] if git cannot be asked."""
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=20)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.decode("utf-8", "replace").splitlines() if p]


def staged_gaps(root, paths, banks, ledger):
    """[(round, knowledge file, bank)] this commit closes a round without.

    A gap is: the commit stages `knowledge/round-NNN-*.md`, a bank for NNN
    exists on disk, and the ledger has no entry for NNN. Deliberately blind
    to everything else -- it is not a second copy of `findings`, it is the
    subset of K001 whose author is still in the room.
    """
    gaps = []
    for rel in paths:
        m = _KNOWLEDGE_ROUND_RE.match(rel.replace(os.sep, "/"))
        if not m:
            continue
        n = int(m.group(1))
        if n not in banks or str(n) in ledger:
            continue
        gaps.append((n, rel, banks[n][0]))
    return sorted(set(gaps))


def evidence_audit(corpus, banks):
    """Per bank round: the evidence `scan` would report, and what it skipped.

    ROUND 489. A detector that returns `(verdict, evidence)` is making two
    claims, and in this repo only the verdict was ever tested. K003 fired on
    round 479 for four rounds with a correct verdict — the bank HAD been
    scored, by round 485, in round 485's own file — and an evidence line
    that is a sentence about ROUND 473's bank. The wrong evidence was
    invisible for exactly as long as the verdict happened to be right, and
    it is the same wrong evidence that would have produced a clean FALSE
    POSITIVE on any round whose scope opens with a sentence about someone
    else's predictions.

    So this audit does not re-run the detector's filter. `credited_rounds`
    is the filter; `mentioned_rounds` is a deliberately WIDER net, and a row
    is `suspect` when the line the detector would publish names some other
    round and never names its own. A checker audited by its own predicate
    can only agree with itself.

    Returns one row per bank round; `--audit-evidence` prints them.
    """
    rows = []
    for n in sorted(banks):
        text = corpus.own_scope(n)
        negated = foreign = promised = 0
        promises = []
        verdict = None
        for kind, line, is_neg in raw_candidates(text):
            line = line.strip()[:200]
            if is_neg:
                negated += 1
                continue
            # Counted and PUBLISHED, not silently dropped. The whole reason
            # this audit exists (round 489) is that a filter nobody can see
            # is a filter nobody can check — and round 495's pointer rule is
            # the first filter here that can veto a line a human would read
            # as a scoring, so it owes the reader its rejects by name.
            sec = unkept_pointer(line, text)
            if sec:
                promised += 1
                promises.append({"section": sec, "line": line})
                continue
            if not _attributable(line, n):
                foreign += 1
                continue
            if verdict is None:
                verdict = (kind, line)
        mentions = sorted(mentioned_rounds(verdict[1]) - {n}) if verdict else []
        rows.append({
            "round": n,
            "negated": negated,
            "rejected_foreign": foreign,
            "rejected_unkept_pointer": promised,
            "unkept_pointers": promises,
            "verdict_kind": verdict[0] if verdict else None,
            "verdict_line": verdict[1] if verdict else None,
            "mentions_other_rounds": mentions,
            "names_itself": bool(verdict
                                 and n in mentioned_rounds(verdict[1])),
            "suspect": bool(verdict and mentions
                            and n not in mentioned_rounds(verdict[1])),
        })
    return rows


def evidence_summary(rows):
    """The three numbers `--audit-evidence` exists to publish."""
    withev = [r for r in rows if r["verdict_line"]]
    suspect = [r for r in withev if r["suspect"]]
    promised = [r for r in rows if r.get("rejected_unkept_pointer")]
    return {"banks": len(rows), "with_evidence": len(withev),
            "rejected_foreign": sum(r["rejected_foreign"] for r in rows),
            "rejected_unkept_pointer": sum(r.get("rejected_unkept_pointer", 0)
                                           for r in rows),
            "unkept_pointer_rounds": [r["round"] for r in promised],
            "suspect": len(suspect),
            "suspect_rounds": [r["round"] for r in suspect]}


SEV = {"K001": "ERROR", "K002": "ERROR", "K003": "ERROR", "K004": "WARN",
       "K005": "ERROR", "K006": "ERROR"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    ap.add_argument("--list", action="store_true", help="print the ledger")
    ap.add_argument("--suggest", action="store_true",
                    help="propose ledger entries for banks that have none")
    ap.add_argument("--audit-quotes", action="store_true",
                    help="per-entry anchor pricing: length, occurrences in "
                         "`where`, foreign scopes that also match")
    ap.add_argument("--requote", type=int, default=None, metavar="ROUND",
                    help="propose replacement anchors for ROUND's entry")
    ap.add_argument("--enter", type=int, default=None, metavar="ROUND",
                    help="derive a ledger entry for ROUND's bank from ROUND's "
                         "own knowledge file, running K002/K005/K006 and the "
                         "pointer rule FORWARDS. Prints; --write commits it.")
    ap.add_argument("--write", action="store_true",
                    help="with --enter: write the proposal into the ledger")
    ap.add_argument("--force", action="store_true",
                    help="with --enter --write: replace an existing entry")
    ap.add_argument("--entered-by", type=int, default=None, metavar="ROUND",
                    help="with --enter: the round writing the entry, when it "
                         "is not the round that banked (round 453's field)")
    ap.add_argument("--owner", default=None,
                    help="with --enter: the track owing the scoring, required "
                         "before an `unscored` proposal can be written")
    ap.add_argument("--note", default=None,
                    help="with --enter: a `note` for the entry")
    ap.add_argument("--staged-check", action="store_true",
                    help="commit-time tier: warn when this commit stages a "
                         "round's knowledge file while that round's bank has "
                         "no ledger entry. Reads the ledger only; no corpus.")
    ap.add_argument("--quiet", action="store_true",
                    help="with --staged-check: print nothing when clean")
    ap.add_argument("--audit-evidence", action="store_true",
                    help="per bank round: the evidence `scan` would publish, "
                         "the candidates it skipped, and whether that "
                         "evidence names a DIFFERENT round (round 489)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(list(sys.argv[1:] if argv is None else argv))
    root = os.path.abspath(args.repo_root)
    if not os.path.isdir(os.path.join(root, "state")):
        print("error: %s has no state/ directory" % root, file=sys.stderr)
        return 2

    if args.staged_check:
        banks, _unnumbered = find_banks(root)
        ledger, _err = load_ledger(root)
        gaps = staged_gaps(root, staged_paths(root), banks, ledger)
        if not gaps:
            if not args.quiet:
                print("carryforward --staged-check: no staged round closes "
                      "without its ledger entry")
            return 0
        for n, rel, bank in gaps:
            print("carryforward: WARN K001-at-commit — this commit stages %s "
                  "while %s has no entry for round %d's bank (%s).\n"
                  "    Derive and write it with:\n"
                  "      python3 skills/skill-authoring/scripts/"
                  "carryforward_check.py --enter %d --write\n"
                  "    That command REFUSES if round %d's knowledge file "
                  "carries no verdict of its own, so it cannot launder an "
                  "unscored bank."
                  % (rel, LEDGER_FILE, n, bank, n, n))
        return 0

    corpus = Corpus(root)
    banks, unnumbered = find_banks(root)
    ledger, err = load_ledger(root)
    latest = max(list(banks) + list(corpus.sections) + [0])
    found = findings(root, corpus, banks, ledger, err, latest)

    if args.audit_evidence:
        rows = evidence_audit(corpus, banks)
        for r in rows:
            if not r["verdict_line"]:
                continue
            print("round %-4d %-14s neg=%-2d foreign=%-2d %s%s"
                  % (r["round"], r["verdict_kind"], r["negated"],
                     r["rejected_foreign"],
                     "SUSPECT(names %s) " % ",".join(
                         str(x) for x in r["mentions_other_rounds"])
                     if r["suspect"] else "",
                     r["verdict_line"][:90]))
        summ = evidence_summary(rows)
        print("evidence-audit: %d bank(s), %d with evidence, %d foreign "
              "line(s) rejected, %d SUSPECT %s"
              % (summ["banks"], summ["with_evidence"],
                 summ["rejected_foreign"], summ["suspect"],
                 summ["suspect_rounds"]))
        if args.json:
            with open(args.json, "w") as fh:
                json.dump({"rows": rows, "summary": summ}, fh, indent=1)
        return 0

    if args.list:
        for n in sorted(banks):
            e = ledger.get(str(n), {})
            print("round %-4d %-44s %-9s %s"
                  % (n, banks[n][0], e.get("status", "MISSING"),
                     ("scored by round %s in %s" % (e.get("scored_by"),
                                                    e.get("where")))
                     if e.get("status") == "scored"
                     else (e.get("why", "")[:70] if e else "")))
        for rel in unnumbered:
            print("round ?    %-44s %-9s (no round number in the path)"
                  % (rel, "-"))

    if args.suggest:
        for n in sorted(banks):
            if str(n) in ledger:
                continue
            hit = scan(corpus, n, banks[n])
            print(json.dumps({str(n): (
                {"bank": banks[n][0], "status": "scored", "scored_by": None,
                 "where": "?", "quote": hit[1]} if hit else
                {"bank": banks[n][0], "status": "unscored", "owner": "?",
                 "why": "no scoring evidence found by --suggest"})}))

    if args.audit_quotes:
        rows = quote_audit(root, corpus, ledger)
        print("round  len  occ  foreign  coordinates")
        for n, ln, occ, fr in rows:
            print("%-6d %-4d %-4d %-8d %s"
                  % (n, ln, occ, len(fr), ", ".join(fr[:2])))
        print("-- %d scored entr(ies): %d absent from `where` (K002), "
              "%d occurring 2+ times (K005), %d with a foreign scope (K006), "
              "%d shorter than 40 chars (the PROXY, not a finding)"
              % (len(rows), sum(1 for r in rows if r[2] == 0),
                 sum(1 for r in rows if r[2] > 1),
                 sum(1 for r in rows if r[3]),
                 sum(1 for r in rows if r[1] < 40)))

    if args.enter is not None:
        entry, diag = enter(root, corpus, banks, ledger, args.enter,
                            entered_by=args.entered_by, owner=args.owner,
                            note=args.note)
        print("-- enter round %d: verdict %s; bank %s; already in ledger: %s"
              % (diag["round"], diag["verdict"], diag["bank"],
                 diag["already_in_ledger"]))
        for rel in diag["where_tried"]:
            print("   searched %-62s %d candidate anchor(s)"
                  % (rel, len(diag["candidates"][rel])))
        if entry is None:
            print("   no bank on disk for round %d — nothing to enter"
                  % args.enter)
        else:
            print(json.dumps({str(args.enter): entry}, indent=1))
        if args.write and entry is not None:
            err_w = write_entry(root, args.enter, entry, force=args.force)
            if err_w:
                print("   NOT WRITTEN: %s" % err_w)
            else:
                print("   written to %s" % LEDGER_FILE)
                ledger, err = load_ledger(root)
                found = findings(root, corpus, banks, ledger, err, latest)
        elif args.write:
            print("   NOT WRITTEN: nothing to write")

    if args.requote is not None:
        cands = requote(root, corpus, ledger, args.requote)
        if not cands:
            print("no candidate anchor for round %s (no scored entry, or no "
                  "line in `where` is unique, foreign-free and >=40 chars)"
                  % args.requote)
        for line in cands[:10]:
            print(json.dumps(line))

    for code, path, msg in found:
        print("%s: %s %s %s" % (path, SEV[code], code, msg))

    n_banks = sum(len(v) for v in banks.values())
    n_scored = sum(1 for e in ledger.values()
                   if isinstance(e, dict) and e.get("status") == "scored")
    n_unscored = sum(1 for e in ledger.values()
                     if isinstance(e, dict) and e.get("status") == "unscored")
    n_err = sum(1 for c, _, _ in found if SEV[c] == "ERROR")
    n_warn = len(found) - n_err
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"repo_root": root, "latest_round": latest,
                       "banks": n_banks, "unnumbered_banks": unnumbered,
                       "scored": n_scored, "unscored": n_unscored,
                       "findings": [{"code": c, "path": p, "message": m}
                                    for c, p, m in found]}, fh, indent=1)
    print("carryforward: %d bank(s) (+%d unnumbered), %d scored, %d unscored, "
          "%d error(s), %d warning(s)"
          % (n_banks, len(unnumbered), n_scored, n_unscored, n_err, n_warn))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
