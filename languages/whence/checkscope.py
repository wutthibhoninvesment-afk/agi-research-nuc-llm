"""Round 516 (language C): what can a `--check` verb actually SEE?

Round 512 asked whether this tree's derived ledgers were FRESH and answered
it from OUTSIDE, with a predicate that is total by construction: a ledger is
fresh iff re-running its declared generator reproduces it byte for byte
(`corpusledger.py`). Three of five were stale. The three had been caught to
three different degrees, and the variable was not care, not the author and
not the generator -- it was WHAT THE GATE'S PREDICATE RANGED OVER.

That answer left the question one level in unasked. Every one of these
ledgers ALSO ships its own `--check` verb, and that verb is what a person
runs, what a failure message tells them to run, and what gets quoted as
evidence. Round 512 measured the artefacts. This module measures the VERBS:

    for each generated ledger, which of the artefact's own top-level keys
    can its own `--check` notice a change to?

HOW IT IS MEASURED: BY MUTATION, NOT BY READING THE CODE
--------------------------------------------------------
Reading `subjprov.check_ledger` and counting the keys it mentions would be a
static approximation that goes stale the first time somebody edits it -- the
exact defect this module is about, one more level up. So the measurement is
empirical. For each top-level key of each ledger, write a COPY of the ledger
with that one key perturbed, point the ledger's own gate at the copy, and
record what the gate says:

    SEES        non-zero exit -- the verb reported the drift
    BLIND       exit 0 -- the verb printed its agreement line
    CRASH       the verb raised; the drift is "detected" only as a traceback
    UNTESTABLE  the gate cannot be pointed at a candidate file at all
    CONFOUNDED  the gate reacts to the file's ENCODING, so a per-key
                verdict would not be about the key

Two perturbations per key, because they are different questions: DELETE the
key entirely, and CORRUPT its value in the smallest way its type allows
(drop one entry from a mapping, drop the last element of a list, +1 an int,
suffix a string). A verb can be blind to one and not the other, and round
516's sweep found exactly that.

WHY NOBODY HAD MEASURED THIS
----------------------------
Because two of the five gates could not be run against anything but their
own hardcoded path. `subjprov.main` called `load_ledger()` with no argument
and `assertshadow.main` called `load_census()` with no argument, so the only
way to run either against a mutant was to OVERWRITE THE REAL LEDGER first --
in a repository where a third-party commit landed mid-round and swept a
round's staged file into itself (round 515). Round 516 added `--ledger` and
`--census` before it measured anything. An instrument that cannot be aimed
somewhere safe does not get aimed.

THREE DESIGN DECISIONS
----------------------
1. THE GATE TABLE IS HAND-TYPED, AND IS PINNED TO A TABLE THAT IS NOT.
   `corpusledger.py` refuses to hand-type its registry, because a
   hand-typed table is a sixth artefact that can go stale. It gets away
   with that because the regeneration command is written INTO the
   artefacts. No artefact declares its own CHECK command, so there is
   nothing to read out, and inventing a `_check` field would rewrite five
   ledgers to make a sixth module prettier. Instead `GATES` is checked
   against `corpusledger.registry()` at run time: every generated ledger
   must have a gate entry or appear as a named UNCOVERED gap, and
   `--list` prints the gap rather than omitting it.

2. EVERY LEDGER'S SWEEP BEGINS WITH A NEGATIVE CONTROL, AND A FAILING
   CONTROL VOIDS THE ROW. The gate is first run against an UNMUTATED copy.
   If that does not exit 0, the gate is not measuring the copy -- it is
   reading the real file, or the tree is dirty, or the redirect did not
   take -- and every verdict below it would be an artefact of the
   apparatus. Such a row is reported UNTESTABLE with the control's own
   output, not silently dropped, and not scored. Round 512's synthetic
   control was wrong in the same way the real tree was wrong; this one is
   there so that failure is loud.

3. THE MUTANT IS ALWAYS A COPY IN A TEMPORARY DIRECTORY. Nothing in this
   module writes to `state/`. The one gate that reads a hardcoded path
   through `curecheck.AGI_ROOT` (the `testcorpus-contributions` pytest
   node) is redirected with a MIRROR ROOT: a temp directory of symlinks to
   the real root, with exactly one real file -- the mutant -- on the path
   that matters. The redirect's correctness is what design decision 2's
   control exists to prove.

WHAT IT IS NOT. It says which keys a verb can see. It does not say the
verb's message is good, and it does not say a key is WORTH seeing: a verb
blind to its own `_what` prose is not thereby defective. The table is the
input to that judgement, not the judgement.

USAGE

    python3 checkscope.py --list             # gate table + coverage gaps
    python3 checkscope.py --scope            # the sweep (a few minutes)
    python3 checkscope.py --scope --only subject-provenance.json
    python3 checkscope.py --scope --json <path>
    python3 checkscope.py --scope --strict   # rc 1 if any gate is not total
    python3 checkscope.py --selfref --tests <dir>            # + its POPULATION
    python3 checkscope.py --selfref --tests <dir> --strict   # rc 1 if empty

ROUND 519 (skills B): `--selfref` WAS CALIBRATED TO THE TREE IT WAS BORN IN.
Round 516's next-step #5 called running it over `harness/tests/` and
`skills/` "mechanical". It was not. Three assumptions were true by
construction in `languages/whence/tests` and had never been written down:
the walk was a non-recursive `os.listdir` (so `--tests skills`, whose 17
test files are all in subdirectories, read ZERO of them); the unit was
`ast.Assert` (so `skills/skill-authoring/scripts` -- 1 026 test functions,
1 863 `self.assert*` calls, 0 bare `assert` -- had a population of ZERO);
and DECLARED-ness was a list of six helper NAMES (so the document read the
plain way, `open` / `json.load`, was invisible -- round 518's next-step #3).

None of the three raised. Each SHRANK THE POPULATION, and the report said
`none -- every one has an operand measured from the tree` for all of them:
a universally quantified claim, printed over the empty set. The population
is now printed on every run, an EMPTY one is its own verdict naming which
side the zero is a fact about, and `--selfref --strict` reddens on it --
never on findings, which are published for a reader to judge.
"""
import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

#: Round 413's sanctioned root helper, not `dirname(dirname(HERE))`. The
#: plain spelling names the REAL checkout from inside a `harness/swe/proc.py`
#: sandbox copy; `copyparity.py escapes` calls that a copy break, and it has
#: entered this tree four times (rounds 464, 504, 507, 512).
ROOT = (os.environ.get("AGI_RESEARCH_ROOT")
        or os.path.dirname(os.path.dirname(HERE)))
LEDGER_DIR = os.path.join(ROOT, "state", "whence")

MUT_DELETE = "delete"
MUT_CORRUPT = "corrupt"

SEES = "SEES"
BLIND = "BLIND"
CRASH = "CRASH"
UNTESTABLE = "UNTESTABLE"
CONFOUNDED = "CONFOUNDED"

