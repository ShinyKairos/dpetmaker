from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QAbstractSpinBox
)
from PyQt6.QtCore import Qt


def make_spin_row(spin, step, width=140):
    """把 QSpinBox/QDoubleSpinBox 包装为 [spin(隐藏自带按钮)] + [▲▼ 独立按钮]。

    解决 PyQt6 定制 QSpinBox 时上下箭头 hitTest 错位的经典坑。
    父容器需要在 QSS 里包含 QPushButton#spin_btn 规则。

    参数：
        spin    QSpinBox / QDoubleSpinBox 实例
        step    每次点击 ▲ / ▼ 的步进值（int 或 float）
        width   容器总宽度（px）
    """
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

    container = QWidget()
    container.setFixedWidth(width)
    h = QHBoxLayout(container)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(4)
    h.addWidget(spin, 1)

    btn_col = QWidget()
    btn_col.setFixedWidth(26)
    v = QVBoxLayout(btn_col)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)

    btn_up = QPushButton("▲")
    btn_up.setObjectName("spin_btn")
    btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_up.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    btn_down = QPushButton("▼")
    btn_down.setObjectName("spin_btn")
    btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
    btn_down.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    btn_up.clicked.connect(lambda checked=False: spin.setValue(spin.value() + step))
    btn_down.clicked.connect(lambda checked=False: spin.setValue(spin.value() - step))

    v.addWidget(btn_up, 1)
    v.addWidget(btn_down, 1)
    h.addWidget(btn_col)
    return container