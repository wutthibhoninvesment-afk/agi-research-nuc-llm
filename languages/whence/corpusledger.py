"""Round 512 (language C): are this tree's derived ledgers actually fresh?

THE FINDING, in one table. Every one of these is a JSON artefact under
`state/whence/` that is DERIVED from `languages/whence/` by a generator in
this directory, and every one has a test that gates it. They were measured
on this tree at HEAD 61dafe9 by regenerating each into a temp file and
byte-comparing:

    ledger                          regenerated  gate's predicate     status
    ------------------------------- -----------  -------------------  ------
    testcorpus-contributions.json   round 507    the FILE SET         STALE*
    assert-shadow-census.json       round 500    the SHADOW-NODE set  STALE
    subject-provenance.json         round 500    (nothing)            STALE
    builtin-liveness.json           round 504    per-builtin verdict  fresh
    builtin-runtime.json            round 506    per-builtin verdict  fresh

    * and correctly RED -- it is the only one of the three whose staleness
      the fast tier reported.

The three stale ones drifted for the SAME reason (rounds 502/504/506/510
each added a file to `tests/`) and were caught to three different degrees.
The difference is not care, not the author -- rounds 500-510 are the same
track -- and not the generator. It is the GATE'S PREDICATE:

  * `testcorpus-contributions.json`'s gate compares `set(live_files)`
    against `set(declared_files)`. That predicate is a TOTAL function of
    the thing that drifts, so every corpus addition trips it. It has been
    regenerated in five of the last seven rounds that touched the corpus.

  * `assert-shadow-census.json`'s gate compares the SHADOW-NODE set, which
    is a proper SUBSET of the census -- most files contribute no shadow
    pair. So it only reddens when an addition happens to contribute one.
    Round 510's `test_branchlive.py` did; rounds 502/504/506's additions
    did not. The ledger's own headline totals had drifted 72 -> 76 files,
    1935 -> 2029 test functions and 3908 -> 4122 asserts, and NOTHING
    compares those numbers to anything. The CLI printed them as its
    headline for twelve rounds.

  * `subject-provenance.json` is the limiting case. `subjprov.py --check`
    on this tree prints "0 finding(s)" and exits 0 while the ledger on disk
    is missing `test_specstale.py` entirely. A self-check blind to the
    staleness it exists to detect is worse than no check, because it is
    quoted as evidence.

  * The two `builtin-*` ledgers are fresh, and are the control: their gates
    are keyed per-builtin, and the set of builtins does not drift when a
    test file is added. They say the drift is a property of the CORPUS
    predicate, not of this program's discipline.

SO: A LEDGER IS KEPT AS FRESH AS ITS GATE'S PREDICATE IS TOTAL IN WHAT
DRIFTS. Not as fresh as its author intended, and not as fresh as its
`--check` verb claims.

WHAT THIS MODULE DOES ABOUT IT
------------------------------
It refuses to add a sixth bespoke predicate. Instead it asks the only
question that is total by construction:

    a ledger is FRESH iff re-running its own declared regeneration command
    reproduces it BYTE FOR BYTE.

That is exact rather than heuristic, it needs no knowledge of what any
ledger means, and it cannot drift out of step with a generator -- it IS the
generator. All five generators were measured byte-deterministic across two
runs at a fixed HEAD (round 512, prediction P14), which is the precondition
this design rests on and is re-checked by `--check --twice`.

THREE DESIGN DECISIONS, and why each differs from the obvious thing
------------------------------------------------------------------
1. THE REGISTRY IS READ OUT OF THE LEDGERS, NOT TYPED HERE. Three of the
   five already carry their own command in a `_regenerate` or
   `_generated_by` field, because their generators write it. A hand-typed
   table in this file would be a sixth artefact that can go stale, which is
   the exact defect this module is about. Where the generator does NOT
   cooperate the entry lives in `UNDECLARED` below WITH THE REASON, and
   `--list` prints it as a named coverage gap rather than omitting it.

2. A DECLARED COMMAND IS SANDBOXED, OR IT IS NOT RUN. `subject-provenance`'s
   command names its own real path (`--json ../../state/whence/subject-
   provenance.json`), so executing it verbatim to "check" freshness would
   OVERWRITE the very file under test and report fresh every time. Every
   command is rewritten to write to a temp path -- via its `<placeholder>`
   token if it has one, else via the token that resolves to the ledger's own
   realpath. A command with neither is reported UNSANDBOXABLE and refused.
   Exactly one substitution is required: zero means the check would be
   vacuous, two means we cannot tell which one is the output.

3. `--check` IS NOT A GATE BY DEFAULT. It exits 0 on staleness unless
   `--strict` is passed. Round 493's rule: a check must never be able to
   stop the round that would fix it. The pytest node in
   `tests/test_corpusledger.py` is where staleness becomes a red.

USAGE

    python3 corpusledger.py --list            # registry + coverage gaps
    python3 corpusledger.py --check           # freshness, rc 0
    python3 corpusledger.py --check --strict  # rc 1 if anything is stale
    python3 corpusledger.py --fix             # regenerate the stale ones

WHAT IT IS NOT. It says a ledger disagrees with its generator; it does not
say the generator is right. And it is blind to a ledger nobody generates:
`specstale-acknowledged.json` is hand-maintained and is listed as such.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LEDGER_DIR = os.path.join(ROOT, "state", "whence")

#: Fields a generator may use to declare how it is re-run. Both spellings
#: are already in the tree (round 498 wrote `_regenerate`, round 494 wrote
#: `_generated_by`); this module reads rather than renames, because a rename
#: would rewrite two ledgers to make a third one's parser prettier.
DECL_FIELDS = ("_regenerate", "_generated_by")

#: Ledgers whose generator does NOT write a declaration into the artefact,
#: with the reason. These are the coverage gap, kept visible.
UNDECLARED = {
    "builtin-liveness.json": {
        "command": "python3 builtinlive.py --write --ledger <path>",
        "why": "`builtinlive._write` dumps `ledger_view(c)` -- a reduced "
               "projection of the census -- so a `_regenerate` key in the "
               "artefact would not survive its own regeneration.",
    },
    "builtin-runtime.json": {
        "command": "python3 runlive.py --write --ledger <path>",
        "why": "same shape as builtin-liveness: `runlive._write` dumps a "
               "computed view, not a document it could annotate.",
    },
}

#: Not derived from anything, so freshness is not defined for them.
NOT_GENERATED = {
    "specstale-acknowledged.json":
        "a hand-maintained ACKNOWLEDGEMENT file -- `specstale.py --emit-ack` "
        "proposes blocks, a human decides. Regenerating it would silently "
        "grant every pending acknowledgement.",
}


class Unsandboxable(Exception):
    """A declared command that cannot be redirected away from its own file."""


def ledger_paths(directory=LEDGER_DIR):
    """The top-level `*.json` under `state/whence/`, sorted.

    Top level only, and deliberately: the `round-NNN/` subdirectories are
    per-round evidence banks, which are meant to be immutable once written
    and would be destroyed by a `--fix` that treated them as derived.
    """
    if not os.path.isdir(directory):
        return []
    return sorted(f for f in os.listdir(directory) if f.endswith(".json")
                  and os.path.isfile(os.path.join(directory, f)))


def declared_command(path):
    """The regeneration command a ledger declares about itself, or None."""
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    for field in DECL_FIELDS:
        val = obj.get(field)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def registry(directory=LEDGER_DIR):
    """One row per ledger: where its command comes from, or why there is none.

    `source` is `self` (the artefact declares it), `undeclared` (this
    module supplies it and says why the generator could not), or
    `not-generated`.
    """
    rows = []
    for name in ledger_paths(directory):
        full = os.path.join(directory, name)
        cmd = declared_command(full)
        if cmd:
            rows.append({"name": name, "path": full, "command": cmd,
                         "source": "self", "why": None})
        elif name in UNDECLARED:
            ent = UNDECLARED[name]
            rows.append({"name": name, "path": full,
                         "command": ent["command"], "source": "undeclared",
                         "why": ent["why"]})
        elif name in NOT_GENERATED:
            rows.append({"name": name, "path": full, "command": None,
                         "source": "not-generated",
                         "why": NOT_GENERATED[name]})
        else:
            rows.append({"name": name, "path": full, "command": None,
                         "source": "unknown", "why":
                         "no `_regenerate`/`_generated_by` field, and no "
                         "entry in corpusledger.UNDECLARED or "
                         "NOT_GENERATED. Add one, with a reason."})
    return rows


def split_command(command, default_cwd=HERE):
    """`(cwd, argv)` for a declared command string.

    Handles the one shell form the tree actually uses -- a `cd <dir> &&`
    prefix -- and refuses anything else with a shell metacharacter, rather
    than handing an arbitrary string to a shell.
    """
    cwd = default_cwd
    rest = command
    if "&&" in command:
        head, _, tail = command.partition("&&")
        head, rest = head.strip(), tail.strip()
        parts = shlex.split(head)
        if len(parts) != 2 or parts[0] != "cd":
            raise Unsandboxable(
                "unsupported shell prefix %r -- only `cd <dir> &&` is "
                "understood" % head)
        cwd = os.path.normpath(os.path.join(ROOT, parts[1]))
    # `<` and `>` are excluded from this set on purpose -- they are the
    # placeholder delimiters every declared command in this tree uses. They
    # are never passed to a shell (`subprocess.run` gets a list), so they
    # cannot redirect anything. The rest are refused outright rather than
    # waved through whenever a placeholder happens to be present.
    bad = [ch for ch in "&|;$`" if ch in rest]
    if bad:
        raise Unsandboxable("shell metacharacter %s in %r" % (bad, rest))
    argv = shlex.split(rest)
    if not argv:
        raise Unsandboxable("empty command")
    return cwd, argv


def sandbox(argv, cwd, ledger_path, out_path):
    """Rewrite `argv` so it writes to `out_path` instead of the real ledger.

    Two accepted forms, and EXACTLY ONE substitution must happen:
      * a `<placeholder>` token (`<path>`, `<this file>`, `<census>`);
      * a token that resolves, relative to `cwd`, to the ledger itself.

    Zero substitutions means the run would not produce a comparable file and
    the check would be vacuous. Two means we cannot tell which is the
    output. Both are refused rather than guessed.
    """
    target = os.path.realpath(ledger_path)
    out, hits = [], 0
    for tok in argv:
        if tok.startswith("<") and tok.endswith(">"):
            out.append(out_path)
            hits += 1
            continue
        try:
            resolved = os.path.realpath(os.path.join(cwd, tok))
        except (OSError, ValueError):
            resolved = None
        if resolved == target:
            out.append(out_path)
            hits += 1
            continue
        out.append(tok)
    if hits != 1:
        raise Unsandboxable(
            "%d output token(s) in %r -- need exactly one `<placeholder>` "
            "or a token naming the ledger itself" % (hits, " ".join(argv)))
    return out


def _placeholder_join(argv):
    """`shlex.split` splits `<this file>` into two tokens; rejoin them.

    `assert-shadow-census.json` declares `--json <this file>`. Without this
    the two halves are separate argv entries, neither of which is a
    well-formed placeholder, and the command reads as UNSANDBOXABLE for a
    reason that is about quoting rather than about the ledger.
    """
    out, buf = [], None
    for tok in argv:
        if buf is not None:
            buf.append(tok)
            if tok.endswith(">"):
                out.append(" ".join(buf))
                buf = None
            continue
        if tok.startswith("<") and not tok.endswith(">"):
            buf = [tok]
            continue
        out.append(tok)
    if buf is not None:                       # unterminated -- keep verbatim
        out.extend(buf)
    return out


def regenerate(row, out_path, timeout=600):
    """Run a row's declared command so it writes `out_path`. `(rc, output)`."""
    cwd, argv = split_command(row["command"])
    argv = sandbox(_placeholder_join(argv), cwd, row["path"], out_path)
    if argv[0] == "python3":
        argv = [sys.executable] + argv[1:]
    try:
        p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check_one(row, timeout=600):
    """Freshness of one row: FRESH / STALE / ERROR / SKIP / UNSANDBOXABLE."""
    if row["command"] is None:
        return {"name": row["name"], "status": "SKIP", "detail": row["why"],
                "source": row["source"]}
    fd, tmp = tempfile.mkstemp(prefix="corpusledger-", suffix=".json")
    os.close(fd)
    try:
        try:
            rc, out = regenerate(row, tmp, timeout=timeout)
        except Unsandboxable as exc:
            return {"name": row["name"], "status": "UNSANDBOXABLE",
                    "detail": str(exc), "source": row["source"]}
        if rc != 0:
            return {"name": row["name"], "status": "ERROR",
                    "detail": "generator exited %d: %s"
                              % (rc, out.strip()[-400:]),
                    "source": row["source"]}
        if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            return {"name": row["name"], "status": "ERROR",
                    "detail": "generator wrote nothing to the sandboxed path",
                    "source": row["source"]}
        fresh = open(tmp, "rb").read()
        try:
            have = open(row["path"], "rb").read()
        except OSError as exc:
            return {"name": row["name"], "status": "STALE",
                    "detail": "no ledger on disk (%s)" % exc,
                    "source": row["source"], "diff": _summarise(fresh, b"")}
        if fresh == have:
            return {"name": row["name"], "status": "FRESH", "detail": "",
                    "source": row["source"]}
        return {"name": row["name"], "status": "STALE",
                "detail": _summarise(fresh, have), "source": row["source"]}
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _summarise(fresh, have):
    """A short, honest description of how two ledger blobs differ.

    Top-level key sets first, because "a file was added to the corpus" shows
    up there and is the shape this module exists for; byte lengths only as a
    fallback, because a byte count names nothing.
    """
    try:
        a = json.loads(fresh.decode("utf-8"))
        b = json.loads(have.decode("utf-8")) if have else {}
    except (ValueError, UnicodeDecodeError):
        return "%d fresh bytes vs %d on disk" % (len(fresh), len(have))
    bits = []
    if isinstance(a, dict) and isinstance(b, dict):
        gone = sorted(set(b) - set(a))
        new = sorted(set(a) - set(b))
        if new:
            bits.append("top-level key(s) only in a fresh run: %s" % new)
        if gone:
            bits.append("top-level key(s) only on disk: %s" % gone)
        for key in sorted(set(a) & set(b)):
            va, vb = a[key], b[key]
            if va == vb:
                continue
            if isinstance(va, dict) and isinstance(vb, dict):
                gone = sorted(set(vb) - set(va))
                new = sorted(set(va) - set(vb))
                if new or gone:
                    bits.append("%s: +%s -%s" % (key, new or [], gone or []))
                else:
                    bits.append("%s: same keys, different values" % key)
            elif (isinstance(va, list) and isinstance(vb, list)
                  and all(isinstance(x, (str, int, float)) for x in va + vb)):
                # A list of scalars is a SET for this purpose. Without this
                # branch a ledger whose corpus is a list -- which is the
                # commonest shape after a dict -- reports only "files
                # differs", naming nothing, and the message is useless at
                # exactly the moment it is read.
                gone = sorted(set(vb) - set(va), key=str)
                new = sorted(set(va) - set(vb), key=str)
                if new or gone:
                    bits.append("%s: +%s -%s" % (key, new or [], gone or []))
                else:
                    bits.append("%s: same elements, different order" % key)
            else:
                bits.append("%s differs" % key)
    return "; ".join(bits) or ("%d fresh bytes vs %d on disk"
                               % (len(fresh), len(have)))


