"""Round 505 (harness A) — tests for `harness/readset.py`.

Two halves, and the split is the point.

The MECHANISM half builds a miniature repo in `tmp_path`, runs a real pytest
inside it under the real audit hook, and asserts on the map that comes out.
Nothing here is about this checkout, so none of it moves when a language
round lands.

The REAL-SUBJECT half is pointed at `harness/readset-map.json` as shipped.
It exists because round 425 named the failure mode it prevents: "the tools'
tests are all pointed at TOY projects, so 'has tests' and 'has tests about
the thing it is used on' came apart and the defect landed in the gap." The
pin that matters is `test_a_new_file_in_the_whence_tree_implicates_the_
copyparity_node` — the shape of round 504's redden, asked with a filename
that does not exist, which is the only way to test the half of the design
(`scans`) that a read set alone cannot express.
"""
import json
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.dirname(_HERE))

import readset as R                                            # noqa: E402

#: The CLI as literal argv, for the same reason
#: `test_swe_copyparity_real_subject.py` writes its own out: `harness/
#: verb_audit.py` reads SOURCE for an entry-point token followed by a verb,
#: and the tests below run exactly these lists from `REPO_ROOT`, so the token
#: the audit reads and the command that runs are one string.
BLAST_ARGV = ["harness/readset.py", "blast"]
SILENT_ARGV = ["harness/readset.py", "silent"]
SHOW_ARGV = ["harness/readset.py", "show"]
RECORD_ARGV = ["harness/readset.py", "record"]

#: A record run of the harness fast tier rosters ~1600 nodes. The floor is
#: far below that so ordinary growth or pruning does not trip it, but a map
#: recorded from a collapsed or mis-selected run does.
MIN_ROSTER = 800


# ------------------------------------------------------------------ helpers --

def _write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _record(root, *pytest_args):
    """Run pytest inside `root` under the plugin; return the parsed map."""
    out = os.path.join(root, "map.json")
    env = dict(os.environ)
    env["READSET_OUT"] = out
    env["READSET_ROOT"] = root
    env["PYTHONPATH"] = (os.path.join(REPO_ROOT, "harness") + os.pathsep
                         + env.get("PYTHONPATH", ""))
    # `-p no:cacheprovider` keeps a `.pytest_cache` out of the tree; the
    # recorder would drop it anyway, and this keeps the assertion honest.
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "readset", "-q",
         "-p", "no:cacheprovider", "-p", "no:randomly"]
        + (list(pytest_args) or ["tests"]),
        cwd=root, env=env, capture_output=True, text=True, timeout=180)
    assert os.path.exists(out), "no map was written"
    with open(out, encoding="utf-8") as f:
        mp = json.load(f)
    # A map from a run that COLLECTED NOTHING has the same shape as a map
    # from a run that recorded nothing, and round 505 spent three tool calls
    # on that ambiguity: an escape in the fixture's own source made the
    # miniature test file unparsable, pytest reported a collection error, and
    # every assertion below failed with "no such key" instead of "the tree
    # did not collect".
    assert mp["roster"], (
        "the miniature suite collected NO tests — that is a broken fixture, "
        "not an empty read set:\n" + (p.stdout or "")[-2000:])
    return mp


def _node(mp, needle):
    keys = [k for k in mp["nodes"] if needle in k]
    assert len(keys) == 1, "expected one key matching %r, got %s" % (
        needle, keys)
    return mp["nodes"][keys[0]]


