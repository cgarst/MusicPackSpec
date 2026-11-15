"""Dynamic schema-driven property editor, sync/beats table, raw JSON editor, and native preview."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .archive import (
    TEXT_SCORE_FORMATS,
    MpakPackage,
    normalize_text_score_utf8,
    pdf_page_count,
    sha256_bytes,
    sha256_file,
    utc_now_iso,
)
from .schema_tree import TreeNodeRef
from .schema_utils import ANCHOR_BY_FORMAT, default_value_for_schema, resolve_schema
from .spec_dialogs import ScoreReplaceDialog

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    HAS_QT_PDF = True
except ImportError:
    HAS_QT_PDF = False


class NodeEditorWidget(QTabWidget):
    """Center workspace: dynamic schema form, sync/beats table, raw JSON, and native preview."""

    dataChanged = Signal(str)  # emits location to refresh/preserve

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.pkg: MpakPackage | None = None
        self.ref: TreeNodeRef | None = None
        self._active_table: QTableWidget | None = None
        self._active_table_kind: str | None = None  # "points" | "beats" | "sections"
        self._pdf_temp: Path | None = None

        self.form_scroll = QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_container = QWidget()
        self.form_scroll.setWidget(self.form_container)

        self.raw_edit = QPlainTextEdit()
        self.raw_apply_btn = QPushButton("Apply Raw JSON")
        self.raw_apply_btn.clicked.connect(self._apply_raw_json)
        raw_page = QWidget()
        raw_layout = QVBoxLayout(raw_page)
        raw_layout.addWidget(self.raw_edit)
        raw_layout.addWidget(self.raw_apply_btn)

        self.preview_page = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_page)

        self.addTab(self.form_scroll, "Editor")
        self.addTab(raw_page, "Raw JSON")
        self.addTab(self.preview_page, "Preview / File")

    def set_node(self, pkg: MpakPackage | None, ref: TreeNodeRef | None) -> None:
        """Render editor tabs for the selected tree node."""
        self.pkg = pkg
        self.ref = ref
        self._active_table = None
        self._active_table_kind = None

        self.form_container = QWidget()
        self.form_scroll.setWidget(self.form_container)
        self._clear_layout_items(self.preview_layout)
        self.raw_edit.clear()

        if pkg is None or ref is None:
            return

        if ref.kind in ("sync_root", "beats_root", "archive_root"):
            self._build_info_banner(ref)
            return

        if ref.kind == "archive_entry":
            self._build_archive_entry_view(ref.doc_key)
            return

        doc = self._get_doc(ref.doc_key)
        val = self._get_at_path(doc, ref.json_path)

        # Populate Raw JSON tab
        self.raw_edit.setPlainText(json.dumps(val, indent=2, ensure_ascii=False) if val is not None else "null")

        # Build dynamic schema form
        self._build_dynamic_form(ref, doc, val)
        self._build_preview_for_node(ref, val)

    def _build_info_banner(self, ref: TreeNodeRef) -> None:
        layout = QVBoxLayout(self.form_container)
        msg = {
            "sync_root": "Right-click 'Sync Files' in the tree to create a new sync/*.json file.",
            "beats_root": "Right-click 'Beats Files' in the tree to create a new beats/*.json file.",
            "archive_root": "Select any archive entry below to inspect, extract, or replace it.",
        }.get(ref.kind, "")
        lbl = QLabel(msg)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        if ref.kind == "archive_root" and self.pkg is not None:
            btn = QPushButton("+ Import File into Archive…")
            btn.clicked.connect(self._import_arbitrary_archive_file)
            layout.addWidget(btn)
        layout.addStretch(1)

    def _build_archive_entry_view(self, entry: str) -> None:
        assert self.pkg is not None
        layout = QVBoxLayout(self.form_container)
        sz = self.pkg.entry_size(entry)
        layout.addWidget(QLabel(f"<b>Archive Entry:</b> <code>{entry}</code>"))
        layout.addWidget(QLabel(f"<b>Size:</b> {sz if sz is not None else '?'} bytes"))

        btn_row = QHBoxLayout()
        btn_extract = QPushButton("Extract To…")
        btn_extract.clicked.connect(lambda: self._extract_entry(entry))
        btn_row.addWidget(btn_extract)
        if entry != "manifest.json":
            btn_replace = QPushButton("Replace File…")
            btn_replace.clicked.connect(lambda: self._replace_arbitrary_entry(entry))
            btn_row.addWidget(btn_replace)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)
        layout.addStretch(1)

        self._populate_file_preview(entry)

    def _build_dynamic_form(self, ref: TreeNodeRef, doc: Any, val: Any) -> None:
        assert self.pkg is not None
        outer = QVBoxLayout(self.form_container)

        # Header
        loc_lbl = QLabel(f"<b>{ref.location}</b>")
        outer.addWidget(loc_lbl)

        # Unset optional object
        if val is None and ref.json_path:
            eff_unset = resolve_schema(ref.root_schema, ref.sub_schema)
            if eff_unset.get("type") == "object" or "properties" in eff_unset:
                btn_init = QPushButton(f"+ Initialize '{ref.json_path[-1]}'")
                btn_init.clicked.connect(lambda: self._init_optional_object(ref))
                outer.addWidget(btn_init)
                outer.addStretch(1)
                return

        eff = resolve_schema(ref.root_schema, ref.sub_schema, val)

        # Array node (e.g., points, beats, sections, or array of objects)
        if isinstance(val, list) or eff.get("type") == "array":
            arr = val if isinstance(val, list) else []
            item_schema = eff.get("items", {})
            item_eff = resolve_schema(ref.root_schema, item_schema, arr[0] if arr else None)
            if item_eff.get("type") == "object" or "properties" in item_eff:
                self._build_object_array_table(outer, ref, doc, arr, item_schema)
            else:
                self._build_primitive_list_editor(outer, ref, doc, arr, item_eff)
            return

        if not isinstance(val, dict):
            outer.addWidget(QLabel(f"Value: {val!r}"))
            outer.addStretch(1)
            return

        # Domain helper actions for Score / Recording / Source
        self._add_domain_action_bar(outer, ref, val)

        # Dynamic QFormLayout from resolved schema properties
        form = QFormLayout()
        props = eff.get("properties", {})
        required = set(eff.get("required", []))

        for key, prop_schema in props.items():
            prop_val = val.get(key)
            prop_eff = resolve_schema(ref.root_schema, prop_schema, prop_val)
            prop_type = prop_eff.get("type")

            # Nested objects / object-arrays / maps are edited via their tree child node
            if prop_type == "object" or "properties" in prop_eff or isinstance(prop_eff.get("additionalProperties"), dict):
                summary = f"{len(prop_val)} keys" if isinstance(prop_val, dict) else "unset"
                lbl = QLabel(f"<i>({summary} — select child in tree)</i>")
                form.addRow(self._field_label(key, key in required, prop_eff), lbl)
                continue
            if prop_type == "array":
                items_eff = resolve_schema(ref.root_schema, prop_eff.get("items", {}))
                if items_eff.get("type") == "object" or "properties" in items_eff:
                    count = len(prop_val) if isinstance(prop_val, list) else 0
                    lbl = QLabel(f"<i>({count} items — select '{key}' in tree)</i>")
                    form.addRow(self._field_label(key, key in required, prop_eff), lbl)
                    continue

            widget = self._make_scalar_widget(ref, doc, val, key, prop_val, prop_eff)
            form.addRow(self._field_label(key, key in required, prop_eff), widget)

        # Unknown / x-* scalar fields preserved in data
        extra_keys = [k for k in val.keys() if k not in props and not isinstance(val[k], (dict, list))]
        if extra_keys:
            form.addRow(QLabel("<b>Extra / Extension Fields</b>"), QLabel(""))
            for key in extra_keys:
                edit = QLineEdit(str(val[key]))
                edit.editingFinished.connect(lambda k=key, e=edit: self._set_scalar(ref, doc, val, k, e.text()))
                form.addRow(QLabel(key), edit)

        outer.addLayout(form)
        outer.addStretch(1)

    def _add_domain_action_bar(self, outer: QVBoxLayout, ref: TreeNodeRef, val: dict[str, Any]) -> None:
        """Add convenient spec-aware file import buttons where applicable."""
        if ref.kind == "manifest_node" and len(ref.json_path) in (2, 4) and ref.json_path[0] == "scores":
            is_score = len(ref.json_path) == 2 or (len(ref.json_path) == 4 and ref.json_path[2] == "alternates")
            if is_score:
                bar = QHBoxLayout()
                btn_import = QPushButton("Import / Replace Score File…")
                btn_import.clicked.connect(lambda: self._import_score_file(ref, val))
                bar.addWidget(btn_import)
                bar.addStretch(1)
                outer.addLayout(bar)

        if ref.kind == "manifest_node" and len(ref.json_path) == 4 and ref.json_path[0] == "recordings" and ref.json_path[2] == "sources":
            if val.get("type") == "file":
                bar = QHBoxLayout()
                btn_audio = QPushButton("Import Audio File…")
                btn_audio.clicked.connect(lambda: self._import_audio_source(ref, val))
                bar.addWidget(btn_audio)
                bar.addStretch(1)
                outer.addLayout(bar)

    def _make_scalar_widget(
        self,
        ref: TreeNodeRef,
        doc: Any,
        obj: dict[str, Any],
        key: str,
        cur_val: Any,
        prop_eff: dict[str, Any],
    ) -> QWidget:
        if "const" in prop_eff:
            lbl = QLineEdit(str(prop_eff["const"]))
            lbl.setReadOnly(True)
            return lbl

        if "enum" in prop_eff:
            combo = QComboBox()
            combo.addItem("<unset>", None)
            for opt in prop_eff["enum"]:
                combo.addItem(str(opt), opt)
            if cur_val in prop_eff["enum"]:
                combo.setCurrentIndex(prop_eff["enum"].index(cur_val) + 1)
            combo.currentIndexChanged.connect(
                lambda _idx, c=combo, k=key: self._on_enum_changed(ref, doc, obj, k, c.currentData())
            )
            return combo

        typ = prop_eff.get("type")
        if typ == "boolean":
            chk = QCheckBox()
            chk.setChecked(bool(cur_val))
            chk.toggled.connect(lambda state, k=key: self._set_scalar(ref, doc, obj, k, state))
            return chk

        if typ == "integer":
            row = QWidget()
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            spin = QSpinBox()
            spin.setMinimum(int(prop_eff.get("minimum", -2_000_000_000)))
            spin.setMaximum(int(prop_eff.get("maximum", 2_000_000_000)))
            spin.setSpecialValueText("<unset>")
            if isinstance(cur_val, int):
                spin.setValue(cur_val)
            else:
                spin.setValue(spin.minimum())
            spin.valueChanged.connect(lambda v, k=key: self._set_scalar(ref, doc, obj, k, v))
            hl.addWidget(spin)
            btn_clr = QPushButton("×")
            btn_clr.setMaximumWidth(26)
            btn_clr.setToolTip("Unset field")
            btn_clr.clicked.connect(lambda _=False, k=key: self._unset_key(ref, doc, obj, k))
            hl.addWidget(btn_clr)
            return row

        if typ == "number":
            spin = QDoubleSpinBox()
            spin.setDecimals(3)
            spin.setMinimum(float(prop_eff.get("minimum", -1e12)))
            spin.setMaximum(float(prop_eff.get("maximum", 1e12)))
            if isinstance(cur_val, (int, float)):
                spin.setValue(float(cur_val))
            spin.valueChanged.connect(lambda v, k=key: self._set_scalar(ref, doc, obj, k, v))
            return spin

        if typ == "array":
            # Primitive array (e.g. tuning, without, omits, only, names)
            text = ", ".join(map(str, cur_val)) if isinstance(cur_val, list) else ""
            edit = QLineEdit(text)
            edit.setPlaceholderText("Comma-separated values")
            items_type = resolve_schema(ref.root_schema, prop_eff.get("items", {})).get("type")
            edit.editingFinished.connect(
                lambda k=key, e=edit, it=items_type: self._set_primitive_array(ref, doc, obj, k, e.text(), it)
            )
            return edit

        # Default: string
        edit = QLineEdit("" if cur_val is None else str(cur_val))
        if "pattern" in prop_eff:
            edit.setPlaceholderText(prop_eff["pattern"])
        edit.editingFinished.connect(lambda k=key, e=edit: self._on_string_edited(ref, doc, obj, k, e.text()))
        return edit

    def _build_object_array_table(
        self,
        outer: QVBoxLayout,
        ref: TreeNodeRef,
        doc: Any,
        arr: list[Any],
        item_schema: dict[str, Any],
    ) -> None:
        sample = arr[0] if arr else None
        item_eff = resolve_schema(ref.root_schema, item_schema, sample)
        cols = list(item_eff.get("properties", {}).keys())
        if not cols:
            cols = ["value"]

        toolbar = QHBoxLayout()
        btn_add = QPushButton("+ Add Row")
        btn_del = QPushButton("Remove Selected")
        btn_sort = QPushButton("Sort by timeMs")
        btn_shift = QPushButton("Shift ±ms…")

        toolbar.addWidget(btn_add)
        toolbar.addWidget(btn_del)
        if "timeMs" in cols:
            toolbar.addWidget(btn_sort)
            toolbar.addWidget(btn_shift)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        table = QTableWidget(len(arr), len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        for r_idx, row_obj in enumerate(arr):
            if not isinstance(row_obj, dict):
                continue
            for c_idx, col in enumerate(cols):
                val = row_obj.get(col, "")
                table.setItem(r_idx, c_idx, QTableWidgetItem("" if val is None else str(val)))

        def on_cell_changed(r_idx: int, c_idx: int) -> None:
            if r_idx >= len(arr) or not isinstance(arr[r_idx], dict):
                return
            col = cols[c_idx]
            raw_text = table.item(r_idx, c_idx).text().strip()
            col_eff = resolve_schema(ref.root_schema, item_eff["properties"].get(col, {}))
            if raw_text == "":
                arr[r_idx].pop(col, None)
            elif col_eff.get("type") == "integer":
                try:
                    arr[r_idx][col] = int(raw_text)
                except ValueError:
                    return
            elif col_eff.get("type") == "number":
                try:
                    arr[r_idx][col] = float(raw_text)
                except ValueError:
                    return
            elif col_eff.get("type") == "boolean":
                arr[r_idx][col] = raw_text.lower() in ("true", "1", "yes")
            else:
                arr[r_idx][col] = raw_text
            self._touch_aux_timestamp(ref, doc)
            assert self.pkg is not None
            self.pkg.dirty = True
            self.dataChanged.emit(ref.location)

        table.cellChanged.connect(on_cell_changed)

        def add_row() -> None:
            new_row = default_value_for_schema(ref.root_schema, item_schema)
            if isinstance(new_row, dict) and "timeMs" in cols and arr and isinstance(arr[-1], dict):
                new_row["timeMs"] = arr[-1].get("timeMs", 0) + 1000
            arr.append(new_row)
            self._touch_aux_timestamp(ref, doc)
            assert self.pkg is not None
            self.pkg.dirty = True
            self.set_node(self.pkg, ref)
            self.dataChanged.emit(ref.location)

        def del_row() -> None:
            rows = sorted({idx.row() for idx in table.selectedIndexes()}, reverse=True)
            for r_idx in rows:
                if 0 <= r_idx < len(arr):
                    arr.pop(r_idx)
            self._touch_aux_timestamp(ref, doc)
            assert self.pkg is not None
            self.pkg.dirty = True
            self.set_node(self.pkg, ref)
            self.dataChanged.emit(ref.location)

        def sort_rows() -> None:
            arr.sort(key=lambda x: x.get("timeMs", 0) if isinstance(x, dict) else 0)
            self._touch_aux_timestamp(ref, doc)
            assert self.pkg is not None
            self.pkg.dirty = True
            self.set_node(self.pkg, ref)
            self.dataChanged.emit(ref.location)

        def shift_rows() -> None:
            delta, ok = QInputDialog.getInt(self, "Shift timeMs", "Delta (ms, may be negative):", 0, -3600000, 3600000)
            if not ok or delta == 0:
                return
            for x in arr:
                if isinstance(x, dict) and isinstance(x.get("timeMs"), (int, float)):
                    x["timeMs"] = max(0, x["timeMs"] + delta)
            self._touch_aux_timestamp(ref, doc)
            assert self.pkg is not None
            self.pkg.dirty = True
            self.set_node(self.pkg, ref)
            self.dataChanged.emit(ref.location)

        btn_add.clicked.connect(add_row)
        btn_del.clicked.connect(del_row)
        btn_sort.clicked.connect(sort_rows)
        btn_shift.clicked.connect(shift_rows)

        outer.addWidget(table)
        self._active_table = table

    def _build_primitive_list_editor(
        self, outer: QVBoxLayout, ref: TreeNodeRef, doc: Any, arr: list[Any], item_eff: dict[str, Any]
    ) -> None:
        edit = QLineEdit(", ".join(map(str, arr)))
        btn = QPushButton("Apply")
        btn.clicked.connect(
            lambda: self._set_primitive_array(
                ref, doc, self._get_at_path(doc, ref.json_path[:-1]), str(ref.json_path[-1]), edit.text(), item_eff.get("type")
            )
        )
        outer.addWidget(edit)
        outer.addWidget(btn)
        outer.addStretch(1)

    def _init_optional_object(self, ref: TreeNodeRef) -> None:
        assert self.pkg is not None
        doc = self._get_doc(ref.doc_key)
        parent = self._get_at_path(doc, ref.json_path[:-1])
        key = str(ref.json_path[-1])
        parent[key] = default_value_for_schema(ref.root_schema, ref.sub_schema)
        self.pkg.dirty = True
        self.dataChanged.emit(ref.location)

    def _on_enum_changed(self, ref: TreeNodeRef, doc: Any, obj: dict[str, Any], key: str, value: Any) -> None:
        if value is None:
            obj.pop(key, None)
        else:
            obj[key] = value
        self._touch_aux_timestamp(ref, doc)
        assert self.pkg is not None
        self.pkg.dirty = True
        self.dataChanged.emit(ref.location)

    def _on_string_edited(self, ref: TreeNodeRef, doc: Any, obj: dict[str, Any], key: str, text: str) -> None:
        old_val = obj.get(key)
        if text == "":
            if key in obj:
                obj.pop(key, None)
        else:
            if text == old_val:
                return
            # Offer ID cascade on score.id or recording.id rename
            if key == "id" and isinstance(old_val, str) and old_val and ref.kind == "manifest_node":
                if len(ref.json_path) == 2 and ref.json_path[0] == "scores":
                    self._maybe_cascade_score_id(old_val, text)
                elif len(ref.json_path) == 2 and ref.json_path[0] == "recordings":
                    self._maybe_cascade_recording_id(old_val, text)
            obj[key] = text

        self._touch_aux_timestamp(ref, doc)
        assert self.pkg is not None
        self.pkg.dirty = True
        self.dataChanged.emit(ref.location)

    def _set_scalar(self, ref: TreeNodeRef, doc: Any, obj: dict[str, Any], key: str, value: Any) -> None:
        obj[key] = value
        self._touch_aux_timestamp(ref, doc)
        assert self.pkg is not None
        self.pkg.dirty = True
        self.dataChanged.emit(ref.location)

    def _unset_key(self, ref: TreeNodeRef, doc: Any, obj: dict[str, Any], key: str) -> None:
        if key in obj:
            obj.pop(key, None)
            self._touch_aux_timestamp(ref, doc)
            assert self.pkg is not None
            self.pkg.dirty = True
            self.set_node(self.pkg, ref)
            self.dataChanged.emit(ref.location)

    def _set_primitive_array(
        self, ref: TreeNodeRef, doc: Any, obj: dict[str, Any], key: str, text: str, item_type: str | None
    ) -> None:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if not parts:
            obj.pop(key, None)
        elif item_type == "integer":
            try:
                obj[key] = [int(p) for p in parts]
            except ValueError:
                QMessageBox.warning(self, "Invalid Integer", "All items must be integers.")
                return
        else:
            obj[key] = parts
        assert self.pkg is not None
        self.pkg.dirty = True
        self.dataChanged.emit(ref.location)

    def _maybe_cascade_score_id(self, old_id: str, new_id: str) -> None:
        assert self.pkg is not None
        reply = QMessageBox.question(
            self,
            "Rename Score ID",
            f"Update references from score '{old_id}' to '{new_id}' across recordings and sync files?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for r in self.pkg.manifest.get("recordings", []):
            if not isinstance(r, dict):
                continue
            for mkey in ("sync", "scoreTracks"):
                if isinstance(r.get(mkey), dict) and old_id in r[mkey]:
                    r[mkey][new_id] = r[mkey].pop(old_id)
            for s in r.get("sources", []):
                if isinstance(s, dict) and s.get("type") == "embedded" and s.get("score") == old_id:
                    s["score"] = new_id
        for sdoc in self.pkg.sync_files.values():
            if sdoc.get("score") == old_id:
                sdoc["score"] = new_id
                sdoc["updatedAt"] = utc_now_iso()

    def _maybe_cascade_recording_id(self, old_id: str, new_id: str) -> None:
        assert self.pkg is not None
        reply = QMessageBox.question(
            self,
            "Rename Recording ID",
            f"Update references from recording '{old_id}' to '{new_id}' across manifest, sync, and beats files?",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for r in self.pkg.manifest.get("recordings", []):
            if not isinstance(r, dict):
                continue
            for k in ("syncFrom", "stemOf"):
                if r.get(k) == old_id:
                    r[k] = new_id
            if isinstance(r.get("without"), list):
                r["without"] = [new_id if x == old_id else x for x in r["without"]]
        for sdoc in self.pkg.sync_files.values():
            if sdoc.get("recording") == old_id:
                sdoc["recording"] = new_id
                sdoc["updatedAt"] = utc_now_iso()
        for bdoc in self.pkg.beats_files.values():
            if bdoc.get("recording") == old_id:
                bdoc["recording"] = new_id

    def _import_score_file(self, ref: TreeNodeRef, score_obj: dict[str, Any]) -> None:
        assert self.pkg is not None
        file_str, _ = QFileDialog.getOpenFileName(self, "Select Score File")
        if not file_str:
            return
        src = Path(file_str)
        raw = src.read_bytes()
        fmt = score_obj.get("format", "")
        if fmt in TEXT_SCORE_FORMATS:
            raw = normalize_text_score_utf8(raw)
        new_hash = sha256_bytes(raw)
        old_hash = score_obj.get("sha256")
        score_id = score_obj.get("id", "score")

        # SPEC §11 check when replacing an existing score
        is_primary = len(ref.json_path) == 2
        recs = self.pkg.manifest.get("recordings", [])
        has_sync = any(isinstance(r, dict) and score_id in r.get("sync", {}) for r in recs)
        has_alts = is_primary and bool(score_obj.get("alternates"))
        has_tracks = is_primary and any(
            isinstance(r, dict) and (score_id in r.get("scoreTracks", {}) or "track" in r.get("stem", {}))
            for r in recs
        )

        if old_hash and old_hash != new_hash and (has_sync or has_alts or has_tracks):
            dlg = ScoreReplaceDialog(score_id, has_sync, has_alts, has_tracks, self)
            if dlg.exec() != dlg.DialogCode.Accepted:
                return
            plan = dlg.plan()
            if not plan.keep_sync:
                for r in recs:
                    if isinstance(r, dict) and isinstance(r.get("sync"), dict):
                        rel = r["sync"].pop(score_id, None)
                        if rel:
                            self.pkg.delete_entry(rel)
            if has_alts and plan.alternates_action == "remove":
                score_obj.pop("alternates", None)
            elif has_alts and plan.alternates_action == "promote":
                alts = score_obj.pop("alternates", [])
                self.pkg.manifest.setdefault("scores", []).extend(alts)
            if not plan.keep_track_links:
                for r in recs:
                    if isinstance(r, dict):
                        if isinstance(r.get("scoreTracks"), dict):
                            r["scoreTracks"].pop(score_id, None)
                        if isinstance(r.get("stem"), dict):
                            r["stem"].pop("track", None)

        if "externalPath" in score_obj and "path" not in score_obj:
            score_obj["sha256"] = new_hash
        else:
            archive_path = score_obj.get("path") or f"score/{src.name}"
            score_obj["path"] = archive_path
            score_obj["sha256"] = new_hash
            self.pkg.stage_file(archive_path, raw)

        if fmt == "pdf" or src.suffix.lower() == ".pdf":
            pages = pdf_page_count(raw)
            if pages is not None:
                score_obj["pages"] = pages

        self.pkg.dirty = True
        self.set_node(self.pkg, ref)
        self.dataChanged.emit(ref.location)

    def _import_audio_source(self, ref: TreeNodeRef, src_obj: dict[str, Any]) -> None:
        assert self.pkg is not None
        file_str, _ = QFileDialog.getOpenFileName(self, "Select Audio File")
        if not file_str:
            return
        src = Path(file_str)
        archive_path = src_obj.get("path") or f"audio/{src.name}"
        src_obj["path"] = archive_path
        src_obj["sha256"] = sha256_file(src)
        self.pkg.stage_file(archive_path, src)
        self.pkg.dirty = True
        self.set_node(self.pkg, ref)
        self.dataChanged.emit(ref.location)

    def _apply_raw_json(self) -> None:
        if self.pkg is None or self.ref is None:
            return
        try:
            parsed = json.loads(self.raw_edit.toPlainText())
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "Invalid JSON", str(exc))
            return

        if self.ref.kind == "manifest_node" and not self.ref.json_path:
            if not isinstance(parsed, dict):
                QMessageBox.warning(self, "Invalid Manifest", "Manifest root must be a JSON object.")
                return
            self.pkg.manifest = parsed
        elif self.ref.kind == "sync_file" and not self.ref.json_path:
            self.pkg.sync_files[self.ref.doc_key] = parsed
        elif self.ref.kind == "beats_file" and not self.ref.json_path:
            self.pkg.beats_files[self.ref.doc_key] = parsed
        else:
            doc = self._get_doc(self.ref.doc_key)
            parent = self._get_at_path(doc, self.ref.json_path[:-1])
            last = self.ref.json_path[-1]
            if isinstance(parent, dict) and isinstance(last, str):
                parent[last] = parsed
            elif isinstance(parent, list) and isinstance(last, int):
                parent[last] = parsed

        self.pkg.dirty = True
        self.set_node(self.pkg, self.ref)
        self.dataChanged.emit(self.ref.location)

    def _build_preview_for_node(self, ref: TreeNodeRef, val: Any) -> None:
        if isinstance(val, dict) and isinstance(val.get("path"), str) and self.pkg and self.pkg.has_entry(val["path"]):
            self._populate_file_preview(val["path"])
        else:
            self.preview_layout.addWidget(QLabel("No embedded file preview for this node."))
            self.preview_layout.addStretch(1)

    def _populate_file_preview(self, entry: str) -> None:
        assert self.pkg is not None
        low = entry.lower()
        if low.endswith(".pdf"):
            if HAS_QT_PDF:
                raw = self.pkg.read_entry_bytes(entry)
                fd, tmp = tempfile.mkstemp(suffix=".pdf")
                import os

                os.close(fd)
                self._pdf_temp = Path(tmp)
                self._pdf_temp.write_bytes(raw)
                doc = QPdfDocument(self)
                doc.load(str(self._pdf_temp))
                view = QPdfView(self)
                view.setDocument(doc)
                view.setPageMode(QPdfView.PageMode.MultiPage)
                self.preview_layout.addWidget(view)
            else:
                pages = pdf_page_count(self.pkg.read_entry_bytes(entry))
                self.preview_layout.addWidget(QLabel(f"PDF file: {entry} ({pages or '?'} pages)"))
                self.preview_layout.addStretch(1)
            return

        if low.endswith((".json", ".txt", ".abc", ".alphatex", ".xml", ".musicxml", ".md")):
            raw = self.pkg.read_entry_bytes(entry, max_bytes=2 * 1024 * 1024)
            viewer = QPlainTextEdit()
            viewer.setReadOnly(True)
            viewer.setPlainText(raw.decode("utf-8", errors="replace"))
            self.preview_layout.addWidget(viewer)
            return

        self.preview_layout.addWidget(QLabel(f"Binary archive entry: {entry}"))
        self.preview_layout.addStretch(1)

    def _extract_entry(self, entry: str) -> None:
        assert self.pkg is not None
        dest, _ = QFileDialog.getSaveFileName(self, "Extract Entry", Path(entry).name)
        if not dest:
            return
        self.pkg.extract_entry_to_file(entry, Path(dest))

    def _replace_arbitrary_entry(self, entry: str) -> None:
        assert self.pkg is not None
        src, _ = QFileDialog.getOpenFileName(self, f"Replace {entry}")
        if not src:
            return
        self.pkg.stage_file(entry, Path(src))
        self.dataChanged.emit(f"archive/{entry}")

    def _import_arbitrary_archive_file(self) -> None:
        assert self.pkg is not None
        src, _ = QFileDialog.getOpenFileName(self, "Import File into Archive")
        if not src:
            return
        src_path = Path(src)
        rel, ok = QInputDialog.getText(self, "Archive Path", "Entry path inside .mpak:", text=f"x-custom/{src_path.name}")
        if not ok or not rel.strip():
            return
        self.pkg.stage_file(rel.strip(), src_path)
        self.dataChanged.emit(f"archive/{rel.strip()}")

    def _touch_aux_timestamp(self, ref: TreeNodeRef, doc: Any) -> None:
        if ref.kind == "sync_file" and isinstance(doc, dict):
            doc["updatedAt"] = utc_now_iso()

    def _get_doc(self, doc_key: str) -> Any:
        assert self.pkg is not None
        if doc_key == "manifest":
            return self.pkg.manifest
        if doc_key in self.pkg.sync_files:
            return self.pkg.sync_files[doc_key]
        if doc_key in self.pkg.beats_files:
            return self.pkg.beats_files[doc_key]
        return {}

    @staticmethod
    def _get_at_path(doc: Any, path: tuple[str | int, ...]) -> Any:
        cur = doc
        for seg in path:
            if isinstance(cur, dict) and isinstance(seg, str):
                cur = cur.get(seg)
            elif isinstance(cur, list) and isinstance(seg, int) and 0 <= seg < len(cur):
                cur = cur[seg]
            else:
                return None
        return cur

    @staticmethod
    def _field_label(name: str, is_req: bool, prop_eff: dict[str, Any]) -> QLabel:
        lbl = QLabel(f"{name} *" if is_req else name)
        if "description" in prop_eff:
            lbl.setToolTip(prop_eff["description"])
        return lbl

    @staticmethod
    def _clear_layout_items(layout: Any) -> None:
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                NodeEditorWidget._clear_layout_items(item.layout())