#: How each generated ledger is CHECKED, as opposed to how it is
#: regenerated (`corpusledger.UNDECLARED` / the artefacts' `_regenerate`).
#: `<path>` is replaced by the mutant. `kind` is `cli` (argv, rc is the
#: verdict) or `pytest` (a node id, run under a mirror root because the
#: gate resolves its own path through `curecheck.AGI_ROOT`).
GATES = {
    "assert-shadow-census.json": {
        "kind": "cli",
        "argv": ["python3", "assertshadow.py", "--check", "--census",
                 "<path>"],
        "verb": "assertshadow.py --check",
    },
    "subject-provenance.json": {
        "kind": "cli",
        "argv": ["python3", "subjprov.py", "--check", "--ledger", "<path>"],
        "verb": "subjprov.py --check",
    },
    "builtin-liveness.json": {
        "kind": "cli",
        "argv": ["python3", "builtinlive.py", "--strict", "--ledger",
                 "<path>"],
        "verb": "builtinlive.py --strict",
    },
    "builtin-runtime.json": {
        "kind": "cli",
        "argv": ["python3", "runlive.py", "--strict", "--ledger", "<path>"],
        "verb": "runlive.py --strict",
    },
    "testcorpus-contributions.json": {
        "kind": "pytest",
        "node": "tests/test_testcorpus_contributions.py",
        "verb": "pytest tests/test_testcorpus_contributions.py",
        "why_mirror": "`depthcensus.contributions_path` resolves through "
                      "`curecheck.AGI_ROOT`; there is no path flag, so the "
                      "mutant is placed on that path inside a mirror root.",
    },
}

#: Keys whose drift is not a claim about the tree, recorded here so that
#: "this verb is not total" can be reported honestly rather than inflated
#: by prose fields. NOT excluded from the sweep -- they are measured and
#: then labelled, because the point is to publish the table.
PROSE_KEYS = ("_what", "_assumption", "_headline_predicate", "_history",
              "_lattice", "_derived", "_regenerate", "_generated_by")


# --------------------------------------------------------------- the differ

def _summarise(a, b, limit=3):
    """Name what changed between two values, without printing both.

    Round 512's `corpusledger._summarise` could not say what changed INSIDE
    a list-valued key -- it printed two lists and left the reader to diff
    them. A ledger key can hold 58 rows, so this one names the changed
    members instead."""
    if isinstance(a, dict) and isinstance(b, dict):
        gone = sorted(set(a) - set(b))
        new = sorted(set(b) - set(a))
        moved = sorted(k for k in set(a) & set(b) if a[k] != b[k])
        bits = []
        if gone:
            bits.append("%d only on disk (%s)"
                        % (len(gone), ", ".join(map(str, gone[:limit]))))
        if new:
            bits.append("%d only in the tree (%s)"
                        % (len(new), ", ".join(map(str, new[:limit]))))
        if moved:
            bits.append("%d value(s) moved (%s)"
                        % (len(moved), ", ".join(map(str, moved[:limit]))))
        return "; ".join(bits) or "equal keys, unequal objects"
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return "%d row(s) on disk, %d in the tree" % (len(a), len(b))
        idx = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        return "%d of %d row(s) differ, first at index %d" % (
            len(idx), len(a), idx[0]) if idx else "equal"
    return "ledger %s, tree %s" % (_short(a), _short(b))


def _short(v, n=120):
    t = repr(v)
    return t if len(t) <= n else t[:n] + "..."


def document_diff(declared, live, ignore=()):
    """`[(key, why)]` for every top-level key on which the two disagree.

    THE ONE PREDICATE THAT IS TOTAL IN WHAT DRIFTS, for a check verb that
    already computes the document it would write. `live` is that document;
    `declared` is what is on disk. `ignore` names the keys some other,
    more readable finding code already owns, so the caller does not report
    the same drift twice.

    A key present on exactly one side is a finding, which is the half a
    hand-written comparison usually forgets: `for k, v in live.items()` is
    blind to a key that exists only on disk."""
    skip = set(ignore)
    out = []
    for key in sorted(set(declared) | set(live)):
        if key in skip:
            continue
        if key not in declared:
            out.append((key, "absent from the ledger; the tree would write "
                             "%s" % _short(live[key])))
        elif key not in live:
            out.append((key, "on disk but the tree would not write it "
                             "(%s)" % _short(declared[key])))
        elif declared[key] != live[key]:
            out.append((key, _summarise(declared[key], live[key])))
    return out


# ------------------------------------------------------------- the encoding

#: Every `json.dump` spelling this tree actually uses, plus the obvious
#: neighbours. Searched rather than configured: see `detect_encoding`.
ENCODINGS = [{"indent": i, "sort_keys": s, "ensure_ascii": a}
             for i in (1, 2, 4, None)
             for s in (True, False)
             for a in (True, False)]


def detect_encoding(path, obj):
    """`(kwargs, tail, exact)` -- how to write `obj` back as these bytes.

    THE SECOND THING THIS SWEEP GOT WRONG, and it produced a wrong headline
    rather than a wrong cell. The first run wrote every mutant with
    `indent=2`, and reported `testcorpus-contributions.json` as the one
    gate in this tree TOTAL over its own document -- 2 keys, both SEES.
    It is not. That gate contains
    `test_the_ledger_on_disk_round_trips_through_its_own_encoding`, which
    byte-compares the file against `json.dumps(..., indent=1,
    sort_keys=True)`. Every re-serialised mutant fails it, whichever key
    was touched, so every key scored SEES. A gate that appears to see
    everything because it is looking at the whitespace is the exact
    failure this module exists to expose, arriving in its own apparatus.

    So the mutant is written in THE LEDGER'S OWN ENCODING, discovered by
    searching for the `json.dumps` keywords that reproduce the file
    byte-for-byte. `exact` is False when none does, and then the row is
    flagged rather than quietly trusted."""
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError:                             # pragma: no cover
        return ENCODINGS[0], "\n", False
    for kw in ENCODINGS:
        for tail in ("\n", ""):
            try:
                if json.dumps(obj, **kw) + tail == raw:
                    return kw, tail, True
            except (TypeError, ValueError):     # pragma: no cover
                continue
    return {"indent": 2, "sort_keys": False, "ensure_ascii": True}, "\n", False


def write_as(obj, path, enc):
    kw, tail, _exact = enc
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, **kw) + tail)


# ------------------------------------------------------------- the mutations

def mutate(obj, key, kind):
    """`(mutant, detail)` -- a copy of `obj` with exactly `key` perturbed.

    `(None, why)` means the perturbation would be a NO-OP -- corrupting an
    empty container, say -- and a no-op mutant proves nothing about the
    gate, so it is reported as a skipped cell rather than counted as BLIND.

    `detail` names exactly what was done, because the table is only worth
    reading if a BLIND cell can be audited. The first version of this
    dropped `sorted(v)[0]` from a mapping, and the first thing the sweep
    reported was `builtin-liveness.json`'s `by_verdict` as BLIND under
    corruption -- because the alphabetically first verdict class on this
    tree holds an EMPTY list, so the mutant was semantically identical to
    the control. A no-op mutation reads as a blind gate. Non-empty members
    are preferred now, and the choice is published."""
    out = dict(obj)
    if kind == MUT_DELETE:
        del out[key]
        return out, "deleted the key"
    v = obj[key]
    if isinstance(v, dict):
        if not v:
            return None, "empty mapping -- nothing to drop"
        ks = sorted(v, key=str)
        drop = next((k for k in ks if v[k] not in (None, [], {}, "", 0)),
                    ks[0])
        out[key] = dict((k, x) for k, x in v.items() if k != drop)
        return out, "dropped member %r" % (drop,)
    if isinstance(v, list):
        if not v:
            return None, "empty list -- nothing to drop"
        out[key] = v[:-1]
        return out, "dropped the last of %d element(s)" % len(v)
    if isinstance(v, bool):
        out[key] = not v
        return out, "negated"
    if isinstance(v, int):
        out[key] = v + 1
        return out, "%d -> %d" % (v, v + 1)
    if isinstance(v, float):
        out[key] = v + 1.0
        return out, "%r -> %r" % (v, v + 1.0)
    if isinstance(v, str):
        out[key] = v + " round-516-mutation"
        return out, "suffixed the string"
    if v is None:
        out[key] = 0
        return out, "null -> 0"
    return None, "unmutatable type %s" % type(v).__name__   # pragma: no cover