@pytest.fixture
def mini(tmp_path):
    """A repo-shaped tree: a `data/` directory the tests read and list, a
    `far/` directory nothing touches, and one test per behaviour."""
    r = str(tmp_path / "repo")
    _write(os.path.join(r, "data", "a.txt"), "alpha\n")
    _write(os.path.join(r, "data", "b.txt"), "beta\n")
    _write(os.path.join(r, "far", "c.txt"), "gamma\n")
    _write(os.path.join(r, "helper.py"), "VALUE = 7\n")
    _write(os.path.join(r, "tests", "test_mini.py"), '''
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import helper                                    # a module-level (collect) read

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_reads_one_file():
    assert io.open(os.path.join(ROOT, "data", "a.txt")).read() == "alpha\\n"


def test_lists_the_directory():
    assert sorted(os.listdir(os.path.join(ROOT, "data"))) == ["a.txt", "b.txt"]


def test_writes_a_file():
    with io.open(os.path.join(ROOT, "data", "written.txt"), "w") as f:
        f.write("x")


def test_reads_outside_the_root(tmp_path):
    p = tmp_path / "outside.txt"
    p.write_text("out")
    assert p.read_text() == "out"


def test_touches_nothing():
    assert 1 + 1 == 2


def test_probe_writes_what_a_child_process_inherits():
    """Not an assertion — a WITNESS. The outer test reads probe.json."""
    import json, subprocess
    child = subprocess.run(
        [sys.executable, "-c",
         "import os,json,importlib.util;"
         "print(json.dumps({'out':os.environ.get('READSET_OUT'),"
         "'root':os.environ.get('READSET_ROOT'),"
         "'pp':os.environ.get('PYTHONPATH'),"
         "'import':importlib.util.find_spec('readset') is not None}))"],
        capture_output=True, text=True)
    with io.open(os.path.join(ROOT, "probe.json"), "w") as f:
        f.write(child.stdout.strip().splitlines()[-1])
''')
    return r


# ------------------------------------------------------------- the recorder --

def test_a_read_is_recorded_against_the_node_that_read_it(mini):
    mp = _record(mini)
    ent = _node(mp, "test_reads_one_file")
    assert "data/a.txt" in ent["files"]
    assert "data/b.txt" not in ent["files"], (
        "b.txt was never opened; a read set that names it is a scan set "
        "wearing the wrong label")


def test_a_write_is_not_a_read(mini):
    """A node that WRITES a repo file does not depend on it. Counting the
    write would make every test that touches `logs/` or a generated registry
    look like a reader of it, and `blast` would then implicate them all on
    any diff under those directories."""
    mp = _record(mini)
    keys = [k for k in mp["nodes"] if "test_writes_a_file" in k]
    written = set()
    for k in keys:
        written |= set(mp["nodes"][k]["files"])
    assert "data/written.txt" not in written, written


def test_a_directory_listing_lands_in_scans_not_files(mini):
    mp = _record(mini)
    ent = _node(mp, "test_lists_the_directory")
    assert "data" in ent["scans"]
    assert not [f for f in ent["files"] if f.startswith("data/")], (
        "listing a directory is not reading its files: %s" % ent["files"])


def test_paths_outside_the_root_are_not_recorded(mini):
    mp = _record(mini)
    keys = [k for k in mp["nodes"] if "test_reads_outside_the_root" in k]
    files = set()
    for k in keys:
        files |= set(mp["nodes"][k]["files"])
    assert files == set(), (
        "a read under /tmp is not a dependence on this repo: %s" % files)
    # The SCAN set is not asserted empty, and that is a measured caveat
    # rather than a looser test. Round 505 found `tests` in this node's scan
    # set with nothing in the node's own code listing it: CPython's import
    # FileFinder re-`scandir`s a `sys.path` directory whose mtime has moved,
    # and the previous test wrote a `__pycache__` entry under `tests/`. So a
    # scan set can name a directory the node never listed. The error is in
    # the over-approximating direction -- `blast` names one extra file to
    # run -- and pinning it empty here would pin pytest's import cache.


def test_a_node_that_touches_nothing_has_no_key_and_is_reported_silent(mini):
    mp = _record(mini)
    assert not [k for k in mp["nodes"] if "test_touches_nothing" in k]
    silent = R.silent_nodes(mp)
    assert [s for s in silent if "test_touches_nothing" in s]
    assert not [s for s in silent if "test_reads_one_file" in s]


def test_module_level_reads_are_kept_in_a_collect_bucket(mini):
    """`import helper` runs at COLLECTION, before any node exists. Round 505
    kept the bucket rather than dropping it because the alternative is a
    silent hole exactly where a test file's top-of-file imports live."""
    mp = _record(mini)
    keys = [k for k in mp["nodes"] if k.endswith(R.COLLECT_SUFFIX)]
    assert keys, "collection reads were attributed to nobody"
    got = set()
    for k in keys:
        got |= set(mp["nodes"][k]["files"])
    assert "helper.py" in got, sorted(got)
    assert R.file_of(keys[0] if "test_mini" in keys[0] else keys[-1])


