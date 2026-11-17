import os
import shutil
from copy import deepcopy

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QMessageBox, QFileDialog, QDialog,
    QFormLayout, QSpinBox, QPlainTextEdit, QTabWidget
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, pyqtSignal

from ...core.gif_importer import split_gif_to_frames
from ...core.frame_utils import load_frames_from_dir
from ..widgets.spin_row import make_spin_row
from .preview_frame_dialog import PreviewFrameDialog


class ActionEditorDialog(QDialog):
    """编辑单个互动动作（create 或 edit 模式）。"""

    request_preview = pyqtSignal(object, int)

    def __init__(self, project, group_id, action_data, mode="edit", parent=None):
        super().__init__(parent)
        self._project = project
        self._group_id = group_id
        self._action_data = deepcopy(action_data)
        self._mode = mode
        self._slot_widgets = {}
        self._build_ui()
        self._load_from_action()

    # ---------- UI ----------
    def _build_ui(self):
        self.setWindowTitle(
            "新建互动动作" if self._mode == "create" else "编辑互动动作"
        )
        self.resize(580, 660)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        action_type = self._action_data.get("type", "instant")
        type_name = "瞬时互动（播放 1 次）" if action_type == "instant" else "持续互动（开场/循环/退场）"
        lbl_type = QLabel(type_name)
        lbl_type.setStyleSheet("color: #666; font-size: 13px;")
        form.addRow("类型：", lbl_type)

        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("动作名称（显示在互动选择窗口）")
        self._edit_name.setMinimumHeight(26)
        form.addRow("名称：", self._edit_name)

        self._spin_fps = QSpinBox()
        self._spin_fps.setRange(1, 60)
        self._spin_fps.setValue(int(self._action_data.get("fps", 16)))
        form.addRow("帧率（fps）：", make_spin_row(self._spin_fps, 1, width=160))

        layout.addLayout(form)

        if action_type == "continuous":
            prompt_frame = QFrame()
            prompt_frame.setStyleSheet(
                "QFrame { background: #f8f9fa; border: 1px solid #e0e0e0;"
                " border-radius: 6px; }"
                "QFrame QLabel { background: transparent; color: #333; font-size: 13px; }"
            )
            pl = QVBoxLayout(prompt_frame)
            pl.setContentsMargins(12, 8, 12, 8)
            pl.setSpacing(4)
            lbl = QLabel("互动状态提示词（对话中触发时注入系统提示词）：")
            lbl.setStyleSheet(
                "background: transparent; color: #555; font-size: 12px; font-weight: bold;"
            )
            pl.addWidget(lbl)
            self._edit_prompt = QPlainTextEdit()
            self._edit_prompt.setMinimumHeight(80)
            self._edit_prompt.setPlaceholderText(
                "例如：**互动状态**{{char}}正在坐着休息，语气慵懒放松"
            )
            self._edit_prompt.setStyleSheet(
                "background: #ffffff; color: #333;"
                " border: 1px solid #d0d0d0; border-radius: 3px; padding: 4px;"
            )
            pl.addWidget(self._edit_prompt)
            layout.addWidget(prompt_frame)
        else:
            self._edit_prompt = None

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs, 1)

        if action_type == "instant":
            self._tabs.addTab(self._build_slot_tab("main", "素材"), "素材")
        else:
            self._tabs.addTab(self._build_slot_tab("start", "开场"), "开场")
            self._tabs.addTab(self._build_slot_tab("loop", "循环"), "循环")
            self._tabs.addTab(self._build_slot_tab("end", "退场"), "退场")

        btns = QHBoxLayout()
        btns.addStretch(1)
        self._btn_ok = QPushButton("确定")
        self._btn_ok.setFixedHeight(34)
        self._btn_ok.setMinimumWidth(100)
        self._btn_ok.clicked.connect(self._on_ok)
        btns.addWidget(self._btn_ok)
        self._btn_cancel = QPushButton("取消")
        self._btn_cancel.setFixedHeight(34)
        self._btn_cancel.setMinimumWidth(100)
        self._btn_cancel.clicked.connect(self.reject)
        btns.addWidget(self._btn_cancel)
        btns.addStretch(1)
        layout.addLayout(btns)

    def _build_slot_tab(self, slot_key, title):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(6)
        cap = QLabel("帧目录：")
        cap.setStyleSheet(
            "background: transparent; color: #555; font-weight: bold; font-size: 12px;"
        )
        cap.setFixedWidth(64)
        row.addWidget(cap)
        edit_dir = QLineEdit()
        edit_dir.setReadOnly(True)
        edit_dir.setMinimumHeight(28)
        edit_dir.setStyleSheet(
            "background: #f8f8f8; color: #333; border: 1px solid #d0d0d0;"
            " border-radius: 3px; padding: 3px 6px;"
            " font-size: 12px; font-family: Consolas, monospace;"
        )
        row.addWidget(edit_dir, 1)
        v.addLayout(row)

        info_row = QHBoxLayout()
        info_row.setSpacing(12)
        preview_label = QLabel()
        preview_label.setFixedSize(96, 96)
        preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_label.setStyleSheet(
            "background: #fafafa; border: 1px dashed #c0c0c0; border-radius: 4px;"
        )
        info_row.addWidget(preview_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        lbl_count = QLabel("帧数：—")
        lbl_count.setStyleSheet("color: #333; font-size: 12px;")
        info_col.addWidget(lbl_count)
        lbl_preview_status = QLabel("预览图：—")
        lbl_preview_status.setStyleSheet("color: #666; font-size: 11px;")
        lbl_preview_status.setWordWrap(True)
        info_col.addWidget(lbl_preview_status)
        info_col.addStretch(1)
        info_row.addLayout(info_col, 1)
        v.addLayout(info_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_import = QPushButton("📂 导入 GIF")
        btn_import.setFixedHeight(30)
        btn_import.setMinimumWidth(110)
        btn_import.clicked.connect(lambda checked=False, s=slot_key: self._on_import_slot(s))
        btn_row.addWidget(btn_import)

        btn_pick = QPushButton("🎬 选预览帧")
        btn_pick.setFixedHeight(30)
        btn_pick.setMinimumWidth(110)
        btn_pick.clicked.connect(lambda checked=False, s=slot_key: self._on_pick_preview(s))
        btn_row.addWidget(btn_pick)

        btn_play = QPushButton("▶ 预览")
        btn_play.setFixedHeight(30)
        btn_play.setMinimumWidth(84)
        btn_play.clicked.connect(lambda checked=False, s=slot_key: self._on_play_slot(s))
        btn_row.addWidget(btn_play)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

        v.addStretch(1)

        self._slot_widgets[slot_key] = {
            "edit_dir": edit_dir,
            "preview_label": preview_label,
            "lbl_count": lbl_count,
            "lbl_preview_status": lbl_preview_status,
        }
        return w

    # ---------- 路径 ----------
    def _action_base_abs(self):
        rel = self._action_data["path"]
        if rel.startswith("./") or rel.startswith(".\\"):
            rel = rel[2:]
        rel_norm = rel.replace("\\", "/")
        return os.path.join(self._project.path, rel_norm)

    def _slot_frames_dir(self, slot_key):
        base = self._action_base_abs()
        if self._action_data["type"] == "instant":
            return base
        return os.path.join(base, slot_key)

    def _slot_mask_dir(self, slot_key):
        frames_dir = self._slot_frames_dir(slot_key)
        rel = os.path.relpath(frames_dir, self._project.path)
        parts = rel.replace("\\", "/").split("/")
        if parts and parts[0] == "assets":
            parts[0] = "mask"
        return os.path.join(self._project.path, *parts)

    def _action_preview_path(self):
        return os.path.join(self._action_base_abs(), "preview.png")

    # ---------- 加载 ----------
    def _load_from_action(self):
        self._edit_name.setText(self._action_data.get("action_name", ""))
        if self._edit_prompt is not None:
            self._edit_prompt.setPlainText(self._action_data.get("prompt", ""))
        for slot_key in self._slot_widgets:
            self._update_slot_display(slot_key)

    def _update_slot_display(self, slot_key):
        w = self._slot_widgets[slot_key]
        frames_dir = self._slot_frames_dir(slot_key)
        frames = load_frames_from_dir(frames_dir)

        w["edit_dir"].setText(frames_dir)
        w["edit_dir"].setToolTip(frames_dir)
        w["edit_dir"].setCursorPosition(0)
        w["lbl_count"].setText(f"帧数：{len(frames)} 帧")

        preview_path = self._action_preview_path()
        if os.path.exists(preview_path):
            pix = QPixmap(preview_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    96, 96,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                w["preview_label"].setPixmap(scaled)
                w["lbl_preview_status"].setText("预览图：已设置")
                return
        w["preview_label"].clear()
        w["preview_label"].setText("未设置")
        w["lbl_preview_status"].setText("预览图：未设置（首次导入 GIF 自动取第 1 帧）")

    # ---------- 事件 ----------
    def _on_import_slot(self, slot_key):
        path, _ = QFileDialog.getOpenFileName(
            self, f"选择 GIF", "", "GIF 图片 (*.gif)"
        )
        if not path:
            return

        frames_dir = self._slot_frames_dir(slot_key)
        mask_dir = self._slot_mask_dir(slot_key)
        os.makedirs(frames_dir, exist_ok=True)
        os.makedirs(mask_dir, exist_ok=True)

        ok, frames, fps, err = split_gif_to_frames(
            path, frames_dir, mask_dir,
            preview_frame_index=0,
            target_size=(
                self._project.config["window"]["width"],
                self._project.config["window"]["height"],
            ),
            clear_before=True,
        )
        if not ok:
            QMessageBox.warning(self, "导入失败", err)
            return

        # 首次导入自动应用 fps（用户可改）
        if not self._action_data.get("fps"):
            self._spin_fps.setValue(fps)

        # 拆帧时生成的 preview.png（在 frames_dir 里）复制到 action 根目录
        src_preview = os.path.join(frames_dir, "preview.png")
        if os.path.exists(src_preview):
            try:
                shutil.copyfile(src_preview, self._action_preview_path())
            except Exception as e:
                print(f"⚠ 复制 preview.png 失败：{e}")

        self._update_slot_display(slot_key)

    def _on_pick_preview(self, slot_key):
        frames_dir = self._slot_frames_dir(slot_key)
        frames = load_frames_from_dir(frames_dir)
        if not frames:
            QMessageBox.information(self, "无素材", "请先导入 GIF。")
            return

        dlg = PreviewFrameDialog(frames_dir, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        idx = dlg.get_selected_index()

        # 用与 frame_utils 一致的排序，取对应文件
        files = [
            f for f in os.listdir(frames_dir)
            if f.lower().endswith(".png") and f.lower() != "preview.png"
        ]

        def _sort_key(n):
            base = os.path.splitext(n)[0]
            if base.isdigit():
                return (0, int(base))
            return (1, base)

        files.sort(key=_sort_key)
        if idx >= len(files):
            return

        src = os.path.join(frames_dir, files[idx])
        try:
            shutil.copyfile(src, self._action_preview_path())
            self._update_slot_display(slot_key)
            QMessageBox.information(
                self, "已设置",
                f"已将第 {idx + 1} 帧设为动作预览图。\n"
                f"点『确定』后保存生效。"
            )
        except Exception as e:
            QMessageBox.warning(self, "设置失败", str(e))

    def _on_play_slot(self, slot_key):
        frames_dir = self._slot_frames_dir(slot_key)
        frames = load_frames_from_dir(frames_dir)
        if not frames:
            QMessageBox.information(self, "无素材", "该素材槽尚未导入 GIF。")
            return
        self.request_preview.emit(frames, self._spin_fps.value())

    def _on_ok(self):
        name = self._edit_name.text().strip()
        if not name:
            QMessageBox.warning(self, "名称不能为空", "请输入动作名称。")
            return

        self._action_data["action_name"] = name
        self._action_data["fps"] = self._spin_fps.value()
        if self._edit_prompt is not None:
            self._action_data["prompt"] = self._edit_prompt.toPlainText()

        # preview_path 固定指向 action 根目录 preview.png
        base = self._action_data["path"].rstrip("/")
        if not base.startswith("./"):
            base = "./" + base.lstrip("/")
        self._action_data["preview_path"] = base + "/preview.png"

        self.accept()

    def get_action_data(self):
        return self._action_data