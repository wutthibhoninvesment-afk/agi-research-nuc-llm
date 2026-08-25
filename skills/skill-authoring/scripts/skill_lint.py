#!/usr/bin/env python3
"""skill_lint.py — validate SKILL.md files against Anthropic's published
constraints and (optionally) this workspace's house format.

Usage:
    python3 skill_lint.py [--house] [--strict] PATH [PATH ...]

Each PATH is either a skill directory (contains SKILL.md) or a directory of
skill directories (each subdir containing SKILL.md is linted).

Exit codes: 0 = no errors, 1 = at least one error, 2 = usage/IO problem.
Warnings never fail the run unless --strict is given.

Official constraints enforced (platform.claude.com Agent Skills docs):
    name:  <=64 chars; ^[a-z0-9]+(-[a-z0-9]+)*$; no reserved words
           ("anthropic", "claude"); non-empty.
    description: non-empty; <=1024 chars; no XML tags; third person;
           should state what AND when (trigger phrasing).
    body:  under 500 lines; relative links resolve; linked references
           should not link onward to further references (one level deep);
           content should live in SKILL.md OR a reference, never both;
           bundled files must be mentioned from SKILL.md (else invisible).
    paths: forward slashes only (Windows-style paths flagged).

House format (--house; this workspace's CLAUDE.md rule 5):
    required sections: trigger conditions, numbered steps, pitfalls,
    verification; exact commands present (a fenced code block).
"""

import argparse
import os
import re
import sys

RESERVED_WORDS = ("anthropic", "claude")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
# An XML/HTML-looking tag: <word ...> or </word>. Excludes bare < / > math.
XML_TAG_RE = re.compile(r"</?[A-Za-z][^>\n]*>")
# Windows-style path: word chars, backslash, word char (foo\bar). Checked
# outside fenced code blocks only, to avoid flagging string escapes in code.
WINPATH_RE = re.compile(r"[\w.]\\[\w]")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
FIRST_PERSON_RE = re.compile(r"\b(I|I'll|I'm|me, Claude)\b|^You can\b", re.I)
TRIGGER_HINT_RE = re.compile(r"\b(use when|when |trigger|use this|use for|for use)\b", re.I)
NUMBERED_STEP_RE = re.compile(r"^\s{0,3}1[.)]\s", re.M)
FENCE_RE = re.compile(r"^\s*(```|~~~)", re.M)


class Finding:
    def __init__(self, path, level, code, message):
        self.path, self.level, self.code, self.message = path, level, code, message

    def __str__(self):
        return f"{self.path}: {self.level} {self.code} {self.message}"


