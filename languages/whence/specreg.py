#!/usr/bin/env python3
"""specreg.py — the SPEC decision registry read as a NUMBERING SYSTEM.

Round 464 (language C).

What already exists, and the gap between them
---------------------------------------------
`skills/skill-authoring/scripts/xref_check.py` (round 345) family `X001`
asks one question of `languages/whence/SPEC.md`:

    is every id someone CITES defined in the registry?

That is a question about citations. It is answered by building a SET of
registry ids and testing membership. Everything a set forgets, it forgets:
an id defined twice, a hole in the sequence, a definition nobody cites, and
— the one that bit — *an id that exists but is not in the registry at all*.

Round 462 minted decision 56. It wrote `### Decision 56 (round 462, language
C): …` into SPEC.md § `Decision 56`, which is where the last four decisions
put their prose, and did not append `56. **…**` to `## Anti-mainstream design
decisions`, which is the registry. (Cited by SECTION, not by line: round
462's own next step 4 says a SPEC file:line is not durable, and the repair
described below moved that section 29 lines down the file — which is the
rule proving itself inside one round.) `xref_check` reported it — but only
because the section HEADING contains the words `Decision 56`, and X001's
citation pattern is `\\bdecision\\s+(\\d+)\\b`. **The definition was caught by
being, accidentally, a citation of itself.** Had round 462 titled its
section the way rounds 446, 450 and 452 titled theirs — `## v0.42 (round
446, language C) — the miss inside a value nothing kept` — the id 56 would
appear nowhere in citable text, the registry would be one entry short, and
no instrument in this tree would say so.

The consequence is not cosmetic, and it is live at HEAD
-------------------------------------------------------
The registry is the only site that assigns the NEXT number. Its own reserved
comment says so:

    Append here in the SAME round that mints a number.

A round that follows that instruction reads the registry, sees max 55, and
mints **56** — which round 462 already used. A missing registry entry is not
a missing sentence; it is a *free number that is not free*, and the failure
it produces lands two rounds later in a different file and looks like a
disagreement about what decision 56 says. `specreg.py next` exists so that
no round has to read a registry to find out, and `S001` exists so that the
gap is reported by something other than luck.

The rule this file is built on
-------------------------------
**A registry that mints ordinals is a DENSE range, and density is checkable
without a single citation.** Membership needs someone to ask; density does
not. So every finding below is derived from the document alone, and the
citation scan (`S006`) is a tally reported beside them, never the thing that
makes an error.

Sites
-----
A decision may be written in up to three places. All three are parsed:

    registry   `N. **Title … (label, round R).**` inside SPEC.md
               § `Anti-mainstream design decisions`. THE registry: this is
               what `xref_check.ordinal_registry` counts, and
               `tests/test_specreg.py` pins the two parsers equal so this
               file can never drift into a second opinion about membership.
    section    a heading `#{1,6} … Decision <N> …` anywhere else in
               SPEC.md. Where rounds 442-462 put the prose.
    version    a heading `## <label> (round R, …)` — the version-history
               section a registry entry's tag points INTO.

    reserved   `A-B. *(reserved — …)*`, a declared hole. Deliberately not in
               the `N. **Bold**` form (round 348), so `ordinal_registry`
               does not count it as an entry and a citation of an id inside
               it still dangles. Parsed here as a RANGE, because density is
               exactly the question a declared hole answers.

Findings
--------
`S001` (ERROR)  minted-unregistered: a `section` defines an id with no
                registry entry. The collision precursor described above.
`S002` (ERROR)  collision: two registry entries, or two sections, for one
                id. Invisible to a set-based reader by construction.
`S003` (ERROR)  hole: an id in `1..max` with no entry and no covering
                reserved range. A gap nobody declared.
`S004` (ERROR)  tag disagreement: a registry entry's `(label, round R)`
                names a label with no such heading, or names one whose
                round is not R. The registry entry and the prose it points
                at are two writings of one fact; a fact written twice and
                checked never is the rot this workspace keeps finding.
`S005` (WARN)   untagged: a registry entry that carries no `round N`.
                Entries 1-13 predate the convention and are exempt by a
                declared floor, not by a guess.
`S006` (WARN)   orphan: a registry id cited NOWHERE outside its own
                definition — the inverse of a dangling citation, and the
                half `xref_check` cannot see. A warning, never an error:
                an uncited decision is unloved, not wrong.

The SECOND registry (round 486)
--------------------------------
This document mints two ordinal sequences. Everything above is about
decisions. `## v0.N (round R, …)` is the other one, and it is the same
shape — dense, minted one at a time, cited from code. Round 464 built
density checking for one of the two.

The consequence was live for three rounds. Rounds 476, 480 and 482 each
wrote a version number into CODE (`#: v0.47 (round 482), decision 60.`,
`tests/test_v46.py`, `tests/test_v47.py`) and none of them wrote the
`## v0.45` / `## v0.46` / `## v0.47` section. Nothing said so.
`tests/test_v22.py::test_spec_level_header_matches_the_highest_version_
section` was GREEN throughout, because it takes the top of the range from
the SECTIONS — so the range is dense by construction and the header agrees
with whatever the document already says. **The top of this range is set by
the code, not by the document**, which is the one direction that test
cannot look.

`S007` (ERROR)  version cited with no section: a `vN.N` written anywhere in
                the citation scope, at or above `VERSION_FLOOR`, with no
                `## vN (…)` heading. S001's question, asked of versions.
`S008` (ERROR)  version hole: a MINOR level inside the range with neither a
                section nor a claim. S003's question. Density is claimed
                over the minor component only — the sub-version dimension
                (v0.14.1-.14, v0.16.1-.6, v0.17.1) is deliberately sparse.
`S009` (WARN)   a registry entry tagged `(round R)` with no label, while a
                `## vN` heading names round R. S004 has two branches and
                only the LABELLED one reaches a version heading; entries
                54-60 all took the other branch, which compares two
                writings by one round in one file. This names the entry
                that should carry the label.
`S010` (ERROR)  the `*Spec level: **vN**` header is not the highest `## vN`
                section. A second writing of `test_v22.py`'s assertion, on
                purpose: that test lives in the whence suite, and this is
                the tool a round runs to ask whether SPEC.md is coherent.
                `tests/test_specreg.py` pins the two equal.

Exit code is driven by ERRORS ONLY (round 363's rule: a check that goes FAIL
every round for a debt the program decided to carry gets ignored, then
uninstalled). The warning counts ride in the summary line.

Usage
-----
    python3 specreg.py audit            # findings; exit 1 if any ERROR
    python3 specreg.py table            # one row per id, all sites
    python3 specreg.py versions         # one row per version level (round 486)
    python3 specreg.py next             # the next free decision number
    python3 specreg.py audit --json OUT # machine-readable

Pitfall this file walks around
-------------------------------
Its own docstring cites decision numbers, and X001's authoritative scope
covers `languages/whence/`. So an id written HERE as an example is a live
dangling citation — round 463's shape, where pasting a failing X001 line
into `research-state.md` took the checker from 1 NEW to 2. Every number
named above is one that exists; a hypothetical id is written `decision N`,
whose `N` the citation pattern cannot match.

This is not a hypothetical pitfall. The FIRST draft of this paragraph
spelled the next free number out as an example, `S006` reported it as cited
but unminted inside one run of the module it was warning inside, and
`test_specreg.py::test_this_module_cites_no_unminted_decision` is what
holds the repair. A rule stated in prose and not pinned by a test is a rule
its own author breaks in the sentence that states it.
"""

