from .base_action_panel import BaseActionPanel


class TalkPanel(BaseActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="对话状态",
            project=project,
            assets_subdir="talk",
            mask_subdir="talk",
            config_assets_key="talk_path",
            config_fps_key="talk_fps",
            parent=parent,
        )