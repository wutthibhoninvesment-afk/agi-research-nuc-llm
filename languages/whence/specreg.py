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

Exit code is driven by ERRORS ONLY (round 363's rule: a check that goes FAIL
every round for a debt the program decided to carry gets ignored, then
uninstalled). The warning counts ride in the summary line.

Usage
-----
    python3 specreg.py audit            # findings; exit 1 if any ERROR
    python3 specreg.py table            # one row per id, all sites
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
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
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

# Entries 1-13 were written for v0.1-v0.4, before this program recorded a
# round beside a decision. A FLOOR, not a per-id allowlist: the exemption
# has to expire for every future entry automatically, which an allowlist
# would not do.
TAG_FLOOR = 27

# X001's own scope, restated (`xref_check.FAMILIES[0].scope_re`). Kept as a
# literal rather than imported so that `specreg.py` runs from a checkout of
# `languages/whence` alone; `tests/test_specreg.py` asserts the two agree.
CITE_SCOPE_RE = re.compile(r"^(languages/whence/|knowledge/|state/research-state)")
CITE_SUFFIXES = (".md", ".py", ".lang", ".txt")
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "research-env",
             "whence_lang.egg-info", ".pytest_cache"}


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

    f.sort(key=lambda x: (x.severity != "ERROR", x.code, x.line))
    return {
        "findings": f,
        "entries": entries,
        "sections": sections,
        "versions": versions,
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


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("cmd", choices=("audit", "table", "next"))
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
                "next": res["next"],
            }, f, indent=1, sort_keys=True)
            f.write("\n")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
