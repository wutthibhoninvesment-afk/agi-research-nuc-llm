#!/usr/bin/env python3
"""specstale.py — a version-named section is a DATE STAMP, and prose inside
one that is written in the present tense reads as current forever.

Round 507 (skills B). Closes round 506's next-step #4.

The defect this is built from
-----------------------------
`SPEC.md:1508` sat inside `## v0.12 (round 122) — structural types` and said,
in the present tense:

    `fn f(a: num, b: Point) { … }` desugars, in the parser, to one leading
    `let a = typed(a, "num", "parameter 'a' of f")` per annotated parameter

That was true when written and stopped being true at **v0.19 (round 344)**,
which moved the parameter contract onto the function node
(`parser._param_contracts`) and applies it in the host
(`interp._check_contract`). The sentence was never marked. Round 506 banked
four of its nine predictions on it, read it as current, and lost all four.

Round 506's own next step says the obvious thing: *"The file has ~50 version
sections and this round has no evidence its bullet was the only stale one —
it is the only one anybody tripped over."*

The signal, and why it is mechanical
------------------------------------
The thing that made round 506's site knowable was not the tense. It was that
**somewhere else in the tree, a comment states the WINDOW**:

    parser.py:2072   "v0.12-v0.18 instead PREPENDED one
                      `let <param> = typed(<param>, <spec>, <label>)` ..."

A version RANGE written down anywhere is a claim that some behaviour held
from A to B and does not hold now. That claim has SUBJECTS — the backticked
identifiers in the sentence that makes it — and it has a WINDOW. Every
`## vN` section whose version falls inside that window and talks about those
same subjects is, by construction, describing history. It must say so.

So the rule is:

    A SPEC section whose version lies inside a stated range, and which
    shares subject terms with the sentence that states the range, must
    carry a staleness marker — the range itself, a `Stale-note correction`,
    or one of a small closed set of past-tense markers. Otherwise: T001.

This is an over-approximation on purpose, in the same spirit as
`harness/readset.py`'s blast radius: the output is a shortlist to READ, the
population is small enough to read, and a false positive costs a minute
while a false negative costs a round's predictions. `--strict` is the
ratchet; the default is the report.

What it deliberately does NOT do
--------------------------------
* **No tense detection.** English present tense is not a closed class and a
  grammar-guessing checker would be a worse instrument with a more confident
  voice. The section-is-in-a-window test does the work; the tense is what a
  READER then confirms.
* **No claim that an unstated range is safe.** T002 reports the other
  direction — a range statement whose window contains NO section at all —
  because that is the shape where this instrument is blind, and a blind spot
  nobody prints is a blind spot nobody knows about.

Usage:
    python3 specstale.py                     # report over SPEC.md + sources
    python3 specstale.py --list              # every range statement + window
    python3 specstale.py --strict            # exit 1 on any unmarked T001
    python3 specstale.py --spec /tmp/old.md  # replay against another file

Exit codes: 0 = nothing unmarked (or not --strict), 1 = unmarked T001 under
--strict, 2 = usage/IO problem.
"""

import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

#: The repo root, reached the ONE sanctioned way (round 413). NOT
#: `join(HERE, "..", "..")`: under `harness/swe/mutation.py` this tree is
#: copied to a tempdir and that expression resolves out of the copy, in
#: silence. `harness/swe/copyparity.py escapes` is the checker; round 504
#: wrote `builtinlive.py` with the unguarded spelling and reopened three
#: `harness/tests/test_swe_copyparity_real_subject.py` nodes for round 505,
#: and round 507 wrote THIS file the same way and reopened the same three
#: for rounds 507-509. `harness/swe/proc.py` exports `AGI_RESEARCH_ROOT`
#: into every sandbox subprocess; outside one the var is unset and this is
#: byte-for-byte the path the old expression produced.
AGI_ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
            or os.path.dirname(os.path.dirname(HERE)))
DEFAULT_SPEC = os.path.join(HERE, "SPEC.md")
DEFAULT_SOURCES = ("whence/parser.py", "whence/interp.py", "whence/values.py",
                   "whence/lexer.py", "specreg.py", "run.py")

# `v0.12-v0.18`, `v0.4–v0.6` (en dash), `v0.14.3-v0.15`. The second version
# may drop its `v`. Anchored on a `v` so a bare `0.12-0.18` (a ratio, a
# tolerance) is not a version range.
RANGE_RE = re.compile(
    r"\bv(\d+\.\d+(?:\.\d+)?)\s*[-–—]+\s*v?(\d+\.\d+(?:\.\d+)?)\b")

