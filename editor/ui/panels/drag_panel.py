from .base_action_panel import BaseActionPanel


class DragPanel(BaseActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="拖拽状态",
            project=project,
            assets_subdir="drag",
            mask_subdir="drag",
            config_assets_key="drag_path",
            config_fps_key="drag_fps",
            parent=parent,
        )