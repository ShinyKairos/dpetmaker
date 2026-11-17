"""
配置读写层：
  1. 从磁盘读 project_config.json
  2. 原子写回（先写 .tmp → 备份 .bak → replace）
  3. 提供一份"空白项目配置"模板

这里是所有配置读写的唯一入口。
后续任何面板（动画/提示词/图标/样式）都调用这三个函数。
"""
import os
import json
import shutil


def load_config(path):
    """读取配置。主文件损坏时自动尝试 .bak。都失败返回 None。"""
    for p in (path, path + ".bak"):
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            print(f"⚠ 读取失败 {p}: {e}")
    return None


def save_config(path, data):
    """原子写。返回 True / False。"""
    try:
        tmp = path + ".tmp"
        bak = path + ".bak"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            try:
                if os.path.exists(bak):
                    os.remove(bak)
                shutil.copy(path, bak)
            except Exception:
                pass
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"⚠ 保存配置失败：{e}")
        try:
            if os.path.exists(path + ".tmp"):
                os.remove(path + ".tmp")
        except Exception:
            pass
        return False


def make_default_config(project_name, size):
    """空白项目配置。结构 = 运行时的 config.json + 编辑器扩展字段。"""
    return {
        "project": {"name": project_name, "version": 1},
        "window": {"width": size, "height": size},
        "icon": {"path": ""},                       # 编辑器扩展：自定义图标
        "ui_style": {
            "bubble": {
                "bg_color": "rgba(255,255,255,230)",
                "text_color": "#000000",
                "padding": 12,
                "font_family": "微软雅黑",
                "font_size": 10,
                "border_radius": 8,
            },
            "chat_input": {
                "menu_bg": "rgba(255,255,255,0.95)",
                "btn_bg": "rgba(255,255,255,0.9)",
                "btn_hover_bg": "#f0f0f0",
                "text_color": "#000000",
                "border_color": "#dddddd",
            },
            "right_menu": {
                "menu_bg": "rgba(255,255,255,0.95)",
                "btn_bg": "rgba(255,255,255,0.9)",
                "btn_hover_bg": "#f0f0f0",
                "text_color": "#000000",
                "border_color": "#dddddd",
            },
            "interact_window": {
                "window_bg": "rgba(255,255,255,0.95)",
                "btn_bg": "#ffffff",
                "btn_hover_bg": "#f0f0f0",
                "btn_disabled_bg": "#f5f5f5",
                "btn_disabled_color": "#bbbbbb",
                "text_color": "#000000",
                "border_color": "#dddddd",
                "tab_bg": "#f5f5f5",
                "tab_selected_bg": "#ffffff",
            },
            "advanced_window": {
                "message_bubble": {
                    "user_bg": "#d0e8ff",
                    "assistant_bg": "#f0f0f0",
                    "border_radius": 8,
                    "max_width": 520,
                    "font_size": 22,
                    "time_color": "#999999",
                    "time_font_size": 11,
                    "text_color": "#000000",
                    "edit_btn_bg": "#ffffff",
                    "edit_btn_border": "#cccccc",
                }
            },
            "behavior_window": {
                "window_bg": "#ffffff",
                "text_color": "#000000",
                "btn_bg": "#ffffff",
                "btn_hover_bg": "#f0f0f0",
                "border_color": "#dddddd",
            },
        },
        "animation": {
            "boot_fps": 16, "exit_fps": 16, "standby_fps": 16, "touch_fps": 16,
            "drag_fps": 16, "move_fps": 16, "long_idle_fps": 16,
            "interact_fps": 16, "talk_fps": 16,
        },
        "assets": {
            "boot_path": "./assets/boot",
            "standby_path": "./assets/standby",
            "touch_normal_path": "./assets/touch/normal",
            "drag_path": "./assets/drag",
            "move_left_path": "./assets/move/left",
            "move_right_path": "./assets/move/right",
            "long_idle_start_path": "./assets/long_idle/start",
            "long_idle_loop_path": "./assets/long_idle/loop",
            "long_idle_end_path": "./assets/long_idle/end",
            "exit_path": "./assets/exit",
            "talk_path": "./assets/talk",
            "special_touches": [],
        },
        "interact": {"groups": []},
        "auto_behavior": {
            "move_trigger_seconds": 7,
            "move_probability": 0.6,
            "move_duration_seconds": 2,
            "move_speed": 20,
            "long_idle_trigger_seconds": 30,
        },
        "ai_system": {
            "api_config": {"base_url": "", "api_key": "", "model_name": ""},
            "model_params": {
                "temperature": 1.0, "max_tokens": 16384,
                "story_max_tokens": 65535, "top_p": 1.0, "top_k": 50,
                "frequency_penalty": 0.0, "presence_penalty": 0.0,
                "enable_thinking": False, "debug_include_reasoning": False,
                "reasoning_effort": "high", "context_max_rounds": 50,
            },
            "prompt_config": {
                "char_name": "", "user_name": "",
                "global_prompt": "", "character_card": "", "user_card": "",
                "realtime_prompt": "", "story_prompt": "", "error_tip": "",
            },
            "ui_config": {
                "text_speed_char_per_sec": 4,
                "bubble_max_width": 320,
                "bubble_stay_seconds": 5,
            },
            "output_filter": {
                "fallback_to_raw_if_empty": True,
                "rules": [
                    {"name": "思考标签",
                     "pattern": "<(think|thinking|reasoning|thought)\\b[^>]*>.*?</\\1>",
                     "flags": ["DOTALL", "IGNORECASE"], "replacement": ""},
                    {"name": "中文思考前缀行",
                     "pattern": "^思考[:：].*?$",
                     "flags": ["MULTILINE"], "replacement": ""},
                    {"name": "多余空行压缩",
                     "pattern": "\\n{3,}",
                     "flags": [], "replacement": "\n\n"},
                    {
                    "name": "回复开头的时间戳（防模型模仿历史格式）",
                    "pattern": "^\\[\\d{1,2}-\\d{1,2}\\s+\\d{1,2}:\\d{2}\\]\\s*",
                    "flags": [],
                    "replacement": ""
                    }
                ],
            },
            "timestamp_config": {
                "enable": True, "inject_to_prompt": True,
                "inject_current_time": True,
                "inject_format": "[{time}] ",
                "time_format": "%m-%d %H:%M",
                "current_time_format": "%Y-%m-%d %H:%M %A",
                "inject_instruction": "你收到的对话记录中，每条消息前的 [时间] 表示该消息发生的真实时间。请结合消息间隔与当前时间自然回应用户：如果用户间隔很久才回复，可以表现出等待、忙碌、困倦等符合角色设定的反应；如果回复很快，则保持连贯的即时交流感。\n**重要**：这些 [时间] 是系统标注的元数据，不是你说话的一部分。你的回复中**绝对不要**以 [时间] 或 [xx-xx xx:xx] 形式开头，也不要包含任何此类时间戳标签。系统会自动处理时间显示，你只需自然地输出角色对话内容。",
            },
        },
    }