# ----------------------------------------------------------------- the gates

def _mirror_root(dest, ledger_name, mutant_path):
    """A temp AGI root: symlinks to the real tree, one real file.

    Everything at the real root's top level is symlinked into `dest`
    except `state`, which is rebuilt the same way one level down, and then
    `state/whence` once more, so that exactly `state/whence/<ledger_name>`
    is the mutant and every other path a gate might read still resolves to
    the real tree."""
    os.makedirs(dest, exist_ok=True)
    for name in os.listdir(ROOT):
        if name == "state":
            continue
        os.symlink(os.path.join(ROOT, name), os.path.join(dest, name))
    state = os.path.join(dest, "state")
    os.makedirs(state)
    real_state = os.path.join(ROOT, "state")
    for name in os.listdir(real_state):
        if name == "whence":
            continue
        os.symlink(os.path.join(real_state, name), os.path.join(state, name))
    whence = os.path.join(state, "whence")
    os.makedirs(whence)
    for name in os.listdir(LEDGER_DIR):
        if name == ledger_name:
            continue
        os.symlink(os.path.join(LEDGER_DIR, name),
                   os.path.join(whence, name))
    shutil.copyfile(mutant_path, os.path.join(whence, ledger_name))
    return dest


def run_gate(name, gate, mutant_path, timeout=900):
    """`(rc, output)` from pointing a ledger's own gate at `mutant_path`."""
    env = dict(os.environ)
    if gate["kind"] == "cli":
        argv = [mutant_path if t == "<path>" else t for t in gate["argv"]]
        if argv[0] == "python3":
            argv = [sys.executable] + argv[1:]
        cwd = HERE
    else:
        tmp = tempfile.mkdtemp(prefix="checkscope-root-")
        root = _mirror_root(os.path.join(tmp, "root"), name, mutant_path)
        env["AGI_RESEARCH_ROOT"] = root
        # `--tb=native` -- ROUND 518. `_verdict` calls a run a CRASH by
        # looking for the CPython traceback header, and pytest's own
        # traceback style never prints it: a gate node that raises
        # `KeyError` was scored SEES, indistinguishable from one that
        # reported the drift. The native style prints the real header, so
        # the CRASH class means the same thing for both gate kinds.
        argv = [sys.executable, "-m", "pytest", "-c", "pytest.ini", "-q",
                "--tb=native", gate["node"]]
        cwd = HERE
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                           text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _verdict(rc, out):
    if "Traceback (most recent call last)" in out:
        return CRASH
    return BLIND if rc == 0 else SEES


# ------------------------------------------------------------------- the sweep

def scope_one(name, gate, ledger_dir=None, timeout=900, progress=None):
    """The per-key table for one ledger, control first."""
    ledger_dir = ledger_dir or LEDGER_DIR
    path = os.path.join(ledger_dir, name)
    with open(path, encoding="utf-8") as fh:
        obj = json.load(fh)
    enc = detect_encoding(path, obj)
    tmp = tempfile.mkdtemp(prefix="checkscope-")
    row = {"ledger": name, "verb": gate["verb"], "keys": [],
           "control": None, "encoding": {"kwargs": enc[0],
                                         "trailing_newline": bool(enc[1]),
                                         "reproduces_the_file": enc[2]}}
    try:
        # CONTROL 1: a byte-identical copy. Proves the gate is reading the
        # copy at all -- a bad redirect or a hardcoded path fails here.
        ctl = os.path.join(tmp, name)
        shutil.copyfile(path, ctl)
        rc, out = run_gate(name, gate, ctl, timeout)
        row["control"] = {"rc": rc, "output": out[-1200:]}
        if rc != 0:
            row["status"] = UNTESTABLE
            row["why"] = ("the gate does not exit 0 on an UNMUTATED copy, "
                          "so no verdict below it would be about the copy")
            return row
        # CONTROL 2: the same object written back the way every mutant will
        # be written. If THIS fails, the gate is reacting to the encoding
        # and every per-key verdict below is confounded -- which is how the
        # first run of this sweep reported a formatting check as the one
        # total gate in the tree.
        ctl2 = os.path.join(tmp, "reserialised-" + name)
        write_as(obj, ctl2, enc)
        rc2, out2 = run_gate(name, gate, ctl2, timeout)
        row["encoding_control"] = {"rc": rc2, "output": out2[-1200:]}
        if rc2 != 0:
            row["status"] = CONFOUNDED
            row["why"] = ("the gate does not exit 0 on a semantically "
                          "IDENTICAL copy re-serialised in %s, so it is "
                          "reacting to the file's encoding and no per-key "
                          "verdict would be about the key"
                          % ("its own encoding" if enc[2]
                             else "this module's default encoding, which "
                                  "does not reproduce the file"))
            return row
        row["status"] = "ok"
        for key in sorted(obj):
            cell = {"key": key,
                    "prose": key in PROSE_KEYS,
                    "verdicts": {}, "mutations": {}}
            for kind in (MUT_DELETE, MUT_CORRUPT):
                mut, detail = mutate(obj, key, kind)
                cell["mutations"][kind] = detail
                if mut is None:
                    cell["verdicts"][kind] = "n/a"
                    continue
                mp = os.path.join(tmp, "%s.%s.json" % (key.strip("_"), kind))
                write_as(mut, mp, enc)
                rc, out = run_gate(name, gate, mp, timeout)
                cell["verdicts"][kind] = _verdict(rc, out)
                if progress:
                    progress("    %-34s %-8s %s"
                             % (key, kind, cell["verdicts"][kind]))
            # ROUND 518. `seen` is an OR over the mutation kinds and
            # that is what the published headline counted -- so a key the
            # gate notices under CORRUPT and misses under DELETE was
            # reported as covered. `assert-shadow-census.json`'s
            # `_history` is the live instance: the residual rebuilds the
            # census with the DECLARED document's own history shape, so
            # deleting the shape key makes both sides agree about it.
            # `total` is the honest predicate -- SEES under every
            # APPLICABLE kind, where a no-op mutation is not applicable.
            applicable = sorted(k for k, v in cell["verdicts"].items()
                                if v != "n/a")
            cell["seen"] = SEES in cell["verdicts"].values()
            cell["applicable"] = applicable
            cell["total"] = bool(applicable) and all(
                cell["verdicts"][k] == SEES for k in applicable)
            cell["partial"] = cell["seen"] and not cell["total"]
            row["keys"].append(cell)
        return row
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def coverage(rows):
    """Counts over the scored rows.

    `seen` is the OR over mutation kinds that round 516 published; `total`
    is SEES under every applicable kind. They differ by `partial`, and the
    difference is not zero on this tree -- see the note in `scope_one`."""
    out = {"keys": 0, "seen": 0, "total": 0, "partial": 0, "crash": 0,
           "blind": 0}
    for r in rows:
        if r.get("status") != "ok":
            continue
        for c in r["keys"]:
            out["keys"] += 1
            out["seen"] += bool(c["seen"])
            out["total"] += bool(c.get("total"))
            out["partial"] += bool(c.get("partial"))
            out["crash"] += CRASH in c["verdicts"].values()
    out["blind"] = out["keys"] - out["seen"]
    return out


def gate_gaps(ledger_dir=None):
    """Generated ledgers with no gate entry, and gate entries with no ledger.

    Design decision 1: this module's table cannot be read out of the
    artefacts, so it is pinned against the one table that can."""
    import corpusledger                                # noqa: PLC0415
    rows = corpusledger.registry(ledger_dir or LEDGER_DIR)
    generated = set(r["name"] for r in rows
                    if r["source"] in ("self", "undeclared"))
    return sorted(generated - set(GATES)), sorted(set(GATES) - generated)