import argparse
import bisect
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Under a mutation/repair copy this file is at `/tmp/<sandbox>/specreg.py`,
# so `HERE/../..` resolves to `/tmp` -- outside the copy AND outside the
# checkout, silently. `harness/swe/proc.py` exports `AGI_RESEARCH_ROOT` into
# every such subprocess for exactly this, and seven other expressions in this
# tree already reach the root through it. Round 467 (SWE-loop D): this was the
# ONE unguarded escape here, and it kept three nodes of
# `harness/tests/test_swe_copyparity_real_subject.py` red for rounds 464-466.
REPO = (os.environ.get("AGI_RESEARCH_ROOT")
        or os.path.abspath(os.path.join(HERE, "..", "..")))
SPEC = os.path.join(HERE, "SPEC.md")
SPEC_REL = "languages/whence/SPEC.md"

REGISTRY_HEADING = "Anti-mainstream design decisions"

# `N. **` at column 0. Identical to `xref_check.ORDINAL_ITEM_RE`'s intent;
# `tests/test_specreg.py` pins the resulting id sets equal rather than
# sharing the regex, because two parsers that agree by TEST stay honest and
# two that agree by import only agree about the import.
ENTRY_RE = re.compile(r"^(\d+)\.\s+\*\*", re.M)
RESERVED_RE = re.compile(r"^(\d+)-(\d+)\.\s+\*\(reserved\b", re.M)
DECISION_HEAD_RE = re.compile(r"^(#{1,6})\s+(.*\bDecision\s+(\d+)\b.*)$", re.M)
VERSION_HEAD_RE = re.compile(r"^##\s+(.+?)\s+\((.*?)\)\s*(?:—|--|$)", re.M)
ROUND_RE = re.compile(r"\bround\s+(\d+)\b", re.I)
CITE_RE = re.compile(r"\bdecision\s+(\d+)\b", re.I)
NEWLINE_RE = re.compile(r"\n")

# Round 486 (language C). THE SECOND REGISTRY.
#
# This document mints two ordinal sequences, not one. Decisions get S001-S006
# above. VERSION LEVELS -- `## v0.N (round R, …)` -- get nothing, and they are
# the same shape: a dense range, minted one at a time by rounds, cited from
# code that says "at v0.45 this returned []".
#
# `VERSION_CITE_RE` requires at least two numeric components so that a bare
# `v1` in prose is not a citation, and allows more so that `v0.14.13` is one.
VERSION_LABEL_RE = re.compile(r"^v(\d+(?:\.\d+)+)$")
VERSION_CITE_RE = re.compile(r"\bv(\d+\.\d+(?:\.\d+)*)\b")

