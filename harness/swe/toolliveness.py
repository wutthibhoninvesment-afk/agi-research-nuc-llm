#!/usr/bin/env python3
"""Was this tool RUNNABLE at that commit? — a per-commit liveness sweep.

Round 395 (SWE-loop D). Round 392 found that `languages/whence/bench/
ref_diff.py` — the tool whose whole job is "a rewrite is byte-identical to
the previous version or it is a different language" — had been dying with
`ModuleNotFoundError` before comparing anything, because a hand-written
`MODULES` tuple never gained `whence/foreign.py`. It published the interval
as "six rounds (386-391)" and asked a future SWE-loop(D) round to sweep the
record for citations of a command that could not run.

That number was itself never re-executed, which is round 321's item 14 in
its purest form. This module re-executes it. It does NOT read the source
and reason about it: for each commit it REBUILDS the exact package the
tool's own `extract_head` would have built at that commit and IMPORTS it in
a fresh subprocess, which is what `load()` does. The verdict is therefore a
run, not an argument.

Two commands answer two different questions and both are needed:

    sweep / intervals   when could the command run?     (the tool's history)
    cites               who quoted it, and when?        (the record's history)

`cites` derives its search patterns from the TOOL'S OWN OUTPUT — the string
literals it prints, read out of its AST — and not only from its filename,
because a round that quotes a tool's RESULT without naming the tool has
still quoted a dead command. Grepping the filename is itself a hand-written
subject set (`skills/derived-subject-set`), and this module would reproduce
round 392's own mistake by using one.

usage:
    python3 -m swe.toolliveness commits [--probe ref_diff]
    python3 -m swe.toolliveness sweep   [--probe ref_diff] [--out FILE]
    python3 -m swe.toolliveness intervals [--out FILE]
    python3 -m swe.toolliveness cites   [--probe ref_diff] [--json]
    python3 -m swe.toolliveness report  [--probe ref_diff] [--out FILE]

`sweep` writes one flushed+fsynced JSONL row per commit and is resumable —
round 377's rule, after round 371 lost a 12-minute sweep that wrote its
output only at the end.
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("AGI_RESEARCH_ROOT") or os.path.dirname(
    os.path.dirname(HERE))

# ONE definition of a round-entry heading (round 397). This module is
# imported both as `harness.swe.toolliveness` and, from inside `harness/`,
# as `swe.toolliveness`, so the parent of `harness/` has to be on the path
# for the absolute import to resolve under the second name.
if os.path.dirname(HERE) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from harness import roundheadings as _roundheadings  # noqa: E402


# --- git, kept in one place so a probe never shells out on its own ---------

def git(*args, repo=None, binary=False):
    """`git -C REPO <args>`. Raises `subprocess.CalledProcessError` on a
    non-zero exit exactly as `ref_diff.extract_head`'s own `check_output`
    does — a missing path IS the finding, not something to swallow."""
    out = subprocess.check_output(
        ["git", "-C", repo or REPO] + list(args),
        stderr=subprocess.DEVNULL if binary else None)
    return out if binary else out.decode()


def try_git(*args, repo=None, binary=False):
    """`git(...)`, or `None` if git exited non-zero.

    git's own `fatal:` line is suppressed here: "this path did not exist at
    that commit" is a VERDICT this module reports (`absent`), not an error,
    and printing it above a clean sweep makes a normal run look broken."""
    try:
        return subprocess.check_output(
            ["git", "-C", repo or REPO] + list(args),
            stderr=subprocess.DEVNULL) if binary else subprocess.check_output(
            ["git", "-C", repo or REPO] + list(args),
            stderr=subprocess.DEVNULL).decode()
    except subprocess.CalledProcessError:
        return None


ROUND_RE = re.compile(r"\bRound (\d{1,4})\b")


def commits_touching(paths, repo=None):
    """Every commit that touched any of `paths`, oldest first.

    A tool's liveness is a pure function of (its own source, the artefact it
    reads) at that commit, so it can only CHANGE at a commit touching one of
    them. Probing this set therefore determines the verdict at every commit
    in history, not only at these — see `intervals`, which carries each
    verdict forward to the next probed commit.
    """
    out = git("log", "--reverse", "--format=%H%x1f%ct%x1f%s", "--",
              *paths, repo=repo)
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, ts, subj = line.split("\x1f", 2)
        m = ROUND_RE.search(subj)
        rows.append({"sha": sha, "short": sha[:7], "ts": int(ts),
                     "subject": subj,
                     "round": int(m.group(1)) if m else None})
    return rows


def all_commits(repo=None):
    """Every commit, oldest first — the denominator `intervals` expands into."""
    return commits_touching([], repo=repo)


# --- probes ----------------------------------------------------------------

class Probe:
    """How to rebuild ONE tool's runnable precondition at a commit.

    `paths` are the files whose change can move the verdict. `check(sha,
    workdir)` returns `(verdict, reason, detail)` where verdict is `"alive"`,
    `"dead"` or `"absent"` (the tool did not exist yet at that commit).
    """

    name = "?"
    paths = ()
    source_path = None

    def __init__(self, repo=None):
        # A probe that can only ever read THIS checkout cannot be tested
        # against a constructed history, and a sweep tool whose own tests
        # must run against the repo it is measuring is the shape round 389
        # hit when an anchor-verified registry and a running sweep became
        # mutually exclusive. `repo` is what keeps them separable.
        self.repo = repo

    def _git(self, *a, **kw):
        return git(*a, repo=self.repo, **kw)

    def _try_git(self, *a, **kw):
        return try_git(*a, repo=self.repo, **kw)

    def check(self, sha, workdir):        # pragma: no cover - interface
        raise NotImplementedError


class RefDiffProbe(Probe):
    """`languages/whence/bench/ref_diff.py`.

    Its precondition is `extract_head` followed by `load`: write one file per
    name in `MODULES` out of the commit's tree into a package directory
    called `whence_ref`, then `import whence_ref.interp` and
    `whence_ref.values`. Everything the tool does afterwards is downstream of
    those two imports, so if they fail the command produces no comparison at
    all — which is the failure round 392 found.

    `MODULES` is read out of the commit's OWN copy of the script, not
    assumed: it was a literal tuple for most of the repo's history and became
    an `os.listdir` derivation in round 392, and a sweep that hard-coded
    either form would measure the wrong tool on one side of that commit.
    """

    name = "ref_diff"
    source_path = "languages/whence/bench/ref_diff.py"
    paths = ("languages/whence/whence/", "languages/whence/bench/ref_diff.py")
    pkg_dir = "languages/whence/whence"

    def modules_at(self, sha):
        """The module-name tuple the script would have used at `sha`.

        Returns `(names, how)`. `how` is `"literal"` when the commit's script
        spells the tuple out, `"derived"` when it reads the package directory
        (round 392's form), and the derivation is then done against the
        commit's tree — which is what the script's `os.listdir(ROOT/whence)`
        resolves to when the working tree IS that commit.
        """
        src = self._try_git("show", "%s:%s" % (sha, self.source_path))
        if src is None:
            return None, "absent"
        tree = ast.parse(src)
        node = None
        for stmt in tree.body:
            if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == "MODULES"):
                node = stmt.value
        if node is None:
            # Round 395 changed the script so that the module set is read
            # from the REVISION BEING BUILT inside `extract_head`, and there
            # is no module-level `MODULES` at all. Derive from that commit's
            # tree, which is exactly what `ref_modules` does. Named against
            # the function rather than a comment because this branch decides
            # `absent` vs a real verdict for every future commit.
            if "def ref_modules(" in src:
                return self._tree_modules(sha), "derived-from-ref"
            return None, "no-modules-binding"
        try:
            return tuple(ast.literal_eval(node)), "literal"
        except (ValueError, TypeError, SyntaxError):
            pass
        if "listdir" in ast.dump(node):
            return self._tree_modules(sha), "derived"
        return None, "unreadable-modules"

    def _tree_modules(self, sha):
        out = self._git("ls-tree", "--name-only", sha, self.pkg_dir + "/")
        return tuple(sorted(
            os.path.basename(p)[:-3] for p in out.split()
            if p.endswith(".py")))

    def check(self, sha, workdir):
        names, how = self.modules_at(sha)
        if names is None:
            return "absent", how, {}
        pkg = os.path.join(workdir, "whence_ref")
        os.makedirs(pkg, exist_ok=True)
        written, missing = [], []
        for m in names:
            blob = self._try_git("show", "%s:%s/%s.py"
                                 % (sha, self.pkg_dir, m), binary=True)
            if blob is None:
                missing.append(m)
                continue
            with open(os.path.join(pkg, m + ".py"), "wb") as f:
                f.write(blob)
            written.append(m)
        detail = {"modules": list(names), "how": how, "written": written}
        if missing:
            # `extract_head`'s `check_output` raises here, so the command
            # dies before any comparison — same outcome, different exception.
            detail["missing"] = missing
            return "dead", "git-show-failed:" + ",".join(missing), detail
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); "
             "import whence_ref.interp, whence_ref.values" % workdir],
            capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return "alive", "", detail
        last = [l for l in r.stderr.strip().splitlines() if l.strip()]
        detail["stderr_tail"] = last[-1] if last else ""
        return "dead", (last[-1] if last else "exit %d" % r.returncode), detail


PROBE_TYPES = {p.name: p for p in (RefDiffProbe,)}
PROBES = {n: t() for n, t in PROBE_TYPES.items()}


# --- the sweep -------------------------------------------------------------

def default_out(probe_name, round_dir=None):
    d = round_dir or os.path.join(REPO, "state", "swe", "round-395")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "liveness-%s.jsonl" % probe_name)


def done_shas(path):
    if not os.path.exists(path):
        return set()
    out = set()
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.add(json.loads(line)["sha"])
            except (ValueError, KeyError):
                continue
    return out


def sweep(probe, out_path, commits=None, budget_s=None, log=None):
    """One flushed row per commit, resumable. Returns the rows written."""
    commits = commits if commits is not None else commits_touching(
        probe.paths, repo=getattr(probe, "repo", None))
    already = done_shas(out_path)
    started = time.time()
    written = []
    with open(out_path, "a") as f:
        for c in commits:
            if c["sha"] in already:
                continue
            if budget_s is not None and time.time() - started > budget_s:
                break
            work = tempfile.mkdtemp(prefix="liveness_")
            t0 = time.time()
            try:
                verdict, reason, detail = probe.check(c["sha"], work)
            finally:
                shutil.rmtree(work, ignore_errors=True)
            row = dict(c, verdict=verdict, reason=reason,
                       probe=probe.name, elapsed_s=round(time.time() - t0, 3),
                       **detail)
            f.write(json.dumps(row, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
            written.append(row)
            if log:
                log("%s %-6s r%-5s %s" % (c["short"], verdict,
                                          c["round"] or "-", reason[:70]))
    return written


def load_rows(path):
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def intervals(rows, commits=None):
    """Collapse per-commit verdicts into maximal same-verdict spans, and
    expand each into the HEADs it covered.

    A probed commit's verdict holds until the next PROBED commit, because
    nothing between them can move it (see `commits_touching`). `heads` is
    therefore the full list of commits that were HEAD under that verdict,
    which is what turns "N commits" into "the rounds that ran".

    Ordering is by POSITION in `git log --reverse`, not by commit timestamp.
    The first version of this function sorted by `ts` and its own hermetic
    test caught it: three fixture commits made inside one second all compared
    equal, every head landed in the wrong span, and the dead span reported
    zero heads. Real git history has the same hazard for a different reason
    --- a rebase or a cherry-pick can leave author time out of order --- so
    the fix is not "the fixture was too fast", it is that history order is
    the graph's, never the clock's.
    """
    if not rows:
        return []
    every = commits if commits is not None else all_commits()
    pos = {c["sha"]: i for i, c in enumerate(every)}
    rows = sorted((r for r in rows if r["sha"] in pos),
                  key=lambda r: pos[r["sha"]])
    if not rows:
        return []
    spans = []
    for i, r in enumerate(rows):
        lo = pos[r["sha"]]
        hi = pos[rows[i + 1]["sha"]] if i + 1 < len(rows) else len(every)
        heads = every[lo:hi]
        if spans and spans[-1]["verdict"] == r["verdict"]:
            spans[-1]["probed"].append(r["short"])
            spans[-1]["heads"].extend(heads)
        else:
            spans.append({"verdict": r["verdict"], "reason": r["reason"],
                          "from": r["short"], "probed": [r["short"]],
                          "heads": list(heads)})
    for s in spans:
        s["n_heads"] = len(s["heads"])
        s["rounds"] = sorted({c["round"] for c in s["heads"]
                              if c["round"] is not None})
        s["last"] = s["heads"][-1]["short"] if s["heads"] else s["from"]
        s["since"] = s["heads"][0]["ts"] if s["heads"] else None
        s["until"] = None
    for a, b in zip(spans, spans[1:]):
        a["until"] = b["since"]
    return spans


# A commit's subject names the round that WROTE it, and a commit becomes HEAD
# only at the END of that round's session, so `span["rounds"]` is the rounds
# whose commits fall inside the span --- the round named by a span's FIRST
# commit was exposed only after it made that commit, and the round named by
# the commit that ENDS the span was exposed until it made that one. Both
# boundary rounds are therefore PARTIALLY exposed, which is exactly the
# distinction round 392's "six rounds (386-391)" collapsed.


# --- citations -------------------------------------------------------------

_FMT = re.compile(r"%[-#0-9. ]*[a-zA-Z]")


def output_literals(source_path, min_len=14):
    """Distinctive string fragments the tool PRINTS, read from its AST.

    A round that writes "0 differing (file, mode) pairs" has quoted this
    tool as surely as one that writes its filename, and a filename grep
    cannot see it. Only literals reachable from a `print` call are used, and
    each is split on its `%` conversions so the surviving fragments are the
    fixed text a quoter would copy.
    """
    with open(source_path) as f:
        tree = ast.parse(f.read())
    lits = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                for frag in _FMT.split(sub.value):
                    frag = " ".join(frag.split())
                    if len(frag) >= min_len:
                        lits.add(frag)
    return sorted(lits)


def record_files(repo=None):
    repo = repo or REPO
    out = [os.path.join(repo, "state", "research-state.md")]
    kdir = os.path.join(repo, "knowledge")
    if os.path.isdir(kdir):
        out += [os.path.join(kdir, f) for f in sorted(os.listdir(kdir))
                if f.endswith(".md")]
    return [p for p in out if os.path.exists(p)]


_ROUND_FILE = re.compile(r"round-(\d+)")
# The pattern this module carried until round 449: one of the four
# independent heading parsers `harness/roundheadings.py` catalogued at round
# 397. It admits `##` and `###` but is blind to `####`/`#####` and to the
# archive's span headings, and nothing on the writing side enforces any of
# it. Kept as a name because the tests pin what it does and does not match.
_STATE_HEAD = re.compile(r"^#{2,3} Round (\d+)\b")


def _round_of_line(path, lineno, lines):
    """The round a line of the record belongs to, or None.

    Round 449 (SWE-loop D) moved this onto `harness.roundheadings`, the
    shared definition. The old scan-backwards for `^#{2,3} Round N` was
    wrong on the archive in a way that is easy to see and was never
    reported: under `### Rounds 114-126 — driver-level, mostly did not run`
    it kept walking past a heading it did not recognise and attributed all
    thirteen rounds' lines to round **113**, the entry above the span. Four
    archived span headings do this. A span now answers with its FIRST round
    rather than with the round before it.
    """
    m = _ROUND_FILE.search(os.path.basename(path))
    if m:
        return int(m.group(1))
    for i in range(lineno - 1, -1, -1):
        h = _roundheadings.parse_heading(lines[i])
        if h is not None:
            return h.rounds[0]
    return None


def find_citations(patterns, files=None, repo=None):
    """Every line in the record matching any pattern, attributed to a round.

    `patterns` is `{kind: [needle, ...]}`; a hit records which kind found it,
    so "cited by name" and "cited by result" stay separable.
    """
    files = files if files is not None else record_files(repo)
    hits = []
    for path in files:
        with open(path, errors="replace") as f:
            lines = f.read().splitlines()
        for i, line in enumerate(lines):
            low = line.lower()
            for kind, needles in patterns.items():
                for nd in needles:
                    if nd.lower() in low:
                        hits.append({
                            "file": os.path.relpath(path, repo or REPO),
                            "line": i + 1, "kind": kind, "needle": nd,
                            "round": _round_of_line(path, i, lines),
                            "text": line.strip()[:200]})
                        break
    return hits


def probe_patterns(probe, repo=None):
    src = os.path.join(repo or getattr(probe, "repo", None) or REPO,
                       probe.source_path)
    # The STEM, not the filename: round 395's first run of this used
    # `os.path.basename(...)` == "ref_diff.py" and silently lost rounds 110,
    # 192, 324 and 347, which write `ref_diff` bare or possessive. A name
    # pattern is a hand-written choice too, and the conservative one is the
    # shortest string that still identifies the tool.
    stem = os.path.basename(probe.source_path).rsplit(".", 1)[0]
    return {"name": [stem], "output": output_literals(src)}


def citations_in_span(hits, span):
    """The hits round 392's item 3 was asking for: citations published by a
    round that ran while the tool could not run."""
    rounds = set(span.get("rounds") or [])
    return [h for h in hits if h["round"] in rounds]


# --- CLI -------------------------------------------------------------------

def _fmt_span(s):
    r = s.get("rounds") or []
    rr = ("rounds %d-%d" % (r[0], r[-1])) if len(r) > 1 else (
        "round %d" % r[0] if r else "no round-tagged head")
    return "%-6s %s..%s  %2d heads  %-18s %s" % (
        s["verdict"], s["from"], s["last"], s["n_heads"], rr,
        (s["reason"] or "")[:60])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="swe.toolliveness")
    ap.add_argument("cmd", choices=["commits", "sweep", "intervals", "cites",
                                    "report"])
    ap.add_argument("--probe", default="ref_diff", choices=sorted(PROBES))
    ap.add_argument("--out")
    ap.add_argument("--budget-s", type=float)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    probe = PROBES[a.probe]
    out = a.out or default_out(probe.name)

    if a.cmd == "commits":
        cs = commits_touching(probe.paths)
        for c in cs:
            print("%s %-5s %s" % (c["short"], c["round"] or "-",
                                  c["subject"][:88]))
        print("%d commits can move %s's verdict" % (len(cs), probe.name))
        return 0

    if a.cmd == "sweep":
        n = len(sweep(probe, out, budget_s=a.budget_s, log=print))
        print("wrote %d new rows to %s (%d total)"
              % (n, out, len(load_rows(out))))
        return 0

    if a.cmd == "intervals":
        for s in intervals(load_rows(out)):
            print(_fmt_span(s))
        return 0

    if a.cmd == "cites":
        pats = probe_patterns(probe)
        hits = find_citations(pats)
        if a.json:
            print(json.dumps(hits, indent=2, sort_keys=True))
            return 0
        by_round = {}
        for h in hits:
            by_round.setdefault(h["round"], set()).add(h["kind"])
        print("%d output literals derived from %s"
              % (len(pats["output"]), probe.source_path))
        for rnd in sorted(k for k in by_round if k is not None):
            print("  round %-4s %s" % (rnd, ",".join(sorted(by_round[rnd]))))
        untagged = len([h for h in hits if h["round"] is None])
        print("%d hits over %d rounds (%d untagged)"
              % (len(hits), len([k for k in by_round if k]), untagged))
        return 0

    # report
    rows = load_rows(out)
    spans = intervals(rows)
    hits = find_citations(probe_patterns(probe))
    print("== liveness ==")
    for s in spans:
        print(_fmt_span(s))
    dead = [s for s in spans if s["verdict"] == "dead"]
    print("\n== citations published while dead ==")
    if not dead:
        print("no dead span")
    for s in dead:
        inside = citations_in_span(hits, s)
        print("span %s..%s rounds %s: %d citation(s)"
              % (s["from"], s["last"], s["rounds"] or "-", len(inside)))
        for h in inside:
            print("   %s:%d [%s] %s" % (h["file"], h["line"], h["kind"],
                                        h["text"][:100]))
    cited = sorted({h["round"] for h in hits if h["round"]})
    print("\nrounds citing %s: %s" % (probe.name, cited))
    return 0


if __name__ == "__main__":
    sys.exit(main())