# ------------------------------------------- the other way a gate is vacuous

#: Calls that yield the DECLARED document -- what is on disk.
DECLARED_SOURCES = ("load_ledger", "load_census", "load_contributions",
                    "load_registry", "load_map", "declared_command")

#: Calls that yield a fresh measurement OF THE TREE.
LIVE_SOURCES = ("scan_tree", "harvest_tests", "analyse_tree", "guard_rows",
                "census", "harvest_file", "analyse_file", "scan_file",
                "registry", "ledger_paths")

#: THE CLASS THAT MAKES THIS ANALYSIS WORTH RUNNING, and the one a
#: name-based reading gets wrong. A JOIN reads the declared document AND
#: the tree, and hands back rows whose CARDINALITY is a property of the
#: document. `subjprov.compare_with_census` is the instance: it joins the
#: live scan onto `assert-shadow-census.json` on `(file, func,
#: magnitude_line)`, so `len(rows)` counts census pairs, not tree
#: assertions. Round 512's vacuous gate was
#: `assert [len(rows), A.load_census()["totals"]["pairs"]] == [57, 57]`,
#: which LOOKS like live-versus-declared and is declared-versus-declared.
#: Classify a join as LIVE and the instance is missed; classify it as
#: DECLARED and every real gate built on one is a false positive. It is
#: its own class, and it is reported as one.
JOIN_SOURCES = ("compare_with_census",)

DECLARED, LIVE, JOIN, OTHER = "declared", "live", "join", "other"


#: ROUND 519. `unittest`'s assertion METHODS. `selfref_asserts` walked
#: `ast.Assert` and nothing else, so a suite that writes `self.assertEqual`
#: had a population of ZERO -- and the report for zero rows says "none --
#: every one has an operand measured from the tree", which is a claim about
#: assertions that were never read. `skills/skill-authoring/scripts` is 13
#: files, 1026 test functions, 1865 `self.assert*` calls and exactly 0 bare
#: `assert` statements. Binary methods contribute their FIRST TWO arguments
#: as the compared expressions; unary ones contribute their single argument,
#: whose own sub-expressions are then the operands (`assertTrue(a == b)`).
UNITTEST_BINARY = (
    "assertEqual", "assertNotEqual", "assertIs", "assertIsNot",
    "assertIn", "assertNotIn", "assertGreater", "assertLess",
    "assertGreaterEqual", "assertLessEqual", "assertAlmostEqual",
    "assertNotAlmostEqual", "assertCountEqual", "assertListEqual",
    "assertDictEqual", "assertSetEqual", "assertTupleEqual",
    "assertMultiLineEqual", "assertSequenceEqual", "assertRegex",
    "assertNotRegex", "assertItemsEqual")
UNITTEST_UNARY = ("assertTrue", "assertFalse", "assertIsNone",
                  "assertIsNotNone")

#: ROUND 519, and round 518's next-step #3. DECLARED-ness was a list of six
#: helper NAMES, so an assertion that reads its document the plain way was
#: invisible: `raw = open(path).read()` / `obj = json.load(open(path))` /
#: `assert raw == json.dumps(obj, ...)` is `x == f(x)` -- it can only ever
#: see the ENCODING -- and `--selfref` did not report it.
DISK_READS = ("open", "load", "safe_load", "read_text", "read_bytes",
              "read", "readlines", "read_json")

#: ...and the reason the widening above needs a guard. A test that WRITES a
#: file and reads it back is also `x == f(x)`, and it is a legitimate
#: round-trip over data the test itself created, not a gate that believes it
#: is checking the tree. Measured on this repo (round 519), `--selfref
#: --tests harness/tests`: 70 rows with this guard disabled, 40 with it.
#: It is NOT the dominant term -- the widening itself takes harness from
#: 4 rows to 70, and the source/data axis below removes 12 more.
WRITE_CALLS = ("dump", "write_text", "write_bytes", "write", "writelines",
               "write_as", "copy", "copyfile", "copy2", "copytree",
               "makedirs", "mkdir", "run", "check_call", "check_output")
TMP_NAMES = ("tmp_path", "tmpdir", "tmp_dir", "tmpdir_factory", "tempfile",
             "mkdtemp", "mkstemp", "TemporaryDirectory",
             "NamedTemporaryFile", "TmpRepo")

#: Not legal Python identifiers, so they can never collide with a name bound
#: in the analysed source. `SELF_WRITTEN` is the per-function flag that the
#: function (or its `setUp`) creates the files it then reads; `LITERALS` maps
#: a module-level constant to the string literals in its value expression.
SELF_WRITTEN = "#self-written"
LITERALS = "#literals"
#: `READS + name` -> what the disk read that made `name` DECLARED opened.
#: Recorded at BINDING time because that is where the read is: by the time
#: the assertion mentions `raw`, the `open()` is three lines up.
READS = "#read:"

#: ROUND 519, AND THE CORRECTION THE FIRST DRAFT OF THE WIDENING NEEDED.
#: "reads a file from disk" is not "reads the declared document". TWELVE of
#: the first draft's 40 `harness/tests` rows were
#: `src = open(DRIVER_SRC).read(); assert src.index(a) < src.index(b)` --
#: `DRIVER_SRC` is `run_driver.sh`, so those assertions ARE a fresh
#: measurement of the tree and clearing them is what `--selfref` is for.
#: The axis is what the read OPENS: a generated data document is DECLARED,
#: a source text of the tree is LIVE. Resolved through module-level
#: constants, because the suffix is almost never written at the call site.
DATA_SUFFIXES = (".json", ".jsonl", ".ndjson", ".yaml", ".yml", ".toml",
                 ".csv")
SOURCE_SUFFIXES = (".py", ".sh", ".bash", ".md", ".txt", ".log", ".lang",
                   ".cfg", ".ini", ".service")


