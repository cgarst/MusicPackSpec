"""Streaming .mpak archive and unpacked-directory reader/writer per SPEC §3, §11, §12."""

from __future__ import annotations

import uuid
import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from . import APP_NAME, APP_VERSION
from .validator import check_entry_name

MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_JSON_AUX_BYTES = 8 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000
MAX_INFLATE_RATIO = 100
CHUNK_SIZE = 1024 * 1024  # 1 MiB streaming chunks

TEXT_SCORE_FORMATS = {"txt", "abc", "alphatex"}


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Stream-compute lowercase hex SHA-256 of a file without loading it into RAM."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def pdf_page_count(source: bytes | Path) -> int | None:
    """Return number of pages in a PDF, or None if unreadable."""
    try:
        reader = PdfReader(io.BytesIO(source) if isinstance(source, bytes) else str(source))
        return len(reader.pages)
    except Exception:
        return None


def normalize_text_score_utf8(raw: bytes) -> bytes:
    """Ensure txt/abc/alphatex score bytes are UTF-8 (SPEC §6)."""
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        raw.decode("utf-8")
        return raw
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
        return text.encode("utf-8")


class MpakSecurityError(ValueError):
    """Raised when an archive violates SPEC §3 or §12 security limits."""


class MpakPackage:
    """In-memory editable view over a .mpak ZIP archive or unpacked directory."""

    def __init__(self) -> None:
        self.source_path: Path | None = None
        self.source_is_dir: bool = False
        self.manifest: dict[str, Any] = {
            "format": "mpak",
            "version": 1,
            "id": str(uuid.uuid4()),
            "createdAt": utc_now_iso(),
            "generator": {"name": APP_NAME, "version": APP_VERSION},
            "scores": [],
        }
        self.sync_files: dict[str, dict[str, Any]] = {}
        self.beats_files: dict[str, dict[str, Any]] = {}
        # Newly added or replaced binary/text entries: entry_name -> bytes or source Path
        self.staged_entries: dict[str, bytes | Path] = {}
        self.deleted_entries: set[str] = set()
        self._base_entries: dict[str, int] = {}  # entry_name -> uncompressed size
        self._sha256_cache: dict[str, str] = {}
        self.dirty: bool = False

    @classmethod
    def new_empty(cls) -> MpakPackage:
        """Create a new minimal MPAK package."""
        return cls()

    @classmethod
    def open(cls, path: Path) -> MpakPackage:
        """Open a .mpak file or an unpacked directory."""
        path = Path(path)
        if path.is_dir():
            return cls._open_dir(path)
        return cls._open_zip(path)

    @classmethod
    def _open_dir(cls, dir_path: Path) -> MpakPackage:
        manifest_path = dir_path / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"No manifest.json found in {dir_path}")
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise MpakSecurityError("manifest.json exceeds 1 MiB limit")

        pkg = cls()
        pkg.source_path = dir_path
        pkg.source_is_dir = True
        pkg.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        for root, _, files in os.walk(dir_path):
            for fname in files:
                full = Path(root) / fname
                rel = full.relative_to(dir_path).as_posix()
                err = check_entry_name(rel)
                if err:
                    raise MpakSecurityError(err)
                pkg._base_entries[rel] = full.stat().st_size

        pkg._load_referenced_json()
        return pkg

    @classmethod
    def _open_zip(cls, zip_path: Path) -> MpakPackage:
        pkg = cls()
        pkg.source_path = zip_path
        pkg.source_is_dir = False

        with zipfile.ZipFile(zip_path, "r") as zf:
            infos = zf.infolist()
            if len(infos) > MAX_ARCHIVE_ENTRIES:
                raise MpakSecurityError(f"Archive has {len(infos)} entries (limit {MAX_ARCHIVE_ENTRIES})")

            seen_lower: set[str] = set()
            for info in infos:
                if info.is_dir():
                    continue
                if info.flag_bits & 0x1:
                    raise MpakSecurityError(f"Encrypted entry not allowed: {info.filename}")
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise MpakSecurityError(f"Unsupported compression method for {info.filename}")
                err = check_entry_name(info.filename)
                if err:
                    raise MpakSecurityError(err)
                low = info.filename.lower()
                if low in seen_lower:
                    raise MpakSecurityError(f"Duplicate archive entry: {info.filename}")
                seen_lower.add(low)

                if not info.filename.startswith("audio/") and info.compress_size > 0:
                    if info.file_size / info.compress_size > MAX_INFLATE_RATIO:
                        raise MpakSecurityError(f"Inflation ratio exceeds {MAX_INFLATE_RATIO}x: {info.filename}")

                pkg._base_entries[info.filename] = info.file_size

            if "manifest.json" not in pkg._base_entries:
                raise MpakSecurityError("Archive missing manifest.json")
            if pkg._base_entries["manifest.json"] > MAX_MANIFEST_BYTES:
                raise MpakSecurityError("manifest.json exceeds 1 MiB limit")

            raw_manifest = _read_zip_bounded(zf, "manifest.json", MAX_MANIFEST_BYTES)
            pkg.manifest = json.loads(raw_manifest.decode("utf-8"))

            pkg._load_referenced_json(zf)
        return pkg

    def _load_referenced_json(self, zf: zipfile.ZipFile | None = None) -> None:
        """Load sync/*.json and beats/*.json referenced in manifest (or present under sync/ & beats/)."""
        sync_paths: set[str] = set()
        beats_paths: set[str] = set()
        for r in self.manifest.get("recordings", []) if isinstance(self.manifest.get("recordings"), list) else []:
            if not isinstance(r, dict):
                continue
            for rel in (r.get("sync", {}) if isinstance(r.get("sync"), dict) else {}).values():
                if isinstance(rel, str):
                    sync_paths.add(rel)
            if isinstance(r.get("beats"), str):
                beats_paths.add(r["beats"])

        for rel in self._base_entries:
            if rel.startswith("sync/") and rel.endswith(".json"):
                sync_paths.add(rel)
            elif rel.startswith("beats/") and rel.endswith(".json"):
                beats_paths.add(rel)

        for rel in sorted(sync_paths):
            if rel in self._base_entries:
                raw = self._read_raw_from_base(rel, MAX_JSON_AUX_BYTES, zf)
                self.sync_files[rel] = json.loads(raw.decode("utf-8"))

        for rel in sorted(beats_paths):
            if rel in self._base_entries:
                raw = self._read_raw_from_base(rel, MAX_JSON_AUX_BYTES, zf)
                self.beats_files[rel] = json.loads(raw.decode("utf-8"))

    def _read_raw_from_base(
        self, entry: str, max_bytes: int | None = None, zf: zipfile.ZipFile | None = None
    ) -> bytes:
        if self.source_path is None:
            raise FileNotFoundError(entry)
        if self.source_is_dir:
            target = (self.source_path / entry).resolve()
            if not str(target).startswith(str(self.source_path.resolve())):
                raise MpakSecurityError(f"Path escape: {entry}")
            if max_bytes is not None and target.stat().st_size > max_bytes:
                raise MpakSecurityError(f"Entry exceeds limit: {entry}")
            return target.read_bytes()
        if zf is not None:
            return _read_zip_bounded(zf, entry, max_bytes)
        with zipfile.ZipFile(self.source_path, "r") as z:
            return _read_zip_bounded(z, entry, max_bytes)

    def list_entries(self) -> list[str]:
        """Return sorted list of all active entry names in the archive."""
        names = set(self._base_entries.keys()) - self.deleted_entries
        names.update(self.staged_entries.keys())
        names.add("manifest.json")
        names.update(self.sync_files.keys())
        names.update(self.beats_files.keys())
        return sorted(names)

    def has_entry(self, entry: str) -> bool:
        """Check whether an entry exists in the current edited state."""
        if entry == "manifest.json" or entry in self.sync_files or entry in self.beats_files:
            return True
        if entry in self.staged_entries:
            return True
        return entry in self._base_entries and entry not in self.deleted_entries

    def entry_size(self, entry: str) -> int | None:
        """Return uncompressed byte size if known."""
        if entry in self.staged_entries:
            val = self.staged_entries[entry]
            return len(val) if isinstance(val, bytes) else val.stat().st_size
        if entry in self._base_entries and entry not in self.deleted_entries:
            return self._base_entries[entry]
        return None

    def read_entry_bytes(self, entry: str, max_bytes: int | None = None) -> bytes:
        """Read an entry's bytes (for scores, text, or small files)."""
        if entry == "manifest.json":
            return json.dumps(self.manifest, indent=2, ensure_ascii=False).encode("utf-8")
        if entry in self.sync_files:
            return json.dumps(self.sync_files[entry], indent=2, ensure_ascii=False).encode("utf-8")
        if entry in self.beats_files:
            return json.dumps(self.beats_files[entry], indent=2, ensure_ascii=False).encode("utf-8")
        if entry in self.staged_entries:
            val = self.staged_entries[entry]
            return val if isinstance(val, bytes) else val.read_bytes()
        if entry in self._base_entries and entry not in self.deleted_entries:
            return self._read_raw_from_base(entry, max_bytes)
        raise FileNotFoundError(entry)

    def extract_entry_to_file(self, entry: str, dest: Path) -> None:
        """Stream an entry to `dest` without loading large audio files into memory."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        if entry in self.staged_entries:
            val = self.staged_entries[entry]
            if isinstance(val, bytes):
                dest.write_bytes(val)
            else:
                shutil.copyfile(val, dest)
            return
        if entry in ("manifest.json",) or entry in self.sync_files or entry in self.beats_files:
            dest.write_bytes(self.read_entry_bytes(entry))
            return
        if self.source_is_dir and self.source_path is not None:
            shutil.copyfile(self.source_path / entry, dest)
            return
        if self.source_path is not None:
            with zipfile.ZipFile(self.source_path, "r") as zf:
                with zf.open(entry, "r") as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst, CHUNK_SIZE)
            return
        raise FileNotFoundError(entry)

    def entry_sha256(self, entry: str) -> str | None:
        """Compute (and cache) lowercase SHA-256 of an entry using streaming."""
        if entry in self._sha256_cache:
            return self._sha256_cache[entry]
        if not self.has_entry(entry):
            return None
        if entry in self.staged_entries:
            val = self.staged_entries[entry]
            digest = sha256_bytes(val) if isinstance(val, bytes) else sha256_file(val)
        elif entry in ("manifest.json",) or entry in self.sync_files or entry in self.beats_files:
            digest = sha256_bytes(self.read_entry_bytes(entry))
        elif self.source_is_dir and self.source_path is not None:
            digest = sha256_file(self.source_path / entry)
        elif self.source_path is not None:
            h = hashlib.sha256()
            with zipfile.ZipFile(self.source_path, "r") as zf:
                with zf.open(entry, "r") as src:
                    while chunk := src.read(CHUNK_SIZE):
                        h.update(chunk)
            digest = h.hexdigest()
        else:
            return None
        self._sha256_cache[entry] = digest
        return digest

    def stage_file(self, entry: str, data_or_path: bytes | Path) -> None:
        """Add or replace an entry in the package."""
        err = check_entry_name(entry)
        if err:
            raise MpakSecurityError(err)
        self.deleted_entries.discard(entry)
        self.staged_entries[entry] = data_or_path
        self._sha256_cache.pop(entry, None)
        self.dirty = True

    def delete_entry(self, entry: str) -> None:
        """Mark an entry for deletion on save."""
        self.staged_entries.pop(entry, None)
        self.sync_files.pop(entry, None)
        self.beats_files.pop(entry, None)
        if entry in self._base_entries:
            self.deleted_entries.add(entry)
        self._sha256_cache.pop(entry, None)
        self.dirty = True

    def save_mpak(self, dest_path: Path, update_generator: bool = True) -> None:
        """Write the package atomically to `dest_path` as a ZIP64 .mpak archive."""
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if update_generator:
            self.manifest["generator"] = {"name": APP_NAME, "version": APP_VERSION}

        fd, tmp_name = tempfile.mkstemp(prefix=".mpak_save_", suffix=".tmp", dir=str(dest_path.parent))
        os.close(fd)
        tmp_path = Path(tmp_name)
        self._write_zip_atomic(dest_path, tmp_path)

    def _write_zip_atomic(self, dest_path: Path, tmp_path: Path) -> None:
        src_zf = (
            zipfile.ZipFile(self.source_path, "r")
            if self.source_path is not None and not self.source_is_dir
            else None
        )
        try:
            with zipfile.ZipFile(tmp_path, "w", allowZip64=True) as out_zf:
                for entry in self.list_entries():
                    compress = zipfile.ZIP_STORED if entry.startswith("audio/") else zipfile.ZIP_DEFLATED
                    if entry in ("manifest.json",) or entry in self.sync_files or entry in self.beats_files:
                        out_zf.writestr(entry, self.read_entry_bytes(entry), compress_type=zipfile.ZIP_DEFLATED)
                    elif entry in self.staged_entries:
                        val = self.staged_entries[entry]
                        if isinstance(val, bytes):
                            out_zf.writestr(entry, val, compress_type=compress)
                        else:
                            out_zf.write(val, arcname=entry, compress_type=compress)
                    elif self.source_is_dir and self.source_path is not None:
                        out_zf.write(self.source_path / entry, arcname=entry, compress_type=compress)
                    elif src_zf is not None:
                        info = zipfile.ZipInfo(entry)
                        info.compress_type = compress
                        with src_zf.open(entry, "r") as r_stream, out_zf.open(info, mode="w") as w_stream:
                            shutil.copyfileobj(r_stream, w_stream, CHUNK_SIZE)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        finally:
            if src_zf is not None:
                src_zf.close()

        os.replace(tmp_path, dest_path)
        # Rebind package to the newly written archive
        self.source_path = dest_path
        self.source_is_dir = False
        self.staged_entries.clear()
        self.deleted_entries.clear()
        self._base_entries.clear()
        with zipfile.ZipFile(dest_path, "r") as zf:
            for info in zf.infolist():
                if not info.is_dir():
                    self._base_entries[info.filename] = info.file_size
        self.dirty = False

    def export_directory(self, dest_dir: Path, update_generator: bool = True) -> None:
        """Unpack/write the current package state into `dest_dir`."""
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        if update_generator:
            self.manifest["generator"] = {"name": APP_NAME, "version": APP_VERSION}
        for entry in self.list_entries():
            target = (dest_dir / entry).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise MpakSecurityError(f"Path escape: {entry}")
            self.extract_entry_to_file(entry, target)


def _read_zip_bounded(zf: zipfile.ZipFile, entry: str, max_bytes: int | None) -> bytes:
    info = zf.getinfo(entry)
    if max_bytes is not None and info.file_size > max_bytes:
        raise MpakSecurityError(f"Entry {entry} exceeds max size ({info.file_size} > {max_bytes})")
    out = bytearray()
    with zf.open(info, "r") as f:
        while chunk := f.read(65536):
            out.extend(chunk)
            if max_bytes is not None and len(out) > max_bytes:
                raise MpakSecurityError(f"Entry {entry} inflated past max size ({max_bytes})")
    return bytes(out)