# Entries 1-13 were written for v0.1-v0.4, before this program recorded a
# round beside a decision. A FLOOR, not a per-id allowlist: the exemption
# has to expire for every future entry automatically, which an allowlist
# would not do.
TAG_FLOOR = 27

# The same device for the version registry. `## v0.6 (round 020)` is the
# FIRST version heading in the document; v0.1-v0.5 predate the convention and
# are documented under prose-titled headings that carry the number in the
# parenthetical instead -- `## Provenance as data (v0.2)`, `## Records as data
# / self-hosting (v0.5, round 014)` -- plus registry entries 1-13, whose tags
# are `v0.1`-`v0.4`. So they are documented, just not as `## vN` sections, and
# S007 would report seven of them forever.
#
# A floor and not an allowlist, for TAG_FLOOR's reason: the exemption has to
# expire automatically for every version above it. Round 486 measured the
# alternative -- with no floor, the live tree reports v0.1, v0.2, v0.2.1,
# v0.3, v0.4, v0.4.1 and v0.5 alongside the three real findings, and a check
# that reports seven permanent non-problems beside three real ones is a check
# somebody switches off (round 363's rule).
VERSION_FLOOR = (0, 6)

# X001's own scope, restated (`xref_check.FAMILIES[0].scope_re`). Kept as a
# literal rather than imported so that `specreg.py` runs from a checkout of
# `languages/whence` alone; `tests/test_specreg.py` asserts the two agree.
CITE_SCOPE_RE = re.compile(r"^(languages/whence/|knowledge/|state/research-state)")
CITE_SUFFIXES = (".md", ".py", ".lang", ".txt")
# ROUND 486 (language C): `.venv`, `venv` and `site-packages` were NOT here,
# and `languages/whence/.venv/` exists (it is a dotfile, so every `ls` in this
# tree's history walked straight past it). Measured before the fix:
# `_in_scope_files()` yielded **1452 files, 984 of them (67.8 %) vendored
# third-party code** under `languages/whence/.venv/lib/python3.12/
# site-packages/`.
#
# For S001-S006 that was inert -- zero of the vendored files happens to
# contain `decision <N>`, so the citation tally never moved. It is not inert
# in the direction that matters: S006 is an INVERSE check ("cited nowhere"),
# so a single vendored sentence saying "decision 3" would have SUPPRESSED a
# warning, silently and in the reassuring direction.
#
# And it is not inert at all for S007 below. `pygments/lexers/meson.py` names
# Meson's 0.58 reference manual, `nodeenv.py` names 0.4.3, `pip._vendor`'s
# `distlib/version.py` names 0.3 -- three false version citations, one of them
# fourteen minor levels above anything this language has ever released, which
# would drive the top of the dense range there and invent a phantom hole for
# every level in between.
#
# (Those three numbers are written WITHOUT their `v` prefix on purpose. This
# module is inside X001's scope, `VERSION_CITE_RE` requires the `v`, and the
# first draft of this comment spelled the Meson one `v` + `0.58` -- which
# S007 then reported, from this file, in the paragraph explaining the
# hazard. Round 464 walked around the identical trap for decision ids one
# docstring above; `tests/test_specreg.py::
# test_this_module_cites_no_unsectioned_version` is the pin.)
#
# The scope was never wrong about the tree. It was wrong about which files
# are the tree.
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "research-env",
             "whence_lang.egg-info", ".pytest_cache",
             ".venv", "venv", "site-packages", ".mypy_cache"}


def read_spec(path=None):
    with open(path or SPEC, encoding="utf-8") as f:
        return f.read()


def _line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def registry_span(text):
    """(start, end) character offsets of the registry section BODY.

    The section ends at the next `## ` heading, which is how
    `xref_check._section_body` bounds it too. A fenced block containing a
    `## ` line would end it early for both readers; there is none, and
    `test_specreg.py::test_the_two_registry_parsers_agree` is what notices
    if one ever appears.
    """
    m = re.search(r"^##\s+" + re.escape(REGISTRY_HEADING) + r"\s*$", text, re.M)
    if not m:
        return None
    start = m.end()
    nxt = re.search(r"^##\s", text[start:], re.M)
    end = start + nxt.start() if nxt else len(text)
    return start, end


def parse_registry(text):
    """[{id, line, title, tag_label, tag_round, body}] in document order."""
    span = registry_span(text)
    if span is None:
        return []
    start, end = span
    body = text[start:end]
    marks = list(ENTRY_RE.finditer(body))
    out = []
    for i, m in enumerate(marks):
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        entry = body[m.start():stop]
        title = _bold_title(entry)
        label, rnd = _parse_tag(title)
        out.append({
            "id": int(m.group(1)),
            "line": _line_of(text, start + m.start()),
            "title": title,
            "tag_label": label,
            "tag_round": rnd,
            "span": (start + m.start(), start + stop),
        })
    return out


