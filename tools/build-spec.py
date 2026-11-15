#!/usr/bin/env python3
"""Build the rendered specification with Bikeshed.

SPEC.md stays the single source. This turns it into a Bikeshed source
(site/spec.bs), renders it to site/index.html, and copies the schemas and
examples beside it so the published site serves them.

    pip install bikeshed && bikeshed update   # once
    python3 tools/build-spec.py               # writes site/
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site"

HEADER = """<pre class=metadata>
Title: Music Pack (.mpak) Specification
Shortname: mpak
Level: 1
Status: w3c/UD
Indent: 2
ED: https://github.com/cgarst/MusicPackSpec
Repository: cgarst/MusicPackSpec
Editor: Corey Garst
Abstract: %s
Markup Shorthands: markdown yes, css no
Local Boilerplate: header yes
Boilerplate: omit conformance, omit copyright
Complain About: accidental-2119 no
</pre>

<style>
code, pre { font-size: 0.92em; }
table { border-collapse: collapse; }
</style>

"""


KEYWORDS = re.compile(r"\b(MUST NOT|SHOULD NOT|MUST|SHOULD|MAY)\b")


def mark_keywords(line: str) -> str:
    """Wrap RFC 2119 keywords (outside `code` spans) so Bikeshed styles them."""
    parts = re.split(r"(`[^`]*`)", line)
    return "".join(
        p if p.startswith("`") else KEYWORDS.sub(r'<em class="rfc2119">\1</em>', p)
        for p in parts)


def bold_code(line: str) -> str:
    """Bikeshed leaves **`code`.** unrendered; emit that form as HTML."""
    return re.sub(
        r"\*\*([^*]*`[^*]*)\*\*",
        lambda m: "<strong>%s</strong>" % re.sub(
            r"`([^`]*)`", r"<code>\1</code>", m.group(1)),
        line)


def link_sections(line: str) -> str:
    """'section 6.1' / 'Section 9' -> a link to that section's heading id."""
    return mark_keywords(_link_sections(bold_code(line)))


def _link_sections(line: str) -> str:
    return re.sub(
        r"\b([Ss]ection) (\d+)(?:\.(\d+))?",
        lambda m: "[%s %s%s](#s%s%s)" % (
            m.group(1), m.group(2), "." + m.group(3) if m.group(3) else "",
            m.group(2), "-" + m.group(3) if m.group(3) else ""),
        line,
    )


def inline_html(text: str) -> str:
    """Inline markdown (code spans, bold) to HTML for table cells."""
    parts = re.split(r"(`[^`]*`)", text)
    out = []
    for p in parts:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append("<code>%s</code>" % p[1:-1].replace("&", "&amp;")
                       .replace("<", "&lt;").replace(">", "&gt;"))
        else:
            p = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", p)
            out.append(mark_keywords(_link_sections(p)))
    return "".join(out)


def table_html(rows: list) -> str:
    """Bikeshed has no markdown tables; emit HTML for a pipe table."""
    cells = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
    head, body = cells(rows[0]), [cells(r) for r in rows[2:]]
    h = "<table class=\"data\">\n<thead><tr>%s</tr></thead>\n<tbody>\n" % "".join(
        "<th>%s</th>" % inline_html(c) for c in head)
    for r in body:
        h += "<tr>%s</tr>\n" % "".join("<td>%s</td>" % inline_html(c) for c in r)
    return h + "</tbody>\n</table>\n"


def convert(src: str) -> str:
    lines = src.splitlines()
    # Everything before "## Contents" is the title and intro.
    ci = lines.index("## Contents")
    first_num = next(i for i, l in enumerate(lines) if l.startswith("## 1. "))
    intro = [l for l in lines[1:ci]]
    paras = [p.strip().replace("\n", " ") for p in "\n".join(intro).split("\n\n") if p.strip()]
    abstract = paras[1]          # "A Music Pack file ... any language can read and write it."
    conventions = [paras[0], paras[2]]   # version note, RFC 2119 note

    out = [HEADER % abstract, '<h2 class="no-num" id="conventions">Conventions</h2>', ""]
    out += [c + "\n" for c in conventions]

    in_code = False
    body = lines[first_num:]
    i = -1
    while i + 1 < len(body):
        i += 1
        line = body[i]
        if not in_code and line.startswith("|"):
            j = i
            while j < len(body) and body[j].startswith("|"):
                j += 1
            out.append(table_html(body[i:j]))
            i = j - 1
            continue
        if line.startswith("```"):
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            out.append(line)
            continue
        m = re.match(r"^(#{2,3}) (?:(\d+)(?:\.(\d+))? ?\.? )?(.*)$", line)
        if m:
            hashes, major, minor, title = m.groups()
            title = title.strip()
            h = "#" * (len(hashes) - 1)         # Bikeshed: "#" is h2
            sid = ""
            if major and not minor:
                sid = " {#s%s}" % major
            elif major and minor:
                sid = " {#s%s-%s}" % (major, minor)
            else:
                sid = " {#%s}" % re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            out.append("%s %s %s%s" % (h, title, h, sid))
            continue
        # Bikeshed wants list continuations indented by its own rule; the
        # simplest robust fix is to join wrapped lines into one.
        if (re.match(r"^\s+\S", line) and not re.match(r"^\s*([-*]|\d+\.) ", line)
                and out and out[-1].strip() and not out[-1].startswith("|")):
            out[-1] += " " + link_sections(line.strip())
            continue
        out.append(link_sections(line))
    # Section ids for sub-headings without numbers inherit nothing; fine.
    return "\n".join(out) + "\n"


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    bs = OUT / "spec.bs"
    bs.write_text(convert((ROOT / "SPEC.md").read_text()))
    r = subprocess.run(["bikeshed", "spec", str(bs), str(OUT / "index.html")])
    if r.returncode != 0:
        sys.exit(r.returncode)
    shutil.copytree(ROOT / "schema", OUT / "schema")
    shutil.copytree(ROOT / "examples", OUT / "examples",
                    ignore=shutil.ignore_patterns("README.md"))
    bs.unlink()
    print("wrote", OUT / "index.html")


if __name__ == "__main__":
    main()
