#!/usr/bin/env python3
"""xref_check.py — check that every IDENTIFIER this workspace CITES is
actually DEFINED somewhere a reader can look it up.

Why this exists
---------------
`skill_lint.py` (round 333) checks that a markdown link's `#fragment`
resolves to a real anchor. `claim_check.py` (round 339) checks that a
Verification block's `# expected: ...` claims are still true. Both stop at
the SKILL.md corpus, and both check *links* and *numbers*.

This workspace also cites a third thing constantly, and nothing checks it:
**bare identifiers that promise a lookup**. `SPEC decision 29`, `house rule
D-013`, `B002`. They read as pointers into a registry. Round 345 found that
three of the four such families in this tree have citations that point
nowhere:

    decision 27/28/29   cited 12x across SPEC.md, parser.py, ast_nodes.py,
                        values.py, test_v12.py, test_v13.py — and SPEC.md's
                        canonical numbered list stops at 13. Decisions 14-26
                        were never minted at all; the namespace jumps.
    D-013               cited 22x as "house rule D-013", including by
                        CURRICULUM.md, which says the hard rules live in
                        CLAUDE.md's `## Ground rules` — a section that
                        exists and is EMPTY.
    B002/R006/C001...   clean, all 8 cited codes are emitted by a script.
                        Checked here so it STAYS clean.

The mechanism is worth naming, because it is a property of long-running
autonomous programs rather than of this repo: **an identifier namespace with
no registry drifts.** A round writes `(decision 29)` because the phrase
"decision N" *looks* like it indexes a registry; appending to the actual
registry is a separate, skippable step; and no reader ever fails loudly,
because a dangling identifier renders as ordinary prose. Rot accumulates in
exactly the places that read most authoritative.

The design consequence, and the one idea to take away
-----------------------------------------------------
**A definition is an entry in a DECLARED REGISTRY, and nothing else.** This
tool does not guess whether a line "looks like" a definition. Every family
below names the file+section (or the code) that is its registry; anything
outside that is a citation. That is what makes the D-013 result exact rather
than heuristic: the registry is declared (`CLAUDE.md` § `Ground rules`), it
is found, it contains zero entries, so all 22 citations dangle. A
definition-sniffing heuristic would instead have seen
`## D-013 prediction ledger` in `nuc/nuc-bench-final.md`, called it a
definition, and reported the corpus clean — a FALSE NEGATIVE, which for an
unwatched checker is strictly worse than a false positive.

Three file scopes, because a citation's meaning depends on when it was written
-----------------------------------------------------------------------------
    authoritative   what a reader is expected to act on TODAY. Findings here
                    are errors.
    historical      `knowledge/round-NNN-*.md`, the research-state archive,
                    banked prediction files. Dated records: a path that was
                    correct when written and renamed later is HISTORY, not
                    rot. Counted and reported, never an error.
    frozen          `state/swe/`, `state/fuzz/`, `state/mutation/` — SWE-loop
                    fixtures containing whole snapshot copies of the project
                    (`state/swe/round-137/orig-proj/SPEC.md` is a second copy
                    of the decisions list). Excluded entirely; a snapshot's
                    references are about the snapshot.

Usage:
    python3 xref_check.py                 # sweep the workspace
    python3 xref_check.py --list          # every citation with its verdict
    python3 xref_check.py --historical    # also report the historical scope
    python3 xref_check.py PATH [PATH ...] # restrict to these files

Exit codes: 0 = no dangling citations in the authoritative scope, 1 = at
least one, 2 = usage/IO problem.
"""

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))

# --------------------------------------------------------------------------
# Scopes
# --------------------------------------------------------------------------
# Directories whose contents are never scanned at all. `node_modules` and
# `.git` are obvious; the `state/` three are SWE-loop fixtures that contain
# entire snapshot copies of `languages/whence/`, including its own SPEC.md.
# Scanning them would double-count every citation in the project and report
# findings against a tree nobody is meant to edit.
# Two kinds, and they must not be conflated. `__pycache__` is frozen wherever
# it appears; `state/swe` is frozen only at the repo root. The first draft
# matched both as "this substring appears anywhere in the path", which made
# an ordinary `nuc/state/swe/` directory frozen too — a silent coverage hole,
# the worst failure mode a checker has.
FROZEN_NAMES = (".git", "node_modules", "__pycache__", ".pytest_cache",
                ".venv")
FROZEN_PREFIXES = ("state/swe", "state/fuzz", "state/mutation",
                   "state/trigger-eval")

# The instrument does not measure itself. `skills/*/scripts/` holds the
# corpus checkers (`skill_lint.py`, `claim_check.py`, this file) and their
# tests. Both QUOTE dangling identifiers on purpose — this file's own
# docstring names `D-013` six times while explaining that `D-013` dangles,
# and `test_claim_check.py` is full of deliberately-broken fixture paths
# like `harness/tests/gone.py` whose whole job is to be missing. Counting
# those as findings would mean the checker's evidence for a defect is
# itself reported as that defect.
#
# This is a NAMED BLIND SPOT, not a free pass: real rot inside these files
# is invisible to the sweep, and the summary line says so with the count.
# The alternative — a per-line opt-out marker — was rejected as more
# machinery than the one directory it would serve.
SELF_EXEMPT_RE = re.compile(r"^skills/[^/]+/scripts/")

# Dated records. Their citations are reported under --historical and never
# raise an error: a knowledge file is a snapshot of what was true on its own
# date, and "correct when written" is the standard it is held to.
HISTORICAL_RE = re.compile(
    r"^(knowledge/"
    r"|state/research-state-archive\.md$"
    r"|state/round-\d+-predictions\.md$"
    r"|nuc/predictions-)")

SCANNED_EXTS = (".md", ".py", ".lang", ".sh")


