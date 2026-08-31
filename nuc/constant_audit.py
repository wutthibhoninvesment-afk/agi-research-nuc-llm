#!/usr/bin/env python3
"""constant_audit.py — grade the PROVENANCE of size constants in a Python tree.

Round 382, discharging round 376's next-steps item 5. Round 376 found that
`fast_lane.QWEN36.expert_bytes` was the expert's ON-DISK int4 size sitting in a
field that means "bytes per cached slot in RAM" — wrong by the 1.889x unpack
ratio the loader performs, green for 250+ rounds behind a test that restated
it. Item 5 asked for one pass over `nuc/` and `harness/` for other constants on
the wrong side of a transform.

The pass found none of that exact shape. What it found is the shape UNDERNEATH
it, and that is what this tool grades:

    A constant's value can be checked. Its PROVENANCE is what decides whether
    anyone ever will.

`expert_bytes` was `1_572_864 + 196_608` — an opaque pair of magic numbers.
Nothing in the expression said which side of the int4->int8 unpack it was on,
so nothing could contradict it, so nothing did. The two OTHER size constants in
the same record (`kv_bytes_per_token`, `fixed_bytes`) had the identical grade,
their derivations living in a comment above the record. Checked against the
engine source this round, one was exactly right and one was a rounded
restatement of a value another module in this same repo already had exact.

So the grades are about EXPRESSIONS, not values:

  derived   the right-hand side is arithmetic over named quantities, at least
            one of which is not a unit scale. `3 * INTER * HIDDEN` cannot be
            silently on the wrong side of a transform: the names say which
            side. This is the target state.
  bare      an opaque literal, optionally times a unit (`int(9.25 * GB)`,
            `40_960`). Provenance is at best a comment, which no test reads.
  disk      the NAME says on-disk/packed/compressed. Not a defect — the whole
            round-376 bug was a disk-sized value in a RAM-named field, and a
            name that declares the side is the cheapest possible fix.

and one cross-cutting flag:

  transform_risk   a `bare` constant whose name means allocated/resident/RAM
            while its own comment block mentions a packing, compression or
            quantization word. That is the round-376 bug, statically.

USAGE
    python3 nuc/constant_audit.py audit nuc harness
    python3 nuc/constant_audit.py audit nuc --json
    python3 nuc/constant_audit.py audit nuc --grade bare

Exit 2 if any `transform_risk` finding survives; 0 otherwise. Grading `bare` is
NOT an error — plenty of constants are single live readings and honestly
cannot be derived. The tool's job is to make the list short and explicit.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

# A name that denotes a number of bytes.
SIZE_NAME = re.compile(
    r"(?i)(^|_)(bytes|size|nbytes)($|_)|bytes_per|per_byte|_b$|_bytes")

# Names that are pure unit scales: multiplying by one is not provenance.
UNIT_NAMES = {"B", "KB", "MB", "GB", "TB", "KIB", "MIB", "GIB", "TIB",
              "F32", "F16", "I8", "U8", "BYTE", "BYTES_PER_MB"}

# Words that mean "this number describes data at rest, in a transformed form".
TRANSFORM_WORDS = re.compile(
    r"(?i)\b(on[- ]?disk|packed|compressed|gzip|zstd|quantiz(ed|ation)|"
    r"int4|int8|nibble|serial(ized|ised)|encoded|shard header|container|"
    r"tarball|du -sb|stat -c)\b")

# Words that mean "this number describes live allocation".
ALLOC_WORDS = re.compile(
    r"(?i)(^|_|\b)(slot|resident|rss|alloc(ated)?|ram|heap|cached|cache|"
    r"footprint|dense|kv|fixed|in memory|per entry)($|_|\b)")

# Directories that are vendored copies of someone else's source.
VENDORED = ("colibri-c", "kv_reuse/upstream", "kv_reuse/patched",
            "hermes-dump", "__pycache__", "scratch-e2", "site-packages")


def _is_unit(name: str) -> bool:
    return name.upper() in UNIT_NAMES


# Callables that convert a number without adding provenance. `int(9.25 * GB)`
# is a single reading in a unit, not a derivation — an early version of this
# tool graded it `derived` because `int` is an `ast.Name`.
NEUTRAL_CALLS = {"int", "round", "float", "abs", "max", "min"}


def grade_expression(node: ast.AST) -> str:
    """`derived` if the expression names a non-unit quantity, else `bare`."""
    skip = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) \
                and sub.func.id in NEUTRAL_CALLS:
            skip.add(id(sub.func))
    for sub in ast.walk(node):
        if id(sub) in skip:
            continue
        if isinstance(sub, ast.Name) and not _is_unit(sub.id):
            return "derived"
        if isinstance(sub, ast.Attribute) and not _is_unit(sub.attr):
            return "derived"
    return "bare"


def _numeric(node: ast.AST) -> bool:
    """Does this expression evaluate to a number at all?

    Only constants and arithmetic over them count; a string, list or call to
    something other than int()/round() is not a size constant.
    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and not isinstance(sub.value, (int, float)):
            return False
        if isinstance(sub, (ast.List, ast.Dict, ast.Set, ast.Tuple, ast.JoinedStr,
                            ast.Compare, ast.Subscript)):
            return False
        if isinstance(sub, ast.Call) and not (
                isinstance(sub.func, ast.Name) and sub.func.id in NEUTRAL_CALLS):
            return False
    # ROUND 382 BUG, found by running this tool on the constants it had just
    # been used to fix: the original required at least one numeric literal, so
    # `SLOT_BYTES = WEIGHT_BYTES + SCALE_BYTES` -- a constant with NO literal
    # at all, which is the tool's own target state -- was silently dropped and
    # never appeared in the report. An audit whose blind spot is exactly the
    # grade it recommends will always report progress.
    return True


