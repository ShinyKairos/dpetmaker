import os
import sys

# 1. 源码运行时的路径兼容（打包后会被冻结，跳过该逻辑）
if not getattr(sys, "frozen", False):
    _HERE   = os.path.dirname(os.path.abspath(__file__))   # …\deskpet\editor
    _DESKPET = os.path.dirname(_HERE)                      # …\deskpet
    if _DESKPET not in sys.path:
        sys.path.insert(0, _DESKPET)

from PyQt6.QtWidgets import QApplication


def main():
    # 2. 判断环境，定位 save 目录
    if getattr(sys, "frozen", False):
        # 打包后：以 exe 所在目录为基准
        base_dir = os.path.dirname(sys.executable)
    else:
        # 源码运行：以 deskpet 根目录为基准
        base_dir = _DESKPET
        
    save_root = os.path.join(base_dir, "save")
    os.makedirs(save_root, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("桌宠制作器")

    # 延迟导入：确保 sys.path 已生效，且 editor 作为顶层包可被识别
    from editor.ui.main_window import MainWindow
    win = MainWindow(save_root)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()