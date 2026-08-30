"""Measured read-scope of a test process (round 361, harness A).

Why this exists
---------------
`swe/slowtier.py` gates every slow-tier ledger entry on `checkout_digest()`:
one sha over every `.py` file in `languages/whence/`. Rule 2 — an entry whose
digest differs from the current tree is `stale_checkout` — is what keeps a
stale pass from being read as evidence, and it works. What it costs is
recall, and the cost was never measured against the SUBJECT half:

  * 61 commits since 2026-08-26 touch a `languages/whence/**.py` file;
    **32 of them (52%) touch nothing under `whence/` and no `run.py`** — they
    are edits to whence's OWN tests and benches. Every one invalidated all 19
    slow-tier entries at once.
  * The tier costs ~76 minutes on this one-CPU box against a per-round budget
    in the low hundreds of seconds. The ledger holds 16 entries after 20
    rounds, and recall against the current checkout is 0%.

That is the exact arithmetic `slowtier.py`'s own "harness deps" section spells
out — "ANY harness edit invalidates ALL 18 files at once ... the ledger would
never accumulate, which is the module's entire purpose" — and it was applied
to `harness/`, precisely, and never to `languages/whence/`.

Why measured and not inferred
-----------------------------
The harness half could be scanned statically because it is pure `import`
graph. The subject half is not: `swe/killers.py:load_whence` imports the
`whence` package by file location, `swe/guest.py` reads
`examples/self_eval.lang` as SOURCE, `swe/mutation.py:_copy_project`
`copytree`s the whole checkout, and `swe/coverage.py` shells out to a pytest
that reads whatever it likes. A static table over those would be a hand-
maintained list of markers — the same shape of unenforced rule this program
keeps finding rotted (`skills/unenforced-documented-rule/`).

So this module measures instead. `sys.addaudithook` sees every `open` the
process performs; the recorded set of checkout-relative paths IS what that
run depended on, with no table to keep current.

The three fail-closed rules
---------------------------
1. **A subprocess makes the scope unknowable.** `subprocess.Popen`,
   `os.exec*` and `os.posix_spawn` are recorded as `opaque` events, and any
   opaque event means the scope covers the WHOLE checkout. `swe/coverage.py`
   spawns a pytest over the real `WHENCE_ROOT`; that child has no audit hook,
   so its reads are invisible and nothing may be narrowed on their account.
2. **Scope is a set of DIRECTORIES, not of files.** A run that read
   `examples/self_eval.lang` has `examples/` in scope, and every file in
   `examples/` — including one ADDED later — counts as a change. Recording
   individual files would be fail-open against enumeration: round 355's
   `list_example_files` shells `git ls-files`, so a new example changes what
   the corpus contains without any existing file being opened.
3. **No observation is not a narrow observation.** An empty scope with no
   opaque event is legal (a test that never touches the checkout — see
   `test_swe_scoreaudit.py`), but a missing or malformed scope record — the
   hook never installed, the process died before `atexit`, the JSON is torn —
   is `ok: false`, and `slowtier` falls back to the whole-checkout digest,
   i.e. exactly its round-341 behaviour. A scoped claim is never available by
   accident.

A note on `.pyc`
----------------
With a populated `__pycache__`, importing `whence.parser` opens
`whence/__pycache__/parser.cpython-312.pyc` and never opens `whence/parser.py`
(the source is `stat`ed, not read). Recording the raw path would put the scope
in a directory `slowtier` ignores by construction, so `normalize_read` maps a
`__pycache__/X.cpython-NNN.pyc` read back to `X.py` in the parent directory.
The mapping is exact: that is the cache key's own definition.
"""
import hashlib
import json
import os

#: Mirrors `slowtier._IGNORED_DIRS`. Kept as its own tuple rather than
#: imported so this module stays importable inside the bootstrap below, which
#: runs before `swe` is on the path.
IGNORED_DIRS = ("__pycache__", ".pytest_cache", ".venv", "research-env", ".git")

#: Audit events that make the rest of the run's reads invisible to us.
OPAQUE_EVENTS = ("subprocess.Popen", "os.exec", "os.posix_spawn",
                 "os.spawn", "os.fork", "os.forkpty")


def _is_ignored(rel):
    parts = rel.replace(os.sep, "/").split("/")
    return any(p in IGNORED_DIRS or p.endswith(".egg-info") for p in parts)


def normalize_read(rel):
    """Checkout-relative read path -> the SOURCE path it is evidence about.

    `whence/__pycache__/parser.cpython-312.pyc` -> `whence/parser.py`.
    Returns None for a path in an ignored directory that is not a bytecode
    cache of a real source (e.g. anything under `.git/`).
    """
    rel = rel.replace(os.sep, "/")
    parts = rel.split("/")
    if len(parts) >= 2 and parts[-2] == "__pycache__" and parts[-1].endswith(".pyc"):
        stem = parts[-1].split(".")[0]
        cand = "/".join(parts[:-2] + [stem + ".py"])
        return cand if not _is_ignored(cand) else None
    if _is_ignored(rel):
        return None
    return rel