# `## v0.19 (round 344) — ...`, `### v0.14 guest parity (round 164)`.
HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)$")
HEADING_VERSION_RE = re.compile(r"\bv(\d+\.\d+(?:\.\d+)?)\b")

BACKTICK_RE = re.compile(r"`([^`\n]{1,120})`")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]{2,}")

# Terms too common to carry evidence of shared subject matter. Kept SHORT and
# explicit: every entry here is a term this corpus uses in every section, so
# an overlap on it means nothing. A long list would quietly become the rule.
STOPWORDS = frozenset("""
    the and for not but with from that this into over under round rounds
    line lines file files name names value values node nodes call calls
    test tests case cases code type types self none true false def class
    return returns list str num bool int float dict set len print
    whence spec lang python host guest parser interp
""".split())

# A section is MARKED when it says, in any of these ways, that what follows
# is history. The range string itself counts and is the strongest of them:
# round 506's repair put `v0.12-v0.18` into the v0.12 section, which is the
# section naming its own window.
MARKER_RES = tuple(re.compile(p, re.I) for p in (
    r"stale-note correction",
    r"\bsuperseded\b",
    r"\bno longer\b",
    r"\bused to\b",
    r"\bas of v\d",
    r"\bsince \*?\*?v\d",
    r"read (?:the rest of )?this .{0,30}as .{0,20}history",
    r"\bhistorical\b",
))


ACK_FILE = os.path.join("state", "whence", "specstale-acknowledged.json")


def block_key(version, block_text):
    """A CONTENT pin for one bullet: its version plus a digest of its first
    non-empty line.

    Deliberately not a file:line. Round 462 of this program measured that a
    SPEC line number is not durable — its own repair moved a section 29 lines
    down inside one round — and round 507's three corrections moved every
    line below 1592. Keyed on content, an acknowledgement survives an edit
    elsewhere in the file and EXPIRES when the bullet it excuses is rewritten,
    which is the behaviour wanted from both directions.
    """
    head = next((l.strip() for l in block_text.split("\n") if l.strip()), "")
    return "v%s|%s" % (vstr(version),
                       hashlib.sha1(head.encode("utf-8")).hexdigest()[:12])


def load_acknowledged(repo_root, path=None):
    try:
        with open(os.path.join(repo_root, path or ACK_FILE),
                  encoding="utf-8") as f:
            return json.load(f).get("blocks", {})
    except (OSError, ValueError):
        return {}


class Section:
    """One version-named heading and everything under it, to the next
    heading of the same or shallower depth."""

    def __init__(self, path, depth, line_no, title, version, start, end):
        self.path, self.depth, self.line_no = path, depth, line_no
        self.title, self.version = title, version
        self.start, self.end = start, end     # 0-based line indices [start, end)
        self.text = ""

    def __repr__(self):                       # pragma: no cover - debugging
        return "<Section v%s %s:%d>" % (vstr(self.version), self.path,
                                        self.line_no)


class Finding:
    def __init__(self, path, line_no, code, message, level="SUSPECT",
                 score=0.0):
        self.path, self.line_no = path, line_no
        self.code, self.message, self.level = code, message, level
        self.score = score

    def __str__(self):
        return "%s:%d: %s %s [%.2f] %s" % (self.path, self.line_no,
                                           self.level, self.code, self.score,
                                           self.message)


def vtuple(text):
    """`0.14.3` -> (0, 14, 3); `0.14` -> (0, 14, 0). One length, so ordinary
    tuple comparison orders `v0.14` before `v0.14.1` before `v0.15`."""
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def vstr(v):
    return "%d.%d" % v[:2] if v[2] == 0 else "%d.%d.%d" % v


def sections(text, path):
    """Every version-named section of a markdown file, in file order.

    A heading counts if a version appears in it. The section ends at the
    next heading of the SAME OR SHALLOWER depth, so `### v0.14 guest parity`
    nested under `## v0.14` does not truncate its parent.
    """
    lines = text.split("\n")
    heads = []
    for i, ln in enumerate(lines):
        m = HEADING_RE.match(ln)
        if m:
            heads.append((i, len(m.group(1)), m.group(2)))
    out = []
    for idx, (i, depth, title) in enumerate(heads):
        vm = HEADING_VERSION_RE.search(title)
        if not vm:
            continue
        end = len(lines)
        for j, d, _ in heads[idx + 1:]:
            if d <= depth:
                end = j
                break
        s = Section(path, depth, i + 1, title.strip(), vtuple(vm.group(1)),
                    i, end)
        s.text = "\n".join(lines[i:end])
        out.append(s)
    return out


