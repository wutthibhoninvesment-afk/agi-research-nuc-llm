"""Round 512 (language C): the gate that is total in what drifts.

WHY THIS FILE EXISTS. Round 510 added `tests/test_branchlive.py` and
reddened SEVEN nodes in FOUR suite files, none of which says the word
"ledger" in its name:

    test_assertshadow.py::test_the_full_census_matches_the_ledger_on_disk
    test_assertshadow.py::test_the_cli_check_exits_zero_on_this_tree
    test_subjprov.py::test_the_cli_check_runs_all_three_gates_and_is_green...
    test_testcorpus_census.py::test_the_exclusions_are_counted_and_reconcile...
    test_testcorpus_contributions.py::test_the_ledger_covers_exactly_the_files...
    test_testcorpus_contributions.py::test_every_declared_contribution_matches...
    test_testcorpus_contributions.py::test_the_ledger_sums_to_the_live_totals

One cause, seven reds, two rounds open. And round 512 measured that the
seven UNDER-report it: `assert-shadow-census.json` had been stale since
round 500 (72 -> 76 files, 1935 -> 2029 test functions, 3908 -> 4122
asserts) and `subject-provenance.json` was stale with NO red at all --
`subjprov.py --check` prints "0 finding(s)" and exits 0 while the ledger on
disk is missing `test_specstale.py`.

`test_every_generated_ledger_reproduces_byte_for_byte` below is one node
whose predicate is TOTAL in the thing that drifts: it re-runs each ledger's
own declared generator and compares bytes. A corpus addition now reddens
ONE node carrying an exact one-command fix, instead of seven nodes carrying
five different regeneration recipes between them.

THIS FILE IS ITSELF IN THE CORPUS, and that is not an oversight -- see
`test_this_files_own_contribution_is_declared_like_any_other`. Adding it
changed `testcorpus-contributions.json` and `assert-shadow-census.json`,
and round 512 regenerated both AFTER writing it. A gate over the corpus
that exempted itself would be the one file whose addition it could not see.

Ordering note (round 494's decision 64, and this file obeys it): where a
node asserts both a SHAPE and a SIZE, the shape assertion comes FIRST, so
that a count moving cannot shadow a structure changing.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import corpusledger as cl                                   # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 1. the registry -- every ledger is classified, none is silently skipped
# ---------------------------------------------------------------------------

def test_every_ledger_in_the_tree_is_classified():
    """MISSING classification is a named failure, not an omission.

    The failure mode this replaces: a new `state/whence/*.json` appears,
    nothing knows how to regenerate it, and no output anywhere says so."""
    rows = cl.registry()
    unknown = sorted(r["name"] for r in rows if r["source"] == "unknown")
    assert unknown == [], (
        "ledger(s) with no `_regenerate`/`_generated_by` field and no entry "
        "in corpusledger.UNDECLARED or NOT_GENERATED -- add one, with a "
        "reason: %s" % unknown)


def test_the_registry_covers_exactly_the_json_files_on_disk():
    """Set difference in both directions, for the same reason round 494 gave:
    "somebody added a ledger" and "a ledger was deleted" are different
    failures and must not arrive as one count."""
    rows = cl.registry()
    on_disk = set(cl.ledger_paths())
    named = {r["name"] for r in rows}
    assert sorted(on_disk - named) == [], "on disk, not in the registry"
    assert sorted(named - on_disk) == [], "in the registry, not on disk"


def test_the_registry_prefers_the_artefacts_own_declaration():
    """The design decision that keeps this module from becoming the sixth
    stale artefact: where the generator writes its own command into the
    file, THAT is the command used. A hand-typed table here would be one
    more thing to forget to update."""
    by_name = {r["name"]: r for r in cl.registry()}
    for name in ("assert-shadow-census.json", "subject-provenance.json",
                 "testcorpus-contributions.json"):
        row = by_name[name]
        assert row["source"] == "self", row
        raw = json.load(open(row["path"], encoding="utf-8"))
        declared = [raw[f] for f in cl.DECL_FIELDS if f in raw]
        assert row["command"] in [d.strip() for d in declared], row


def test_a_ledger_declared_here_says_why_its_generator_could_not():
    """A coverage gap with no reason attached is indistinguishable from an
    oversight, which is how the two `builtin-*` ledgers would read."""
    for name, ent in cl.UNDECLARED.items():
        assert ent["why"].strip(), name
        assert "<" in ent["command"], ("a hand-declared command needs a "
                                       "placeholder to be sandboxable: %s"
                                       % name)
    for name, why in cl.NOT_GENERATED.items():
        assert why.strip(), name


# ---------------------------------------------------------------------------
# 2. the sandbox -- a check that overwrites its subject proves nothing
# ---------------------------------------------------------------------------

def test_the_sandbox_rewrites_a_command_that_names_its_own_ledger():
    """`subject-provenance.json`'s declared command names its REAL path.
    Run verbatim it would rewrite the file it is supposed to be checking and
    report fresh every time -- a check that cannot fail."""
    ledger = os.path.join(cl.LEDGER_DIR, "subject-provenance.json")
    cwd, argv = cl.split_command(
        "cd languages/whence && python3 subjprov.py --json "
        "../../state/whence/subject-provenance.json")
    out = cl.sandbox(cl._placeholder_join(argv), cwd, ledger, "/tmp/OUT.json")
    assert out[-1] == "/tmp/OUT.json"
    assert not any("subject-provenance" in tok for tok in out), out


def test_a_placeholder_split_by_shlex_is_rejoined():
    """`--json <this file>` is three shlex tokens, none of which is a
    well-formed placeholder. Without the rejoin the census reads as
    UNSANDBOXABLE for a reason that is about quoting, not about the ledger."""
    assert cl._placeholder_join(["--json", "<this", "file>"]) == \
        ["--json", "<this file>"]
    assert cl._placeholder_join(["--json", "<path>"]) == ["--json", "<path>"]
    assert cl._placeholder_join(["--json", "<unterminated"]) == \
        ["--json", "<unterminated"]


@pytest.mark.parametrize("argv,why", [
    (["python3", "gen.py"], "no output token at all -- the check would be "
                            "vacuous"),
    (["python3", "gen.py", "--json", "<a>", "--also", "<b>"],
     "two output tokens -- which one is the ledger?"),
])
def test_the_sandbox_refuses_what_it_cannot_redirect(argv, why):
    """Zero substitutions and two substitutions are both refused rather than
    guessed. Guessing here means either a vacuous PASS or a clobbered
    ledger, and both are worse than an honest refusal."""
    with pytest.raises(cl.Unsandboxable):
        cl.sandbox(argv, cl.HERE, "/nowhere/x.json", "/tmp/OUT.json")


def test_split_command_understands_the_cd_prefix_and_refuses_other_shell():
    cwd, argv = cl.split_command("cd languages/whence && python3 x.py")
    assert argv == ["python3", "x.py"]
    assert os.path.basename(cwd) == "whence"
    for bad in ("python3 x.py; rm -rf /", "python3 x.py | tee out",
                "python3 x.py && python3 y.py"):
        with pytest.raises(cl.Unsandboxable):
            cl.split_command(bad)


def test_checking_a_self_naming_ledger_does_not_rewrite_it():
    """The sandbox, end to end rather than as a unit. `subject-provenance`
    is the one whose declared command names itself, so it is the one worth
    the ~3s: its bytes must be identical either side of a `--check`."""
    path = os.path.join(cl.LEDGER_DIR, "subject-provenance.json")
    before = open(path, "rb").read()
    cl.check(only={"subject-provenance.json"})
    assert open(path, "rb").read() == before


# ---------------------------------------------------------------------------
# 3. the negative control -- does the check detect drift it did not cause?
# ---------------------------------------------------------------------------

#: A generator that DECLARES ITSELF, exactly as the three real self-
#: declaring ledgers do. It reconstructs its own invocation from argv rather
#: than carrying a hardcoded string -- which is the same discipline this
#: module is about, and the first draft of this fixture got it wrong in
#: precisely the way the real tree does: the declaration said one thing and
#: the run produced another, so a genuinely fresh ledger read as STALE.
_GEN = """\
import json, os, sys
corpus = sys.argv[1]
out = sys.argv[sys.argv.index("--json") + 1]
cmd = "cd %s && python3 gen.py %s --json <path>" % (os.getcwd(), corpus)
files = sorted(f for f in os.listdir(corpus) if f.endswith(".txt"))
with open(out, "w") as fh:
    json.dump({"_generated_by": cmd, "files": files}, fh,
              indent=1, sort_keys=True)
    fh.write("\\n")