def _bold_title(entry):
    """The `**…**` title of a registry entry, whitespace-collapsed.

    Returns "" when the bold never closes — a malformed entry, which
    `_parse_tag` then reports as untagged rather than crashing. A checker
    that raises on a bad corpus stops being run.
    """
    m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", entry, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def _parse_tag(title):
    """The trailing `(label, round R)` of a registry title -> (label, R).

    Three real forms in this document, all exercised by the corpus:

        `… (v0.20, round 348).`               -> ("v0.20", 348)
        `… (round 456).`                      -> (None, 456)
        `… (v0.12/v0.13 guest parity, round 338).`
                                              -> ("v0.12/v0.13 guest parity", 338)
        `… (v0.3).`                           -> ("v0.3", None)

    The LAST parenthetical only. Entry bodies quote rounds constantly (entry
    13 names rounds 338 and 345 in prose); reading anything but the tag would
    turn every historical aside into a coordinate claim, which is round 462's
    "one predicate, two questions" in this file's own key.
    """
    if not title:
        return None, None
    m = None
    for m in re.finditer(r"\(([^()]*)\)", title):
        pass
    if m is None:
        return None, None
    inner = m.group(1).strip()
    rm = ROUND_RE.search(inner)
    rnd = int(rm.group(1)) if rm else None
    label = inner[:rm.start()].rstrip(" ,;") if rm else inner
    return (label or None), rnd


def parse_sections(text):
    """[{id, line, level, heading}] for `Decision N` headings OUTSIDE the
    registry section."""
    span = registry_span(text)
    lo, hi = span if span else (0, 0)
    out = []
    for m in DECISION_HEAD_RE.finditer(text):
        if lo <= m.start() < hi:
            continue
        out.append({
            "id": int(m.group(3)),
            "line": _line_of(text, m.start()),
            "level": len(m.group(1)),
            "heading": m.group(2).strip(),
            "round": _first_round(m.group(2)),
        })
    return out


def _first_round(s):
    m = ROUND_RE.search(s)
    return int(m.group(1)) if m else None


def parse_versions(text):
    """{label: {line, round, heading}} for `## <label> (…)` headings.

    The label is everything before the parenthetical, which is exactly what
    a registry tag carries. `## v0.19 (round 344, landed by round 345;
    specified round 348)` yields round 344 — the FIRST round named, because
    the tag's round is the one that minted the decision and the later ones
    are the landing story.
    """
    out = {}
    for m in VERSION_HEAD_RE.finditer(text):
        label, paren = m.group(1).strip(), m.group(2)
        out.setdefault(label, {
            "line": _line_of(text, m.start()),
            "round": _first_round(paren),
            "heading": m.group(0).strip(),
        })
    return out


def parse_reserved(text):
    """[(lo, hi, line)] declared holes in the registry's numbering."""
    span = registry_span(text)
    if span is None:
        return []
    start, end = span
    return [(int(m.group(1)), int(m.group(2)), _line_of(text, start + m.start()))
            for m in RESERVED_RE.finditer(text[start:end])]


# --------------------------------------------------------------------------
# the version registry (round 486)
# --------------------------------------------------------------------------

def vkey(label):
    """`"v0.14.10"` -> `(0, 14, 10)`; `None` for anything not a version label.

    Sorting version labels as STRINGS puts v0.9 above v0.44 and v0.14.2 above
    v0.14.13. `test_v22.py`'s header pin already carries its own `_ver` helper
    with a comment saying so, which is the second writing of this function in
    this tree; `tests/test_specreg.py` pins the two orderings equal rather
    than importing, per this module's standing convention.
    """
    m = VERSION_LABEL_RE.match(label or "")
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def version_sections(text):
    """{label: info} for the `## vN (…)` headings only.

    `parse_versions` returns EVERY `## <label> (…)` heading, because a
    registry tag may point at a prose-titled one (`## Decision 50 (round
    420)`, `## Records as data / self-hosting (v0.5, round 014)`). This is the
    subset that is a version LEVEL, which is the sequence density is a claim
    about. At round 486's HEAD: 70 headings, 60 of them version levels.
    """
    return {label: info for label, info in parse_versions(text).items()
            if vkey(label) is not None}


