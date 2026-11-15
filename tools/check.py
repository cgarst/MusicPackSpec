#!/usr/bin/env python3
"""Validates the examples (must pass) and conformance/invalid (must fail) against the schemas, and checks the rules a
JSON Schema cannot express: unique ids, references, strictly increasing sync times, anchor type matching the score.

Usage: python3 tools/check.py        (needs the `jsonschema` package)
"""
import json, sys, glob, os
from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load = lambda p: json.load(open(p))
manifest_v = Draft202012Validator(load(f"{ROOT}/schema/manifest.schema.json"))
sync_v = Draft202012Validator(load(f"{ROOT}/schema/sync.schema.json"))
ANCHOR = {"gp3": "bar", "gp4": "bar", "gp5": "bar", "gp": "bar", "gpx": "bar", "musicxml": "bar", "mxl": "bar",
          "mscz": "bar", "alphatex": "bar", "midi": "tick", "abc": "text", "pdf": "pdf", "txt": "text"}


def schema_errors(validator, doc):
    return [f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in validator.iter_errors(doc)]


def rule_errors_manifest(m):
    errs, recs, scores = [], m.get("recordings", []), m.get("scores", [])
    sids = [t.get("id") for t in scores]
    all_ids = []
    for t in scores:
        parts = [(t, f"score {t.get('id')}")] + [(a, f"alternate {a.get('id')}") for a in t.get("alternates", [])]
        for x, name in parts:
            all_ids.append(x.get("id"))
            if "startPage" in x and "endPage" in x and x["endPage"] < x["startPage"]:
                errs.append(f"{name}: endPage must be >= startPage")
            if "pages" in x and "startPage" in x and x["startPage"] > x["pages"]:
                errs.append(f"{name}: startPage exceeds pages")
            if "pages" in x and "endPage" in x and x["endPage"] > x["pages"]:
                errs.append(f"{name}: endPage exceeds pages")
            if x is not t and ANCHOR.get(x.get("format")) != ANCHOR.get(t.get("format")):
                errs.append(f"{name}: anchor type of {x.get('format')} differs from its parent score {t.get('id')}")
    if len(all_ids) != len(set(all_ids)):
        errs.append("duplicate score or alternate ids")
    ids = [r["id"] for r in recs]
    if len(ids) != len(set(ids)):
        errs.append("duplicate recording ids")
    for r in recs:
        for k in ("syncFrom", "stemOf"):
            if k in r and r[k] not in ids:
                errs.append(f"{r['id']}.{k} names unknown recording {r[k]}")
        for k in r.get("sync", {}):
            if k not in sids:
                errs.append(f"{r['id']}.sync names unknown score {k}")
        for k, v in r.get("scoreTracks", {}).items():
            if k not in sids:
                errs.append(f"{r['id']}.scoreTracks names unknown score {k}")
            lst = v.get("omits", v.get("only"))
            if "names" in v and lst is not None and len(v["names"]) != len(lst):
                errs.append(f"{r['id']}.scoreTracks.{k}: names must have one name for each index")
        sids_src = [s["id"] for s in r.get("sources", []) if "id" in s]
        for s in r.get("sources", []):
            if "derivedFrom" in s and s["derivedFrom"] not in sids_src:
                errs.append(f"{r['id']}: derivedFrom names unknown source {s['derivedFrom']}")
            if s.get("type") == "embedded" and "score" in s and s["score"] not in sids:
                errs.append(f"{r['id']}: source names unknown score {s['score']}")
    return errs


def rule_errors_sync(s, score_format=None):
    errs = []
    t = [p["timeMs"] for p in s["points"]]
    if any(b <= a for a, b in zip(t, t[1:])):
        errs.append("timeMs not strictly increasing")
    if score_format and ANCHOR[score_format] != s["anchorType"]:
        errs.append(f"anchorType {s['anchorType']} does not match score format {score_format}")
    return errs


bad = 0
for mp in sorted(glob.glob(f"{ROOT}/examples/*/manifest.json")):
    d = os.path.dirname(mp)
    m = load(mp)
    errs = schema_errors(manifest_v, m) + rule_errors_manifest(m)
    fmt = {t["id"]: t["format"] for t in m.get("scores", [])}
    for r in m.get("recordings", []):
        for sid, rel in r.get("sync", {}).items():
            sp = os.path.join(d, rel)
            if not os.path.exists(sp):
                errs.append(f"{r['id']}: missing {rel}")
                continue
            s = load(sp)
            errs += [f"{rel}: {e}" for e in schema_errors(sync_v, s) + rule_errors_sync(s, fmt.get(sid))]
            if s.get("recording") != r["id"]:
                errs.append(f"{rel}: recording id mismatch")
            if s.get("score") != sid:
                errs.append(f"{rel}: score id mismatch")
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