def _comment_block(lines: list[str], lineno: int, back: int = 12) -> str:
    """The contiguous `#` comment block immediately above `lineno`, plus the
    line itself — where a bare constant's provenance actually lives."""
    out = [lines[lineno - 1]] if 0 < lineno <= len(lines) else []
    i = lineno - 2
    seen = 0
    while i >= 0 and seen < back:
        stripped = lines[i].strip()
        if stripped.startswith("#"):
            out.append(stripped)
            seen += 1
            i -= 1
            continue
        if not stripped:            # a blank line inside a comment block is fine
            i -= 1
            seen += 1
            continue
        break
    return "\n".join(reversed(out))


def field_declarations(tree: ast.AST, lines: list[str]) -> dict[str, dict[str, str]]:
    """`{ClassName: {field: trailing comment}}` for annotated class fields.

    ROUND 382. This is what makes the round-376 bug detectable at all. The
    value's comment said where the number CAME FROM ("read from the shard
    headers", "int4 ... container"); the field declaration said what it MEANT
    ("bytes per cached expert slot"). Neither text alone is suspicious. The
    defect is the pair, and the pair is only visible if the auditor reads the
    class declaration as well as the call site.
    """
    out: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        fields: dict[str, str] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                line = lines[stmt.lineno - 1] if stmt.lineno <= len(lines) else ""
                fields[stmt.target.id] = line.split("#", 1)[1].strip() if "#" in line else ""
        if fields:
            out[node.name] = fields
    return out


