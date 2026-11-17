from .base_action_panel import BaseActionPanel


class ExitPanel(BaseActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="退出动作",
            project=project,
            assets_subdir="exit",
            mask_subdir="exit",
            config_assets_key="exit_path",
            config_fps_key="exit_fps",
            parent=parent,
        )