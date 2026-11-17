import os
import shutil
from PIL import Image
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QMessageBox, QScrollArea, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap


ICON_SIZE = 64


class IconPanel(QWidget):
    """成品图标面板：导入 / 校验 / 预览 64×64 PNG。"""

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

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("成品图标")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            f"导入一张 {ICON_SIZE}×{ICON_SIZE} 像素的 PNG 作为成品图标。\n"
            "封装时会自动转为 ICO，同时用作成品 exe 文件图标与系统托盘图标；"
            "未导入时使用内置默认图标。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #666; background: transparent;")
        layout.addWidget(desc)

        layout.addWidget(self._build_preview_card())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_import = QPushButton("📂 导入 PNG")
        self.btn_import.setFixedHeight(34)
        self.btn_import.setMinimumWidth(120)
        self.btn_import.clicked.connect(self._on_import)
        btn_row.addWidget(self.btn_import)

        self.btn_clear = QPushButton("🗑 清除图标")
        self.btn_clear.setFixedHeight(34)
        self.btn_clear.setMinimumWidth(120)
        self.btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self.btn_clear)

        self.btn_save = QPushButton("💾 保存本页")
        self.btn_save.setFixedHeight(34)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_save)

        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 12px; padding: 2px 0;")
        layout.addWidget(self.lbl_hint)

        layout.addStretch(1)

    def _build_preview_card(self):
        card = QFrame()
        card.setObjectName("card_preview")
        card.setStyleSheet("""
            QFrame#card_preview {
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }
            QFrame#card_preview QLabel {
                background: transparent;
                color: #333;
                font-size: 13px;
            }
        """)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(8)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(16)

        self.preview_label = QLabel()
        self.preview_label.setFixedSize(128, 128)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_row.addWidget(self.preview_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(6)

        self.lbl_status = QLabel("（未设置）")
        info_col.addWidget(self.lbl_status)

        self.lbl_size = QLabel(f"建议尺寸：{ICON_SIZE}×{ICON_SIZE} 像素 PNG")
        self.lbl_size.setStyleSheet(
            "background: transparent; font-size: 12px; color: #666;"
        )
        info_col.addWidget(self.lbl_size)

        self.lbl_path = QLabel("—")
        self.lbl_path.setStyleSheet(
            "background: transparent; font-size: 12px; color: #666;"
        )
        self.lbl_path.setWordWrap(True)
        self.lbl_path.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        info_col.addWidget(self.lbl_path)

        info_col.addStretch(1)
        preview_row.addLayout(info_col, 1)

        cl.addLayout(preview_row)
        return card

    # ---------- 预览 ----------
    def _empty_preview_style(self):
        return (
            "background: #ffffff; border: 1px dashed #c0c0c0;"
            " border-radius: 4px; color: #888; font-size: 12px;"
        )

    def _update_preview(self):
        if not self.project.is_open:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("未打开项目")
            self.preview_label.setStyleSheet(self._empty_preview_style())
            self.lbl_status.setText("（未打开项目）")
            self.lbl_status.setStyleSheet(
                "background: transparent; font-size: 13px; color: #888;"
            )
            self.lbl_path.setText("—")
            return

        path_rel = self.project.config.get("icon", {}).get("path", "")
        if not path_rel:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("未设置\n（使用默认图标）")
            self.preview_label.setStyleSheet(self._empty_preview_style())
            self.lbl_status.setText("（未设置）")
            self.lbl_status.setStyleSheet(
                "background: transparent; font-size: 13px; color: #888;"
            )
            self.lbl_path.setText("—")
            return

        if path_rel.startswith("./") or path_rel.startswith(".\\"):
            abs_path = os.path.join(self.project.path, path_rel[2:])
        else:
            abs_path = os.path.join(self.project.path, path_rel)

        if not os.path.exists(abs_path):
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("文件丢失")
            self.preview_label.setStyleSheet(
                "background: #fff0f0; border: 1px dashed #d04040;"
                " border-radius: 4px; color: #d04040; font-size: 12px;"
            )
            self.lbl_status.setText("⚠ 图标文件丢失")
            self.lbl_status.setStyleSheet(
                "background: transparent; font-size: 13px; color: #d04040;"
            )
            self.lbl_path.setText(path_rel)
            return

        pix = QPixmap(abs_path)
        if pix.isNull():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("无法加载")
            self.preview_label.setStyleSheet(
                "background: #fff0f0; border: 1px dashed #d04040;"
                " border-radius: 4px; color: #d04040; font-size: 12px;"
            )
            self.lbl_status.setText("⚠ 文件损坏")
            self.lbl_status.setStyleSheet(
                "background: transparent; font-size: 13px; color: #d04040;"
            )
            self.lbl_path.setText(path_rel)
            return

        scaled = pix.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.setStyleSheet(
            "background: #ffffff; border: 1px dashed #c0c0c0; border-radius: 4px;"
        )
        self.lbl_status.setText(f"✅ 已设置 · {pix.width()}×{pix.height()}")
        self.lbl_status.setStyleSheet(
            "background: transparent; font-size: 13px; color: #2a7a2a;"
        )
        self.lbl_path.setText(path_rel)
        self.lbl_path.setToolTip(abs_path)

    # ---------- 导入 ----------
    def _on_import(self):
        if not self.project.is_open:
            QMessageBox.warning(self, "无法导入", "请先创建或打开项目。")
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "选择图标 PNG", "", "PNG 图片 (*.png)"
        )
        if not path:
            return

        pix = QPixmap(path)
        if pix.isNull():
            QMessageBox.warning(self, "加载失败", "所选文件无法作为图片加载。")
            return

        if pix.width() != ICON_SIZE or pix.height() != ICON_SIZE:
            QMessageBox.warning(
                self, "尺寸不符",
                f"图标必须是 {ICON_SIZE}×{ICON_SIZE} 像素。\n"
                f"当前图片尺寸：{pix.width()}×{pix.height()}。\n\n"
                "请使用绘图工具调整后重新导入。"
            )
            return

        # 1. 保存原始的 PNG（供编辑器预览使用）
        target_dir = os.path.join(self.project.path, "assets", "icon")
        os.makedirs(target_dir, exist_ok=True)
        target_png_path = os.path.join(target_dir, "icon.png")
        
        # 2. 生成 ico 文件（供运行时的托盘图标使用）
        target_ico_path = os.path.join(self.project.path, "assets", "icon.ico")

        try:
            shutil.copyfile(path, target_png_path)
            # 同步转换为 ICO，强制尺寸为 64x64
            img = Image.open(path).convert("RGBA")
            img.save(target_ico_path, format='ICO', sizes=[(ICON_SIZE, ICON_SIZE)])
        except Exception as e:
            QMessageBox.warning(self, "写入失败", f"保存图标文件失败：\n{e}")
            return

        # 3. 更新配置并刷新
        self.project.config.setdefault("icon", {})["path"] = "./assets/icon/icon.png"
        self.project.dirty = True
        self._update_preview()
        self.project_changed.emit()
        self.lbl_hint.setText("✅ 已导入（PNG+ICO） · 点『💾 保存本页』写入配置")

    # ---------- 清除 ----------
    def _on_clear(self):
        if not self.project.is_open:
            return
        if not self.project.config.get("icon", {}).get("path"):
            return

        ret = QMessageBox.question(
            self, "清除图标",
            "确定要清除当前图标吗？\n"
            "（会删除 assets/icon/icon.png 和 assets/icon.ico，封装时使用默认图标）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        target_png_path = os.path.join(self.project.path, "assets", "icon", "icon.png")
        target_ico_path = os.path.join(self.project.path, "assets", "icon.ico")
        
        try:
            if os.path.exists(target_png_path):
                os.remove(target_png_path)
            if os.path.exists(target_ico_path):
                os.remove(target_ico_path)  # 同步删除 ICO
        except Exception as e:
            print(f"⚠ 删除图标失败：{e}")

        self.project.config.setdefault("icon", {})["path"] = ""
        self.project.dirty = True
        self._update_preview()
        self.project_changed.emit()
        self.lbl_hint.setText("🗑 已清除图标 · 点『💾 保存本页』写入配置")

    # ---------- 保存 ----------
    def _on_save(self):
        if not self.project.is_open:
            return
        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self.page_saved.emit()
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    # ---------- 刷新 ----------
    def refresh_from_project(self):
        if not self.project.is_open:
            self.btn_import.setEnabled(False)
            self.btn_clear.setEnabled(False)
            self.btn_save.setEnabled(False)
            self._update_preview()
            self.lbl_hint.setText("请先创建或打开项目。")
            return

        self.btn_import.setEnabled(True)
        self.btn_clear.setEnabled(True)
        self.btn_save.setEnabled(True)
        self._update_preview()
        self.lbl_hint.setText("")