def _attr_key(node):
    """`"self.reg"` for a one-deep attribute on `self`, else None.

    ROUND 519. `unittest` binds its data in `setUp` as attributes, so a
    name-keyed environment sees nothing: `self.reg = load_registry()` then
    `self.assertEqual(self.reg["a"], self.reg["b"])` classifies as OTHER
    because the only `ast.Name` in either operand is `self`. 1 468 of the
    skills suite's operand expressions are rooted at `self`."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
            and node.value.id == "self":
        return "self." + node.attr
    return None


def _names_and_calls(node):
    """`(bare names, called function names)` inside an expression.

    `names` carries `self.x` keys alongside bare identifiers (round 519);
    `SELF_WRITTEN` is not an identifier so it can never appear here."""
    names, calls = set(), set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            names.add(n.id)
        elif isinstance(n, ast.Attribute):
            key = _attr_key(n)
            if key:
                names.add(key)
        if isinstance(n, ast.Call):
            f = n.func
            calls.add(f.attr if isinstance(f, ast.Attribute)
                      else getattr(f, "id", ""))
    return names, calls


def _reads_disk(node):
    """A call in this expression that opens a file (round 518's #3)."""
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
        if name in DISK_READS:
            return True
    return False


def _module_literals(tree):
    """module-level NAME -> the string literals in its value expression.

    `DRIVER_SRC = os.path.join(ROOT, "run_driver.sh")` is how every one of
    these tests names its subject; the suffix that says what the file IS
    never appears at the `open()` call site."""
    out = {}
    for n in tree.body:
        if not isinstance(n, ast.Assign):
            continue
        lits = [c.value for c in ast.walk(n.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        if not lits:
            continue
        for t in n.targets:
            if isinstance(t, ast.Name):
                out[t.id] = lits
    return out


def _read_target(node, env):
    """`"data"` | `"source"` | `"unresolved"` -- what a read opens.

    UNRESOLVED IS REPORTED, NOT DROPPED. Round 518's own live case is
    `open(dc.contributions_path())`: a call, no literal anywhere, and it
    reads a ledger. Dropping what cannot be resolved would lose exactly the
    instance this widening was built for, so the fallback is to publish and
    say so -- the module's convention, one level down."""
    lits = list(env.get(LITERALS, {}).get("", []))
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            lits.append(n.value)
        elif isinstance(n, ast.Name):
            lits.extend(env.get(LITERALS, {}).get(n.id, []))
    low = [x.lower() for x in lits]
    if any(x.endswith(DATA_SUFFIXES) for x in low):
        return "data"
    if any(x.endswith(SOURCE_SUFFIXES) for x in low):
        return "source"
    return "unresolved"


def _writes_or_temps(fn):
    """True if this function creates the files it then reads.

    The guard on the disk-read widening. A test that writes a fixture and
    reads it back is a round-trip over its OWN data -- `x == f(x)`, but the
    `x` is not the tree's, so calling it a vacuous gate is a false positive.
    Measured (round 519, this repo), this guard off -> on: whence 30 -> 25,
    harness 70 -> 40, skills 5 -> 3 rows."""
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and n.id in TMP_NAMES:
            return True
        if isinstance(n, ast.Attribute) and n.attr in TMP_NAMES:
            return True
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) \
                else getattr(f, "id", "")
            if name in TMP_NAMES or name in WRITE_CALLS:
                return True
            if name == "open" and len(n.args) > 1:
                mode = n.args[1]
                if isinstance(mode, ast.Constant) and \
                        isinstance(mode.value, str) and \
                        any(c in mode.value for c in "wax+"):
                    return True
        if isinstance(n, ast.keyword) and n.arg == "mode" and \
                isinstance(n.value, ast.Constant) and \
                isinstance(n.value.value, str) and \
                any(c in n.value.value for c in "wax+"):
            return True
    return False


def _dominant(kind):
    """A tuple binding reduced to one origin: LIVE beats JOIN beats DECLARED."""
    if not isinstance(kind, list):
        return kind
    for k in (LIVE, JOIN, DECLARED):
        if k in kind:
            return k
    return OTHER


def _classify(node, env):
    """The origin of an expression: LIVE beats JOIN beats DECLARED.

    LIVE wins because one live operand is enough to make an assertion a
    claim about the tree, which is the property being looked for."""
    names, calls = _names_and_calls(node)
    kinds = set(_dominant(env.get(n, OTHER)) for n in names)
    if calls & set(LIVE_SOURCES) or LIVE in kinds:
        return LIVE
    if calls & set(JOIN_SOURCES) or JOIN in kinds:
        return JOIN
    if calls & set(DECLARED_SOURCES) or DECLARED in kinds:
        return DECLARED
    # Round 519: the document read the plain way. Guarded twice -- a
    # function that writes its own fixtures reads its own data back, and a
    # read of the tree's SOURCE is a live measurement, not a document.
    if not env.get(SELF_WRITTEN) and _reads_disk(node):
        return LIVE if _read_target(node, env) == "source" else DECLARED
    return OTHER


def _elementwise(node, env):
    """A tuple expression classified PER ELEMENT, else as a whole.

    THE DIFFERENCE BETWEEN FINDING ROUND 512'S GATE AND NOT FINDING IT.
    `test_subjprov.py`'s `live` fixture is

        rows, helpers = S.compare_with_census()
        return rows, helpers, S.guard_rows()

    -- a JOIN, an opaque helper map and a genuinely LIVE scan, in one
    tuple. Classified as a whole it is LIVE, because `guard_rows` is; and
    then `rows, _helpers, _guards = live` makes `rows` LIVE too, and
    `assert [len(rows), A.load_census()["totals"]["pairs"]] == [57, 57]`
    reads as a live-versus-declared comparison. It is not one: `len(rows)`
    counts census pairs. Element-wise binding is what keeps the third
    element's liveness from being spread over the first."""
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_classify(e, env) for e in node.elts]
    # A name already bound to a per-element origin keeps it. Without this
    # `rows, _h, _g = live` collapses the fixture's [JOIN, JOIN, LIVE] back
    # to LIVE at the first unpack and the analysis is exactly as blind as
    # the whole-tuple version it replaced.
    if isinstance(node, ast.Name) and isinstance(env.get(node.id), list):
        return env[node.id]
    return _classify(node, env)


def _bind(target, kind, env):
    """Bind an assignment target, distributing a tuple origin element-wise."""
    if isinstance(target, (ast.Tuple, ast.List)) and \
            isinstance(kind, list) and len(kind) == len(target.elts):
        for el, k in zip(target.elts, kind):
            _bind(el, k, env)
        return
    flat = _dominant(kind)
    if isinstance(target, ast.Name):
        env[target.id] = kind if isinstance(kind, list) else flat
        return
    key = _attr_key(target)                     # round 519: `self.reg = ...`
    if key:
        env[key] = kind if isinstance(kind, list) else flat
        return
    for n in ast.walk(target):
        if isinstance(n, ast.Name):
            env[n.id] = flat


def _fixture_origins(tree):
    """Fixture name -> origin, by reading the fixture's own return.

    A fixture called `live` is not evidence that it is live. In
    `test_subjprov.py` it returns `compare_with_census()`, which is a JOIN;
    in `test_testcorpus_contributions.py` a fixture of the same name
    returns a genuine harvest. Round 512's gate survived twelve rounds
    partly because its file's `live` fixture reads the census."""
    out = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        decorated = any("fixture" in ast.dump(d) for d in fn.decorator_list)
        if not decorated:
            continue
        inner = {}
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign):
                _bind_all(n.targets, _elementwise(n.value, inner), inner)
        got = None
        for n in ast.walk(fn):
            value = None
            if isinstance(n, ast.Return):
                value = n.value
            elif isinstance(n, ast.Yield):
                value = n.value
            if value is None:
                continue
            got = _elementwise(value, inner)
            break
        if got is not None and _dominant(got) != OTHER:
            out[fn.name] = got
    return out


def _bind_all(targets, kind, env):
    for t in targets:
        _bind(t, kind, env)


def _class_env(cls, fixtures, base=None):
    """Origins bound by a `unittest` class's `setUp` / `setUpClass`.

    ROUND 519. Returned separately from the write flag because a `setUp`
    that builds a temp repo makes every read in every method of that class
    a read of the class's OWN data."""
    env, wrote = dict(base or {}), False
    for fn in cls.body:
        if not (isinstance(fn, ast.FunctionDef)
                and fn.name in ("setUp", "setUpClass")):
            continue
        wrote = wrote or _writes_or_temps(fn)
        if wrote:
            env[SELF_WRITTEN] = True
        for n in ast.walk(fn):
            if isinstance(n, ast.Assign):
                _bind_all(n.targets, _elementwise(n.value, env), env)
    return env, wrote


