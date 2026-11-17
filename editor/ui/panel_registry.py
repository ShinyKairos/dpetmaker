from .placeholder_panel import PlaceholderPanel
from .panels.boot_panel import BootPanel
from .panels.exit_panel import ExitPanel
from .panels.standby_panel import StandbyPanel
from .panels.touch_normal_panel import TouchNormalPanel
from .panels.drag_panel import DragPanel
from .panels.talk_panel import TalkPanel
from .panels.move_panel import MovePanel
from .panels.long_idle_panel import LongIdlePanel
from .panels.behavior_panel import BehaviorPanel
from .panels.prompt_panel import PromptPanel
from .panels.icon_panel import IconPanel
from .panels.touch_special_panel import SpecialTouchPanel
from .panels.ui_style_panel import UIStylePanel
from .panels.interact_panel import InteractPanel

# 每个叶子 key 的元信息（里程碑 E 会被替换成真实面板类）
PANEL_META = {
    "icon": {
        "title": "成品图标",
        "config_path": "icon.path（64×64 PNG，封装时自动转 ICO）",
        "asset_dir": "assets/icon/",
    },
    "boot": {
        "title": "开机动作",
        "config_path": "assets.boot_path",
        "asset_dir": "assets/boot/",
    },
    "exit": {
        "title": "退出动作",
        "config_path": "assets.exit_path",
        "asset_dir": "assets/exit/",
    },
    "standby": {
        "title": "默认待机（必填）",
        "config_path": "assets.standby_path（其它状态缺失素材时回落到此）",
        "asset_dir": "assets/standby/",
    },
    "move": {
        "title": "自主移动",
        "config_path": "assets.move_left_path / move_right_path",
        "asset_dir": "assets/move/left/、assets/move/right/",
    },
    "long_idle": {
        "title": "长时间待机",
        "config_path": "assets.long_idle_start_path / loop / end",
        "asset_dir": "assets/long_idle/{start,loop,end}/",
    },
    "behavior": {
        "title": "行为参数",
        "config_path": "auto_behavior.*（触发等待/概率/时长/速度）",
        "asset_dir": "",
    },
    "touch_normal": {
        "title": "默认触摸",
        "config_path": "assets.touch_normal_path",
        "asset_dir": "assets/touch/normal/",
    },
    "touch_special": {
        "title": "特殊触摸",
        "config_path": "assets.special_touches[]",
        "asset_dir": "assets/touch/special1/、special2/…",
    },
    "drag": {
        "title": "拖拽状态",
        "config_path": "assets.drag_path",
        "asset_dir": "assets/drag/",
    },
    "interact": {
        "title": "互动分组",
        "config_path": "interact.groups[]",
        "asset_dir": "assets/interact/{group_id}/{action_id}/",
    },
    "talk": {
        "title": "对话状态",
        "config_path": "assets.talk_path",
        "asset_dir": "assets/talk/",
    },
    "ui_style": {
        "title": "UI 样式",
        "config_path": "ui_style.*（气泡 / 输入栏 / 右键菜单 / 各窗口）",
        "asset_dir": "assets/ui/",
    },
    "prompt": {
        "title": "提示词编辑",
        "config_path": "ai_system.prompt_config",
        "asset_dir": "",
    },
}


def create_panel(key, project):
    meta = PANEL_META.get(key)
    if meta is None:
        return PlaceholderPanel(
            title=f"未知面板：{key}",
            config_path="",
            asset_dir="",
        )

    # ---------- 已实现的真实面板 ----------
    if key == "boot":
        return BootPanel(project)
    if key == "exit":
        return ExitPanel(project)
    if key == "standby":
        return StandbyPanel(project)
    if key == "touch_normal":
        return TouchNormalPanel(project)
    if key == "drag":
        return DragPanel(project)
    if key == "talk":
        return TalkPanel(project)
    if key == "move":
        return MovePanel(project)
    if key == "long_idle":
        return LongIdlePanel(project)
    if key == "behavior":
        return BehaviorPanel(project)
    if key == "prompt":
        return PromptPanel(project)
    if key == "icon":
        return IconPanel(project)
    if key == "touch_special":
        return SpecialTouchPanel(project)
    if key == "ui_style":
        return UIStylePanel(project)
    if key == "interact":
        return InteractPanel(project)

    # ---------- 其余仍为占位（后续里程碑填充）----------
    return PlaceholderPanel(
        title=meta["title"],
        config_path=meta["config_path"],
        asset_dir=meta["asset_dir"],
    )