def scope_of(rel):
    """Return 'frozen', 'historical' or 'authoritative' for a repo-relative
    path. Checked in that order — frozen wins over historical."""
    # NOT `lstrip("./")` — that strips leading DOTS as a character class, so
    # `.venv/...` became `venv/...` and stopped matching FROZEN_NAMES, quietly
    # pulling 1441 vendored files into the sweep. Found by eyeballing the
    # file count between two runs, not by a test; the regression test lives in
    # `test_a_dotted_top_level_directory_is_frozen`.
    norm = rel.replace(os.sep, "/")
    if norm.startswith("./"):
        norm = norm[2:]
    if any(part in FROZEN_NAMES for part in norm.split("/")):
        return "frozen"
    for d in FROZEN_PREFIXES:
        if norm == d or norm.startswith(d + "/"):
            return "frozen"
    if HISTORICAL_RE.match(norm):
        return "historical"
    return "authoritative"


def walk_files(repo_root):
    """Yield (abs_path, rel_path, scope) for every scannable file."""
    for dirpath, dirnames, filenames in os.walk(repo_root):
        rel_dir = os.path.relpath(dirpath, repo_root)
        dirnames[:] = [d for d in sorted(dirnames)
                       if scope_of(os.path.join(rel_dir, d)
                                   if rel_dir != "." else d) != "frozen"]
        for fn in sorted(filenames):
            if not fn.endswith(SCANNED_EXTS):
                continue
            rel = os.path.normpath(os.path.join(rel_dir, fn)) \
                if rel_dir != "." else fn
            sc = scope_of(rel)
            if sc == "frozen":
                continue
            yield os.path.join(dirpath, fn), rel.replace(os.sep, "/"), sc


# --------------------------------------------------------------------------
# Registries
# --------------------------------------------------------------------------

ORDINAL_ITEM_RE = re.compile(r"^(\d+)\.\s+\*\*", re.M)
ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.M)


def ordinal_registry(repo_root, doc, heading):
    """Entries of a markdown ordinal list living under `heading` in `doc`.

    Returns (ids, status). `status` is one of 'ok', 'no-doc', 'no-section',
    'empty' — reported verbatim, because "the registry is missing" and "the
    registry is present but empty" are different diagnoses and this tool
    exists precisely to keep them distinguishable.

    Only `N. **Bold** ...` items count. That is this repo's convention for a
    real registry entry (SPEC.md's decision list uses it for all 13), and it
    excludes the many ordinary numbered procedure lists elsewhere in the same
    documents — which are steps, not definitions.
    """
    path = os.path.join(repo_root, doc)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set(), "no-doc"
    section = _section_body(text, heading)
    if section is None:
        return set(), "no-section"
    ids = {int(m.group(1)) for m in ORDINAL_ITEM_RE.finditer(section)}
    return ids, ("ok" if ids else "empty")


def _headings(heading):
    """Normalise a spec's heading to a list.

    A registry may legitimately span more than one section of its document.
    `D-013` is a HOUSE rule but the operator filed it under the Track E hard
    rules, while `## Ground rules` is where a general one would go -- so the
    house-rule registry is both sections, and declaring only one is what let
    round 345 read a populated document as an empty registry. Union, not
    first-match: an id is defined if ANY declared section defines it, and a
    reader should not have to know which.
    """
    return [heading] if isinstance(heading, str) else list(heading)


FENCE_RE = re.compile(r"^[ \t]*(```|~~~)", re.M)


def _fenced_spans(text):
    """[(start, end)] of fenced code blocks, so a `# comment` inside one is
    not mistaken for a heading.

    Latent rather than live when this was written -- none of the three
    declared registry sections contains a fence -- but it is this round's
    own failure mode one level down: a `#`-commented shell line inside a
    fenced example would END the section early and the registry would read
    SHORT, with no symptom except citations that dangle for no visible
    reason. Closed while the cost is one regex.
    """
    spans, open_at = [], None
    for m in FENCE_RE.finditer(text):
        if open_at is None:
            open_at = m.start()
        else:
            spans.append((open_at, m.end()))
            open_at = None
    if open_at is not None:          # unterminated fence: to end of document
        spans.append((open_at, len(text)))
    return spans


def _headings_outside_fences(text):
    spans = _fenced_spans(text)
    for m in ANY_HEADING_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue
        yield m


def _section_body(text, heading):
    """Body of the section whose heading text matches `heading`, up to the
    next heading of the SAME OR SHALLOWER level. Returns None if absent."""
    start = None
    level = None
    for m in _headings_outside_fences(text):
        if start is None:
            if m.group(2).strip().lower() == heading.strip().lower():
                start, level = m.end(), len(m.group(1))
            continue
        if len(m.group(1)) <= level:
            return text[start:m.start()]
    if start is None:
        return None
    return text[start:]


def token_registry(repo_root, doc, heading, id_re):
    """IDs that appear LITERALLY inside a declared registry section.

    The second registry kind, and the one an opaque ID needs. `decision N`
    is defined by the numbering of SPEC's list, so `ordinal_registry` reads
    the ordinals; `D-013` is defined by the token itself appearing in
    `CLAUDE.md` § `Ground rules`, so there is nothing to count — only to
    find.

    The first draft wired X002 to `ordinal_registry` and the unit test
    `test_populating_the_registry_clears_the_family` caught it: the registry
    yielded `{13}` (an int) while the citation was `'D-013'` (a str), so
    populating the section would NOT have cleared the family. The tool would
    have kept reporting 22 dangling citations after the exact fix it was
    asking for — a checker that cannot be satisfied gets muted, which is the
    same end state as a checker that cries wolf.
    """
    path = os.path.join(repo_root, doc)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return set(), "no-doc"
    sections = [s for s in (_section_body(text, h) for h in _headings(heading))
                if s is not None]
    if not sections:
        return set(), "no-section"
    ids = set()
    for section in sections:
        ids.update(id_re.findall(section))
    return ids, ("ok" if ids else "empty")