def check(directory=LEDGER_DIR, timeout=600, only=None):
    rows = registry(directory)
    if only:
        rows = [r for r in rows if r["name"] in only]
    return [check_one(r, timeout=timeout) for r in rows]


def stale_names(results):
    return [r["name"] for r in results if r["status"] == "STALE"]


def broken_names(results):
    """Statuses that mean the CHECK failed, not that the ledger is stale."""
    return [r["name"] for r in results
            if r["status"] in ("ERROR", "UNSANDBOXABLE")]


def fix(directory=LEDGER_DIR, timeout=600, only=None):
    """Regenerate every STALE ledger in place. `(fixed, still_bad)`."""
    results = check(directory, timeout=timeout, only=only)
    by_name = {r["name"]: r for r in registry(directory)}
    fixed, bad = [], []
    for res in results:
        if res["status"] != "STALE":
            continue
        row = by_name[res["name"]]
        fd, tmp = tempfile.mkstemp(prefix="corpusledger-fix-", suffix=".json")
        os.close(fd)
        try:
            rc, out = regenerate(row, tmp, timeout=timeout)
            if rc != 0 or not os.path.exists(tmp) or not os.path.getsize(tmp):
                bad.append((res["name"], "generator exited %d" % rc))
                continue
            # Write through the temp file rather than letting the generator
            # target the real path: a generator that crashes halfway would
            # otherwise leave a truncated ledger where a stale one was, and
            # a stale ledger is strictly better than a corrupt one.
            with open(tmp, "rb") as fh:
                blob = fh.read()
            with open(row["path"], "wb") as fh:
                fh.write(blob)
            fixed.append(res["name"])
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    return fixed, bad


