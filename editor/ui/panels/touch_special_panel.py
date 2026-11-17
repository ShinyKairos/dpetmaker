import os
import shutil
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox, QScrollArea, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QRectF

from ...core.gif_importer import split_gif_to_frames
from ...core.frame_utils import load_frames_from_dir


class SpecialTouchPanel(QWidget):
    """特殊触摸面板：多条目列表 + 每条独立素材目录 + 框选触发区域。

    F-2 状态：
      - 每条独立卡片，支持命名、导入素材、框选 area_ratio。
      - 预览区通过 set_preview_area() 由 MainWindow 注入。
      - 框选期间，本面板 _active_sid 非空，其他卡片的框选按钮禁用。
    F-3 待办：
      - 画新框时对已有矩形做重叠校验，重叠则禁用"确认"。
    """

    request_preview = pyqtSignal(object, int)
    project_changed = pyqtSignal()
    page_saved = pyqtSignal()

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._cards = {}                # sid -> widget dict
        self._preview_area = None       # PreviewPanel 引用（MainWindow 注入）
        self._active_sid = None         # 正在框选的 sid
        self._build_ui()

    # ===================== 由 MainWindow 调用 =====================
    def set_preview_area(self, preview_area):
        if getattr(self, "_preview_area", None):
            try:
                self._preview_area.selection_rect_changed.disconnect(self._on_preview_selection_changed)
            except TypeError:
                pass
        self._preview_area = preview_area
        if self._preview_area:
            self._preview_area.selection_rect_changed.connect(self._on_preview_selection_changed)

    # ===================== UI 骨架 =====================
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

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("特殊触摸")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "可创建多个特殊触摸，每条独立绑定素材目录与触发区域。\n"
            "点『🔲 框选触发区域』→ 在预览区拖拽画框 → 点『✓ 确认选择』生效。"
            "触发区域不可重叠（F-3 将加入重叠校验）。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #666; background: transparent;")
        layout.addWidget(desc)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(10)
        layout.addWidget(self._cards_container)

        add_row = QHBoxLayout()
        add_row.setSpacing(8)
        self.btn_add = QPushButton("＋ 添加特殊触摸")
        self.btn_add.setFixedHeight(34)
        self.btn_add.setMinimumWidth(140)
        self.btn_add.clicked.connect(self._on_add)
        add_row.addWidget(self.btn_add)
        add_row.addStretch(1)
        layout.addLayout(add_row)

        save_row = QHBoxLayout()
        save_row.setSpacing(8)
        self.btn_save = QPushButton("💾 保存本页")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self.btn_save)
        save_row.addStretch(1)
        layout.addLayout(save_row)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 12px; padding: 2px 0;")
        layout.addWidget(self.lbl_hint)

        layout.addStretch(1)

    def _card_style(self, object_name):
        return f"""
            QFrame#{object_name} {{
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }}
            QFrame#{object_name} QLabel {{
                background: transparent;
                color: #333;
                font-size: 13px;
            }}
            QFrame#{object_name} QLineEdit {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
                min-height: 22px;
            }}
            QFrame#{object_name} QLineEdit:read-only {{
                color: #666;
                font-family: Consolas, "Courier New", monospace;
            }}
            QFrame#{object_name} QPushButton {{
                background: #ffffff;
                color: #333;
                border: 1px solid #b8b8b8;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px 8px;
            }}
            QFrame#{object_name} QPushButton:hover {{
                background: #f0f0f0;
                border-color: #a0a0a0;
            }}
            QFrame#{object_name} QPushButton:pressed {{
                background: #e0e0e0;
            }}
            QFrame#{object_name} QPushButton:disabled {{
                background: #f5f5f5;
                color: #aaa;
                border-color: #e0e0e0;
            }}
            QFrame#{object_name} QPushButton#btn_delete {{
                background: #fff0f0;
                color: #c0392b;
                border: 1px solid #e8b8b8;
            }}
            QFrame#{object_name} QPushButton#btn_delete:hover {{
                background: #ffe0e0;
                border-color: #d04040;
            }}
        """

    # ===================== 路径解析 =====================
    def _resolve_dirs(self, special):
        rel_path = special.get("path", "")
        if rel_path.startswith("./") or rel_path.startswith(".\\"):
            rel = rel_path[2:]
        else:
            rel = rel_path
        rel_norm = rel.replace("\\", "/")
        frames_abs = os.path.join(self.project.path, rel_norm)
        parts = rel_norm.split("/")
        if parts and parts[0] == "assets":
            parts[0] = "mask"
        mask_abs = os.path.join(self.project.path, "/".join(parts))
        return frames_abs, mask_abs

    def _has_valid_area(self, special):
        r = special.get("area_ratio") or {}
        try:
            return float(r.get("width", 0)) > 0 and float(r.get("height", 0)) > 0
        except (TypeError, ValueError):
            return False

    # ===================== 卡片构建 =====================
    def _build_card(self, special):
        sid = special["id"]
        obj_name = f"card_{sid}"
        card = QFrame()
        card.setObjectName(obj_name)
        card.setStyleSheet(self._card_style(obj_name))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        # ---------- 头：名称 + 删除 ----------
        head = QHBoxLayout()
        head.setSpacing(8)
        lbl_name = QLabel("名称：")
        lbl_name.setFixedWidth(64)
        lbl_name.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        head.addWidget(lbl_name)

        edit_name = QLineEdit()
        edit_name.setText(special.get("name", sid))
        edit_name.textChanged.connect(
            lambda text, s=sid: self._on_name_changed(s, text)
        )
        head.addWidget(edit_name, 1)

        btn_delete = QPushButton("🗑 删除")
        btn_delete.setObjectName("btn_delete")
        btn_delete.setFixedHeight(28)
        btn_delete.setMinimumWidth(72)
        btn_delete.clicked.connect(
            lambda checked=False, s=sid: self._on_delete(s)
        )
        head.addWidget(btn_delete)
        cl.addLayout(head)

        # ---------- 帧目录 ----------
        row_f = QHBoxLayout()
        row_f.setSpacing(6)
        c1 = QLabel("帧目录：")
        c1.setFixedWidth(64)
        c1.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        row_f.addWidget(c1)
        edit_frames = QLineEdit()
        edit_frames.setReadOnly(True)
        edit_frames.setPlaceholderText("—")
        row_f.addWidget(edit_frames, 1)
        cl.addLayout(row_f)

        # ---------- 掩码目录 ----------
        row_m = QHBoxLayout()
        row_m.setSpacing(6)
        c2 = QLabel("掩码目录：")
        c2.setFixedWidth(64)
        c2.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        row_m.addWidget(c2)
        edit_mask = QLineEdit()
        edit_mask.setReadOnly(True)
        edit_mask.setPlaceholderText("—")
        row_m.addWidget(edit_mask, 1)
        cl.addLayout(row_m)

        # ---------- 触发区域（动态显示）----------
        row_a = QHBoxLayout()
        row_a.setSpacing(6)
        c3 = QLabel("触发区域：")
        c3.setFixedWidth(64)
        c3.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        row_a.addWidget(c3)
        lbl_area = QLabel()
        lbl_area.setWordWrap(True)
        row_a.addWidget(lbl_area, 1)
        cl.addLayout(row_a)

        # ---------- 素材状态 + 导入/预览 ----------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        lbl_status = QLabel("（未导入）")
        lbl_status.setStyleSheet(
            "background: transparent; font-size: 12px; color: #888;"
        )
        btn_row.addWidget(lbl_status)
        btn_row.addStretch(1)

        btn_import = QPushButton("📂 导入 GIF")
        btn_import.setFixedHeight(28)
        btn_import.setMinimumWidth(110)
        btn_import.clicked.connect(
            lambda checked=False, sp=special: self._on_import(sp)
        )
        btn_row.addWidget(btn_import)

        btn_preview = QPushButton("👁 预览")
        btn_preview.setFixedHeight(28)
        btn_preview.setMinimumWidth(84)
        btn_preview.clicked.connect(
            lambda checked=False, sp=special: self._on_preview(sp)
        )
        btn_row.addWidget(btn_preview)
        cl.addLayout(btn_row)

        # ---------- 框选按钮组 ----------
        select_row = QHBoxLayout()
        select_row.setSpacing(6)

        btn_select = QPushButton("🔲 框选触发区域")
        btn_select.setFixedHeight(28)
        btn_select.setMinimumWidth(140)
        btn_select.clicked.connect(
            lambda checked=False, sp=special: self._on_start_select(sp)
        )
        select_row.addWidget(btn_select)

        btn_confirm = QPushButton("✓ 确认选择")
        btn_confirm.setFixedHeight(28)
        btn_confirm.setMinimumWidth(110)
        btn_confirm.setStyleSheet(
            "QPushButton {"
            " background: #e8f5e8; color: #2a7a2a; border: 1px solid #a0d0a0;"
            " border-radius: 4px; font-size: 12px; padding: 2px 8px;"
            "}"
            "QPushButton:hover { background: #d8f0d8; border-color: #80c080; }"
            "QPushButton:pressed { background: #c8e8c8; }"
        )
        btn_confirm.clicked.connect(
            lambda checked=False, sp=special: self._on_confirm_select(sp)
        )
        btn_confirm.hide()
        select_row.addWidget(btn_confirm)

        btn_cancel = QPushButton("✕ 取消")
        btn_cancel.setFixedHeight(28)
        btn_cancel.setMinimumWidth(80)
        btn_cancel.setStyleSheet(
            "QPushButton {"
            " background: #fff0f0; color: #c0392b; border: 1px solid #e8b8b8;"
            " border-radius: 4px; font-size: 12px; padding: 2px 8px;"
            "}"
            "QPushButton:hover { background: #ffe0e0; border-color: #d04040; }"
            "QPushButton:pressed { background: #ffd0d0; }"
        )
        btn_cancel.clicked.connect(
            lambda checked=False, sp=special: self._on_cancel_select(sp)
        )
        btn_cancel.hide()
        select_row.addWidget(btn_cancel)

        select_row.addStretch(1)
        cl.addLayout(select_row)

        self._cards[sid] = {
            "special_ref": special,
            "edit_name": edit_name,
            "edit_frames": edit_frames,
            "edit_mask": edit_mask,
            "lbl_status": lbl_status,
            "lbl_area": lbl_area,
            "btn_select": btn_select,
            "btn_confirm": btn_confirm,
            "btn_cancel": btn_cancel,
        }
        self._update_card_area_display(sid)
        return card

    def _update_card_area_display(self, sid):
        if sid not in self._cards:
            return
        w = self._cards[sid]
        special = w["special_ref"]
        if self._has_valid_area(special):
            r = special["area_ratio"]
            w["lbl_area"].setText(
                f"✅ x={float(r['x']):.4f} · y={float(r['y']):.4f} · "
                f"w={float(r['width']):.4f} · h={float(r['height']):.4f}"
            )
            w["lbl_area"].setStyleSheet(
                "background: transparent; color: #2a7a2a; font-size: 12px;"
            )
        else:
            w["lbl_area"].setText("⚠ 未设置（点下方『🔲 框选触发区域』）")
            w["lbl_area"].setStyleSheet(
                "background: transparent; color: #c0392b; font-size: 12px;"
            )

    def _update_card_status(self, sid):
        if sid not in self._cards or not self.project.is_open:
            return
        w = self._cards[sid]
        special = w["special_ref"]
        frames_abs, mask_abs = self._resolve_dirs(special)
        n = len(load_frames_from_dir(frames_abs))

        if n > 0:
            w["lbl_status"].setText(f"✅ {n} 帧")
            w["lbl_status"].setStyleSheet(
                "background: transparent; font-size: 12px; color: #2a7a2a;"
            )
        else:
            w["lbl_status"].setText("（未导入）")
            w["lbl_status"].setStyleSheet(
                "background: transparent; font-size: 12px; color: #888;"
            )
        w["edit_frames"].setText(frames_abs)
        w["edit_frames"].setToolTip(frames_abs)
        w["edit_frames"].setCursorPosition(0)
        w["edit_mask"].setText(mask_abs)
        w["edit_mask"].setToolTip(mask_abs)
        w["edit_mask"].setCursorPosition(0)

    def _refresh_cards(self):
        while self._cards_layout.count() > 0:
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards = {}

        if not self.project.is_open:
            return

        specials = self.project.config.get("assets", {}).get("special_touches", [])
        if not specials:
            lbl_empty = QLabel("暂无特殊触摸。点下方『＋ 添加特殊触摸』创建。")
            lbl_empty.setStyleSheet(
                "font-size: 13px; color: #888; padding: 30px;"
            )
            lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._cards_layout.addWidget(lbl_empty)
            return

        for special in specials:
            card = self._build_card(special)
            self._cards_layout.addWidget(card)
            self._update_card_status(special["id"])

        # 若框选中的条目已不存在，自动退出
        if self._active_sid is not None and self._active_sid not in self._cards:
            self._active_sid = None
            if self._preview_area is not None:
                self._preview_area.exit_selection_mode()

        self._apply_select_ui_state()

    def _set_enabled(self, enabled):
        self.btn_add.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    # ===================== 框选状态管理 =====================
    def _apply_select_ui_state(self):
        """按 _active_sid 更新所有卡片的框选按钮显示。"""
        for sid, w in self._cards.items():
            is_active = (sid == self._active_sid)
            other_locked = (self._active_sid is not None and not is_active)

            if is_active:
                w["btn_select"].hide()
                w["btn_confirm"].show()
                w["btn_cancel"].show()
                w["btn_import"].setEnabled(False) if "btn_import" in w else None
            else:
                w["btn_select"].show()
                w["btn_select"].setEnabled(not other_locked)
                w["btn_confirm"].hide()
                w["btn_cancel"].hide()

    def _reset_select_state(self):
        """切面板时由 MainWindow 调用：退出框选（不写 config）。"""
        if self._active_sid is not None and self._preview_area is not None:
            self._preview_area.exit_selection_mode()
        self._active_sid = None
        self._apply_select_ui_state()

    # ===================== 事件：名称 / 增删 =====================
    def _on_name_changed(self, sid, text):
        if not self.project.is_open:
            return
        if sid in self._cards:
            self._cards[sid]["special_ref"]["name"] = text
            self.project.dirty = True
            self.project_changed.emit()

    def _on_add(self):
        if not self.project.is_open:
            return
        specials = self.project.config.setdefault("assets", {}).setdefault(
            "special_touches", []
        )
        used = set()
        for sp in specials:
            sid = sp.get("id", "")
            if sid.startswith("special") and sid[7:].isdigit():
                used.add(int(sid[7:]))
        next_n = 1
        while next_n in used:
            next_n += 1
        new_id = f"special{next_n}"
        new_name = f"特殊触摸{next_n}"
        new_path_rel = f"./assets/touch/{new_id}"

        frames_dir = os.path.join(self.project.path, "assets", "touch", new_id)
        mask_dir = os.path.join(self.project.path, "mask", "touch", new_id)
        try:
            os.makedirs(frames_dir, exist_ok=True)
            os.makedirs(mask_dir, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "创建目录失败", str(e))
            return

        specials.append({
            "id": new_id,
            "name": new_name,
            "path": new_path_rel,
            # ★ F-2：全 0 视为"未设置"，强制用户框选
            "area_ratio": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
        })

        self.project.dirty = True
        self._refresh_cards()
        self.project_changed.emit()
        self.lbl_hint.setText(
            f"✅ 已添加「{new_name}」· 请导入素材后框选触发区域"
        )

    def _on_delete(self, sid):
        if not self.project.is_open or sid not in self._cards:
            return
        special = self._cards[sid]["special_ref"]
        name = special.get("name", sid)

        # ★ 若删除的是当前框选中的条目，先退出框选
        if self._active_sid == sid:
            if self._preview_area is not None:
                self._preview_area.exit_selection_mode()
            self._active_sid = None

        ret = QMessageBox.question(
            self, "删除特殊触摸",
            f"确定删除「{name}」吗？\n"
            f"对应的素材目录（assets/touch/{sid}）也会被删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        specials = self.project.config.get("assets", {}).get("special_touches", [])
        self.project.config["assets"]["special_touches"] = [
            sp for sp in specials if sp.get("id") != sid
        ]

        try:
            frames_dir = os.path.join(self.project.path, "assets", "touch", sid)
            mask_dir = os.path.join(self.project.path, "mask", "touch", sid)
            if os.path.isdir(frames_dir):
                shutil.rmtree(frames_dir, ignore_errors=True)
            if os.path.isdir(mask_dir):
                shutil.rmtree(mask_dir, ignore_errors=True)
        except Exception as e:
            print(f"⚠ 删除目录失败：{e}")

        self.project.dirty = True
        self._refresh_cards()
        self.project_changed.emit()
        self.lbl_hint.setText(f"🗑 已删除「{name}」")

    # ===================== 事件：导入 / 预览 =====================
    def _on_import(self, special):
        if not self.project.is_open:
            return
        sid = special["id"]
        display = special.get("name", sid)
        path, _ = QFileDialog.getOpenFileName(
            self, f"选择 {display} GIF", "", "GIF 图片 (*.gif)"
        )
        if not path:
            return

        frames_dir, mask_dir = self._resolve_dirs(special)
        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(mask_dir, exist_ok=True)

        ok, frames, fps, err = split_gif_to_frames(
            path, frames_dir, mask_dir,
            preview_frame_index=0,
            target_size=(
                self.project.config["window"]["width"],
                self.project.config["window"]["height"],
            ),
            clear_before=True,
        )
        if not ok:
            QMessageBox.warning(self, "导入失败", err)
            return

        self._update_card_status(sid)
        self.project.dirty = True
        self.project_changed.emit()
        self.lbl_hint.setText(
            f"✅ {display}：已拆帧 {len(frames)} 张。"
            "接下来点『🔲 框选触发区域』设置触发位置。"
        )

        touch_fps = self.project.config.get("animation", {}).get("touch_fps", 16)
        self.request_preview.emit(frames, int(touch_fps))

    def _on_preview(self, special):
        if not self.project.is_open:
            return
        frames_dir, _ = self._resolve_dirs(special)
        frames = load_frames_from_dir(frames_dir)
        if not frames:
            QMessageBox.information(
                self, "无素材",
                f"{special.get('name', special['id'])} 尚未导入 GIF。"
            )
            return
        touch_fps = self.project.config.get("animation", {}).get("touch_fps", 16)
        self.request_preview.emit(frames, int(touch_fps))

    # ===================== 事件：框选三连 =====================
    def _on_start_select(self, special):
        if not self.project.is_open:
            return
        if self._preview_area is None:
            QMessageBox.warning(
                self, "无法框选",
                "预览区未初始化，请重启制作器。"
            )
            return
        if self._active_sid is not None:
            QMessageBox.information(
                self, "已在框选",
                "请先完成或取消当前的框选操作。"
            )
            return

        sid = special["id"]

        # ★ 先确保预览区显示当前条目的素材
        frames_dir, _ = self._resolve_dirs(special)
        frames = load_frames_from_dir(frames_dir)
        if not frames:
            QMessageBox.information(
                self, "无素材",
                f"「{special.get('name', sid)}」尚未导入 GIF。\n"
                "请先点『📂 导入 GIF』导入素材，再框选触发区域。"
            )
            return
        touch_fps = self.project.config.get("animation", {}).get("touch_fps", 16)
        self._preview_area.set_frames(frames, int(touch_fps), autoplay=True)

        # 收集其他条目已有的矩形（红色参考）
        existing = []
        for sp in self.project.config.get("assets", {}).get("special_touches", []):
            if sp["id"] == sid:
                continue
            if self._has_valid_area(sp):
                r = sp["area_ratio"]
                existing.append(QRectF(
                    float(r["x"]), float(r["y"]),
                    float(r["width"]), float(r["height"]),
                ))

        # 当前条目的已有矩形（蓝色回显）
        editing = None
        if self._has_valid_area(special):
            r = special["area_ratio"]
            editing = QRectF(
                float(r["x"]), float(r["y"]),
                float(r["width"]), float(r["height"]),
            )

        self._active_sid = sid
        self._preview_area.enter_selection_mode(editing, existing)
        self._apply_select_ui_state()
        
        # 立即检查一次当前状态（可能回显了已有区域）
        rect = self._preview_area.get_pending_rect()
        if rect is None:
            self._on_preview_selection_changed(None, False)
        else:
            is_overlap = not self._preview_area.is_pending_rect_valid()
            self._on_preview_selection_changed(rect, is_overlap)

    def _on_confirm_select(self, special):
        if self._active_sid != special["id"]:
            return
        if self._preview_area is None:
            return
        rect = self._preview_area.get_pending_rect()
        if rect is None:
            QMessageBox.information(
                self, "无选择",
                "请先在预览区拖动鼠标画出一个矩形，再点『✓ 确认选择』。\n"
                "（若已画过，可能是矩形太小被忽略，请重画一个略大的）"
            )
            return
        if not self._preview_area.is_pending_rect_valid():
            QMessageBox.warning(
                self, "区域重叠",
                "当前画框与已有特殊触摸区域重叠，无法保存。\n请重新框选不重叠的区域。"
            )
            return

        # 写入 config

        special["area_ratio"] = {
            "x": round(rect.x(), 4),
            "y": round(rect.y(), 4),
            "width": round(rect.width(), 4),
            "height": round(rect.height(), 4),
        }
        self.project.dirty = True
        self.project_changed.emit()

        self._preview_area.exit_selection_mode()
        self._active_sid = None
        self._refresh_cards()
        self.lbl_hint.setText(
            f"✅ 已设置「{special.get('name', special['id'])}」的触发区域。"
            "点『💾 保存本页』写入配置。"
        )

    def _on_preview_selection_changed(self, rect, is_overlapping):
        if not self._active_sid:
            return
        w = self._cards.get(self._active_sid)
        if not w:
            return
        
        if rect is None or is_overlapping:
            w["btn_confirm"].setEnabled(False)
            if is_overlapping:
                self.lbl_hint.setText("⚠ 画框与已有特殊触摸区域重叠，请重新框选不重叠的区域。")
                self.lbl_hint.setStyleSheet("font-size: 12px; color: #d04040; padding: 2px 0;")
            else:
                self.lbl_hint.setText("请先在预览区拖动鼠标画出一个矩形。")
                self.lbl_hint.setStyleSheet("font-size: 12px; padding: 2px 0;")
        else:
            w["btn_confirm"].setEnabled(True)
            self.lbl_hint.setText("✅ 区域有效。点『✓ 确认选择』保存。")
            self.lbl_hint.setStyleSheet("font-size: 12px; color: #2a7a2a; padding: 2px 0;")

    def _on_cancel_select(self, special):
        if self._preview_area is not None:
            self._preview_area.exit_selection_mode()
        self._active_sid = None
        self._refresh_cards()
        self.lbl_hint.setText("已取消框选。")

    # ===================== 保存 =====================
    def _on_save(self):
        if not self.project.is_open:
            return
        # 再次同步名称（保险）
        for sid, w in self._cards.items():
            special = w["special_ref"]
            name = w["edit_name"].text().strip()
            special["name"] = name if name else sid

        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self.page_saved.emit()
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    # ===================== 刷新 =====================
    def refresh_from_project(self):
        if not self.project.is_open:
            self._set_enabled(False)
            self._refresh_cards()
            self.lbl_hint.setText("请先创建或打开项目。")
            return

        self._set_enabled(True)
        self._refresh_cards()
        self.lbl_hint.setText("")

        # 自动预览第一个有素材的
        specials = self.project.config.get("assets", {}).get("special_touches", [])
        for sp in specials:
            frames_dir, _ = self._resolve_dirs(sp)
            frames = load_frames_from_dir(frames_dir)
            if frames:
                touch_fps = self.project.config.get("animation", {}).get("touch_fps", 16)
                self.request_preview.emit(frames, int(touch_fps))
                return