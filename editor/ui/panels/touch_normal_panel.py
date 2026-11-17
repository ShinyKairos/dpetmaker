from .base_action_panel import BaseActionPanel


class TouchNormalPanel(BaseActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="默认触摸",
            project=project,
            assets_subdir="touch/normal",
            mask_subdir="touch/normal",
            config_assets_key="touch_normal_path",
            config_fps_key="touch_fps",
            parent=parent,
        )