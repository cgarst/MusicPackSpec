"""Main window for MPAK Manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from . import APP_NAME, APP_VERSION
from .archive import MpakPackage
from .audio_bar import AudioBar
from .schema_form import NodeEditorWidget
from .schema_tree import PackTreeWidget, _fmt_bytes
from .schema_utils import SchemaRegistry
from .validator import ValidationIssue, validate_package


class MainWindow(QMainWindow):
    """Three-pane native Qt desktop window for MPAK Manager."""

    def __init__(self, initial_path: Path | None = None, parent: Any = None) -> None:
        super().__init__(parent)
        self.schemas = SchemaRegistry()
        self.pkg: MpakPackage | None = None

        self.resize(1280, 800)
        self._build_ui()
        self._build_menus_and_toolbar()

        if initial_path is not None:
            self.open_path(initial_path)
        else:
            self._load_package(None)

    def _build_ui(self) -> None:
        central = QWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = PackTreeWidget(self.schemas)
        self.editor = NodeEditorWidget()

        # Right panel: validation & summary
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        self.lbl_val_summary = QLabel("<b>Validation</b>")
        self.issues_list = QListWidget()
        self.issues_list.itemDoubleClicked.connect(self._on_issue_activated)
        self.lbl_arch_summary = QLabel()
        self.lbl_arch_summary.setWordWrap(True)

        right_layout.addWidget(self.lbl_val_summary)
        right_layout.addWidget(self.issues_list, 1)
        right_layout.addWidget(QLabel("<b>Archive Summary</b>"))
        right_layout.addWidget(self.lbl_arch_summary)

        self.splitter.addWidget(self.tree)
        self.splitter.addWidget(self.editor)
        self.splitter.addWidget(right_panel)
        self.splitter.setSizes([280, 680, 300])

        self.audio_bar = AudioBar()

        root_layout.addWidget(self.splitter, 1)
        root_layout.addWidget(self.audio_bar)
        self.setCentralWidget(central)

        # Signals
        self.tree.nodeSelected.connect(lambda ref: self.editor.set_node(self.pkg, ref))
        self.tree.packageMutated.connect(self._on_package_mutated)
        self.editor.dataChanged.connect(self._on_editor_changed)

    def _build_menus_and_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_new = QAction("New", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self.action_new)

        act_open = QAction("Open .mpak…", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.action_open_file)

        act_open_dir = QAction("Open Dir…", self)
        act_open_dir.triggered.connect(self.action_open_dir)

        self.act_save = QAction("Save", self)
        self.act_save.setShortcut(QKeySequence.StandardKey.Save)
        self.act_save.triggered.connect(self.action_save)

        self.act_save_as = QAction("Save As…", self)
        self.act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.act_save_as.triggered.connect(self.action_save_as)

        self.act_unpack = QAction("Unpack…", self)
        self.act_unpack.triggered.connect(self.action_unpack)

        self.act_validate = QAction("Validate", self)
        self.act_validate.triggered.connect(self.run_validation)

        for a in (act_new, act_open, act_open_dir, self.act_save, self.act_save_as, self.act_unpack, self.act_validate):
            tb.addAction(a)

        tb.addSeparator()
        self.lbl_status_badge = QLabel("  No file open  ")
        tb.addWidget(self.lbl_status_badge)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(act_new)
        file_menu.addAction(act_open)
        file_menu.addAction(act_open_dir)
        file_menu.addSeparator()
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addAction(self.act_unpack)
        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        pack_menu = self.menuBar().addMenu("&Pack")
        pack_menu.addAction(self.act_validate)

        help_menu = self.menuBar().addMenu("&Help")
        act_about = QAction(f"About {APP_NAME}", self)
        act_about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                f"About {APP_NAME}",
                f"{APP_NAME} v{APP_VERSION}\nNative Qt6 / Python tool for Music Pack (.mpak) v1 archives.",
            )
        )
        help_menu.addAction(act_about)

    def _confirm_discard(self) -> bool:
        if self.pkg is None or not self.pkg.dirty:
            return True
        ans = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Current package has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return ans == QMessageBox.StandardButton.Discard

    def action_new(self) -> None:
        if not self._confirm_discard():
            return
        self._load_package(MpakPackage.new_empty())

    def action_open_file(self) -> None:
        if not self._confirm_discard():
            return
        path_str, _ = QFileDialog.getOpenFileName(self, "Open .mpak File", "", "Music Pack (*.mpak);;All Files (*)")
        if path_str:
            self.open_path(Path(path_str))

    def action_open_dir(self) -> None:
        if not self._confirm_discard():
            return
        dir_str = QFileDialog.getExistingDirectory(self, "Open Unpacked .mpak Directory")
        if dir_str:
            self.open_path(Path(dir_str))

    def open_path(self, path: Path) -> None:
        try:
            pkg = MpakPackage.open(path)
        except Exception as exc:
            QMessageBox.critical(self, "Failed to Open Package", str(exc))
            return
        self._load_package(pkg)

    def action_save(self) -> None:
        if self.pkg is None:
            return
        if self.pkg.source_path is None or self.pkg.source_is_dir:
            self.action_save_as()
            return
        try:
            self.pkg.save_mpak(self.pkg.source_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return
        self._update_title()
        self.run_validation()

    def action_save_as(self) -> None:
        if self.pkg is None:
            return
        default_name = (self.pkg.source_path.stem if self.pkg.source_path else "song") + ".mpak"
        path_str, _ = QFileDialog.getSaveFileName(self, "Save .mpak As", default_name, "Music Pack (*.mpak)")
        if not path_str:
            return
        dest = Path(path_str)
        if dest.suffix.lower() != ".mpak":
            dest = dest.with_suffix(".mpak")
        try:
            self.pkg.save_mpak(dest)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return
        self._load_package(self.pkg)

    def action_unpack(self) -> None:
        if self.pkg is None:
            return
        dir_str = QFileDialog.getExistingDirectory(self, "Select Empty Output Directory")
        if not dir_str:
            return
        try:
            self.pkg.export_directory(Path(dir_str))
        except Exception as exc:
            QMessageBox.critical(self, "Unpack Failed", str(exc))
            return
        QMessageBox.information(self, "Unpacked", f"Exported package to:\n{dir_str}")

    def _load_package(self, pkg: MpakPackage | None) -> None:
        self.pkg = pkg
        has_pkg = pkg is not None
        for act in (self.act_save, self.act_save_as, self.act_unpack, self.act_validate):
            act.setEnabled(has_pkg)
        self.tree.set_package(pkg, preserve_location="manifest" if has_pkg else None)
        if not has_pkg:
            self.editor.set_node(None, None)
        self.audio_bar.set_package(pkg)
        self._update_title()
        self.run_validation()

    def _on_package_mutated(self) -> None:
        self.audio_bar.set_package(self.pkg)
        self._update_title()
        self.run_validation()

    def _on_editor_changed(self, location: str) -> None:
        self.tree.set_package(self.pkg, preserve_location=location)
        self.audio_bar.set_package(self.pkg)
        self._update_title()
        self.run_validation()

    def run_validation(self) -> None:
        self.issues_list.clear()
        if self.pkg is None:
            self.lbl_val_summary.setText("<b>Validation:</b> No file open")
            self.lbl_status_badge.setText("  No file open  ")
            self.lbl_status_badge.setStyleSheet("")
            self.lbl_arch_summary.setText("Open a .mpak file, open an unpacked directory, or click New.")
            return

        issues = validate_package(self.pkg, self.schemas, verify_hashes=True)
        errs = sum(1 for i in issues if i.severity == "error")
        warns = sum(1 for i in issues if i.severity == "warning")

        for issue in issues:
            prefix = "✗" if issue.severity == "error" else "⚠"
            item = QListWidgetItem(f"{prefix} [{issue.location}] {issue.message}")
            item.setData(Qt.ItemDataRole.UserRole, issue)
            item.setForeground(QColor("#c62828") if issue.severity == "error" else QColor("#ef6c00"))
            self.issues_list.addItem(item)

        self.lbl_val_summary.setText(f"<b>Validation:</b> {errs} error(s), {warns} warning(s)")
        if errs > 0:
            self.lbl_status_badge.setText(f"  ✗ {errs} Error(s)  ")
            self.lbl_status_badge.setStyleSheet("color: #c62828; font-weight: bold;")
        elif warns > 0:
            self.lbl_status_badge.setText(f"  ⚠ {warns} Warning(s)  ")
            self.lbl_status_badge.setStyleSheet("color: #ef6c00; font-weight: bold;")
        else:
            self.lbl_status_badge.setText("  ✓ Valid  ")
            self.lbl_status_badge.setStyleSheet("color: #2e7d32; font-weight: bold;")

        entries = self.pkg.list_entries()
        total_bytes = sum(self.pkg.entry_size(e) or 0 for e in entries)
        src_desc = str(self.pkg.source_path) if self.pkg.source_path else "(unsaved new pack)"
        self.lbl_arch_summary.setText(
            f"Source: {src_desc}<br>"
            f"Entries: {len(entries)}<br>"
            f"Uncompressed size: {_fmt_bytes(total_bytes)}"
        )

    def _on_issue_activated(self, item: QListWidgetItem) -> None:
        issue = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(issue, ValidationIssue):
            self.tree.select_location(issue.location)

    def _update_title(self) -> None:
        if self.pkg is None:
            self.setWindowTitle(APP_NAME)
            return
        name = self.pkg.source_path.name if self.pkg.source_path else "Untitled"
        dirty = " *" if self.pkg.dirty else ""
        self.setWindowTitle(f"{name}{dirty} — {APP_NAME}")

    def closeEvent(self, event: Any) -> None:
        if self._confirm_discard():
            self.audio_bar._stop_and_clear()
            event.accept()
        else:
            event.ignore()
