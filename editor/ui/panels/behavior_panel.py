from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QDoubleSpinBox, QFrame, QMessageBox, QScrollArea,
    QFormLayout, QAbstractSpinBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from ..widgets.spin_row import make_spin_row


class BehaviorPanel(QWidget):
    """行为参数面板：编辑 config.auto_behavior。"""

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

        title = QLabel("行为参数")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        layout.addWidget(self._build_move_card())
        layout.addWidget(self._build_idle_card())

        self.lbl_warn = QLabel("")
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet(
            "font-size: 13px; color: #d04040; padding: 2px;"
        )
        layout.addWidget(self.lbl_warn)

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
            QFrame#{object_name} QSpinBox,
            QFrame#{object_name} QDoubleSpinBox {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 13px;
                min-height: 24px;
            }}
            QFrame#{object_name} QSpinBox:focus,
            QFrame#{object_name} QDoubleSpinBox:focus {{
                border: 1px solid #5a9bd5;
            }}
            QFrame#{object_name} QPushButton#spin_btn {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 0px;
                font-size: 9px;
                min-height: 0px;
                min-width: 0px;
            }}
            QFrame#{object_name} QPushButton#spin_btn:hover {{
                background: #eef4fb;
                border-color: #a0b8d8;
            }}
            QFrame#{object_name} QPushButton#spin_btn:pressed {{
                background: #d8e3f0;
            }}
        """

    def _build_move_card(self):
        card = QFrame()
        card.setObjectName("card_move")
        card.setStyleSheet(self._card_style("card_move"))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        lbl_h = QLabel("自主移动")
        lbl_h.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        cl.addWidget(lbl_h)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_move_trigger = QSpinBox()
        self.spin_move_trigger.setRange(1, 3600)
        self.spin_move_trigger.setSuffix(" 秒")
        self.spin_move_trigger.valueChanged.connect(self._on_value_changed)
        form.addRow("移动触发等待：", make_spin_row(self.spin_move_trigger, 1))

        self.spin_move_prob = QDoubleSpinBox()
        self.spin_move_prob.setRange(0.0, 1.0)
        self.spin_move_prob.setSingleStep(0.05)
        self.spin_move_prob.setDecimals(2)
        self.spin_move_prob.setSuffix("  (0~1)")
        self.spin_move_prob.valueChanged.connect(self._on_value_changed)
        form.addRow("移动概率：", make_spin_row(self.spin_move_prob, 0.05))

        self.spin_move_duration = QSpinBox()
        self.spin_move_duration.setRange(1, 3600)
        self.spin_move_duration.setSuffix(" 秒")
        self.spin_move_duration.valueChanged.connect(self._on_value_changed)
        form.addRow("移动持续时长：", make_spin_row(self.spin_move_duration, 1))

        self.spin_move_speed = QSpinBox()
        self.spin_move_speed.setRange(1, 200)
        self.spin_move_speed.setSuffix(" 像素/帧")
        self.spin_move_speed.valueChanged.connect(self._on_value_changed)
        form.addRow("移动速度：", make_spin_row(self.spin_move_speed, 1))

        cl.addLayout(form)
        return card

    def _build_idle_card(self):
        card = QFrame()
        card.setObjectName("card_idle")
        card.setStyleSheet(self._card_style("card_idle"))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(8)

        lbl_h = QLabel("长时间待机")
        lbl_h.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        cl.addWidget(lbl_h)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_long_idle_trigger = QSpinBox()
        self.spin_long_idle_trigger.setRange(1, 36000)
        self.spin_long_idle_trigger.setSuffix(" 秒")
        self.spin_long_idle_trigger.valueChanged.connect(self._on_value_changed)
        form.addRow(
            "长待机触发等待：",
            make_spin_row(self.spin_long_idle_trigger, 1)
        )

        cl.addLayout(form)
        return card

    # ---------- 校验 ----------
    def _validate(self):
        move = self.spin_move_trigger.value()
        long_idle = self.spin_long_idle_trigger.value()
        if long_idle <= move:
            self.lbl_warn.setText(
                f"⚠ 长待机触发等待（{long_idle} 秒）必须大于移动触发等待（{move} 秒）"
            )
            return False
        self.lbl_warn.setText("")
        return True

    def _sync_ui_to_config(self):
        """把当前 UI 值写回内存 config（不落盘，落盘由 save 触发）。"""
        ab = self.project.config.setdefault("auto_behavior", {})
        ab["move_trigger_seconds"] = int(self.spin_move_trigger.value())
        ab["move_probability"] = round(float(self.spin_move_prob.value()), 2)
        ab["move_duration_seconds"] = int(self.spin_move_duration.value())
        ab["move_speed"] = int(self.spin_move_speed.value())
        ab["long_idle_trigger_seconds"] = int(self.spin_long_idle_trigger.value())

    # ---------- 事件 ----------
    def _on_value_changed(self):
        if not self.project.is_open:
            return
        self.project.dirty = True
        self._sync_ui_to_config()
        self._validate()
        self.project_changed.emit()

    def _set_enabled(self, enabled):
        for w in (
            self.spin_move_trigger, self.spin_move_prob,
            self.spin_move_duration, self.spin_move_speed,
            self.spin_long_idle_trigger,
        ):
            w.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    # ---------- 保存 ----------
    def _on_save(self):
        if not self.project.is_open:
            return
        if not self._validate():
            QMessageBox.warning(
                self, "参数不合规",
                "长待机触发等待必须大于移动触发等待，请调整后重试。"
            )
            return

        self._sync_ui_to_config()      # ★ 用共享方法，不重复写字段

        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return

        self.page_saved.emit()         # ★ 通知主窗从脏集合移除本 key
        self.lbl_hint.setText(f"✅ 已保存到 {self.project.config_path}")

    # ---------- 刷新 ----------
    def refresh_from_project(self):
        if not self.project.is_open:
            self._set_enabled(False)
            self.lbl_warn.setText("")
            self.lbl_hint.setText("请先创建或打开项目。")
            return

        self._set_enabled(True)

        ab = self.project.config.get("auto_behavior", {})

        for w in (
            self.spin_move_trigger, self.spin_move_prob,
            self.spin_move_duration, self.spin_move_speed,
            self.spin_long_idle_trigger,
        ):
            w.blockSignals(True)

        self.spin_move_trigger.setValue(int(ab.get("move_trigger_seconds", 7)))
        self.spin_move_prob.setValue(float(ab.get("move_probability", 0.6)))
        self.spin_move_duration.setValue(int(ab.get("move_duration_seconds", 2)))
        self.spin_move_speed.setValue(int(ab.get("move_speed", 20)))
        self.spin_long_idle_trigger.setValue(int(ab.get("long_idle_trigger_seconds", 30)))

        for w in (
            self.spin_move_trigger, self.spin_move_prob,
            self.spin_move_duration, self.spin_move_speed,
            self.spin_long_idle_trigger,
        ):
            w.blockSignals(False)

        self._validate()
        self.lbl_hint.setText("")