from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt


class PlaceholderPanel(QWidget):
    """通用"待开发"占位面板。
    每个面板必须通过 refresh_from_project() 实现后续刷新接口，
    这样里程碑 E 替换真实面板时，MainWindow 不用改任何代码。
    """

    def __init__(self, title, config_path="", asset_dir="", parent=None):
        super().__init__(parent)
        self._title = title
        self._config_path = config_path
        self._asset_dir = asset_dir
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title_label = QLabel(self._title)
        title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #333;"
            "background: transparent;"
        )
        layout.addWidget(title_label)

        hint = QLabel("🚧 本面板待开发（里程碑 E 实现）")
        hint.setStyleSheet("font-size: 14px; color: #d04040; background: transparent;")
        layout.addWidget(hint)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("color: #eee;")
        layout.addWidget(line)

        if self._config_path:
            p = QLabel(f"配置字段：<code>{self._config_path}</code>")
            p.setTextFormat(Qt.TextFormat.RichText)
            p.setStyleSheet("font-size: 13px; color: #666; background: transparent;")
            p.setWordWrap(True)
            layout.addWidget(p)

        if self._asset_dir:
            d = QLabel(f"素材目录：<code>{self._asset_dir}</code>")
            d.setTextFormat(Qt.TextFormat.RichText)
            d.setStyleSheet("font-size: 13px; color: #666; background: transparent;")
            d.setWordWrap(True)
            layout.addWidget(d)

        layout.addStretch(1)

    def refresh_from_project(self):
        """占位面板无需刷新。里程碑 E 真实面板必须实现这个方法。"""
        pass