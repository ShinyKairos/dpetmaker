import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QFrame, QFileDialog, QMessageBox, QLineEdit,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...core.gif_importer import split_gif_to_frames
from ...core.frame_utils import load_frames_from_dir


class BaseActionPanel(QWidget):
    """单 GIF 素材类面板的通用实现。

    适用：
      boot / exit / standby / touch_normal / drag / talk
    不适用：
      move / long_idle / touch_special / interact（各自子类实现）
    """

    request_preview = pyqtSignal(object, int)   # frames list, fps
    project_changed = pyqtSignal()              # 项目 dirty / 保存状态变化
    page_saved = pyqtSignal()

    def __init__(self, title, project,
                 assets_subdir, mask_subdir,
                 config_assets_key, config_fps_key,
                 default_fps=16,
                 parent=None):
        super().__init__(parent)
        self.title_text = title
        self.project = project
        self.assets_subdir = assets_subdir
        self.mask_subdir = mask_subdir
        self.config_assets_key = config_assets_key
        self.config_fps_key = config_fps_key
        self.default_fps = default_fps
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        # 外层滚动容器：内容高度不足时无滚动条，超出时纵向滚动
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

        # ---------- 标题 ----------
        title = QLabel(self.title_text)
        # 不指定 color，跟随系统主题（与左侧资源树一致）
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold;"
            "background: transparent;"
        )
        layout.addWidget(title)

        # ---------- 状态卡片 ----------
        card = QFrame()
        card.setObjectName("status_card")
        # ★ 关键：卡片内所有 QLabel 强制深色文字，不再随系统主题变化
        card.setStyleSheet("""
            QFrame#status_card {
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            QFrame#status_card QLabel {
                background: transparent;
                color: #333;
                font-size: 13px;
            }
            QFrame#status_card QLineEdit {
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
                font-family: Consolas, "Courier New", monospace;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(8)

        # 状态行
        row_status = QHBoxLayout()
        row_status.setSpacing(6)
        lbl_status_caption = QLabel("状态：")
        lbl_status_caption.setFixedWidth(72)
        lbl_status_caption.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 13px;"
        )
        row_status.addWidget(lbl_status_caption)
        self.lbl_status = QLabel("（未导入）")
        self.lbl_status.setWordWrap(True)
        row_status.addWidget(self.lbl_status, 1)
        card_layout.addLayout(row_status)

        # 帧目录行（只读 QLineEdit：长路径横向滚动 + 可复制 + tooltip）
        row_frames = QHBoxLayout()
        row_frames.setSpacing(6)
        lbl_frames_caption = QLabel("帧目录：")
        lbl_frames_caption.setFixedWidth(72)
        lbl_frames_caption.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 13px;"
        )
        row_frames.addWidget(lbl_frames_caption)
        self.lbl_frames_dir = QLineEdit()
        self.lbl_frames_dir.setReadOnly(True)
        self.lbl_frames_dir.setPlaceholderText("—")
        self.lbl_frames_dir.setMinimumHeight(26)
        row_frames.addWidget(self.lbl_frames_dir, 1)
        card_layout.addLayout(row_frames)

        # 掩码目录行
        row_mask = QHBoxLayout()
        row_mask.setSpacing(6)
        lbl_mask_caption = QLabel("掩码目录：")
        lbl_mask_caption.setFixedWidth(72)
        lbl_mask_caption.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 13px;"
        )
        row_mask.addWidget(lbl_mask_caption)
        self.lbl_mask_dir = QLineEdit()
        self.lbl_mask_dir.setReadOnly(True)
        self.lbl_mask_dir.setPlaceholderText("—")
        self.lbl_mask_dir.setMinimumHeight(26)
        row_mask.addWidget(self.lbl_mask_dir, 1)
        card_layout.addLayout(row_mask)

        layout.addWidget(card)

        # ---------- fps 参数 ----------
        fps_row = QHBoxLayout()
        fps_row.setSpacing(6)
        lbl_fps = QLabel("帧率（fps）：")
        lbl_fps.setStyleSheet("font-size: 13px;")  # 颜色跟随系统
        fps_row.addWidget(lbl_fps)
        self.spin_fps = QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(self.default_fps)
        self.spin_fps.setFixedWidth(90)
        self.spin_fps.valueChanged.connect(self._on_fps_changed)
        fps_row.addWidget(self.spin_fps)
        fps_row.addStretch(1)
        layout.addLayout(fps_row)

        # ---------- 按钮行 ----------
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_import = QPushButton("📂 导入 GIF")
        self.btn_import.setFixedHeight(34)
        self.btn_import.setMinimumWidth(120)
        self.btn_import.clicked.connect(self._on_import_gif)
        btn_row.addWidget(self.btn_import)

        self.btn_save = QPushButton("💾 保存本页")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_save)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # ---------- 底部提示 ----------
        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet(
            "font-size: 12px; padding: 2px 0;"
        )
        layout.addWidget(self.lbl_hint)

        layout.addStretch(1)

    # ---------- 状态 ----------
    def _set_enabled(self, enabled):
        self.btn_import.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.spin_fps.setEnabled(enabled)

    def _set_path_text(self, widget, path):
        """把路径写入只读 QLineEdit，并设置 tooltip 显示完整路径。"""
        if path and path != "—":
            widget.setText(path)
            widget.setToolTip(path)
            # 光标置 0：默认显示路径开头（末尾可通过横滚/选中查看）
            widget.setCursorPosition(0)
        else:
            widget.setText("")
            widget.setToolTip("")

    def _update_status(self, frames_dir, mask_dir, n_frames, fps):
        if n_frames > 0:
            self.lbl_status.setText(f"✅ 已导入 · {n_frames} 帧 · {fps} fps")
            self.lbl_status.setStyleSheet(
                "background: transparent; font-size: 13px; color: #2a7a2a;"
            )
        else:
            self.lbl_status.setText("（未导入）")
            self.lbl_status.setStyleSheet(
                "background: transparent; font-size: 13px; color: #888;"
            )
        self._set_path_text(self.lbl_frames_dir, frames_dir)
        self._set_path_text(self.lbl_mask_dir, mask_dir)

    def _clear_status(self):
        self.lbl_status.setText("（未打开项目）")
        self.lbl_status.setStyleSheet(
            "background: transparent; font-size: 13px; color: #888;"
        )
        self._set_path_text(self.lbl_frames_dir, "")
        self._set_path_text(self.lbl_mask_dir, "")
        self.lbl_hint.setText("")

    # ---------- 路径 ----------
    def _frames_dir(self):
        return os.path.join(self.project.path, "assets", self.assets_subdir)

    def _mask_dir(self):
        return os.path.join(self.project.path, "mask", self.mask_subdir)

    # ---------- 导入 ----------
    def _on_import_gif(self):
        if not self.project.is_open:
            QMessageBox.warning(self, "无法导入", "请先创建或打开项目。")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, f"选择 {self.title_text} GIF", "", "GIF 图片 (*.gif)"
        )
        if not path:
            return

        frames_dir = self._frames_dir()
        mask_dir = self._mask_dir()
        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(mask_dir, exist_ok=True)

        ok, frames, fps, err = split_gif_to_frames(
            path, frames_dir, mask_dir,
            preview_frame_index=0,   # E 阶段固定 0；互动面板会覆盖为可选
            target_size=(
                self.project.config["window"]["width"],
                self.project.config["window"]["height"],
            ),
            clear_before=True,
        )
        if not ok:
            QMessageBox.warning(self, "导入失败", err)
            return

        # 自动应用 fps
        self.spin_fps.blockSignals(True)
        self.spin_fps.setValue(fps)
        self.spin_fps.blockSignals(False)
        self.project.config["animation"][self.config_fps_key] = int(fps)
        self.project.dirty = True

        self._update_status(frames_dir, mask_dir, len(frames), fps)
        self.lbl_hint.setText(
            f"✅ 已拆帧 {len(frames)} 张。点『💾 保存本页』写入配置。"
        )
        self.request_preview.emit(frames, fps)
        self.project_changed.emit()

    # ---------- fps 修改 ----------
    def _on_fps_changed(self, value):
        if not self.project.is_open:
            return
        self.project.config["animation"][self.config_fps_key] = int(value)
        self.project.dirty = True
        frames_dir = self._frames_dir()
        mask_dir = self._mask_dir()
        n = len(load_frames_from_dir(frames_dir))
        self._update_status(frames_dir, mask_dir, n, value)
        self.project_changed.emit()

    # ---------- 保存 ----------
    def _on_save(self):
        if not self.project.is_open:
            return
        self.project.config["animation"][self.config_fps_key] = self.spin_fps.value()
        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self.page_saved.emit()
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    # ---------- 刷新（切面板时由主窗调用）----------
    def refresh_from_project(self):
        if not self.project.is_open:
            self._set_enabled(False)
            self._clear_status()
            return

        self._set_enabled(True)

        # 1. fps
        fps = self.project.config.get("animation", {}).get(
            self.config_fps_key, self.default_fps
        )
        self.spin_fps.blockSignals(True)
        self.spin_fps.setValue(int(fps))
        self.spin_fps.blockSignals(False)

        # 2. 扫当前帧目录
        frames_dir = self._frames_dir()
        mask_dir = self._mask_dir()
        frames = load_frames_from_dir(frames_dir)
        self._update_status(frames_dir, mask_dir, len(frames), fps)

        # 3. 触发预览
        if frames:
            self.request_preview.emit(frames, int(fps))
            self.lbl_hint.setText("")
        else:
            self.lbl_hint.setText(
                f"尚未导入素材。点『📂 导入 GIF』开始，帧将写入：{frames_dir}"
            )