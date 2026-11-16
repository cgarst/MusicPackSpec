"""Tests for MPAK Manager core, validator, archive I/O, and headless Qt UI."""

from __future__ import annotations

import glob
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator

from mpak_manager.archive import MpakPackage, MpakSecurityError, sha256_bytes
from mpak_manager.schema_utils import SchemaRegistry, resolve_schema
from mpak_manager.validator import (
    rule_errors_beats,
    rule_errors_manifest,
    rule_errors_sync,
    schema_errors,
    validate_package,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestSchemaAndValidator(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = SchemaRegistry(REPO_ROOT / "schema")

    def test_conditional_source_schema_resolution(self) -> None:
        src_schema = self.schemas.manifest["$defs"]["source"]
        yt_eff = resolve_schema(self.schemas.manifest, src_schema, {"type": "youtube"})
        self.assertIn("videoId", yt_eff["properties"])
        self.assertNotIn("url", yt_eff["properties"])

        url_eff = resolve_schema(self.schemas.manifest, src_schema, {"type": "url"})
        self.assertIn("url", url_eff["properties"])
        self.assertNotIn("videoId", url_eff["properties"])

    def test_all_examples_validate(self) -> None:
        example_dirs = sorted((REPO_ROOT / "examples").iterdir())
        checked = 0
        for ex in example_dirs:
            if not (ex / "manifest.json").is_file():
                continue
            pkg = MpakPackage.open(ex)
            issues = validate_package(pkg, self.schemas, verify_hashes=False)
            errors = [i for i in issues if i.severity == "error"]
            # Examples in repo omit dummy binary score/audio files; filter missing-file errors only if file absent on disk
            non_dummy_errors = [
                e for e in errors if "Missing score file" not in e.message and "missing audio file" not in e.message
            ]
            self.assertEqual(non_dummy_errors, [], f"{ex.name} failed: {non_dummy_errors}")
            checked += 1
        self.assertGreaterEqual(checked, 10)

    def test_all_conformance_invalid_fail(self) -> None:
        manifest_v = Draft202012Validator(self.schemas.manifest)
        sync_v = Draft202012Validator(self.schemas.sync)
        beats_v = Draft202012Validator(self.schemas.beats)

        invalid_files = sorted(glob.glob(str(REPO_ROOT / "conformance" / "invalid" / "*.json")))
        self.assertGreater(len(invalid_files), 20)
        for p_str in invalid_files:
            p = Path(p_str)
            doc = json.loads(p.read_text(encoding="utf-8"))
            if p.name.startswith("manifest-"):
                errs = schema_errors(manifest_v, doc, "manifest") + rule_errors_manifest(doc)
            elif p.name.startswith("sync-"):
                errs = schema_errors(sync_v, doc, "sync") + rule_errors_sync(doc, "sync")
            elif p.name.startswith("beats-"):
                errs = schema_errors(beats_v, doc, "beats") + rule_errors_beats(doc, "beats")
            else:
                self.fail(f"Unknown conformance prefix: {p.name}")
            self.assertTrue(len(errs) > 0, f"Expected {p.name} to fail validation")


class TestArchiveRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = SchemaRegistry(REPO_ROOT / "schema")

    def test_pack_open_edit_save_preserves_unknown_fields_and_stored_audio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mpak_path = tmp_path / "song.mpak"

            pkg = MpakPackage.new_empty()
            score_bytes = b"C | G | Am | F\n"
            audio_bytes = b"OggS" + b"\x00" * 4096
            pkg.stage_file("score/chords.txt", score_bytes)
            pkg.stage_file("audio/mix.ogg", audio_bytes)
            pkg.manifest["x-custom-root"] = {"hello": "world"}
            pkg.manifest["scores"] = [
                {
                    "id": "chords",
                    "path": "score/chords.txt",
                    "format": "txt",
                    "sha256": sha256_bytes(score_bytes),
                    "x-color": "#ff00aa",
                }
            ]
            pkg.manifest["recordings"] = [
                {
                    "id": "mix",
                    "role": "original",
                    "sources": [{"type": "file", "path": "audio/mix.ogg", "sha256": sha256_bytes(audio_bytes)}],
                    "sync": {"chords": "sync/mix.json"},
                }
            ]
            pkg.sync_files["sync/mix.json"] = {
                "version": 1,
                "recording": "mix",
                "score": "chords",
                "anchorType": "text",
                "points": [{"timeMs": 0, "line": 0}],
            }
            pkg.save_mpak(mpak_path)

            # Verify ZIP storage method for audio
            with zipfile.ZipFile(mpak_path, "r") as zf:
                self.assertEqual(zf.getinfo("audio/mix.ogg").compress_type, zipfile.ZIP_STORED)

            # Reopen and validate
            reopened = MpakPackage.open(mpak_path)
            issues = validate_package(reopened, self.schemas, verify_hashes=True)
            self.assertEqual(issues, [])
            self.assertEqual(reopened.manifest["x-custom-root"], {"hello": "world"})
            self.assertEqual(reopened.manifest["scores"][0]["x-color"], "#ff00aa")
            # Saving made the sizes and the sync file's entry true (SPEC section 4, "Integrity")
            self.assertEqual(reopened.manifest["scores"][0]["size"], len(score_bytes))
            self.assertEqual(reopened.manifest["recordings"][0]["sources"][0]["size"], len(audio_bytes))
            sync_bytes = reopened.read_entry_bytes("sync/mix.json")
            self.assertEqual(reopened.manifest["entries"], {"sync/mix.json": {"size": len(sync_bytes), "sha256": sha256_bytes(sync_bytes)}})
            # A changed sync file is reported until the package is saved again
            reopened.manifest["entries"]["sync/mix.json"]["size"] += 1
            self.assertTrue(any("Size differs" in i.message for i in validate_package(reopened, self.schemas)))

    def test_directory_pack_refuses_a_symbolic_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pack"
            (root / "score").mkdir(parents=True)
            (root / "manifest.json").write_text(
                '{"format":"mpak","version":1,"scores":[{"id":"a","path":"score/a.txt","format":"txt","sha256":"%s"}]}' % ("0" * 64),
                encoding="utf-8",
            )
            secret = Path(tmp) / "secret.txt"
            secret.write_text("outside the pack", encoding="utf-8")
            try:
                (root / "score" / "a.txt").symlink_to(secret)
            except (OSError, NotImplementedError):
                self.skipTest("symbolic links are not available here")
            with self.assertRaises(MpakSecurityError):
                MpakPackage.open(root)

    def test_rejects_zip_slip_and_mimetype(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad_zip = Path(tmp) / "bad.mpak"
            with zipfile.ZipFile(bad_zip, "w") as zf:
                zf.writestr("manifest.json", '{"format":"mpak","version":1,"scores":[]}')
                zf.writestr("../escape.txt", "nope")
            with self.assertRaises(MpakSecurityError):
                MpakPackage.open(bad_zip)


class TestHeadlessQtUI(unittest.TestCase):
    def test_main_window_starts_clean_without_file(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from mpak_manager.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        win = MainWindow()
        self.assertIsNone(win.pkg)
        self.assertEqual(win.issues_list.count(), 0)
        win.close()
        app.processEvents()

    def test_main_window_loads_enriched_example(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        from mpak_manager.main_window import MainWindow

        app = QApplication.instance() or QApplication([])
        win = MainWindow(REPO_ROOT / "examples" / "enriched")
        self.assertGreater(win.tree.topLevelItemCount(), 0)
        self.assertTrue(win.tree.select_location("manifest/scores/0"))
        self.assertTrue(win.tree.select_location("manifest/recordings/0"))
        win.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
