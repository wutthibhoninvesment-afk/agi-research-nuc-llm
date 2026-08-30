#!/usr/bin/env python3
"""state_claim_check.py — re-derive the checkable claims in the LIVE
"Next steps" block of a rolling status document, instead of trusting them.

Why this exists
---------------
`claim_check.py` (round 339) closed half of round 321's item 14: it
re-executes the `## Verification` claims in every SKILL.md. Round 333 said
the item's real scope was wider — *"any line asserting a number that no
round re-executes", covering SKILL.md Verification blocks and
`research-state.md` header lines together* — and round 334 repeated it.
This file is the other half.

The rot it catches has a specific, mechanical cause, and the cause is not
carelessness. `state/research-state.md` ends in a stack of
`## Next steps (as of round N)` blocks. Each round writes a new one, and it
writes it by **copying the previous round's block and editing the items it
touched**. An item nobody touched is therefore re-asserted verbatim, in a
fresh document, over the author's own name — with no step anywhere that
re-derives it. The idiom this corpus uses for those items, *"Standing and
unchanged: …"*, is an explicit assertion about the present tense, and it is
the one assertion in the file that is never checked.

The instance that forced this file (round 351):

    round 339  split `fuzz-mutate-kill-loop/SKILL.md` from 415 body lines
               to 399, closing an 8-round B002 backlog, and its own entry
               in research-state.md says so in bold.
    round 343  "fuzz-mutate-kill-loop/SKILL.md is still 415 body lines (B002)"
    round 346  same sentence
    round 347  same sentence
    round 348  same sentence
    round 349  same sentence, plus "8th consecutive round carried"

Five next-steps blocks re-asserting a number that the same file, 1000 lines
earlier, records as fixed. Nothing was lying; nothing was re-derived. The
number was 399 the whole time, and `skill_lint.py --house --strict` had been
exiting 0 on the corpus for ten rounds.

Scope: the LIVE block only
--------------------------
Only the block with the HIGHEST round number is checked. Older blocks are a
frozen record — `bash harness/run_tests_fast.sh` -> `412 passed` was true
when round 311 wrote it, and flagging it now would be both wrong and
permanent noise. This is the same authoritative/historical split
`xref_check.py` uses for CLAUDE.md.

"Highest round number", not "last block in the file": in the real
`research-state.md` the trailing stack is only roughly reverse-chronological
(round 341's block sits physically between round 343's and round 349's), so
file order is not chronology here. Checked, not assumed.

Findings
--------
`S001`  a body-line count that no longer matches the file.
`S002`  a lint code cited as currently firing (`… (B002)`) that `skill_lint`
        does not emit for that file any more.
`S003`  an inline `` `cmd` -> result `` claim whose command, re-run, prints
        something else. Requires `--run`; the command must classify `auto`
        under `claim_check.py`'s fail-closed allowlist, so nothing here can
        ssh, spend money, or write to the checkout.
`CARRIED` (never an error) the age of each extracted claim: how many
        distinct next-steps blocks assert it verbatim, and from which round.
        An age of 1 means this round derived it. An age of 11 means eleven
        rounds have signed their name to a sentence none of them re-ran.

Coverage is reported unconditionally, because the honest number is not "0
stale claims" but "0 stale of the N we can check, out of M items". A checker
nobody watches must have a zero false-positive rate even at the cost of
recall, and must publish the recall gap — round 339's rule, applied to its
own successor.

Usage:
    python3 state_claim_check.py state/research-state.md
    python3 state_claim_check.py --list state/research-state.md
    python3 state_claim_check.py --run state/research-state.md
    python3 state_claim_check.py --block 349 state/research-state.md

Exit codes: 0 = no stale claims, 1 = at least one, 2 = usage/IO problem.
"""

import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))

if HERE not in sys.path:                                  # pragma: no cover
    sys.path.insert(0, HERE)

# Reuse rather than re-implement. `classify` is the fail-closed allowlist that
# keeps this tool from running anything that costs money or leaves the box;
# `run_command`'s process-group kill is the fix for the orphaned-grandchild
# pitfall round 339 hit. Re-deriving either here would be a second copy to
# keep in sync — exactly what skills/copied-mirror-drift warns about.
import claim_check
import skill_lint


BLOCK_HEADING_RE = re.compile(r"^##\s+Next steps\s*\(as of round\s+(\d+)[^)]*\)",
                              re.M)
ITEM_START_RE = re.compile(r"^(\d+)\.\s")


