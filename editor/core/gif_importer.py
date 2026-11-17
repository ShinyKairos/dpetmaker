"""
GIF 拆帧 + 掩码生成核心逻辑。

对外只暴露一个函数 split_gif_to_frames()，输入 GIF 路径和两个输出目录，
输出 QPixmap 列表 + fps，供预览区直接播放。

里程碑 E 复用此函数，只是 frames_dir / mask_dir 换成项目内的 assets / mask 子目录。

素材尺寸自适应：
  传入 target_size=(w, h) 时，每一帧会被"等比缩放（只缩不放）+ 居中"
  贴到 w×h 的透明画布上，最终 PNG 尺寸严格等于 target_size。
  这样运行时直接 1:1 绘制即可，不会溢出/歪斜，预览区 1:1 显示即所见即所得。
"""
import os
import shutil

from PIL import Image, ImageSequence


def split_gif_to_frames(
    gif_path,
    frames_dir,
    mask_dir,
    preview_frame_index=0,
    mask_scale=4,
    clear_before=True,
    target_size=None,
):
    """拆分 GIF 为 PNG 序列帧，生成 preview.png 和 1/4 二值掩码。

    参数：
        gif_path             输入 GIF 路径
        frames_dir           帧输出目录（PNG，4 位补零命名 0001.png ~）
        mask_dir             掩码输出目录（1/4 尺寸二值 PNG，同名）
        preview_frame_index  preview.png 使用第几帧（0 起，None/负数按 0）
        mask_scale           掩码缩小倍数（默认 4，即 1/4 尺寸）
        clear_before         导入前是否清空 frames_dir 和 mask_dir
        target_size          (w, h) 或 None。
                             None → 保持原尺寸；
                             给定 → 每帧缩放到 w×h 画布（等比、居中、只缩不放）。

    返回：
        (ok, frames, fps, err_msg)
    """
    from PyQt6.QtGui import QPixmap  # 延迟导入，core 层尽量不依赖 UI

    if not os.path.isfile(gif_path):
        return False, [], 10, f"文件不存在：{gif_path}"

    # 校验 target_size
    if target_size is not None:
        try:
            tw, th = int(target_size[0]), int(target_size[1])
            if tw <= 0 or th <= 0:
                raise ValueError
            target_size = (tw, th)
        except (TypeError, ValueError, IndexError):
            return False, [], 10, f"target_size 非法：{target_size!r}"

    # 清空旧内容
    if clear_before:
        for d in (frames_dir, mask_dir):
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(mask_dir, exist_ok=True)

    # 打开 GIF
    try:
        img = Image.open(gif_path)
    except Exception as e:
        return False, [], 10, f"打开 GIF 失败：{e}"

    # 拆帧（自动处理 disposal=2 残影问题）
    try:
        rgba_frames = _extract_rgba_frames(img)
    except Exception as e:
        return False, [], 10, f"拆帧失败：{e}"

    if not rgba_frames:
        return False, [], 10, "GIF 中未提取到任何帧"

    # ★ 路线 A：每帧缩放到 target_size（等比、居中、只缩不放）
    if target_size is not None:
        try:
            rgba_frames = [
                _fit_and_center_frame(f, target_size[0], target_size[1])
                for f in rgba_frames
            ]
        except Exception as e:
            return False, [], 10, f"缩放至目标尺寸失败：{e}"

    # 推算 fps（GIF 的 duration 单位是毫秒）
    duration_ms = img.info.get("duration", 100)
    try:
        duration_ms = int(duration_ms)
    except Exception:
        duration_ms = 100
    if duration_ms <= 0:
        duration_ms = 100
    fps = max(1, min(60, int(round(1000 / duration_ms))))

    # 保存每帧 PNG + 对应掩码（掩码基于缩放后的帧生成，保证 1/4 对齐）
    frames = []
    try:
        for i, frame in enumerate(rgba_frames):
            frame_path = os.path.join(frames_dir, f"{i + 1:04d}.png")
            frame.save(frame_path, "PNG")

            mask_path = os.path.join(mask_dir, f"{i + 1:04d}.png")
            _make_mask(frame, mask_path, mask_scale)

            pix = QPixmap(frame_path)
            if not pix.isNull():
                frames.append(pix)
    except Exception as e:
        return False, [], 10, f"保存帧失败：{e}"

    # preview.png（用户指定的帧）
    if preview_frame_index is None or preview_frame_index < 0:
        preview_frame_index = 0
    preview_frame_index = min(preview_frame_index, len(rgba_frames) - 1)
    try:
        rgba_frames[preview_frame_index].save(
            os.path.join(frames_dir, "preview.png"), "PNG"
        )
    except Exception as e:
        print(f"⚠ 保存 preview.png 失败：{e}")

    return True, frames, fps, ""


