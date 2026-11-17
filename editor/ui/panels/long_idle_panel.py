from .multi_slot_action_panel import MultiSlotActionPanel


class LongIdlePanel(MultiSlotActionPanel):
    def __init__(self, project, parent=None):
        super().__init__(
            title="长时间待机",
            project=project,
            slots=[
                {
                    "slot_key": "start",
                    "display_name": "开场",
                    "assets_subdir": "long_idle/start",
                    "mask_subdir": "long_idle/start",
                },
                {
                    "slot_key": "loop",
                    "display_name": "循环",
                    "assets_subdir": "long_idle/loop",
                    "mask_subdir": "long_idle/loop",
                },
                {
                    "slot_key": "end",
                    "display_name": "退场",
                    "assets_subdir": "long_idle/end",
                    "mask_subdir": "long_idle/end",
                },
            ],
            config_fps_key="long_idle_fps",
            default_fps=16,
            parent=parent,
        )