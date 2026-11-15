"""Dynamic schema-driven QTreeWidget builder for MPAK packages."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QInputDialog, QMenu, QTreeWidget, QTreeWidgetItem

from .archive import MpakPackage
from .schema_utils import (
    SchemaRegistry,
    default_value_for_schema,
    item_label,
    resolve_schema,
)


@dataclass
class TreeNodeRef:
    """Metadata attached to every item in the schema-driven pack tree."""

    kind: str  # "manifest_node" | "sync_root" | "sync_file" | "beats_root" | "beats_file" | "archive_root" | "archive_entry"
    doc_key: str  # "manifest" | rel_path
    json_path: tuple[str | int, ...]
    root_schema: dict[str, Any]
    sub_schema: dict[str, Any]
    location: str  # matches ValidationIssue.location prefix


class PackTreeWidget(QTreeWidget):
    """Tree view populated dynamically from JSON Schemas + archive contents."""

    nodeSelected = Signal(object)  # TreeNodeRef
    packageMutated = Signal()

    def __init__(self, schemas: SchemaRegistry, parent: Any = None) -> None:
        super().__init__(parent)
        self.schemas = schemas
        self.pkg: MpakPackage | None = None
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.currentItemChanged.connect(self._on_current_changed)
        self._location_map: dict[str, QTreeWidgetItem] = {}

    def set_package(self, pkg: MpakPackage | None, preserve_location: str | None = None) -> None:
        """Rebuild the tree from `pkg` and the runtime schemas."""
        self.pkg = pkg
        target_loc = preserve_location
        if target_loc is None and self.currentItem() is not None:
            ref = self.currentItem().data(0, Qt.ItemDataRole.UserRole)
            if isinstance(ref, TreeNodeRef):
                target_loc = ref.location

        self.blockSignals(True)
        self.clear()
        self._location_map.clear()
        if pkg is None:
            self.blockSignals(False)
            return

        # 1. Manifest root (walked dynamically from manifest.schema.json)
        m_ref = TreeNodeRef(
            kind="manifest_node",
            doc_key="manifest",
            json_path=(),
            root_schema=self.schemas.manifest,
            sub_schema=self.schemas.manifest,
            location="manifest",
        )
        m_root = self._make_item("Manifest", m_ref)
        self.addTopLevelItem(m_root)
        self._populate_schema_children(
            m_root,
            self.schemas.manifest,
            self.schemas.manifest,
            pkg.manifest,
            doc_key="manifest",
            json_path=(),
            loc_prefix="manifest",
        )
        m_root.setExpanded(True)

        # 2. Sync Files
        sync_root_ref = TreeNodeRef(
            kind="sync_root",
            doc_key="sync_root",
            json_path=(),
            root_schema=self.schemas.sync,
            sub_schema=self.schemas.sync,
            location="sync",
        )
        sync_root = self._make_item(f"Sync Files ({len(pkg.sync_files)})", sync_root_ref)
        self.addTopLevelItem(sync_root)
        for rel in sorted(pkg.sync_files.keys()):
            sdoc = pkg.sync_files[rel]
            s_ref = TreeNodeRef(
                kind="sync_file",
                doc_key=rel,
                json_path=(),
                root_schema=self.schemas.sync,
                sub_schema=self.schemas.sync,
                location=f"sync/{rel}",
            )
            label = f"{rel}  ({sdoc.get('recording', '?')} ↔ {sdoc.get('score', '?')})"
            s_item = self._make_item(label, s_ref)
            sync_root.addChild(s_item)
            self._populate_schema_children(
                s_item,
                self.schemas.sync,
                self.schemas.sync,
                sdoc,
                doc_key=rel,
                json_path=(),
                loc_prefix=f"sync/{rel}",
                kind="sync_file",
            )
        sync_root.setExpanded(True)

        # 3. Beats Files
        beats_root_ref = TreeNodeRef(
            kind="beats_root",
            doc_key="beats_root",
            json_path=(),
            root_schema=self.schemas.beats,
            sub_schema=self.schemas.beats,
            location="beats",
        )
        beats_root = self._make_item(f"Beats Files ({len(pkg.beats_files)})", beats_root_ref)
        self.addTopLevelItem(beats_root)
        for rel in sorted(pkg.beats_files.keys()):
            bdoc = pkg.beats_files[rel]
            b_ref = TreeNodeRef(
                kind="beats_file",
                doc_key=rel,
                json_path=(),
                root_schema=self.schemas.beats,
                sub_schema=self.schemas.beats,
                location=f"beats/{rel}",
            )
            label = f"{rel}  ({bdoc.get('recording', '?')})"
            b_item = self._make_item(label, b_ref)
            beats_root.addChild(b_item)
            self._populate_schema_children(
                b_item,
                self.schemas.beats,
                self.schemas.beats,
                bdoc,
                doc_key=rel,
                json_path=(),
                loc_prefix=f"beats/{rel}",
                kind="beats_file",
            )
        beats_root.setExpanded(True)

        # 4. Archive Files
        entries = pkg.list_entries()
        arch_root_ref = TreeNodeRef(
            kind="archive_root",
            doc_key="archive",
            json_path=(),
            root_schema={},
            sub_schema={},
            location="archive",
        )
        arch_root = self._make_item(f"Archive Files ({len(entries)})", arch_root_ref)
        self.addTopLevelItem(arch_root)
        for entry in entries:
            e_ref = TreeNodeRef(
                kind="archive_entry",
                doc_key=entry,
                json_path=(),
                root_schema={},
                sub_schema={},
                location=f"archive/{entry}",
            )
            sz = pkg.entry_size(entry)
            sz_str = f" ({_fmt_bytes(sz)})" if sz is not None else ""
            arch_root.addChild(self._make_item(f"{entry}{sz_str}", e_ref))

        self.blockSignals(False)

        if target_loc and self.select_location(target_loc):
            return
        self.setCurrentItem(m_root)

    def select_location(self, location: str) -> bool:
        """Select the closest matching tree node for a validation issue location."""
        cur = location
        while cur:
            if cur in self._location_map:
                item = self._location_map[cur]
                self.setCurrentItem(item)
                self.scrollToItem(item)
                return True
            if "/" not in cur:
                break
            cur = cur.rsplit("/", 1)[0]
        return False

    def _make_item(self, label: str, ref: TreeNodeRef) -> QTreeWidgetItem:
        item = QTreeWidgetItem([label])
        item.setData(0, Qt.ItemDataRole.UserRole, ref)
        self._location_map[ref.location] = item
        return item

    def _populate_schema_children(
        self,
        parent_item: QTreeWidgetItem,
        root_schema: dict[str, Any],
        sub_schema: dict[str, Any],
        data: Any,
        doc_key: str,
        json_path: tuple[str | int, ...],
        loc_prefix: str,
        kind: str = "manifest_node",
    ) -> None:
        eff = resolve_schema(root_schema, sub_schema, data)
        props = eff.get("properties", {})

        if isinstance(data, dict) or eff.get("type") == "object" or props:
            data_dict = data if isinstance(data, dict) else {}
            # Walk schema properties that are objects, arrays of objects, or maps
            for key, prop_schema in props.items():
                prop_val = data_dict.get(key)
                prop_eff = resolve_schema(root_schema, prop_schema, prop_val)
                prop_type = prop_eff.get("type")
                child_path = (*json_path, key)
                child_loc = f"{loc_prefix}/{key}"

                if prop_type == "object" or "properties" in prop_eff or isinstance(prop_eff.get("additionalProperties"), dict):
                    present = key in data_dict
                    label = key if present else f"{key} (unset)"
                    c_ref = TreeNodeRef(kind, doc_key, child_path, root_schema, prop_schema, child_loc)
                    c_item = self._make_item(label, c_ref)
                    parent_item.addChild(c_item)
                    if present and isinstance(prop_val, dict):
                        self._populate_schema_children(
                            c_item, root_schema, prop_schema, prop_val, doc_key, child_path, child_loc, kind
                        )
                        c_item.setExpanded(key in ("scores", "recordings"))

                elif prop_type == "array":
                    items_schema = prop_eff.get("items", {})
                    items_eff = resolve_schema(root_schema, items_schema)
                    # Show array branch in tree if items are objects (or if it's points/beats/sections)
                    if items_eff.get("type") == "object" or "properties" in items_eff:
                        arr = prop_val if isinstance(prop_val, list) else []
                        c_ref = TreeNodeRef(kind, doc_key, child_path, root_schema, prop_schema, child_loc)
                        c_item = self._make_item(f"{key} ({len(arr)})", c_ref)
                        parent_item.addChild(c_item)
                        # Avoid exploding thousands of points/beats into tree items; edit them in the table!
                        if key not in ("points", "beats", "sections"):
                            for idx, elem in enumerate(arr):
                                elem_path = (*child_path, idx)
                                elem_loc = f"{child_loc}/{idx}"
                                prefix = "★ " if (key == "scores" and idx == 0) else ""
                                el_ref = TreeNodeRef(kind, doc_key, elem_path, root_schema, items_schema, elem_loc)
                                el_item = self._make_item(f"{prefix}{item_label(elem, idx)}", el_ref)
                                c_item.addChild(el_item)
                                self._populate_schema_children(
                                    el_item, root_schema, items_schema, elem, doc_key, elem_path, elem_loc, kind
                                )
                            c_item.setExpanded(key in ("scores", "recordings", "alternates"))

            # Map entries via additionalProperties (e.g., sync, scoreTracks)
            addl = eff.get("additionalProperties")
            if isinstance(addl, dict) and isinstance(data_dict, dict):
                for key, val in data_dict.items():
                    if key in props:
                        continue
                    c_path = (*json_path, key)
                    c_loc = f"{loc_prefix}/{key}"
                    c_ref = TreeNodeRef(kind, doc_key, c_path, root_schema, addl, c_loc)
                    c_item = self._make_item(str(key), c_ref)
                    parent_item.addChild(c_item)
                    if isinstance(val, dict):
                        self._populate_schema_children(
                            c_item, root_schema, addl, val, doc_key, c_path, c_loc, kind
                        )

            # Unknown / x-* object or array fields present in data (preserved dynamically!)
            if isinstance(data_dict, dict) and not isinstance(addl, dict):
                for key, val in data_dict.items():
                    if key in props:
                        continue
                    if isinstance(val, (dict, list)):
                        c_path = (*json_path, key)
                        c_loc = f"{loc_prefix}/{key}"
                        c_ref = TreeNodeRef(kind, doc_key, c_path, root_schema, {}, c_loc)
                        c_item = self._make_item(f"{key} (extra)", c_ref)
                        parent_item.addChild(c_item)

    def _on_current_changed(self, current: QTreeWidgetItem | None, _prev: QTreeWidgetItem | None) -> None:
        if current is None:
            return
        ref = current.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(ref, TreeNodeRef):
            self.nodeSelected.emit(ref)

    def _on_context_menu(self, pos: Any) -> None:
        if self.pkg is None:
            return
        item = self.itemAt(pos)
        if item is None:
            return
        ref = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(ref, TreeNodeRef):
            return

        menu = QMenu(self)
        if ref.kind in ("manifest_node", "sync_file", "beats_file"):
            doc = self._get_doc(ref.doc_key)
            val = _get_at_path(doc, ref.json_path)
            eff = resolve_schema(ref.root_schema, ref.sub_schema, val)

            if eff.get("type") == "array" and "items" in eff:
                act_add = QAction(f"+ Add {ref.json_path[-1] if ref.json_path else 'item'}", self)
                act_add.triggered.connect(lambda: self._add_array_item(ref))
                menu.addAction(act_add)

            if isinstance(eff.get("additionalProperties"), dict):
                act_add_k = QAction("+ Add Key…", self)
                act_add_k.triggered.connect(lambda: self._add_map_entry(ref, eff["additionalProperties"]))
                menu.addAction(act_add_k)

            if ref.json_path:
                parent_val = _get_at_path(doc, ref.json_path[:-1])
                if isinstance(parent_val, list):
                    act_del = QAction("Remove Item", self)
                    act_del.triggered.connect(lambda: self._remove_node(ref))
                    menu.addAction(act_del)
                elif isinstance(parent_val, dict) and ref.json_path[-1] in parent_val:
                    act_del = QAction(f"Clear '{ref.json_path[-1]}'", self)
                    act_del.triggered.connect(lambda: self._remove_node(ref))
                    menu.addAction(act_del)

        elif ref.kind == "sync_root":
            act = QAction("+ New Sync File…", self)
            act.triggered.connect(self._new_sync_file)
            menu.addAction(act)
        elif ref.kind == "sync_file" and not ref.json_path:
            act = QAction("Delete Sync File", self)
            act.triggered.connect(lambda: self._delete_aux_file(ref.doc_key))
            menu.addAction(act)
        elif ref.kind == "beats_root":
            act = QAction("+ New Beats File…", self)
            act.triggered.connect(self._new_beats_file)
            menu.addAction(act)
        elif ref.kind == "beats_file" and not ref.json_path:
            act = QAction("Delete Beats File", self)
            act.triggered.connect(lambda: self._delete_aux_file(ref.doc_key))
            menu.addAction(act)
        elif ref.kind == "archive_entry" and ref.doc_key != "manifest.json":
            act = QAction("Delete Archive Entry", self)
            act.triggered.connect(lambda: self._delete_aux_file(ref.doc_key))
            menu.addAction(act)

        if menu.actions():
            menu.exec(self.viewport().mapToGlobal(pos))

    def _get_doc(self, doc_key: str) -> Any:
        assert self.pkg is not None
        if doc_key == "manifest":
            return self.pkg.manifest
        if doc_key in self.pkg.sync_files:
            return self.pkg.sync_files[doc_key]
        if doc_key in self.pkg.beats_files:
            return self.pkg.beats_files[doc_key]
        return {}

    def _add_array_item(self, ref: TreeNodeRef) -> None:
        assert self.pkg is not None
        doc = self._get_doc(ref.doc_key)
        parent = _get_at_path(doc, ref.json_path[:-1]) if ref.json_path else doc
        key = ref.json_path[-1]
        arr = parent.setdefault(key, [])
        eff = resolve_schema(ref.root_schema, ref.sub_schema, arr)
        new_item = default_value_for_schema(ref.root_schema, eff.get("items", {}))
        if isinstance(new_item, dict) and "id" in new_item and not new_item["id"]:
            new_item["id"] = f"{key[:-1] if key.endswith('s') else key}-{len(arr) + 1}"
        arr.append(new_item)
        self.pkg.dirty = True
        self.set_package(self.pkg, preserve_location=f"{ref.location}/{len(arr) - 1}")
        self.packageMutated.emit()

    def _add_map_entry(self, ref: TreeNodeRef, val_schema: dict[str, Any]) -> None:
        assert self.pkg is not None
        key, ok = QInputDialog.getText(self, "Add Key", "Key (e.g. score id):")
        if not ok or not key.strip():
            return
        key = key.strip()
        doc = self._get_doc(ref.doc_key)
        parent = _get_at_path(doc, ref.json_path[:-1]) if ref.json_path else doc
        mapping = parent.setdefault(ref.json_path[-1], {})
        mapping[key] = default_value_for_schema(ref.root_schema, val_schema)
        self.pkg.dirty = True
        self.set_package(self.pkg, preserve_location=f"{ref.location}/{key}")
        self.packageMutated.emit()

    def _remove_node(self, ref: TreeNodeRef) -> None:
        assert self.pkg is not None
        doc = self._get_doc(ref.doc_key)
        parent = _get_at_path(doc, ref.json_path[:-1])
        last = ref.json_path[-1]
        if isinstance(parent, list) and isinstance(last, int) and 0 <= last < len(parent):
            parent.pop(last)
        elif isinstance(parent, dict) and last in parent:
            parent.pop(last)
        self.pkg.dirty = True
        parent_loc = ref.location.rsplit("/", 1)[0] if "/" in ref.location else "manifest"
        self.set_package(self.pkg, preserve_location=parent_loc)
        self.packageMutated.emit()

    def _new_sync_file(self) -> None:
        assert self.pkg is not None
        rel, ok = QInputDialog.getText(self, "New Sync File", "Archive path:", text="sync/mix.json")
        if not ok or not rel.strip():
            return
        rel = rel.strip()
        rec_id = ""
        recs = self.pkg.manifest.get("recordings", [])
        if isinstance(recs, list) and recs and isinstance(recs[0], dict):
            rec_id = recs[0].get("id", "")
        score_id = ""
        anchor = "bar"
        scores = self.pkg.manifest.get("scores", [])
        if isinstance(scores, list) and scores and isinstance(scores[0], dict):
            score_id = scores[0].get("id", "")
            from .schema_utils import ANCHOR_BY_FORMAT

            anchor = ANCHOR_BY_FORMAT.get(scores[0].get("format", ""), "bar")
        from .archive import utc_now_iso

        self.pkg.sync_files[rel] = {
            "version": 1,
            "recording": rec_id,
            "score": score_id,
            "anchorType": anchor,
            "updatedAt": utc_now_iso(),
            "points": [],
        }
        self.pkg.dirty = True
        self.set_package(self.pkg, preserve_location=f"sync/{rel}")
        self.packageMutated.emit()

    def _new_beats_file(self) -> None:
        assert self.pkg is not None
        rel, ok = QInputDialog.getText(self, "New Beats File", "Archive path:", text="beats/mix.json")
        if not ok or not rel.strip():
            return
        rel = rel.strip()
        rec_id = ""
        recs = self.pkg.manifest.get("recordings", [])
        if isinstance(recs, list) and recs and isinstance(recs[0], dict):
            rec_id = recs[0].get("id", "")
        self.pkg.beats_files[rel] = {
            "version": 1,
            "recording": rec_id,
            "beats": [],
            "sections": [],
        }
        self.pkg.dirty = True
        self.set_package(self.pkg, preserve_location=f"beats/{rel}")
        self.packageMutated.emit()

    def _delete_aux_file(self, entry: str) -> None:
        assert self.pkg is not None
        self.pkg.delete_entry(entry)
        self.set_package(self.pkg, preserve_location="manifest")
        self.packageMutated.emit()


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


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if n < 1024 or unit == "GiB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024  # type: ignore[assignment]
    return f"{n} B"
