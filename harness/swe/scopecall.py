"""Is the code a mutation campaign is scoring actually REACHED by anything?
(round 503, SWE-loop D)

The defect this closes
----------------------
`nodecampaign.py` declares its subject scope as three line ranges and a
comment calling them *"the three regions of `nuc/perturbation.py` that carry
published numbers: `classify_bucket`, the hypergeometric/power block, and
`verdict_floor`"*. Round 502 checked one third of that sentence by hand --
`git log --oneline -S "classify_bucket(" -- nuc/perturbation.py` returns
exactly the commit that DEFINED it, and `-S "= classify_bucket"` returns
nothing -- and found that in 108 rounds `classify_bucket` has been called by
its test file and by nothing else.

So a third of the campaign's scope was mutating code no product path runs, and
the campaign reported one POOLED kill rate over all of it. Those mutants are
not measuring the subject. They are measuring the test file's agreement with
itself, which is a strictly easier grading problem, and pooling them
FLATTERS the headline number in the direction that reads as good news.

Round 502 found that with `git log -S` and a paragraph. This module is the
runnable form of the same question, asked of every def in a scope rather than
one, and re-asked every time the campaign runs.

The verdict, and which way it fails
-----------------------------------
For each def the scope covers:

  ``live``          something outside the test tree reaches it (directly, or
                    through another ``live`` def)
  ``test_only``     every reference to it, transitively, comes from a test
                    file -- a mutant here scores the SUITE against itself
  ``unreferenced``  nothing anywhere refers to it but its own definition

An orphan claim is a strong claim -- it says a whole region of a published
scope is dead -- so every ambiguity resolves toward ``live``:

  * a reference is counted whether it is a call ``foo(...)``, a bare load
    (a callback, a decorator, a dispatch-table VALUE), or an identifier
    sitting inside a runtime string (``getattr(m, "foo")``, a subcommand
    name, an ``__all__`` entry);
  * a reference from ANY non-test file counts, whether or not that file is
    imported by anything;
  * name resolution is by NAME, not by binding, so `foo` in an unrelated
    module counts as a reference to this module's `foo`. That
    over-approximates callers, which under-reports orphans.

Two reference kinds are collected and deliberately do NOT confer liveness:
``docstring`` and ``comment``. A docstring cannot call anything; neither can
a comment. Excluding them is not a heuristic, it is the definition -- and it
is load-bearing here, because `nodecampaign.py`'s scope COMMENT is itself the
only non-test mention of `classify_bucket` in this repo. Counting comments
would have let the false claim vouch for itself.

Both are still reported, per def, because "the only thing outside the tests
that mentions this function is a comment asserting it is live" is the finding.

What it is not
--------------
Not a call graph. It answers "could anything outside the tests reach this
name", not "does this specific execution". Round 502's `survivor_impact.py`
answers the dynamic question for one subject by tracing a battery of published
verbs; this answers the static one for any subject, in milliseconds, with no
runnable battery required. Use the cheap one to size the scope and the
expensive one to grade the survivors.
"""

import argparse
import ast
import io
import json
import os
import re
import sys
import time
import tokenize

#: Reference kinds that make a def reachable, strongest first.
LIVE_KINDS = ("call", "name", "string", "dynamic_prefix", "decorator")

#: Decorators that do NOT hand the function object to code this scan cannot
#: see. `@staticmethod`/`@classmethod`/`@property` and friends bind the def
#: as an attribute of its own class and register it nowhere; `@overload` and
#: `@final` are annotations. Everything ELSE receives the function object at
#: definition time and may put it anywhere -- a table, a route map, a plugin
#: registry -- so it counts as a reference. Matched on the last dotted
#: component, so `@x.setter` and `@functools.wraps(f)` are both caught.
#: Round 504: this list is deliberately SHORT. The module's stated bias is
#: that every ambiguity resolves toward `live`, and a decorator whose effect
#: this scanner cannot read is exactly such an ambiguity.
INERT_DECORATORS = frozenset((
    "staticmethod", "classmethod", "property", "abstractmethod",
    "abstractproperty", "cached_property", "override", "overload",
    "final", "setter", "getter", "deleter", "wraps", "dataclass",
    "total_ordering", "runtime_checkable",
))
#: A constructed name shorter than this is not evidence of anything -- a
#: prefix of `"_"` would vouch for every private def in the tree.
MIN_DYNAMIC_PREFIX = 3
#: Collected, reported, and never counted as reachability. See module docstring.
INERT_KINDS = ("docstring", "comment")

VERDICT_LIVE = "live"
VERDICT_TEST_ONLY = "test_only"
VERDICT_UNREFERENCED = "unreferenced"


class ScopeError(ValueError):
    """Raised rather than returning an empty result. A gate that passes on an
    input it never read is worse than one that fails (round 490's rule)."""


# --------------------------------------------------------------------- defs