"""


@pytest.fixture
def fake(tmp_path):
    """A ledger dir, a corpus dir and a generator that derives one from the
    other -- the whole shape in miniature, so that STALE and FIX can be
    exercised without regenerating the real tree."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("a")
    gen = tmp_path / "gen.py"
    gen.write_text(_GEN)
    ledgers = tmp_path / "ledgers"
    ledgers.mkdir()
    led = ledgers / "fake.json"
    subprocess.run([sys.executable, str(gen), str(corpus), "--json",
                    str(led)], check=True, cwd=str(tmp_path))
    return {"dir": str(ledgers), "corpus": corpus, "ledger": led}


def test_a_fresh_synthetic_ledger_reads_as_fresh(fake):
    """The control's control. Without this, a checker that reported STALE
    unconditionally would pass the drift test below."""
    res = cl.check(directory=fake["dir"])
    assert [r["status"] for r in res] == ["FRESH"], res


def test_an_addition_to_the_corpus_turns_the_synthetic_ledger_stale(fake):
    """THE CLAIM THIS MODULE MAKES, tested where the answer is known: add a
    file to the corpus, change nothing else, and the ledger must go stale
    and must NAME what appeared."""
    (fake["corpus"] / "b.txt").write_text("b")
    res = cl.check(directory=fake["dir"])
    assert [r["status"] for r in res] == ["STALE"], res
    assert "b.txt" in res[0]["detail"], res[0]["detail"]


