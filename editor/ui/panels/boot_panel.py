from .base_action_panel import BaseActionPanel


class BootPanel(BaseActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="开机动作",
            project=project,
            assets_subdir="boot",
            mask_subdir="boot",
            config_assets_key="boot_path",
            config_fps_key="boot_fps",
            parent=parent,
        )