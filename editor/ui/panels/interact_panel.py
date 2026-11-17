import os
import shutil

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox, QScrollArea, QInputDialog,
    QDialog
)
from PyQt6.QtCore import Qt, pyqtSignal

from .interact_editor import ActionEditorDialog


class InteractPanel(QWidget):
    """互动分组面板：管理分组 + 动作。"""

    request_preview = pyqtSignal(object, int)
    project_changed = pyqtSignal()
    page_saved = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(24, 20, 24, 20)
        self._layout.setSpacing(12)

        title = QLabel("互动分组")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        self._layout.addWidget(title)

        desc = QLabel(
            "管理互动分组与动作。每个动作可选瞬时（播放 1 次）或持续（开场/循环/退场）类型，"
            "类型创建后不可改，需要更换类型请删除重建。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #666; background: transparent;")
        self._layout.addWidget(desc)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.btn_add_group = QPushButton("＋ 新建分组")
        self.btn_add_group.setFixedHeight(34)
        self.btn_add_group.setMinimumWidth(120)
        self.btn_add_group.clicked.connect(self._on_add_group)
        add_row.addWidget(self.btn_add_group)
        add_row.addStretch(1)
        self._layout.addLayout(add_row)

        self._groups_container = QWidget()
        self._groups_layout = QVBoxLayout(self._groups_container)
        self._groups_layout.setContentsMargins(0, 0, 0, 0)
        self._groups_layout.setSpacing(10)
        self._layout.addWidget(self._groups_container)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self.btn_save = QPushButton("💾 保存本页")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self.btn_save)
        save_row.addStretch(1)
        self._layout.addLayout(save_row)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 12px; padding: 2px 0;")
        self._layout.addWidget(self.lbl_hint)

        self._layout.addStretch(1)

    def _card_style(self, obj_name):
        return f"""
            QFrame#{obj_name} {{
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }}
            QFrame#{obj_name} QLabel {{
                background: transparent;
                color: #333;
                font-size: 13px;
            }}
            QFrame#{obj_name} QLineEdit {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 13px;
                min-height: 22px;
            }}
            QFrame#{obj_name} QPushButton {{
                background: #ffffff;
                color: #333;
                border: 1px solid #b8b8b8;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px 8px;
            }}
            QFrame#{obj_name} QPushButton:hover {{
                background: #f0f0f0;
                border-color: #a0a0a0;
            }}
            QFrame#{obj_name} QPushButton:pressed {{
                background: #e0e0e0;
            }}
            QFrame#{obj_name} QPushButton#btn_del {{
                background: #fff0f0;
                color: #c0392b;
                border: 1px solid #e8b8b8;
            }}
            QFrame#{obj_name} QPushButton#btn_del:hover {{
                background: #ffe0e0;
                border-color: #d04040;
            }}
        """

    # ---------- 刷新 ----------
    def _refresh_groups(self):
        while self._groups_layout.count() > 0:
            item = self._groups_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        if not self.project.is_open:
            return

        groups = self.project.config.get("interact", {}).get("groups", [])
        if not groups:
            lbl = QLabel("暂无分组。点上方『＋ 新建分组』开始。")
            lbl.setStyleSheet("font-size: 13px; color: #888; padding: 30px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._groups_layout.addWidget(lbl)
            return

        for idx, group in enumerate(groups):
            card = self._build_group_card(idx, group, len(groups))
            self._groups_layout.addWidget(card)

    def _build_group_card(self, idx, group, total):
        card = QFrame()
        obj_name = f"group_{group['group_id']}"
        card.setObjectName(obj_name)
        card.setStyleSheet(self._card_style(obj_name))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        # 头部
        head = QHBoxLayout()
        head.setSpacing(6)

        cap = QLabel("分组：")
        cap.setFixedWidth(44)
        cap.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        head.addWidget(cap)

        edit_name = QLineEdit()
        edit_name.setText(group.get("group_name", ""))
        edit_name.textChanged.connect(
            lambda text, g=group: self._on_group_name_changed(g, text)
        )
        head.addWidget(edit_name, 1)

        btn_up = QPushButton("▲")
        btn_up.setFixedWidth(28)
        btn_up.setToolTip("上移分组")
        btn_up.setEnabled(idx > 0)
        btn_up.clicked.connect(lambda checked=False, i=idx: self._on_move_group(i, -1))
        head.addWidget(btn_up)

        btn_down = QPushButton("▼")
        btn_down.setFixedWidth(28)
        btn_down.setToolTip("下移分组")
        btn_down.setEnabled(idx < total - 1)
        btn_down.clicked.connect(lambda checked=False, i=idx: self._on_move_group(i, 1))
        head.addWidget(btn_down)

        btn_del = QPushButton("🗑")
        btn_del.setObjectName("btn_del")
        btn_del.setFixedWidth(36)
        btn_del.setToolTip("删除分组")
        btn_del.clicked.connect(lambda checked=False, i=idx: self._on_delete_group(i))
        head.addWidget(btn_del)
        cl.addLayout(head)

        # 动作列表
        actions = group.get("actions", [])
        if not actions:
            empty_lbl = QLabel("（暂无动作）")
            empty_lbl.setStyleSheet(
                "background: transparent; color: #888; font-size: 12px; padding: 6px;"
            )
            cl.addWidget(empty_lbl)
        else:
            for a_idx, action in enumerate(actions):
                row = self._build_action_row(group, action, a_idx, len(actions))
                cl.addWidget(row)

        add_a_row = QHBoxLayout()
        add_a_row.addStretch(1)
        btn_add_action = QPushButton("＋ 添加动作")
        btn_add_action.setFixedHeight(28)
        btn_add_action.setMinimumWidth(100)
        btn_add_action.clicked.connect(
            lambda checked=False, g=group: self._on_add_action(g)
        )
        add_a_row.addWidget(btn_add_action)
        cl.addLayout(add_a_row)

        return card

    def _build_action_row(self, group, action, idx, total):
        row = QFrame()
        row.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
            }
            QFrame QLabel { background: transparent; color: #333; font-size: 12px; }
            QFrame QPushButton {
                background: #f8f8f8;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 3px;
                font-size: 11px;
                padding: 1px 6px;
            }
            QFrame QPushButton:hover { background: #efefef; }
        """)
        h = QHBoxLayout(row)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)

        type_name = "瞬时" if action.get("type") == "instant" else "持续"
        type_lbl = QLabel(f"[{type_name}]")
        type_lbl.setStyleSheet("background: transparent; color: #666; font-size: 11px;")
        type_lbl.setFixedWidth(44)
        h.addWidget(type_lbl)

        name_lbl = QLabel(action.get("action_name", "?"))
        name_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        h.addWidget(name_lbl, 1)

        btn_edit = QPushButton("✎ 编辑")
        btn_edit.setFixedHeight(24)
        btn_edit.clicked.connect(
            lambda checked=False, g=group, a=action: self._on_edit_action(g, a)
        )
        h.addWidget(btn_edit)

        btn_move = QPushButton("→ 移动")
        btn_move.setFixedHeight(24)
        btn_move.clicked.connect(
            lambda checked=False, g=group, a=action: self._on_move_action_to_group(g, a)
        )
        h.addWidget(btn_move)

        btn_up = QPushButton("▲")
        btn_up.setFixedHeight(24)
        btn_up.setFixedWidth(28)
        btn_up.setEnabled(idx > 0)
        btn_up.clicked.connect(
            lambda checked=False, g=group, i=idx: self._on_move_action(g, i, -1)
        )
        h.addWidget(btn_up)

        btn_down = QPushButton("▼")
        btn_down.setFixedHeight(24)
        btn_down.setFixedWidth(28)
        btn_down.setEnabled(idx < total - 1)
        btn_down.clicked.connect(
            lambda checked=False, g=group, i=idx: self._on_move_action(g, i, 1)
        )
        h.addWidget(btn_down)

        btn_del = QPushButton("🗑")
        btn_del.setFixedHeight(24)
        btn_del.setFixedWidth(32)
        btn_del.setStyleSheet(
            "background: #fff0f0; color: #c0392b; border: 1px solid #e8b8b8;"
        )
        btn_del.clicked.connect(
            lambda checked=False, g=group, a=action: self._on_delete_action(g, a)
        )
        h.addWidget(btn_del)

        return row

    # ---------- 分组事件 ----------
    def _on_group_name_changed(self, group, text):
        if not self.project.is_open:
            return
        group["group_name"] = text
        self.project.dirty = True
        self.project_changed.emit()

    def _on_add_group(self):
        if not self.project.is_open:
            return
        name, ok = QInputDialog.getText(
            self, "新建分组", "分组名称：", text="新分组"
        )
        if not ok or not name.strip():
            return
        name = name.strip()

        groups = self.project.config.setdefault("interact", {}).setdefault("groups", [])
        max_n = 0
        for g in groups:
            gid = g.get("group_id", "")
            if gid.startswith("group_"):
                try:
                    max_n = max(max_n, int(gid[6:]))
                except ValueError:
                    pass
        new_id = f"group_{max_n + 1}"

        try:
            os.makedirs(
                os.path.join(self.project.path, "assets", "interact", new_id),
                exist_ok=True,
            )
            os.makedirs(
                os.path.join(self.project.path, "mask", "interact", new_id),
                exist_ok=True,
            )
        except Exception as e:
            QMessageBox.warning(self, "创建目录失败", str(e))
            return

        groups.append({
            "group_id": new_id,
            "group_name": name,
            "actions": [],
        })
        self.project.dirty = True
        self._refresh_groups()
        self.project_changed.emit()
        self.lbl_hint.setText(f"✅ 已新建分组「{name}」")

    def _on_move_group(self, idx, delta):
        if not self.project.is_open:
            return
        groups = self.project.config["interact"]["groups"]
        new_idx = idx + delta
        if 0 <= new_idx < len(groups):
            groups[idx], groups[new_idx] = groups[new_idx], groups[idx]
            self.project.dirty = True
            self._refresh_groups()
            self.project_changed.emit()

    def _on_delete_group(self, idx):
        if not self.project.is_open:
            return
        groups = self.project.config["interact"]["groups"]
        if not (0 <= idx < len(groups)):
            return
        group = groups[idx]
        name = group.get("group_name", "?")
        action_count = len(group.get("actions", []))

        msg = f"确定删除分组「{name}」吗？"
        if action_count > 0:
            msg += f"\n该分组下有 {action_count} 个动作，将一并删除。"
        msg += f"\n对应素材目录 assets/interact/{group['group_id']} 会被删除。"

        ret = QMessageBox.question(
            self, "删除分组", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        groups.pop(idx)

        gid = group["group_id"]
        for kind in ("assets", "mask"):
            d = os.path.join(self.project.path, kind, "interact", gid)
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

        self.project.dirty = True
        self._refresh_groups()
        self.project_changed.emit()
        self.lbl_hint.setText(f"🗑 已删除分组「{name}」")

    # ---------- 动作事件 ----------
    def _generate_action_id(self, action_type):
        max_n = 0
        for g in self.project.config.get("interact", {}).get("groups", []):
            for a in g.get("actions", []):
                aid = a.get("action_id", "")
                prefix = f"{action_type}_"
                if aid.startswith(prefix):
                    try:
                        max_n = max(max_n, int(aid[len(prefix):]))
                    except ValueError:
                        pass
        return f"{action_type}_{max_n + 1}"

    def _on_add_action(self, group):
        if not self.project.is_open:
            return

        items = ["瞬时互动（播放 1 次）", "持续互动（开场/循环/退场）"]
        item, ok = QInputDialog.getItem(
            self, "添加动作", "选择动作类型：", items, 0, False
        )
        if not ok:
            return

        action_type = "instant" if "瞬时" in item else "continuous"
        action_id = self._generate_action_id(action_type)
        action_path_rel = f"./assets/interact/{group['group_id']}/{action_id}"

        action_dir = os.path.join(
            self.project.path, "assets", "interact",
            group["group_id"], action_id
        )
        try:
            if action_type == "continuous":
                for slot in ("start", "loop", "end"):
                    os.makedirs(os.path.join(action_dir, slot), exist_ok=True)
                    os.makedirs(
                        os.path.join(
                            self.project.path, "mask", "interact",
                            group["group_id"], action_id, slot
                        ),
                        exist_ok=True,
                    )
            else:
                os.makedirs(action_dir, exist_ok=True)
                os.makedirs(
                    os.path.join(
                        self.project.path, "mask", "interact",
                        group["group_id"], action_id
                    ),
                    exist_ok=True,
                )
        except Exception as e:
            QMessageBox.warning(self, "创建目录失败", str(e))
            return

        type_label = "瞬时" if action_type == "instant" else "持续"
        new_action = {
            "action_id": action_id,
            "action_name": f"{type_label}{action_id.rsplit('_', 1)[-1]}",
            "type": action_type,
            "path": action_path_rel,
            "preview_path": action_path_rel + "/preview.png",
            "fps": 16,
        }
        if action_type == "continuous":
            new_action["prompt"] = ""

        dlg = ActionEditorDialog(
            self.project, group["group_id"], new_action, "create", parent=self
        )
        dlg.request_preview.connect(self.request_preview.emit)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            group.setdefault("actions", []).append(dlg.get_action_data())
            self.project.dirty = True
            self._refresh_groups()
            self.project_changed.emit()
            self.lbl_hint.setText(
                f"✅ 已添加动作「{dlg.get_action_data()['action_name']}」"
            )
        else:
            # 用户取消 → 清理刚建的目录
            for kind in ("assets", "mask"):
                d = os.path.join(
                    self.project.path, kind, "interact",
                    group["group_id"], action_id
                )
                if os.path.isdir(d):
                    shutil.rmtree(d, ignore_errors=True)

    def _on_edit_action(self, group, action):
        dlg = ActionEditorDialog(
            self.project, group["group_id"], action, "edit", parent=self
        )
        dlg.request_preview.connect(self.request_preview.emit)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_action_data()
            actions = group.get("actions", [])
            for i, a in enumerate(actions):
                if a.get("action_id") == action.get("action_id"):
                    actions[i] = new_data
                    break
            self.project.dirty = True
            self._refresh_groups()
            self.project_changed.emit()

    def _on_move_action_to_group(self, src_group, action):
        if not self.project.is_open:
            return
        groups = self.project.config["interact"]["groups"]
        options = [
            (g["group_id"], g["group_name"])
            for g in groups
            if g["group_id"] != src_group["group_id"]
        ]
        if not options:
            QMessageBox.information(self, "无法移动", "当前只有 1 个分组，无法移动。")
            return

        names = [n for _, n in options]
        item, ok = QInputDialog.getItem(
            self, "移动动作", "选择目标分组：", names, 0, False
        )
        if not ok:
            return

        target_gid = options[names.index(item)][0]
        target_group = next(g for g in groups if g["group_id"] == target_gid)

        # 检查目标分组下是否有同 action_id（理论上不会，但防御一下）
        aid = action["action_id"]
        for a in target_group.get("actions", []):
            if a.get("action_id") == aid:
                QMessageBox.warning(
                    self, "无法移动",
                    f"目标分组下已存在 id 为 {aid} 的动作，移动中止。"
                )
                return

        # 从源移除
        try:
            src_group["actions"].remove(action)
        except ValueError:
            return

        # 移动目录
        old_asset_dir = os.path.join(
            self.project.path, "assets", "interact",
            src_group["group_id"], aid
        )
        old_mask_dir = os.path.join(
            self.project.path, "mask", "interact",
            src_group["group_id"], aid
        )
        new_asset_dir = os.path.join(
            self.project.path, "assets", "interact", target_gid, aid
        )
        new_mask_dir = os.path.join(
            self.project.path, "mask", "interact", target_gid, aid
        )

        try:
            if os.path.isdir(old_asset_dir):
                shutil.move(old_asset_dir, new_asset_dir)
            if os.path.isdir(old_mask_dir):
                shutil.move(old_mask_dir, new_mask_dir)
        except Exception as e:
            QMessageBox.warning(self, "移动目录失败", str(e))
            src_group["actions"].append(action)  # 回滚
            return

        action["path"] = f"./assets/interact/{target_gid}/{aid}"
        action["preview_path"] = action["path"] + "/preview.png"
        target_group.setdefault("actions", []).append(action)

        self.project.dirty = True
        self._refresh_groups()
        self.project_changed.emit()
        self.lbl_hint.setText(
            f"✅ 已移动「{action.get('action_name')}」→「{target_group['group_name']}」"
        )

    def _on_move_action(self, group, idx, delta):
        actions = group.get("actions", [])
        new_idx = idx + delta
        if 0 <= new_idx < len(actions):
            actions[idx], actions[new_idx] = actions[new_idx], actions[idx]
            self.project.dirty = True
            self._refresh_groups()
            self.project_changed.emit()

    def _on_delete_action(self, group, action):
        name = action.get("action_name", action.get("action_id", "?"))
        ret = QMessageBox.question(
            self, "删除动作",
            f"确定删除动作「{name}」吗？\n"
            f"素材目录 assets/interact/{group['group_id']}/{action['action_id']} 会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        try:
            group["actions"].remove(action)
        except ValueError:
            return

        for kind in ("assets", "mask"):
            d = os.path.join(
                self.project.path, kind, "interact",
                group["group_id"], action["action_id"]
            )
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

        self.project.dirty = True
        self._refresh_groups()
        self.project_changed.emit()
        self.lbl_hint.setText(f"🗑 已删除动作「{name}」")

    # ---------- 保存 / 刷新 ----------
    def _on_save(self):
        if not self.project.is_open:
            return
        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self.page_saved.emit()
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    def refresh_from_project(self):
        if not self.project.is_open:
            self.btn_add_group.setEnabled(False)
            self.btn_save.setEnabled(False)
            self._refresh_groups()
            self.lbl_hint.setText("请先创建或打开项目。")
            return
        self.btn_add_group.setEnabled(True)
        self.btn_save.setEnabled(True)
        self._refresh_groups()
        self.lbl_hint.setText("")