def test_fix_closes_the_drift_and_is_idempotent(fake):
    """`--fix` must both work and stop working -- a second run has nothing
    to do. An idempotence check is what distinguishes regenerating from
    appending."""
    (fake["corpus"] / "b.txt").write_text("b")
    fixed, bad = cl.fix(directory=fake["dir"])
    assert (sorted(fixed), bad) == (["fake.json"], [])
    assert [r["status"] for r in cl.check(directory=fake["dir"])] == ["FRESH"]
    again, bad2 = cl.fix(directory=fake["dir"])
    assert (again, bad2) == ([], [])


def test_a_generator_that_fails_is_an_ERROR_and_not_a_stale_verdict(fake):
    """Distinguishing "the ledger is out of date" from "the check could not
    run" is the difference between a fix command that works and one that
    quietly writes a truncated file. `--fix` must not touch an ERROR row.

    ROUND 522 kept the intent and split it from a second claim the old
    assertion had bundled with it. Not TOUCHING an ERROR row is right, and
    the byte-comparison below is what pins it. Not MENTIONING it was not a
    decision anybody took: `fix` returned `([], [])` and `cmd_fix` printed
    "nothing stale" and exited 0 on a tree it had failed to make fresh.
    Round 522 hit that live -- `corpusledger.py --fix` regenerated
    `assert-shadow-census.json`, exited 0, and left `subject-provenance
    .json` stale, because that row had come back ERROR in the same pass
    (its generator refuses while its input census is stale) and was
    dropped in silence."""
    shutil.rmtree(str(fake["corpus"]))       # generator will now raise
    res = cl.check(directory=fake["dir"])
    assert [r["status"] for r in res] == ["ERROR"], res
    before = fake["ledger"].read_bytes()
    fixed, bad = cl.fix(directory=fake["dir"])
    assert fixed == []
    assert [n for n, _why in bad] == ["fake.json"]
    assert "not attempted" in bad[0][1], bad[0][1]
    # THE INTENT, unchanged: reported, never rewritten.
    assert fake["ledger"].read_bytes() == before


# ---------------------------------------------------------------------------
# 4. the ratchet
# ---------------------------------------------------------------------------

def test_every_generated_ledger_reproduces_byte_for_byte():
    """THE GATE. One node, total in what drifts.

    Round 512 measured what this replaces: three ledgers stale, caught to
    three different degrees by three different predicates -- the file-set
    gate caught its own (7 reds, 4 files), the shadow-node gate caught its
    own only because round 510's addition happened to contribute a shadow
    pair, and `subject-provenance` was caught by nothing at all.

    If this is the only red you have, the fix is the command in the message
    and nothing else. If it is red ALONGSIDE a suite failure, fix this one
    first -- a stale ledger reddens other people's assertions."""
    res = cl.check()
    stale = cl.stale_names(res)
    broken = cl.broken_names(res)
    assert broken == [], (
        "ledger(s) whose freshness could not be established at all -- this "
        "is not staleness, it is a broken check: %s"
        % [r for r in res if r["name"] in broken])
    assert stale == [], (
        "stale ledger(s). Regenerate: cd languages/whence && python3 "
        "corpusledger.py --fix\n%s"
        % "\n".join("  %-32s %s" % (r["name"], r["detail"])
                    for r in res if r["status"] == "STALE"))


def test_the_cli_agrees_with_the_library_on_this_tree():
    """The CLI is the path the failure message above names, so it is run
    rather than assumed to work -- round 500's lesson, which is why
    `test_the_cli_check_exits_zero_on_this_tree` exists next door."""
    r = subprocess.run([sys.executable, "corpusledger.py", "--check",
                        "--strict"], cwd=cl.HERE, capture_output=True,
                       text=True, timeout=900)
    assert [r.returncode, "reproduces byte-for-byte" in r.stdout] == \
        [0, True], r.stdout + r.stderr


def test_this_files_own_contribution_is_declared_like_any_other():
    """"Your own artefacts are in the corpus." This file adds rows to
    `testcorpus-contributions.json`; a gate over the corpus that exempted
    itself would be blind to exactly one file -- its own.

    Shape before size, per decision 64: that the row EXISTS is the claim;
    its magnitude is incidental and is asserted second."""
    declared = json.load(open(os.path.join(
        cl.LEDGER_DIR, "testcorpus-contributions.json"), encoding="utf-8"))
    assert "test_corpusledger.py" in declared["files"], (
        "this file is not in the contributions ledger -- regenerate it: "
        "cd languages/whence && python3 corpusledger.py --fix")
    mine = declared["files"]["test_corpusledger.py"]
    assert set(mine) >= {"calls", "programs", "residual"}, mine
    assert mine["residual"] == 0, (
        "this file must not add an unreadable residual row to the corpus it "
        "reports on: %s" % mine)
