from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QDoubleSpinBox, QFrame, QMessageBox, QScrollArea,
    QColorDialog, QFormLayout, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor

from ..widgets.spin_row import make_spin_row
from ..widgets.color_utils import parse_color
from .preview_widgets.bubble_preview import BubblePreview
from .preview_widgets.chat_input_preview import ChatInputPreview
from .preview_widgets.right_menu_preview import RightMenuPreview
from .preview_widgets.interact_window_preview import InteractWindowPreview
from .preview_widgets.advanced_window_preview import AdvancedWindowPreview
from .preview_widgets.behavior_window_preview import BehaviorWindowPreview


PREVIEW_CLASSES = {
    "bubble": BubblePreview,
    "chat_input": ChatInputPreview,
    "right_menu": RightMenuPreview,
    "interact_window": InteractWindowPreview,
    "advanced_window.message_bubble": AdvancedWindowPreview,
    "behavior_window": BehaviorWindowPreview,
}


class UIStylePanel(QWidget):
    """UI 样式编辑面板：编辑 config.ui_style。
    每个分区卡片底部内嵌实时预览。
    """

    project_changed = pyqtSignal()
    page_saved = pyqtSignal()

    SECTIONS = [
        {
            "key": "bubble",
            "title": "对话气泡",
            "fields": [
                ("bg_color", "背景色", "color"),
                ("text_color", "文字颜色", "color"),
                ("padding", "内边距 (px)", "int"),
                ("font_family", "字体", "text"),
                ("font_size", "字号", "int"),
                ("border_radius", "圆角半径 (px)", "int"),
            ],
            # 气泡行为参数（存 ai_system.ui_config）
            "extra_fields": [
                {
                    "key": "bubble_max_width",
                    "display": "气泡最大宽度 (px)",
                    "kind": "int",
                    "min": 60, "max": 800, "step": 20,
                    "default": 320,
                    "config_path": "ai_system.ui_config.bubble_max_width",
                },
                {
                    "key": "text_speed_char_per_sec",
                    "display": "文字显示速度 (字/秒)",
                    "kind": "float",
                    "min": 0.5, "max": 30.0, "step": 0.5, "decimals": 1,
                    "default": 4.0,
                    "config_path": "ai_system.ui_config.text_speed_char_per_sec",
                },
                {
                    "key": "bubble_stay_seconds",
                    "display": "气泡停留时间 (秒)",
                    "kind": "float",
                    "min": 1.0, "max": 60.0, "step": 1.0, "decimals": 1,
                    "default": 5.0,
                    "config_path": "ai_system.ui_config.bubble_stay_seconds",
                },
            ],
        },
        {
            "key": "chat_input",
            "title": "对话输入栏",
            "fields": [
                ("btn_bg", "按钮背景", "color"),
                ("btn_hover_bg", "按钮悬停背景", "color"),
                ("text_color", "文字颜色", "color"),
                ("border_color", "边框颜色", "color"),
            ],
        },
        {
            "key": "right_menu",
            "title": "右键菜单",
            "fields": [
                ("btn_bg", "按钮背景", "color"),
                ("btn_hover_bg", "按钮悬停背景", "color"),
                ("text_color", "文字颜色", "color"),
                ("border_color", "边框颜色", "color"),
            ],
        },
        {
            "key": "interact_window",
            "title": "互动选择窗口",
            "fields": [
                ("window_bg", "窗口背景", "color"),
                ("btn_bg", "按钮背景", "color"),
                ("btn_hover_bg", "按钮悬停背景", "color"),
                ("btn_disabled_bg", "按钮禁用背景", "color"),
                ("btn_disabled_color", "按钮禁用文字", "color"),
                ("text_color", "文字颜色", "color"),
                ("border_color", "边框颜色", "color"),
                ("tab_bg", "标签背景", "color"),
                ("tab_selected_bg", "标签选中背景", "color"),
            ],
        },
        {
            "key": "advanced_window.message_bubble",
            "title": "高级对话气泡",
            "fields": [
                ("user_bg", "用户气泡背景", "color"),
                ("assistant_bg", "助手气泡背景", "color"),
                ("border_radius", "圆角半径 (px)", "int"),
                ("max_width", "最大宽度 (px)", "int"),
                ("font_size", "字号", "int"),
                ("time_color", "时间戳颜色", "color"),
                ("time_font_size", "时间戳字号", "int"),
                ("text_color", "文字颜色", "color"),
                ("edit_btn_bg", "编辑按钮背景", "color"),
                ("edit_btn_border", "编辑按钮边框", "color"),
            ],
        },
        {
            "key": "behavior_window",
            "title": "行为设置窗口",
            "fields": [
                ("window_bg", "窗口背景", "color"),
                ("text_color", "文字颜色", "color"),
                ("btn_bg", "按钮背景", "color"),
                ("btn_hover_bg", "按钮悬停背景", "color"),
                ("border_color", "边框颜色", "color"),
            ],
        },
    ]

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._field_widgets = {}
        self._previews = {}
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("UI 样式")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; background: transparent;"
        )
        layout.addWidget(title)

        desc = QLabel(
            "颜色支持 #RRGGBB / rgba(r,g,b,a) / transparent / Qt 颜色名。"
            "点 🎨 打开颜色选择器。每个分区下方实时预览当前样式。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #666; background: transparent;")
        layout.addWidget(desc)

        for section in self.SECTIONS:
            layout.addWidget(self._build_section_card(section))

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
            QFrame#{object_name} QLineEdit {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 3px 6px;
                font-size: 12px;
                min-height: 22px;
                font-family: Consolas, "Courier New", monospace;
            }}
            QFrame#{object_name} QSpinBox,
            QFrame#{object_name} QDoubleSpinBox {{
                background: #ffffff;
                color: #333;
                border: 1px solid #d0d0d0;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 12px;
                min-height: 22px;
            }}
            QFrame#{object_name} QSpinBox:focus,
            QFrame#{object_name} QDoubleSpinBox:focus {{
                border: 1px solid #5a9bd5;
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
            QFrame#{object_name} QPushButton#spin_btn:disabled {{
                background: #f5f5f5;
                color: #aaa;
                border-color: #e0e0e0;
            }}
        """

    def _build_section_card(self, section):
        card = QFrame()
        obj_name = "sec_" + section["key"].replace(".", "_")
        card.setObjectName(obj_name)
        card.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        card.setStyleSheet(self._card_style(obj_name))

        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 10, 14, 10)
        cl.setSpacing(6)

        lbl_h = QLabel(section["title"])
        lbl_h.setStyleSheet(
            "background: transparent; color: #333; font-size: 14px; font-weight: bold;"
        )
        cl.addWidget(lbl_h)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        for field_key, display, kind in section["fields"]:
            widget = self._make_field_widget(section["key"], field_key, kind)
            form.addRow(display + "：", widget)

        cl.addLayout(form)

        # 分隔线
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #e0e0e0; background: transparent;")
        cl.addWidget(divider)

        # ★ 外挂字段区块（如 bubble 的 ui_config）
        extra_block = self._build_extra_fields_block(section)
        if extra_block is not None:
            cl.addWidget(extra_block)
            divider2 = QFrame()
            divider2.setFrameShape(QFrame.Shape.HLine)
            divider2.setStyleSheet("color: #e0e0e0; background: transparent;")
            cl.addWidget(divider2)

        # 预览区
        preview_cls = PREVIEW_CLASSES.get(section["key"])
        if preview_cls is not None:
            preview = preview_cls()
            self._previews[section["key"]] = preview
            cl.addWidget(preview)

        return card

    # ---------- 外挂字段区块 ----------
    def _build_extra_fields_block(self, section):
        """构建 section 的 extra_fields 子区块（存储路径不在 ui_style 下）。"""
        extra = section.get("extra_fields", [])
        if not extra:
            return None

        block = QWidget()
        v = QVBoxLayout(block)
        v.setContentsMargins(0, 2, 0, 2)
        v.setSpacing(4)

        lbl = QLabel("气泡行为参数")
        lbl.setStyleSheet(
            "background: transparent; color: #333; font-size: 13px; font-weight: bold;"
        )
        v.addWidget(lbl)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        for ef in extra:
            widget = self._make_extra_widget(section["key"], ef)
            form.addRow(ef["display"] + "：", widget)

        v.addLayout(form)
        return block

    def _make_extra_widget(self, section_key, ef):
        """根据 extra_fields 配置创建 QSpinBox / QDoubleSpinBox 控件。"""
        kind = ef.get("kind", "int")
        fkey = ef["key"]

        if kind == "int":
            spin = QSpinBox()
            spin.setRange(int(ef.get("min", 0)), int(ef.get("max", 9999)))
            spin.valueChanged.connect(self._on_changed)
            widget = spin
        elif kind == "float":
            spin = QDoubleSpinBox()
            spin.setRange(float(ef.get("min", 0.0)), float(ef.get("max", 9999.0)))
            spin.setSingleStep(float(ef.get("step", 0.1)))
            spin.setDecimals(int(ef.get("decimals", 1)))
            spin.valueChanged.connect(self._on_changed)
            widget = spin
        else:
            edit = QLineEdit()
            edit.textChanged.connect(self._on_changed)
            widget = edit

        self._field_widgets[(section_key, fkey)] = (kind, widget)

        if kind in ("int", "float"):
            return make_spin_row(widget, ef.get("step", 1), width=140)
        return widget

    # ---------- 按路径读写 config ----------
    def _get_by_path(self, path, create=False):
        """按 'a.b.c' 路径读取 config 里的值。create=True 时路径不存在则创建空 dict。"""
        parts = path.split(".")
        cur = self.project.config
        for p in parts:
            if not isinstance(cur, dict):
                return None
            if p not in cur:
                if create:
                    cur[p] = {}
                else:
                    return None
            cur = cur[p]
        return cur

    def _set_by_path(self, path, value):
        """按 'a.b.c' 路径写入 config，自动创建中间层 dict。"""
        parts = path.split(".")
        cur = self.project.config
        for p in parts[:-1]:
            if p not in cur or not isinstance(cur[p], dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = value

    def _make_field_widget(self, section_key, field_key, kind):
        if kind == "color":
            return self._make_color_widget(section_key, field_key)
        if kind == "int":
            return self._make_int_widget(section_key, field_key)
        return self._make_text_widget(section_key, field_key)

    def _make_color_widget(self, section_key, field_key):
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        edit = QLineEdit()
        edit.textChanged.connect(self._on_changed)
        h.addWidget(edit, 1)

        btn = QPushButton("🎨")
        btn.setFixedSize(28, 28)
        btn.setToolTip("打开颜色选择器")
        btn.clicked.connect(lambda checked=False, e=edit: self._pick_color(e))
        h.addWidget(btn)

        self._field_widgets[(section_key, field_key)] = ("color", edit)
        return container

    def _make_int_widget(self, section_key, field_key):
        spin = QSpinBox()
        spin.setRange(0, 9999)
        spin.valueChanged.connect(self._on_changed)
        container = make_spin_row(spin, 1, width=140)
        self._field_widgets[(section_key, field_key)] = ("int", spin)
        return container

    def _make_text_widget(self, section_key, field_key):
        edit = QLineEdit()
        edit.textChanged.connect(self._on_changed)
        self._field_widgets[(section_key, field_key)] = ("text", edit)
        return edit

    # ---------- 颜色工具 ----------
    def _pick_color(self, edit_widget):
        current = parse_color(edit_widget.text())
        color = QColorDialog.getColor(
            current, self, "选择颜色",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not color.isValid():
            return
        edit_widget.setText(self._qcolor_to_css(color))

    def _qcolor_to_css(self, color):
        """QColor → QSS 安全颜色字符串。
        - 不透明 → '#rrggbb'
        - 半透明 → 'rgba(r,g,b,0~255)'（整数 alpha，QSS 合法）
        """
        if color.alpha() == 255:
            return color.name()
        return (
            f"rgba({color.red()},{color.green()},"
            f"{color.blue()},{color.alpha()})"      # ★ 整数 alpha
        )

    # ---------- 事件 ----------
    def _on_changed(self, *args):
        if not self.project.is_open:
            return
        self.project.dirty = True
        self._sync_ui_to_config()   # ★ 关键：UI 值先同步进内存 config
        self.project_changed.emit()
        self._refresh_previews()    # 现在从 config 读到的是最新值

    def _set_enabled(self, enabled):
        for kind, w in self._field_widgets.values():
            w.setEnabled(enabled)
        for btn in self.findChildren(QPushButton):
            if btn.objectName() == "spin_btn":
                btn.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)

    def _get_nested(self, section_key):
        parts = section_key.split(".")
        cur = self.project.config.setdefault("ui_style", {})
        for p in parts:
            if not isinstance(cur, dict):
                return {}
            cur = cur.setdefault(p, {})
        return cur

    def _refresh_previews(self):
        for section_key, preview in self._previews.items():
            try:
                # 复制一层，避免把临时字段写回 config
                data = dict(self._get_nested(section_key))
                # ★ 气泡预览额外注入文字速度（来自 ai_system.ui_config）
                if section_key == "bubble":
                    ui_cfg = self.project.config.get("ai_system", {}).get("ui_config", {})
                    data["_text_speed"] = ui_cfg.get("text_speed_char_per_sec", 4.0)
                preview.apply_style(data)
            except Exception as e:
                print(f"⚠ 预览刷新失败 {section_key}: {e}")

    def _sync_ui_to_config(self):
        """把当前 UI 控件值写回内存 config。
        _on_changed 和 _on_save 共用，保证 config 始终反映最新输入。"""
        for section in self.SECTIONS:
            target = self._get_nested(section["key"])
            for field_key, display, kind in section["fields"]:
                entry = self._field_widgets.get((section["key"], field_key))
                if not entry:
                    continue
                fkind, widget = entry
                if fkind == "int":
                    target[field_key] = int(widget.value())
                else:
                    target[field_key] = widget.text()

            # ★ 外挂字段：按 config_path 写回（如 ai_system.ui_config.*）
            for ef in section.get("extra_fields", []):
                entry = self._field_widgets.get((section["key"], ef["key"]))
                if not entry:
                    continue
                fkind, widget = entry
                if fkind == "int":
                    self._set_by_path(ef["config_path"], int(widget.value()))
                elif fkind == "float":
                    self._set_by_path(ef["config_path"], float(widget.value()))
                else:
                    self._set_by_path(ef["config_path"], widget.text())

    def _on_save(self):
        if not self.project.is_open:
            return
        self._sync_ui_to_config()   # 复用共享方法，不重复代码

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
            self.lbl_hint.setText("请先创建或打开项目。")
            return

        self._set_enabled(True)

        for section in self.SECTIONS:
            data = self._get_nested(section["key"])
            for field_key, display, kind in section["fields"]:
                entry = self._field_widgets.get((section["key"], field_key))
                if not entry:
                    continue
                fkind, widget = entry
                value = data.get(field_key, 0 if fkind == "int" else "")
                widget.blockSignals(True)
                try:
                    if fkind == "int":
                        widget.setValue(int(value))
                    else:
                        widget.setText(str(value))
                except Exception as e:
                    print(f"⚠ {section['key']}.{field_key} 值无效：{e}")
                widget.blockSignals(False)

            # ★ 外挂字段：从 config_path 读取，缺失时写回默认值（自愈）
            for ef in section.get("extra_fields", []):
                entry = self._field_widgets.get((section["key"], ef["key"]))
                if not entry:
                    continue
                fkind, widget = entry
                value = self._get_by_path(ef["config_path"])
                if value is None:
                    default = ef.get("default", 0 if fkind == "int" else 0.0)
                    self._set_by_path(ef["config_path"], default)
                    value = default
                widget.blockSignals(True)
                try:
                    if fkind == "int":
                        widget.setValue(int(value))
                    elif fkind == "float":
                        widget.setValue(float(value))
                    else:
                        widget.setText(str(value))
                except Exception as e:
                    print(f"⚠ {ef['config_path']} 值无效：{e}")
                widget.blockSignals(False)

        self._refresh_previews()
        self.lbl_hint.setText("")