def version_citations(repo=REPO, spec_text=None):
    """{label: [(rel, line)]} -- every `vN.N` written anywhere in X001's scope.

    A version token in this tree is a CITATION in exactly X001's sense. A
    comment reading `#: v0.47 (round 482), decision 60.` and a docstring
    reading `v0.45 returned [] for the empty list` are both promises that a
    reader can look v0.47 / v0.45 up, and there is only one place to look.

    SPEC.md's own `## vN (…)` heading lines are excluded, mirroring what
    `citations()` does with a decision's own definition sites: a definition is
    not a reader of itself. Everything else in SPEC.md counts -- including the
    `*Spec level: **vN**` header, which is a genuine claim about the document.

    A trailing `.0` is normalised away by `_normalise`, below.
    """
    text = spec_text if spec_text is not None else read_spec()
    own_lines = {info["line"] for info in version_sections(text).values()}

    hits = {}
    for rel in _in_scope_files(repo):
        try:
            with open(os.path.join(repo, rel), encoding="utf-8",
                      errors="replace") as f:
                body = f.read()
        except OSError:
            continue
        is_spec = (rel == SPEC_REL)
        # `body.count("\n", 0, pos)` per match is what `citations()` does, and
        # it is fine there: `decision <N>` matches a few dozen times per file.
        # A version token matches thousands of times in
        # `state/research-state.md` (30 000 lines), and count-from-zero is
        # O(len) each, so the pair is O(n*m). Measured round 486: 8.07 s for
        # the audit, against a 20 s tier budget on a box where `nproc` is 1
        # and the driver runs four suites at once. One newline index per file
        # and a bisect takes it to the number in the round file.
        starts = [0] + [m.end() for m in NEWLINE_RE.finditer(body)]
        for m in VERSION_CITE_RE.finditer(body):
            line = bisect.bisect_right(starts, m.start())
            if is_spec and line in own_lines:
                continue
            hits.setdefault(_normalise("v" + m.group(1)), []).append((rel, line))
    return hits


def _normalise(label):
    """`"v0.44.0"` -> `"v0.44"`. Every other label is returned unchanged.

    ROUND 486. This tree spells one version level two ways.
    `languages/whence/CHANGELOG.md` -- a TRACKED file this program does not
    own (`state/known-standing-dirty-paths.json` lists it; it arrived in
    `3658e02`, "chore(whence): Production release v0.44 …", which is not a
    round commit) -- writes `## [v0.44.0]`, `## [v0.19.0]`, `## [v0.14.0]` in
    the three-component semver form. SPEC.md writes `## v0.44`.

    They are the same level, and the collapse is unambiguous *in this
    document's convention* rather than in general: the third component here
    means a patch release, this document has seven of them (v0.14.1-.14,
    v0.16.1-.6, v0.17.1), and NOT ONE is `.0`. So a trailing zero cannot be a
    patch level and can only be the semver spelling of the two-component one.
    `test_no_version_section_ends_in_a_zero_patch` asserts that precondition
    rather than trusting it, because the day somebody mints a section whose
    label ends `.0` this normalisation starts merging two real levels. (That
    sentence named such a label in its first draft and S007 reported it, from
    this file, for the third time in one round -- see `SKIP_DIRS`.)
    """
    return label[:-2] if re.fullmatch(r"v\d+\.\d+\.0", label or "") else label


# --------------------------------------------------------------------------
# citations
# --------------------------------------------------------------------------

def _in_scope_files(repo=REPO):
    for base in ("languages/whence", "knowledge"):
        root = os.path.join(repo, base)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in sorted(filenames):
                if fn.endswith(CITE_SUFFIXES):
                    rel = os.path.relpath(os.path.join(dirpath, fn), repo)
                    if CITE_SCOPE_RE.match(rel):
                        yield rel
    rs = "state/research-state.md"
    if os.path.exists(os.path.join(repo, rs)):
        yield rs


def citations(repo=REPO, spec_text=None):
    """{id: [(rel, line)]} over X001's scope, EXCLUDING each id's own
    definition sites in SPEC.md.

    "Own definition" is the registry entry's own character span and the
    `Decision N` heading line. A cross-reference from ANOTHER entry counts —
    entry 42's title names decision 41's table, and that is a real pointer,
    not a self-mention. `S006` is a claim about readers, and one registry
    entry reading another is a reader.
    """
    text = spec_text if spec_text is not None else read_spec()
    own = {}
    for e in parse_registry(text):
        own.setdefault(e["id"], []).append(e["span"])
    sec_lines = {}
    for s in parse_sections(text):
        sec_lines.setdefault(s["id"], set()).add(s["line"])

    hits = {}
    for rel in _in_scope_files(repo):
        try:
            with open(os.path.join(repo, rel), encoding="utf-8",
                      errors="replace") as f:
                body = f.read()
        except OSError:
            continue
        is_spec = (rel == SPEC_REL)
        for m in CITE_RE.finditer(body):
            n = int(m.group(1))
            line = body.count("\n", 0, m.start()) + 1
            if is_spec:
                if any(lo <= m.start() < hi for lo, hi in own.get(n, ())):
                    continue
                if line in sec_lines.get(n, ()):
                    continue
            hits.setdefault(n, []).append((rel, line))
    return hits


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------