def audit_source(src: str, path: str) -> list[dict]:
    """Every size-named constant in one module, graded."""
    tree = ast.parse(src)
    lines = src.splitlines()
    decls = field_declarations(tree, lines)
    found: list[dict] = []

    def record(name: str, value_node: ast.AST, lineno: int, kind: str,
               declared: str = ""):
        if not SIZE_NAME.search(name) or not _numeric(value_node):
            return
        grade = grade_expression(value_node)
        if re.search(r"(?i)(disk|packed|compressed|on_disk|tar)", name):
            grade = "disk"
        ctx = _comment_block(lines, lineno)
        # The "this is live allocation" side may be stated in the NAME or in
        # the field's declared meaning; the "this came from data at rest" side
        # is in the value's comment block. Round 376's `expert_bytes` said it
        # only in the declaration -- which is why the first version of this
        # tool, keying on the name alone, scored the historical source 0 risks.
        means_alloc = bool(ALLOC_WORDS.search(name) or ALLOC_WORDS.search(declared))
        risk = grade == "bare" and means_alloc and bool(TRANSFORM_WORDS.search(ctx))
        found.append({
            "file": path, "line": lineno, "name": name, "kind": kind,
            "grade": grade, "transform_risk": risk, "declared_as": declared,
            "expr": (ast.get_source_segment(src, value_node) or "").strip(),
        })

    def is_sentinel(value: ast.AST) -> bool:
        """A dataclass field default of 0/None is a placeholder, not a size."""
        return isinstance(value, ast.Constant) and value.value in (0, None, False)

    def visit(node: ast.AST) -> None:
        """Module and class scope only.

        Function bodies hold locals and intermediate rates -- an early version
        of this tool reported `per_byte_s = 1.0 / (nvme_mb_s * MB)` and a
        `size = int(header[2])` parsed out of a ledger line. Neither is a
        constant anybody could get on the wrong side of a transform.
        """
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Assign):
                for t in child.targets:
                    if isinstance(t, ast.Name):
                        record(t.id, child.value, child.lineno, "assign")
            elif isinstance(child, ast.AnnAssign) and child.value is not None:
                if isinstance(child.target, ast.Name) and not is_sentinel(child.value):
                    record(child.target.id, child.value, child.lineno, "annassign")
            elif isinstance(child, ast.Call):
                callee = child.func.id if isinstance(child.func, ast.Name) else ""
                fields = decls.get(callee, {})
                for kw in child.keywords:
                    if kw.arg:
                        record(kw.arg, kw.value,
                               getattr(kw.value, "lineno", child.lineno), "keyword",
                               declared=fields.get(kw.arg, ""))
            visit(child)

    visit(tree)
    return found


def _skip(path: Path) -> bool:
    s = str(path)
    return any(v in s for v in VENDORED)


def audit_paths(paths: list[str], include_tests: bool = False) -> list[dict]:
    out: list[dict] = []
    for p in paths:
        root = Path(p)
        files = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for f in files:
            if _skip(f):
                continue
            if not include_tests and (f.name.startswith("test_")
                                      or f.parent.name == "tests"):
                continue
            try:
                out.extend(audit_source(f.read_text(), str(f)))
            except (SyntaxError, UnicodeDecodeError):
                continue
    return out


def summarize(findings: list[dict]) -> dict:
    grades: dict[str, int] = {}
    for f in findings:
        grades[f["grade"]] = grades.get(f["grade"], 0) + 1
    risky = [f for f in findings if f["transform_risk"]]
    return {"n": len(findings), "by_grade": grades,
            "transform_risk": len(risky),
            "derived_fraction": (round(grades.get("derived", 0) / len(findings), 3)
                                 if findings else 0.0)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="grade size constants under PATHS")
    a.add_argument("paths", nargs="+")
    a.add_argument("--json", action="store_true")
    a.add_argument("--grade", default=None,
                   help="only report this grade (derived/bare/disk)")
    a.add_argument("--include-tests", action="store_true",
                   help="also grade test modules (off by default: a test's "
                        "literals are usually the assertion, not a constant)")
    args = ap.parse_args(argv)

    findings = audit_paths(args.paths, include_tests=args.include_tests)
    if args.grade:
        findings = [f for f in findings if f["grade"] == args.grade]
    summary = summarize(findings)

    if args.json:
        print(json.dumps({"summary": summary, "findings": findings}, indent=2))
    else:
        print(f"# constant provenance audit: {summary['n']} size constant(s) "
              f"in {len(set(f['file'] for f in findings))} file(s)")
        print(f"# {summary['by_grade']}  derived_fraction="
              f"{summary['derived_fraction']}  transform_risk="
              f"{summary['transform_risk']}")
        for f in sorted(findings, key=lambda x: (x["grade"] != "bare",
                                                 x["file"], x["line"])):
            flag = "  <== TRANSFORM RISK" if f["transform_risk"] else ""
            print(f"{f['grade']:8} {f['file']}:{f['line']:<5} {f['name']:26} "
                  f"= {f['expr'][:46]}{flag}")
    return 2 if summary["transform_risk"] else 0


if __name__ == "__main__":
    sys.exit(main())
