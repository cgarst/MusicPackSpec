#!/usr/bin/env python3
"""Validates the examples (must pass) and conformance/invalid (must fail) against the schemas, and checks the rules a
JSON Schema cannot express: unique ids, references, strictly increasing sync times, anchor type matching the tab.

Usage: python3 tools/check.py        (needs the `jsonschema` package)
"""
import json, sys, glob, os
from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load = lambda p: json.load(open(p))
manifest_v = Draft202012Validator(load(f"{ROOT}/schema/manifest.schema.json"))
sync_v = Draft202012Validator(load(f"{ROOT}/schema/sync.schema.json"))
ANCHOR = {"gp3": "bar", "gp4": "bar", "gp5": "bar", "gp": "bar", "gpx": "bar", "musicxml": "bar", "mxl": "bar",
          "mscz": "bar", "midi": "tick", "abc": "text", "pdf": "pdf", "txt": "text"}


def schema_errors(validator, doc):
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in validator.iter_errors(doc)]


def rule_errors_manifest(m):
    errs, recs, t = [], m.get("recordings", []), m.get("tab", {})
    if "startPage" in t and "endPage" in t and t["endPage"] < t["startPage"]:
        errs.append("tab.endPage must be >= tab.startPage")
    if "pages" in t and "startPage" in t and t["startPage"] > t["pages"]:
        errs.append("tab.startPage exceeds tab.pages")
    if "pages" in t and "endPage" in t and t["endPage"] > t["pages"]:
        errs.append("tab.endPage exceeds tab.pages")
    ids = [r["id"] for r in recs]
    if len(ids) != len(set(ids)):
        errs.append("duplicate recording ids")
    for r in recs:
        for k in ("syncFrom", "stemOf"):
            if k in r and r[k] not in ids:
                errs.append(f"{r['id']}.{k} names unknown recording {r[k]}")
        sids = [s["id"] for s in r.get("sources", []) if "id" in s]
        for s in r.get("sources", []):
            if "derivedFrom" in s and s["derivedFrom"] not in sids:
                errs.append(f"{r['id']}: derivedFrom names unknown source {s['derivedFrom']}")
    if "defaultRecording" in m and m["defaultRecording"] not in ids:
        errs.append("defaultRecording names unknown recording")
    return errs


def rule_errors_sync(s, tab_format=None):
    errs = []
    t = [p["timeMs"] for p in s["points"]]
    if any(b <= a for a, b in zip(t, t[1:])):
        errs.append("timeMs not strictly increasing")
    if tab_format and ANCHOR[tab_format] != s["anchorType"]:
        errs.append(f"anchorType {s['anchorType']} does not match tab format {tab_format}")
    return errs


bad = 0
for mp in sorted(glob.glob(f"{ROOT}/examples/*/manifest.json")):
    d = os.path.dirname(mp)
    m = load(mp)
    errs = schema_errors(manifest_v, m) + rule_errors_manifest(m)
    for r in m.get("recordings", []):
        if "sync" in r:
            sp = os.path.join(d, r["sync"])
            if not os.path.exists(sp):
                errs.append(f"{r['id']}: missing {r['sync']}")
                continue
            s = load(sp)
            errs += [f"{r['sync']}: {e}" for e in schema_errors(sync_v, s) + rule_errors_sync(s, m["tab"]["format"])]
            if s.get("recording") != r["id"]:
                errs.append(f"{r['sync']}: recording id mismatch")
    print(("FAIL " if errs else "ok   ") + os.path.relpath(mp, ROOT))
    for e in errs:
        print("     ", e)
    bad += bool(errs)

for p in sorted(glob.glob(f"{ROOT}/conformance/invalid/*.json")):
    name = os.path.basename(p)
    v = sync_v if name.startswith("sync-") else manifest_v
    doc = load(p)
    errs = schema_errors(v, doc)
    if not errs and name.startswith("manifest-"):
        errs = rule_errors_manifest(doc)
    print(("ok   " if errs else "FAIL ") + "invalid/" + name + ("" if errs else "  (was accepted)"))
    bad += not errs

sys.exit(1 if bad else 0)
