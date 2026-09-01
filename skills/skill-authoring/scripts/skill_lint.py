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
    body:  under 500 lines; relative links resolve; link FRAGMENTS resolve
           to a real anchor in the target file; linked references should not
           link onward to further references (one level deep); content should
           live in SKILL.md OR a reference, never both; bundled files must be
           mentioned from SKILL.md (else invisible).
    paths: forward slashes only (Windows-style paths flagged).

House format (--house; this workspace's CLAUDE.md rule 5):
    required sections: trigger conditions, numbered steps, pitfalls,
    verification; exact commands present (a fenced code block).
"""

import argparse
import glob
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


VERIF_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*verif.*)$", re.I | re.M)
ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+", re.M)
# A fenced line that INVOKES something, as opposed to one that shows output,
# a diff, JSON, or a fragment of Python source. Round 429: this is the whole
# discriminator behind H006, and it was chosen by measurement, not taste.
# `filter-shares-the-defect`'s references file has four fenced blocks holding
# fifteen lines of Python source and ZERO invocations — it is legitimately
# prose-only and H006 must not touch it. `pristine-checkout-differential`'s
# had four blocks and 23 lines, of which the invocations are `$ python3
# harness/pristine_check.py ...`, so the `$ ` prompt has to be tolerated.
INVOCATION_RE = re.compile(
    r"^\s*(?:\$\s+)?(?:python3?|pytest|bash|sh|git|grep|find|make|npm|node|\./)"
    r"(?![\w.-])")


def verification_body(body):
    """The text under the first `## Verification`-ish heading, or ""."""
    m = VERIF_HEADING_RE.search(body)
    if not m:
        return ""
    level = len(m.group(1))
    for h in ANY_HEADING_RE.finditer(body, m.end()):
        if len(h.group(1)) <= level:
            return body[m.end():h.start()]
    return body[m.end():]


def fenced_invocations(text):
    """Count lines inside fences that invoke a program."""
    n, tok = 0, None
    for line in text.split("\n"):
        s = line.lstrip()
        if tok is None:
            if s.startswith("```") or s.startswith("~~~"):
                tok = s[:3]
            continue
        if s.startswith(tok):
            tok = None
            continue
        if INVOCATION_RE.match(line):
            n += 1
    return n


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


def is_sibling_skill(target_path, md_path):
    """True if a link points at ANOTHER skill's SKILL.md.

    R002/R003/R004 all police *bundled references* — the progressive-
    disclosure files a skill ships in its own `references/` directory. A
    pointer to a sibling skill is navigation, not bundled content, and the
    three rules are wrong about it in three different ways: it needs no ToC
    (R002), its own onward links are its business and not this skill's
    depth budget (R003), and shared vocabulary between two related skills is
    not duplicated content to be deleted (R004).

    Round 345 hit R002 on exactly this: `skill-authoring/SKILL.md` linking
    `../citation-registry-integrity/SKILL.md`. R006 anchor resolution is
    deliberately NOT filtered here — a fragment into a sibling skill still
    has to resolve, or the link lands the reader at the top of the file.
    """
    return (os.path.basename(target_path) == "SKILL.md"
            and os.path.normpath(target_path) != os.path.normpath(md_path))


def _rel(path, skill_dir):
    """`path` relative to the skill dir, forward-slashed, for messages."""
    return os.path.relpath(path, skill_dir).replace(os.sep, "/")


# --- anchors -------------------------------------------------------------
# A link fragment (`ref.md#frag`, `#frag`) is only useful if `frag` actually
# resolves in the target file; otherwise the reader lands at the top of a
# possibly-400-line reference and silently reads the wrong section. Nothing
# checked this before round 333 -- R001 stripped the fragment off and only
# verified the FILE existed.
#
# Two anchor sources, matching GitHub and the common markdown renderers:
#   1. an explicit HTML anchor:  <a id="x"></a>  /  <a name="x"></a>
#   2. the auto-generated slug of an ATX heading
#
# The slug rule is github-slugger's: lowercase, trim, drop every character
# that is not a word char / whitespace / hyphen, then replace EACH remaining
# whitespace character with '-'. Consecutive hyphens are NOT collapsed, and
# that detail is load-bearing -- both real corpus cases turn on it:
#   `## Fire rates (`--repeats N`)`   -> fire-rates---repeats-n   (3 hyphens:
#       one from the space, two from the flag; the parens/backticks vanish)
#   `## Instrument drift - canary`    (with an em dash) ->
#       instrument-drift--canary      (the em dash is DROPPED but both spaces
#       around it survive as hyphens)
# A whitespace-collapsing slugifier gets the second one wrong; a
# hyphen-collapsing one gets both wrong.
#
# Known limitation: setext headings (`Foo\n===`) are not recognised as
# anchor sources. This corpus uses ATX headings exclusively.
EXPLICIT_ANCHOR_RE = re.compile(
    r"""<a\s[^>]*?\b(?:id|name)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
ATX_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*$", re.M)
SLUG_DROP_RE = re.compile(r"[^\w\s-]")
CLOSING_HASHES_RE = re.compile(r"\s+#+$")


def heading_slug(text):
    """GitHub's heading -> anchor slug. See the note above; does NOT collapse
    runs of whitespace or hyphens."""
    text = CLOSING_HASHES_RE.sub("", text.strip())      # closed ATX: `## X ##`
    return re.sub(r"\s", "-", SLUG_DROP_RE.sub("", text.lower()).strip())


def md_anchors(text):
    """Return (all_anchors, explicit_anchors) defined by a markdown document.

    `all_anchors` is every fragment a link may legitimately target: explicit
    <a id>/<a name> anchors plus heading slugs. Duplicate heading slugs get
    GitHub's `-1`, `-2`, ... disambiguating suffixes. Headings inside fenced
    code blocks are not headings.
    """
    explicit = {a or b for a, b in EXPLICIT_ANCHOR_RE.findall(text) if a or b}
    all_anchors, seen = set(explicit), {}
    for m in ATX_HEADING_RE.finditer(strip_fenced_code(text)):
        slug = heading_slug(m.group(1))
        if not slug:
            continue
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        all_anchors.add(slug if n == 0 else "%s-%d" % (slug, n))
    return all_anchors, explicit


def fragment_links(text, base_dir, self_path):
    """Yield (raw_target, absolute_target_path, fragment) for every link in
    `text` carrying a `#fragment` whose target is this same file or a local
    .md path. Links to non-markdown files (`script.py#L10`) have no markdown
    anchors to check and are skipped; fenced code is ignored.

    The target is NOT stat'd here -- a target that does not exist (or cannot
    be read) is caught once, by the caller's "no anchor set" branch, so that
    a missing file produces exactly one finding (R001) rather than two. An
    earlier draft guarded it in both places; the second guard was
    unreachable, and a mutation run proved it by deleting it with no test
    failing."""
    for m in MD_LINK_RE.finditer(strip_fenced_code(text)):
        target = m.group(1)
        if "://" in target or target.startswith("mailto:"):
            continue
        file_part, sep, frag = target.partition("#")
        if not sep or not frag:
            continue
        if file_part == "":
            path = os.path.normpath(self_path)
        else:
            path = os.path.normpath(os.path.join(base_dir, file_part))
            if not path.endswith(".md"):
                continue
        yield target, path, frag


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
        elif target_path.endswith(".md") and not is_sibling_skill(
                target_path, md_path):
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
        if is_sibling_skill(target_path, md_path):
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

    # --- link fragments resolve to a real anchor (R006), and every explicit
    # anchor is actually linked (R007) ---
    # Checked across SKILL.md AND every first-level reference it links to:
    # the Contents/ToC lists live IN the reference files, so their own
    # same-file fragments are exactly where anchor drift shows up (round 333
    # found `#fire-rates--repeats-n` rotted there, in a ToC whose three
    # sibling entries all used the correct slug).
    anchor_cache = {}

    def anchors_for(path):
        if path not in anchor_cache:
            try:
                with open(path, encoding="utf-8") as f:
                    anchor_cache[path] = md_anchors(f.read())
            except (OSError, UnicodeDecodeError):
                anchor_cache[path] = (None, set())
        return anchor_cache[path]

    self_path = os.path.normpath(md_path)
    anchor_sources = [self_path]
    for _t, p in local_md_links(body, skill_dir):
        p = os.path.normpath(p)
        if os.path.isfile(p) and p not in anchor_sources:
            anchor_sources.append(p)

    used_frags = {}
    for src in anchor_sources:
        try:
            with open(src, encoding="utf-8") as f:
                src_text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        for raw, tgt, frag in fragment_links(
                src_text, os.path.dirname(src) or ".", src):
            used_frags.setdefault(tgt, set()).add(frag)
            defined, _ = anchors_for(tgt)
            if defined is None:
                continue        # missing/unreadable target: R001 owns that
            if frag in defined:
                continue
            where = "" if src == self_path else " (in %s)" % _rel(src, skill_dir)
            err("R006", "link %s%s targets anchor '#%s', which %s does not "
                        "define (no <a id>/<a name> and no heading slugging "
                        "to it) — the reader lands at the top of the file "
                        "instead" % (raw, where, frag, _rel(tgt, skill_dir)))

    for src in anchor_sources:
        _, explicit = anchors_for(src)
        for name in sorted(explicit - used_frags.get(src, set())):
            warn("R007", "anchor '<a id=\"%s\">' in %s is never linked to "
                         "from this skill — either a link rotted away or the "
                         "anchor outlived its entry" % (name, _rel(src, skill_dir)))

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
        # H006 (round 429). H004 asks whether a Verification section EXISTS
        # and H005 whether the body has a fence anywhere; neither notices when
        # a `references/` split carries the section's only runnable commands
        # out of the file. That has now happened three times in this corpus
        # (round 426 caught itself and disclosed it; round 427 did it again to
        # `pristine-checkout-differential`, which then parsed to zero commands
        # for two rounds; `generator-trampoline-evaluator` had been in that
        # state longer). B002 is the pressure that causes it — it fires at 400
        # body lines and transcripts are the easiest lines to move — so the
        # rule that pushes commands out now has one that pulls them back.
        verif = verification_body(body)
        if verif and not FENCE_RE.search(verif):
            moved = []
            for ref in sorted(glob.glob(os.path.join(skill_dir, "references",
                                                     "*.md"))):
                try:
                    with open(ref, encoding="utf-8") as f:
                        n = fenced_invocations(f.read())
                except (OSError, UnicodeDecodeError):
                    continue
                if n:
                    moved.append("%s (%d)" % (_rel(ref, skill_dir), n))
            if moved:
                house_finding(
                    "H006", "Verification section has no fenced command, but "
                            "%s carries runnable invocations — a references "
                            "split moved the skill's own evidence out of it; "
                            "keep at least one command in SKILL.md"
                            % ", ".join(moved))
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
