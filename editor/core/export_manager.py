"""
一键封装流水线核心逻辑。
负责：复制运行时模板 → 复制素材/掩码 → 精简配置 → 处理图标。
"""
import os
import json
import shutil
import copy

def _create_shortcut(exe_path, ico_path, output_dir, project_name):
    """
    使用 PowerShell 调用 WScript.Shell 在当前目录生成带自定义图标的快捷方式。
    """
    shortcut_path = os.path.join(output_dir, f"{project_name}.lnk")
    
    # 如果 ico 不存在，则快捷方式不带自定义图标
    icon_location = ico_path if os.path.exists(ico_path) else exe_path

    # 构建 PowerShell 脚本。注意处理路径中的单双引号
    ps_script = f"""
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut('{shortcut_path}')
    $sc.TargetPath = '{exe_path}'
    $sc.WorkingDirectory = '{output_dir}'
    $sc.IconLocation = '{icon_location},0'
    $sc.Save()
    """
    
    import subprocess
    try:
        # 调用 PowerShell，执行策略设为 Bypass 以防止签名拦截
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True, text=True, timeout=10
        )
        return True
    except Exception as e:
        print(f"[封装] 生成快捷方式失败：{e}")
        return False

def export_project(project, output_root, runtime_template_dir):
    """
    将当前项目封装导出为成品文件夹。
    返回 (ok: bool, msg: str)
    """
    if not project.is_open:
        return False, "没有打开的项目。"
    
    if not os.path.exists(runtime_template_dir):
        return False, f"运行时模板缺失，请检查目录：\n{runtime_template_dir}"
    
    exe_path = os.path.join(runtime_template_dir, "pet_runtime.exe")
    if not os.path.exists(exe_path):
        return False, f"运行时模板中未找到 pet_runtime.exe，请重新打包模板。"

    # 1. 准备输出目录
    project_name = project.name
    dest_dir = os.path.join(output_root, project_name)
    
    # 如果目标已存在，这里默认由 UI 层询问过，直接清除重建
    if os.path.exists(dest_dir):
        try:
            shutil.rmtree(dest_dir)
        except Exception as e:
            return False, f"无法清理已存在的目标文件夹：\n{e}"

    try:
        os.makedirs(dest_dir)
    except Exception as e:
        return False, f"创建输出目录失败：\n{e}"

    # 2. 复制运行时模板
    try:
        # 忽略模板可能自带的 data 文件夹或 config.json，防止污染
        def ignore_patterns(path, names):
            ignored = []
            for name in names:
                if name == "data" or name == "config.json":
                    ignored.append(name)
            return ignored

        shutil.copytree(
            runtime_template_dir, 
            dest_dir, 
            ignore=ignore_patterns, 
            dirs_exist_ok=True
        )
    except Exception as e:
        return False, f"复制运行时模板失败：\n{e}"

    # 3. 重命名 exe
    new_exe_path = os.path.join(dest_dir, f"{project_name}.exe")
    try:
        os.rename(os.path.join(dest_dir, "pet_runtime.exe"), new_exe_path)
    except Exception as e:
        return False, f"重命名 exe 失败：\n{e}"

    # 4. 准备成品目录结构
    dest_data_dir = os.path.join(dest_dir, "data")
    os.makedirs(dest_data_dir, exist_ok=True)
    os.makedirs(os.path.join(dest_data_dir, "chat"), exist_ok=True)

    # 5. 复制素材与掩码（必须复制到 exe 根目录）
    src_assets = os.path.join(project.path, "assets")
    src_mask = os.path.join(project.path, "mask")
    
    if os.path.exists(src_assets):
        shutil.copytree(src_assets, os.path.join(dest_dir, "assets"))
    if os.path.exists(src_mask):
        shutil.copytree(src_mask, os.path.join(dest_dir, "mask"))

    # 6. 处理图标 (运行时优先读取 data/icon.ico 作为托盘图标)
    src_ico = os.path.join(project.path, "assets", "icon.ico")
    if os.path.exists(src_ico):
        shutil.copy2(src_ico, os.path.join(dest_data_dir, "icon.ico"))

    # 7. 生成精简配置文件（必须生成在 exe 根目录）
    try:
        cfg = copy.deepcopy(project.config)
        
        # 剔除编辑器专属字段
        cfg.pop("project", None)
        cfg.pop("icon", None)
        
        if "animation" in cfg:
            cfg["animation"].pop("exit_fps", None)
            
        if "assets" in cfg and "special_touches" in cfg["assets"]:
            for touch in cfg["assets"]["special_touches"]:
                touch.pop("name", None)
                
        config_dest = os.path.join(dest_dir, "config.json")
        with open(config_dest, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        return False, f"生成成品配置失败：\n{e}"

    # 7.5 生成带图标的快捷方式
    shortcut_created = False
    src_ico_for_shortcut = os.path.join(dest_data_dir, "icon.ico")
    # 调用辅助函数
    shortcut_created = _create_shortcut(
        new_exe_path, 
        src_ico_for_shortcut, 
        dest_dir, 
        project_name
    )

    # 生成提示信息
    msg = f"封装成功！\n\n已生成到：\n{dest_dir}"
    if shortcut_created:
        msg += "\n\n✅ 已在输出目录生成带自定义图标的快捷方式。"
        if os.path.exists(src_ico_for_shortcut):
            msg += "\n（你可以直接发送/移动该 .lnk 文件到任何地方使用）"
        else:
            msg += "\n（未配置自定义图标，使用默认图标）"

    msg = f"封装成功！\n\n已生成到：\n{dest_dir}"
    return True, msg