def _fn_env(fn, fixtures, base=None):
    """name -> origin inside one test function."""
    env = dict(base or {})
    #: Function-LOCAL literals matter as much as module ones: the harness
    #: suite writes `script = os.path.join(d, "run_tests_fast.sh")` inside
    #: the test, and without this the read that follows is `unresolved`
    #: rather than `source` -- so a genuine tree measurement is published
    #: as a self-reference.
    env[LITERALS] = dict((base or {}).get(LITERALS, {}))
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        lits = [c.value for c in ast.walk(node.value)
                if isinstance(c, ast.Constant) and isinstance(c.value, str)]
        if not lits:
            continue
        for t in node.targets:
            for nm in ast.walk(t):
                if isinstance(nm, ast.Name):
                    env[LITERALS][nm.id] = lits
    if _writes_or_temps(fn):
        env[SELF_WRITTEN] = True
    for a in fn.args.args + fn.args.kwonlyargs:
        if a.arg in fixtures:
            env[a.arg] = fixtures[a.arg]
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        kind = _elementwise(value, env)
        if _dominant(kind) == OTHER:
            continue
        if kind == DECLARED and _reads_disk(value):
            tgt = _read_target(value, env)
            for t in targets:
                for nm in ast.walk(t):
                    if isinstance(nm, ast.Name):
                        env[READS + nm.id] = tgt
        elif kind == DECLARED:
            #: propagate: `again = json.dumps(obj)` inherits `obj`'s read.
            srcs = [env[READS + n.id] for n in ast.walk(value)
                    if isinstance(n, ast.Name) and READS + n.id in env]
            if srcs:
                for t in targets:
                    for nm in ast.walk(t):
                        if isinstance(nm, ast.Name):
                            env[READS + nm.id] = srcs[0]
        _bind_all(targets, kind, env)
    return env


def _row_reads(node, env):
    """What the reads behind ONE operand opened, transitively."""
    out = set()
    if _reads_disk(node):
        out.add(_read_target(node, env))
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and READS + n.id in env:
            out.add(env[READS + n.id])
    return out


def _derived_operands(node, env):
    """Distinct top-most sub-expressions that come from the document.

    Top-most so that `d["totals"]["pairs"]` counts once rather than three
    times, and distinct by source position so that the same expression
    written twice is one operand, not two."""
    found, seen = [], set()
    #: Only these END the descent. Without them the whole `Compare` node
    #: classifies as DECLARED and the assert reads as ONE operand, which
    #: is how the first draft of this analysis reported zero findings on a
    #: tree that has two.
    terminal = (ast.Name, ast.Attribute, ast.Subscript, ast.Call)

    def walk(n):
        if isinstance(n, terminal) and _classify(n, env) in (DECLARED, JOIN):
            key = ast.dump(n)
            if key not in seen:
                seen.add(key)
                found.append((n, _classify(n, env)))
            return
        for child in ast.iter_child_nodes(n):
            walk(child)

    walk(node)
    return found


def _assert_exprs(fn):
    """Every assertion in one test function, as `(expr, lineno, form)`.

    `form` is `"assert"` or the `unittest` method name. A binary method
    contributes a synthetic tuple of its first two arguments, which is what
    `_derived_operands` already knows how to descend; a unary one
    contributes its single argument, so `assertTrue(a == b)` still yields
    two operands. `assertRaises` and friends are not comparisons and are
    not assertions for this purpose -- they are counted as SKIPPED-AS-
    NON-COMPARING rather than silently dropped."""
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Assert):
            out.append((n.test, n.lineno, "assert"))
            continue
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        name = n.func.attr
        if name in UNITTEST_BINARY and len(n.args) >= 2:
            pair = ast.Tuple(elts=[n.args[0], n.args[1]], ctx=ast.Load())
            ast.copy_location(pair, n)
            out.append((pair, n.lineno, name))
        elif name in UNITTEST_UNARY and n.args:
            out.append((n.args[0], n.lineno, name))
    return out


def _test_files(directory):
    """`test_*.py` under `directory`, RECURSIVELY.

    ROUND 519. The walk was a single non-recursive `os.listdir`, so
    `--tests skills` -- the directory round 516's next-step #5 names -- read
    ZERO files and reported a clean tree. `skills/` has 17 test files, none
    of them at its top level."""
    skip = ("__pycache__", "node_modules", "research-env", ".git",
            "site-packages", ".venv")
    out = []
    for base, dirs, names in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in sorted(names):
            if name.startswith("test_") and name.endswith(".py"):
                out.append(os.path.join(base, name))
    return sorted(out)


def selfref_scan(directory=None):
    """`(rows, census)` -- the findings AND the population they came from.

    ROUND 519. The findings alone are not a result. `render_selfref` used
    to print, for an empty list, "none -- every one has an operand measured
    from the tree" -- a claim about assertions, quantified over a set that
    may be EMPTY. Run against `skills/skill-authoring/scripts` it examined
    1 026 test functions, found 0 assertions (that suite is `unittest`, so
    every one of its 1 865 assertions is a method call) and printed the
    clean-tree line. This is round 513's shape exactly: the absence was a
    fact about the FILTER and the message was written about the far side.
    The census is the denominator, and it is what makes the zero readable.
    """
    directory = directory or os.path.join(HERE, "tests")
    rows = []
    census = {"dir": directory, "files": 0, "functions": 0, "assertions": 0,
              "bare": 0, "unittest": 0, "reported": 0, "skipped_live": 0,
              "skipped_pin": 0, "skipped_no_declared": 0,
              "unresolved_read": 0, "synthetic": 0}
    for path in _test_files(directory):
        census["files"] += 1
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            tree = ast.parse(src)
        except SyntaxError:                     # pragma: no cover
            continue
        name = os.path.relpath(path, directory)
        fixtures = _fixture_origins(tree)
        lines = src.splitlines()
        mlits = {LITERALS: _module_literals(tree)}
        class_of, class_envs = {}, {}
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            class_envs[cls.name] = _class_env(cls, fixtures, mlits)[0]
            for m in cls.body:
                if isinstance(m, ast.FunctionDef):
                    class_of[id(m)] = cls.name
        for fn in ast.walk(tree):
            if not (isinstance(fn, ast.FunctionDef)
                    and fn.name.startswith("test")):
                continue
            census["functions"] += 1
            env = _fn_env(fn, fixtures,
                          class_envs.get(class_of.get(id(fn)), mlits))
            for node, lineno, form in _assert_exprs(fn):
                census["assertions"] += 1
                census["bare" if form == "assert" else "unittest"] += 1
                if _classify(node, env) == LIVE:
                    census["skipped_live"] += 1
                    continue
                ops = _derived_operands(node, env)
                if not ops:
                    census["skipped_no_declared"] += 1
                    continue
                if len(ops) < 2:
                    census["skipped_pin"] += 1
                    continue
                census["reported"] += 1
                reads = sorted(set().union(*[_row_reads(o, env)
                                             for o, k in ops]))
                synthetic = bool(env.get(SELF_WRITTEN))
                census["synthetic"] += synthetic
                census["unresolved_read"] += "unresolved" in reads
                rows.append({
                    "file": name,
                    "func": fn.name,
                    "lineno": lineno,
                    "form": form,
                    "reads": reads,
                    "synthetic": synthetic,
                    "source": lines[lineno - 1].strip()[:160],
                    "operands": sorted(set(
                        "%s(%s)" % (_src(o, lines), k) for o, k in ops)),
                    "join": any(k == JOIN for _o, k in ops),
                })
    return rows, census


def selfref_asserts(directory=None):
    """Assert statements whose truth is a function of the LEDGER ALONE.

    ROUND 512's NEXT-STEP #8, and the second way a gate can be vacuous.
    `checkscope --scope` finds a gate that ranges over too FEW of its
    document's keys; this finds one that never leaves the document.

    THE RULE: an assertion is reported when it relates TWO OR MORE distinct
    expressions derived from the declared document (or from a JOIN onto
    it) and NO expression derived from the tree. One declared expression
    against a literal is not reported -- that is a pin, and the literal is
    external information a human typed.

    `depthcensus.check_contributions` already states the rule this looks
    for, and obeys it: it re-derives each row's two internal identities
    "against the LIVE side ... A ledger that can only be compared to
    itself proves nothing."

    Heuristic, and PUBLISHED RATHER THAN FILTERED -- the convention every
    census in this tree follows. An internal-consistency assertion is a
    legitimate thing to write; this cannot tell one from a gate that
    believes it is checking the tree, and reports where a reader decides.

    Round 519 kept this signature and moved the body to `selfref_scan`,
    which also returns the population. Callers that only want the rows are
    unchanged; callers that want to know whether a zero MEANS anything have
    to ask for the census, which is the point."""
    return selfref_scan(directory)[0]


