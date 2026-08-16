"""Shared list-widget click / modifier selection helpers."""

from __future__ import annotations

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem


def selected_paths_from_list(list_widget: QListWidget) -> set[str]:
    out: set[str] = set()
    for it in list_widget.selectedItems():
        p = it.data(Qt.ItemDataRole.UserRole)
        if isinstance(p, str):
            out.add(p)
    return out


def pick_paths_with_modifiers(
    paths: list[str],
    selected: set[str],
    path: str,
    *,
    ctrl: bool,
    shift: bool,
    anchor: str | None,
) -> tuple[set[str], str | None]:
    """Apply Ctrl / Shift click rules; return ``(new_selected, new_anchor)``."""
    if path not in paths:
        return selected, anchor
    if shift and anchor and anchor in paths:
        ai = paths.index(anchor)
        ci = paths.index(path)
        lo, hi = sorted((ai, ci))
        new_range = set(paths[lo : hi + 1])
        if ctrl:
            return selected | new_range, anchor
        return new_range, anchor
    if ctrl:
        new_sel = set(selected)
        if path in new_sel:
            new_sel.discard(path)
        else:
            new_sel.add(path)
        return new_sel, path
    return {path}, path


def sync_list_widget_selection(
    list_widget: QListWidget,
    path_to_item: dict[str, QListWidgetItem],
    selected: set[str],
    primary: str | None,
) -> None:
    list_widget.blockSignals(True)
    list_widget.clearSelection()
    last: QListWidgetItem | None = None
    for p in selected:
        it = path_to_item.get(p)
        if it is not None:
            it.setSelected(True)
            last = it
    cur_item: QListWidgetItem | None = None
    if primary and primary in selected:
        cur_item = path_to_item.get(primary)
    if cur_item is None:
        cur_item = last
    if cur_item is not None:
        # NoUpdate: moving current must not ClearAndSelect (breaks Ctrl+toggle deselect).
        list_widget.setCurrentItem(cur_item, QItemSelectionModel.SelectionFlag.NoUpdate)
    list_widget.blockSignals(False)
