"""Spec-enforced interactive dialogs (SPEC §11 Changing a Score, ID rename cascades)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
)


@dataclass
class ScoreReplacePlan:
    """User's explicit SPEC §11 decisions when replacing an existing score file."""

    keep_sync: bool = True
    alternates_action: str = "keep"  # "keep" | "promote" | "remove"
    keep_track_links: bool = True


class ScoreReplaceDialog(QDialog):
    """Prompts the user for SPEC §11 decisions when a score's bytes/sha256 change."""

    def __init__(
        self,
        score_id: str,
        has_sync: bool,
        has_alternates: bool,
        has_track_links: bool,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Replace Score '{score_id}' (SPEC §11)")
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)

        intro = QLabel(
            f"You are replacing score <b>{score_id}</b>, which updates its <code>sha256</code>.<br>"
            "Per SPEC §11, confirm whether the score's structure is unchanged or clear dependent data:"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.chk_keep_sync: QCheckBox | None = None
        if has_sync:
            self.chk_keep_sync = QCheckBox(
                "Structure unchanged (same bars/pages/lines) — keep existing sync points"
            )
            self.chk_keep_sync.setChecked(True)
            layout.addWidget(self.chk_keep_sync)

        self.alt_keep: QRadioButton | None = None
        self.alt_promote: QRadioButton | None = None
        self.alt_remove: QRadioButton | None = None
        if has_alternates:
            layout.addWidget(QLabel("<b>Alternates</b> (SPEC §11.3):"))
            self.alt_keep = QRadioButton("Alternates still line up with the new primary score (keep)")
            self.alt_promote = QRadioButton("Promote alternates to standalone scores")
            self.alt_remove = QRadioButton("Remove alternates")
            self.alt_keep.setChecked(True)
            layout.addWidget(self.alt_keep)
            layout.addWidget(self.alt_promote)
            layout.addWidget(self.alt_remove)

        self.chk_keep_tracks: QCheckBox | None = None
        if has_track_links:
            self.chk_keep_tracks = QCheckBox(
                "Track order unchanged — keep stem.track and scoreTracks links"
            )
            self.chk_keep_tracks.setChecked(True)
            layout.addWidget(self.chk_keep_tracks)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def plan(self) -> ScoreReplacePlan:
        alt = "keep"
        if self.alt_promote and self.alt_promote.isChecked():
            alt = "promote"
        elif self.alt_remove and self.alt_remove.isChecked():
            alt = "remove"
        return ScoreReplacePlan(
            keep_sync=self.chk_keep_sync.isChecked() if self.chk_keep_sync else True,
            alternates_action=alt,
            keep_track_links=self.chk_keep_tracks.isChecked() if self.chk_keep_tracks else True,
        )