def block_around(lines, i, radius=10):
    """The paragraph a line sits in: outward from `i` until a blank line, a
    fence, or `radius` lines. Used as a range statement's CONTEXT.

    A fixed window would drag in a neighbouring bullet's identifiers and
    inflate every overlap; a paragraph is the unit both markdown bullets and
    Python comment blocks are actually written in.
    """
    def stop(ln):
        s = ln.strip()
        return not s or s.startswith("```")
    lo = i
    while lo > 0 and i - lo < radius and not stop(lines[lo - 1]):
        lo -= 1
    hi = i
    while hi + 1 < len(lines) and hi - i < radius and not stop(lines[hi + 1]):
        hi += 1
    return "\n".join(lines[lo:hi + 1])


def terms(text):
    """Subject terms: identifiers found INSIDE backticks, minus stopwords.

    Backticks only. Prose words are shared by every section of a design
    document; a backticked `_param_contracts` is a subject. This is the one
    decision that keeps the overlap test meaningful rather than universal.
    """
    out = set()
    for span in BACKTICK_RE.findall(text):
        for ident in IDENT_RE.findall(span):
            low = ident.lower()
            if low not in STOPWORDS:
                out.add(low)
    return out


# A sentence boundary is a full stop or semicolon followed by something a
# sentence starts with. `v\d` is in that set because in this corpus the most
# common way to open a sentence about history is the version itself —
# "... for a `-> Type`. v0.12-v0.18 erased a PARAMETER annotation further" —
# and leaving it out meant the one sentence shape this instrument exists to
# read was the one shape it never split on.
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z`(]|v\d)")
LINE_FURNITURE_RE = re.compile(r"^\s*(?:[#>]+|[-*+]\s|\d+\.\s)\s*")


def claiming_sentence(paragraph, raw):
    """The one sentence that makes the range claim, not the paragraph.

    THE SECOND SCOPE ERROR of this file's first draft, found the same way as
    the first. `parser.py:388` is a fourteen-line comment about
    `PRIMITIVE_TYPES`; only its third sentence says `v0.12-v0.18 erased a
    PARAMETER annotation further, into a prepended `typed(...)` guard`. Taking
    the paragraph's subjects took `param_types`, `ret_type`, `A.NameRef`,
    `FnDef` and `guess` along with `typed`, and every one of those matches
    thirty unrelated sections. A claim's subject is what the CLAIMING
    sentence names.

    Falls back to the paragraph when the sentence carries no backticked term
    at all — a claim with no subject is better over-matched than dropped,
    and the fallback is counted so the report can say how often it fires.
    """
    # Strip each line's leading comment/bullet furniture BEFORE joining.
    # Without this a Python comment block never splits into sentences at all:
    # the splitter needs a capital or a backtick after the full stop and
    # finds a `#`, so every `.py` claim silently took its whole paragraph
    # and `parser.py:388` contributed five identifiers it does not talk
    # about. Found by a synthetic test failing, not by the corpus — the
    # corpus was quietly wrong and looked fine.
    flat = " ".join(LINE_FURNITURE_RE.sub("", l).strip()
                    for l in paragraph.split("\n"))
    for sent in SENTENCE_SPLIT_RE.split(flat):
        if raw in sent:
            if terms(sent):
                return sent, False
            return paragraph, True
    return paragraph, True


def range_statements(text, path):
    """Every `vA-vB` claim in a file, with its claiming sentence and terms."""
    lines = text.split("\n")
    out = []
    for i, ln in enumerate(lines):
        for m in RANGE_RE.finditer(ln):
            lo, hi = vtuple(m.group(1)), vtuple(m.group(2))
            if hi < lo:
                lo, hi = hi, lo
            para = block_around(lines, i)
            sent, widened = claiming_sentence(para, m.group(0))
            out.append({
                "path": path, "line_no": i + 1, "lo": lo, "hi": hi,
                "raw": m.group(0), "context": para, "sentence": sent,
                "widened": widened, "terms": terms(sent),
            })
    return out