def scope_dirs(reads):
    """The set of checkout-relative directories a read set implies.

    `"."` for a file at the checkout root. Rule 2: the DIRECTORY is the unit,
    so a file added beside one that was read counts as a change.
    """
    out = set()
    for rel in reads:
        norm = normalize_read(rel)
        if norm is None:
            continue
        d = os.path.dirname(norm)
        out.add(d if d else ".")
    return sorted(out)


def dir_digest(root, rel_dir, exts=None):
    """sha256[:16] over every file directly in `<root>/<rel_dir>`.

    Non-recursive by design: `scope_dirs` reports every directory that was
    actually read from, so a subdirectory that matters appears on its own.
    Making this recursive would silently re-couple `whence/` to directories
    nothing in it reads.

    `exts=None` means EVERY file, whatever the extension — the point of a
    directory-granular digest is that `examples/self_eval.lang` and a
    `README` added next to it both count. Callers that want the narrower
    source-only rule pass `exts`.
    """
    full_dir = os.path.join(root, rel_dir) if rel_dir != "." else root
    h = hashlib.sha256()
    try:
        names = sorted(os.listdir(full_dir))
    except (IOError, OSError):
        return "<missing>"
    for n in names:
        full = os.path.join(full_dir, n)
        if not os.path.isfile(full):
            continue
        if exts is not None and not n.endswith(tuple(exts)):
            continue
        rel = n if rel_dir == "." else rel_dir + "/" + n
        if _is_ignored(rel):
            continue
        h.update(n.encode("utf-8"))
        h.update(b"\0")
        try:
            with open(full, "rb") as f:
                h.update(hashlib.sha256(f.read()).digest())
        except (IOError, OSError):
            h.update(b"<unreadable>")
    return h.hexdigest()[:16]


def scope_digests(root, dirs, exts=None):
    return dict((d, dir_digest(root, d, exts)) for d in dirs)


def read_scope_file(path):
    """Load a scope record written by the bootstrap. Fail-closed rule 3.

    Returns a dict with `ok`, `dirs`, `opaque`, `n_reads`. `ok` is False for
    anything that is not a well-formed record: missing file, torn JSON, wrong
    shape. `ok` True with an opaque event is still `ok` — the record is
    trustworthy, it just says the scope is everything.
    """
    empty = {"ok": False, "dirs": [], "opaque": [], "n_reads": 0,
             "why": "missing"}
    if not os.path.exists(path):
        return empty
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (IOError, OSError, ValueError):
        return dict(empty, why="unreadable")
    if not isinstance(raw, dict) or not isinstance(raw.get("reads"), list) \
            or not isinstance(raw.get("opaque"), list):
        return dict(empty, why="malformed")
    reads = [r for r in raw["reads"] if isinstance(r, str)]
    return {"ok": True, "dirs": scope_dirs(reads),
            "opaque": sorted(set(str(o) for o in raw["opaque"])),
            "n_reads": len(reads), "why": ""}


def scope_is_narrowable(scope):
    """True when a scope may be used INSTEAD of the whole-checkout digest.

    Fail-closed rules 1 and 3 in one predicate: the record must be well
    formed, and no opaque event may have occurred.
    """
    return bool(scope.get("ok")) and not scope.get("opaque")


#: Source of the in-process recorder. Kept as a string (not a module the
#: child imports) so the child needs nothing on `sys.path` before the hook is
#: installed — the hook must be live BEFORE pytest's own imports, since those
#: are how `swe.*` and `whence.*` get read in the first place.
#:
#: `%(out)s` is filled with the scope-record path, `%(root)s` with the
#: checkout root, `%(args)r` with pytest's argv.
BOOTSTRAP = r'''
import atexit, json, os, sys
_ROOT = os.path.abspath(%(root)r)
_OUT = %(out)r
_reads = set()
_opaque = []
_OPAQUE = %(opaque)r
def _hook(event, args):
    if event == "open":
        if not args:
            return
        p = args[0]
        try:
            ap = os.fsdecode(p)
        except (TypeError, ValueError, UnicodeDecodeError):
            return
        if not isinstance(ap, str):
            return
        # Prefilter before `abspath`, which calls `getcwd()` on every hit:
        # an ABSOLUTE path outside the root can be rejected on a string
        # compare. Relative paths still pay for the resolution, but a test
        # run's relative opens are a small minority of its total.
        if ap[:1] == os.sep and not ap.startswith(_ROOT + os.sep):
            return
        try:
            ap = os.path.abspath(ap)
        except (ValueError, OSError):
            return
        if ap.startswith(_ROOT + os.sep):
            _reads.add(ap[len(_ROOT) + 1:])
    elif event in _OPAQUE:
        if len(_opaque) < 20:
            _opaque.append(event)
def _dump():
    try:
        tmp = _OUT + ".part"
        with open(tmp, "w") as f:
            json.dump({"reads": sorted(_reads), "opaque": _opaque}, f)
        os.replace(tmp, _OUT)
    except Exception:
        pass
atexit.register(_dump)
sys.addaudithook(_hook)
import pytest
sys.exit(pytest.main(%(args)r))
'''


def bootstrap_source(root, out_path, pytest_args):
    return BOOTSTRAP % {"root": root, "out": out_path,
                        "args": list(pytest_args), "opaque": OPAQUE_EVENTS}