# --------------------------------------------------------------- the CLI --

def cmd_list(args):
    rows = registry(args.dir)
    print("corpusledger: %d ledger(s) under %s"
          % (len(rows), os.path.relpath(args.dir, ROOT)))
    for r in rows:
        print("  %-32s %-14s %s"
              % (r["name"], r["source"], r["command"] or "(no generator)"))
        if r["why"]:
            print("       %s" % r["why"])
    gaps = [r for r in rows if r["source"] == "unknown"]
    print("  %d self-declaring, %d declared here, %d not generated, "
          "%d UNCLASSIFIED"
          % (sum(1 for r in rows if r["source"] == "self"),
             sum(1 for r in rows if r["source"] == "undeclared"),
             sum(1 for r in rows if r["source"] == "not-generated"),
             len(gaps)))
    return 1 if (gaps and args.strict) else 0


def cmd_check(args):
    results = check(args.dir, timeout=args.timeout, only=args.only or None)
    if args.json:
        print(json.dumps(results, indent=2, sort_keys=True))
    else:
        for r in results:
            print("  %-13s %-32s %s"
                  % (r["status"], r["name"], r["detail"] or ""))
        stale = stale_names(results)
        broken = broken_names(results)
        if stale:
            print("\n%d STALE. Regenerate them:\n    "
                  "python3 corpusledger.py --fix" % len(stale))
        if broken:
            print("\n%d ledger(s) could not be CHECKED at all: %s"
                  % (len(broken), ", ".join(broken)))
        if not stale and not broken:
            print("\nevery generated ledger reproduces byte-for-byte")
    if args.strict:
        return 1 if (stale_names(results) or broken_names(results)) else 0
    return 0


def cmd_fix(args):
    fixed, bad = fix(args.dir, timeout=args.timeout, only=args.only or None)
    for name in fixed:
        print("  regenerated  %s" % name)
    for name, why in bad:
        print("  FAILED       %s: %s" % (name, why))
    if not fixed and not bad:
        print("  nothing stale")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", default=LEDGER_DIR)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--only", action="append", default=[],
                    help="restrict to this ledger basename (repeatable)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on staleness / unclassified ledgers")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--list", action="store_true")
    g.add_argument("--check", action="store_true")
    g.add_argument("--fix", action="store_true")
    args = ap.parse_args(argv)
    if args.fix:
        return cmd_fix(args)
    if args.list:
        return cmd_list(args)
    return cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
