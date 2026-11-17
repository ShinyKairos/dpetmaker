from .multi_slot_action_panel import MultiSlotActionPanel


class MovePanel(MultiSlotActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="自主移动",
            project=project,
            slots=[
                {
                    "slot_key": "left",
                    "display_name": "左移",
                    "assets_subdir": "move/left",
                    "mask_subdir": "move/left",
                },
                {
                    "slot_key": "right",
                    "display_name": "右移",
                    "assets_subdir": "move/right",
                    "mask_subdir": "move/right",
                },
            ],
            config_fps_key="move_fps",
            default_fps=16,
            parent=parent,
        )