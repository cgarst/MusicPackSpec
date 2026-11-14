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
Title: Multi-Track Tab (.mtab) Specification
Shortname: mtab
Level: 1
Status: LS
Indent: 2
ED: https://github.com/cgarst/MultiTrackTabSpec
Repository: cgarst/MultiTrackTabSpec
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


def link_sections(line: str) -> str:
    """'section 6.1' / 'Section 9' -> a link to that section's heading id."""
    return mark_keywords(_link_sections(line))


def _link_sections(line: str) -> str:
    return re.sub(
        r"\b([Ss]ection) (\d+)(?:\.(\d+))?",
        lambda m: "[%s %s%s](#s%s%s)" % (
            m.group(1), m.group(2), "." + m.group(3) if m.group(3) else "",
            m.group(2), "-" + m.group(3) if m.group(3) else ""),
        line,
    )


def convert(src: str) -> str:
    lines = src.splitlines()
    # Everything before "## Contents" is the title and intro.
    ci = lines.index("## Contents")
    first_num = next(i for i, l in enumerate(lines) if l.startswith("## 1. "))
    intro = [l for l in lines[1:ci]]
    paras = [p.strip().replace("\n", " ") for p in "\n".join(intro).split("\n\n") if p.strip()]
    abstract = paras[1]          # "A Multi-Track Tab file ... any language can read and write it."
    conventions = [paras[0], paras[2]]   # version note, RFC 2119 note

    out = [HEADER % abstract, '<h2 class="no-num" id="conventions">Conventions</h2>', ""]
    out += [c + "\n" for c in conventions]

    in_code = False
    for line in lines[first_num:]:
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