class Def(object):
    """One def/class, with the line span a mutant is attributed to."""

    __slots__ = ("qualname", "name", "kind", "lineno", "end_lineno",
                 "body_lineno")

    def __init__(self, qualname, name, kind, lineno, end_lineno, body_lineno):
        self.qualname = qualname
        self.name = name
        self.kind = kind
        self.lineno = lineno            # includes decorators
        self.end_lineno = end_lineno
        self.body_lineno = body_lineno  # the `def`/`class` keyword line

    def covers(self, lineno):
        return self.lineno <= lineno <= self.end_lineno

    def as_dict(self):
        return {"qualname": self.qualname, "name": self.name,
                "kind": self.kind, "first_line": self.lineno,
                "last_line": self.end_lineno, "def_line": self.body_lineno}

    def __repr__(self):                                   # pragma: no cover
        return "Def(%s, %d-%d)" % (self.qualname, self.lineno, self.end_lineno)


def defs_in(source, filename="<file>"):
    """Every def/class in `source`, outermost first, then by line.

    The span STARTS at the first decorator, not at the `def`: a decorator is a
    mutation site one line above the keyword, and attributing it to module
    level would put the wrong name on the finding. (Same rule as round 502's
    `survivor_impact.enclosing_defs`, which this deliberately mirrors.)
    """
    tree = ast.parse(source, filename=filename)
    out = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                qual = prefix + child.name
                lo = min([child.lineno]
                         + [d.lineno for d in child.decorator_list])
                kind = "class" if isinstance(child, ast.ClassDef) else "def"
                out.append(Def(qual, child.name, kind, lo, child.end_lineno,
                               child.lineno))
                walk(child, qual + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return sorted(out, key=lambda d: (d.lineno, d.qualname))


def innermost(defs, lineno):
    """The narrowest def covering `lineno`, or None for module level."""
    best = None
    for d in defs:
        if d.covers(lineno):
            if best is None or (d.end_lineno - d.lineno) < (best.end_lineno
                                                            - best.lineno):
                best = d
    return best


# --------------------------------------------------------- reference scanner

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


_PREFIX_MARK = "\x00prefix\x00"
_IDENT_FRAGMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _prefix_of(text):
    """The identifier-shaped head of a format/concat template, or None.

    `"_stmt_"` -> `_stmt_`; `"cmd_%s"` -> `cmd_`; `"do_{}"` -> `do_`;
    `"%s_tail"` -> None (nothing is known about the head).
    """
    if not isinstance(text, str):
        return None
    head = text.split("%")[0].split("{")[0]
    if len(head) < MIN_DYNAMIC_PREFIX or not _IDENT_FRAGMENT.match(head):
        return None
    return head


def _dynamic_prefixes(tree):
    """`[(prefix, lineno)]` for every string literal this module builds a name
    out of."""
    out = []

    def add(value, node):
        pref = _prefix_of(value)
        if pref:
            out.append((pref, node.lineno))

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
            if isinstance(node.left, ast.Constant):
                add(node.left.value, node)
        elif isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant):
                    add(part.value, node)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == "format" \
                and isinstance(node.func.value, ast.Constant):
            add(node.func.value.value, node)
    return out


def _docstring_nodes(tree):
    """Line numbers of every string that is a module/def/class DOCSTRING."""
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef,
                                 ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            for ln in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                out.add(ln)
    return out