# A block is one bullet, or one paragraph. Column-0 `- ` starts a new bullet;
# a blank line ends whatever was open. THE UNIT MATTERS MORE THAN THE RULES
# AROUND IT — see `is_marked`.
BLOCK_START_RE = re.compile(r"^(?:[-*+]\s|\d+\.\s|#{2,6}\s)")


def blocks(section_text, first_line):
    """(line_no, text) for every bullet/paragraph of a section.

    The first draft of this file made both the overlap test and the marker
    test SECTION-scoped, and it produced a clean, plausible, entirely false
    answer: replayed against the pre-round-506 SPEC it reported 34 findings
    and **not** the one site round 506 had proved stale. The cause was here.
    `## v0.12 (round 122)` is 132 lines and carries a `Stale-note correction
    (round 240)` about an unrelated bullet, so one marker anywhere in it
    marked the whole thing — a section that has EVER been corrected was
    permanently exempt from every future finding.

    A staleness marker is a property of a SENTENCE. Treating it as a
    property of its section is the same error one level up as the rule it
    was written to catch: text that was true where it was written, read as
    if it governed everything around it.
    """
    lines = section_text.split("\n")
    out, buf, start = [], [], 0
    def flush():
        if any(l.strip() for l in buf):
            out.append((first_line + start, "\n".join(buf)))
    for i, ln in enumerate(lines):
        if BLOCK_START_RE.match(ln) or (not ln.strip() and buf):
            flush()
            buf, start = ([ln] if ln.strip() else []), i
        else:
            buf.append(ln)
    flush()
    return out


def is_marked(text, stmt):
    """True if this BLOCK already says it is describing history.

    Scoped to the block on purpose; see `blocks`.
    """
    if stmt["raw"] in text:
        return True
    # `v0.12-v0.18` and `v0.12–v0.18` are the same marker written two ways.
    for m in RANGE_RE.finditer(text):
        if (vtuple(m.group(1)), vtuple(m.group(2))) == (stmt["lo"], stmt["hi"]):
            return True
    return any(rx.search(text) for rx in MARKER_RES)


def doc_freq(secs):
    """term -> how many version sections mention it."""
    df = {}
    for sec in secs:
        for t in terms(sec.text):
            df[t] = df.get(t, 0) + 1
    return df


def rarity_score(overlap, df, n_sections):
    """Sum of (1 - df/n) over the shared terms.

    A term nothing else mentions scores ~1; a term half the document
    mentions scores ~0.5. This is the RANK, and ranking is what makes the
    report usable WITHOUT a threshold that deletes the founding case: round
    507 measured that `--min-overlap 2` cuts the pre-506 replay from 67
    findings to 6 and takes the one known-true finding with them, while
    ranking leaves every finding in the output and lifts that one.
    """
    if not n_sections:
        return 0.0
    return sum(1.0 - df.get(t, 0) / float(n_sections) for t in overlap)


# Below this many sections a document-frequency filter measures nothing: on
# two sections every term is in 50% of them. Synthetic documents and small
# specs get the unfiltered vocabulary, which is the honest answer.
MIN_SECTIONS_FOR_DF = 8


def common_terms(secs, max_df):
    """Terms so widespread across version sections that sharing one is not
    evidence of shared subject matter — measured, not listed.

    `STOPWORDS` above is a hand list and hand lists grow until they become
    the rule. This is the corpus answering the same question for itself: at
    the default cutoff, `let` (53% of sections) is dropped and `typed` (14%)
    is kept, which is the discrimination the instrument needs and the one a
    threshold on the OVERLAP COUNT cannot make — round 507 measured that
    raising `--min-overlap` to 2 buys quiet by deleting the one finding this
    tool was built to reproduce.
    """
    if max_df >= 1.0 or len(secs) < MIN_SECTIONS_FOR_DF:
        return set()
    df = {}
    for sec in secs:
        for t in terms(sec.text):
            df[t] = df.get(t, 0) + 1
    return {t for t, n in df.items() if n / float(len(secs)) > max_df}


