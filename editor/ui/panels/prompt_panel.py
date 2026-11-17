from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QFrame, QMessageBox, QScrollArea,
    QDialog, QDialogButtonBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal


class PromptEditorDialog(QDialog):
    """展开式提示词编辑器。确定后把内容写回源 QPlainTextEdit。"""

    def __init__(self, parent, title, source_edit):
        super().__init__(parent)
        self.source_edit = source_edit
        self.setWindowTitle(title)
        self.resize(800, 600)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(source_edit.toPlainText())
        layout.addWidget(self.editor, 1)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("确定")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_ok(self):
        self.source_edit.setPlainText(self.editor.toPlainText())
        self.accept()


class PromptPanel(QWidget):
    """提示词编辑面板：编辑 ai_system.prompt_config。"""

    project_changed = pyqtSignal()
    page_saved = pyqtSignal()

    PROMPT_FIELDS = [
        ("global_prompt",  "全局提示词"),
        ("character_card", "角色设定"),
        ("user_card",      "用户身份卡"),
        ("realtime_prompt","实时对话提示词"),
        ("story_prompt",   "故事模式提示词"),
    ]

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._prompt_edits = {}
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

        title = QLabel("提示词编辑")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "提示词会在封装后作为成品默认值，最终用户在成品高级设置中仍可修改。"
            "支持 {{char}} / {{user}} 宏替换。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #666; background: transparent;")
        layout.addWidget(desc)

        layout.addWidget(self._build_identity_card())
        layout.addWidget(self._build_prompts_card())
        layout.addWidget(self._build_error_card())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
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

    def _card_style(self, name):
        return f"""
            QFrame#{name} {{
                background: #f8f9fa;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
            }}
            QFrame#{name} QLabel {{
                background: transparent;
                color: #333;
                font-size: 13px;
            }}
            QFrame#{name} QLineEdit {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 13px;
                min-height: 24px;
            }}
            QFrame#{name} QPlainTextEdit {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 4px;
                font-size: 13px;
            }}
            QFrame#{name} QPushButton {{
                background: #ffffff;
                color: #333;
                border: 1px solid #b8b8b8;
                border-radius: 4px;
                font-size: 12px;
                padding: 2px 8px;
            }}
            QFrame#{name} QPushButton:hover {{
                background: #f0f0f0;
                border-color: #a0a0a0;
            }}
            QFrame#{name} QPushButton:pressed {{
                background: #e0e0e0;
            }}
            QFrame#{name} QPushButton:disabled {{
                background: #f5f5f5;
                color: #aaa;
                border-color: #e0e0e0;
            }}
        """

    def _build_identity_card(self):
        card = QFrame()
        card.setObjectName("card_identity")
        card.setStyleSheet(self._card_style("card_identity"))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        lbl_h = QLabel("角色与身份")
        lbl_h.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        cl.addWidget(lbl_h)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.edit_char_name = QLineEdit()
        self.edit_char_name.setPlaceholderText("角色名（用于 {{char}} 宏替换）")
        self.edit_char_name.textChanged.connect(self._on_changed)
        form.addRow("角色名：", self.edit_char_name)

        self.edit_user_name = QLineEdit()
        self.edit_user_name.setPlaceholderText("用户名（用于 {{user}} 宏替换）")
        self.edit_user_name.textChanged.connect(self._on_changed)
        form.addRow("用户名：", self.edit_user_name)

        cl.addLayout(form)
        return card

    def _build_prompts_card(self):
        card = QFrame()
        card.setObjectName("card_prompts")
        card.setStyleSheet(self._card_style("card_prompts"))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(10)

        lbl_h = QLabel("提示词")
        lbl_h.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        cl.addWidget(lbl_h)

        for field_key, display in self.PROMPT_FIELDS:
            block = QVBoxLayout()
            block.setSpacing(4)

            head = QHBoxLayout()
            head.setSpacing(6)
            lbl = QLabel(display + "：")
            lbl.setStyleSheet(
                "background: transparent; color: #333; font-size: 13px; font-weight: bold;"
            )
            head.addWidget(lbl)
            head.addStretch(1)

            btn_expand = QPushButton("↗ 展开编辑")
            btn_expand.setFixedHeight(24)
            btn_expand.setMinimumWidth(96)
            btn_expand.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_expand.clicked.connect(
                lambda checked=False, k=field_key, d=display: self._on_expand(k, d)
            )
            head.addWidget(btn_expand)
            block.addLayout(head)

            edit = QPlainTextEdit()
            edit.setMinimumHeight(90)
            edit.textChanged.connect(self._on_changed)
            block.addWidget(edit)

            self._prompt_edits[field_key] = edit
            cl.addLayout(block)

        return card

    def _build_error_card(self):
        card = QFrame()
        card.setObjectName("card_error")
        card.setStyleSheet(self._card_style("card_error"))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        lbl_h = QLabel("异常兜底")
        lbl_h.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        cl.addWidget(lbl_h)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.edit_error_tip = QLineEdit()
        self.edit_error_tip.setPlaceholderText("API 请求失败时，角色说的台词")
        self.edit_error_tip.textChanged.connect(self._on_changed)
        form.addRow("角色报错语：", self.edit_error_tip)

        cl.addLayout(form)
        return card

    # ---------- 事件 ----------
    def _on_expand(self, field_key, display):
        src = self._prompt_edits[field_key]
        dlg = PromptEditorDialog(self, f"编辑 - {display}", src)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._on_changed()

    def _sync_ui_to_config(self):
        """把当前 UI 值写回内存 config。"""
        pc = self.project.config.setdefault("ai_system", {}).setdefault(
            "prompt_config", {}
        )
        pc["char_name"] = self.edit_char_name.text().strip()
        pc["user_name"] = self.edit_user_name.text().strip()
        for key, edit in self._prompt_edits.items():
            pc[key] = edit.toPlainText()
        pc["error_tip"] = self.edit_error_tip.text().strip()

    def _on_changed(self):
        if not self.project.is_open:
            return
        self.project.dirty = True
        self._sync_ui_to_config()
        self.project_changed.emit()

    def _set_enabled(self, enabled):
        self.edit_char_name.setEnabled(enabled)
        self.edit_user_name.setEnabled(enabled)
        self.edit_error_tip.setEnabled(enabled)
        for edit in self._prompt_edits.values():
            edit.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    # ---------- 保存 ----------
    def _on_save(self):
        if not self.project.is_open:
            return
        self._sync_ui_to_config()      # ★ 复用共享方法

        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self.page_saved.emit()         # ★
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    # ---------- 刷新 ----------
    def refresh_from_project(self):
        if not self.project.is_open:
            self._set_enabled(False)
            self.lbl_hint.setText("请先创建或打开项目。")
            return

        self._set_enabled(True)

        pc = self.project.config.get("ai_system", {}).get("prompt_config", {})

        widgets = [self.edit_char_name, self.edit_user_name, self.edit_error_tip]
        widgets += list(self._prompt_edits.values())
        for w in widgets:
            w.blockSignals(True)

        self.edit_char_name.setText(pc.get("char_name", ""))
        self.edit_user_name.setText(pc.get("user_name", ""))
        for key, edit in self._prompt_edits.items():
            edit.setPlainText(pc.get(key, ""))
        self.edit_error_tip.setText(pc.get("error_tip", ""))

        for w in widgets:
            w.blockSignals(False)

        self.lbl_hint.setText("")