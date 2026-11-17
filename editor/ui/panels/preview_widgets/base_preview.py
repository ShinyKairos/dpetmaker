from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame


class BasePreview(QWidget):
    """预览容器基类：统一"预览 · 标题" + 虚线画布。

    子类在 __init__ 里往 self._preview_layout 里 addWidget 预览内容，
    并实现 apply_style(data) 让内容跟随参数更新。
    """

    def __init__(self, section_title, parent=None):
        super().__init__(parent)
        self._section_title = section_title
        self._build_frame()

    def _build_frame(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 6, 0, 0)
        outer.setSpacing(4)

        lbl = QLabel(f"预览 · {self._section_title}")
        lbl.setStyleSheet(
            "background: transparent; color: #888; font-size: 11px;"
        )
        outer.addWidget(lbl)

        self.preview_area = QFrame()
        self.preview_area.setObjectName("preview_area")
        self.preview_area.setStyleSheet("""
            QFrame#preview_area {
                background: #ffffff;
                border: 1px dashed #c0c0c0;
                border-radius: 4px;
            }
        """)
        self._preview_layout = QVBoxLayout(self.preview_area)
        self._preview_layout.setContentsMargins(10, 10, 10, 10)
        self._preview_layout.setSpacing(6)
        outer.addWidget(self.preview_area)

    def apply_style(self, data):
        """子类实现：根据 config section data 更新预览。"""
        pass