def parse_frontmatter(text):
    """Minimal YAML-subset parser for SKILL.md frontmatter.

    Returns (fields: dict[str, str], body: str, error: str|None).
    Supports `key: value`, quoted values, `key: >-`/`|` block scalars, and
    nested block mappings (captured as raw text under the top-level key).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text, "no frontmatter: file must start with '---' on line 1"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text, "frontmatter opened with '---' but never closed"

    fields = {}
    block_keys = set()
    fields["__block__"] = block_keys
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line[0] in " \t":
            return fields, "", f"unexpected indented line in frontmatter at line {i + 1}"
        if ":" not in line:
            return fields, "", f"malformed frontmatter line {i + 1}: {line!r}"
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest in (">", ">-", "|", "|-"):
            block = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][0] in " \t"):
                block.append(lines[i].strip())
                i += 1
            joiner = " " if rest.startswith(">") else "\n"
            fields[key] = joiner.join(b for b in block if b).strip()
            block_keys.add(key)
            continue
        if rest == "":
            # nested block mapping (e.g. metadata:) — capture raw, skip
            block = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][0] in " \t"):
                block.append(lines[i])
                i += 1
            fields[key] = "\n".join(b.strip() for b in block).strip()
            block_keys.add(key)
            continue
        if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in "\"'":
            rest = rest[1:-1]
        fields[key] = rest
        i += 1
    body = "\n".join(lines[end + 1:])
    return fields, body, None


def strip_fenced_code(body):
    """Return body with fenced code block contents blanked (fences kept)."""
    out, in_fence, fence_tok = [], False, None
    for line in body.split("\n"):
        stripped = line.lstrip()
        if in_fence:
            if stripped.startswith(fence_tok):
                in_fence = False
                out.append(line)
            else:
                out.append("")
        else:
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence, fence_tok = True, stripped[:3]
            out.append(line)
    return "\n".join(out)


DUP_MIN_CHARS = 120
SKIP_DIRS = {"__pycache__", ".git", "node_modules"}


def _norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def content_chunks(body):
    """Split a markdown body into normalised chunks: prose paragraphs and
    fenced code blocks, each at least DUP_MIN_CHARS long. Headings are
    dropped (they legitimately repeat across files)."""
    chunks, para, fence = [], [], None
    def flush():
        txt = _norm("\n".join(para))
        if len(txt) >= DUP_MIN_CHARS:
            chunks.append(txt)
        para.clear()
    for line in body.split("\n"):
        st = line.strip()
        if fence is None and (st.startswith("```") or st.startswith("~~~")):
            flush()
            fence = st[:3]
            continue
        if fence is not None:
            if st.startswith(fence):
                flush()
                fence = None
            else:
                para.append(line)
            continue
        if not st:
            flush()
        elif st.startswith("#"):
            flush()
        else:
            para.append(line)
    flush()
    return chunks


def local_md_links(text, base_dir):
    """Yield (raw_target, absolute_path) for relative .md links in text."""
    for m in MD_LINK_RE.finditer(strip_fenced_code(text)):
        target = m.group(1)
        if "://" in target or target.startswith(("#", "mailto:")):
            continue
        path = os.path.normpath(os.path.join(base_dir, target.split("#")[0]))
        if path.endswith(".md"):
            yield target, path


def bundled_files(skill_dir):
    """All regular files under skill_dir except SKILL.md, hidden files and
    build/cache directories; returned as forward-slash relative paths."""
    out = []
    for root, dirs, files in os.walk(skill_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(files):
            if fn.startswith(".") or fn.endswith((".pyc", ".pyo")):
                continue
            rel = os.path.relpath(os.path.join(root, fn), skill_dir).replace(os.sep, "/")
            if rel != "SKILL.md":
                out.append(rel)
    return out


EXEMPT_BASENAMES_RE = re.compile(r"^(LICENSE|LICENCE|COPYING)(\..*)?$", re.I)


def is_mentioned(rel, text):
    """A bundled file counts as referenced when its relative path or its
    basename appears anywhere in SKILL.md (links, fenced commands, prose),
    or when one of its ancestor directories is mentioned *as a directory*
    ("see `templates/`", "read `references/layouts/<layout>.md`") — i.e.
    followed by something that is not a file name. A sibling's path
    ("scripts/other.py") does not count as mentioning the directory."""
    if rel in text or os.path.basename(rel) in text:
        return True
    parts = rel.split("/")[:-1]
    for i in range(1, len(parts) + 1):
        d = "/".join(parts[:i])
        if re.search(re.escape(d) + r"/(?![\w.-])", text):
            return True
    return False


def is_exempt(rel):
    """Files that are legitimately unmentioned: licences, and private helper
    modules (``_helpers.py``, ``__init__.py``) reached through a mentioned
    script rather than directly."""
    base = os.path.basename(rel)
    return bool(EXEMPT_BASENAMES_RE.match(base)) or (base.startswith("_") and base.endswith(".py"))


def lint_skill(skill_dir, house=False):
    """Lint one skill directory. Returns list[Finding]."""
    findings = []
    rel = skill_dir
    md_path = os.path.join(skill_dir, "SKILL.md")

    def err(code, msg):
        findings.append(Finding(md_path, "ERROR", code, msg))

    def warn(code, msg):
        findings.append(Finding(md_path, "WARN", code, msg))

    if not os.path.isfile(md_path):
        err("F001", "SKILL.md not found")
        return findings
    try:
        with open(md_path, encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        err("F001", f"cannot read SKILL.md: {e}")
        return findings

    fields, body, fm_err = parse_frontmatter(text)
    if fm_err:
        err("F002", fm_err)
        return findings

    # --- name ---
    name = fields.get("name", "")
    if not name:
        err("N001", "frontmatter 'name' missing or empty")
    else:
        if len(name) > 64:
            err("N002", f"name is {len(name)} chars (max 64)")
        if not NAME_RE.match(name):
            err("N003", f"name {name!r} must be lowercase letters/digits/hyphens "
                        "(no leading/trailing/double hyphens)")
        for w in RESERVED_WORDS:
            if w in name.split("-") or w in name:
                err("N004", f"name contains reserved word {w!r}")
        dirname = os.path.basename(os.path.abspath(skill_dir))
        if NAME_RE.match(name) and name != dirname:
            warn("N005", f"name {name!r} != directory name {dirname!r}")

    # --- description ---
    desc = fields.get("description", "")
    if not desc:
        err("D001", "frontmatter 'description' missing or empty")
    else:
        if len(desc) > 1024:
            err("D002", f"description is {len(desc)} chars (max 1024)")
        if XML_TAG_RE.search(desc):
            err("D003", "description contains XML/HTML tags")
        if FIRST_PERSON_RE.search(desc):
            warn("D004", "description not in third person (found 'I'/'You can')")
        if not TRIGGER_HINT_RE.search(desc):
            warn("D005", "description has no trigger phrasing "
                         "(no 'Use when …' / 'when …' clause)")
        if "description" in fields.get("__block__", ()):
            warn("D006", "description uses a YAML block scalar / next-line "
                         "value; naive frontmatter extractors index it as "
                         "empty and the skill silently never triggers — put "
                         "it on one line")

    # --- body ---
    body_lines = body.split("\n")
    n_lines = len(body_lines)
    if n_lines > 500:
        err("B001", f"body is {n_lines} lines (keep under 500; split into "
                    "reference files)")
    elif n_lines > 400:
        warn("B002", f"body is {n_lines} lines (approaching the 500-line limit)")

    prose = strip_fenced_code(body)
    if WINPATH_RE.search(prose):
        warn("B003", "possible Windows-style path (backslash) outside code fence")

    # --- relative links resolve; long reference files need a ToC ---
    for m in MD_LINK_RE.finditer(prose):
        target = m.group(1)
        if "://" in target or target.startswith(("#", "mailto:")):
            continue
        target_path = os.path.normpath(
            os.path.join(skill_dir, target.split("#")[0]))
        if not os.path.exists(target_path):
            err("R001", f"linked file does not exist: {target}")
        elif target_path.endswith(".md"):
            try:
                with open(target_path, encoding="utf-8") as f:
                    ref_lines = f.read().split("\n")
                if len(ref_lines) > 100 and not any(
                        re.match(r"^#{1,3}\s+(contents|table of contents)",
                                 l.strip(), re.I) for l in ref_lines[:30]):
                    warn("R002", f"reference file {target} is "
                                 f"{len(ref_lines)} lines with no Contents/ToC "
                                 "heading near the top")
            except (OSError, UnicodeDecodeError):
                pass

    # --- references: one level deep, no duplicated content ---
    skill_chunks = None
    for target, target_path in local_md_links(body, skill_dir):
        if not os.path.isfile(target_path):
            continue
        try:
            with open(target_path, encoding="utf-8") as f:
                ref_text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        ref_dir = os.path.dirname(target_path)
        first_level = {p for _, p in local_md_links(body, skill_dir)}
        first_level.add(os.path.normpath(md_path))
        for sub_target, sub_path in local_md_links(ref_text, ref_dir):
            if sub_path not in first_level:
                warn("R003", f"reference {target} links onward to {sub_target}; "
                             "keep references one level deep from SKILL.md "
                             "(link it from SKILL.md or inline it)")
        if skill_chunks is None:
            skill_chunks = content_chunks(body)
        ref_norm = _norm(ref_text)
        dup = [c for c in skill_chunks if c in ref_norm]
        if dup:
            warn("R004", f"{len(dup)} paragraph/code chunk(s) of SKILL.md are "
                         f"duplicated verbatim in {target}; content should live "
                         "in exactly one place")

    # --- bundled files must be reachable from SKILL.md ---
    files = bundled_files(skill_dir)
    for rel in files:
        if is_exempt(rel) or is_mentioned(rel, text):
            continue
        base = os.path.basename(rel)
        if base.startswith("test_") or base.endswith("_test.py"):
            subject = base[5:] if base.startswith("test_") else base[:-8] + ".py"
            if is_mentioned(os.path.join(os.path.dirname(rel), subject), text):
                continue                       # tests of a referenced script
        warn("R005", f"bundled file {rel} is never mentioned in SKILL.md "
                     "(an unreferenced file is invisible to the model)")

    # --- house format ---
    if house:
        level = "ERROR"

        def house_finding(code, msg):
            findings.append(Finding(md_path, level, code, msg))

        headings = [l.strip() for l in body_lines if l.strip().startswith("#")]
        heading_blob = "\n".join(headings).lower()
        if not re.search(r"trigger|when to use", heading_blob):
            house_finding("H001", "no trigger section (heading matching "
                                  "'trigger' or 'when to use')")
        if not NUMBERED_STEP_RE.search(body):
            house_finding("H002", "no numbered steps (no line starting '1. ')")
        if not re.search(r"pitfall|anti-pattern|gotcha", heading_blob):
            house_finding("H003", "no pitfalls section")
        if not re.search(r"verif", heading_blob):
            house_finding("H004", "no verification section")
        if not FENCE_RE.search(body):
            house_finding("H005", "no fenced code block (house format wants "
                                  "exact commands)")
    return findings


def discover_skill_dirs(path):
    """Given a path, return the skill dirs to lint."""
    if os.path.isfile(path) and os.path.basename(path) == "SKILL.md":
        return [os.path.dirname(path) or "."]
    if os.path.isdir(path):
        if os.path.isfile(os.path.join(path, "SKILL.md")):
            return [path]
        subs = []
        for entry in sorted(os.listdir(path)):
            sub = os.path.join(path, entry)
            if os.path.isdir(sub) and os.path.isfile(os.path.join(sub, "SKILL.md")):
                subs.append(sub)
        return subs
    return []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--house", action="store_true",
                    help="also enforce house format (triggers/steps/pitfalls/"
                         "verification/commands) as errors")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as errors for the exit code")
    args = ap.parse_args(argv)

    skill_dirs = []
    for p in args.paths:
        found = discover_skill_dirs(p)
        if not found:
            print(f"{p}: no SKILL.md found here or in immediate subdirectories",
                  file=sys.stderr)
            return 2
        skill_dirs.extend(found)

    all_findings = []
    for d in skill_dirs:
        all_findings.extend(lint_skill(d, house=args.house))

    for f in all_findings:
        print(f)
    n_err = sum(1 for f in all_findings if f.level == "ERROR")
    n_warn = sum(1 for f in all_findings if f.level == "WARN")
    print(f"skill-lint: {len(skill_dirs)} skill(s), {n_err} error(s), "
          f"{n_warn} warning(s)")
    if n_err or (args.strict and n_warn):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
