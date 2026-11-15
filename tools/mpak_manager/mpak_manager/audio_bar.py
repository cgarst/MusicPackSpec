"""Native QtMultimedia audio bar for playback and Tap Sync (SPEC §10/§12)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QWidget,
)

from .archive import MpakPackage

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    HAS_MULTIMEDIA = True
except ImportError:
    HAS_MULTIMEDIA = False


class AudioBar(QWidget):
    """Bottom playback bar with recording selector."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.pkg: MpakPackage | None = None
        self._temp_audio: Path | None = None
        self._loaded_key: str | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setEnabled(False)
        self.btn_play.clicked.connect(self._toggle_play)

        self.lbl_time = QLabel("00:00.000 / 00:00.000")
        self.lbl_time.setMinimumWidth(150)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._on_seek)

        self.rec_combo = QComboBox()
        self.rec_combo.setMinimumWidth(180)
        self.rec_combo.currentIndexChanged.connect(self._on_recording_changed)

        layout.addWidget(self.btn_play)
        layout.addWidget(self.lbl_time)
        layout.addWidget(self.slider, 1)
        layout.addWidget(QLabel("Rec:"))
        layout.addWidget(self.rec_combo)

        if HAS_MULTIMEDIA:
            self.player = QMediaPlayer(self)
            self.audio_out = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_out)
            self.player.positionChanged.connect(self._on_pos_changed)
            self.player.durationChanged.connect(self._on_dur_changed)
            self.player.playbackStateChanged.connect(self._on_state_changed)
        else:
            self.player = None  # type: ignore[assignment]
            self.btn_play.setToolTip("QtMultimedia unavailable")

    def set_package(self, pkg: MpakPackage | None) -> None:
        """Populate recording selector from package manifest without loading audio."""
        self.pkg = pkg
        self._stop_and_clear()
        self.rec_combo.blockSignals(True)
        self.rec_combo.clear()
        if pkg is not None:
            for r in pkg.manifest.get("recordings", []):
                if not isinstance(r, dict):
                    continue
                rid = r.get("id", "?")
                label = r.get("label") or r.get("role", "")
                srcs = r.get("sources", [])
                playable = any(isinstance(s, dict) and s.get("type") in ("file", "url") for s in srcs)
                if playable:
                    self.rec_combo.addItem(f"{rid} ({label})" if label else rid, r)
        self.rec_combo.blockSignals(False)
        self.btn_play.setEnabled(HAS_MULTIMEDIA and self.rec_combo.count() > 0)

    def _on_recording_changed(self) -> None:
        self._stop_and_clear()
        self.btn_play.setEnabled(HAS_MULTIMEDIA and self.rec_combo.count() > 0)

    def _toggle_play(self) -> None:
        if not HAS_MULTIMEDIA or self.player is None or self.pkg is None:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return

        rec = self.rec_combo.currentData()
        if not isinstance(rec, dict):
            return
        rid = rec.get("id", "")
        if self._loaded_key != rid:
            if not self._load_recording_source(rec):
                return
            self._loaded_key = rid
        self.player.play()

    def _load_recording_source(self, rec: dict[str, Any]) -> bool:
        assert self.pkg is not None
        srcs = rec.get("sources", [])
        file_src = next((s for s in srcs if isinstance(s, dict) and s.get("type") == "file"), None)
        if file_src and isinstance(file_src.get("path"), str):
            entry = file_src["path"]
            if not self.pkg.has_entry(entry):
                QMessageBox.warning(self, "Missing Audio", f"Audio entry not found in archive: {entry}")
                return False
            suffix = Path(entry).suffix or ".audio"
            fd, tmp = tempfile.mkstemp(prefix="mpak_audio_", suffix=suffix)
            os.close(fd)
            self._cleanup_temp()
            self._temp_audio = Path(tmp)
            self.pkg.extract_entry_to_file(entry, self._temp_audio)
            self.player.setSource(QUrl.fromLocalFile(str(self._temp_audio)))
            return True

        url_src = next((s for s in srcs if isinstance(s, dict) and s.get("type") == "url"), None)
        if url_src and isinstance(url_src.get("url"), str):
            url = url_src["url"]
            if url.startswith("http://"):
                ans = QMessageBox.warning(
                    self,
                    "Unencrypted HTTP Source (SPEC §12)",
                    f"This recording uses an unencrypted http:// URL:\n{url}\n\nLoad anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return False
            self.player.setSource(QUrl(url))
            return True

        QMessageBox.information(self, "No Playable Source", "Selected recording has no file or url source.")
        return False

    def _on_seek(self, pos: int) -> None:
        if HAS_MULTIMEDIA and self.player is not None:
            self.player.setPosition(pos)

    def _on_pos_changed(self, pos: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(pos)
        dur = self.player.duration() if self.player else 0
        self.lbl_time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(dur)}")

    def _on_dur_changed(self, dur: int) -> None:
        self.slider.setRange(0, max(0, dur))
        pos = self.player.position() if self.player else 0
        self.lbl_time.setText(f"{_fmt_ms(pos)} / {_fmt_ms(dur)}")

    def _on_state_changed(self, state: Any) -> None:
        if HAS_MULTIMEDIA and state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸ Pause")
        else:
            self.btn_play.setText("▶ Play")

    def _stop_and_clear(self) -> None:
        self._loaded_key = None
        if HAS_MULTIMEDIA and self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())
        self.slider.setRange(0, 0)
        self.lbl_time.setText("00:00.000 / 00:00.000")
        self._cleanup_temp()

    def _cleanup_temp(self) -> None:
        if self._temp_audio and self._temp_audio.exists():
            try:
                self._temp_audio.unlink()
            except OSError:
                pass
        self._temp_audio = None


def _fmt_ms(ms: int) -> str:
    ms = max(0, int(ms))
    s, rem = divmod(ms, 1000)
    m, s = divmod(s, 60)
    return f"{m:02d}:{s:02d}.{rem:03d}"