def audit(spec_text, spec_path, sources, min_overlap=1, max_df=0.25,
          window_mode="low", acknowledged=None):
    """Returns (findings, stats). `sources` is a list of (path, text).

    `window` is the single most important knob and the last one round 507
    tried, after three that failed. A range `vA-vB` says a behaviour held
    from A to B — but the behaviour was SPECIFIED at A. Sections A+1..B
    merely lived with it, and they are where every false positive came
    from: the type-system vocabulary is shared by all thirty sections that
    `v0.12-v0.18` spans, so matching on it means nothing there and
    everything at v0.12 itself.

      "low"  (default) — only sections whose version IS the low end.
      "all"             — every section in [A, B]. Higher recall in
                          principle, and measured at 67 findings to find
                          the 1 known-true one; kept so the claim above can
                          be re-derived rather than believed.
    """
    secs = sections(spec_text, spec_path)
    stmts = list(range_statements(spec_text, spec_path))
    for path, text in sources:
        stmts.extend(range_statements(text, path))
    acknowledged = acknowledged or {}
    seen_keys = set()
    df = doc_freq(secs)
    common = common_terms(secs, max_df)
    for st in stmts:
        st["terms"] -= common

    findings = []
    n_pairs = n_marked = n_empty = n_ack = 0
    for st in stmts:
        if window_mode == "low":
            win = [s for s in secs if s.version == st["lo"]]
        else:
            win = [s for s in secs if st["lo"] <= s.version <= st["hi"]]
        # A statement inside a section of its OWN window is that section
        # describing itself, not a later section narrating it.
        win = [s for s in win
               if not (s.path == st["path"]
                       and s.start < st["line_no"] <= s.end)]
        if not win:
            n_empty += 1
            findings.append(Finding(
                st["path"], st["line_no"], "T002",
                "range %s names a window with no version section in %s — "
                "this statement is outside what the instrument can check"
                % (st["raw"], os.path.basename(spec_path)), level="BLIND"))
            continue
        for sec in win:
            for line_no, block in blocks(sec.text, sec.line_no):
                overlap = st["terms"] & (terms(block) - common)
                if len(overlap) < min_overlap:
                    continue
                n_pairs += 1
                if is_marked(block, st):
                    n_marked += 1
                    continue
                key = block_key(sec.version, block)
                seen_keys.add(key)
                if key in acknowledged:
                    n_ack += 1
                    continue
                findings.append(Finding(
                    spec_path, line_no, "T001",
                    "in v%s section %r, inside the range %s stated at %s:%d; "
                    "shares %d subject term(s) %s and carries no staleness "
                    "marker — this bullet reads as current"
                    % (vstr(sec.version), sec.title[:48], st["raw"],
                       st["path"], st["line_no"], len(overlap),
                       "/".join(sorted(overlap)[:6])),
                    score=rarity_score(overlap, df, len(secs))))
    # The expiry control. An acknowledgement whose bullet no longer exists
    # (rewritten, re-marked, or deleted) is a claim about nothing, and a
    # baseline that only ever shrinks silently is how a suppression file
    # outlives its subject. Same shape as this repo's content-pinned
    # standing-dirty and known-absent registries.
    for key, entry in sorted(acknowledged.items()):
        if key not in seen_keys:
            findings.append(Finding(
                ACK_FILE, 1, "T003",
                "acknowledgement %s (%r) matches no unmarked block any more "
                "— the bullet it excused was rewritten, re-marked or "
                "deleted; drop the entry"
                % (key, str(entry.get("head", ""))[:60]), level="EXPIRED"))

    stats = {"sections": len(secs), "statements": len(stmts),
             "acknowledged": n_ack,
             "expired": sum(1 for f in findings if f.code == "T003"),
             "widened": sum(1 for st in stmts if st["widened"]),
             "pairs": n_pairs, "marked": n_marked, "blind": n_empty,
             "window": window_mode,
             "common_terms": len(common),
             "unmarked": sum(1 for f in findings if f.code == "T001")}
    return findings, stats


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--spec", default=DEFAULT_SPEC,
                    help="the version-sectioned document (default: SPEC.md "
                         "beside this script). Point it at a file dumped "
                         "from git to replay history.")
    ap.add_argument("--source", action="append", default=None,
                    help="extra file to scan for range statements "
                         "(repeatable; default: the whence implementation)")
    ap.add_argument("--max-df", type=float, default=0.25,
                    help="drop a subject term appearing in more than this "
                         "FRACTION of version sections; 1.0 disables "
                         "(default: 0.25)")
    ap.add_argument("--min-overlap", type=int, default=1,
                    help="subject terms a section must share with a range "
                         "statement before it is reported (default: 1)")
    ap.add_argument("--list", action="store_true",
                    help="print every range statement and its window")
    ap.add_argument("--acknowledged", default=None,
                    help="baseline of hand-audited false positives "
                         "(default: %s, content-pinned)" % ACK_FILE)
    ap.add_argument("--no-ack", action="store_true",
                    help="ignore the baseline entirely — what a fresh "
                         "auditor sees")
    ap.add_argument("--emit-ack", action="store_true",
                    help="print a baseline skeleton for the current "
                         "findings, reasons left blank for a human")
    ap.add_argument("--window", choices=("low", "all"), default="low",
                    help="which sections a range statement is checked "
                         "against: just the version it starts at (default) "
                         "or every version it spans")
    ap.add_argument("--top", type=int, default=12,
                    help="print only the N highest-ranked findings (rarity-"
                         "weighted subject overlap); 0 prints all. The count "
                         "on the summary line is always the full one.")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any T001 is unmarked")
    ap.add_argument("--json", default=None, help="write the findings here")
    args = ap.parse_args(argv)

    try:
        spec_text = read(args.spec)
    except OSError as e:
        print("cannot read %s: %s" % (args.spec, e), file=sys.stderr)
        return 2

    src_paths = args.source if args.source is not None else [
        os.path.join(HERE, p) for p in DEFAULT_SOURCES]
    sources = []
    for p in src_paths:
        try:
            sources.append((os.path.relpath(p, HERE), read(p)))
        except OSError:
            continue          # a source that is not in this checkout

    repo_root = AGI_ROOT
    ack = {} if args.no_ack else load_acknowledged(repo_root, args.acknowledged)
    findings, stats = audit(spec_text, args.spec, sources, args.min_overlap,
                            args.max_df, args.window, ack)

    if args.list:
        secs = sections(spec_text, args.spec)
        stmts = list(range_statements(spec_text, args.spec))
        for p, t in sources:
            stmts.extend(range_statements(t, p))
        for st in sorted(stmts, key=lambda s: (s["path"], s["line_no"])):
            win = [s for s in secs if st["lo"] <= s.version <= st["hi"]]
            print("%s:%d  %-14s window=%d section(s) %s  terms=%d"
                  % (st["path"], st["line_no"], st["raw"], len(win),
                     ",".join("v" + vstr(s.version) for s in win) or "-",
                     len(st["terms"])))

    ranked = sorted(findings, key=lambda f: (f.code, -f.score, f.line_no))
    shown = ranked[:args.top] if args.top else ranked
    for f in shown:
        print(f)
    if args.top and len(ranked) > args.top:
        # Round 433's no-silent-caps rule: a bounded report says what it cut.
        print("... %d more finding(s) below rank %d, suppressed by --top; "
              "re-run with --top 0 to see them"
              % (len(ranked) - args.top, args.top))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"findings": [f.__dict__ for f in findings],
                       "stats": stats}, fh, indent=1, sort_keys=True)
    if args.emit_ack:
        secs = sections(spec_text, args.spec)
        by_version = {s.line_no: s for s in secs}
        out = {}
        for f in findings:
            if f.code != "T001":
                continue
            sec = max((s for s in secs if s.line_no <= f.line_no),
                      key=lambda s: s.line_no)
            for line_no, block in blocks(sec.text, sec.line_no):
                if line_no == f.line_no:
                    head = next((l.strip() for l in block.split("\n")
                                 if l.strip()), "")
                    out[block_key(sec.version, block)] = {
                        "head": head[:120], "reason": "FILL IN: why this "
                        "bullet is NOT stale, from reading it"}
        print(json.dumps({"blocks": out}, indent=1, ensure_ascii=False,
                         sort_keys=True))

    print("specstale: %d version section(s), %d range statement(s), "
          "%d term(s) dropped as common (--max-df %g); "
          "%d claim(s) had no backticked subject and fell back to their "
          "paragraph; %d (statement, block) pair(s) share a subject: "
          "%d already marked, %d hand-acknowledged, %d UNMARKED; "
          "%d statement(s) name an empty window (T002, the blind spot); "
          "%d expired acknowledgement(s) (T003)"
          % (stats["sections"], stats["statements"], stats["common_terms"],
             args.max_df, stats["widened"], stats["pairs"], stats["marked"],
             stats["acknowledged"], stats["unmarked"], stats["blind"],
             stats["expired"]))
    return 1 if (args.strict and (stats["unmarked"] or stats["expired"])) \
        else 0


if __name__ == "__main__":
    sys.exit(main())
