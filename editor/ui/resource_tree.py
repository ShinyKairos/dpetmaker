from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem
from PyQt6.QtCore import Qt, pyqtSignal


# (key, 显示名, 父节点key, 是否分类父节点)
# 所有叶子 key 必须与 panel_registry.PANEL_META 一致
TREE_STRUCTURE = [
    ("category_global", "全局资源", None, True),
    ("icon", "成品图标", "category_global", False),

    ("category_action", "全局动作", None, True),
    ("boot", "开机动作", "category_action", False),
    ("exit", "退出动作", "category_action", False),

    ("category_standby", "待机动作", None, True),
    ("standby", "默认待机（必填）", "category_standby", False),
    ("move", "自主移动", "category_standby", False),
    ("long_idle", "长时间待机", "category_standby", False),
    ("behavior", "行为参数", "category_standby", False),

    ("category_touch", "触摸动作", None, True),
    ("touch_normal", "默认触摸", "category_touch", False),
    ("touch_special", "特殊触摸", "category_touch", False),

    ("category_drag", "拖拽动作", None, True),
    ("drag", "拖拽状态", "category_drag", False),

    ("category_interact", "互动动作", None, True),
    ("interact", "互动分组", "category_interact", False),

    ("category_talk", "对话动作", None, True),
    ("talk", "对话状态", "category_talk", False),

    ("category_ui_ai", "界面与 AI", None, True),
    ("ui_style", "UI 样式", "category_ui_ai", False),
    ("prompt", "提示词编辑", "category_ui_ai", False),
]


class ResourceTree(QTreeWidget):
    """左侧资源树。
    - 分类节点：不可选中，单击展开/折叠
    - 叶子节点：点击触发 leaf_selected(key)
    """
    leaf_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.setAnimated(True)

        self._key_to_item = {}
        self._build()
        self.expandAll()

        # 连接信号：分类折叠用 itemClicked，叶子切换用 currentItemChanged
        self.itemClicked.connect(self._on_item_clicked)
        self.currentItemChanged.connect(self._on_current_changed)

    def _build(self):
        for key, display, parent_key, is_category in TREE_STRUCTURE:
            item = QTreeWidgetItem([display])
            item.setData(0, Qt.ItemDataRole.UserRole, key)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, is_category)
            item.setData(0, Qt.ItemDataRole.UserRole + 2, display)

            if is_category:
                # 分类节点不可选中 → 点击时 currentItemChanged 不会触发
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                f = item.font(0)
                f.setBold(True)
                item.setFont(0, f)
                # ★ 不设置任何颜色 → 自动跟随系统主题（亮/暗都清晰）

            if parent_key is None:
                self.addTopLevelItem(item)
            else:
                parent = self._key_to_item.get(parent_key)
                if parent is not None:
                    parent.addChild(item)
                else:
                    print(f"⚠ 树的父节点缺失：{parent_key}，{key} 将作为顶层节点")
                    self.addTopLevelItem(item)

            self._key_to_item[key] = item

    # ---------- 事件 ----------
    def _on_item_clicked(self, item, column):
        # 只处理分类节点：单击切换展开/折叠
        if item.data(0, Qt.ItemDataRole.UserRole + 1):
            item.setExpanded(not item.isExpanded())

    def _on_current_changed(self, current, previous):
        if current is None:
            return
        if current.data(0, Qt.ItemDataRole.UserRole + 1):
            return  # 分类节点不触发
        key = current.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.leaf_selected.emit(key)

    # ---------- 外部接口 ----------
    def select_first_leaf(self):
        """选中并触发第一个叶子节点（用于打开项目后自动显示默认面板）"""
        for key, display, parent_key, is_category in TREE_STRUCTURE:
            if not is_category:
                item = self._key_to_item.get(key)
                if item is not None:
                    self.setCurrentItem(item)
                    return

    # ---------- ★ 新增：脏叶圆点刷新 ----------
    def set_dirty_leaves(self, dirty_keys):
        """按 dirty_keys（叶子 key 集合）刷新圆点。
        - 叶子在集合中 → "● 原文字"
        - 分类任一子孙叶子脏 → "● 原文字"
        """
        dirty_keys = dirty_keys or set()
        for key, item in self._key_to_item.items():
            base = item.data(0, Qt.ItemDataRole.UserRole + 2) or item.text(0)
            is_cat = bool(item.data(0, Qt.ItemDataRole.UserRole + 1))
            if is_cat:
                dirty = self._has_dirty_descendant(item, dirty_keys)
            else:
                dirty = key in dirty_keys
            new_text = f"● {base}" if dirty else base
            if item.text(0) != new_text:
                item.setText(0, new_text)

    def _has_dirty_descendant(self, item, dirty_keys):
        for i in range(item.childCount()):
            child = item.child(i)
            ckey = child.data(0, Qt.ItemDataRole.UserRole)
            ccat = bool(child.data(0, Qt.ItemDataRole.UserRole + 1))
            if ccat:
                if self._has_dirty_descendant(child, dirty_keys):
                    return True
            else:
                if ckey in dirty_keys:
                    return True
        return False