# --------------------------------------------------------------------------
# Block and item extraction
# --------------------------------------------------------------------------

class Block:
    """One `## Next steps (as of round N)` section."""

    def __init__(self, round_no, first_line, lines):
        self.round_no = round_no
        self.first_line = first_line          # 1-based line of the heading
        self.lines = lines                    # body lines, heading excluded

    def __repr__(self):                       # pragma: no cover - debugging
        return "<Block round=%d line=%d>" % (self.round_no, self.first_line)


def find_blocks(text):
    """Every next-steps block in `text`, in file order."""
    lines = text.split("\n")
    starts = []
    for i, line in enumerate(lines):
        m = BLOCK_HEADING_RE.match(line)
        if m:
            starts.append((i, int(m.group(1))))
    blocks = []
    for idx, (i, round_no) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        # A block ends at the next next-steps heading OR at the first
        # `### Round N` entry after it, whichever comes first. Level 3 and
        # shallower, not level 2 and shallower: research-state.md interleaves
        # `### Round N — track` entries with next-steps blocks, and a block
        # that swallowed the following round entry would age and re-check
        # that entry's prose as if it were a live next step. No next-steps
        # block in this corpus contains a sub-heading of its own (asserted by
        # `test_no_live_corpus_block_loses_content_to_the_level_3_stop`).
        stop = end
        for j in range(i + 1, end):
            if re.match(r"^#{1,3}\s", lines[j]):
                stop = j
                break
        blocks.append(Block(round_no, i + 1, lines[i + 1:stop]))
    return blocks


def live_block(blocks):
    """The block a reader is meant to act on: the highest round number.

    Ties are an error rather than a guess — two blocks claiming the same
    round means the document itself is ambiguous about which one is current,
    and silently picking one would make every later finding unattributable.
    """
    if not blocks:
        return None, "no `## Next steps (as of round N)` block found"
    best = max(b.round_no for b in blocks)
    winners = [b for b in blocks if b.round_no == best]
    if len(winners) > 1:
        return None, ("%d blocks both claim round %d (lines %s) — cannot tell "
                      "which is live" %
                      (len(winners), best,
                       ", ".join(str(b.first_line) for b in winners)))
    return winners[0], None


class Item:
    """One numbered next-step, with its text unwrapped onto a single line.

    `char_lines[k]` is the 1-based FILE line that `text[k]` came from, so a
    finding on a claim that straddles a line break (`(`grep -c
    mutation_test\\n   harness/swe/campaign.py` -> 0)` in round 349's block)
    still reports the line the claim STARTS on rather than the line the item
    starts on.
    """

    def __init__(self, block, number, text, char_lines):
        self.block = block
        self.number = number
        self.text = text
        self.char_lines = char_lines

    def line_at(self, offset):
        if not self.char_lines:                           # pragma: no cover
            return self.block.first_line
        return self.char_lines[min(offset, len(self.char_lines) - 1)]


def parse_items(block):
    """Split a block into numbered items with wrapped lines joined.

    Joining is what makes the command grammar work at all: markdown prose in
    this file is hard-wrapped at ~72 columns, and a backticked command is
    wrapped like any other text, so half the claims in the corpus have a
    newline inside their backticks.
    """
    items = []
    cur_num = None
    parts = []          # list of (text, file_line)
    for offset, raw in enumerate(block.lines):
        file_line = block.first_line + 1 + offset
        m = ITEM_START_RE.match(raw)
        if m:
            if cur_num is not None:
                items.append(_build(block, cur_num, parts))
            cur_num = int(m.group(1))
            parts = [(raw[m.end():].strip(), file_line)]
        elif cur_num is not None:
            if not raw.strip():
                items.append(_build(block, cur_num, parts))
                cur_num, parts = None, []
            else:
                parts.append((raw.strip(), file_line))
    if cur_num is not None:
        items.append(_build(block, cur_num, parts))
    return items


def _build(block, number, parts):
    text_bits, char_lines = [], []
    for i, (chunk, file_line) in enumerate(parts):
        if i:
            text_bits.append(" ")
            char_lines.append(file_line)
        text_bits.append(chunk)
        char_lines.extend([file_line] * len(chunk))
    return Item(block, number, "".join(text_bits), char_lines)


# --------------------------------------------------------------------------
# Claim grammars (allowlist — a sentence matches one of these or is not a
# claim as far as this tool is concerned)
# --------------------------------------------------------------------------

