"""Full MPAK v1 validator: JSON Schema + spec rules + archive integrity & security checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator

from .schema_utils import ANCHOR_BY_FORMAT, SchemaRegistry

if TYPE_CHECKING:
    from .archive import MpakPackage

_ARCHIVE_PATH_RE = re.compile(r"^(?!/)(?!.*(^|/)\.\.(/|$))(?!.*//)(?!.*\\)[^\x00-\x1f]+$")


@dataclass
class ValidationIssue:
    """A single validation error or warning tied to a logical path in the pack."""

    severity: str  # "error" | "warning"
    location: str  # e.g. "manifest/scores/0", "sync/mix.json", "archive"
    message: str


def check_entry_name(name: str) -> str | None:
    """Validate an archive entry name per SPEC section 3 & 12. Returns error or None."""
    if not name or not _ARCHIVE_PATH_RE.match(name):
        return f"Invalid archive entry path: {name!r}"
    return None


def schema_errors(validator: Draft202012Validator, doc: Any, prefix: str) -> list[ValidationIssue]:
    """Run Draft 2020-12 JSON Schema validation and return structured issues."""
    issues: list[ValidationIssue] = []
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.path)):
        path = "/".join(map(str, err.path))
        loc = f"{prefix}/{path}" if path else prefix
        issues.append(ValidationIssue("error", loc, err.message))
    return issues


def rule_errors_manifest(m: dict[str, Any]) -> list[ValidationIssue]:
    """Check manifest rules that JSON Schema cannot express (mirrors tools/check.py)."""
    issues: list[ValidationIssue] = []
    recs = m.get("recordings", []) if isinstance(m.get("recordings"), list) else []
    scores = m.get("scores", []) if isinstance(m.get("scores"), list) else []
    sids = [t.get("id") for t in scores if isinstance(t, dict)]

    all_ids: list[tuple[Any, str]] = []
    for i, t in enumerate(scores):
        if not isinstance(t, dict):
            continue
        loc_base = f"manifest/scores/{i}"
        parts: list[tuple[dict[str, Any], str, str]] = [(t, f"score {t.get('id')}", loc_base)]
        for j, a in enumerate(t.get("alternates", [])):
            if isinstance(a, dict):
                parts.append((a, f"alternate {a.get('id')}", f"{loc_base}/alternates/{j}"))
        for x, name, loc in parts:
            all_ids.append((x.get("id"), loc))
            if "startPage" in x and "endPage" in x and isinstance(x["endPage"], int) and isinstance(x["startPage"], int):
                if x["endPage"] < x["startPage"]:
                    issues.append(ValidationIssue("error", loc, f"{name}: endPage must be >= startPage"))
            if "pages" in x and "startPage" in x and isinstance(x["pages"], int) and isinstance(x["startPage"], int):
                if x["startPage"] > x["pages"]:
                    issues.append(ValidationIssue("error", loc, f"{name}: startPage exceeds pages"))
            if "pages" in x and "endPage" in x and isinstance(x["pages"], int) and isinstance(x["endPage"], int):
                if x["endPage"] > x["pages"]:
                    issues.append(ValidationIssue("error", loc, f"{name}: endPage exceeds pages"))
            if x is not t and ANCHOR_BY_FORMAT.get(x.get("format")) != ANCHOR_BY_FORMAT.get(t.get("format")):
                issues.append(
                    ValidationIssue(
                        "error",
                        loc,
                        f"{name}: anchor type of {x.get('format')} differs from its parent score {t.get('id')}",
                    )
                )

    seen_sids: set[Any] = set()
    for sid, loc in all_ids:
        if sid in seen_sids:
            issues.append(ValidationIssue("error", loc, f"duplicate score or alternate id: {sid}"))
        seen_sids.add(sid)

    rec_ids = [r.get("id") for r in recs if isinstance(r, dict)]
    seen_rids: set[Any] = set()
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        loc = f"manifest/recordings/{i}"
        rid = r.get("id")
        if rid in seen_rids:
            issues.append(ValidationIssue("error", loc, f"duplicate recording id: {rid}"))
        seen_rids.add(rid)

        for k in ("syncFrom", "stemOf"):
            if k in r and r[k] not in rec_ids:
                issues.append(ValidationIssue("error", loc, f"{rid}.{k} names unknown recording {r[k]}"))
        for k in r.get("sync", {}) if isinstance(r.get("sync"), dict) else {}:
            if k not in sids:
                issues.append(ValidationIssue("error", f"{loc}/sync", f"{rid}.sync names unknown score {k}"))
        for k, v in (r.get("scoreTracks", {}) if isinstance(r.get("scoreTracks"), dict) else {}).items():
            if k not in sids:
                issues.append(ValidationIssue("error", f"{loc}/scoreTracks", f"{rid}.scoreTracks names unknown score {k}"))
            if isinstance(v, dict):
                lst = v.get("omits", v.get("only"))
                if "names" in v and isinstance(v["names"], list) and isinstance(lst, list) and len(v["names"]) != len(lst):
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{loc}/scoreTracks/{k}",
                            f"{rid}.scoreTracks.{k}: names must have one name for each index",
                        )
                    )
        for w in r.get("without", []) if isinstance(r.get("without"), list) else []:
            t = next((x for x in recs if isinstance(x, dict) and x.get("id") == w), None)
            if t is None:
                issues.append(ValidationIssue("error", loc, f"{rid}.without names unknown recording {w}"))
            elif t.get("role") != "stem":
                issues.append(ValidationIssue("error", loc, f"{rid}.without names {w}, which is not a stem"))

        sids_src = [s.get("id") for s in r.get("sources", []) if isinstance(s, dict) and "id" in s]
        for j, s in enumerate(r.get("sources", []) if isinstance(r.get("sources"), list) else []):
            if not isinstance(s, dict):
                continue
            sloc = f"{loc}/sources/{j}"
            if "derivedFrom" in s and s["derivedFrom"] not in sids_src:
                issues.append(ValidationIssue("error", sloc, f"{rid}: derivedFrom names unknown source {s['derivedFrom']}"))
            if s.get("type") == "embedded" and "score" in s and s["score"] not in sids:
                issues.append(ValidationIssue("error", sloc, f"{rid}: source names unknown score {s['score']}"))
            if s.get("type") == "url" and isinstance(s.get("url"), str) and s["url"].startswith("http://"):
                issues.append(
                    ValidationIssue("warning", sloc, f"{rid}: unencrypted http:// URL source (SPEC §12 recommends https)")
                )
    return issues


def rule_errors_sync(s: dict[str, Any], loc: str, score_format: str | None = None) -> list[ValidationIssue]:
    """Check sync file rules (strictly increasing timeMs, matching anchorType)."""
    issues: list[ValidationIssue] = []
    pts = s.get("points", [])
    if isinstance(pts, list):
        times = [p["timeMs"] for p in pts if isinstance(p, dict) and isinstance(p.get("timeMs"), (int, float))]
        if any(b <= a for a, b in zip(times, times[1:])):
            issues.append(ValidationIssue("error", loc, "timeMs not strictly increasing"))
    if score_format and ANCHOR_BY_FORMAT.get(score_format) != s.get("anchorType"):
        issues.append(
            ValidationIssue(
                "error",
                loc,
                f"anchorType {s.get('anchorType')} does not match score format {score_format}",
            )
        )
    return issues


def rule_errors_beats(b: dict[str, Any], loc: str) -> list[ValidationIssue]:
    """Check beats file rules (strictly increasing timeMs for beats & sections)."""
    issues: list[ValidationIssue] = []
    for k in ("beats", "sections"):
        arr = b.get(k, [])
        if isinstance(arr, list):
            times = [x["timeMs"] for x in arr if isinstance(x, dict) and isinstance(x.get("timeMs"), (int, float))]
            if any(y <= x for x, y in zip(times, times[1:])):
                issues.append(ValidationIssue("error", loc, f"{k}: timeMs not strictly increasing"))
    return issues


def validate_package(pkg: MpakPackage, schemas: SchemaRegistry, verify_hashes: bool = True) -> list[ValidationIssue]:
    """Run complete schema, rule, and archive validation on an MpakPackage."""
    issues: list[ValidationIssue] = []
    manifest_v = Draft202012Validator(schemas.manifest)
    sync_v = Draft202012Validator(schemas.sync)
    beats_v = Draft202012Validator(schemas.beats)

    # Archive entry name checks
    seen_lower: set[str] = set()
    for entry in pkg.list_entries():
        if entry == "mimetype":
            issues.append(ValidationIssue("error", "archive", "Archive MUST NOT contain a 'mimetype' entry (SPEC §3)"))
        err = check_entry_name(entry)
        if err:
            issues.append(ValidationIssue("error", "archive", err))
        low = entry.lower()
        if low in seen_lower:
            issues.append(ValidationIssue("error", "archive", f"Case-insensitive duplicate archive entry: {entry}"))
        seen_lower.add(low)

    # Manifest
    m = pkg.manifest
    issues.extend(schema_errors(manifest_v, m, "manifest"))
    issues.extend(rule_errors_manifest(m))

    scores = m.get("scores", []) if isinstance(m.get("scores"), list) else []
    fmt_by_id = {t["id"]: t.get("format") for t in scores if isinstance(t, dict) and "id" in t}

    # Check score files & hashes
    for i, score in enumerate(scores):
        if not isinstance(score, dict):
            continue
        for j_or_none, item, loc in [(None, score, f"manifest/scores/{i}")] + [
            (j, alt, f"manifest/scores/{i}/alternates/{j}")
            for j, alt in enumerate(score.get("alternates", []) if isinstance(score.get("alternates"), list) else [])
            if isinstance(alt, dict)
        ]:
            path = item.get("path")
            if isinstance(path, str):
                if not pkg.has_entry(path):
                    issues.append(ValidationIssue("error", loc, f"Missing score file in archive: {path}"))
                elif verify_hashes and isinstance(item.get("sha256"), str):
                    actual = pkg.entry_sha256(path)
                    if actual and actual != item["sha256"]:
                        issues.append(
                            ValidationIssue(
                                "warning",
                                loc,
                                f"Score sha256 mismatch for {path} (expected {item['sha256'][:12]}…, got {actual[:12]}…)",
                            )
                        )

    # Check recordings -> sync, beats, file sources
    recs = m.get("recordings", []) if isinstance(m.get("recordings"), list) else []
    for i, r in enumerate(recs):
        if not isinstance(r, dict):
            continue
        rid = r.get("id", f"#{i}")
        rloc = f"manifest/recordings/{i}"

        # Sync files
        sync_map = r.get("sync", {})
        if isinstance(sync_map, dict):
            for sid, rel in sync_map.items():
                sloc = f"sync/{rel}"
                if rel not in pkg.sync_files:
                    issues.append(ValidationIssue("error", f"{rloc}/sync", f"{rid}: missing sync file {rel}"))
                    continue
                sdoc = pkg.sync_files[rel]
                issues.extend(schema_errors(sync_v, sdoc, sloc))
                issues.extend(rule_errors_sync(sdoc, sloc, fmt_by_id.get(sid)))
                if sdoc.get("recording") != r.get("id"):
                    issues.append(ValidationIssue("error", sloc, f"{rel}: recording id mismatch ({sdoc.get('recording')} != {r.get('id')})"))
                if sdoc.get("score") != sid:
                    issues.append(ValidationIssue("error", sloc, f"{rel}: score id mismatch ({sdoc.get('score')} != {sid})"))

        # Beats file
        if "beats" in r and isinstance(r["beats"], str):
            rel = r["beats"]
            bloc = f"beats/{rel}"
            if rel not in pkg.beats_files:
                issues.append(ValidationIssue("error", rloc, f"{rid}: missing beats file {rel}"))
            else:
                bdoc = pkg.beats_files[rel]
                issues.extend(schema_errors(beats_v, bdoc, bloc))
                issues.extend(rule_errors_beats(bdoc, bloc))
                if bdoc.get("recording") != r.get("id"):
                    issues.append(ValidationIssue("error", bloc, f"{rel}: recording id mismatch ({bdoc.get('recording')} != {r.get('id')})"))

        # File sources
        for j, src in enumerate(r.get("sources", []) if isinstance(r.get("sources"), list) else []):
            if not isinstance(src, dict) or src.get("type") != "file":
                continue
            path = src.get("path")
            if isinstance(path, str) and not pkg.has_entry(path):
                issues.append(ValidationIssue("error", f"{rloc}/sources/{j}", f"{rid}: missing audio file {path}"))

    return issues
