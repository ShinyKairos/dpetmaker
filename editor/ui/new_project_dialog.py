from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QButtonGroup, QLabel, QDialogButtonBox
)
from PyQt6.QtCore import Qt

from ..core.project import SIZE_OPTIONS


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # 项目名
        form = QFormLayout()
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("给桌宠起个名字")
        form.addRow("项目名：", self.edit_name)
        layout.addLayout(form)

        # 尺寸
        layout.addWidget(QLabel("宠物尺寸："))
        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        self.size_group = QButtonGroup(self)
        self.size_group.setExclusive(True)
        self.size_buttons = {}
        for s in SIZE_OPTIONS:
            btn = QPushButton(f"{s}px")
            btn.setCheckable(True)
            btn.setMinimumHeight(44)
            self.size_group.addButton(btn)
            self.size_buttons[s] = btn
            size_row.addWidget(btn)
        self.size_buttons[364].setChecked(True)
        layout.addLayout(size_row)

        self.size_hint = QLabel("")
        self.size_hint.setStyleSheet("color: #666; font-size: 12px;")
        self.size_hint.setWordWrap(True)
        layout.addWidget(self.size_hint)
        self._update_hint(364)

        self.size_group.buttonClicked.connect(self._on_size_clicked)

        layout.addStretch(1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("创建")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_size_clicked(self, btn):
        for s, b in self.size_buttons.items():
            if b is btn:
                self._update_hint(s)
                break

    def _update_hint(self, size):
        hints = {
            182: "极小挂件，放角落",
            258: "小号，不挡工作",
            364: "推荐尺寸",
            516: "大号，动画清晰",
            728: "超大，需大屏空间",
        }
        self.size_hint.setText(f"当前：{size}×{size} px — {hints[size]}")

    def _on_ok(self):
        if not self.edit_name.text().strip():
            self.edit_name.setFocus()
            return
        self.accept()

    def project_name(self):
        return self.edit_name.text().strip()

    def selected_size(self):
        for s, b in self.size_buttons.items():
            if b.isChecked():
                return s
        return 364