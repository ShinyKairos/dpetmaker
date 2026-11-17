# 封装时裁剪 project / icon / special_touches[].name / animation.exit_fps

"""
项目容器：管理"当前项目"状态 + 目录创建 + 打开/保存。

一个 Project 实例 = 一个打开的项目。
未打开项目时 is_open 返回 False。
"""
import os
import shutil

from .config_io import load_config, save_config, make_default_config


# 五档尺寸（设计草案 2.1）
SIZE_OPTIONS = [182, 258, 364, 516, 728]

# 新建项目时一次性建好的目录（相对项目根，跟运行时 config.json 一一对应）
ASSET_SUBDIRS = [
    "assets/boot",
    "assets/exit",
    "assets/standby",
    "assets/move/left",
    "assets/move/right",
    "assets/long_idle/start",
    "assets/long_idle/loop",
    "assets/long_idle/end",
    "assets/touch/normal",
    "assets/drag",
    "assets/talk",
    "assets/interact",
    "assets/ui",
    "assets/icon",
    "mask/boot",
    "mask/exit",
    "mask/standby",
    "mask/move/left",
    "mask/move/right",
    "mask/long_idle/start",
    "mask/long_idle/loop",
    "mask/long_idle/end",
    "mask/touch/normal",
    "mask/drag",
    "mask/talk",
    "mask/interact"
]


class Project:
    def __init__(self):
        self.path = ""        # 项目根目录（绝对路径）
        self.config = None    # 已加载的配置字典
        self.dirty = False    # 是否有未保存改动

    @property
    def is_open(self):
        return bool(self.path) and self.config is not None

    @property
    def name(self):
        return os.path.basename(self.path) if self.path else ""

    @property
    def config_path(self):
        return os.path.join(self.path, "project_config.json") if self.path else ""

    # ---------- 新建 ----------
    def create(self, save_root, project_name, size):
        """返回 (ok, err_msg)。"""
        name = (project_name or "").strip()
        if not name:
            return False, "项目名不能为空"
        if size not in SIZE_OPTIONS:
            return False, f"尺寸必须是 {SIZE_OPTIONS} 之一"

        project_path = os.path.join(save_root, name)
        if os.path.exists(project_path):
            return False, f"已存在同名项目：{project_path}"

        try:
            os.makedirs(project_path, exist_ok=False)
            for sub in ASSET_SUBDIRS:
                os.makedirs(os.path.join(project_path, sub), exist_ok=True)

            cfg = make_default_config(name, size)
            if not save_config(os.path.join(project_path, "project_config.json"), cfg):
                raise RuntimeError("初始配置写入失败")
        except Exception as e:
            shutil.rmtree(project_path, ignore_errors=True)
            return False, f"创建项目失败：{e}"

        self.path = project_path
        self.config = cfg
        self.dirty = False
        return True, ""

    # ---------- 打开 ----------
    def open(self, project_path):
        project_path = os.path.abspath(project_path)
        cfg_path = os.path.join(project_path, "project_config.json")
        if not os.path.exists(cfg_path):
            return False, f"未找到 project_config.json：\n{cfg_path}"
        cfg = load_config(cfg_path)
        if cfg is None:
            return False, "配置文件读取失败（主文件与 .bak 均损坏）"

        self.path = project_path
        self.config = cfg
        self.dirty = False
        return True, ""

    # ---------- 保存 ----------
    def save(self):
        if not self.is_open:
            return False, "当前没有打开的项目"
        if not save_config(self.config_path, self.config):
            return False, "保存失败（可能是磁盘只读 / 权限不足）"
        self.dirty = False
        return True, ""