# `fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002)
# `x/SKILL.md` is now at 399 body lines
#
# `\**` around the number is not decoration this can ignore: emphasising the
# figure you want the reader to notice is the single most likely way for a
# careful author to write this sentence, and a grammar that misses `**399**`
# would silently drop exactly the claims someone bothered to highlight. Round
# 351's own corrected item 1 was written that way on the first attempt and
# extracted to nothing.
BODY_LINES_RE = re.compile(
    r"`(?P<path>[^`\s]+?\.md)`\s+(?:is|remains|stands at|sits at)\s+"
    r"(?:now\s+|still\s+)?(?:at\s+)?\**(?P<n>\d+)\**\s+body\s+lines"
    r"(?:\s*\((?P<code>[A-Z]\d{3})\))?")

# `grep -c mutation_test harness/swe/campaign.py` -> 0
# `bash harness/run_tests_fast.sh` -> **412 passed**
COMMAND_CLAIM_RE = re.compile(
    r"`(?P<cmd>[^`]{3,240})`\s*(?:->|→)\s*(?P<claim>[^,;)\n]{1,120})")

BARE_INT_RE = re.compile(r"^\**(\d+)\**$")


class Claim:
    """One extracted, re-derivable assertion."""

    def __init__(self, item, kind, offset, span_text, payload):
        self.item = item
        self.kind = kind                # "body-lines" | "command"
        self.offset = offset
        self.span_text = span_text      # verbatim matched text (for CARRIED)
        self.payload = payload          # kind-specific dict
        self.checkable = True
        self.skip_reason = None

    @property
    def line(self):
        return self.item.line_at(self.offset)

    def key(self):
        """Normalised identity used to age a claim across blocks."""
        return normalise(self.span_text)


