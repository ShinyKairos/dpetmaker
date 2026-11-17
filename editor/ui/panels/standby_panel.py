from .base_action_panel import BaseActionPanel


class StandbyPanel(BaseActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="默认待机（必填）",
            project=project,
            assets_subdir="standby",
            mask_subdir="standby",
            config_assets_key="standby_path",
            config_fps_key="standby_fps",
            parent=parent,
        )