# ===================== 路线 A：等比缩放 + 居中 =====================
def _fit_and_center_frame(rgba_img, target_w, target_h):
    """把 RGBA 图像等比缩放（只缩不放）后居中贴到 target_w × target_h 透明画布上。

    - 原图 <= 目标：保持原尺寸，居中，四周留透明边（不放大避免糊）。
    - 原图 > 目标：等比缩小到能放进目标，居中。
    - 永远不拉伸（宽高同比例）。
    """
    w, h = rgba_img.size
    if w <= 0 or h <= 0:
        return Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))

    # 只缩小不放大：scale = min(目标宽/原宽, 目标高/原高, 1.0)
    scale = min(target_w / w, target_h / h, 1.0)

    if scale < 1.0:
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        # LANCZOS 是质量最高的缩小算法
        resized = rgba_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    else:
        new_w, new_h = w, h
        resized = rgba_img

    canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    # 用 resized 自身 alpha 做 mask，透明像素完全透出来
    canvas.paste(resized, (offset_x, offset_y), resized)
    return canvas


# ===================== 内部：拆帧 =====================
def _extract_rgba_frames(img):
    """从 GIF 提取所有帧为 RGBA 列表。

    策略：
      - 无 disposal=2 的 GIF → 简单路径（ImageSequence 迭代）
      - 有 disposal=2 的 GIF → 手动合成路径（避免残影）
    """
    n_frames = getattr(img, "n_frames", 1)
    if n_frames <= 1:
        return [img.convert("RGBA").copy()]

    # 探测是否使用 disposal=2（恢复背景）
    has_disposal_2 = False
    for i in range(n_frames):
        try:
            img.seek(i)
            if getattr(img, "disposal_method", 0) == 2:
                has_disposal_2 = True
                break
        except Exception:
            continue

    if not has_disposal_2:
        img.seek(0)
        return [f.convert("RGBA").copy() for f in ImageSequence.Iterator(img)]

    # 手动合成路径（避坑点 1）
    print(f"[GIF 拆帧] 检测到 disposal=2（共 {n_frames} 帧），启用手动合成路径")
    size = img.size
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    frames = []
    prev_disposal = 0

    for i in range(n_frames):
        img.seek(i)
        frame = img.convert("RGBA")

        if prev_disposal == 2:
            # 前一帧要求"恢复背景" → 重置画布为透明
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))

        canvas = Image.alpha_composite(canvas, frame)
        frames.append(canvas.copy())

        prev_disposal = getattr(img, "disposal_method", 0)

    return frames


# ===================== 内部：掩码 =====================
def _make_mask(rgba_image, mask_path, scale=4):
    """1/4 二值掩码：alpha >= 128 → 白，否则黑。"""
    w, h = rgba_image.size
    mw = max(1, w // scale)
    mh = max(1, h // scale)

    alpha = rgba_image.split()[-1]  # RGBA 的 A 通道
    alpha_small = alpha.resize((mw, mh), Image.Resampling.BOX)
    mask = alpha_small.point(lambda p: 255 if p >= 128 else 0).convert("L")
    mask.save(mask_path, "PNG")