def _src(node, lines):
    """The source text of an operand, on one line, for the report."""
    try:
        seg = "\n".join(lines[node.lineno - 1:node.end_lineno])
        if node.lineno == node.end_lineno:
            seg = lines[node.lineno - 1][node.col_offset:node.end_col_offset]
    except (AttributeError, IndexError):        # pragma: no cover
        return "?"
    return " ".join(seg.split())[:70]


def render_selfref(rows, census=None):
    """The findings, then the population -- never the findings alone.

    ROUND 519. The old zero-message was `"none -- every one has an operand
    measured from the tree"`, which asserts a property of every assertion
    in the directory. It printed unchanged when the directory held no
    assertions the analysis could read, and when it held no test files at
    all. A report that cannot tell those apart cannot be believed when it
    says zero, so the denominator is printed for every run and the empty
    population is called out by name."""
    out = ["assertions whose truth is a function of the ledger alone -- %d"
           % len(rows)]
    for r in rows:
        out.append("  %s::%s:%d%s%s"
                   % (r["file"], r["func"], r["lineno"],
                      "" if r.get("form", "assert") == "assert"
                      else "   [%s]" % r["form"],
                      "   [via a JOIN]" if r["join"] else ""))
        tags = ([] if not r.get("synthetic") else ["fixture written by the "
                                                  "test itself"]) + \
            ["read: " + x for x in r.get("reads", [])]
        if tags:
            out.append("      (%s)" % "; ".join(tags))
        out.append("      %s" % r["source"])
        for o in r["operands"]:
            out.append("        operand %s" % o)
    if census is None:                          # pragma: no cover
        if not rows:
            out.append("  none reported (no census taken -- call "
                       "selfref_scan for the denominator)")
        return "\n".join(out)
    c = census
    out.append("  population: %d file(s), %d test function(s), "
               "%d assertion(s) (%d bare `assert`, %d unittest method)"
               % (c["files"], c["functions"], c["assertions"],
                  c["bare"], c["unittest"]))
    out.append("  not reported: %d cleared by a LIVE operand, %d pinned "
               "against a literal, %d with no declared operand"
               % (c["skipped_live"], c["skipped_pin"],
                  c["skipped_no_declared"]))
    if not c["files"]:
        out.append("  EMPTY POPULATION -- no test_*.py under %s. This zero "
                   "is a fact about the directory, not about its "
                   "assertions." % c["dir"])
    elif not c["assertions"]:
        out.append("  EMPTY POPULATION -- %d test function(s) and 0 readable "
                   "assertion(s). This zero is a fact about the analysis, "
                   "not about the suite." % c["functions"])
    elif not rows:
        out.append("  none of the %d assertion(s) examined relates two "
                   "declared expressions with nothing measured from the "
                   "tree." % c["assertions"])
    return "\n".join(out)


# ------------------------------------------- who else uses this instrument

#: Attributes of THIS module that a MEASURED GATE may reach for.
#: ROUND 516's next-step #4: `checkscope` is imported by `subjprov` and
#: `assertshadow`, two of the five gates it measures, and by round 518 also
#: by `runlive` and `builtinlive`. That is benign for exactly one reason,
#: and the reason is a property of the function rather than of the callers:
#: `document_diff` is pure in its two arguments. It is NOT benign for the
#: module's other names. `ROOT` is read from `AGI_RESEARCH_ROOT` at import
#: and `LEDGER_DIR` is derived from it -- and `run_gate` SETS that variable
#: to the mirror root while a pytest gate is being measured. A gate that
#: read `checkscope.LEDGER_DIR` would therefore be reading the MUTANT
#: directory, handed to it by the instrument that is grading it.
SAFE_ATTRIBUTES = ("document_diff", "DECLARED", "LIVE", "JOIN", "OTHER")

#: Module-level bindings whose value expression mentions one of these is
#: STATE -- it depends on the filesystem, the environment or the cwd -- and
#: a pure function may not read one.
STATEFUL_CALLS = ("environ", "getenv", "dirname", "abspath", "join",
                  "getcwd", "listdir", "open", "expanduser", "realpath",
                  "mkdtemp", "gettempdir")


def _module_bindings(tree):
    """`{name: kind}` for every module-level binding: function / class /
    module / path / constant. `path` is the one that matters -- a binding
    whose value is computed from the environment or the filesystem."""
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = "function"
        elif isinstance(node, ast.ClassDef):
            out[node.name] = "class"
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out[(a.asname or a.name).split(".")[0]] = "module"
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = (node.targets if isinstance(node, ast.Assign)
                       else [node.target])
            names, calls = (_names_and_calls(node.value)
                            if node.value is not None else (set(), set()))
            attrs = set()
            if node.value is not None:
                for n in ast.walk(node.value):
                    if isinstance(n, ast.Attribute):
                        attrs.add(n.attr)
            kind = ("path" if (calls | attrs | names) & set(STATEFUL_CALLS)
                    else "constant")
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out[n.id] = kind
    return out


def _locally_bound(fn):
    """Every name the function binds itself -- so a global READ is not
    confused with a local write of the same name."""
    bound = set(a.arg for a in fn.args.args + fn.args.kwonlyargs
                + fn.args.posonlyargs)
    if fn.args.vararg:
        bound.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        bound.add(fn.args.kwarg.arg)
    for n in ast.walk(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store,
                                                          ast.Del)):
            bound.add(n.id)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                bound.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            bound.add(n.name)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
    return bound


def function_reads(name, path=None):
    """`{module-level name: kind}` that `name`'s body READS.

    The evidence for "benign", stated so it can be falsified rather than
    asserted. A function that reads only other functions and literals
    cannot be affected by the instrument's own root, its ledger directory
    or its gate table -- which is the entire argument for letting a gate
    import the module that grades it."""
    path = path or os.path.join(HERE, "checkscope.py")
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    bindings = _module_bindings(tree)
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and fn.name == name:
            local = _locally_bound(fn)
            out = {}
            for n in ast.walk(fn):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) \
                        and n.id not in local and n.id in bindings:
                    out[n.id] = bindings[n.id]
            return out
    raise KeyError("no module-level function %r in %s" % (name, path))


def importers(directory=None, module="checkscope"):
    """`[{module, imports, scope, attributes, unsafe}]` -- every module in
    `directory` that imports `module`, and what it reaches for.

    ROUND 516's next-step #4 turned from a note into a runnable gate. The
    edge is real: four of the five gates this module measures now import
    it. What makes it benign is not the count, it is that every one of
    them touches only `SAFE_ATTRIBUTES`. `unsafe` is the list that breaks
    that, and `--importers --strict` exits 1 on it."""
    directory = directory or HERE
    out = []
    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".py") or fname == module + ".py":
            continue
        with open(os.path.join(directory, fname), encoding="utf-8") as fh:
            src = fh.read()
        try:
            tree = ast.parse(src)
        except SyntaxError:                     # pragma: no cover
            continue
        # Which import statements name the module, and at what scope.
        inner = set()
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    inner.add(id(n))
        sites, attrs, alias = [], set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == module:
                        alias.add(a.asname or a.name)
                        sites.append((node.lineno,
                                      "function" if id(node) in inner
                                      else "module"))
            elif isinstance(node, ast.ImportFrom) and node.module == module:
                for a in node.names:
                    attrs.add(a.name)
                sites.append((node.lineno,
                              "function" if id(node) in inner else "module"))
        if not sites:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) \
                    and isinstance(node.value, ast.Name) \
                    and node.value.id in alias:
                attrs.add(node.attr)
        out.append({
            "module": fname,
            "lines": sorted(l for l, _s in sites),
            "scope": ("module" if any(s == "module" for _l, s in sites)
                      else "function"),
            "attributes": sorted(attrs),
            "unsafe": sorted(a for a in attrs if a not in SAFE_ATTRIBUTES),
        })
    return out


