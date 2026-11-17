import os
import sys
from functools import partial
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QLabel,
    QStackedWidget, QFileDialog, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor

from ..core.project import Project
from .new_project_dialog import NewProjectDialog
from .resource_tree import ResourceTree
from .panel_registry import create_panel, PANEL_META
from .preview_panel import PreviewPanel
from ..core.export_manager import export_project


class MainWindow(QMainWindow):
    def __init__(self, save_root):
        super().__init__()
        self.save_root = save_root
        self.project = Project()
        self._panel_cache = {}  # key → QWidget
        self._dirty_leaves = set()

        self.setWindowTitle("桌宠制作器")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)

        self._build_menu()
        self._build_body()
        self._build_statusbar()
        self._refresh_title()
        self._refresh_enabled()

        # 首次启动自动选中第一个叶子（成品图标），让右栏有内容
        self.tree.select_first_leaf()

    # ---------- 构建 ----------
    def _build_menu(self):
        m_file = self.menuBar().addMenu("文件")
        self.act_new  = m_file.addAction("新建项目...")
        self.act_open = m_file.addAction("打开项目...")
        self.act_save = m_file.addAction("保存项目")

        m_file.addSeparator()
        self.act_export = m_file.addAction("封装成品...")
        self.act_export.triggered.connect(self.on_export)

        m_file.addSeparator()
        self.act_exit = m_file.addAction("退出")

        # ★ 快捷键（菜单右侧自动显示对应文字提示）
        self.act_new.setShortcut("Ctrl+N")
        self.act_open.setShortcut("Ctrl+O")
        self.act_save.setShortcut("Ctrl+S")

        self.act_new.triggered.connect(self.on_new)
        self.act_open.triggered.connect(self.on_open)
        self.act_save.triggered.connect(self.on_save)
        self.act_exit.triggered.connect(self.close)

    def _build_body(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左：资源树
        self.tree = ResourceTree()
        self.tree.leaf_selected.connect(self._on_leaf_selected)
        splitter.addWidget(self.tree)

        # 中：预览区
        self.preview_area = PreviewPanel(self.save_root)
        splitter.addWidget(self.preview_area)

        # 右：参数面板（QStackedWidget 懒加载）
        self.stack = QStackedWidget()
        # 设定了 380px 保底，内部卡片正常滚动
        self.stack.setMinimumWidth(380) 
        splitter.addWidget(self.stack)

        # 初始比例：左 240，中 620，右 420
        splitter.setSizes([240, 620, 420])
        splitter.setStretchFactor(1, 1)
        
        # ★ 限制三栏均不可被拖拽折叠至 0 宽
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        
        self.setCentralWidget(splitter)

    def _build_statusbar(self):
        self.statusBar().showMessage("就绪")

    # ---------- 面板切换（懒加载核心）----------
    def _on_leaf_selected(self, key):
        # 切面板前，若 touch_special 面板正在框选，先重置（不写 config）
        sp = self._panel_cache.get("touch_special")
        if sp is not None and hasattr(sp, "_reset_select_state"):
            sp._reset_select_state()
        # 兜底：预览区 overlay 如仍可见，强制退出（幂等）
        if hasattr(self.preview_area, "overlay") and self.preview_area.overlay.isVisible():
            self.preview_area.exit_selection_mode()

        panel = self._lazy_get_panel(key)
        if panel is None:
            return
        self.stack.setCurrentWidget(panel)
        # 切到面板时刷新（会触发 request_preview 让预览区显示该面板的素材）
        if hasattr(panel, "refresh_from_project"):
            try:
                panel.refresh_from_project()
            except Exception as e:
                print(f"⚠ 面板刷新失败：{e}")
        meta = PANEL_META.get(key)
        if meta:
            self.statusBar().showMessage(f"当前面板：{meta['title']}")

    def _lazy_get_panel(self, key):
        if key in self._panel_cache:
            return self._panel_cache[key]
        panel = create_panel(key, self.project)
        self._panel_cache[key] = panel
        self.stack.addWidget(panel)
        # 连接真实面板的两个信号
        if hasattr(panel, "request_preview"):
            panel.request_preview.connect(self._on_panel_request_preview)
        if hasattr(panel, "project_changed"):
            panel.project_changed.connect(
                partial(self._on_panel_project_changed, key)
            )
        if hasattr(panel, "page_saved"):
            panel.page_saved.connect(
                partial(self._on_panel_saved, key)
            )
        # 给需要框选的面板注入预览区引用
        if hasattr(panel, "set_preview_area"):
            panel.set_preview_area(self.preview_area)
        print(f"[懒加载] 创建面板：{key}")
        return panel

    def _sync_preview_target_size(self):
        """把当前项目的 window 尺寸同步到预览区。
        未打开项目时清空（None）。
        """
        if self.project.is_open:
            w = self.project.config.get("window", {}).get("width", 0)
            h = self.project.config.get("window", {}).get("height", 0)
            self.preview_area.set_target_size(w, h)
        else:
            self.preview_area.set_target_size(0, 0)

    def _on_panel_request_preview(self, frames, fps):
        """面板请求预览区播放这些帧。"""
        if frames:
            self.preview_area.set_frames(frames, fps, autoplay=True)

    def _on_panel_project_changed(self, key):
        """面板发生未保存改动 → 标记该叶子为脏，刷新树与标题。"""
        if key in self._dirty_leaves:
            return          # 已在集合里，避免重复刷新
        self._dirty_leaves.add(key)
        self.tree.set_dirty_leaves(self._dirty_leaves)
        self._refresh_title()
        self._refresh_enabled()

    def _on_panel_saved(self, key):
        """某个面板点了"保存本页" → 从脏集合移除该 key。"""
        if key in self._dirty_leaves:
            self._dirty_leaves.discard(key)
            self.tree.set_dirty_leaves(self._dirty_leaves)
            self._refresh_title()
            self._refresh_enabled()

    def _refresh_current_panel(self):
        current = self.stack.currentWidget()
        if current is None:
            return
        if hasattr(current, "refresh_from_project"):
            try:
                current.refresh_from_project()
            except Exception as e:
                print(f"⚠ 面板刷新失败：{e}")

    # ---------- 菜单动作 ----------
    def on_new(self):
        if not self._confirm_discard():
            return
        dlg = NewProjectDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        ok, err = self.project.create(
            self.save_root, dlg.project_name(), dlg.selected_size()
        )
        if not ok:
            QMessageBox.warning(self, "创建失败", err)
            return
        # 重置框选状态
        sp = self._panel_cache.get("touch_special")
        if sp is not None and hasattr(sp, "_reset_select_state"):
            sp._reset_select_state()
        if hasattr(self.preview_area, "overlay") and self.preview_area.overlay.isVisible():
            self.preview_area.exit_selection_mode()

        self._dirty_leaves.clear()
        self.tree.set_dirty_leaves(self._dirty_leaves)
        self._refresh_title()
        self._refresh_enabled()
        self._sync_preview_target_size()
        self._refresh_current_panel()
        self.statusBar().showMessage(f"已创建：{self.project.name}")
        QMessageBox.information(
            self, "创建成功",
            f"项目已创建：\n{self.project.path}\n\n"
            f"尺寸：{self.project.config['window']['width']}×"
            f"{self.project.config['window']['height']}"
        )
        self._refresh_enabled()

    def on_open(self):
        if not self._confirm_discard():
            return
        start = self.save_root if os.path.isdir(self.save_root) else ""
        path = QFileDialog.getExistingDirectory(self, "选择项目文件夹", start)
        if not path:
            return
        ok, err = self.project.open(path)
        if not ok:
            QMessageBox.warning(self, "打开失败", err)
            return
        self._dirty_leaves.clear()
        self.tree.set_dirty_leaves(self._dirty_leaves)
        self._refresh_title()
        self._refresh_enabled()
        self._sync_preview_target_size()
        self._refresh_current_panel()
        self.statusBar().showMessage(f"已打开：{self.project.name}")
        self._refresh_enabled()

    def on_save(self):
        if not self.project.is_open:
            return
        ok, err = self.project.save()
        if not ok:
            QMessageBox.warning(self, "保存失败", err)
            return
        self._dirty_leaves.clear()
        self.tree.set_dirty_leaves(self._dirty_leaves)
        self.statusBar().showMessage(f"已保存：{self.project.name}")
        self._refresh_title()
        self._refresh_enabled()

    def on_export(self):
        if not self.project.is_open:
            return
        if self.project.dirty or self._dirty_leaves:
            QMessageBox.warning(self, "无法封装", "请先保存当前项目再做封装。")
            return

        # 1. 获取输出目录
        start_dir = self.save_root if os.path.isdir(self.save_root) else ""
        out_dir = QFileDialog.getExistingDirectory(self, "选择成品输出目录", start_dir)
        if not out_dir:
            return

        # 2. 检查目标项目文件夹是否已存在
        dest_project = os.path.join(out_dir, self.project.name)
        if os.path.exists(dest_project):
            ret = QMessageBox.question(
                self, "覆盖确认",
                f"目标文件夹已存在：\n{dest_project}\n\n是否覆盖它？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        # 3. 定位运行时模板（兼容源码运行和打包后运行）
        if getattr(sys, "frozen", False):
            # 打包后，从 exe 所在目录找 data/runtime_template
            base_dir = os.path.dirname(sys.executable)
        else:
            # 源码运行，从当前文件所在目录推导
            base_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
            
        template_dir = os.path.join(base_dir, "data", "runtime_template")

        # 4. UI 反馈：禁用按钮、变等待光标、显示状态栏
        self.act_export.setEnabled(False)
        self.setCursor(QCursor(Qt.CursorShape.WaitCursor))
        self.statusBar().showMessage("封装中……请稍候")
        
        # 强制刷新一次事件队列，让光标变化和文字立刻在屏幕上显示出来
        QApplication.processEvents()

        # 5. 执行封装
        try:
            ok, msg = export_project(self.project, out_dir, template_dir)
        finally:
            # 恢复UI状态
            self.unsetCursor()
            self._refresh_enabled()
            
        # 6. 提示结果
        if ok:
            self.statusBar().showMessage("封装完成")
            QMessageBox.information(self, "封装成功", msg)
        else:
            self.statusBar().showMessage("封装失败")
            QMessageBox.critical(self, "封装失败", msg)

    # ---------- 辅助 ----------
    def _confirm_discard(self):
        if not self.project.is_open:
            return True
        # 双保险：任一为真即视为有未保存改动
        if not self.project.dirty and not self._dirty_leaves:
            return True
        r = QMessageBox.question(
            self, "未保存的改动",
            "当前项目有未保存的改动，是否放弃？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return r == QMessageBox.StandardButton.Yes

    def _refresh_title(self):
        if self.project.is_open:
            mark = " ●" if self._dirty_leaves else ""    # ★ 用集合判断
            self.setWindowTitle(f"桌宠制作器 — {self.project.name}{mark}")
        else:
            self.setWindowTitle("桌宠制作器")

    def _refresh_enabled(self):
        is_open = self.project.is_open
        self.act_save.setEnabled(is_open)
        
        # 封装仅在已打开、且无脏数据时可用
        can_export = is_open and not self.project.dirty and not self._dirty_leaves
        self.act_export.setEnabled(can_export)

    def closeEvent(self, event):
        # 关窗前先退出框选（避免 overlay 残留）
        sp = self._panel_cache.get("touch_special")
        if sp is not None and hasattr(sp, "_reset_select_state"):
            sp._reset_select_state()
        if hasattr(self.preview_area, "overlay") and self.preview_area.overlay.isVisible():
            self.preview_area.exit_selection_mode()

        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()