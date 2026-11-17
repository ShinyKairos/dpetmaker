import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QFrame, QFileDialog, QMessageBox, QLineEdit,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...core.gif_importer import split_gif_to_frames
from ...core.frame_utils import load_frames_from_dir


class MultiSlotActionPanel(QWidget):
    """多 slot 素材面板基类。

    适用：
      move（左移 / 右移）
      long_idle（开场 / 循环 / 退场）
    不适用：
      touch_special / interact（每 slot 有额外结构，子类自己重写）
    """

    request_preview = pyqtSignal(object, int)
    project_changed = pyqtSignal()
    page_saved = pyqtSignal()

    def __init__(self, title, project, slots, config_fps_key,
                 default_fps=16, parent=None):
        """
        slots: list of dict，每个元素：
            {
                "slot_key":       "left" / "start" 等，仅内部标识
                "display_name":   "左移" / "开场" 等，UI 显示
                "assets_subdir":  "move/left" / "long_idle/start" 等
                "mask_subdir":    "move/left" / "long_idle/start" 等
            }
        """
        super().__init__(parent)
        self.title_text = title
        self.project = project
        self.slots = slots
        self.config_fps_key = config_fps_key
        self.default_fps = default_fps
        self._slot_widgets = {}
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

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel(self.title_text)
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        # 每个 slot 一张卡片
        for slot in self.slots:
            layout.addWidget(self._build_slot_card(slot))

        # 共用 fps
        fps_row = QHBoxLayout()
        fps_row.setSpacing(6)
        lbl_fps = QLabel("帧率（fps）：")
        lbl_fps.setStyleSheet("font-size: 13px;")
        fps_row.addWidget(lbl_fps)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(self.default_fps)
        self.spin_fps.setFixedWidth(90)
        self.spin_fps.valueChanged.connect(self._on_fps_changed)
        fps_row.addWidget(self.spin_fps)
        fps_row.addStretch(1)
        layout.addLayout(fps_row)

        # 保存按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_save = QPushButton("💾 保存本页")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_save)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # 底部提示
        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 12px; padding: 2px 0;")
        layout.addWidget(self.lbl_hint)

        layout.addStretch(1)

    def _build_slot_card(self, slot):
        card = QFrame()
        card.setObjectName(f"card_{slot['slot_key']}")
        card.setStyleSheet(f"""
            QFrame#card_{slot['slot_key']} {{
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }}
            QFrame#card_{slot['slot_key']} QLabel {{
                background: transparent;
                color: #333;
                font-size: 13px;
            }}
            QFrame#card_{slot['slot_key']} QLineEdit {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
                font-family: Consolas, "Courier New", monospace;
            }}
            QFrame#card_{slot['slot_key']} QPushButton {{
                background: #ffffff;
                color: #333;
                border: 1px solid #b8b8b8;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px 8px;
            }}
            QFrame#card_{slot['slot_key']} QPushButton:hover {{
                background: #f0f0f0;
                border-color: #a0a0a0;
            }}
            QFrame#card_{slot['slot_key']} QPushButton:pressed {{
                background: #e0e0e0;
            }}
            QFrame#card_{slot['slot_key']} QPushButton:disabled {{
                background: #f5f5f5;
                color: #aaa;
                border-color: #e0e0e0;
            }}
        """)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        # 标题行
        head = QHBoxLayout()
        head.setSpacing(8)
        lbl_title = QLabel(slot["display_name"])
        lbl_title.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        head.addWidget(lbl_title)
        head.addStretch(1)
        lbl_status = QLabel("（未导入）")
        lbl_status.setStyleSheet(
            "background: transparent; font-size: 12px; color: #888;"
        )
        head.addWidget(lbl_status)
        cl.addLayout(head)

        # 帧目录
        row_frames = QHBoxLayout()
        row_frames.setSpacing(6)
        cap1 = QLabel("帧目录：")
        cap1.setFixedWidth(72)
        cap1.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        row_frames.addWidget(cap1)
        edit_frames = QLineEdit()
        edit_frames.setReadOnly(True)
        edit_frames.setPlaceholderText("—")
        edit_frames.setMinimumHeight(26)
        row_frames.addWidget(edit_frames, 1)
        cl.addLayout(row_frames)

        # 掩码目录
        row_mask = QHBoxLayout()
        row_mask.setSpacing(6)
        cap2 = QLabel("掩码目录：")
        cap2.setFixedWidth(72)
        cap2.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        row_mask.addWidget(cap2)
        edit_mask = QLineEdit()
        edit_mask.setReadOnly(True)
        edit_mask.setPlaceholderText("—")
        edit_mask.setMinimumHeight(26)
        row_mask.addWidget(edit_mask, 1)
        cl.addLayout(row_mask)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_import = QPushButton("📂 导入 GIF")
        btn_import.setFixedHeight(30)
        btn_import.setMinimumWidth(110)
        btn_import.clicked.connect(
            lambda checked=False, s=slot: self._on_import_slot(s)
        )
        btn_row.addWidget(btn_import)

        btn_preview = QPushButton("👁 预览")
        btn_preview.setFixedHeight(30)
        btn_preview.setMinimumWidth(84)
        btn_preview.clicked.connect(
            lambda checked=False, s=slot: self._on_preview_slot(s)
        )
        btn_row.addWidget(btn_preview)

        btn_row.addStretch(1)
        cl.addLayout(btn_row)

        self._slot_widgets[slot["slot_key"]] = {
            "lbl_status": lbl_status,
            "edit_frames": edit_frames,
            "edit_mask": edit_mask,
            "btn_import": btn_import,
            "btn_preview": btn_preview,
        }
        return card

    # ---------- 辅助 ----------
    def _set_path_text(self, widget, path):
        if path:
            widget.setText(path)
            widget.setToolTip(path)
            widget.setCursorPosition(0)
        else:
            widget.setText("")
            widget.setToolTip("")

    def _slot_frames_dir(self, slot):
        return os.path.join(self.project.path, "assets", slot["assets_subdir"])

    def _slot_mask_dir(self, slot):
        return os.path.join(self.project.path, "mask", slot["mask_subdir"])

    def _set_enabled(self, enabled):
        for w in self._slot_widgets.values():
            w["btn_import"].setEnabled(enabled)
            w["btn_preview"].setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.spin_fps.setEnabled(enabled)

    def _update_slot_status(self, slot):
        w = self._slot_widgets[slot["slot_key"]]
        if not self.project.is_open:
            return 0
        frames_dir = self._slot_frames_dir(slot)
        mask_dir = self._slot_mask_dir(slot)
        n = len(load_frames_from_dir(frames_dir))

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
        self._set_path_text(w["edit_frames"], frames_dir)
        self._set_path_text(w["edit_mask"], mask_dir)
        return n

    # ---------- 导入 ----------
    def _on_import_slot(self, slot):
        if not self.project.is_open:
            QMessageBox.warning(self, "无法导入", "请先创建或打开项目。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"选择 {slot['display_name']} GIF", "", "GIF 图片 (*.gif)"
        )
        if not path:
            return

        frames_dir = self._slot_frames_dir(slot)
        mask_dir = self._slot_mask_dir(slot)
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

        # 每次导入自动应用拆出的 fps（共用一个 fps 字段）
        self.spin_fps.blockSignals(True)
        self.spin_fps.setValue(fps)
        self.spin_fps.blockSignals(False)
        self.project.config.setdefault("animation", {})[self.config_fps_key] = int(fps)
        self.project.dirty = True

        # 刷新所有 slot（帧数可能都变了）
        for s in self.slots:
            self._update_slot_status(s)

        self.lbl_hint.setText(
            f"✅ {slot['display_name']}：已拆帧 {len(frames)} 张。"
            f"点『💾 保存本页』写入配置。"
        )
        self.request_preview.emit(frames, fps)
        self.project_changed.emit()

    def _on_preview_slot(self, slot):
        if not self.project.is_open:
            return
        frames = load_frames_from_dir(self._slot_frames_dir(slot))
        if not frames:
            QMessageBox.information(
                self, "无素材",
                f"{slot['display_name']} 尚未导入 GIF。"
            )
            return
        fps = self.project.config.get("animation", {}).get(
            self.config_fps_key, self.default_fps
        )
        self.request_preview.emit(frames, int(fps))

    # ---------- fps ----------
    def _on_fps_changed(self, value):
        if not self.project.is_open:
            return
        self.project.config.setdefault("animation", {})[self.config_fps_key] = int(value)
        self.project.dirty = True
        self.project_changed.emit()

    # ---------- 保存 ----------
    def _on_save(self):
        if not self.project.is_open:
            return
        self.project.config.setdefault("animation", {})[self.config_fps_key] = (
            self.spin_fps.value()
        )
        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self.page_saved.emit()
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    # ---------- 刷新 ----------
    def refresh_from_project(self):
        if not self.project.is_open:
            self._set_enabled(False)
            for w in self._slot_widgets.values():
                w["lbl_status"].setText("（未打开项目）")
                w["lbl_status"].setStyleSheet(
                    "background: transparent; font-size: 12px; color: #888;"
                )
                self._set_path_text(w["edit_frames"], "")
                self._set_path_text(w["edit_mask"], "")
            self.lbl_hint.setText("")
            return

        self._set_enabled(True)

        fps = self.project.config.get("animation", {}).get(
            self.config_fps_key, self.default_fps
        )
        self.spin_fps.blockSignals(True)
        self.spin_fps.setValue(int(fps))
        self.spin_fps.blockSignals(False)

        first_frames = None
        for slot in self.slots:
            n = self._update_slot_status(slot)
            if first_frames is None and n > 0:
                first_frames = load_frames_from_dir(self._slot_frames_dir(slot))

        if first_frames:
            self.request_preview.emit(first_frames, int(fps))
            self.lbl_hint.setText("")
        else:
            self.lbl_hint.setText("尚未导入素材。点各卡片的『📂 导入 GIF』开始。")