def scan_references(source, filename="<file>"):
    """`[(name, lineno, kind)]` for every identifier `source` refers to.

    `kind` is one of `call`, `name`, `string`, `docstring`, `comment` --
    see the module docstring for which of those confer reachability and why
    the last two do not.
    """
    tree = ast.parse(source, filename=filename)
    docstring_lines = _docstring_nodes(tree)
    called = set()          # id(node) of every func expression in a Call
    refs = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called.add(id(node.func))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs.append((node.id, node.lineno,
                         "call" if id(node) in called else "name"))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            refs.append((node.attr, node.lineno,
                         "call" if id(node) in called else "name"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            kind = ("docstring" if node.lineno in docstring_lines else "string")
            base = node.lineno
            for i, line in enumerate(node.value.splitlines() or [""]):
                for m in _IDENT.finditer(line):
                    refs.append((m.group(0), base + i, kind))

    # CONSTRUCTED NAMES. `getattr(self, "_stmt_" + kind)(depth)` is a call to
    # every `_stmt_*` method in the class and a name scan sees none of them.
    # The first sweep of `harness/swe/` reported 119 orphans in
    # `alias_effects.py` for exactly this reason, and every one was false --
    # found because they arrived as a same-prefix FAMILY, which is the
    # signature of a dispatch and not of dead code.
    #
    # So: any string literal that is concatenated, %-formatted, `.format`ed or
    # f-string-interpolated is taken as a NAME PREFIX, and every def whose
    # name starts with it counts as referenced. This can only add liveness,
    # never remove it, which is the direction an orphan claim has to fail in.
    for pref, lineno in _dynamic_prefixes(tree):
        refs.append((_PREFIX_MARK + pref, lineno, "dynamic_prefix"))

    # DECORATED DEFS. A decorator RECEIVES the function object at definition
    # time; the def's own name need never be spelled again. Round 503's
    # whole-repo sweep called all 37 of `languages/whence/whence/interp.py`'s
    # builtins not-live -- the entire builtin surface of the language, the
    # implementation of `print` among them -- because every one is
    # `@register("print", 1, "v") def b_print(...)` and `register`'s `wrap`
    # closure appends it to a table under the WHENCE name. The verdict was a
    # true statement about the identifier and a false statement about the
    # code.
    #
    # Like `dynamic_prefix` this can only ADD liveness, which is the
    # direction an orphan claim has to fail in. It is attributed to the
    # ENCLOSING scope, not to the decorated def -- see `_owner_of_line`'s
    # `skip_qual` -- because the decorator expression is evaluated and
    # applied by whatever encloses the `def`, so a builtin registered inside
    # a factory is live exactly when the factory is.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        for dec in node.decorator_list:
            if _decorator_tail(dec) in INERT_DECORATORS:
                continue
            refs.append((node.name, dec.lineno, "decorator"))
            break

    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                for m in _IDENT.finditer(tok.string):
                    refs.append((m.group(0), tok.start[0], "comment"))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # A file `ast.parse` accepted but `tokenize` choked on. Comments are
        # report-only, so losing them cannot change a verdict -- but say so.
        refs.append(("<tokenize-failed>", 0, "comment"))

    return refs


# ------------------------------------------------------------- file walking

def _decorator_tail(dec):
    """The last dotted component of a decorator expression, or `""`.

    `@register("x")` -> `register`; `@prop.setter` -> `setter`;
    `@functools.wraps(f)` -> `wraps`; anything stranger -> `""`, which is
    in no allowlist and therefore counts as a live reference.
    """
    node = dec.func if isinstance(dec, ast.Call) else dec
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def is_test_file(rel):
    """True for the test tree. Basename `test_*.py` / `conftest.py`, or any
    path with a `tests` component -- the three shapes this repo actually
    uses."""
    rel = rel.replace(os.sep, "/")
    base = rel.rsplit("/", 1)[-1]
    if base.startswith("test_") or base == "conftest.py":
        return True
    return "tests" in rel.split("/")[:-1]


DEFAULT_SKIP_DIRS = (".git", ".venv", "__pycache__", "node_modules",
                     ".mypy_cache", ".pytest_cache", "venv", "site-packages")


def python_files(root, subdirs=None, skip_dirs=DEFAULT_SKIP_DIRS):
    """Repo-relative paths of every `.py` under `root` (or under each of
    `subdirs`), skipping the usual noise."""
    out = []
    bases = [os.path.join(root, s) for s in (subdirs or ["."])]
    for base in bases:
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if fn.endswith(".py"):
                    full = os.path.join(dirpath, fn)
                    out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(set(out))


def reference_index(root, rel_paths):
    """`{name: {rel: {kind: [lineno, ...]}}}` over `rel_paths`.

    Unparseable files are counted, not skipped silently -- the count rides in
    the report so a scope audit can never quietly be an audit of half a tree.
    """
    index, unparseable = {}, []
    for rel in rel_paths:
        full = os.path.join(root, rel)
        try:
            with open(full, encoding="utf-8") as fh:
                src = fh.read()
            refs = scan_references(src, rel)
        except (SyntaxError, ValueError, UnicodeDecodeError) as exc:
            unparseable.append({"path": rel, "error": type(exc).__name__})
            continue
        for name, lineno, kind in refs:
            index.setdefault(name, {}).setdefault(rel, {}) \
                 .setdefault(kind, []).append(lineno)
    return index, unparseable


# ---------------------------------------------------------------- the audit

def _skip(rec, d):
    """The def a reference must not be attributed to itself. Only a
    decorator has one -- see `_owner_of_line`."""
    return d.qualname if rec["kind"] == "decorator" else None


def _evidence_for(index, rel_subject, d, defs):
    """Split every reference to `d.name` into the four buckets that decide the
    verdict, dropping references that lie inside `d`'s OWN span (a recursive
    call does not make a function live) and references from a def NESTED in
    it."""
    ev = {"nontest": [], "test": [], "inert": [], "self": []}
    hits = dict((rel, dict(by_kind))
                for rel, by_kind in (index.get(d.name) or {}).items())
    for key, per_file in index.items():
        if not key.startswith(_PREFIX_MARK):
            continue
        if not d.name.startswith(key[len(_PREFIX_MARK):]):
            continue
        for rel, by_kind in per_file.items():
            for kind, lines in by_kind.items():
                hits.setdefault(rel, {}).setdefault(kind, [])
                hits[rel][kind] = list(hits[rel][kind]) + list(lines)
    for rel, by_kind in hits.items():
        for kind, lines in by_kind.items():
            for ln in lines:
                rec = {"path": rel, "line": ln, "kind": kind}
                # A decorator is never a self-reference. `defs_in` starts a
                # def's span AT its first decorator (so a mutation there is
                # attributed to the right name), which would otherwise make
                # every `@register`-style registration invisible -- filed
                # under `self` and dropped, exactly like a recursive call.
                if kind == "decorator" and rel == rel_subject \
                        and d.covers(ln):
                    ev["nontest" if not is_test_file(rel) else "test"] \
                        .append(rec)
                elif rel == rel_subject and d.covers(ln):
                    ev["self"].append(rec)
                elif kind in INERT_KINDS:
                    ev["inert"].append(rec)
                elif is_test_file(rel):
                    ev["test"].append(rec)
                else:
                    ev["nontest"].append(rec)
    for k in ev:
        ev[k].sort(key=lambda r: (r["path"], r["line"], r["kind"]))
    return ev


def _owner_of_line(defs, rel, rel_subject, lineno, skip_qual=None):
    """Qualname of the subject def a reference sits inside, or None.

    `skip_qual` (round 504) excludes one def from the search, and exists for
    exactly one caller: a DECORATOR sits inside the span of the def it
    decorates, but it is evaluated and applied by the ENCLOSING scope. So
    `@register(...) def b_print` is owned by `_make_builtin_table`, and
    `b_print` is live exactly when the factory that registers it is --
    which is the true statement. Without this, a decorated def would be
    seeded live by a reference owned by itself, which is the same mistake
    as counting a recursive call.
    """
    if rel != rel_subject:
        return None
    cands = [x for x in defs if x.qualname != skip_qual] \
        if skip_qual else defs
    d = innermost(cands, lineno)
    return d.qualname if d else None


def audit(root, rel, line_ranges=None, search_paths=None, subdirs=None,
          prebuilt=None):
    """Verdict every def in `rel` (optionally, only those a scope covers).

    Returns the report dict `audit_lines` prints. `line_ranges` is
    `[(lo, hi)]` in the same form `nodecampaign.parse_ranges` produces.
    `prebuilt` is `(index, unparseable, search_paths)` from a previous
    `reference_index` -- the whole cost of this module is the one tree walk,
    so `sweep` builds it once and hands it to every subject.
    """
    full = os.path.join(root, rel)
    if not os.path.isfile(full):
        raise ScopeError("subject does not exist: %s" % full)
    with open(full, encoding="utf-8") as fh:
        src = fh.read()
    defs = defs_in(src, rel)
    if not defs:
        raise ScopeError("subject has no def/class to verdict: %s" % rel)

    if prebuilt is not None:
        index, unparseable, search_paths = prebuilt
        if rel not in search_paths:
            raise ScopeError(
                "subject %s is outside the prebuilt reference index -- its "
                "own internal callers would be invisible and every def would "
                "verdict as unreferenced" % rel)
    else:
        if search_paths is None:
            search_paths = python_files(root, subdirs=subdirs)
        if rel not in search_paths:
            search_paths = sorted(set(list(search_paths) + [rel]))
        index, unparseable = reference_index(root, search_paths)

    # Pass 1: direct evidence per def.
    ev = dict((d.qualname, _evidence_for(index, rel, d, defs)) for d in defs)

    # Pass 2: propagate liveness INSIDE the subject. A def referenced only
    # from another def of this module is live exactly when that other def is.
    # Module-level code in the subject is always a root: it runs on import.
    by_qual = dict((d.qualname, d) for d in defs)
    live = set()
    seeded_by = {}
    for d in defs:
        for rec in ev[d.qualname]["nontest"]:
            owner = _owner_of_line(defs, rec["path"], rel, rec["line"],
                                   _skip(rec, d))
            if rec["path"] != rel or owner is None:
                live.add(d.qualname)
                seeded_by.setdefault(d.qualname, rec)
                break

    changed = True
    while changed:
        changed = False
        for d in defs:
            if d.qualname in live:
                continue
            for rec in ev[d.qualname]["nontest"] + ev[d.qualname]["test"]:
                if rec["path"] != rel:
                    continue
                owner = _owner_of_line(defs, rec["path"], rel, rec["line"],
                                       _skip(rec, d))
                if owner is None:
                    continue
                # a reference from inside a live def, or from inside a live
                # def's nested scope, makes this one live too
                chain = [owner]
                while "." in chain[-1]:
                    chain.append(chain[-1].rsplit(".", 1)[0])
                if any(c in live for c in chain):
                    live.add(d.qualname)
                    seeded_by.setdefault(d.qualname, rec)
                    changed = True
                    break
    # A method is reachable if its class is: the class's own liveness is what
    # a `C().method()` call site through a variable looks like to a name scan.
    changed = True
    while changed:
        changed = False
        for d in defs:
            if d.qualname in live or "." not in d.qualname:
                continue
            parent = d.qualname.rsplit(".", 1)[0]
            if parent in live and by_qual.get(parent) is not None \
                    and by_qual[parent].kind == "class":
                live.add(d.qualname)
                seeded_by.setdefault(d.qualname,
                                     {"path": rel, "line": by_qual[parent].lineno,
                                      "kind": "enclosing-class-is-live"})
                changed = True

    rows = []
    for d in defs:
        e = ev[d.qualname]
        if d.qualname in live:
            verdict = VERDICT_LIVE
        elif e["test"]:
            verdict = VERDICT_TEST_ONLY
        elif e["nontest"]:
            # non-test references exist but all of them sit inside defs that
            # are themselves not live -- dead code with a dead caller
            verdict = VERDICT_TEST_ONLY
        elif e["inert"]:
            verdict = VERDICT_UNREFERENCED
        else:
            verdict = VERDICT_UNREFERENCED
        row = dict(d.as_dict())
        row["verdict"] = verdict
        # `test_only` arrives two ways and they read differently in a report:
        # DIRECT means a test file names it; TRANSITIVE means only other
        # not-live defs of this module do, i.e. it is inside a cluster whose
        # only entry point is a test. `sadc_reclaim_literals` is transitive --
        # zero test references, two callers, both of them test_only.
        row["test_only_kind"] = (
            None if verdict != VERDICT_TEST_ONLY
            else ("direct" if e["test"] else "transitive"))
        row["in_scope"] = _in_scope(d, line_ranges)
        row["n_nontest_refs"] = len(e["nontest"])
        row["n_test_refs"] = len(e["test"])
        row["n_inert_refs"] = len(e["inert"])
        row["nontest_kinds"] = sorted(set(r["kind"] for r in e["nontest"]))
        row["inert_kinds"] = sorted(set(r["kind"] for r in e["inert"]))
        row["inert_only_mentions"] = (
            [r for r in e["inert"]] if verdict != VERDICT_LIVE else [])
        row["live_because"] = seeded_by.get(d.qualname)
        # D5's question: would this def still be live without the STRING rule?
        row["live_only_via_string"] = bool(
            verdict == VERDICT_LIVE
            and row["nontest_kinds"] == ["string"])
        # The two conservative rules, each measured rather than asserted: a
        # def live ONLY because of one of them would flip to test_only if that
        # rule were dropped.
        row["live_only_via_dynamic_prefix"] = bool(
            verdict == VERDICT_LIVE
            and row["nontest_kinds"] == ["dynamic_prefix"])
        rows.append(row)

    scoped = [r for r in rows if r["in_scope"]]
    rep = {
        "root": os.path.abspath(root),
        "subject": rel,
        "line_ranges": [list(t) for t in (line_ranges or [])],
        "n_defs": len(rows),
        "n_scoped_defs": len(scoped),
        "n_search_paths": len(search_paths),
        "n_unparseable": len(unparseable),
        "unparseable": unparseable,
        "defs": rows,
        "counts": _counts(rows),
        "scoped_counts": _counts(scoped),
        "scoped_not_live": sorted(r["qualname"] for r in scoped
                                  if r["verdict"] != VERDICT_LIVE),
        "live_only_via_string": sorted(r["qualname"] for r in rows
                                       if r["live_only_via_string"]),
        "live_only_via_dynamic_prefix": sorted(
            r["qualname"] for r in rows if r["live_only_via_dynamic_prefix"]),
    }
    return rep


def _in_scope(d, line_ranges):
    if not line_ranges:
        return True
    return any(not (d.end_lineno < lo or d.lineno > hi)
               for lo, hi in line_ranges)


def _counts(rows):
    out = {VERDICT_LIVE: 0, VERDICT_TEST_ONLY: 0, VERDICT_UNREFERENCED: 0}
    for r in rows:
        out[r["verdict"]] = out.get(r["verdict"], 0) + 1
    return out


# --------------------------------------------------------------- the strata

def stratify(report, ledger_rows, subject_digest=None):
    """Split a mutation ledger by the scope verdict of the def each mutant
    lands in, and give a kill rate PER STRATUM.

    This is the point of the module. One pooled kill rate over a scope whose
    regions differ in whether anything outside the tests runs them is not a
    measurement of the suite: the `test_only` stratum is graded by tests
    written directly against it and nothing else, so it drags the headline up
    for a reason that has nothing to do with the product.

    `ledger_rows` is the LAST-WINS view -- `{(id, digest): row}.values()` --
    not the raw file. A re-score is an append (round 502), so counting rows
    counts verdicts the campaign no longer holds.
    """
    defs = report["defs"]
    strata = {}
    unattributed = []
    for row in ledger_rows:
        if subject_digest is not None \
                and row.get("subject_digest") != subject_digest:
            continue
        line = row.get("line")
        owner, verdict = None, None
        best = None
        if not isinstance(line, int):
            # A ledger row with no `line` -- hand-written rows and rows from
            # before the field existed. It gets its own stratum rather than a
            # crash OR a silent drop: dropping it would shrink a published
            # denominator without saying so.
            s = strata.setdefault("no_line", {"n": 0, "killed": 0,
                                              "survived": 0, "other": 0,
                                              "owners": {}})
            s["n"] += 1
            st = row.get("status")
            s["killed" if st == "killed" else
              "survived" if st == "survived" else "other"] += 1
            s["owners"]["<no-line>"] = s["owners"].get("<no-line>", 0) + 1
            unattributed.append(row.get("id"))
            continue
        for d in defs:
            if d["first_line"] <= line <= d["last_line"]:
                width = d["last_line"] - d["first_line"]
                if best is None or width < best[0]:
                    best = (width, d)
        if best is not None:
            owner, verdict = best[1]["qualname"], best[1]["verdict"]
        else:
            verdict = "module_level"
            unattributed.append(row.get("id"))
        s = strata.setdefault(verdict, {"n": 0, "killed": 0, "survived": 0,
                                        "other": 0, "owners": {}})
        s["n"] += 1
        st = row.get("status")
        if st == "killed":
            s["killed"] += 1
        elif st == "survived":
            s["survived"] += 1
        else:
            s["other"] += 1
        s["owners"][owner or "<module>"] = s["owners"].get(owner or "<module>", 0) + 1

    for s in strata.values():
        graded = s["killed"] + s["survived"]
        s["graded"] = graded
        s["kill_rate"] = round(s["killed"] / graded, 4) if graded else None
        s["owners"] = dict(sorted(s["owners"].items()))

    tot_k = sum(s["killed"] for s in strata.values())
    tot_g = sum(s["graded"] for s in strata.values())
    live = strata.get(VERDICT_LIVE, {})
    live_k, live_g = live.get("killed", 0), live.get("graded", 0)
    return {
        "strata": dict(sorted(strata.items())),
        "pooled": {"killed": tot_k, "graded": tot_g,
                   "kill_rate": round(tot_k / tot_g, 4) if tot_g else None},
        "live_only": {"killed": live_k, "graded": live_g,
                      "kill_rate": round(live_k / live_g, 4) if live_g else None},
        "pooled_minus_live_pp": (
            round(100.0 * (tot_k / tot_g - live_k / live_g), 2)
            if tot_g and live_g else None),
        "mutants_not_inside_any_def": sorted(x for x in unattributed if x),
    }


def sweep(root, rels, subdirs=None, search_paths=None):
    """Audit many subjects against ONE reference index.

    Every non-test `.py` in the tree is a potential caller of every other, so
    the index is global and building it per subject would be the entire cost
    N times over. Returns `{"subjects": [report, ...], "totals": {...}}`.

    Test files are audited too when they are named -- a `test_only` verdict on
    a def INSIDE a test file just means a helper only its own tests use, which
    is the normal and correct state for a fixture.
    """
    if search_paths is None:
        search_paths = python_files(root, subdirs=subdirs)
    missing = [r for r in rels if r not in search_paths]
    search_paths = sorted(set(list(search_paths) + list(rels)))
    index, unparseable = reference_index(root, search_paths)
    prebuilt = (index, unparseable, search_paths)

    reports, failed = [], []
    for rel in rels:
        try:
            reports.append(audit(root, rel, prebuilt=prebuilt))
        except (ScopeError, SyntaxError) as exc:
            failed.append({"path": rel, "error": "%s: %s"
                           % (type(exc).__name__, exc)})
    totals = {VERDICT_LIVE: 0, VERDICT_TEST_ONLY: 0, VERDICT_UNREFERENCED: 0}
    for rep in reports:
        for k, v in rep["counts"].items():
            totals[k] = totals.get(k, 0) + v
    return {
        "root": os.path.abspath(root),
        "n_subjects": len(reports),
        "n_subjects_failed": len(failed),
        "failed": failed,
        "subjects_outside_search_scope": sorted(missing),
        "n_search_paths": len(search_paths),
        "n_unparseable": len(unparseable),
        "unparseable": unparseable,
        "totals": totals,
        "not_live": sorted(
            [{"path": rep["subject"], "qualname": r["qualname"],
              "verdict": r["verdict"], "kind": r["test_only_kind"],
              "first_line": r["first_line"], "last_line": r["last_line"],
              "n_test_refs": r["n_test_refs"]}
             for rep in reports for r in rep["defs"]
             if r["verdict"] != VERDICT_LIVE],
            key=lambda x: (x["path"], x["first_line"])),
        "subjects": reports,
    }


def sweep_lines(sw):
    out = ["scope-sweep: %d subject(s) (%d unauditable), %d file(s) searched;"
           " %d live, %d test_only, %d unreferenced"
           % (sw["n_subjects"], sw["n_subjects_failed"], sw["n_search_paths"],
              sw["totals"].get(VERDICT_LIVE, 0),
              sw["totals"].get(VERDICT_TEST_ONLY, 0),
              sw["totals"].get(VERDICT_UNREFERENCED, 0))]
    for r in sw["not_live"]:
        out.append("  %-13s %-11s %s::%s (lines %d-%d, %d test ref(s))"
                   % (r["verdict"], r["kind"] or "-", r["path"], r["qualname"],
                      r["first_line"], r["last_line"], r["n_test_refs"]))
    for f in sw["failed"]:
        out.append("  UNAUDITABLE   %s -- %s" % (f["path"], f["error"]))
    return out


# ------------------------------------------------------------------ reports

def audit_lines(rep):
    """Human-readable, one line per not-live def plus a summary."""
    out = []
    sc = rep["scoped_counts"]
    out.append("scope-audit: %s -- %d def(s), %d in scope (%s live, %s "
               "test_only, %s unreferenced); %d file(s) searched, %d "
               "unparseable"
               % (rep["subject"], rep["n_defs"], rep["n_scoped_defs"],
                  sc.get(VERDICT_LIVE, 0), sc.get(VERDICT_TEST_ONLY, 0),
                  sc.get(VERDICT_UNREFERENCED, 0), rep["n_search_paths"],
                  rep["n_unparseable"]))
    for r in rep["defs"]:
        if not r["in_scope"] or r["verdict"] == VERDICT_LIVE:
            continue
        mention = ""
        if r["inert_only_mentions"]:
            m = r["inert_only_mentions"][0]
            mention = ("; mentioned only in a %s at %s:%d"
                       % (m["kind"], m["path"], m["line"]))
        out.append("  %-10s %-11s %s (lines %d-%d, %d test ref(s))%s"
                   % (r["verdict"], r["test_only_kind"] or "-", r["qualname"],
                      r["first_line"], r["last_line"], r["n_test_refs"],
                      mention))
    return out


def strata_lines(st):
    out = []
    p, l = st["pooled"], st["live_only"]
    out.append("strata: pooled kill rate %s (%d/%d); live-only %s (%d/%d); "
               "pooling adds %s pp"
               % (p["kill_rate"], p["killed"], p["graded"],
                  l["kill_rate"], l["killed"], l["graded"],
                  st["pooled_minus_live_pp"]))
    for name, s in st["strata"].items():
        out.append("  %-14s n=%-4d killed=%-4d survived=%-4d kill_rate=%s"
                   % (name, s["n"], s["killed"], s["survived"], s["kill_rate"]))
    return out


# ------------------------------------------------- the registry cross-check

#: Files a shell script or a CI config can invoke, which no `.py` scan sees.
NONPY_CALLER_SUFFIXES = (".sh", ".yml", ".yaml", ".toml", ".cfg", ".mk")
NONPY_CALLER_NAMES = ("Makefile",)


def nonpy_callers(root, skip_dirs=DEFAULT_SKIP_DIRS):
    """`{rel: text}` for every file that can invoke a script without importing
    it. `run_driver.sh` is how a third of this repo's entry points are reached;
    a Python-only scan would call every one of them an orphan."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fn in filenames:
            if not (fn.endswith(NONPY_CALLER_SUFFIXES) or fn in NONPY_CALLER_NAMES):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            try:
                with open(full, encoding="utf-8", errors="replace") as fh:
                    out[rel] = fh.read()
            except OSError:
                continue
    return out


def registry_audit(root, registry_path="harness/wiring-registry.json"):
    """Cross-check `harness/wiring-registry.json` against reachability.

    The registry's own question is "is this file reached at all", and a test
    file counts. That is a defensible answer to that question and a MISLEADING
    one to the question the word `wired` gets read as, which is "something
    other than its own tests runs this".

    The verdict this reports is deliberately NOT called `dead`. A round that
    ran a CLI inline -- `python3 -m swe.nodecampaign --stale ...` -- is a real
    caller that left no committed trace, and several entries here are exactly
    that. `no_committed_caller` is the claim the evidence supports: nothing in
    the repository invokes it except its own tests, so nobody can re-run it
    from the record without a human remembering the command.
    """
    full_reg = (registry_path if os.path.isabs(registry_path)
                else os.path.join(root, registry_path))
    if not os.path.isfile(full_reg):
        raise ScopeError("no wiring registry at %s" % full_reg)
    with open(full_reg, encoding="utf-8") as fh:
        reg = json.load(fh)
    eps = reg.get("entry_points")
    if not isinstance(eps, dict) or not eps:
        raise ScopeError("registry has no `entry_points` to check: %s" % full_reg)

    paths = python_files(root)
    index, unparseable = reference_index(root, paths)
    shell = nonpy_callers(root)

    rows, missing = [], []
    for rel in sorted(eps):
        meta = eps[rel] or {}
        if not rel.endswith(".py") or not os.path.isfile(os.path.join(root, rel)):
            missing.append(rel)
            continue
        via = str(meta.get("via") or "")
        via_path = via.split(":")[0]
        mod = os.path.basename(rel)[:-3]
        base = os.path.basename(rel)
        py_callers = sorted(
            p for p, by_kind in (index.get(mod) or {}).items()
            if p != rel and not is_test_file(p)
            and any(k in LIVE_KINDS for k in by_kind))
        sh_callers = sorted(p for p, text in shell.items()
                            if rel in text or base in text)
        if py_callers or sh_callers:
            verdict = "has_committed_caller"
        else:
            verdict = "no_committed_caller"
        rows.append({
            "path": rel,
            "registry_status": meta.get("status"),
            "registry_via": via or None,
            "via_is_a_test_file": bool(via_path) and is_test_file(via_path),
            "verdict": verdict,
            "py_callers": py_callers,
            "nonpy_callers": sh_callers,
        })

    flagged = [r for r in rows
               if r["registry_status"] == "wired"
               and r["via_is_a_test_file"]
               and r["verdict"] == "no_committed_caller"]
    return {
        "root": os.path.abspath(root),
        "registry": registry_path,
        "n_entries": len(eps),
        "n_checked": len(rows),
        "n_entries_not_an_existing_py_file": len(missing),
        "entries_not_an_existing_py_file": missing,
        "n_wired": sum(1 for r in rows if r["registry_status"] == "wired"),
        "n_wired_via_a_test_file": sum(
            1 for r in rows
            if r["registry_status"] == "wired" and r["via_is_a_test_file"]),
        "n_no_committed_caller": sum(
            1 for r in rows if r["verdict"] == "no_committed_caller"),
        "declared_wired_by_their_own_tests": [r["path"] for r in flagged],
        "n_unparseable": len(unparseable),
        "rows": rows,
    }


def registry_lines(ra):
    out = ["registry-audit: %d entry(s), %d checked (%d not an existing .py); "
           "%d wired, %d of those via a TEST file; %d with no committed caller"
           % (ra["n_entries"], ra["n_checked"],
              ra["n_entries_not_an_existing_py_file"], ra["n_wired"],
              ra["n_wired_via_a_test_file"], ra["n_no_committed_caller"])]
    out.append("  declared `wired` by their own tests and nothing else: %d"
               % len(ra["declared_wired_by_their_own_tests"]))
    for p in ra["declared_wired_by_their_own_tests"]:
        row = next(r for r in ra["rows"] if r["path"] == p)
        out.append("    %-52s <- %s" % (p, row["registry_via"]))
    return out


# ---------------------------------------------------------------------- CLI

def _parse_ranges(text):
    if not text:
        return None
    out = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            out.append((int(lo), int(hi)))
        else:
            out.append((int(part), int(part)))
    return out or None


def _load_ledger(path):
    """Last-wins, keyed `(id, subject_digest)` -- the same rule
    `nodecampaign.load_ledger` uses, restated here so this module can be run
    without importing the campaign."""
    out = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            out[(r["id"], r.get("subject_digest"))] = r
    return out


def build_parser():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="verdict every def in a subject")
    a.add_argument("--root", default=".")
    a.add_argument("--rel", required=True, help="subject, repo-relative")
    a.add_argument("--ranges", default=None,
                   help="campaign scope, e.g. 556-634,1573-1662")
    a.add_argument("--search", default=None,
                   help="comma-separated subdirs to search for references "
                        "(default: the whole root)")
    a.add_argument("--json", default=None, help="write the full report here")
    a.add_argument("--strict", action="store_true",
                   help="exit 1 if any def IN SCOPE is not live")

    w = sub.add_parser("sweep", help="audit many subjects on one index")
    w.add_argument("--root", default=".")
    w.add_argument("--rels", default=None,
                   help="comma-separated subjects; default: every non-test "
                        "`.py` under --in")
    w.add_argument("--in", dest="in_dirs", default=None,
                   help="comma-separated subdirs to take subjects from")
    w.add_argument("--search", default=None,
                   help="comma-separated subdirs to search for references "
                        "(default: the whole root -- narrowing this can only "
                        "INVENT orphans, so it is reported in the artefact)")
    w.add_argument("--json", default=None)
    w.add_argument("--strict", action="store_true",
                   help="exit 1 if any audited def is not live")

    g = sub.add_parser("registry",
                       help="cross-check the wiring registry against "
                            "reachability")
    g.add_argument("--root", default=".")
    g.add_argument("--registry", default="harness/wiring-registry.json")
    g.add_argument("--json", default=None)
    g.add_argument("--strict", action="store_true",
                   help="exit 1 if any entry is declared `wired` by nothing "
                        "but its own test file")

    s = sub.add_parser("strata", help="kill rate per scope verdict")
    s.add_argument("--root", default=".")
    s.add_argument("--rel", required=True)
    s.add_argument("--ledger", required=True)
    s.add_argument("--ranges", default=None)
    s.add_argument("--search", default=None)
    s.add_argument("--subject-digest", default=None,
                   help="score only rows taken against this subject digest")
    s.add_argument("--json", default=None)
    s.add_argument("--strict", action="store_true",
                   help="exit 1 if any graded mutant is outside the live "
                        "stratum -- i.e. if the pooled rate is not the "
                        "live rate")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    t0 = time.time()
    search = getattr(a, "search", None)
    subdirs = [x.strip() for x in search.split(",")] if search else None

    if a.cmd == "sweep":
        if a.rels:
            rels = [x.strip() for x in a.rels.split(",") if x.strip()]
        else:
            in_dirs = ([x.strip() for x in a.in_dirs.split(",")]
                       if a.in_dirs else None)
            rels = [r for r in python_files(a.root, subdirs=in_dirs)
                    if not is_test_file(r)]
        if not rels:
            raise ScopeError("sweep selected no subject -- refusing to report "
                             "a clean sweep of nothing")
        sw = sweep(a.root, rels, subdirs=subdirs)
        sw["wall_seconds"] = round(time.time() - t0, 2)
        for line in sweep_lines(sw):
            print(line)
        if a.json:
            _write(a.json, sw)
        return 1 if (a.strict and sw["not_live"]) else 0

    if a.cmd == "registry":
        ra = registry_audit(a.root, a.registry)
        ra["wall_seconds"] = round(time.time() - t0, 2)
        for line in registry_lines(ra):
            print(line)
        if a.json:
            _write(a.json, ra)
        return 1 if (a.strict and ra["declared_wired_by_their_own_tests"]) else 0

    ranges = _parse_ranges(a.ranges)
    rep = audit(a.root, a.rel, line_ranges=ranges, subdirs=subdirs)
    rep["wall_seconds"] = round(time.time() - t0, 2)

    if a.cmd == "audit":
        for line in audit_lines(rep):
            print(line)
        if a.json:
            _write(a.json, rep)
        return 1 if (a.strict and rep["scoped_not_live"]) else 0

    rows = _load_ledger(os.path.join(a.root, a.ledger)
                        if not os.path.isabs(a.ledger) else a.ledger)
    st = stratify(rep, list(rows.values()), subject_digest=a.subject_digest)
    st["audit"] = rep
    st["wall_seconds"] = round(time.time() - t0, 2)
    for line in audit_lines(rep):
        print(line)
    for line in strata_lines(st):
        print(line)
    if a.json:
        _write(a.json, st)
    if a.strict:
        off = sum(s["graded"] for k, s in st["strata"].items()
                  if k != VERDICT_LIVE)
        return 1 if off else 0
    return 0


def _write(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, indent=1, sort_keys=True) + "\n")
    print("wrote %s" % path)


if __name__ == "__main__":                                # pragma: no cover
    sys.exit(main())