def render_importers(rows, path=None):
    reads = function_reads("document_diff", path)
    stateful = sorted(k for k, v in reads.items() if v == "path")
    out = ["%d module(s) here import checkscope" % len(rows)]
    for r in rows:
        out.append("  %-22s %-8s line(s) %s   %s%s"
                   % (r["module"], r["scope"],
                      ", ".join(map(str, r["lines"])),
                      ", ".join(r["attributes"]) or "-",
                      "   UNSAFE: " + ", ".join(r["unsafe"])
                      if r["unsafe"] else ""))
    out.append("  document_diff reads %d module-level name(s): %s"
               % (len(reads), ", ".join("%s(%s)" % (k, v)
                                        for k, v in sorted(reads.items()))
                  or "none"))
    out.append("  %s"
               % ("REACHES MODULE STATE: " + ", ".join(stateful) if stateful
                  else "no path- or environment-derived state -- the import "
                       "edge is benign for this attribute"))
    return "\n".join(out)


# ------------------------------------------------------------------- rendering

def render_list(ledger_dir=None):
    out = ["checkscope: %d gate(s)" % len(GATES)]
    for name in sorted(GATES):
        g = GATES[name]
        out.append("  %-32s %-7s %s" % (name, g["kind"], g["verb"]))
    ungated, orphan = gate_gaps(ledger_dir)
    for n in ungated:
        out.append("  UNCOVERED  %s -- generated, but no gate entry here" % n)
    for n in orphan:
        out.append("  ORPHAN     %s -- gate entry for no generated ledger" % n)
    if not (ungated or orphan):
        out.append("  every generated ledger has a gate, and no gate is "
                   "stale")
    return "\n".join(out)


def render_scope(rows):
    out = []
    for r in rows:
        if r.get("status") != "ok":
            out.append("%s  [%s] %s" % (r["ledger"], r["status"],
                                        r.get("why", "")))
            out.append("    control rc=%d: %s"
                       % (r["control"]["rc"],
                          r["control"]["output"].strip().splitlines()[-1]
                          if r["control"]["output"].strip() else ""))
            continue
        seen = sum(1 for c in r["keys"] if c["seen"])
        tot = sum(1 for c in r["keys"] if c.get("total"))
        out.append("%s  -- %s  sees %d/%d key(s), total over %d"
                   % (r["ledger"], r["verb"], seen, len(r["keys"]), tot))
        for c in r["keys"]:
            out.append("    %-34s delete=%-10s corrupt=%-10s%s%s"
                       % (c["key"], c["verdicts"][MUT_DELETE],
                          c["verdicts"][MUT_CORRUPT],
                          "  (prose)" if c["prose"] else "",
                          "  PARTIAL" if c.get("partial") else ""))
    cov = coverage(rows)
    out.append("")
    out.append("%d key(s) across %d scored ledger(s): %d seen under some "
               "mutation, %d under EVERY applicable one, %d partial, "
               "%d blind, %d reachable only as a CRASH"
               % (cov["keys"], sum(1 for r in rows
                                   if r.get("status") == "ok"),
                  cov["seen"], cov["total"], cov["partial"], cov["blind"],
                  cov["crash"]))
    total = [r["ledger"] for r in rows
             if r.get("status") == "ok"
             and r["keys"] and all(c.get("total") for c in r["keys"])]
    out.append("total gates: %s" % (", ".join(total) if total else "NONE"))
    return "\n".join(out)


def build_report(rows):
    cov = coverage(rows)
    return {
        "_what": "which top-level keys of each generated ledger under "
                 "state/whence its OWN --check verb can see, measured by "
                 "mutation -- round 512's next-steps #4 and #6, answered "
                 "by round 516.",
        "_regenerate": "cd languages/whence && python3 checkscope.py "
                       "--scope --json <this file>",
        "_method": "one key perturbed per run (delete, and the smallest "
                   "corruption its type allows); the gate is pointed at "
                   "the mutant; a non-zero exit is SEES, exit 0 is BLIND, "
                   "a traceback is CRASH. Every ledger's sweep starts from "
                   "an unmutated control that must exit 0.",
        "totals": {"keys": cov["keys"], "seen": cov["seen"],
                   "seen_under_every_applicable_mutation": cov["total"],
                   "partial": cov["partial"], "blind": cov["blind"],
                   "crash_only": cov["crash"]},
        "ledgers": rows,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scope", action="store_true")
    ap.add_argument("--importers", action="store_true",
                    help="every module that imports this one and what it "
                         "reaches for (round 516's next-step #4)")
    ap.add_argument("--src", default=None,
                    help="a directory of modules for --importers")
    ap.add_argument("--selfref", action="store_true",
                    help="assertions whose two sides both come from the "
                         "declared document (round 512's next-step #8). "
                         "Prints its POPULATION on every run; with --strict "
                         "exits 1 when that population is EMPTY (round 519)")
    ap.add_argument("--tests", default=None,
                    help="a tests/ directory, walked RECURSIVELY (round 519)")
    ap.add_argument("--only", default=None,
                    help="one ledger name instead of all of them")
    ap.add_argument("--json", default=None)
    ap.add_argument("--dir", default=None, help="a ledger directory")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 unless every gate is total over its own "
                         "document; with --selfref, exit 1 on an empty "
                         "population; with --importers, on an unsafe edge")
    args = ap.parse_args(argv)
    if not (args.list or args.scope or args.selfref or args.importers):
        args.list = True
    if args.list:
        print(render_list(args.dir))
    imp_bad = []
    if args.importers:
        imps = importers(args.src)
        print(render_importers(imps))
        imp_bad = [r for r in imps if r["unsafe"]]
    sref_empty = False
    if args.selfref:
        sref, scensus = selfref_scan(args.tests)
        print(render_selfref(sref, scensus))
        #: `--selfref --strict` reddens on an EMPTY POPULATION, not on
        #: findings. Findings are published for a reader to judge (the
        #: module's own convention); a run that examined nothing and
        #: printed a clean line is the failure that LOOKS like a pass.
        sref_empty = not scensus["assertions"]
    if not args.scope:
        return 1 if (args.strict and (imp_bad or sref_empty)) else 0

    names = sorted(GATES) if args.only is None else [args.only]
    rows = []
    for name in names:
        if name not in GATES:
            print("no gate for %s" % name)
            return 2
        if not args.quiet:
            print("  sweeping %s ..." % name, flush=True)
        rows.append(scope_one(name, GATES[name], args.dir,
                              progress=None if args.quiet
                              else lambda s: print(s, flush=True)))
    print(render_scope(rows))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(build_report(rows), fh, indent=2)
            fh.write("\n")
        print("wrote %s" % args.json)
    if args.strict:
        bad = [r for r in rows
               if r.get("status") != "ok"
               or not all(c.get("total") for c in r["keys"])]
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