def normalise(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_claims(item):
    """Every claim in one item, in order of appearance."""
    out = []
    for m in BODY_LINES_RE.finditer(item.text):
        out.append(Claim(item, "body-lines", m.start(), m.group(0),
                         {"path": m.group("path"),
                          "n": int(m.group("n")),
                          "code": m.group("code")}))
    for m in COMMAND_CLAIM_RE.finditer(item.text):
        cmd = re.sub(r"\s+", " ", m.group("cmd")).strip()
        claim_text = m.group("claim").strip()
        c = Claim(item, "command", m.start(), m.group(0),
                  {"cmd": cmd, "claim": claim_text})
        kind, reason = claim_check.classify(cmd)
        if kind != "auto":
            c.checkable = False
            c.skip_reason = reason
        out.append(c)
    out.sort(key=lambda c: c.offset)
    return out


# --------------------------------------------------------------------------
# Re-derivation
# --------------------------------------------------------------------------

class Finding:
    def __init__(self, claim, code, message, level="STALE"):
        self.claim, self.code, self.message, self.level = \
            claim, code, message, level

    def __str__(self):
        return "%s:%d: %s %s %s" % (self.claim.item.block.path,
                                    self.claim.line, self.level, self.code,
                                    self.message)


def resolve_md(path, repo_root):
    """Resolve a markdown path written the way a next-step writes it.

    `fuzz-mutate-kill-loop/SKILL.md` is relative to `skills/`, not to the
    repo root — that is how a skills(B) round refers to a skill in prose.
    Bases are tried in order and the first hit wins. An unresolved path is
    NOT a finding: prose names hypothetical files ("if a `pyproject.toml`
    ever appears at the repo root"), and a checker that flags those gets
    muted, which costs more than the recall it buys.
    """
    for base in (repo_root, os.path.join(repo_root, "skills"),
                 os.path.join(repo_root, "state")):
        cand = os.path.normpath(os.path.join(base, path))
        if os.path.isfile(cand):
            return cand
    return None


def body_line_count(md_path):
    """Body lines as `skill_lint.py`'s B001/B002 count them.

    Imported from `skill_lint` rather than re-derived: if the linter's idea
    of "body" ever changes, a claim about its threshold must move with it or
    the two tools disagree about the same number.
    """
    with open(md_path, encoding="utf-8") as f:
        _, body, _ = skill_lint.parse_frontmatter(f.read())
    return len(body.split("\n"))


def lint_codes(md_path):
    """The set of codes `skill_lint` currently emits for one skill.

    `house=True` on purpose: the house rules are what this workspace's
    `--house --strict` sweep runs, so a prose citation of a house code
    (`H004`, `S003`) has to be checked against the same configuration a
    round would have used, not against the stricter-by-omission default.
    """
    findings = skill_lint.lint_skill(os.path.dirname(md_path), house=True)
    return {f.code for f in findings}


def check_body_lines(claim, repo_root):
    p = claim.payload
    md = resolve_md(p["path"], repo_root)
    if md is None:
        claim.checkable = False
        claim.skip_reason = "unresolved path: %r is not a file under the " \
                            "repo root, skills/ or state/" % p["path"]
        return []
    findings = []
    actual = body_line_count(md)
    if actual != p["n"]:
        findings.append(Finding(
            claim, "S001",
            "claims `%s` is %d body lines; it is %d"
            % (p["path"], p["n"], actual)))
    if p["code"]:
        codes = lint_codes(md)
        if p["code"] not in codes:
            findings.append(Finding(
                claim, "S002",
                "cites `%s` as currently firing on `%s`; skill_lint emits %s"
                % (p["code"], p["path"],
                   ", ".join(sorted(codes)) if codes else "nothing")))
    return findings


def check_command(claim, repo_root, timeout):
    """S003: re-run an `auto` command and diff its output against the claim.

    Two comparison modes, both exact:
      * named metrics (`412 passed`, `exit 0`, `17 skill(s)`) via
        `claim_check`'s own METRICS table, so the two tools cannot drift
        apart on what "passed" means;
      * a BARE INTEGER claim (`-> 0`) against the last integer-only line of
        the output. This is the `grep -c` / `wc -l` shape, which states a
        number that matches no metric name and would otherwise be silently
        counted as unquantified.
    """
    cmd_obj = claim_check.Command(claim.item.block.path, claim.line,
                                  claim.payload["cmd"], claim.payload["claim"])
    cmd_obj.kind, cmd_obj.reason = "auto", None
    output, rc = claim_check.run_command(cmd_obj, repo_root, repo_root, timeout)
    findings = []
    wanted = claim_check.claim_metrics(claim.payload["claim"])
    bare = BARE_INT_RE.match(claim.payload["claim"].strip())
    if not wanted and not bare:
        return [Finding(claim, "S004",
                        "claim %r states no checkable number; ran it for the "
                        "exit code only (exit %d)"
                        % (claim.payload["claim"], rc),
                        level="UNQUANTIFIED")]
    if wanted:
        got = claim_check.observed_metrics(output, rc)
        for name, want in sorted(wanted.items()):
            if name not in got:
                findings.append(Finding(
                    claim, "S003",
                    "claim says %s=%d but `%s` printed no %s at all"
                    % (name, want, claim.payload["cmd"], name)))
            elif got[name] != want:
                findings.append(Finding(
                    claim, "S003",
                    "claim says %s=%d, observed %s=%d (`%s`)"
                    % (name, want, name, got[name], claim.payload["cmd"])))
    if bare:
        want = int(bare.group(1))
        tail = [ln.strip() for ln in output.strip().split("\n") if ln.strip()]
        got = None
        for ln in reversed(tail):
            if re.match(r"^-?\d+$", ln):
                got = int(ln)
                break
        if got is None:
            findings.append(Finding(
                claim, "S003",
                "claim says the output is %d but `%s` printed no bare integer"
                % (want, claim.payload["cmd"])))
        elif got != want:
            findings.append(Finding(
                claim, "S003",
                "claim says %d, observed %d (`%s`)"
                % (want, got, claim.payload["cmd"])))
    return findings


# --------------------------------------------------------------------------
# Carry-forward age
# --------------------------------------------------------------------------

def claim_ages(live, all_blocks):
    """For each claim key, the set of round numbers whose block asserts it.

    Exact substring match on the NORMALISED matched span — not a similarity
    score. A fuzzy match would let this become the thing it is auditing: a
    number nobody can re-derive. The span is short and structured
    (``fuzz-mutate-kill-loop/SKILL.md` is still 415 body lines (B002)`), so
    exact matching costs almost no recall and buys certainty.
    """
    live_keys = set()
    for item in parse_items(live):
        for claim in extract_claims(item):
            live_keys.add(claim.key())
    ages = {k: set() for k in live_keys}
    for block in all_blocks:
        haystack = normalise(" ".join(block.lines))
        for key in live_keys:
            if key and key in haystack:
                ages[key].add(block.round_no)
    return ages


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def analyse(path, repo_root, run=False, timeout=300, block_round=None):
    """Returns (findings, report) for one status document."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    blocks = find_blocks(text)
    for b in blocks:
        b.path = path
    if block_round is not None:
        chosen = [b for b in blocks if b.round_no == block_round]
        if not chosen:
            raise ValueError("no next-steps block for round %d" % block_round)
        if len(chosen) > 1:
            raise ValueError("%d blocks claim round %d"
                             % (len(chosen), block_round))
        live = chosen[0]
    else:
        live, err = live_block(blocks)
        if live is None:
            raise ValueError(err)

    items = parse_items(live)
    findings, claims = [], []
    for item in items:
        for claim in extract_claims(item):
            claims.append(claim)
            if claim.kind == "body-lines":
                findings.extend(check_body_lines(claim, repo_root))
            elif claim.kind == "command" and claim.checkable:
                if run:
                    findings.extend(check_command(claim, repo_root, timeout))

    ages = claim_ages(live, blocks)
    report = {
        "path": path,
        "live_round": live.round_no,
        "live_line": live.first_line,
        "n_blocks": len(blocks),
        "n_items": len(items),
        "n_items_with_claims": len({c.item.number for c in claims}),
        "claims": claims,
        "ages": ages,
        "ran": run,
    }
    return findings, report


def format_report(findings, report, show_carried=True):
    out = []
    for f in findings:
        out.append(str(f))
    if show_carried:
        for claim in report["claims"]:
            rounds = sorted(report["ages"].get(claim.key(), ()))
            if len(rounds) > 1:
                out.append("%s:%d: CARRIED S005 asserted verbatim by %d "
                           "next-steps blocks (rounds %s) — no round between "
                           "them re-derived it: %s"
                           % (report["path"], claim.line, len(rounds),
                              ", ".join(str(r) for r in rounds),
                              re.sub(r"\s+", " ", claim.span_text)[:90]))
    checkable = [c for c in report["claims"] if c.checkable]
    skipped = [c for c in report["claims"] if not c.checkable]
    reasons = {}
    for c in skipped:
        head = (c.skip_reason or "unknown").split(":")[0]
        reasons[head] = reasons.get(head, 0) + 1
    unrun = [c for c in checkable if c.kind == "command" and not report["ran"]]
    n_stale = sum(1 for f in findings if f.level == "STALE")
    out.append("state_claim_check: %s — live block is round %d (line %d) of "
               "%d blocks; %d item(s), %d with a checkable claim"
               % (os.path.basename(report["path"]), report["live_round"],
                  report["live_line"], report["n_blocks"], report["n_items"],
                  report["n_items_with_claims"]))
    out.append("state_claim_check: %d claim(s): %d re-derivable, %d skipped "
               "(%s)%s; %d stale"
               % (len(report["claims"]), len(checkable), len(skipped),
                  ", ".join("%s %d" % kv for kv in sorted(reasons.items()))
                  or "none",
                  "" if not unrun else
                  "; %d command claim(s) need --run" % len(unrun),
                  n_stale))
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--repo-root", default=DEFAULT_REPO_ROOT,
                    help="base for resolving repo-relative paths "
                         "(default: the repo this script lives in)")
    ap.add_argument("--list", action="store_true",
                    help="print every extracted claim with its verdict")
    ap.add_argument("--run", action="store_true",
                    help="execute `auto` command claims and diff their real "
                         "output (never runs `manual` ones)")
    ap.add_argument("--no-carried", action="store_true",
                    help="suppress the CARRIED age lines")
    ap.add_argument("--block", type=int, default=None,
                    help="check the block for this round instead of the live "
                         "one (for regression-testing a historical block)")
    ap.add_argument("--timeout", type=int, default=300,
                    help="per-command timeout in seconds under --run")
    args = ap.parse_args(argv)

    repo_root = os.path.abspath(args.repo_root)
    rc = 0
    for path in args.paths:
        try:
            findings, report = analyse(path, repo_root, run=args.run,
                                       timeout=args.timeout,
                                       block_round=args.block)
        except (OSError, UnicodeDecodeError) as e:
            print("%s: cannot read: %s" % (path, e), file=sys.stderr)
            return 2
        except ValueError as e:
            print("%s: %s" % (path, e), file=sys.stderr)
            return 2
        if args.list:
            for c in report["claims"]:
                print("%s:%d: %-11s %-6s %s%s"
                      % (path, c.line, c.kind,
                         "check" if c.checkable else "skip",
                         re.sub(r"\s+", " ", c.span_text)[:80],
                         "" if c.checkable else "   [%s]" % c.skip_reason))
        print(format_report(findings, report,
                            show_carried=not args.no_carried))
        if any(f.level == "STALE" for f in findings):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