def emitted_code_registry(repo_root):
    """Rule codes any checker script actually emits, e.g. `err("R006", ...)`.

    A code-derived registry rather than a documented one: the authority on
    which codes exist is the code that prints them, and a documented list
    would itself need checking. Status is 'ok'/'empty' only — there is no
    "missing document" case to distinguish."""
    ids, lit = set(), re.compile(r'"([A-Z]\d{3})"')
    scripts_root = os.path.join(repo_root, "skills")
    for dirpath, dirnames, filenames in os.walk(scripts_root):
        dirnames[:] = [d for d in dirnames if d not in
                       ("__pycache__", ".pytest_cache")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            try:
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    ids.update(lit.findall(f.read()))
            except (OSError, UnicodeDecodeError):
                continue
    return ids, ("ok" if ids else "empty")


# --------------------------------------------------------------------------
# Registry provenance (round 346)
# --------------------------------------------------------------------------
# The sweep answers "is this citation resolvable TODAY". It deliberately does
# not answer the question a reader asks next, which is the one that decides
# who fixes it:
#
#     the registry is empty -- do I go and GET the text, or WRITE it?
#
# Those are different jobs with different owners and different risk.
# Transcribing a definition that already exists is repair, and any round may
# do it. Inventing the definition of a rule that governs every future round
# is authorship, and it is the operator's call. Round 345 had exactly this
# decision in front of it for `CLAUDE.md § Ground rules`, judged it
# authorship, and deferred -- reasonably, given what it knew. It was
# actually repair: the section's body is in this repo's git history at the
# initial commit `ee30654` and was destroyed by `e376750`. One `git log` on
# the registry document separates the two cases, and nothing was running it.
#
# So: for every id the sweep reports as dangling, ask the registry's own
# file history whether that id was EVER defined. `resurrectable` names the
# commit to transcribe from; `never-defined` is real authorship.
#
# Read-only. `git log` / `git show` only, no writes, no network.

GIT_SEP = "\x1f"


class RegistrySpec:
    """Where a registry lives, in enough detail to read it out of history.

    `kind` is 'ordinal' or 'token', mirroring the two registry readers --
    the distinction that round 345's section 3.2 bug proved is load-bearing
    (an ordinal registry yields ints, a token registry yields strings, and
    comparing one to the other silently never matches).
    """

    def __init__(self, doc, heading, kind, id_re=None):
        if kind not in ("ordinal", "token"):
            raise ValueError("kind must be 'ordinal' or 'token': %r" % kind)
        if kind == "token" and id_re is None:
            raise ValueError("a token registry needs an id_re")
        self.doc = doc
        self.headings = _headings(heading)
        self.heading = " + ".join(self.headings)
        self.kind = kind
        self.id_re = id_re

    def ids_in(self, text):
        """Ids defined by this registry inside `text`, a whole document.

        Returns (ids, status) with the same four statuses the live readers
        use, so a historical revision and the working tree are described in
        exactly one vocabulary.
        """
        sections = [s for s in (_section_body(text, h)
                                for h in self.headings) if s is not None]
        if not sections:
            return set(), "no-section"
        ids = set()
        for section in sections:
            if self.kind == "ordinal":
                ids.update(int(m.group(1))
                           for m in ORDINAL_ITEM_RE.finditer(section))
            else:
                ids.update(self.id_re.findall(section))
        return ids, ("ok" if ids else "empty")

    def has_body(self, text):
        """Does the declared section have ANY prose, ids or not?

        Split from `ids_in` because the first live run proved they are
        different questions. `CLAUDE.md § Ground rules` held seven numbered
        house rules at `ee30654` and none of them contained a `D-NNN` token,
        so an ids-only reading called the section "never populated" -- of a
        section whose 7-item body a later commit deleted. Reporting that as
        `never-populated` would have told a reader "there is nothing to
        recover" about text that is sitting in git.
        """
        return any((_section_body(text, h) or "").strip()
                   for h in self.headings)

    def locate_in_document(self, text):
        """{id: heading} for every id of this family ANYWHERE in `text`.

        The registry declaration can simply point at the wrong section, and
        that failure is invisible to a reader of the current file: the
        section is empty either way. Searching the whole document separates
        "the definition is gone" from "the definition is filed elsewhere",
        which have different fixes -- transcribe, versus correct the
        pointer and then transcribe.
        """
        if self.kind == "ordinal":
            pat, conv = ORDINAL_ITEM_RE, int
        else:
            pat, conv = self.id_re, str
        heads = [(m.start(), m.group(2).strip())
                 for m in _headings_outside_fences(text)]
        found = {}
        for m in pat.finditer(text):
            head = None
            for off, title in heads:
                if off < m.start():
                    head = title
                else:
                    break
            found.setdefault(conv(m.group(1)), head)
        return found


def _git(repo_root, argv, runner=subprocess.run):
    """One git invocation. Returns (ok, stdout). Never raises: an absent
    git, a non-repo directory and a path unknown to the index are all just
    "no history available", which the caller reports as `no-vcs` rather
    than crashing a checker that is otherwise pure file reads."""
    try:
        res = runner(["git", "-C", repo_root] + argv,
                     capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False, ""
    if res.returncode != 0:
        return False, ""
    return True, res.stdout


def file_revisions(repo_root, doc, max_commits=200, runner=subprocess.run):
    """[(sha, author_date_iso)] for `doc`, newest first. [] if unavailable.

    `--follow` is deliberately NOT used. It guesses at renames, and a wrong
    guess here would attribute someone else's section body to this registry
    -- inventing a definition, which is the one failure mode this whole
    family exists to prevent. A registry that moved between paths is
    reported as having a short history, which is honest.
    """
    ok, out = _git(repo_root,
                   ["log", "--format=%%H%s%%aI" % GIT_SEP,
                    "--max-count=%d" % max_commits, "--", doc],
                   runner=runner)
    if not ok:
        return []
    revs = []
    for line in out.splitlines():
        if GIT_SEP not in line:
            continue
        sha, _, date = line.partition(GIT_SEP)
        if sha.strip():
            revs.append((sha.strip(), date.strip()))
    return revs


def registry_history(repo_root, spec, max_commits=200, runner=subprocess.run):
    """Per-revision reading of one registry, newest first.

    Each element is {'sha', 'date', 'status', 'ids'}. A revision in which
    the document did not exist, or could not be decoded, is skipped rather
    than recorded as empty -- "absent" and "present but empty" are the very
    distinction this tool sells, and quietly folding one into the other in
    the history reader would undo it.
    """
    out = []
    for sha, date in file_revisions(repo_root, spec.doc, max_commits, runner):
        ok, text = _git(repo_root, ["show", "%s:%s" % (sha, spec.doc)],
                        runner=runner)
        if not ok:
            continue
        ids, status = spec.ids_in(text)
        out.append({"sha": sha, "date": date, "status": status,
                    "ids": ids, "body": spec.has_body(text),
                    "elsewhere": spec.locate_in_document(text)})
    return out


def provenance(repo_root, spec, dangling_ids, max_commits=200,
               runner=subprocess.run):
    """Was each dangling id EVER defined by this registry?

    Returns a dict with a registry-level `verdict` and a per-id verdict.

    Registry verdicts, ordered by how much there is to recover:
      ok               -- populated in the working tree; nothing to recover
      ids-deleted      -- the section defined ids in an ancestor and does
                          not now. The strongest case: transcribe.
      body-deleted     -- the section had prose in an ancestor and is empty
                          now, but never defined ids of this family under
                          THIS heading. Something was destroyed and is
                          recoverable, but the registry declaration may also
                          be pointing at the wrong section -- read the
                          per-id verdicts before acting.
      never-populated  -- no revision ever had a body here. AUTHORSHIP.
      no-vcs           -- no history readable (not a repo, no git, untracked)

    Per-id verdicts:
      resurrectable    -- defined under the declared heading in some
                          ancestor. Transcribing it is repair.
      elsewhere-in-doc -- the id is defined in the document's history but
                          under a DIFFERENT heading. The text is recoverable
                          AND the registry declaration is wrong. Two fixes.
      never-defined    -- absent from every revision. Authorship.

    Registry verdict and id verdicts are computed independently on purpose:
    a registry can read `ok` and still be missing a specific id that was
    deleted out of an otherwise healthy list, which no amount of looking at
    the current file reveals.
    """
    hist = registry_history(repo_root, spec, max_commits, runner)
    # "Is it populated NOW" is a question about the WORKING TREE, not about
    # HEAD. They differ for exactly as long as a fix is uncommitted, which
    # is precisely when someone is running this. Reading `hist[0]` for the
    # current state made the probe report `body-deleted` about a file that
    # had already been repaired on disk -- the same mistake as the first
    # draft, one level along: asking the right question of the wrong source.
    cur_ids, cur_status, cur_body = set(), "no-doc", False
    try:
        with open(os.path.join(repo_root, spec.doc), encoding="utf-8") as f:
            cur_text = f.read()
    except (OSError, UnicodeDecodeError):
        cur_text = None
    if cur_text is not None:
        cur_ids, cur_status = spec.ids_in(cur_text)
        cur_body = spec.has_body(cur_text)

    result = {"doc": spec.doc, "heading": spec.heading, "kind": spec.kind,
              "revisions": len(hist), "verdict": None, "last_populated": None,
              "last_body": None, "current_status": cur_status, "ids": {}}
    if not hist:
        result["verdict"] = "no-vcs"
        for ident in dangling_ids:
            result["ids"][ident] = {"verdict": "unknown", "sha": None,
                                    "date": None, "heading": None}
        return result

    with_ids = [r for r in hist if r["ids"]]
    with_body = [r for r in hist if r["body"]]
    if cur_ids:
        result["verdict"] = "ok"
    elif with_ids:
        result["verdict"] = "ids-deleted"
    elif with_body and not cur_body:
        result["verdict"] = "body-deleted"
    else:
        # Either no revision ever had a body here, or a body is present and
        # simply is not this registry. Same actionable state -- there is
        # nothing to transcribe -- so one verdict rather than a fifth that
        # nobody would know what to do with.
        result["verdict"] = "never-populated"
    if with_ids:
        result["last_populated"] = {"sha": with_ids[0]["sha"],
                                    "date": with_ids[0]["date"],
                                    "n_entries": len(with_ids[0]["ids"])}
    if with_body:
        result["last_body"] = {"sha": with_body[0]["sha"],
                               "date": with_body[0]["date"]}

    for ident in dangling_ids:
        hit = next((r for r in hist if ident in r["ids"]), None)
        if hit is not None:
            result["ids"][ident] = {"verdict": "resurrectable",
                                    "sha": hit["sha"], "date": hit["date"],
                                    "heading": hit["elsewhere"].get(
                                        ident, spec.heading)}
            continue
        other = next((r for r in hist if ident in r["elsewhere"]), None)
        if other is not None:
            result["ids"][ident] = {"verdict": "elsewhere-in-doc",
                                    "sha": other["sha"], "date": other["date"],
                                    "heading": other["elsewhere"][ident]}
            continue
        result["ids"][ident] = {"verdict": "never-defined", "sha": None,
                                "date": None, "heading": None}
    return result


# --------------------------------------------------------------------------
# Families
# --------------------------------------------------------------------------
# A family binds three things: how a CITATION is spelled, which files may
# contain one, and where its REGISTRY is. `cite_re` must expose the bare id
# as group 1.

class Family:
    def __init__(self, code, name, cite_re, registry, registry_desc,
                 scope_re=None, normalise=str, provenance=None):
        self.code = code
        self.name = name
        self.cite_re = cite_re
        self.registry = registry            # callable(repo_root) -> (ids, status)
        self.registry_desc = registry_desc
        self.scope_re = scope_re            # which rel paths may cite this
        self.normalise = normalise
        # Where this registry LIVES as a versioned file, so its history can
        # be read. `None` means the registry is not a tracked document and
        # a dangling id in it can never be resurrected -- X003's registry is
        # derived from live code, so "what did it used to be" is not a
        # question about a file. Keeping this explicit rather than inferring
        # it from `registry` is what stops the probe from silently reporting
        # `no-vcs` for a family that simply has no document.
        self.provenance = provenance        # RegistrySpec | None

    def applies_to(self, rel):
        return self.scope_re is None or self.scope_re.match(rel)


# Both sections of CLAUDE.md that carry numbered house rules. Round 345 read
# only the first and concluded the registry had never been populated; round
# 346's provenance probe found `D-013` defined under the second at `ee30654`.
# Adding a section here is how a future house rule filed somewhere new gets
# recognised -- the alternative, sniffing the whole document for `D-NNN`,
# would make any prose mention a definition.
HOUSE_RULE_SECTIONS = ("Ground rules",
                       "Track E — NUC integration: HARD RULES")

FAMILIES = [
    Family(
        "X001", "SPEC design decision",
        # `decision 29`, `SPEC decision 29`, `v0.18 decision 28`. Scoped to
        # the whence subtree plus research-state, which are the only places
        # that use "decision N" as a registry pointer; elsewhere the same two
        # words are ordinary English.
        re.compile(r"\bdecision\s+(\d+)\b", re.I),
        lambda root: ordinal_registry(
            root, "languages/whence/SPEC.md",
            "Anti-mainstream design decisions"),
        "languages/whence/SPEC.md § Anti-mainstream design decisions",
        # `knowledge/` is IN scope even though it is historical: every
        # `decision N` there is a SPEC pointer too (checked by hand over all
        # of them), and excluding it would have made the historical tier
        # unreachable for the one family that most needs it — findings there
        # are reported, never errors.
        scope_re=re.compile(
            r"^(languages/whence/|knowledge/|state/research-state)"),
        normalise=int,
        provenance=RegistrySpec(
            "languages/whence/SPEC.md",
            "Anti-mainstream design decisions", "ordinal"),
    ),
    Family(
        "X002", "house rule",
        re.compile(r"\b(D-\d{3})\b"),
        # CURRICULUM.md line 45: "Hard rules in CLAUDE.md: ... predictions
        # before measurements (D-013)". So the registry is declared by the
        # curriculum itself; this tool just takes it at its word.
        lambda root: token_registry(root, "CLAUDE.md", HOUSE_RULE_SECTIONS,
                                    re.compile(r"\b(D-\d{3})\b")),
        "CLAUDE.md § Ground rules + § Track E — NUC integration: HARD RULES",
        provenance=RegistrySpec("CLAUDE.md", HOUSE_RULE_SECTIONS, "token",
                                re.compile(r"\b(D-\d{3})\b")),
    ),
    Family(
        "X003", "lint rule code",
        re.compile(r"\b([A-Z]\d{3})\b"),
        emitted_code_registry,
        'string literals in skills/*/scripts/*.py',
        scope_re=re.compile(r"^skills/.*\.md$"),
        # No RegistrySpec: this registry is the union of literals across many
        # scripts, not a section of one document, so "what did it say before"
        # has no single file to ask. Reported as `not-a-document`, never as
        # `no-vcs` -- the tree IS versioned, the registry just is not a file.
        provenance=None,
    ),
]

# `[[slug]]` memory links. NOT a family: a dangling `[[name]]` is legal by
# design ("it marks something worth writing later, not an error"), so this is
# a tally, never a finding. Reported because an unmeasured tally is how the
# other three families got to 34 dangling citations unnoticed.
WIKILINK_RE = re.compile(r"\[\[([A-Za-z0-9_-]+)\]\]")
MEMORY_DIR = os.path.expanduser(
    "~/.claude/projects/-home-pgain-agi-research-nuc-llm/memory")

# --------------------------------------------------------------------------
# Prose paths (X004)
# --------------------------------------------------------------------------
# Deliberately the tightest rule in the file. `claim_check.py`'s C001 fought
# this exact fight over Verification-block commands and needed four
# suppression rules; the winning trick was that a token is only checkable if
# it is ANCHORED — its first component is itself a real directory. Applied
# here as a precondition rather than a fallback: a token is a candidate only
# if its first component is a top-level directory of THIS repo. Everything
# else (bare filenames, `foo/bar` from another project, `/tmp/...`) is not
# checked and is counted as skipped.
PATH_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]*[A-Za-z0-9_-]/[A-Za-z0-9_./-]+")
# `NNN`/`<x>`/globs are the documented template markers. The last alternative
# catches a path COMPONENT that is a single capital letter — `state/swe/
# round-N/` — which this repo uses as a metavariable exactly the way `NNN` is
# used, just shorter.
PLACEHOLDER_RE = re.compile(
    r"NNN|<|>|\*|\?|\{|\}|\$|\.\.\.|XXX|(?<![A-Za-z0-9])[A-Z](?![A-Za-z0-9])")

# The character immediately after a match decides whether the match is the
# WHOLE path or just as much of it as the character class could reach. This
# distinction is the entire false-positive story for X004, and it cost the
# first draft 340 findings of which every single one inspected was a
# truncation artifact:
#
#   `state/known-standing-`      <- hard-wrapped mid-path; the rest of the
#   dirty-paths.json`               name is on the NEXT LINE, so the token
#                                   as matched is a prefix that of course
#                                   does not exist
#   `logs/round-*.json`          <- `*` is not in the class, so the match
#                                   stops at `logs/round-` and PLACEHOLDER_RE
#                                   never gets to see the glob it was written
#                                   to suppress
#
# Both are the same bug wearing two hats: **a token truncated by its own
# delimiter is not evidence about anything.** So a match is only checkable
# when the next character is one that genuinely ENDS a path in prose. A
# newline is deliberately NOT in that set: this repo hard-wraps its markdown
# at ~72 columns, so end-of-line is the single most likely place for a path
# to be cut in half. That costs real recall on paths that legitimately end a
# line, which is why `paths_skipped` is reported beside `paths_checked`
# rather than left implicit.
PATH_TERMINATORS = set(" \t`)]},;:'\"!?")

# A test file's paths are FIXTURES. `test_run_driver_health_check.py` writes
# `harness/tests/test_x.py` into a tmp tree; `test_driver_health.py` names
# `logs/round-114.json` as a log that never existed. Both are supposed not to
# exist, for the same reason the checker scripts' own docstrings are exempt.
TEST_FILE_RE = re.compile(r"(^|/)test_[^/]*\.py$")

ABSENT_ALLOWLIST = os.path.join("state", "known-absent-paths.json")


BASELINE_FILE = os.path.join("state", "known-dangling-citations.json")


def load_baseline(repo_root, path=None):
    """Citations already known to dangle, keyed `CODE:identifier`.

    Same idea as `state/known-record-gaps.json`, which this repo already uses
    to keep a recurring check usable while a real backlog stays open. Without
    it this checker exits 1 forever on two registry gaps that are NOT its
    author's to close (one belongs to language(C)'s SPEC, one to the
    operator's CLAUDE.md), and a check that can never go green is a check
    people stop reading — the exact failure this tool was built to fix, one
    level up."""
    try:
        with open(os.path.join(repo_root, path or BASELINE_FILE),
                  encoding="utf-8") as f:
            return json.load(f).get("citations", {})
    except (OSError, ValueError):
        return {}


def load_absent_allowlist(repo_root):
    """Paths authoritative prose may legitimately name while they do not
    exist. Explicit and reviewable on purpose — see the file's own
    `_comment`, and `state/known-standing-dirty-paths.json` for the
    precedent this copies."""
    try:
        with open(os.path.join(repo_root, ABSENT_ALLOWLIST),
                  encoding="utf-8") as f:
            return set(json.load(f).get("paths", {}))
    except (OSError, ValueError):
        return set()


def top_level_dirs(repo_root):
    return {d for d in os.listdir(repo_root)
            if os.path.isdir(os.path.join(repo_root, d))
            and not d.startswith(".") and d != "node_modules"}


def resolve_prose_path(repo_root, tok, tops):
    """Return one of 'ok', 'prefix', 'prose', 'missing' for a path token.

    Two RECOVERY rules (they buy coverage back rather than suppress) and two
    IMPOSSIBILITY rules (the token cannot denote a path at all, so a miss is
    not evidence of rot):

      prefix (recovery)  — the exact token is absent but `tok*` matches
        something. This repo abbreviates constantly: `knowledge/round-019`
        for a file whose real name carries a slug, and
        `dest_dir="state/nuc-swap-watch"` for a default that gets `-r256`
        appended at call time. Both are resolvable by a reader and by a
        glob. Reported under its own counter, never silently folded into
        `ok`, because a prefix match is weaker evidence than an exact one.

      prose (impossibility) — `state/research-state.md/knowledge/git`. A
        PROPER PREFIX of the token exists and is a REGULAR FILE, so nothing
        can live below it; the slashes are prose ("...left zero trace in
        research-state.md / knowledge / git"). Stated as "you cannot descend
        into a file" rather than "an extension cannot appear mid-path",
        because `state/swe/round-149/repair-recheck.json/` is a real
        DIRECTORY in this very tree and the extension form would have been
        wrong about it.

      prose (impossibility) — `logs/state`, where BOTH components are
        top-level directories of this repo. That is "logs and state", not a
        path; verified against the tree that no real `<top>/<top>` exists.
    """
    if os.path.exists(os.path.join(repo_root, tok)):
        return "ok"
    parts = tok.split("/")
    if len(parts) == 2 and parts[0] in tops and parts[1] in tops:
        return "prose"
    for i in range(1, len(parts)):
        if os.path.isfile(os.path.join(repo_root, *parts[:i])):
            return "prose"
    parent = os.path.dirname(tok)
    base = os.path.basename(tok)
    pdir = os.path.join(repo_root, parent) if parent else repo_root
    try:
        if any(n.startswith(base) for n in os.listdir(pdir)):
            return "prefix"
    except OSError:
        pass
    return "missing"


def prose_path_tokens(text, tops):
    """Yield (token, offset, checkable) for path-looking tokens anchored at a
    top-level directory of this repo.

    `checkable` False means "this looks like a path but the tool cannot see
    all of it" — counted as skipped by the caller, never reported.
    """
    for m in PATH_TOKEN_RE.finditer(text):
        raw = m.group(0)
        head = raw.split("/")[0]
        if head not in tops:
            continue
        nxt = text[m.end()] if m.end() < len(text) else " "
        if nxt not in PATH_TERMINATORS:
            yield raw, m.start(), False        # truncated: not evidence
            continue
        tok = raw.rstrip(".,;:)")
        if PLACEHOLDER_RE.search(tok):
            yield tok, m.start(), False        # template, not a real path
            continue
        yield tok, m.start(), True


# --------------------------------------------------------------------------
# Sweep
# --------------------------------------------------------------------------

class Finding:
    def __init__(self, rel, line_no, code, message, scope, ident):
        self.rel, self.line_no = rel, line_no
        self.code, self.message, self.scope = code, message, scope
        self.ident = ident

    @property
    def key(self):
        """Baseline key: the CODE and the IDENTIFIER, never the file or line.

        Deliberately coarse. Line numbers churn every time a paragraph is
        rewrapped, so a file:line baseline would go stale within a round and
        get regenerated on autopilot — which is how a baseline stops being a
        record of accepted debt and becomes a rubber stamp. Keyed this way,
        acknowledging `X001:29` accepts EVERY site citing decision 29 and
        still flags the first citation of a decision the registry has
        never heard of. (Phrased without naming a number on purpose: a
        hypothetical ID written in prose is indistinguishable from a real
        citation, and this docstring would have minted one.)"""
        return "%s:%s" % (self.code, self.ident)

    def __str__(self):
        return "%s:%d: %s %s %s" % (
            self.rel, self.line_no,
            "DANGLING" if self.scope == "authoritative" else "historical",
            self.code, self.message)


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


def sweep(repo_root, only=None, want_list=False):
    """Returns (findings, stats). `only` restricts to those rel paths."""
    registries = {}
    for fam in FAMILIES:
        ids, status = fam.registry(repo_root)
        registries[fam.code] = (ids, status)
    tops = top_level_dirs(repo_root)
    absent_ok = load_absent_allowlist(repo_root)

    findings = []
    stats = {
        "files": 0, "historical_files": 0,
        "cited": {f.code: 0 for f in FAMILIES},
        "dangling_ids": {f.code: set() for f in FAMILIES},
        "paths_checked": 0, "paths_skipped": 0, "self_exempt_files": 0,
        "paths_prefix": 0, "paths_absent_ok": 0,
        "wikilinks": 0, "wikilinks_dangling": 0,
        "wikilink_slugs": set(), "wikilink_dangling_slugs": set(),
        "listing": [],
        "registries": registries,
    }
    memory_slugs = set()
    if os.path.isdir(MEMORY_DIR):
        memory_slugs = {os.path.splitext(f)[0]
                        for f in os.listdir(MEMORY_DIR) if f.endswith(".md")}
    stats["memory_slugs"] = memory_slugs

    for abs_path, rel, scope in walk_files(repo_root):
        if only is not None and rel not in only:
            continue
        try:
            with open(abs_path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        stats["files"] += 1
        if scope == "historical":
            stats["historical_files"] += 1

        self_exempt = SELF_EXEMPT_RE.match(rel) is not None
        if self_exempt:
            stats["self_exempt_files"] += 1
        for fam in FAMILIES:
            if self_exempt or not fam.applies_to(rel):
                continue
            known, status = registries[fam.code]
            for m in fam.cite_re.finditer(text):
                raw = m.group(1)
                try:
                    ident = fam.normalise(raw)
                except ValueError:
                    continue
                stats["cited"][fam.code] += 1
                ok = ident in known
                if want_list:
                    stats["listing"].append(
                        "%s:%d: %-4s %-8s %s" % (
                            rel, line_of(text, m.start()), fam.code, raw,
                            "ok" if ok else "DANGLING (registry: %s)"
                            % status))
                if ok:
                    continue
                stats["dangling_ids"][fam.code].add(raw)
                findings.append(Finding(
                    rel, line_of(text, m.start()), fam.code,
                    "%s %r is cited but not defined in its registry "
                    "(%s: %s)" % (fam.name, raw, fam.registry_desc, status),
                    scope, raw))

        # X004 — prose paths
        is_test = TEST_FILE_RE.search(rel) is not None
        for tok, off, checkable in prose_path_tokens(text, tops):
            if self_exempt or is_test or not checkable:
                stats["paths_skipped"] += 1
                continue
            verdict = resolve_prose_path(repo_root, tok, tops)
            if verdict == "prose":
                stats["paths_skipped"] += 1
                continue
            stats["paths_checked"] += 1
            if verdict == "ok":
                continue
            if verdict == "prefix":
                stats["paths_prefix"] += 1
                continue
            if tok in absent_ok:
                stats["paths_absent_ok"] += 1
                continue
            findings.append(Finding(
                rel, line_of(text, off), "X004",
                "path %r does not exist" % tok, scope, tok))

        # X005 — wikilink tally (never a finding)
        for m in WIKILINK_RE.finditer(text):
            slug = m.group(1)
            stats["wikilinks"] += 1
            stats["wikilink_slugs"].add(slug)
            if slug not in memory_slugs:
                stats["wikilinks_dangling"] += 1
                stats["wikilink_dangling_slugs"].add(slug)

    return findings, stats


def report(findings, stats, show_historical, baseline=None,
           show_acknowledged=False):
    baseline = baseline or {}
    auth = [f for f in findings if f.scope == "authoritative"]
    hist = [f for f in findings if f.scope == "historical"]
    known = [f for f in auth if f.key in baseline]
    new = [f for f in auth if f.key not in baseline]
    for f in new:
        print(f)
    if show_acknowledged:
        for f in known:
            print("%s  [acknowledged: %s]" % (f, baseline[f.key]))
    if show_historical:
        for f in hist:
            print(f)

    print("xref_check: %d file(s) scanned (%d historical, reported %s)"
          % (stats["files"], stats["historical_files"],
             "above" if show_historical else "only as a count"))
    for fam in FAMILIES:
        ids, status = stats["registries"][fam.code]
        dang = sorted(stats["dangling_ids"][fam.code])
        print("  %s %-22s registry %-9s %3d entr%s; %3d citation(s), "
              "%d dangling id(s)%s"
              % (fam.code, fam.name, status, len(ids),
                 "y" if len(ids) == 1 else "ies",
                 stats["cited"][fam.code], len(dang),
                 (": " + ", ".join(dang)) if dang else ""))
    n_x004 = sum(1 for f in findings if f.code == "X004")
    print("  X004 prose path           %d checked (%d exact, %d prefix-only, "
          "%d allowlisted-absent), %d missing, %d skipped"
          % (stats["paths_checked"],
             stats["paths_checked"] - stats["paths_prefix"]
             - stats["paths_absent_ok"] - n_x004,
             stats["paths_prefix"], stats["paths_absent_ok"], n_x004,
             stats["paths_skipped"]))
    print("  X005 memory wikilink      %d occurrence(s), %d distinct slug(s); "
          "%d occurrence(s) / %d slug(s) have no memory file "
          "(legal by design, tally only)"
          % (stats["wikilinks"], len(stats["wikilink_slugs"]),
             stats["wikilinks_dangling"],
             len(stats["wikilink_dangling_slugs"])))
    print("  blind spot: %d file(s) under skills/*/scripts/ exempt "
          "(the checkers themselves quote the rot they detect)"
          % stats["self_exempt_files"])
    print("xref_check: %d dangling citation(s) in the authoritative scope "
          "(%d NEW, %d pre-acknowledged in %s), %d in the historical scope"
          % (len(auth), len(new), len(known), BASELINE_FILE, len(hist)))
    return 1 if new else 0


def report_provenance(repo_root, only=None, max_commits=200,
                      runner=subprocess.run, out=None):
    """Print, for every family, whether its dangling ids are recoverable.

    Runs the ordinary sweep first, because the question is only meaningful
    about ids that actually dangle RIGHT NOW -- resurrecting an id nothing
    cites is busywork, and an id that resolves needs no owner. Exit code is
    0: this reports on debt, it does not gate on it. `--strict` on the main
    sweep is the gate.
    """
    pr = (lambda s: print(s, file=out)) if out is not None else print
    _, stats = sweep(repo_root, only=only)
    n_res = n_auth = 0
    pr("xref_check provenance: can each dangling citation be recovered "
       "from git, or must it be written?")
    for fam in FAMILIES:
        dang = sorted(stats["dangling_ids"][fam.code], key=str)
        if fam.provenance is None:
            pr("  %s %-22s registry not-a-document (%s)"
               % (fam.code, fam.name, fam.registry_desc))
            if dang:
                pr("      %d dangling id(s), none recoverable from a file: %s"
                   % (len(dang), ", ".join(str(d) for d in dang)))
            continue
        info = provenance(repo_root, fam.provenance, dang, max_commits,
                          runner=runner)
        lp, lb = info["last_populated"], info["last_body"]
        detail = ""
        if lp:
            detail = ("; last defined ids %s @ %s (%d entr%s)"
                      % (lp["date"][:10], lp["sha"][:7], lp["n_entries"],
                         "y" if lp["n_entries"] == 1 else "ies"))
        elif lb:
            detail = ("; last had a body %s @ %s, but never ids of this "
                      "family" % (lb["date"][:10], lb["sha"][:7]))
        pr("  %s %-22s registry %-16s %s (%d revision(s)%s)"
           % (fam.code, fam.name, info["verdict"], info["doc"],
              info["revisions"], detail))
        for ident in dang:
            v = info["ids"][ident]
            if v["verdict"] == "resurrectable":
                n_res += 1
                pr("      %-8s RESURRECTABLE -- defined under the declared "
                   "heading at %s (%s). Transcribing it is repair."
                   % (ident, v["sha"][:7], v["date"][:10]))
            elif v["verdict"] == "elsewhere-in-doc":
                n_res += 1
                pr("      %-8s RESURRECTABLE -- but under %r, not the "
                   "declared %r, at %s (%s). The text is recoverable AND "
                   "the registry declaration is mis-pointed: two fixes."
                   % (ident, v["heading"], info["heading"], v["sha"][:7],
                      v["date"][:10]))
            elif v["verdict"] == "never-defined":
                n_auth += 1
                pr("      %-8s never-defined in %d revision(s). Writing it "
                   "is authorship." % (ident, info["revisions"]))
            else:
                pr("      %-8s unknown (no readable history)" % ident)
    pr("xref_check provenance: %d dangling id(s) recoverable by transcription, "
       "%d require authorship" % (n_res, n_auth))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="*",
                    help="restrict the sweep to these files (default: the "
                         "whole workspace)")
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT)
    ap.add_argument("--list", action="store_true",
                    help="print every citation with its verdict")
    ap.add_argument("--baseline",
                    help="JSON of already-known dangling citations "
                         "(default: %s)" % BASELINE_FILE)
    ap.add_argument("--show-acknowledged", action="store_true",
                    help="also print findings the baseline already accepts")
    ap.add_argument("--historical", action="store_true",
                    help="also print findings from dated records "
                         "(knowledge/, the archive, prediction files)")
    ap.add_argument("--provenance", action="store_true",
                    help="instead of the sweep report, ask git whether each "
                         "dangling id was EVER defined (repair vs authorship)")
    ap.add_argument("--max-commits", type=int, default=200,
                    help="history depth per registry document for "
                         "--provenance (default: 200)")
    args = ap.parse_args(argv)

    repo_root = os.path.abspath(args.repo_root)
    if not os.path.isdir(repo_root):
        print("no such repo root: %s" % repo_root, file=sys.stderr)
        return 2
    only = None
    if args.paths:
        only = set()
        for p in args.paths:
            ap_ = os.path.abspath(p)
            if not os.path.exists(ap_):
                print("no such path: %s" % p, file=sys.stderr)
                return 2
            only.add(os.path.relpath(ap_, repo_root).replace(os.sep, "/"))

    if args.provenance:
        return report_provenance(repo_root, only=only,
                                 max_commits=args.max_commits)

    findings, stats = sweep(repo_root, only=only, want_list=args.list)
    if args.list:
        for line in stats["listing"]:
            print(line)
    return report(findings, stats, args.historical,
                  load_baseline(repo_root, args.baseline),
                  args.show_acknowledged)


if __name__ == "__main__":
    sys.exit(main())