class Finding:
    def __init__(self, code, severity, line, message):
        self.code, self.severity = code, severity
        self.line, self.message = line, message

    def __str__(self):
        return "%s:%s: %s %s %s" % (SPEC_REL, self.line, self.severity,
                                    self.code, self.message)

    def as_dict(self):
        return {"code": self.code, "severity": self.severity,
                "line": self.line, "message": self.message}


def audit(repo=REPO, spec_text=None, with_citations=True):
    text = spec_text if spec_text is not None else read_spec()
    entries = parse_registry(text)
    sections = parse_sections(text)
    versions = parse_versions(text)
    reserved = parse_reserved(text)
    by_id = {}
    for e in entries:
        by_id.setdefault(e["id"], []).append(e)
    sec_by_id = {}
    for s in sections:
        sec_by_id.setdefault(s["id"], []).append(s)

    f = []

    # S002 collisions, first: every later check reads a set, and a set is
    # what hides this one.
    for n, es in sorted(by_id.items()):
        if len(es) > 1:
            f.append(Finding("S002", "ERROR", es[1]["line"],
                             "decision %d has %d registry entries (lines %s) "
                             "— a set-based reader counts one"
                             % (n, len(es),
                                ", ".join(str(e["line"]) for e in es))))
    for n, ss in sorted(sec_by_id.items()):
        if len(ss) > 1:
            f.append(Finding("S002", "ERROR", ss[1]["line"],
                             "decision %d has %d prose sections (lines %s)"
                             % (n, len(ss),
                                ", ".join(str(s["line"]) for s in ss))))

    # S001 minted but unregistered.
    for n, ss in sorted(sec_by_id.items()):
        if n not in by_id:
            f.append(Finding("S001", "ERROR", ss[0]["line"],
                             "decision %d has a prose section (%r) and NO "
                             "entry in %s — the registry's max is %s, so the "
                             "next round to mint a number reuses %d"
                             % (n, ss[0]["heading"][:60], REGISTRY_HEADING,
                                max(by_id) if by_id else "n/a", n)))

    # S003 undeclared holes.
    minted = set(by_id) | set(sec_by_id)
    if minted:
        for n in range(1, max(minted) + 1):
            if n in by_id:
                continue
            if any(lo <= n <= hi for lo, hi, _ in reserved):
                continue
            if n in sec_by_id:
                continue          # already S001; one finding per fact
            f.append(Finding("S003", "ERROR", registry_span(text) and
                             _line_of(text, registry_span(text)[0]) or 0,
                             "decision %d is absent from the registry and "
                             "covered by no declared reserved range" % n))

    # S004 tag vs the heading it points at.
    for e in entries:
        n, label, rnd = e["id"], e["tag_label"], e["tag_round"]
        if rnd is None:
            continue
        if label:
            v = versions.get(label)
            if v is None:
                f.append(Finding("S004", "ERROR", e["line"],
                                 "decision %d is tagged %r but no `## %s (…)` "
                                 "heading exists in this document"
                                 % (n, label, label)))
            elif v["round"] is not None and v["round"] != rnd:
                f.append(Finding("S004", "ERROR", e["line"],
                                 "decision %d says round %d; `## %s` at line "
                                 "%d says round %d"
                                 % (n, rnd, label, v["line"], v["round"])))
        else:
            ss = sec_by_id.get(n) or []
            owned = [s for s in ss if s["round"] is not None]
            if owned and owned[0]["round"] != rnd:
                f.append(Finding("S004", "ERROR", e["line"],
                                 "decision %d says round %d; its prose "
                                 "section at line %d says round %d"
                                 % (n, rnd, owned[0]["line"],
                                    owned[0]["round"])))

    # S005 untagged, above the declared floor.
    for e in entries:
        if e["id"] >= TAG_FLOOR and e["tag_round"] is None:
            f.append(Finding("S005", "WARN", e["line"],
                             "decision %d carries no `round N` in its tag "
                             "(floor is %d; entries below it predate the "
                             "convention)" % (e["id"], TAG_FLOOR)))

    cites = citations(repo, text) if with_citations else {}
    if with_citations:
        for e in entries:
            if not cites.get(e["id"]):
                f.append(Finding("S006", "WARN", e["line"],
                                 "decision %d is cited nowhere outside its "
                                 "own definition" % e["id"]))

    # ---- the version registry (round 486) --------------------------------
    #
    # Same three questions S001/S003/S006 ask of the decision registry, asked
    # of the OTHER dense ordinal sequence in this document. The one that
    # matters is S007, and the reason it matters is structural rather than
    # cosmetic: `test_v22.py::test_spec_level_header_matches_the_highest_
    # version_section` computes the top of the range from the SECTIONS, so the
    # range it checks is dense by construction and its top is whatever the
    # document already says. The top is actually set by the CODE.
    vsecs = version_sections(text)
    vcites = version_citations(repo, text) if with_citations else {}
    top_line = max((i["line"] for i in vsecs.values()), default=0)

    def _in_namespace(label):
        """This document mints the `v0.*` namespace and no other.

        ROUND 486, and this cost the family its first run. `VERSION_CITE_RE`
        over prose is not a Whence-version detector, it is a `vN.N` detector,
        and X001's scope is the whole of `knowledge/` — where round 106 names
        a server `v1.7.0`, rounds 105 and 111 name a skills schema `v4.1` /
        `v4.2`, and `languages/whence/CHANGELOG.md` links
        `semver.org/spec/v2.0.0.html`. Four foreign namespaces, none of them a
        claim about this language.

        The first draft had no namespace test, so S008's `hi` came out
        `(4, 2)` and its `while n <= hi` walked `(0, 6), (0, 7), …` — which
        never reaches `(4, 2)`, because a minor cannot overtake a major. It
        did not raise; it appended findings until it was killed. That is why
        S008 below iterates an explicit `range()` over one major.
        """
        k = vkey(label)
        return k is not None and k[0] == VERSION_FLOOR[0] and k >= VERSION_FLOOR

    # S007 cited but unsectioned -- S001's question for versions.
    dangling = sorted((l for l in vcites if _in_namespace(l) and l not in vsecs),
                      key=vkey)
    for label in dangling:
        where = vcites[label]
        top = max(vsecs, key=vkey) if vsecs else "none"
        f.append(Finding(
            "S007", "ERROR", top_line,
            "version %s is claimed in %d place(s) (%s) and has no `## %s (…)` "
            "section; the highest section is %s"
            % (label, len(where),
               ", ".join("%s:%d" % w for w in where[:3])
               + (", …" if len(where) > 3 else ""),
               label, top)))

    # S008 a hole in the MINOR sequence -- S003's question for versions.
    #
    # Density is claimed over the minor component only. The sub-version
    # dimension is deliberately sparse (v0.14 has .1-.14, v0.16 has .1-.6,
    # v0.17 has .1, and nothing else has any), so asking it to be dense would
    # invent a hole under every level that never needed a patch release.
    major = VERSION_FLOOR[0]
    known = {vkey(l)[1] for l in vsecs if _in_namespace(l)}
    known |= {vkey(l)[1] for l in vcites if _in_namespace(l)}
    for minor in range(VERSION_FLOOR[1], (max(known) if known else 0) + 1):
        if minor in known:
            continue
        f.append(Finding("S008", "ERROR", top_line,
                         "version v%d.%d is a hole: no `## v%d.%d` section "
                         "and nothing in scope claims it, but v%d.%d and "
                         "v%d.%d both exist"
                         % (major, minor, major, minor,
                            VERSION_FLOOR[0], VERSION_FLOOR[1],
                            major, max(known))))

    # S009 the tag that could point at a version and does not.
    #
    # S004 has two branches. An entry tagged `(v0.44, round 452)` is checked
    # against the version heading; an entry tagged `(round 456)` is checked
    # against its own prose section -- two writings by the same round in the
    # same file, which agree by construction. Registry entries 54-60 (rounds
    # 456-482) ALL carry the second form, so S004's version branch has had no
    # new subject since entry 53 and could not have seen v0.45/46/47 go
    # missing. This is the warning that stops the next one.
    by_round = {}
    for label, info in vsecs.items():
        if info["round"] is not None:
            by_round.setdefault(info["round"], label)
    for e in entries:
        if e["tag_label"] or e["tag_round"] is None:
            continue
        label = by_round.get(e["tag_round"])
        if label:
            f.append(Finding("S009", "WARN", e["line"],
                             "decision %d is tagged `(round %d)` with no "
                             "label while `## %s` at line %d names the same "
                             "round — S004's version branch cannot see this "
                             "entry; tag it `(%s, round %d)`"
                             % (e["id"], e["tag_round"], label,
                                vsecs[label]["line"], label, e["tag_round"])))

    # S010 the header line, which is the version registry's own summary.
    hdr = re.search(r"^\*Spec level: \*\*(v\d+\.\d+(?:\.\d+)*)\*\*", text, re.M)
    if vsecs:
        top = max(vsecs, key=vkey)
        if hdr is None:
            f.append(Finding("S010", "ERROR", 1,
                             "no `*Spec level: **vN**` header line; the "
                             "highest section is %s" % top))
        elif hdr.group(1) != top:
            f.append(Finding("S010", "ERROR", _line_of(text, hdr.start()),
                             "header says %s; the highest `## vN` section is "
                             "%s" % (hdr.group(1), top)))

    f.sort(key=lambda x: (x.severity != "ERROR", x.code, x.line))
    return {
        "findings": f,
        "entries": entries,
        "sections": sections,
        "versions": versions,
        "version_sections": vsecs,
        "version_citations": {k: len(v) for k, v in vcites.items()},
        "reserved": reserved,
        "citations": {k: len(v) for k, v in cites.items()},
        "next": next_free(text),
    }