def test_the_arming_variable_and_the_plugin_path_do_not_reach_a_child(mini):
    """The defect that cost round 505 a 548 s recording, as a falsifier.

    The first `record` armed the plugin with `PYTHONPATH=<root>/harness` and
    left `READSET_OUT` in the environment. Both are inherited by every
    subprocess the suite spawns, and this suite spawns many:

      * `READSET_OUT` inherited => each child installs its own audit hook and
        races the parent to write the SAME map file.
      * `PYTHONPATH` inherited => `harness/tests/test_swe_proc.py::
        test_ref_diff_test_survives_running_from_a_tempdir_copy` went RED. It
        copies `languages/whence` to a tempdir and requires that running it
        there WITHOUT `AGI_RESEARCH_ROOT` fails with `ModuleNotFoundError:
        swe` — round 149's whole point. With the harness directory on the
        inherited path, `import swe` succeeded in the copy, the "broken" run
        came back green and the assertion inverted. The instrument had
        changed the subject.

    The fix is that instrumentation is exactly one process deep: the plugin
    POPS both variables at arm time, and `record` puts the plugin on
    `sys.path` through a `-c` bootstrap rather than on `PYTHONPATH`."""
    # Through the CLI verb on purpose: `_record` above drives pytest itself
    # and sets PYTHONPATH to make the plugin importable, which is exactly the
    # leak under test. Only `record` has the `-c` bootstrap.
    p = subprocess.run(
        [sys.executable, "harness/readset.py", "--root", mini, "record",
         "--out", os.path.join(mini, "cli.json"), "tests"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    with open(os.path.join(mini, "probe.json"), encoding="utf-8") as f:
        probe = json.load(f)
    assert probe["out"] is None, "READSET_OUT survived into a child process"
    assert probe["root"] is None, "READSET_ROOT survived into a child process"
    assert not (probe["pp"] or ""), (
        "PYTHONPATH was exported to the child: %r" % probe["pp"])
    assert probe["import"] is False, (
        "a child process can import the plugin — the recorder is more than "
        "one process deep and the map is no longer attributable")


def test_gitignored_paths_are_dropped_by_gits_own_rule():
    """`logs/` is 65% of an unfiltered map and cannot ever produce a hit: a
    gitignored path never appears in `git status --porcelain`. Asked of git
    rather than re-implemented, and fail-OPEN — if git errors nothing is
    dropped, because an over-full map answers every query correctly and an
    empty one answers `nothing is implicated`."""
    got = R.gitignored({"logs/health_round_1.log", "harness/readset.py",
                        "state/research-state.md"}, REPO_ROOT)
    assert "logs/health_round_1.log" in got
    assert "harness/readset.py" not in got
    assert "state/research-state.md" not in got
    assert R.gitignored(set(), REPO_ROOT) == set()


def test_the_ignored_directory_names_never_reach_the_map():
    rec = R.Recorder(REPO_ROOT)
    for part in ("__pycache__", ".venv", "research-env", "site-packages"):
        assert rec.rel(os.path.join(REPO_ROOT, part, "x.py")) is None, part
    assert rec.rel(os.path.join(REPO_ROOT, "harness", "readset.py")) == \
        "harness/readset.py"


def test_the_repo_root_is_a_scannable_directory_not_a_dropped_path():
    """A node that `os.walk`s the checkout scans the ROOT first, and an
    added TOP-LEVEL file has `os.path.dirname(p) == ""`. Dropping the root
    would make the one directory every whole-tree audit lists the one
    directory no addition can be attributed to."""
    rec = R.Recorder(REPO_ROOT)
    assert rec.rel(REPO_ROOT) == "."
    mp = {"nodes": {"n": {"files": [], "scans": ["."]}}}
    rows = R.implicated(["brand_new_top_level.py"], mp)
    assert rows and rows[0]["hits"][0]["reason"] == "scan"
    assert R.implicated(["sub/brand_new.py"], mp) == []


def test_a_pseudo_path_is_not_a_path():
    """CPython's SyntaxError handler literally calls `open("<unknown>",
    "rb")`. It is relative, so `abspath` places it INSIDE the repo, and the
    first recording round 505 made carried `<unknown>` as a file that no
    diff could ever name."""
    rec = R.Recorder(REPO_ROOT)
    for junk in ("<unknown>", "<string>", "<stdin>",
                 "<frozen importlib._bootstrap>"):
        assert rec.rel(junk) is None, junk


def test_the_read_predicate_follows_the_open_mode():
    assert R.Recorder.is_read("rb", None) is True
    assert R.Recorder.is_read("r", None) is True
    assert R.Recorder.is_read("w", None) is False
    assert R.Recorder.is_read("a", None) is False
    assert R.Recorder.is_read("r+", None) is False
    assert R.Recorder.is_read(None, os.O_RDONLY) is True
    assert R.Recorder.is_read(None, os.O_WRONLY | os.O_CREAT) is False


def test_the_audit_hook_is_not_installed_without_the_env_var():
    """An audit hook cannot be removed once added. Importing this module as
    a library — which `blast` does, and which this very file does — must not
    install one, or every process in this program pays for it forever."""
    env = dict(os.environ)
    env.pop("READSET_OUT", None)
    env["PYTHONPATH"] = os.path.join(REPO_ROOT, "harness")
    p = subprocess.run(
        [sys.executable, "-c",
         "import readset; print('REC', readset._REC)"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    assert "REC None" in p.stdout, p.stdout


# ------------------------------------------------------------- the blast query --

def test_a_modified_file_is_implicated_by_the_read_set(mini):
    mp = _record(mini)
    rows = R.implicated(["data/a.txt"], mp)
    keys = [r["key"] for r in rows]
    assert [k for k in keys if "test_reads_one_file" in k]
    assert all(h["reason"] == "read" for r in rows for h in r["hits"]
               if h["path"] == "data/a.txt" and "reads_one_file" in r["key"])


def test_an_added_file_is_implicated_by_the_scan_set_alone(mini):
    """THE design claim, stated as a test.

    `data/brand_new.txt` does not exist and was never read, so it cannot be
    in any read set — which is precisely the situation for every file a
    round ADDS. The only recorded evidence that some node would have read it
    is that the node listed the directory. Delete `scans` and this test is
    the one that fails; round 504's two added files are the real instance."""
    mp = _record(mini)
    rows = R.implicated(["data/brand_new.txt"], mp)
    assert rows, "an added file in a scanned directory implicated nothing"
    hit = [r for r in rows if "test_lists_the_directory" in r["key"]]
    assert hit, [r["key"] for r in rows]
    assert hit[0]["hits"][0]["reason"] == "scan"
    # and the read-set-only node is NOT implicated: the two sets are
    # answering different questions and neither subsumes the other.
    assert not [r for r in rows if "test_reads_one_file" in r["key"]]


def test_a_file_added_in_an_unscanned_directory_implicates_nothing(mini):
    """The negative control. Without it, an instrument that implicated
    everything would pass every other test in this file."""
    mp = _record(mini)
    assert R.implicated(["far/brand_new.txt"], mp) == []


def test_by_file_unions_the_keys_of_one_suite_file(mini):
    mp = _record(mini)
    rows = R.implicated(["data/a.txt", "data/brand_new.txt"], mp)
    files = R.by_file(rows)
    mine = [d for d in files if d["file"].endswith("tests/test_mini.py")]
    assert mine and mine[0]["n_keys"] >= 2, files
    assert sorted(mine[0]["reasons"]) == ["read", "scan"]


def test_changed_paths_sees_an_untracked_file(tmp_path):
    """`git status --porcelain`, not `git diff`: the shape this module
    exists for is the ADDED file, and an added file is untracked until
    somebody says `git add`."""
    r = str(tmp_path / "gitrepo")
    os.makedirs(os.path.join(r, "sub"))
    for cmd in (["init", "-q"], ["config", "user.email", "t@t"],
                ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", r] + cmd, check=True,
                       capture_output=True)
    _write(os.path.join(r, "tracked.txt"), "one\n")
    subprocess.run(["git", "-C", r, "add", "-A"], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", r, "commit", "-qm", "x"], check=True,
                   capture_output=True)
    _write(os.path.join(r, "sub", "added.txt"), "new\n")
    _write(os.path.join(r, "tracked.txt"), "two\n")
    got = R.changed_paths(r)
    assert "sub/added.txt" in got and "tracked.txt" in got, got


def test_staleness_names_both_revisions(tmp_path):
    ok, note = R.staleness({"head": R.git_head(REPO_ROOT)}, REPO_ROOT)
    assert ok is False and "which is HEAD" in note
    stale, note = R.staleness({"head": "0" * 40}, REPO_ROOT)
    assert stale is True and "000000000000" in note


# ---------------------------------------------------------- the real subject --

@pytest.fixture(scope="module")
def real_map():
    path = R.DEFAULT_MAP
    assert os.path.exists(path), (
        "harness/readset-map.json is missing — re-record it with\n"
        "    python3 harness/readset.py record")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def test_the_shipped_map_covers_the_harness_fast_tier(real_map):
    assert len(real_map.get("roster", ())) >= MIN_ROSTER, (
        "only %d node(s) rostered — a map recorded from a collapsed run "
        "reports every diff as touching nothing"
        % len(real_map.get("roster", ())))
    assert real_map.get("schema") == 1
    assert real_map.get("head"), "a map with no HEAD cannot be called stale"


def test_a_new_file_in_the_whence_tree_implicates_the_copyparity_node(
        real_map):
    """Round 504's shape, asked with a filename that does not exist.

    Round 504 (language C) added `languages/whence/builtinlive.py` carrying
    an import-time `dirname(dirname(ROOT))` repo-root escape, and reddened
    three nodes of `harness/tests/test_swe_copyparity_real_subject.py` plus
    one of `harness/tests/test_whenceslow.py`. Nothing round 504 could have
    run would have said so: both files live in the harness suite, which a
    language round does not run, and the health check that runs them starts
    after the round's process has exited.

    Asked about a file that does not exist, only the SCAN set can answer —
    which is the whole reason the map records two sets."""
    rows = R.implicated(
        ["languages/whence/no_such_file_round505.py"], real_map)
    files = {d["file"] for d in R.by_file(rows)}
    assert "harness/tests/test_swe_copyparity_real_subject.py" in files, \
        sorted(files)
    assert all(h["reason"] == "scan" for r in rows for h in r["hits"])


def test_a_new_test_in_the_whence_suite_implicates_the_whenceslow_pin(
        real_map):
    """The other half of round 504's redden. `whenceslow.slow_tier_units()`
    lists `languages/whence/tests/` and AST-parses every file in it, so a
    new marked test file moves the pinned totals."""
    rows = R.implicated(
        ["languages/whence/tests/test_no_such_round505.py"], real_map)
    files = {d["file"] for d in R.by_file(rows)}
    assert "harness/tests/test_whenceslow.py" in files, sorted(files)


def test_round_504s_two_real_files_are_in_the_recorded_read_sets(real_map):
    """After the fact, the ADDED files are ordinary read-set members — which
    is exactly why a read set alone is useless to the round that adds them.
    Both directions are pinned so the map cannot be recorded from a tree
    that never saw either file."""
    for path, want in (
            ("languages/whence/builtinlive.py",
             "harness/tests/test_swe_copyparity_real_subject.py"),
            ("languages/whence/tests/test_builtinlive.py",
             "harness/tests/test_whenceslow.py")):
        rows = R.implicated([path], real_map)
        files = {d["file"] for d in R.by_file(rows)}
        assert want in files, (path, sorted(files))
        assert any(h["reason"] == "read"
                   for r in rows for h in r["hits"]), path


def test_the_shipped_map_carries_no_gitignored_path(real_map):
    """A path git ignores can never appear in `git status --porcelain`, so it
    can never match a `blast` query and is dead weight in the map. Pinned so
    a future recording that loses the filter is visible as a red rather than
    as a slowly growing file.

    Asked of GIT, via `readset.gitignored`, not of a path prefix. Round 505
    wrote this as `p.split("/")[0] == "logs"` because `logs/` was 17023 of
    26385 entries and the prose that measured it said "a map that names
    `logs/` is carrying bytes no query can use". That sentence is false, and
    round 506 measured it: `.gitignore` never ignores `logs/` as a whole --
    it lists patterns INSIDE it (`logs/*.json`, `logs/round-*.json`,
    `logs/corpus-evidence/`, ...) -- and 23 files under `logs/` are tracked
    in git right now. So the directory `logs` itself is not ignored, a diff
    CAN name a path under it, and the 25 nodes that scan it hold real
    evidence this assertion was deleting. The shorthand for the measurement
    was pinned instead of the measurement.
    """
    every = set()
    for ent in real_map["nodes"].values():
        every |= set(ent["files"]) | set(ent["scans"])
    bad = R.gitignored(every, REPO_ROOT)
    assert not bad, sorted(bad)[:10]
    assert real_map.get("n_gitignored_dropped", 0) > 0, (
        "no path was dropped at all — the filter did not run")


def test_the_filter_drops_an_ignored_path_and_keeps_a_tracked_sibling():
    """The positive control for the test above, which can only ever say that
    nothing ignored survived — it passes just as well against a filter that
    dropped everything, or against `logs/` being wholly ignored after all.

    Both directions, against the live `.gitignore`: `logs/driver.log` is
    ignored by name, `logs` and a file `git ls-files` reports under it are
    not.
    """
    tracked = subprocess.run(["git", "-C", REPO_ROOT, "ls-files", "logs"],
                             capture_output=True, text=True, timeout=60)
    kept = [l for l in tracked.stdout.splitlines() if l.strip()]
    assert kept, "no tracked file under logs/ — the premise moved"
    probe = ["logs", "logs/driver.log", kept[0]]
    out = R.gitignored(probe, REPO_ROOT)
    assert "logs/driver.log" in out
    assert "logs" not in out, (
        "`logs` itself is ignored now — the map may legitimately drop it")
    assert kept[0] not in out, kept[0]


def test_the_map_does_not_claim_the_harness_suite_reads_nothing(real_map):
    """A guard against the failure that makes every other pin vacuous: a
    recorder that silently dropped everything writes a map full of empty
    sets and `blast` then reports every diff as safe."""
    nodes = real_map.get("nodes", {})
    with_files = [k for k, v in nodes.items() if v.get("files")]
    with_scans = [k for k, v in nodes.items() if v.get("scans")]
    assert len(with_files) >= 50, len(with_files)
    assert len(with_scans) >= 10, len(with_scans)


def test_the_blast_cli_runs_from_the_repo_root_and_names_its_map():
    """The verb, actually invoked. `harness/verb_audit.py` V003 counts an
    entry point that declares verbs none of which is invoked anywhere; this
    runs the real argv from the real root."""
    argv = list(BLAST_ARGV) + ["--json",
                               "languages/whence/no_such_file_round505.py"]
    p = subprocess.run([sys.executable] + argv, cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stdout + p.stderr
    got = json.loads(p.stdout)
    assert "harness/tests/test_swe_copyparity_real_subject.py" in \
        {d["file"] for d in got["files"]}, p.stdout[:2000]
    assert got["paths"] == ["languages/whence/no_such_file_round505.py"]


def test_the_record_verb_runs_end_to_end_on_a_miniature_repo(mini, tmp_path):
    """The fourth verb, invoked for real rather than only by the helper.

    `_record` above drives pytest directly, which exercises the PLUGIN and
    not the CLI. This runs `harness/readset.py record` itself, pointed at a
    tree small enough to be free, and checks that the summary line it prints
    is derived from the map it wrote rather than from a constant."""
    out = str(tmp_path / "cli-map.json")
    argv = list(RECORD_ARGV)                       # ["harness/readset.py", "record"]
    p = subprocess.run([sys.executable, argv[0], "--root", mini, argv[1],
                        "--out", out, "tests"],
                       cwd=REPO_ROOT, capture_output=True,
                       text=True, timeout=300)
    assert p.returncode == 0, p.stdout + p.stderr
    assert os.path.exists(out), p.stdout + p.stderr
    with open(out, encoding="utf-8") as f:
        mp = json.load(f)
    assert "readset record:" in p.stdout
    assert "%d node(s) rostered" % len(mp["roster"]) in p.stdout
    assert "%d key(s) with evidence" % len(mp["nodes"]) in p.stdout
    assert "data/a.txt" in set().union(*[set(v["files"])
                                         for v in mp["nodes"].values()])


def test_the_silent_and_show_verbs_run(real_map):
    for argv in (list(SILENT_ARGV),
                 list(SHOW_ARGV) + ["test_the_real_tree_yields_the_units"]):
        p = subprocess.run([sys.executable] + argv, cwd=REPO_ROOT,
                           capture_output=True, text=True, timeout=180)
        assert p.returncode == 0, (argv, p.stdout + p.stderr)
        assert p.stdout.strip(), argv


def test_blast_strict_is_opt_in_and_the_driver_does_not_use_it():
    """A check must never be able to stop the round that would fix it
    (round 493's rule, stated in `run_driver.sh`'s red-debt block). `blast`
    exits 0 on findings unless `--strict` is asked for, and nothing
    automatic asks."""
    argv = list(BLAST_ARGV) + ["--strict",
                               "languages/whence/no_such_file_round505.py"]
    p = subprocess.run([sys.executable] + argv, cwd=REPO_ROOT,
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 1, p.stdout
    with open(os.path.join(REPO_ROOT, "run_driver.sh"), encoding="utf-8") as f:
        driver = f.read()
    assert "readset.py blast --strict" not in driver
