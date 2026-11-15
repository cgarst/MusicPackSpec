# MPAK Manager

Cross-platform native desktop GUI (Windows, macOS, Linux) for reading, inspecting, validating, and editing Music Pack (`.mpak`) archives per [SPEC.md](../../SPEC.md). Built with **Python** and **PySide6 (Qt 6)** — no Electron, no webviews.

## Features

- **Schema-driven tree & property forms:** Reads `schema/manifest.schema.json`, `schema/sync.schema.json`, and `schema/beats.schema.json` at runtime so schema additions appear automatically.
- **Full MPAK v1 validation:** Validates JSON Schemas, spec rules (`tools/check.py` parity), archive security limits (SPEC §3 & §12), and `sha256` checksums.
- **Spec §11 guardrails:** Auto-computes `sha256` and PDF `pages` on score import/replacement, normalizes `txt`/`abc`/`alphatex` to UTF-8, updates `sync.updatedAt` and `generator`, and prompts for structural/track-link decisions when replacing a score.
- **Preserves extensions:** Unknown and `x-*` fields and extra archive entries are preserved verbatim on round-trip.
- **Native media:** Built-in `QtMultimedia` audio playback for recordings, plus native `QtPdf` / text score preview.

## Run

```bash
cd tools/mpak_manager
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
mpak-manager                # or: python -m mpak_manager [path/to/song.mpak]
```

## Test

```bash
PYTHONPATH=tools/mpak_manager QT_QPA_PLATFORM=offscreen tools/mpak_manager/.venv/bin/python -m unittest discover -s tools/mpak_manager/tests -v
```