def registry_ids(text=None):
    return {e["id"] for e in parse_registry(text if text is not None
                                            else read_spec())}


def minted_ids(text=None):
    """Every id defined at ANY site. The set a round must not collide with."""
    t = text if text is not None else read_spec()
    return registry_ids(t) | {s["id"] for s in parse_sections(t)}


def next_free(text=None):
    """The next decision number a round may mint.

    `max(every site) + 1`, then walked forward past any declared reserved
    range. Derived from all three sites on purpose: reading the registry
    alone is what produces the collision this module exists to prevent.
    """
    t = text if text is not None else read_spec()
    ids = minted_ids(t)
    reserved = parse_reserved(t)
    n = (max(ids) + 1) if ids else 1
    while any(lo <= n <= hi for lo, hi, _ in reserved):
        n += 1
    return n


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _print_table(res):
    sec = {}
    for s in res["sections"]:
        sec.setdefault(s["id"], []).append(s)
    print("  id  reg-line  tag                       round  section  cites")
    for e in res["entries"]:
        ss = sec.get(e["id"], [])
        print("  %3d  %8d  %-24s  %5s  %7s  %5d"
              % (e["id"], e["line"], (e["tag_label"] or "-")[:24],
                 e["tag_round"] if e["tag_round"] is not None else "-",
                 ss[0]["line"] if ss else "-",
                 res["citations"].get(e["id"], 0)))
    reg = {e["id"] for e in res["entries"]}
    for n in sorted(set(sec) - reg):
        print("  %3d  %8s  %-24s  %5s  %7d  %5d   << NOT IN REGISTRY"
              % (n, "-", "-",
                 sec[n][0]["round"] if sec[n][0]["round"] is not None else "-",
                 sec[n][0]["line"], res["citations"].get(n, 0)))


