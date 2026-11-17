from PyQt6.QtGui import QColor


def parse_color(text):
    """CSS 风格颜色字符串 → QColor。支持
    #RGB / #RRGGBB / #AARRGGBB / rgb(r,g,b) / rgba(r,g,b,a) / transparent / Qt 颜色名
    alpha 支持 0~1（0.5）和 0~255（128）两种写法。
    """
    if not text or not str(text).strip():
        return QColor(255, 255, 255, 255)
    text = str(text).strip()
    low = text.lower()
    if low == "transparent":
        return QColor(0, 0, 0, 0)
    if low.startswith("rgba(") or low.startswith("rgb("):
        try:
            inside = text[text.index("(") + 1:text.rindex(")")]
            parts = [x.strip() for x in inside.split(",")]
            r = int(float(parts[0]))
            g = int(float(parts[1]))
            b = int(float(parts[2]))
            if len(parts) >= 4:
                a_val = float(parts[3])
                a = int(round(a_val * 255)) if a_val <= 1.0 else int(round(a_val))
            else:
                a = 255
            return QColor(r, g, b, a)
        except Exception:
            return QColor(255, 255, 255, 255)
    c = QColor(text)
    return c if c.isValid() else QColor(255, 255, 255, 255)