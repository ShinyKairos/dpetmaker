import os
from PyQt6.QtGui import QPixmap


def load_frames_from_dir(dir_path):
    """从目录读取 0001.png ~ NNNN.png，自然排序，排除 preview.png。

    参数：
        dir_path  帧目录

    返回：
        list[QPixmap]（空目录/目录不存在返回 []）
    """
    if not os.path.isdir(dir_path):
        return []

    files = [
        f for f in os.listdir(dir_path)
        if f.lower().endswith(".png") and f.lower() != "preview.png"
    ]

    def sort_key(name):
        base = os.path.splitext(name)[0]
        try:
            return (0, int(base))
        except ValueError:
            return (1, base)

    files.sort(key=sort_key)

    frames = []
    for f in files:
        pix = QPixmap(os.path.join(dir_path, f))
        if not pix.isNull():
            frames.append(pix)
    return frames