def _print_versions(res):
    """One row per version LEVEL — the second registry, side by side with the
    only two things that can disagree about it: whether the document has a
    section, and whether the tree claims the number."""
    vsecs = res["version_sections"]
    vcites = res["version_citations"]
    labels = sorted(set(vsecs) | {l for l in vcites if vkey(l) is not None},
                    key=vkey)
    print("  version      line  round  section  claims")
    for label in labels:
        info = vsecs.get(label)
        k = vkey(label)
        if info:
            note = ""
        elif k[0] != VERSION_FLOOR[0]:
            note = "   -- outside the v%d.* namespace, not a finding" % (
                VERSION_FLOOR[0],)
        elif k < VERSION_FLOOR:
            note = "   -- below VERSION_FLOOR v%d.%d, not a finding" % (
                VERSION_FLOOR)
        else:
            note = "   << CLAIMED, NO SECTION  (S007)"
        print("  %-10s  %5s  %5s  %7s  %5d%s"
              % (label,
                 info["line"] if info else "-",
                 (info["round"] if info and info["round"] is not None
                  else "-"),
                 "yes" if info else "NO",
                 vcites.get(label, 0), note))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cmd", choices=("audit", "table", "versions", "next"))
    p.add_argument("--json", metavar="OUT")
    p.add_argument("--spec", metavar="PATH", default=None)
    a = p.parse_args(argv)

    text = read_spec(a.spec)
    if a.cmd == "next":
        print(next_free(text))
        return 0

    # A `--spec` document is synthetic; scanning the live tree for
    # citations of ITS ids would mix two corpora. S006 is a claim about
    # this repo and is only asked when this repo's SPEC is the subject.
    res = audit(spec_text=text, with_citations=a.spec is None)
    if a.cmd == "table":
        _print_table(res)
    if a.cmd == "versions":
        _print_versions(res)

    errs = [x for x in res["findings"] if x.severity == "ERROR"]
    warns = [x for x in res["findings"] if x.severity != "ERROR"]
    if a.cmd == "audit":
        for x in res["findings"]:
            print(x)
    reserved = ", ".join("%d-%d" % (lo, hi) for lo, hi, _ in res["reserved"])
    print("specreg: %d registry entr(ies), %d prose section(s), %d version "
          "heading(s), reserved %s; next free is %d"
          % (len(res["entries"]), len(res["sections"]), len(res["versions"]),
             reserved or "none", res["next"]))
    vsecs = res["version_sections"]
    hdr = re.search(r"^\*Spec level: \*\*(v[\d.]+)\*\*", text, re.M)
    print("specreg: %d version level(s), highest %s; header says %s"
          % (len(vsecs), max(vsecs, key=vkey) if vsecs else "none",
             hdr.group(1) if hdr else "absent"))
    print("specreg: %d error(s), %d warning(s)" % (len(errs), len(warns)))

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({
                "findings": [x.as_dict() for x in res["findings"]],
                "entries": [{k: v for k, v in e.items() if k != "span"}
                            for e in res["entries"]],
                "sections": res["sections"],
                "reserved": [{"lo": lo, "hi": hi, "line": ln}
                             for lo, hi, ln in res["reserved"]],
                "citations": res["citations"],
                "version_sections": res["version_sections"],
                "version_citations": res["version_citations"],
                "next": res["next"],
            }, f, indent=1, sort_keys=True)
            f.write("\n")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
