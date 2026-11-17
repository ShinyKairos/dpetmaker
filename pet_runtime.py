import sys, os, json, time, random, requests, re

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QPushButton, QTabWidget,
    QSystemTrayIcon, QMenu, QLabel, QHBoxLayout, QGridLayout,
    QLineEdit,
    QFormLayout, QSlider, QDoubleSpinBox, QSpinBox, QCheckBox,
    QPlainTextEdit, QScrollArea, QGroupBox, QMessageBox,
    QDialog,
    QComboBox, QFileDialog,
    QInputDialog
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QPainter, QBitmap, QImage,
    QFont, QPainterPath, QColor, QFontMetrics, QPolygonF,
    QPalette, qAlpha, qRgb
)
from PyQt6.QtCore import (
    Qt, QPoint, QSize, QTimer, pyqtSignal, QRect, QRectF, QPointF, QThread, QFileSystemWatcher
)

# ===================== 全局路径计算 =====================
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def _p(rel_path):
    """把相对路径转成基于 exe/脚本所在目录的绝对路径。"""
    if not rel_path:
        return rel_path
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.normpath(os.path.join(BASE_DIR, rel_path.lstrip("./\\")))

# ===================== API 错误分类 =====================
def _classify_api_error(e):
    """把 requests 异常分类为 (error_type, friendly_hint, detail) 三元组。

    error_type     —— 用于日志/程序分辨，不直接展示
    friendly_hint  —— 给用户看的简短提示（一行）
    detail         —— 给开发者看的详细原因（含响应正文摘要）
    """
    # 1. 超时
    if isinstance(e, requests.exceptions.Timeout):
        return (
            "timeout",
            "AI 响应超时，请检查网络连接后重试。",
            str(e) or "请求超时",
        )

    # 2. HTTP 状态码错误（raise_for_status 抛出）
    if isinstance(e, requests.exceptions.HTTPError):
        response = getattr(e, "response", None)
        status = response.status_code if response is not None else 0

        body_snippet = ""
        if response is not None:
            try:
                body_snippet = response.text[:500]
            except Exception:
                pass

        detail = f"HTTP {status}: {body_snippet or str(e)}"

        # 服务端返回的具体错误消息（可能为空）
        server_msg = _extract_server_error_message(body_snippet)

        # ★ 400 智能判断：读取服务端消息，判断是否是模型名/接口名问题
        if status == 400:
            msg_lower = (server_msg or "").lower()
            # 判定规则：消息里出现 "model"/"模型"，且同时出现
            # "not" / "exist" / "invalid" / "不存在" / "无法" 之一，
            # 才归为模型名问题（避免 "invalid api key" 等误判）
            if (
                ("model" in msg_lower or "模型" in msg_lower)
                and any(k in msg_lower for k in
                        ("not", "exist", "invalid", "不存在", "无法", "未找到"))
            ):
                hint = "模型名或接口地址不存在，请检查设置。"
                if server_msg:
                    hint = f"模型名或接口地址不存在：{server_msg[:100]}"
                return ("not_found", hint, detail)
            # 其他 400：直接把服务端消息展示给用户（最有助于排查）
            if server_msg:
                return ("bad_request", f"请求被拒绝：{server_msg[:100]}", detail)
            return ("bad_request", "请求参数有误（HTTP 400），请检查设置。", detail)

        if status == 401:
            return ("auth", "API Key 无效或已过期，请在设置中检查。", detail)
        if status == 403:
            return ("forbidden", "当前账号无权访问该接口，或额度已耗尽。", detail)
        if status == 404:
            # 404 有时也返回消息，能显示就更清晰
            if server_msg:
                return ("not_found", f"接口地址或模型名不存在：{server_msg[:100]}", detail)
            return ("not_found", "接口地址或模型名不存在，请检查设置。", detail)
        if status == 422:
            if server_msg:
                return ("bad_request", f"请求被拒绝：{server_msg[:100]}", detail)
            return ("bad_request", "请求参数有误（HTTP 422），请检查设置。", detail)
        if status == 429:
            return ("rate_limit", "请求过于频繁，请稍后再试。", detail)
        if 500 <= status < 600:
            return ("server", "AI 服务端出错，请稍后重试。", detail)
        return ("unknown", f"AI 请求失败（HTTP {status}）。", detail)

    # 3. 连接层错误（DNS 失败、拒绝连接、断网等）
    if isinstance(e, requests.exceptions.ConnectionError):
        return ("network", "无法连接到服务器，请检查网络连接。", str(e))

    # 4. 其他 requests 异常
    if isinstance(e, requests.exceptions.RequestException):
        return ("unknown", "AI 请求失败，请检查网络或设置。", str(e))

    # 5. 非 requests 异常（编程错误等）
    return ("unknown", "AI 请求失败，请查看控制台日志。", str(e))

def _extract_server_error_message(body):
    """从 API 响应正文中提取可读的错误消息。

    兼容多种格式：
    - OpenAI 兼容：{"error": {"message": "..."}}
    - SiliconFlow 等：{"message": "...", "code": ...}
    - 纯文本：直接返回
    返回空串表示无法提取。
    """
    if not body:
        return ""

    body = body.strip()

    # 尝试解析 JSON
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        # 非 JSON（或被截断），直接返回原始文本
        return body[:200]

    if not isinstance(data, dict):
        return ""

    # OpenAI 兼容格式：{"error": {"message": "..."}}
    err = data.get("error")
    if isinstance(err, dict):
        msg = err.get("message", "")
        if msg:
            return str(msg)[:200]
    elif isinstance(err, str):
        return err[:200]

    # SiliconFlow / 其他：{"message": "..."}
    msg = data.get("message", "")
    if msg:
        return str(msg)[:200]

    # 部分服务用 msg
    msg = data.get("msg", "")
    if msg:
        return str(msg)[:200]

    return ""

# ===================== 屏幕边界辅助函数 =====================
def _fit_rect_to_screen(rect, screen=None):
    """把 QRect 夹紧到指定屏幕（默认取矩形中心所在屏幕）的可用区域内。
    若矩形比屏幕还大，则只保证左上角在屏幕内（调用方负责先缩小）。
    """
    if screen is None:
        screen = QApplication.screenAt(rect.center())
    if screen is None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return rect
    geo = screen.availableGeometry()

    # 若矩形比屏幕大，夹到屏幕大小
    w = min(rect.width(), geo.width())
    h = min(rect.height(), geo.height())
    x = max(geo.left(), min(rect.left(), geo.right() - w + 1))
    y = max(geo.top(), min(rect.top(), geo.bottom() - h + 1))
    return QRect(x, y, w, h)


def _screen_of_widget(widget):
    """取 widget 中心所在屏幕，失败回落主屏。"""
    if widget is None:
        return QApplication.primaryScreen()
    s = QApplication.screenAt(widget.frameGeometry().center())
    if s is None:
        s = QApplication.primaryScreen()
    return s

def _estimate_tokens(text):
    """粗略估算 token 数：CJK 1 字≈1 token，其他约 4 字符≈1 token。"""
    if not text:
        return 0
    cjk = 0
    other = 0
    for c in text:
        cp = ord(c)
        if (0x4E00 <= cp <= 0x9FFF or    # CJK 统一表意
            0x3400 <= cp <= 0x4DBF or    # CJK 扩展 A
            0x3040 <= cp <= 0x30FF or    # 日文假名
            0xAC00 <= cp <= 0xD7AF):     # 韩文
            cjk += 1
        else:
            other += 1
    return cjk + (other + 3) // 4

# ===================== 对话气泡控件 =====================
class ChatBubble(QWidget):
    size_changed = pyqtSignal()  # 新增：气泡大小变化时发射信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        # 配置参数
        self.max_width = 320
        self.text_color = QColor("#000000")
        self.bg_color = QColor(255, 255, 255, 230)
        self.padding = 12
        self.font = QFont("微软雅黑", 10)
        self.border_radius = 8
        
        # 逐字显示相关
        self.full_text = ""
        self.show_text = ""
        self.text_timer = QTimer()
        self.text_timer.timeout.connect(self._next_char)
        self.char_speed = 0.25  # 每个字间隔秒数，对应4字/秒
        
        # 停留定时器
        self.stay_timer = QTimer()
        self.stay_timer.setSingleShot(True)
        self.stay_timer.timeout.connect(self.hide)
        
        self.hide()

    def set_config(self, max_width, speed_char_per_sec, stay_seconds):
        """从配置更新参数"""
        self.max_width = max_width
        self.char_speed = 1.0 / speed_char_per_sec
        self.stay_timer.setInterval(int(stay_seconds * 1000))

    def set_style(self, style_dict):
        """从 config 的 ui_style.bubble 应用样式。缺省字段用当前值。"""
        if not style_dict:
            return
        if "bg_color" in style_dict:
            self.bg_color = _css_color_to_qcolor(style_dict["bg_color"])
        if "text_color" in style_dict:
            self.text_color = _css_color_to_qcolor(style_dict["text_color"])
        if "padding" in style_dict:
            self.padding = int(style_dict["padding"])
        if "font_family" in style_dict or "font_size" in style_dict:
            family = style_dict.get("font_family", self.font.family())
            size = int(style_dict.get("font_size", self.font.pointSize()))
            self.font = QFont(family, size)
        if "border_radius" in style_dict:
            self.border_radius = int(style_dict["border_radius"])
        # 若已有文字，让尺寸跟随新 padding/font 重新计算
        if self.full_text:
            self._adjust_size()
        self.update()

    def show_text_animated(self, text):
        """显示文字，启动逐字效果"""
        self.full_text = text
        self.show_text = ""
        self.text_timer.stop()
        self.stay_timer.stop()
        self.show()
        self.raise_()

        # 优化：立即显示第一个字，消除 250ms 的空白感
        if self.full_text:
            self.show_text = self.full_text[0]
            self._adjust_size()
            self.update()
            if len(self.full_text) > 1:
                self.text_timer.start(int(self.char_speed * 1000))
            else:
                self.stay_timer.start()

    def _next_char(self):
        if len(self.show_text) < len(self.full_text):
            self.show_text += self.full_text[len(self.show_text)]
            self._adjust_size()
            self.update()
        else:
            self.text_timer.stop()
            self.stay_timer.start()

    def _adjust_size(self):
        """根据文字自动计算气泡大小"""
        fm = QFontMetrics(self.font)
        # 自动换行计算
        text_rect = fm.boundingRect(
            0, 0, self.max_width - self.padding * 2, 1000,
            Qt.TextFlag.TextWordWrap, self.show_text
        )
        w = text_rect.width() + self.padding * 2
        h = text_rect.height() + self.padding * 2 + 8  # 留小尾巴高度
        # 变化 ≤2px 不重排，避免逐字显示时主窗每帧重定位
        if abs(self.width() - w) <= 2 and abs(self.height() - h) <= 2:
            return
        self.resize(w, h)
        self.size_changed.emit()  # 新增：大小变化后通知主窗口更新位置

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 画气泡背景+小尾巴
        path = QPainterPath()
        # 修复1：整数矩形转浮点矩形，适配addRoundedRect参数要求
        bubble_rect = QRectF(self.rect().adjusted(0, 0, 0, -8))
        path.addRoundedRect(bubble_rect, self.border_radius, self.border_radius)
        
        # 底部中间小三角
        center_x = self.width() / 2  # 用浮点除法
        triangle = [
            QPointF(center_x - 6, self.height() - 8),
            QPointF(center_x + 6, self.height() - 8),
            QPointF(center_x, self.height())
        ]
        path.addPolygon(QPolygonF(triangle))
        
        painter.fillPath(path, self.bg_color)
        
        # 画文字
        painter.setPen(self.text_color)
        painter.setFont(self.font)
        text_rect = self.rect().adjusted(
            self.padding, self.padding,
            -self.padding, -self.padding - 8
        )
        # 同步转浮点矩形，避免同类类型报错
        painter.drawText(QRectF(text_rect), Qt.TextFlag.TextWordWrap, self.show_text)

    def show_placeholder(self, text="…"):
        """显示临时占位（等待 AI 回复时用），不启动停留计时"""
        self.text_timer.stop()
        self.stay_timer.stop()
        self.full_text = text
        self.show_text = text
        self._adjust_size()
        self.update()
        self.show()
        self.raise_()

# ===================== 基础对话输入栏 =====================
class ChatInputBar(QWidget):
    send_clicked = pyqtSignal(str)    # 发送消息信号，携带输入文本
    open_advanced = pyqtSignal()     # 打开高级窗口信号
    close_clicked = pyqtSignal()     # 关闭对话信号

    BAR_HEIGHT = 36

    def __init__(self, parent=None):
        super().__init__()
        self._parent_ref = parent
        self._pet = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(512, self.BAR_HEIGHT)

        # ========== 样式变量（后续制作器可直接从配置读取） ==========
        # 字段与右键菜单完全对齐，支持制作器全局统一样式配置
        self.style_config = {
            "menu_bg": "rgba(255,255,255,0.95)",
            "btn_bg": "rgba(255,255,255,0.9)",
            "btn_hover_bg": "#f0f0f0",
            "text_color": "#000000",
            "border_color": "#dddddd"
        }

        # 水平布局
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 输入框
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("和我说点什么吧~")
        self.input_edit.setFixedHeight(self.BAR_HEIGHT)
        self.input_edit.returnPressed.connect(self._on_send)
        layout.addWidget(self.input_edit, 1)

        # 三个功能按钮
        self.btn_send = QPushButton("←")
        self.btn_send.setFixedSize(self.BAR_HEIGHT, self.BAR_HEIGHT)
        self.btn_send.clicked.connect(self._on_send)
        layout.addWidget(self.btn_send)

        self.btn_advanced = QPushButton("…")
        self.btn_advanced.setFixedSize(self.BAR_HEIGHT, self.BAR_HEIGHT)
        self.btn_advanced.clicked.connect(self.open_advanced.emit)
        layout.addWidget(self.btn_advanced)

        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(self.BAR_HEIGHT, self.BAR_HEIGHT)
        self.btn_close.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.btn_close)

        self._update_style()

    def attach_pet(self, pet_window):
        self._pet = pet_window
        self._sync_style_from_config()

    def _sync_style_from_config(self):
        if self._pet is None:
            return
        try:
            ui = self._pet.config.get("ui_style", {}).get("chat_input", {})
            if ui:
                self.set_style_config(ui)
        except Exception as e:
            print(f"[warn] chat_input 样式刷新失败: {e}")

    def set_style_config(self, config_dict):
        """从 config 的 ui_style.chat_input 应用样式。"""
        if not config_dict:
            return
        self.style_config.update(config_dict)
        self._update_style()

    def _update_style(self):
        s = self.style_config
        bg = _qss_color(s['btn_bg'])
        text = _qss_color(s['text_color'])
        border = _qss_color(s['border_color'])
        hover = _qss_color(s['btn_hover_bg'])

        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 0 8px;
                font-size: 12px;
            }}
        """)

        btn_qss = f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                font-size: 16px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:disabled {{
                background-color: #f5f5f5;
                color: #bbbbbb;
            }}
        """
        self.btn_send.setStyleSheet(btn_qss)
        self.btn_advanced.setStyleSheet(btn_qss)
        self.btn_close.setStyleSheet(btn_qss)

    def _on_send(self):
        """发送按钮触发"""
        text = self.input_edit.text().strip()
        if text:
            self.send_clicked.emit(text)
            self.input_edit.clear()

    def set_input_enabled(self, enabled):
        """控制输入框和发送按钮是否可用"""
        self.input_edit.setEnabled(enabled)
        self.btn_send.setEnabled(enabled)

    def focus_input(self):
        """自动聚焦输入框"""
        self.input_edit.setFocus()

# ===================== AI请求后台线程（兼容增强版） =====================
class AIRequestWorker(QThread):
    reply_chunk_received = pyqtSignal(str)      # 流式：收到正文片段
    reply_received = pyqtSignal(str)           # 完整回复接收成功
    request_finished = pyqtSignal()            # 请求结束
    request_error = pyqtSignal(str, str, str)  # 请求出错：(error_type, friendly_hint, detail)

    def __init__(self, api_config, model_params, messages):
        super().__init__()
        self.api_config = api_config
        self.model_params = model_params
        self.messages = messages
        self._is_running = True
        self._total_timeout = 120
        self._fallback_non_stream = False  # 流式失败自动降级非流式

    def stop(self):
        self._is_running = False

    def run(self):
        # 先尝试流式请求
        result = self._run_stream()
        # 流式返回空正文，自动降级非流式重试一次
        if result == "empty" and not self._fallback_non_stream and self._is_running:
            print("【调试】流式返回空正文，自动降级非流式重试")
            self._fallback_non_stream = True
            result = self._run_non_stream()
        
        if result == "ok":
            pass
        elif result == "empty":
            if self._is_running:
                self.request_error.emit(
                    "empty",
                    "AI 返回了空内容，请检查提示词或模型设置。",
                    "模型返回空正文（流式+非流式均失败）",
                )
        elif result == "error":
            pass  # 错误已在内部发出
        
        self.request_finished.emit()

    def _run_stream(self):
        """流式请求，返回 ok / empty / error"""
        full_reply = ""
        start_time = time.time()
        buffer = ""

        try:
            base_url = self.api_config["base_url"].rstrip("/")
            url = f"{base_url}/chat/completions"

            headers = {
                "Authorization": f"Bearer {self.api_config['api_key']}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Connection": "keep-alive",
                "Cache-Control": "no-cache"
            }

            payload = {
                "model": self.api_config["model_name"],
                "messages": self.messages,
                "temperature": self.model_params["temperature"],
                "max_tokens": self.model_params["max_tokens"],
                "top_p": self.model_params["top_p"],
                "frequency_penalty": self.model_params["frequency_penalty"],
                "presence_penalty": self.model_params["presence_penalty"],
                "stream": True
            }

            if self.model_params.get("enable_thinking", False):
                payload["reasoning_effort"] = self.model_params.get("reasoning_effort", "medium")

            response = requests.post(
                url, headers=headers, json=payload,
                stream=True, timeout=(10, 60)
            )
            response.raise_for_status()

            for raw_line in response.iter_lines(decode_unicode=False):
                if time.time() - start_time > self._total_timeout:
                    self.request_error.emit(
                        "timeout",
                        "AI 响应超时，请检查网络连接后重试。",
                        f"请求总超时（>{self._total_timeout} 秒）",
                    )
                    return "error"
                if not self._is_running:
                    return "error"
                if not raw_line:
                    continue

                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue

                data = line[5:].strip()
                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta", choices[0].get("message", {}))
                content = delta.get("content", "") or ""
                reasoning = delta.get("reasoning_content", "") or delta.get("reasoning", "") or ""

                # debug 开关：把思考内容也拼进正文，用于验证过滤规则是否生效
                if self.model_params.get("debug_include_reasoning", False) and reasoning:
                    content = reasoning + content

                if content:
                    full_reply += content
                    self.reply_chunk_received.emit(content)

            if full_reply.strip():
                self.reply_received.emit(full_reply)
                return "ok"
            else:
                return "empty"

        except requests.exceptions.Timeout as e:
            if self._is_running:
                err_type, hint, detail = _classify_api_error(e)
                self.request_error.emit(err_type, hint, detail)
            return "error"
        except Exception as e:
            if self._is_running:
                err_type, hint, detail = _classify_api_error(e)
                self.request_error.emit(err_type, hint, detail)
            return "error"

    def _run_non_stream(self):
        """非流式降级请求，返回 ok / empty / error"""
        try:
            base_url = self.api_config["base_url"].rstrip("/")
            url = f"{base_url}/chat/completions"

            headers = {
                "Authorization": f"Bearer {self.api_config['api_key']}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": self.api_config["model_name"],
                "messages": self.messages,
                "temperature": self.model_params["temperature"],
                "max_tokens": self.model_params["max_tokens"],
                "top_p": self.model_params["top_p"],
                "frequency_penalty": self.model_params["frequency_penalty"],
                "presence_penalty": self.model_params["presence_penalty"],
                "stream": False
            }

            if self.model_params.get("enable_thinking", False):
                payload["reasoning_effort"] = self.model_params.get("reasoning_effort", "medium")

            response = requests.post(
                url, headers=headers, json=payload, timeout=30
            )
            response.raise_for_status()
            data = response.json()

            reply_text = data["choices"][0]["message"]["content"]
            if reply_text.strip():
                self.reply_received.emit(reply_text)
                return "ok"
            else:
                return "empty"

        except Exception as e:
            if self._is_running:
                err_type, hint, detail = _classify_api_error(e)
                self.request_error.emit(err_type, hint, detail)
            return "error"

class PromptEngine:
    def __init__(self, config):
        self.config = config  # 持有配置引用，热重载自动生效

    def _replace_macros(self, text):
        prompt_cfg = self.config["ai_system"]["prompt_config"]
        text = text.replace("{{char}}", prompt_cfg["char_name"])
        text = text.replace("{{user}}", prompt_cfg["user_name"])
        return text

    def _get_ts_config(self):
        return self.config["ai_system"].get("timestamp_config", {})

    def _time_prefix(self, msg):
        """按配置生成时间前缀；未开启或旧记录无时间戳时返回空串"""
        ts_cfg = self._get_ts_config()
        if not ts_cfg.get("enable", False) or not ts_cfg.get("inject_to_prompt", False):
            return ""
        ts = msg.get("ts")
        if not ts:
            return ""
        try:
            time_str = time.strftime(
                ts_cfg.get("time_format", "%m-%d %H:%M"),
                time.localtime(float(ts)),
            )
        except Exception:
            return ""
        fmt = ts_cfg.get("inject_format", "[{time}] ")
        return fmt.replace("{time}", time_str)

    def _format_history(self, history, max_rounds, enable_timestamp=True):
        """截断 → 加时间前缀 → 合并连续同角色消息。
        enable_timestamp=False 时不加 [时间] 前缀（故事模式用）。
        """
        if len(history) > max_rounds * 2:
            history = history[-max_rounds * 2:]

        merged = []
        for msg in history:
            role = msg.get("role", "user")
            content = (self._time_prefix(msg) if enable_timestamp else "") + msg.get("content", "")
            if merged and merged[-1]["role"] == role:
                merged[-1]["content"] += "\n" + content
            else:
                merged.append({"role": role, "content": content})
        return merged

    def _build_system_content(self, base_parts, enable_timestamp=True):
        """拼接 system 内容。
        enable_timestamp=False 时跳过"当前时间"注入和时间指令（故事模式用）。
        无论什么模式，都强制注入角色名与用户名。
        """
        ts_cfg = self._get_ts_config()
        parts = list(base_parts)

        if enable_timestamp and ts_cfg.get("enable", False) and ts_cfg.get("inject_to_prompt", False):
            if ts_cfg.get("inject_current_time", False):
                try:
                    now_str = time.strftime(
                        ts_cfg.get("current_time_format", "%Y-%m-%d %H:%M %A"),
                        time.localtime(),
                    )
                except Exception:
                    now_str = time.strftime("%Y-%m-%d %H:%M", time.localtime())
                parts.append("当前真实时间：" + now_str)

            instruction = (ts_cfg.get("inject_instruction") or "").strip()
            if instruction:
                parts.append(instruction)

        # ★ 强制注入角色名与用户名（实时 + 故事模式都生效，与时间配置无关）
        prompt_cfg = self.config["ai_system"]["prompt_config"]
        char_name = (prompt_cfg.get("char_name") or "").strip()
        user_name = (prompt_cfg.get("user_name") or "").strip()
        if char_name or user_name:
            identity_parts = []
            if char_name:
                identity_parts.append(f"你的名字是「{char_name}」")
            if user_name:
                identity_parts.append(f"与你对话的用户名字是「{user_name}」")
            parts.append("；".join(identity_parts) + "。")

        return "\n\n".join([p for p in parts if p])

    def build_realtime_messages(self, history, extra_scene_prompt=""):
        prompt_cfg = self.config["ai_system"]["prompt_config"]
        max_rounds = self.config["ai_system"]["model_params"]["context_max_rounds"]

        system_parts = [
            self._replace_macros(prompt_cfg["global_prompt"]),
            self._replace_macros(prompt_cfg["user_card"]),
            self._replace_macros(prompt_cfg["character_card"]),
        ]
        scene_prompt = prompt_cfg["realtime_prompt"]
        if extra_scene_prompt:
            scene_prompt += "\n" + extra_scene_prompt
        system_parts.append(self._replace_macros(scene_prompt))

        messages = [{
            "role": "system",
            "content": self._build_system_content(system_parts),
        }]
        messages.extend(self._format_history(history, max_rounds))
        return messages

    def build_story_messages(self, history):
        prompt_cfg = self.config["ai_system"]["prompt_config"]
        max_rounds = self.config["ai_system"]["model_params"]["context_max_rounds"]

        system_parts = [
            self._replace_macros(prompt_cfg["global_prompt"]),
            self._replace_macros(prompt_cfg["user_card"]),
            self._replace_macros(prompt_cfg["character_card"]),
            self._replace_macros(prompt_cfg["story_prompt"]),
        ]

        messages = [{
            "role": "system",
            "content": self._build_system_content(system_parts, enable_timestamp=False),
        }]
        messages.extend(self._format_history(history, max_rounds, enable_timestamp=False))
        return messages

# ===================== 样式工具函数 =====================
def _css_color_to_qcolor(s):
    """CSS 风格颜色字符串 → QColor。
    支持 '#RGB'、'#RRGGBB'、'#AARRGGBB'、'rgb(r,g,b)'、'rgba(r,g,b,a)'、'transparent'、
    以及 Qt 能直接识别的颜色名（'red' 等）。alpha 支持 0~1 和 0~255 两种写法。
    """
    if not s:
        return QColor(0, 0, 0, 0)
    s = str(s).strip()
    low = s.lower()
    if low == "transparent":
        return QColor(0, 0, 0, 0)
    if low.startswith("rgba(") or low.startswith("rgb("):
        try:
            inside = s[s.index("(") + 1:s.rindex(")")]
            parts = [x.strip() for x in inside.split(",")]
            r, g, b = int(float(parts[0])), int(float(parts[1])), int(float(parts[2]))
            if len(parts) >= 4:
                a_val = float(parts[3])
                a = int(round(a_val * 255)) if a_val <= 1.0 else int(round(a_val))
            else:
                a = 255
            return QColor(r, g, b, a)
        except Exception:
            return QColor(0, 0, 0, 0)
    return QColor(s)

def _qss_color(s):
    """把任意格式颜色归一化为 QSS 可安全解析的格式。
    - 不透明时输出 '#rrggbb'
    - 半透明时输出 'rgba(r,g,b,a)'，a 是 0~255 整数
    - 无法识别时输出 'transparent'
    """
    c = _css_color_to_qcolor(s)
    if c.alpha() == 0:
        return "transparent"
    if c.alpha() == 255:
        return c.name()          # "#rrggbb"
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"

# ===================== 文本后处理过滤器（配置驱动版） =====================
_DEFAULT_FILTER_RULES = [
    {
        "name": "思考标签（think/thinking/reasoning/thought）",
        "pattern": r"<(think|thinking|reasoning|thought)\b[^>]*>.*?</\1>",
        "flags": ["DOTALL", "IGNORECASE"],
        "replacement": "",
    },
    {
        "name": "中文思考前缀行",
        "pattern": r"^思考[:：].*?$",
        "flags": ["MULTILINE"],
        "replacement": "",
    },
    {
        "name": "多余空行压缩",
        "pattern": r"\n{3,}",
        "flags": [],
        "replacement": "\n\n",
    },
]

_FLAG_MAP = {
    "DOTALL": re.DOTALL,
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "VERBOSE": re.VERBOSE,
}


def _parse_flags(flag_names):
    flags = 0
    for name in flag_names or []:
        flags |= _FLAG_MAP.get(str(name).upper(), 0)
    return flags


def get_filter_rules(config):
    """从配置读取过滤规则；配置缺失或格式错误时回落内置默认"""
    try:
        rules = config["ai_system"].get("output_filter", {}).get("rules")
        if isinstance(rules, list) and rules:
            return rules
    except Exception:
        pass
    return _DEFAULT_FILTER_RULES


def filter_ai_output(text, config=None):
    """按配置规则清洗文本。config 为 None 时使用内置默认规则"""
    if not text:
        return ""

    rules = get_filter_rules(config) if config is not None else _DEFAULT_FILTER_RULES
    result = text
    for rule in rules:
        pattern = rule.get("pattern", "")
        if not pattern:
            continue
        try:
            result = re.sub(
                pattern,
                rule.get("replacement", ""),
                result,
                flags=_parse_flags(rule.get("flags", [])),
            )
        except re.error as e:
            print(f"【过滤规则错误】规则「{rule.get('name', '未命名')}」：{e}，已跳过")
            continue

    strip_result = True
    if config is not None:
        try:
            strip_result = config["ai_system"].get("output_filter", {}).get("strip_result", True)
        except Exception:
            pass
    return result.strip() if strip_result else result

# ===================== 多模式对话历史管理器 =====================
class ChatHistoryManager:
    def __init__(self, root_dir="./data/chat"):
        self.root_dir = root_dir
        self.sessions_dir = os.path.join(root_dir, "sessions")
        self.index_path = os.path.join(self.sessions_dir, "index.json")
        
        # 按模式分子目录存储
        self.realtime_dir = os.path.join(self.sessions_dir, "realtime")
        self.story_dir = os.path.join(self.sessions_dir, "story")
        os.makedirs(self.realtime_dir, exist_ok=True)
        os.makedirs(self.story_dir, exist_ok=True)

        # 当前状态
        self.current_mode = "realtime"  # realtime / story
        self.current_session_id = None
        
        self._ensure_index()
        self._load_index()

        # 各模式独立确保有默认会话
        data = self._read_full_index()
        if not data.get("current_realtime"):
            self.create_session("realtime", "默认对话", set_active=True)
        if not data.get("current_story"):
            self.create_session("story", "默认故事", set_active=False)

    # ========== 索引管理 ==========
    def _ensure_index(self):
        """确保索引可用。不存在或损坏时从目录扫描重建。"""
        if not os.path.exists(self.index_path):
            self._rebuild_index_from_dirs()
            return
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "sessions" not in data:
                raise ValueError("索引结构不完整")
        except Exception:
            # 备份损坏索引，避免直接丢弃
            broken_path = self.index_path + ".broken"
            try:
                os.replace(self.index_path, broken_path)
                print(f"⚠️ 索引已损坏，已备份为 {broken_path}，将从目录重建")
            except Exception:
                pass
            self._rebuild_index_from_dirs()

    def _rebuild_index_from_dirs(self):
        """扫描 realtime/ 和 story/ 目录下的 .jsonl 文件，重建索引。
        会话名从文件 id（YYYYMMDD_HHMMSS）反推生成，last_time 用文件 mtime。
        """
        sessions = []
        for mode, dir_path in [("realtime", self.realtime_dir), ("story", self.story_dir)]:
            if not os.path.exists(dir_path):
                continue
            for fn in os.listdir(dir_path):
                if not fn.endswith(".jsonl"):
                    continue
                sid = fn[:-len(".jsonl")]
                file_path = os.path.join(dir_path, fn)
                # 从文件 id 反推创建时间（格式 YYYYMMDD_HHMMSS）
                try:
                    ts = time.mktime(time.strptime(sid, "%Y%m%d_%H%M%S"))
                except Exception:
                    ts = os.path.getmtime(file_path)
                try:
                    last = os.path.getmtime(file_path)
                except Exception:
                    last = ts
                label = "对话" if mode == "realtime" else "故事"
                sessions.append({
                    "id": sid,
                    "name": f"{label} {time.strftime('%m-%d %H:%M', time.localtime(ts))}",
                    "type": mode,
                    "create_time": ts,
                    "last_time": last,
                })

        # 按 last_time 升序（会话列表通常按从旧到新展示）
        sessions.sort(key=lambda s: s.get("last_time", 0))

        # 各模式当前会话：取该模式里 last_time 最大的
        current_realtime = None
        current_story = None
        for s in sessions:
            if s["type"] == "realtime":
                current_realtime = s["id"]
            elif s["type"] == "story":
                current_story = s["id"]

        data = {
            "current_realtime": current_realtime,
            "current_story": current_story,
            "sessions": sessions,
        }
        self._save_index(data)
        print(f"✅ 索引已从目录重建：{len(sessions)} 个会话")
        return data

    def _load_index(self):
        data = self._read_full_index()  # 已包含损坏自愈
        if self.current_mode == "realtime":
            self.current_session_id = data.get("current_realtime")
        else:
            self.current_session_id = data.get("current_story")

    def _save_index(self, data):
        """原子写索引：先写 .tmp 再 replace，防止写一半崩溃导致截断。"""
        tmp_path = self.index_path + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.index_path)
        except Exception as e:
            print(f"保存索引失败：{e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _get_session_dir(self, mode):
        return self.realtime_dir if mode == "realtime" else self.story_dir

    def _get_session_file(self, session_id, mode):
        return os.path.join(self._get_session_dir(mode), f"{session_id}.jsonl")

    def _read_full_index(self):
        """读取索引；任何异常/结构不完整都触发从目录重建。"""
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "sessions" not in data:
                raise ValueError("索引结构不完整")
            return data
        except Exception:
            return self._rebuild_index_from_dirs()

    # ========== 模式切换 ==========
    def switch_mode(self, mode):
        """切换对话模式：realtime / story，自动加载对应模式的当前会话"""
        if mode not in ["realtime", "story"]:
            return False
        self.current_mode = mode
        data = self._read_full_index()
        self.current_session_id = data.get(f"current_{mode}")
        
        # 该模式无会话则自动创建默认
        if not self.current_session_id:
            default_name = "默认对话" if mode == "realtime" else "默认故事"
            self.create_session(mode, default_name)
        return True

    # ========== 会话操作接口 ==========
    def list_sessions(self, mode=None):
        """获取指定模式的会话列表，不传则返回当前模式"""
        target_mode = mode if mode else self.current_mode
        data = self._read_full_index()
        return [s for s in data["sessions"] if s["type"] == target_mode]

    def create_session(self, mode=None, session_name="新对话", set_active=True):
        """新建会话。
        set_active=True  ：同时更新 self.current_mode / self.current_session_id（实时对话用）
        set_active=False ：仅更新 data["current_{mode}"]，不改变实例状态（故事模式用）
        """
        target_mode = mode if mode else self.current_mode
        now = time.time()
        session_id = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))

        # 先读 data，避免同一秒内 id 冲突
        data = self._read_full_index()
        existing_ids = {s["id"] for s in data["sessions"]}
        if session_id in existing_ids:
            session_id = f"{session_id}_{int((now % 1) * 1000):03d}"

        session_file = self._get_session_file(session_id, target_mode)
        with open(session_file, "w", encoding="utf-8") as f:
            pass

        data["sessions"].append({
            "id": session_id,
            "name": session_name,
            "type": target_mode,
            "create_time": now,
            "last_time": now
        })
        data[f"current_{target_mode}"] = session_id
        self._save_index(data)

        if set_active:
            self.current_mode = target_mode
            self.current_session_id = session_id
        return session_id

    def switch_session(self, session_id, set_active=True):
        """切换到指定会话。
        set_active=False 时只更新 data["current_{mode}"]，不改实例状态。
        """
        data = self._read_full_index()
        target_session = None
        for s in data["sessions"]:
            if s["id"] == session_id:
                target_session = s
                break
        if not target_session:
            return None

        mode = target_session["type"]
        data[f"current_{mode}"] = session_id
        target_session["last_time"] = time.time()
        self._save_index(data)

        if set_active:
            self.current_mode = mode
            self.current_session_id = session_id
        # 注意：返回的是显式路径加载，避免依赖 self.current_mode
        return self._load_history_file(self._get_session_file(session_id, mode))

    def delete_session(self, session_id, set_active=True):
        """删除指定会话。
        set_active=False 时只更新 data["current_{mode}"]，不改 self.current_session_id。
        """
        data = self._read_full_index()
        target_session = None
        for s in data["sessions"]:
            if s["id"] == session_id:
                target_session = s
                break
        if not target_session:
            return False

        mode = target_session["type"]
        session_file = self._get_session_file(session_id, mode)
        if os.path.exists(session_file):
            os.remove(session_file)

        data["sessions"] = [s for s in data["sessions"] if s["id"] != session_id]

        if data[f"current_{mode}"] == session_id:
            mode_sessions = [s for s in data["sessions"] if s["type"] == mode]
            if mode_sessions:
                data[f"current_{mode}"] = mode_sessions[0]["id"]
            else:
                # 该模式已无任何会话 → 自动建一个默认
                new_id = self._create_default_session_in_data(data, mode)
                data[f"current_{mode}"] = new_id

            if set_active:
                self.current_session_id = data[f"current_{mode}"]

        self._save_index(data)
        return True

    def _create_default_session_in_data(self, data, mode):
        """内部辅助：在给定 data 里添加一个新的默认会话，返回新 id（不落盘）。"""
        now = time.time()
        new_id = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
        existing_ids = {s["id"] for s in data["sessions"]}
        if new_id in existing_ids:
            new_id = f"{new_id}_{int((now % 1) * 1000):03d}"

        default_name = "默认对话" if mode == "realtime" else "默认故事"
        new_file = self._get_session_file(new_id, mode)
        os.makedirs(os.path.dirname(new_file), exist_ok=True)
        with open(new_file, "w", encoding="utf-8") as f:
            pass

        data["sessions"].append({
            "id": new_id,
            "name": default_name,
            "type": mode,
            "create_time": now,
            "last_time": now,
        })
        return new_id

    def rename_session(self, session_id, new_name):
        """重命名会话"""
        data = self._read_full_index()
        for s in data["sessions"]:
            if s["id"] == session_id:
                s["name"] = new_name
                break
        self._save_index(data)
        return True

    # ========== 历史读写 ==========
    def load_current_history(self):
        """加载当前会话的历史记录"""
        if not self.current_session_id:
            return []
        session_file = self._get_session_file(self.current_session_id, self.current_mode)
        return self._load_history_file(session_file)

    def save_current_history(self, history):
        """保存当前会话的历史记录，更新最后活跃时间。
        采用原子写 + .bak 备份，任何时刻磁盘上都是完整版本。
        """
        if not self.current_session_id:
            return False
        session_file = self._get_session_file(self.current_session_id, self.current_mode)
        if not self._atomic_save(session_file, history):
            return False
        # 更新最后活跃时间
        data = self._read_full_index()
        for s in data["sessions"]:
            if s["id"] == self.current_session_id:
                s["last_time"] = time.time()
                break
        self._save_index(data)
        return True

    def _load_history_file(self, path):
        """优先加载 .jsonl；缺失时尝试 .bak；逐行解析，遇到坏行跳过不中断。"""
        if not os.path.exists(path):
            bak_path = path + ".bak"
            if os.path.exists(bak_path):
                print(f"⚠️ 主文件缺失，尝试从备份加载：{bak_path}")
                path = bak_path
            else:
                return []

        history = []
        bad_lines = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        history.append(json.loads(line))
                    except json.JSONDecodeError:
                        bad_lines += 1
                        continue
        except Exception as e:
            print(f"加载对话历史失败：{e}")
        if bad_lines:
            print(f"⚠️ 对话文件有 {bad_lines} 行损坏，已跳过")
        return history

    def get_current_session_file_path(self):
        """获取当前会话文件路径，用于文件监听"""
        if not self.current_session_id:
            return None
        return self._get_session_file(self.current_session_id, self.current_mode)

    def _atomic_save(self, file_path, history):
        """原子保存：写 .tmp → 备份旧文件为 .bak → replace。
        任何异常都不会损坏现有 .jsonl 文件。
        """
        tmp_path = file_path + ".tmp"
        bak_path = file_path + ".bak"
        try:
            # 1. 先写临时文件
            with open(tmp_path, "w", encoding="utf-8") as f:
                for msg in history:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

            # 2. 原文件存在则备份（旧备份先删除，只保留一份 .bak）
            if os.path.exists(file_path):
                try:
                    if os.path.exists(bak_path):
                        os.remove(bak_path)
                    os.replace(file_path, bak_path)
                except Exception as e:
                    print(f"⚠️ 备份失败（不影响主流程）：{e}")

            # 3. 原子替换
            os.replace(tmp_path, file_path)
            return True
        except Exception as e:
            print(f"保存对话历史失败：{e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False

    # ========== 独立模式读写（不改变实例状态，供故事模式使用） ==========
    def get_active_session_id(self, mode=None):
        """读取指定模式当前会话 ID，不改变 self.current_mode / self.current_session_id"""
        target = mode or self.current_mode
        data = self._read_full_index()
        return data.get(f"current_{target}")

    def get_active_history(self, mode=None):
        """读取指定模式当前会话的历史，不改变实例状态"""
        target = mode or self.current_mode
        sid = self.get_active_session_id(target)
        if not sid:
            return []
        return self._load_history_file(self._get_session_file(sid, target))

    def save_active_history(self, history, mode=None):
        """保存到指定模式当前会话，不改变实例状态。"""
        target = mode or self.current_mode
        sid = self.get_active_session_id(target)
        if not sid:
            return False
        file_path = self._get_session_file(sid, target)
        if not self._atomic_save(file_path, history):
            return False
        # 更新 last_time
        data = self._read_full_index()
        for s in data["sessions"]:
            if s["id"] == sid:
                s["last_time"] = time.time()
                break
        self._save_index(data)
        return True

    def cleanup_empty_sessions(self):
        """删除所有消息数为 0 的空会话（含 .jsonl、.bak、索引记录）。
        返回被删除数量。
        清理后若某模式无剩余会话，current_xxx 置 None（调用方负责重建默认会话）。
        """
        data = self._read_full_index()
        deleted = 0
        keep_sessions = []

        for s in data["sessions"]:
            sid = s["id"]
            mode = s["type"]
            file_path = self._get_session_file(sid, mode)

            # 判断是否为空会话（文件不存在或所有行都是空行 → 空）
            is_empty = True
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                is_empty = False
                                break
                except Exception:
                    is_empty = True  # 读不出视为空

            if is_empty:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    bak_path = file_path + ".bak"
                    if os.path.exists(bak_path):
                        os.remove(bak_path)
                    deleted += 1
                    continue
                except Exception as e:
                    print(f"删除空会话失败：{e}")

            keep_sessions.append(s)

        data["sessions"] = keep_sessions

        # 各模式重新选定当前会话
        for mode in ["realtime", "story"]:
            cur = data.get(f"current_{mode}")
            mode_sessions = [s for s in keep_sessions if s["type"] == mode]
            valid_ids = [s["id"] for s in mode_sessions]
            if not cur or cur not in valid_ids:
                data[f"current_{mode}"] = valid_ids[0] if valid_ids else None

        # 同步实例状态
        if self.current_mode == "realtime":
            self.current_session_id = data.get("current_realtime")
        elif self.current_mode == "story":
            self.current_session_id = data.get("current_story")

        self._save_index(data)
        return deleted

# ===================== 自定义右键菜单类 =====================
class PetRightMenu(QWidget):
    def __init__(self, pet_window):
        super().__init__()
        self.pet = pet_window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Popup
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(120, 180)

        # ========== 样式变量（后续制作器可直接从配置读取） ==========
        self.style_config = {
            "menu_bg": "rgba(255,255,255,0.95)",
            "btn_bg": "rgba(255,255,255,0.9)",
            "btn_hover_bg": "#f0f0f0",
            "text_color": "#000000",
            "border_color": "#dddddd"
        }
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.btn_interact = QPushButton("互动")
        self.btn_chat = QPushButton("对话")
        self.btn_setting = QPushButton("行为设置")
        self.btn_close = QPushButton("关闭菜单")
        self.btn_exit = QPushButton("退出")

        layout.addWidget(self.btn_interact)
        layout.addWidget(self.btn_chat)
        layout.addWidget(self.btn_setting)
        layout.addWidget(self.btn_close)
        layout.addWidget(self.btn_exit)

        # 绑定事件：互动/对话/设置 不关闭菜单；关闭/退出 关闭菜单
        self.btn_interact.clicked.connect(self.open_interact)
        self.btn_chat.clicked.connect(self.on_chat_clicked)
        self.btn_setting.clicked.connect(self.on_setting_clicked)
        self.btn_close.clicked.connect(self.hide)
        self.btn_exit.clicked.connect(self.on_exit_clicked)

    def set_style_config(self, config_dict):
        """从 config 的 ui_style.right_menu 应用样式。"""
        if not config_dict:
            return
        self.style_config.update(config_dict)
        self._update_style()

    def _update_style(self):
        s = self.style_config

        # 容器底：menu_bg 支持 'transparent'
        menu_bg = (s.get('menu_bg') or "transparent").strip().lower()
        bg = "transparent" if menu_bg == "transparent" else _qss_color(menu_bg)
        # PetRightMenu 本身已 WA_TranslucentBackground，这里 bg 只是"如果用户真给了颜色，也允许用户加回去"
        # 但为了保证"完全透明"契约，把容器底彻底透明固定：
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {_qss_color(s['btn_bg'])};
                color: {_qss_color(s['text_color'])};
                border: 1px solid {_qss_color(s['border_color'])};
                border-radius: 4px;
                padding: 8px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {_qss_color(s['btn_hover_bg'])};
            }}
        """)

    def show_at_pet(self):
        """右键菜单默认在角色右侧、底边对齐；右边界不够时翻到左侧。"""
        # ★ 每次右键显示前，从 pet.config 拉最新样式，保证 config 改动立即生效
        try:
            ui = self.pet.config.get("ui_style", {}).get("right_menu", {})
            if ui:
                self.set_style_config(ui)
        except Exception as e:
            print(f"[warn] right_menu 样式刷新失败: {e}")

        pet_rect = self.pet.frameGeometry()
        ideal_x = pet_rect.right() + 5
        ideal_y = pet_rect.bottom() - self.height()

        screen = _screen_of_widget(self.pet)
        geo = screen.availableGeometry()

        # 右侧越界 → 翻到角色左侧
        if ideal_x + self.width() > geo.right():
            ideal_x = pet_rect.left() - self.width() - 5

        rect = _fit_rect_to_screen(
            QRect(ideal_x, ideal_y, self.width(), self.height()), screen
        )
        self.move(rect.left(), rect.top())
        self.show()
        self.raise_()

    def open_interact(self):
        # 打开互动窗口，不关闭右键菜单
        self.pet.show_interact_window()

    def on_chat_clicked(self):
        # AI对话按钮，不关闭菜单
        self.pet.open_chat()
        self.hide()


    def on_setting_clicked(self):
        # 行为设置按钮：打开行为设置窗口并关闭右键菜单
        self.pet.show_behavior_setting()
        self.hide()

    def on_exit_clicked(self):
        self.hide()
        self.pet.start_exit()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.pet.touch_user_activity()

# ===================== 自定义动作按钮（预览图+文字） =====================
class ActionButton(QWidget):
    clicked = pyqtSignal()
    def __init__(self, action_config, parent=None):
        super().__init__(parent)
        self.action_config = action_config
        self.setFixedSize(72, 86)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 预览图区域
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(64, 64)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("border: 1px solid #ddd; border-radius: 4px; background: #fafafa;")
        # 加载预览图
        preview_path = _p(action_config.get("preview_path", ""))
        if os.path.exists(preview_path):
            pix = QPixmap(preview_path).scaled(
                64, 64, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.preview_label.setPixmap(pix)

        # 动作名称
        self.name_label = QLabel(action_config["action_name"])
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-size: 11px; color: #000;")
        self.name_label.setWordWrap(True)

        layout.addWidget(self.preview_label)
        layout.addWidget(self.name_label)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

# ===================== 互动选择窗口类（翻页版） =====================
class InteractWindow(QWidget):
    def __init__(self, pet_window):
        super().__init__()
        self.pet = pet_window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(520, 420)  # 放大窗口尺寸

        # 样式变量（后续制作器可直接从配置读取）
        self.style_config = {
            "window_bg": "rgba(255,255,255,0.95)",
            "btn_bg": "#ffffff",
            "btn_hover_bg": "#f0f0f0",
            "btn_disabled_bg": "#f5f5f5",
            "btn_disabled_color": "#bbbbbb",
            "text_color": "#000000",
            "border_color": "#dddddd",
            "tab_bg": "#f5f5f5",
            "tab_selected_bg": "#ffffff"
        }
        self._update_style()

        # 窗口拖拽变量
        self.drag_offset = QPoint()
        self.is_dragging = False
        self.press_global_pos = QPoint()
        self.DRAG_THRESHOLD = 5

        # 翻页参数
        self.TABS_PER_PAGE = 4       # 每页最多4个分组标签
        self.ACTIONS_PER_PAGE = 8    # 每页最多8个动作（2行×4列）
        self.current_tab_start = 0   # 当前标签页起始索引
        self.current_action_start = 0 # 当前动作页起始索引
        self.current_group_index = 0 # 当前选中的分组索引

        # ========== 主容器 ==========
        container = QWidget()
        container.setObjectName("container")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)

        # ---------- 顶部：标签栏 + 翻页按钮 + 关闭按钮 ----------
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(6)

        # 标签左翻页（最左侧）
        self.btn_prev_tab = QPushButton("◀")
        self.btn_prev_tab.setObjectName("page_btn")
        self.btn_prev_tab.setFixedSize(24, 24)
        self.btn_prev_tab.clicked.connect(self.prev_tab_page)
        top_bar_layout.addWidget(self.btn_prev_tab)

        # 标签容器
        self.tab_container = QWidget()
        self.tab_layout = QHBoxLayout(self.tab_container)
        self.tab_layout.setContentsMargins(0, 0, 0, 0)
        self.tab_layout.setSpacing(2)
        top_bar_layout.addWidget(self.tab_container, 1)

        # 标签右翻页（紧贴标签区域右侧）
        self.btn_next_tab = QPushButton("▶")
        self.btn_next_tab.setObjectName("page_btn")
        self.btn_next_tab.setFixedSize(24, 24)
        self.btn_next_tab.clicked.connect(self.next_tab_page)
        top_bar_layout.addWidget(self.btn_next_tab)

        # 关闭按钮（最右侧）
        self.btn_close = QPushButton("×")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.btn_close.clicked.connect(self.hide)
        top_bar_layout.addWidget(self.btn_close)

        main_layout.addWidget(top_bar)

        # ---------- 中间：动作网格区域 ----------
        self.action_container = QWidget()
        self.action_grid = QGridLayout(self.action_container)
        self.action_grid.setContentsMargins(0, 0, 0, 0)
        self.action_grid.setSpacing(10)
        main_layout.addWidget(self.action_container, 1)

        # ---------- 底部：动作翻页栏 + 页码圆点 ----------
        bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        self.btn_prev_action = QPushButton("◀")
        self.btn_prev_action.setObjectName("page_btn")
        self.btn_prev_action.setFixedSize(28, 24)
        self.btn_prev_action.clicked.connect(self.prev_action_page)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_prev_action)

        # 页码圆点容器
        self.page_dots_container = QWidget()
        self.dots_layout = QHBoxLayout(self.page_dots_container)
        self.dots_layout.setContentsMargins(0, 0, 0, 0)
        self.dots_layout.setSpacing(6)
        bottom_layout.addWidget(self.page_dots_container)

        self.btn_next_action = QPushButton("▶")
        self.btn_next_action.setObjectName("page_btn")
        self.btn_next_action.setFixedSize(28, 24)
        self.btn_next_action.clicked.connect(self.next_action_page)
        bottom_layout.addWidget(self.btn_next_action)
        bottom_layout.addStretch()

        main_layout.addWidget(bottom_bar)

        # 外层布局
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

        # 初始化刷新
        self.refresh_tabs()
        self.refresh_actions()

    def set_style_config(self, config_dict):
        """从 config 的 ui_style.interact_window 应用样式。"""
        if not config_dict:
            return
        self.style_config.update(config_dict)
        self._update_style()

    def _update_style(self):
        s = self.style_config

        def c(k):
            return _qss_color(s.get(k, "transparent"))

        self.setStyleSheet(f"""
            QWidget#container {{
                background-color: {c('window_bg')};
                border: 1px solid {c('border_color')};
                border-radius: 8px;
                color: {c('text_color')};
            }}
            QPushButton {{
                border: 1px solid {c('border_color')};
                border-radius: 4px;
                background: {c('btn_bg')};
                color: {c('text_color')};
                font-size: 12px;
            }}
            QPushButton:hover {{ background: {c('btn_hover_bg')}; }}
            QPushButton:disabled {{
                background: {c('btn_disabled_bg')};
                color: {c('btn_disabled_color')};
                border-color: #eee;
            }}
            /* ★ 翻页按钮禁用时：背景完全透明，视觉上融入 container 的 window_bg */
            QPushButton#page_btn:disabled {{
                background: transparent;
                color: {c('btn_disabled_color')};
                border: 1px solid transparent;
            }}
            QPushButton#tab_btn {{
                padding: 6px 10px;
                background: {c('tab_bg')};
                border-bottom: none;
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
            }}
            QPushButton#tab_btn:checked {{
                background: {c('tab_selected_bg')};
                font-weight: bold;
            }}
        """)

    # ===================== 标签栏刷新与翻页 =====================
    def refresh_tabs(self):
        # 清空原有标签
        while self.tab_layout.count() > 0:
            item = self.tab_layout.takeAt(0)
            item.widget().deleteLater()

        groups = self.pet.config["interact"]["groups"]
        end = min(self.current_tab_start + self.TABS_PER_PAGE, len(groups))
        show_groups = groups[self.current_tab_start:end]

        for i, group in enumerate(show_groups):
            global_idx = self.current_tab_start + i
            btn = QPushButton(group["group_name"])
            btn.setObjectName("tab_btn")
            btn.setCheckable(True)
            if global_idx == self.current_group_index:
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, idx=global_idx: self.switch_group(idx))
            self.tab_layout.addWidget(btn)

        # 更新翻页按钮状态：边界置灰
        self.btn_prev_tab.setEnabled(self.current_tab_start > 0)
        self.btn_next_tab.setEnabled(end < len(groups))

    def prev_tab_page(self):
        if self.current_tab_start > 0:
            self.current_tab_start -= self.TABS_PER_PAGE
            self.refresh_tabs()

    def next_tab_page(self):
        total = len(self.pet.config["interact"]["groups"])
        if self.current_tab_start + self.TABS_PER_PAGE < total:
            self.current_tab_start += self.TABS_PER_PAGE
            self.refresh_tabs()

    def switch_group(self, group_index):
        self.current_group_index = group_index
        self.current_action_start = 0  # 切换分组重置动作页到第1页
        self.refresh_tabs()
        self.refresh_actions()

    # ===================== 动作网格刷新与翻页 =====================
    def refresh_actions(self):
        # 清空原有按钮
        while self.action_grid.count() > 0:
            item = self.action_grid.takeAt(0)
            item.widget().deleteLater()

        groups = self.pet.config["interact"]["groups"]
        if not groups:                    # 空列表保护
            self.refresh_page_dots()
            self.btn_prev_action.setEnabled(False)
            self.btn_next_action.setEnabled(False)
            return
        if self.current_group_index >= len(groups):
            self.current_group_index = 0
            self.current_action_start = 0
        actions = groups[self.current_group_index]["actions"]
        end = min(self.current_action_start + self.ACTIONS_PER_PAGE, len(actions))
        show_actions = actions[self.current_action_start:end]

        # 2行4列网格排布
        for i, action in enumerate(show_actions):
            row = i // 4
            col = i % 4
            btn = ActionButton(action)
            btn.clicked.connect(lambda a=action: self.on_action_click(a))
            self.action_grid.addWidget(btn, row, col)

        # 剩余位置填空白占位
        for i in range(len(show_actions), self.ACTIONS_PER_PAGE):
            row = i // 4
            col = i % 4
            spacer = QWidget()
            self.action_grid.addWidget(spacer, row, col)

        # 更新页码圆点与翻页按钮状态
        self.refresh_page_dots()
        self.btn_prev_action.setEnabled(self.current_action_start > 0)
        self.btn_next_action.setEnabled(end < len(actions))

    def refresh_page_dots(self):
        # 清空原有圆点
        while self.dots_layout.count() > 0:
            item = self.dots_layout.takeAt(0)
            item.widget().deleteLater()

        groups = self.pet.config["interact"]["groups"]
        if not groups:                      # 空列表保护
            return
        if self.current_group_index >= len(groups):
            self.current_group_index = 0
            self.current_action_start = 0
        actions = groups[self.current_group_index]["actions"]
        total_pages = max(1, (len(actions) + self.ACTIONS_PER_PAGE - 1) // self.ACTIONS_PER_PAGE)
        current_page = self.current_action_start // self.ACTIONS_PER_PAGE

        for i in range(total_pages):
            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if i == current_page:
                dot.setStyleSheet("color: #000; font-size: 10px;")
            else:
                dot.setStyleSheet("color: #bbb; font-size: 10px;")
            self.dots_layout.addWidget(dot)

    def prev_action_page(self):
        if self.current_action_start > 0:
            groups = self.pet.config["interact"]["groups"]
            if not groups:                      # 空列表保护（热重载时）
                return
            self.current_action_start -= self.ACTIONS_PER_PAGE
            self.refresh_actions()

    def next_action_page(self):
        groups = self.pet.config["interact"]["groups"]
        if not groups:                          # 空列表保护（热重载时）
            return
        total = len(groups[self.current_group_index]["actions"])
        if self.current_action_start + self.ACTIONS_PER_PAGE < total:
            self.current_action_start += self.ACTIONS_PER_PAGE
            self.refresh_actions()

    def on_action_click(self, action_config):
        self.pet.play_interact(action_config)

    def show_at_pet(self):
        """互动窗口默认在角色正上方居中；上方越界翻到下方；最后夹紧。"""
        # ★ 每次显示前刷新样式
        try:
            ui = self.pet.config.get("ui_style", {}).get("interact_window", {})
            if ui:
                self.set_style_config(ui)
        except Exception as e:
            print(f"[warn] interact_window 样式刷新失败: {e}")

        pet_rect = self.pet.frameGeometry()
        ideal_x = pet_rect.center().x() - self.width() // 2
        ideal_y = pet_rect.top() - self.height() - 10

        screen = _screen_of_widget(self.pet)
        geo = screen.availableGeometry()

        # 上方越界 → 翻到角色下方
        if ideal_y < geo.top():
            ideal_y = pet_rect.bottom() + 10

        rect = _fit_rect_to_screen(
            QRect(ideal_x, ideal_y, self.width(), self.height()), screen
        )
        self.move(rect.left(), rect.top())
        self.show()
        self.raise_()
        self.refresh_tabs()
        self.refresh_actions()

    # ===================== 窗口拖拽逻辑 =====================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.press_global_pos = event.globalPosition().toPoint()
            self.is_dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            dist = (event.globalPosition().toPoint() - self.press_global_pos).manhattanLength()
            if dist > self.DRAG_THRESHOLD and not self.is_dragging:
                self.is_dragging = True
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            event.accept()

# ===================== 提示词展开编辑对话框 =====================
class PromptEditorDialog(QDialog):
    """展开式提示词编辑器。实时双向同步到源文本框。
    点「确定」或关闭窗口时，编辑内容均已写回源文本框。
    """
    def __init__(self, parent, title, source_edit):
        super().__init__(parent)
        self.source_edit = source_edit
        self.setWindowTitle(title)
        self.resize(800, 600)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(self._get_source_text())
        self.editor.setFont(source_edit.font())
        layout.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_ok = QPushButton("确定")
        self.btn_ok.setMinimumWidth(120)
        self.btn_ok.setFixedHeight(32)
        self.btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_ok)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        # 实时同步：dialog 编辑 → 源文本框
        self.editor.textChanged.connect(self._sync_to_source)

    def _get_source_text(self):
        """兼容 QPlainTextEdit 与 QLineEdit 两种源控件。"""
        if hasattr(self.source_edit, "toPlainText"):
            return self.source_edit.toPlainText()
        if hasattr(self.source_edit, "text"):
            return self.source_edit.text()
        return ""

    def _set_source_text(self, text):
        if hasattr(self.source_edit, "setPlainText"):
            self.source_edit.setPlainText(text)
        elif hasattr(self.source_edit, "setText"):
            self.source_edit.setText(text)

    def _sync_to_source(self):
        text = self.editor.toPlainText()
        if self._get_source_text() != text:
            self._set_source_text(text)

# ===================== 单条消息气泡（支持右键删除/编辑） =====================
class MessageBubble(QWidget):
    """一条消息。user 右对齐蓝底，assistant 左对齐灰底。
    右键菜单：编辑 / 删除。
    编辑态：内嵌 QPlainTextEdit，下方有确认/取消按钮。
    """
    delete_requested = pyqtSignal(int)          # 携带该消息在 chat_history 中的索引
    edit_requested = pyqtSignal(int, str)       # 携带索引 + 新内容

    def __init__(self, role, content, time_str, index, bubble_style=None, parent=None):
        super().__init__(parent)
        self.role = role
        self.index = index
        self._content = content
        self._time_str = time_str
        self._bubble_style = bubble_style or {}
        self._editing = False

        # 解析样式
        s = self._bubble_style
        self._user_bg = s.get("user_bg", "#d0e8ff")
        self._assistant_bg = s.get("assistant_bg", "#f0f0f0")
        self._radius = s.get("border_radius", 8)
        self._max_width = s.get("max_width", 520)
        self._font_size = s.get("font_size", 14)
        self._time_color = s.get("time_color", "#999999")
        self._time_font_size = s.get("time_font_size", 11)
        # 文本色：正文、编辑器、确认/取消按钮共用
        self._text_color = s.get("text_color", "#000000")
        # 编辑态按钮/编辑器背景色（避免系统主题污染）
        self._edit_btn_bg = s.get("edit_btn_bg", "#ffffff")
        self._edit_btn_border = s.get("edit_btn_border", "#cccccc")

        self._build_ui()

    # ---------- 构建 ----------
    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 2, 4, 2)
        outer.setSpacing(0)

        self.bubble_widget = QWidget()
        self.bubble_widget.setMaximumWidth(self._max_width)
        self.b_layout = QVBoxLayout(self.bubble_widget)
        self.b_layout.setContentsMargins(12, 8, 12, 6)
        self.b_layout.setSpacing(2)

        # 显示态
        self.content_label = QLabel(self._content)
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.content_label.setStyleSheet(
            f"font-size: {self._font_size}px; color: {self._text_color}; background: transparent;"
        )
        self.content_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.content_label.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.content_label.mapToGlobal(pos))
        )

        # 编辑态（初始隐藏）
        self.edit_editor = QPlainTextEdit()
        self.edit_editor.setPlainText(self._content)
        self.edit_editor.setMinimumHeight(70)
        self.edit_editor.setMaximumHeight(260)
        self.edit_editor.setStyleSheet(
            f"font-size: {self._font_size}px; color: {self._text_color};"
            f"background-color: {self._edit_btn_bg};"
            f"border: 1px solid {self._edit_btn_border}; border-radius: 4px;"
            f"padding: 4px;"
        )
        self.edit_editor.hide()

        # 编辑确认/取消按钮（初始隐藏）
        self.edit_btn_row = QWidget()
        btn_layout = QHBoxLayout(self.edit_btn_row)
        btn_layout.setContentsMargins(0, 2, 0, 0)
        btn_layout.setSpacing(6)
        btn_layout.addStretch(1)
        self.btn_confirm_edit = QPushButton("确认")
        self.btn_confirm_edit.setFixedSize(58, 26)
        self.btn_confirm_edit.clicked.connect(self._on_confirm_edit)
        self.btn_cancel_edit = QPushButton("取消")
        self.btn_cancel_edit.setFixedSize(58, 26)
        self.btn_cancel_edit.clicked.connect(self._exit_edit_mode)
        # 显式设置按钮样式，避免被系统深色主题污染导致文字看不清
        _btn_style = (
            f"QPushButton {{"
            f"  font-size: {max(11, self._font_size - 2)}px;"
            f"  color: {self._text_color};"
            f"  background-color: {self._edit_btn_bg};"
            f"  border: 1px solid {self._edit_btn_border};"
            f"  border-radius: 4px;"
            f"  padding: 0px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: #f0f0f0;"
            f"}}"
            f"QPushButton:pressed {{"
            f"  background-color: #e0e0e0;"
            f"}}"
        )
        self.btn_confirm_edit.setStyleSheet(_btn_style)
        self.btn_cancel_edit.setStyleSheet(_btn_style)
        btn_layout.addWidget(self.btn_confirm_edit)
        btn_layout.addWidget(self.btn_cancel_edit)
        self.edit_btn_row.hide()

        # 时间戳
        self.time_label = QLabel(self._time_str)
        self.time_label.setStyleSheet(
            f"font-size: {self._time_font_size}px; color: {self._time_color}; background: transparent;"
        )
        self.time_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.time_label.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.time_label.mapToGlobal(pos))
        )

        self.b_layout.addWidget(self.content_label)
        self.b_layout.addWidget(self.edit_editor)
        self.b_layout.addWidget(self.edit_btn_row)
        self.b_layout.addWidget(self.time_label)

        bg = self._user_bg if self.role == "user" else self._assistant_bg
        self.bubble_widget.setStyleSheet(
            f"background-color: {bg}; border-radius: {self._radius}px;"
        )

        # 气泡容器背景空白区域也能右键
        self.bubble_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.bubble_widget.customContextMenuRequested.connect(
            lambda pos: self._show_menu(self.bubble_widget.mapToGlobal(pos))
        )

        if self.role == "user":
            outer.addStretch(1)
            outer.addWidget(self.bubble_widget)
        else:
            outer.addWidget(self.bubble_widget)
            outer.addStretch(1)

    # ---------- 右键菜单 ----------
    def _show_menu(self, global_pos):
        if self._editing:
            return
        menu = QMenu(self)
        act_edit = menu.addAction("编辑此消息")
        act_edit.triggered.connect(self._enter_edit_mode)
        act_del = menu.addAction("删除此消息")
        act_del.triggered.connect(lambda: self.delete_requested.emit(self.index))
        menu.exec(global_pos)

    def contextMenuEvent(self, event):
        # 兜底：整个 widget 的空白处右键
        self._show_menu(event.globalPos())

    # ---------- 编辑态切换 ----------
    def _enter_edit_mode(self):
        if self._editing:
            return
        self._editing = True
        self.edit_editor.setPlainText(self._content)
        self.content_label.hide()
        self.edit_editor.show()
        self.edit_btn_row.show()
        self.edit_editor.setFocus()
        # 光标放到末尾
        cursor = self.edit_editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.edit_editor.setTextCursor(cursor)

    def _exit_edit_mode(self):
        if not self._editing:
            return
        self._editing = False
        self.edit_editor.hide()
        self.content_label.show()
        self.edit_btn_row.hide()

    def _on_confirm_edit(self):
        new_text = self.edit_editor.toPlainText()
        if not new_text.strip():
            QMessageBox.warning(self, "内容为空", "消息内容不能为空，请输入或点取消。")
            return
        self._content = new_text
        self.content_label.setText(new_text)
        self._exit_edit_mode()
        self.edit_requested.emit(self.index, new_text)

# ===================== 高级对话窗口（5.6.1：骨架 + 设置 Tab） =====================
class AdvancedChatWindow(QWidget):
    """高级对话窗口：三 Tab 结构。
    5.6.1 阶段只完整实现设置 Tab，实时对话/故事模式为占位。
    """

    def __init__(self, pet_window):
        super().__init__()
        self.pet = pet_window
        self.setWindowTitle("高级对话")
        self.resize(800, 700)
        self.setMinimumSize(640, 480)
        # 隐藏左上角系统菜单图标（保留标题栏、最小化、最大化、关闭）
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.CustomizeWindowHint
        )
        # 制作器可注入的样式字典（含 message_bubble 子节）
        self.style_config = {}
        self._bubble_style = {}
        # 流式显示状态
        self._streaming_active = False
        self._streaming_mode = None
        self._streaming_content = "..."
        self._streaming_bubble = None
        self._build_ui()

    # ---------- 主界面 ----------
    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(8)

        # 三 Tab
        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)
        self.tabs.addTab(self._build_realtime_tab(), "实时对话")
        self.tabs.addTab(self._build_story_tab(), "故事模式")
        self.tabs.addTab(self._build_settings_tab(), "设置")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # 底部按钮栏
        bottom = QHBoxLayout()
        self.btn_save = QPushButton("保存设置")
        self.btn_save.setFixedHeight(32)
        self.btn_save.setMinimumWidth(120)
        self.btn_save.clicked.connect(self._on_save_clicked)

        # token 估算 label（左端，与按钮同高，颜色跟随按钮）
        self.token_label = QLabel("")
        self.token_label.setStyleSheet("font-size: 12px;")
        self.token_label.setMinimumHeight(32)
        self.token_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._sync_token_label_color()

        bottom.addWidget(self.token_label, 1)
        bottom.addWidget(self.btn_save)
        main.addLayout(bottom)

    # ---------- 实时对话 Tab ----------
    def _build_realtime_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ===== 顶部工具栏 =====
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.combo_sessions = QComboBox()
        self.combo_sessions.setMinimumWidth(240)
        self.combo_sessions.currentIndexChanged.connect(self._on_switch_session)
        toolbar.addWidget(self.combo_sessions, 1)
        self.combo_sessions.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.combo_sessions.customContextMenuRequested.connect(self._on_rt_combo_context_menu)

        self.btn_new_session = QPushButton("新建")
        self.btn_new_session.setFixedHeight(28)
        self.btn_new_session.setMinimumWidth(72)
        self.btn_new_session.clicked.connect(self._on_new_session)
        toolbar.addWidget(self.btn_new_session)

        self.btn_export = QPushButton("导出")
        self.btn_export.setFixedHeight(28)
        self.btn_export.setMinimumWidth(72)
        self.btn_export.clicked.connect(self._on_export)
        toolbar.addWidget(self.btn_export)

        self.btn_delete_session = QPushButton("删除会话")
        self.btn_delete_session.setFixedHeight(28)
        self.btn_delete_session.setMinimumWidth(96)
        self.btn_delete_session.clicked.connect(self._on_delete_session)
        toolbar.addWidget(self.btn_delete_session)

        self.btn_clean_empty = QPushButton("清理空对话")
        self.btn_clean_empty.setFixedHeight(28)
        self.btn_clean_empty.setMinimumWidth(100)
        self.btn_clean_empty.setToolTip("删除所有没有消息的空会话（实时+故事）")
        self.btn_clean_empty.clicked.connect(self._on_clean_empty_sessions)
        toolbar.addWidget(self.btn_clean_empty)

        layout.addLayout(toolbar)

        # ===== 中间消息滚动区 =====
        self.rt_scroll = QScrollArea()
        self.rt_scroll.setWidgetResizable(True)
        rt_container = QWidget()
        self.rt_messages_layout = QVBoxLayout(rt_container)
        self.rt_messages_layout.setContentsMargins(4, 4, 4, 4)
        self.rt_messages_layout.setSpacing(4)
        self.rt_messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.rt_scroll.setWidget(rt_container)
        layout.addWidget(self.rt_scroll, 1)

        # ===== 错误提示条（默认隐藏，失败时显示） =====
        self.rt_error_label = QLabel("")
        self.rt_error_label.setWordWrap(True)
        self.rt_error_label.setStyleSheet(
            "color: #d04040; font-size: 12px; background: transparent; padding: 4px 8px;"
        )
        self.rt_error_label.hide()
        layout.addWidget(self.rt_error_label)

        # ===== 底部输入区 =====
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        # 输入框（先建，方便下方按钮引用）
        self.rt_input = QLineEdit()
        self.rt_input.setPlaceholderText("输入文字，回车或单击发送")
        self.rt_input.returnPressed.connect(self._on_rt_send)

        # 左侧 ↗ 展开按钮（独立占位，不遮挡文字）
        self.rt_expand_btn = QPushButton("↗")
        self.rt_expand_btn.setFixedSize(32, 32)
        self.rt_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rt_expand_btn.setToolTip("在独立窗口中编辑当前输入")
        self.rt_expand_btn.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.rt_expand_btn.clicked.connect(
            lambda: self._open_prompt_editor("实时对话输入", self.rt_input)
        )
        input_row.addWidget(self.rt_expand_btn)

        input_row.addWidget(self.rt_input, 1)

        self.rt_btn_send = QPushButton("发送")
        self.rt_btn_send.setFixedHeight(32)
        self.rt_btn_send.setMinimumWidth(72)
        self.rt_btn_send.clicked.connect(self._on_rt_send)
        input_row.addWidget(self.rt_btn_send)

        layout.addLayout(input_row)
        return page

    # ---------- 故事模式 Tab ----------
    def _build_story_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # ===== 顶部工具栏 =====
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.story_combo_sessions = QComboBox()
        self.story_combo_sessions.setMinimumWidth(240)
        self.story_combo_sessions.currentIndexChanged.connect(self._on_story_switch_session)
        toolbar.addWidget(self.story_combo_sessions, 1)
        self.story_combo_sessions.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.story_combo_sessions.customContextMenuRequested.connect(self._on_story_combo_context_menu)

        self.btn_story_new_session = QPushButton("新建")
        self.btn_story_new_session.setFixedHeight(28)
        self.btn_story_new_session.clicked.connect(self._on_story_new_session)
        toolbar.addWidget(self.btn_story_new_session)

        self.btn_story_export = QPushButton("导出")
        self.btn_story_export.setFixedHeight(28)
        self.btn_story_export.clicked.connect(self._on_story_export)
        toolbar.addWidget(self.btn_story_export)

        self.btn_story_delete_session = QPushButton("删除会话")
        self.btn_story_delete_session.setFixedHeight(28)
        self.btn_story_delete_session.clicked.connect(self._on_story_delete_session)
        toolbar.addWidget(self.btn_story_delete_session)

        self.btn_story_clean_empty = QPushButton("清理空对话")
        self.btn_story_clean_empty.setFixedHeight(28)
        self.btn_story_clean_empty.setToolTip("删除所有没有消息的空会话（实时+故事）")
        self.btn_story_clean_empty.clicked.connect(self._on_clean_empty_sessions)
        toolbar.addWidget(self.btn_story_clean_empty)

        layout.addLayout(toolbar)

        # ===== 中间消息滚动区 =====
        self.story_scroll = QScrollArea()
        self.story_scroll.setWidgetResizable(True)
        story_container = QWidget()
        self.story_messages_layout = QVBoxLayout(story_container)
        self.story_messages_layout.setContentsMargins(4, 4, 4, 4)
        self.story_messages_layout.setSpacing(4)
        self.story_messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.story_scroll.setWidget(story_container)
        layout.addWidget(self.story_scroll, 1)

        # ===== 错误提示条（默认隐藏） =====
        self.story_error_label = QLabel("")
        self.story_error_label.setWordWrap(True)
        self.story_error_label.setStyleSheet(
            "color: #d04040; font-size: 12px; background: transparent; padding: 4px 8px;"
        )
        self.story_error_label.hide()
        layout.addWidget(self.story_error_label)

        # ===== 底部输入区 =====
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.story_input = QLineEdit()
        self.story_input.setPlaceholderText("输入文字，回车或单击发送")
        self.story_input.returnPressed.connect(self._on_story_send)

        # 左侧 ↗ 展开按钮
        self.story_expand_btn = QPushButton("↗")
        self.story_expand_btn.setFixedSize(32, 32)
        self.story_expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.story_expand_btn.setToolTip("在独立窗口中编辑当前输入")
        self.story_expand_btn.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.story_expand_btn.clicked.connect(
            lambda: self._open_prompt_editor("故事模式输入", self.story_input)
        )
        input_row.addWidget(self.story_expand_btn)

        input_row.addWidget(self.story_input, 1)

        self.story_btn_send = QPushButton("发送")
        self.story_btn_send.setFixedHeight(32)
        self.story_btn_send.setMinimumWidth(72)
        self.story_btn_send.clicked.connect(self._on_story_send)
        input_row.addWidget(self.story_btn_send)

        layout.addLayout(input_row)
        return page

    def set_style_config(self, config_dict):
        """制作器注入样式。config_dict 支持嵌套 message_bubble 子节。"""
        if not config_dict:
            return
        self.style_config.update(config_dict)
        if "message_bubble" in config_dict:
            self._bubble_style = config_dict["message_bubble"]
            if hasattr(self, "rt_messages_layout") and self.isVisible():
                self._refresh_realtime_messages(scroll_to_bottom=False)
            if hasattr(self, "story_messages_layout") and self.isVisible():
                self._refresh_story_messages(scroll_to_bottom=False)

    def _make_prompt_row(self, label_name, textbox):
        """构造一行：[↗ 展开按钮] [提示词文本框]"""
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        btn = QPushButton("↗")
        btn.setFixedSize(26, 26)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(f"在独立窗口中编辑「{label_name}」")
        btn.setStyleSheet("font-size: 14px; font-weight: bold;")
        btn.clicked.connect(lambda: self._open_prompt_editor(label_name, textbox))

        h.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop)
        h.addWidget(textbox, 1)
        return row

    def _open_prompt_editor(self, label_name, textbox):
        dlg = PromptEditorDialog(self, f"编辑 - {label_name}", textbox)
        dlg.exec()

    # ---------- 设置 Tab ----------
    def _build_settings_tab(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = QWidget()
        scroll.setWidget(content)

        outer = QVBoxLayout(content)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(16)

        # ===== 分组 1：API 配置 =====
        g_api = QGroupBox("API 配置")
        form_api = QFormLayout(g_api)
        form_api.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.edit_base_url = QLineEdit()
        form_api.addRow("Base URL:", self.edit_base_url)

        self.edit_api_key = QLineEdit()
        self.edit_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_api.addRow("API Key:", self.edit_api_key)

        self.edit_model_name = QLineEdit()
        form_api.addRow("模型名:", self.edit_model_name)

        outer.addWidget(g_api)

        # ===== 分组 2：模型参数 =====
        g_model = QGroupBox("模型参数")
        form_model = QFormLayout(g_model)
        form_model.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Temperature（0.0 ~ 2.0，步长 0.1）
        self.slider_temperature = QSlider(Qt.Orientation.Horizontal)
        self.slider_temperature.setRange(0, 20)
        self.spin_temperature = QDoubleSpinBox()
        self.spin_temperature.setRange(0.0, 2.0)
        self.spin_temperature.setSingleStep(0.1)
        self.spin_temperature.setDecimals(2)
        self.slider_temperature.valueChanged.connect(
            lambda v: self.spin_temperature.setValue(v / 10.0)
        )
        self.spin_temperature.valueChanged.connect(
            lambda v: self.slider_temperature.setValue(int(round(v * 10)))
        )
        row_t = QHBoxLayout()
        row_t.addWidget(self.slider_temperature, 1)
        row_t.addWidget(self.spin_temperature)
        form_model.addRow("Temperature:", row_t)

        # Top P（0.0 ~ 1.0，步长 0.05）
        self.slider_top_p = QSlider(Qt.Orientation.Horizontal)
        self.slider_top_p.setRange(0, 100)
        self.spin_top_p = QDoubleSpinBox()
        self.spin_top_p.setRange(0.0, 1.0)
        self.spin_top_p.setSingleStep(0.05)
        self.spin_top_p.setDecimals(2)
        self.slider_top_p.valueChanged.connect(
            lambda v: self.spin_top_p.setValue(v / 100.0)
        )
        self.spin_top_p.valueChanged.connect(
            lambda v: self.slider_top_p.setValue(int(round(v * 100)))
        )
        row_p = QHBoxLayout()
        row_p.addWidget(self.slider_top_p, 1)
        row_p.addWidget(self.spin_top_p)
        form_model.addRow("Top P:", row_p)

        # Frequency Penalty（-2.0 ~ 2.0，步长 0.1）
        self.slider_freq = QSlider(Qt.Orientation.Horizontal)
        self.slider_freq.setRange(-20, 20)
        self.spin_freq = QDoubleSpinBox()
        self.spin_freq.setRange(-2.0, 2.0)
        self.spin_freq.setSingleStep(0.1)
        self.spin_freq.setDecimals(2)
        self.slider_freq.valueChanged.connect(
            lambda v: self.spin_freq.setValue(v / 10.0)
        )
        self.spin_freq.valueChanged.connect(
            lambda v: self.slider_freq.setValue(int(round(v * 10)))
        )
        row_f = QHBoxLayout()
        row_f.addWidget(self.slider_freq, 1)
        row_f.addWidget(self.spin_freq)
        form_model.addRow("Frequency Penalty:", row_f)

        # Presence Penalty（-2.0 ~ 2.0，步长 0.1）
        self.slider_pres = QSlider(Qt.Orientation.Horizontal)
        self.slider_pres.setRange(-20, 20)
        self.spin_pres = QDoubleSpinBox()
        self.spin_pres.setRange(-2.0, 2.0)
        self.spin_pres.setSingleStep(0.1)
        self.spin_pres.setDecimals(2)
        self.slider_pres.valueChanged.connect(
            lambda v: self.spin_pres.setValue(v / 10.0)
        )
        self.spin_pres.valueChanged.connect(
            lambda v: self.slider_pres.setValue(int(round(v * 10)))
        )
        row_p2 = QHBoxLayout()
        row_p2.addWidget(self.slider_pres, 1)
        row_p2.addWidget(self.spin_pres)
        form_model.addRow("Presence Penalty:", row_p2)

        # Max Tokens
        self.spin_max_tokens = QSpinBox()
        self.spin_max_tokens.setRange(1, 65536)
        self.spin_max_tokens.setSingleStep(100)
        form_model.addRow("Max Tokens:", self.spin_max_tokens)

        # 故事模式专用的 Max Tokens
        self.spin_story_max_tokens = QSpinBox()
        self.spin_story_max_tokens.setRange(1, 65536)
        self.spin_story_max_tokens.setSingleStep(100)
        self.spin_story_max_tokens.setToolTip("故事模式专用的输出上限，不受实时对话影响")
        form_model.addRow("故事模式 Max Tokens:", self.spin_story_max_tokens)

        # 上下文最大轮数
        self.spin_max_rounds = QSpinBox()
        self.spin_max_rounds.setRange(1, 200)
        self.spin_max_rounds.setSingleStep(1)
        form_model.addRow("上下文最大轮数:", self.spin_max_rounds)

        # 思考模式
        self.chk_thinking = QCheckBox("启用思考模式（部分模型支持）")
        form_model.addRow(self.chk_thinking)

        outer.addWidget(g_model)

        # ===== 分组 3：角色与身份 =====
        g_id = QGroupBox("角色与身份")
        form_id = QFormLayout(g_id)
        form_id.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.edit_char_name = QLineEdit()
        form_id.addRow("角色名 ({{char}}):", self.edit_char_name)

        self.edit_user_name = QLineEdit()
        form_id.addRow("用户名 ({{user}}):", self.edit_user_name)

        outer.addWidget(g_id)

        # ===== 分组 4：系统提示词 =====
        g_prompt = QGroupBox("系统提示词")
        form_prompt = QFormLayout(g_prompt)
        form_prompt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.edit_global_prompt = QPlainTextEdit()
        self.edit_global_prompt.setMinimumHeight(70)
        form_prompt.addRow("全局提示词:", self._make_prompt_row("全局提示词", self.edit_global_prompt))

        self.edit_character_card = QPlainTextEdit()
        self.edit_character_card.setMinimumHeight(90)
        form_prompt.addRow("角色设定:", self._make_prompt_row("角色设定", self.edit_character_card))

        self.edit_user_card = QPlainTextEdit()
        self.edit_user_card.setMinimumHeight(70)
        form_prompt.addRow("用户身份卡:", self._make_prompt_row("用户身份卡", self.edit_user_card))

        self.edit_realtime_prompt = QPlainTextEdit()
        self.edit_realtime_prompt.setMinimumHeight(70)
        form_prompt.addRow("实时对话提示词:", self._make_prompt_row("实时对话提示词", self.edit_realtime_prompt))

        self.edit_story_prompt = QPlainTextEdit()
        self.edit_story_prompt.setMinimumHeight(70)
        form_prompt.addRow("故事模式提示词:", self._make_prompt_row("故事模式提示词", self.edit_story_prompt))

        outer.addWidget(g_prompt)

        # ===== 分组 5：异常兜底 =====
        g_err = QGroupBox("异常提示")
        form_err = QFormLayout(g_err)
        form_err.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.edit_error_tip = QLineEdit()
        form_err.addRow("角色报错语:", self.edit_error_tip)

        outer.addWidget(g_err)

        # ===== 分组 6：高级对话显示 =====
        g_display = QGroupBox("高级对话显示")
        form_display = QFormLayout(g_display)
        form_display.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.spin_bubble_font_size = QSpinBox()
        self.spin_bubble_font_size.setRange(10, 24)
        self.spin_bubble_font_size.setSingleStep(1)
        self.spin_bubble_font_size.setSuffix(" px")
        self.spin_bubble_font_size.valueChanged.connect(self._on_bubble_font_size_changed)
        form_display.addRow("消息气泡字体大小:", self.spin_bubble_font_size)

        outer.addWidget(g_display)

        outer.addStretch(1)
        return scroll

    # ---------- 从 config 填充控件 ----------
    def _load_from_config(self):
        cfg = self.pet.config["ai_system"]
        api = cfg["api_config"]
        mp = cfg["model_params"]
        pc = cfg["prompt_config"]

        # API
        self.edit_base_url.setText(api.get("base_url", ""))
        self.edit_api_key.setText(api.get("api_key", ""))
        self.edit_model_name.setText(api.get("model_name", ""))

        # 模型参数（setValue 会自动联动滑块）
        self.spin_temperature.setValue(float(mp.get("temperature", 1.0)))
        self.spin_top_p.setValue(float(mp.get("top_p", 1.0)))
        self.spin_freq.setValue(float(mp.get("frequency_penalty", 0.0)))
        self.spin_pres.setValue(float(mp.get("presence_penalty", 0.0)))
        self.spin_max_tokens.setValue(int(mp.get("max_tokens", 1000)))
        self.spin_story_max_tokens.setValue(int(mp.get("story_max_tokens", 4000)))
        self.spin_max_rounds.setValue(int(mp.get("context_max_rounds", 20)))
        self.chk_thinking.setChecked(bool(mp.get("enable_thinking", False)))

        # 身份
        self.edit_char_name.setText(pc.get("char_name", ""))
        self.edit_user_name.setText(pc.get("user_name", ""))

        # 提示词
        self.edit_global_prompt.setPlainText(pc.get("global_prompt", ""))
        self.edit_character_card.setPlainText(pc.get("character_card", ""))
        self.edit_user_card.setPlainText(pc.get("user_card", ""))
        self.edit_realtime_prompt.setPlainText(pc.get("realtime_prompt", ""))
        self.edit_story_prompt.setPlainText(pc.get("story_prompt", ""))

        # 报错
        self.edit_error_tip.setText(pc.get("error_tip", ""))

        # 高级对话显示
        ui_style = self.pet.config.get("ui_style", {})
        adv = ui_style.get("advanced_window", {}).get("message_bubble", {})
        self.spin_bubble_font_size.setValue(int(adv.get("font_size", 14)))
        self._update_token_label()

    # ---------- 从控件收集到 config ----------
    def _save_to_config(self):
        cfg = self.pet.config["ai_system"]

        cfg["api_config"]["base_url"] = self.edit_base_url.text().strip()
        cfg["api_config"]["api_key"] = self.edit_api_key.text().strip()
        cfg["api_config"]["model_name"] = self.edit_model_name.text().strip()

        cfg["model_params"]["temperature"] = self.spin_temperature.value()
        cfg["model_params"]["top_p"] = self.spin_top_p.value()
        cfg["model_params"]["frequency_penalty"] = self.spin_freq.value()
        cfg["model_params"]["presence_penalty"] = self.spin_pres.value()
        cfg["model_params"]["max_tokens"] = self.spin_max_tokens.value()
        cfg["model_params"]["story_max_tokens"] = self.spin_story_max_tokens.value()
        cfg["model_params"]["context_max_rounds"] = self.spin_max_rounds.value()
        cfg["model_params"]["enable_thinking"] = self.chk_thinking.isChecked()

        cfg["prompt_config"]["char_name"] = self.edit_char_name.text().strip()
        cfg["prompt_config"]["user_name"] = self.edit_user_name.text().strip()
        cfg["prompt_config"]["global_prompt"] = self.edit_global_prompt.toPlainText()
        cfg["prompt_config"]["character_card"] = self.edit_character_card.toPlainText()
        cfg["prompt_config"]["user_card"] = self.edit_user_card.toPlainText()
        cfg["prompt_config"]["realtime_prompt"] = self.edit_realtime_prompt.toPlainText()
        cfg["prompt_config"]["story_prompt"] = self.edit_story_prompt.toPlainText()
        cfg["prompt_config"]["error_tip"] = self.edit_error_tip.text().strip()

        ui_style = self.pet.config.setdefault("ui_style", {})
        adv_win = ui_style.setdefault("advanced_window", {})
        msg_bubble = adv_win.setdefault("message_bubble", {})
        msg_bubble["font_size"] = self.spin_bubble_font_size.value()

    def _on_bubble_font_size_changed(self, val):
        """字体大小滑块实时生效：立即更新样式并重绘。"""
        ui_style = self.pet.config.setdefault("ui_style", {})
        adv_win = ui_style.setdefault("advanced_window", {})
        msg_bubble = adv_win.setdefault("message_bubble", {})
        msg_bubble["font_size"] = int(val)
        # 同步 AdvancedChatWindow 缓存
        self._bubble_style = msg_bubble
        # 立即重绘消息列表
        if hasattr(self, "rt_messages_layout") and self.isVisible():
            self._refresh_realtime_messages(scroll_to_bottom=False)
        if hasattr(self, "story_messages_layout") and self.isVisible():
            self._refresh_story_messages(scroll_to_bottom=False)

    def _sync_token_label_color(self):
        """token label 的文字颜色与保存按钮文字颜色同步。"""
        if not hasattr(self, "token_label") or not hasattr(self, "btn_save"):
            return
        color = self.btn_save.palette().color(
            QPalette.ColorRole.ButtonText
        ).name()
        self.token_label.setStyleSheet(f"color: {color}; font-size: 12px;")

    def _update_token_label(self):
        """根据当前 Tab 重算 token 估算值。"""
        if not hasattr(self, "token_label"):
            return
        try:
            idx = self.tabs.currentIndex()
            if idx == 0:
                history = self.pet.chat_history
                messages = self.pet.prompt_engine.build_realtime_messages(history, "")
                prefix = "实时"
            elif idx == 1:
                history = self.pet.story_history
                messages = self.pet.prompt_engine.build_story_messages(history)
                prefix = "故事"
            else:
                self.token_label.setText("")
                return

            if not messages:
                self.token_label.setText(f"{prefix} · 0 tokens")
                return

            system_tokens = _estimate_tokens(messages[0]["content"])
            history_tokens = sum(
                _estimate_tokens(m["content"]) for m in messages[1:]
            )
            total = system_tokens + history_tokens

            self.token_label.setText(
                f"{prefix} · 提示词 {system_tokens} · "
                f"历史 {history_tokens} · 合计 {total} tokens"
            )
            self._sync_token_label_color()
        except Exception as e:
            self.token_label.setText("")
            print(f"⚠ token 估算失败：{e}")

    # ---------- 保存按钮 ----------
    def _on_save_clicked(self):
        try:
            self._save_to_config()
            ok = self.pet.save_config()
            if ok:
                QMessageBox.information(
                    self, "已保存",
                    "配置已保存并生效。"
                )
            else:
                QMessageBox.warning(
                    self, "保存失败",
                    "写入 config.json 失败，请检查文件权限。"
                )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存时出错：\n{e}")

    # ---------- 打开窗口（居中到桌宠所在屏幕） ----------
    def show_window(self):
        self._load_from_config()
        self._refresh_session_combo()
        self._refresh_realtime_messages(scroll_to_bottom=True)
        self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")
        self._refresh_story_session_combo()
        self._refresh_story_messages(scroll_to_bottom=True)

        screen = _screen_of_widget(self.pet)
        geo = screen.availableGeometry()

        # 若窗口比屏幕大，先缩到屏幕大小
        if self.width() > geo.width() or self.height() > geo.height():
            self.resize(
                min(self.width(), geo.width()),
                min(self.height(), geo.height()),
            )

        # 居中
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        rect = _fit_rect_to_screen(QRect(x, y, self.width(), self.height()), screen)
        self.move(rect.left(), rect.top())

        self.show()
        self.raise_()
        self.activateWindow()

    # ===================== 实时对话页：会话管理 =====================
    def _refresh_session_combo(self):
        """刷新会话下拉框，选中当前会话。"""
        self.combo_sessions.blockSignals(True)
        self.combo_sessions.clear()
        sessions = self.pet.history_manager.list_sessions("realtime")
        for s in sessions:
            time_str = time.strftime("%m-%d %H:%M", time.localtime(s.get("last_time", s.get("create_time", 0))))
            label = f"{s.get('name', '未命名')}  ({time_str})"
            self.combo_sessions.addItem(label, s["id"])
            if s["id"] == self.pet.history_manager.current_session_id:
                self.combo_sessions.setCurrentIndex(self.combo_sessions.count() - 1)
        self.combo_sessions.blockSignals(False)

    def _on_new_session(self):
        """新建会话并切过去。"""
        name = f"对话 {time.strftime('%m-%d %H:%M')}"
        self.pet.create_new_chat_session(name=name, mode="realtime")
        # create_new_chat_session 会 emit chat_history_updated → on_history_updated 会刷新

    def _on_switch_session(self, idx):
        """下拉框切换会话。"""
        if idx < 0:
            return
        session_id = self.combo_sessions.itemData(idx)
        if not session_id:
            return
        if session_id == self.pet.history_manager.current_session_id:
            return
        self.pet.switch_chat_session(session_id)
        # switch_chat_session 会 emit chat_history_updated

    def _on_delete_session(self):
        """删除当前会话（需用户确认）。"""
        cur_id = self.pet.history_manager.current_session_id
        if not cur_id:
            return
        ret = QMessageBox.question(
            self, "删除会话",
            "确定要删除当前会话吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.pet.history_manager.delete_session(cur_id)
        # 删除后当前会话可能变成 None 或另一个，需要重新加载
        self.pet.chat_history = self.pet.history_manager.load_current_history()
        # 通知更新（借用 switch 后已有的路径：直接 emit）
        self.pet.chat_history_updated.emit()

    def _on_export(self):
        """导出当前会话为纯文本。"""
        default_name = f"对话_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出对话", default_name, "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"会话：{self.pet.history_manager.current_session_id}\n")
                f.write(f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                for msg in self.pet.chat_history:
                    role_cn = "用户" if msg.get("role") == "user" else "助手"
                    ts = msg.get("time", "")
                    f.write(f"[{ts}] {role_cn}：\n{msg.get('content', '')}\n")
                    f.write("-" * 40 + "\n")
            QMessageBox.information(self, "导出成功", f"已导出到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"写入文件失败：\n{e}")

    # ===================== 会话重命名与清理 =====================
    def _on_rt_combo_context_menu(self, pos):
        self._show_combo_context_menu(pos, mode="realtime", combo=self.combo_sessions)

    def _on_story_combo_context_menu(self, pos):
        self._show_combo_context_menu(pos, mode="story", combo=self.story_combo_sessions)

    def _show_combo_context_menu(self, pos, mode, combo):
        """下拉框右键菜单：重命名当前会话"""
        menu = QMenu(self)
        act_rename = menu.addAction("重命名当前会话")
        act_rename.triggered.connect(lambda: self._rename_current_session(mode))
        menu.exec(combo.mapToGlobal(pos))

    def _rename_current_session(self, mode):
        """弹出输入框，重命名当前会话"""
        if mode == "realtime":
            cur_id = self.pet.history_manager.current_session_id
            sessions = self.pet.history_manager.list_sessions("realtime")
        else:
            cur_id = self.pet.history_manager.get_active_session_id("story")
            sessions = self.pet.history_manager.list_sessions("story")

        if not cur_id:
            QMessageBox.information(self, "提示", "当前没有选中的会话。")
            return

        cur_name = ""
        for s in sessions:
            if s["id"] == cur_id:
                cur_name = s.get("name", "")
                break

        new_name, ok = QInputDialog.getText(
            self, "重命名会话", "输入新名称：", text=cur_name
        )
        if not ok or not new_name.strip():
            return

        self.pet.history_manager.rename_session(cur_id, new_name.strip())

        if mode == "realtime":
            self._refresh_session_combo()
        else:
            self._refresh_story_session_combo()

    def _on_clean_empty_sessions(self):
        """清理所有空会话（实时 + 故事）"""
        ret = QMessageBox.question(
            self, "清理空会话",
            "将删除所有没有消息的空会话，是否继续？\n（此操作不可撤销）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        n = self.pet.history_manager.cleanup_empty_sessions()

        # 刷新主程序的内存缓存
        self.pet.chat_history = self.pet.history_manager.load_current_history()
        self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")

        # 若某模式无剩余会话，自动创建默认会话
        data = self.pet.history_manager._read_full_index()
        if not data.get("current_realtime"):
            self.pet.history_manager.create_session("realtime", "默认对话", set_active=True)
            self.pet.chat_history = self.pet.history_manager.load_current_history()
        if not data.get("current_story"):
            self.pet.history_manager.create_session("story", "默认故事", set_active=False)
            self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")

        # 通知所有组件刷新
        self.pet.chat_history_updated.emit()
        self._refresh_story_session_combo()
        self._refresh_story_messages(scroll_to_bottom=True)

        QMessageBox.information(self, "清理完成", f"已删除 {n} 个空会话。")

    # ===================== 错误提示条控制 =====================
    def show_realtime_error(self, hint):
        if hasattr(self, "rt_error_label"):
            self.rt_error_label.setText("⚠ " + hint)
            self.rt_error_label.show()

    def clear_realtime_error(self):
        if hasattr(self, "rt_error_label"):
            self.rt_error_label.setText("")
            self.rt_error_label.hide()

    def show_story_error(self, hint):
        if hasattr(self, "story_error_label"):
            self.story_error_label.setText("⚠ " + hint)
            self.story_error_label.show()

    def clear_story_error(self):
        if hasattr(self, "story_error_label"):
            self.story_error_label.setText("")
            self.story_error_label.hide()

    # ===================== 滚动 + 流式显示辅助 =====================
    def _scroll_to_bottom(self, scroll_area):
        """可靠地滚动到最底部：多次延迟覆盖布局完成时间。"""
        if scroll_area is None:
            return
        bar = scroll_area.verticalScrollBar()

        def _do():
            try:
                bar.setValue(bar.maximum())
            except Exception:
                pass

        try:
            bar.setValue(bar.maximum())
        except Exception:
            pass
        QTimer.singleShot(0, _do)
        QTimer.singleShot(30, _do)
        QTimer.singleShot(80, _do)
        QTimer.singleShot(150, _do)

    def _append_streaming_bubble_to(self, layout):
        """在 layout 末尾追加流式占位气泡（临时，不入历史）。"""
        self._streaming_bubble = MessageBubble(
            role="assistant",
            content=self._streaming_content or "...",
            time_str="",
            index=-1,
            bubble_style=self._bubble_style,
        )
        # 临时气泡禁用右键菜单，避免误操作编辑/删除
        try:
            self._streaming_bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._streaming_bubble.content_label.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._streaming_bubble.bubble_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self._streaming_bubble.time_label.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        except Exception:
            pass
        layout.addWidget(self._streaming_bubble)

    def begin_ai_streaming(self, mode="realtime"):
        """AI 请求刚发出：立即显示"..."占位气泡。"""
        self._streaming_active = True
        self._streaming_mode = mode
        self._streaming_content = "..."
        if mode == "realtime":
            if hasattr(self, "rt_messages_layout"):
                self._append_streaming_bubble_to(self.rt_messages_layout)
                self._scroll_to_bottom(self.rt_scroll)
        else:
            if hasattr(self, "story_messages_layout"):
                self._append_streaming_bubble_to(self.story_messages_layout)
                self._scroll_to_bottom(self.story_scroll)

    def update_ai_streaming(self, raw_text, config):
        """流式 chunk 到达：过滤后实时更新占位气泡。"""
        if not self._streaming_active or self._streaming_bubble is None:
            return
        filtered = filter_ai_output(raw_text, config)
        self._streaming_content = filtered if filtered else "..."
        try:
            self._streaming_bubble.content_label.setText(self._streaming_content)
        except Exception:
            return
        if self._streaming_mode == "realtime":
            self._scroll_to_bottom(self.rt_scroll)
        elif self._streaming_mode == "story":
            self._scroll_to_bottom(self.story_scroll)

    def end_ai_streaming(self):
        """AI 完成/失败：清理流式状态（气泡由下次 refresh 清除）。"""
        self._streaming_active = False
        self._streaming_mode = None
        self._streaming_content = "..."
        self._streaming_bubble = None

    # ===================== 实时对话页：消息渲染与发送 =====================
    def _refresh_realtime_messages(self, scroll_to_bottom=True):
        """清空消息区并按 pet.chat_history 全量重建。"""
        if not hasattr(self, "rt_messages_layout"):
            return
        # 清空
        while self.rt_messages_layout.count() > 0:
            item = self.rt_messages_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # 遍历 chat_history 重建
        for idx, msg in enumerate(self.pet.chat_history):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ts = msg.get("time", "")
            bubble = MessageBubble(
                role=role, content=content, time_str=ts,
                index=idx, bubble_style=self._bubble_style
            )
            bubble.delete_requested.connect(self._on_delete_message)
            bubble.edit_requested.connect(self._on_edit_message)
            self.rt_messages_layout.addWidget(bubble)

        # 若有活跃的流式生成，追加占位气泡
        if self._streaming_active and self._streaming_mode == "realtime":
            self._append_streaming_bubble_to(self.rt_messages_layout)

        if scroll_to_bottom:
            self._scroll_to_bottom(self.rt_scroll)

    def _on_edit_message(self, index, new_text):
        """用户确认编辑后的新内容：写入 chat_history 并落盘。"""
        if not (0 <= index < len(self.pet.chat_history)):
            return
        self.pet.chat_history[index]["content"] = new_text
        # 附带标记编辑时间（可选，便于后续追溯）
        self.pet.chat_history[index]["edited_at"] = time.time()
        self.pet._is_saving_history = True
        self.pet.history_manager.save_current_history(self.pet.chat_history)
        QTimer.singleShot(600, lambda: setattr(self.pet, '_is_saving_history', False))
        # 不主动刷新：bubble 内部已更新自己的显示文本，下次刷新时重建的也是新内容

    def _on_delete_message(self, index):
        """按索引删除一条消息。"""
        if not (0 <= index < len(self.pet.chat_history)):
            return
        msg = self.pet.chat_history[index]
        role_cn = "用户" if msg.get("role") == "user" else "助手"
        preview = msg.get("content", "")[:40]
        ret = QMessageBox.question(
            self, "删除消息",
            f"删除该条 {role_cn} 消息？\n\n预览：{preview}...",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.pet.chat_history.pop(index)
        self.pet._is_saving_history = True
        self.pet.history_manager.save_current_history(self.pet.chat_history)
        QTimer.singleShot(600, lambda: setattr(self.pet, '_is_saving_history', False))
        self._refresh_realtime_messages(scroll_to_bottom=False)

    def _on_rt_send(self):
        """从高级窗口发送消息，复用 pet.on_user_send_message 全流程。"""
        text = self.rt_input.text().strip()
        if not text:
            return
        self.rt_input.clear()
        self.pet.on_user_send_message(text)
        # 输入禁用与恢复由 pet.on_user_send_message / on_ai_request_finished 统一处理

    # ===================== 供 DesktopPet 调用的槽 =====================
    def on_history_updated(self):
        """收到 pet.chat_history_updated 信号后刷新会话列表 + 消息。"""
        self._refresh_session_combo()
        self._refresh_realtime_messages(scroll_to_bottom=True)
        self._update_token_label()

    def set_input_enabled(self, enabled):
        """供 DesktopPet 统一控制输入框与发送按钮可用性。
        同时控制实时对话与故事模式两套输入。"""
        # 实时对话
        if hasattr(self, "rt_input"):
            self.rt_input.setEnabled(enabled)
            self.rt_btn_send.setEnabled(enabled)
            if hasattr(self, "rt_expand_btn"):
                self.rt_expand_btn.setEnabled(enabled)
            self.btn_new_session.setEnabled(enabled)
            self.btn_delete_session.setEnabled(enabled)
            self.combo_sessions.setEnabled(enabled)
            self.btn_export.setEnabled(enabled)
            self.btn_clean_empty.setEnabled(enabled)
        # 故事模式
        if hasattr(self, "story_input"):
            self.story_input.setEnabled(enabled)
            self.story_btn_send.setEnabled(enabled)
            if hasattr(self, "story_expand_btn"):
                self.story_expand_btn.setEnabled(enabled)
            self.btn_story_new_session.setEnabled(enabled)
            self.btn_story_delete_session.setEnabled(enabled)
            self.story_combo_sessions.setEnabled(enabled)
            self.btn_story_export.setEnabled(enabled)
            self.btn_story_clean_empty.setEnabled(enabled)

    # ===================== 故事模式页：会话管理 =====================
    def _refresh_story_session_combo(self):
        """刷新故事模式会话下拉框，选中当前 story 会话。"""
        self.story_combo_sessions.blockSignals(True)
        self.story_combo_sessions.clear()
        sessions = self.pet.history_manager.list_sessions("story")
        current_sid = self.pet.history_manager.get_active_session_id("story")
        for s in sessions:
            time_str = time.strftime(
                "%m-%d %H:%M",
                time.localtime(s.get("last_time", s.get("create_time", 0)))
            )
            label = f"{s.get('name', '未命名')}  ({time_str})"
            self.story_combo_sessions.addItem(label, s["id"])
            if s["id"] == current_sid:
                self.story_combo_sessions.setCurrentIndex(
                    self.story_combo_sessions.count() - 1
                )
        self.story_combo_sessions.blockSignals(False)

    def _on_story_new_session(self):
        """新建故事会话。"""
        name = f"故事 {time.strftime('%m-%d %H:%M')}"
        self.pet.history_manager.create_session(
            mode="story", session_name=name, set_active=False
        )
        self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")
        self._refresh_story_session_combo()
        self._refresh_story_messages(scroll_to_bottom=True)

    def _on_story_switch_session(self, idx):
        """故事模式切换会话。"""
        if idx < 0:
            return
        sid = self.story_combo_sessions.itemData(idx)
        if not sid:
            return
        current_sid = self.pet.history_manager.get_active_session_id("story")
        if sid == current_sid:
            return
        self.pet.history_manager.switch_session(sid, set_active=False)
        self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")
        self._refresh_story_session_combo()
        self._refresh_story_messages(scroll_to_bottom=True)

    def _on_story_delete_session(self):
        """删除当前故事会话。"""
        cur_sid = self.pet.history_manager.get_active_session_id("story")
        if not cur_sid:
            return
        ret = QMessageBox.question(
            self, "删除故事会话",
            "确定要删除当前故事会话吗？此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.pet.history_manager.delete_session(cur_sid, set_active=False)
        # 若删除后无会话，自动创建默认
        if not self.pet.history_manager.get_active_session_id("story"):
            self.pet.history_manager.create_session(
                "story", "默认故事", set_active=False
            )
        self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")
        self._refresh_story_session_combo()
        self._refresh_story_messages(scroll_to_bottom=True)

    def _on_story_export(self):
        """导出故事会话为纯文本。"""
        default_name = f"故事_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出故事", default_name, "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            sid = self.pet.history_manager.get_active_session_id("story")
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"故事会话：{sid}\n")
                f.write(f"导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                for msg in self.pet.story_history:
                    role_cn = "用户" if msg.get("role") == "user" else "助手"
                    ts = msg.get("time", "")
                    f.write(f"[{ts}] {role_cn}：\n{msg.get('content', '')}\n")
                    f.write("-" * 40 + "\n")
            QMessageBox.information(self, "导出成功", f"已导出到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"写入文件失败：\n{e}")

    # ===================== 故事模式页：消息渲染与发送 =====================
    def _refresh_story_messages(self, scroll_to_bottom=True):
        """按 pet.story_history 全量重建故事消息区。"""
        if not hasattr(self, "story_messages_layout"):
            return
        while self.story_messages_layout.count() > 0:
            item = self.story_messages_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        for idx, msg in enumerate(self.pet.story_history):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            ts = msg.get("time", "")
            bubble = MessageBubble(
                role=role, content=content, time_str=ts,
                index=idx, bubble_style=self._bubble_style
            )
            bubble.delete_requested.connect(self._on_story_delete_message)
            bubble.edit_requested.connect(self._on_story_edit_message)
            self.story_messages_layout.addWidget(bubble)

        # 若有活跃的流式生成，追加占位气泡
        if self._streaming_active and self._streaming_mode == "story":
            self._append_streaming_bubble_to(self.story_messages_layout)

        if scroll_to_bottom:
            self._scroll_to_bottom(self.story_scroll)

    def _on_story_edit_message(self, index, new_text):
        if not (0 <= index < len(self.pet.story_history)):
            return
        self.pet.story_history[index]["content"] = new_text
        self.pet.story_history[index]["edited_at"] = time.time()
        self.pet._is_saving_history = True
        self.pet.history_manager.save_active_history(self.pet.story_history, mode="story")
        QTimer.singleShot(600, lambda: setattr(self.pet, '_is_saving_history', False))

    def _on_story_delete_message(self, index):
        if not (0 <= index < len(self.pet.story_history)):
            return
        msg = self.pet.story_history[index]
        role_cn = "用户" if msg.get("role") == "user" else "助手"
        preview = msg.get("content", "")[:40]
        ret = QMessageBox.question(
            self, "删除消息",
            f"删除该条 {role_cn} 消息？\n\n预览：{preview}...",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.pet.story_history.pop(index)
        self.pet._is_saving_history = True
        self.pet.history_manager.save_active_history(self.pet.story_history, mode="story")
        QTimer.singleShot(600, lambda: setattr(self.pet, '_is_saving_history', False))
        self._refresh_story_messages(scroll_to_bottom=False)

    def _on_story_send(self):
        """故事模式发送：走 pet.send_story_message（独立链路）。"""
        text = self.story_input.text().strip()
        if not text:
            return
        self.story_input.clear()
        self.pet.send_story_message(text)

    def on_story_history_updated(self):
        """供 DesktopPet 在故事模式历史变更后调用。"""
        self._refresh_story_session_combo()
        self._refresh_story_messages(scroll_to_bottom=True)
        self._update_token_label()

    # ===================== Tab 切换 =====================
    def _on_tab_changed(self, index):
        """Tab 切换时按需刷新。"""
        if index == 0:
            # 实时对话
            self._refresh_realtime_messages(scroll_to_bottom=True)
        elif index == 1:
            # 故事模式：从磁盘重新加载（覆盖可能的外部修改）
            self.pet.story_history = self.pet.history_manager.get_active_history(mode="story")
            self._refresh_story_session_combo()
            self._refresh_story_messages(scroll_to_bottom=True)
        # index == 2：设置，无需处理
        self._update_token_label()

# ===================== 行为设置窗口 =====================
class BehaviorSettingWindow(QWidget):
    """行为设置窗口：调整 config.auto_behavior 参数。
    字号固定 14px（标题 16px 加粗），保证可读性。
    样式来自 ui_style.behavior_window，缺失走默认。
    """

    def __init__(self, pet_window):
        super().__init__()
        self.pet = pet_window
        self.setWindowTitle("行为设置")
        self.resize(520, 400)
        self.setMinimumSize(440, 340)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowMinMaxButtonsHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.CustomizeWindowHint
        )
        # 默认样式（会被 set_style_config 覆盖）
        self.style_config = {
            "window_bg": "#ffffff",
            "text_color": "#000000",
            "btn_bg": "#ffffff",
            "btn_hover_bg": "#f0f0f0",
            "border_color": "#dddddd",
        }
        self._build_ui()
        self._apply_style()

    # ---------- 构建 ----------
    def _build_ui(self):
        # 创建主容器并设置 objectName
        main_container = QWidget(self)
        main_container.setObjectName("container")
        main = QVBoxLayout(main_container)
        main.setContentsMargins(20, 16, 20, 16)
        main.setSpacing(12)
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.addWidget(main_container)

        # 顶部标题（加粗略大，与正文区分）
        self.title_label = QLabel("自动行为参数")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main.addWidget(self.title_label)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        # 移动触发等待（秒）
        self.spin_move_trigger = QSpinBox()
        self.spin_move_trigger.setRange(1, 3600)
        self.spin_move_trigger.setSingleStep(1)
        self.spin_move_trigger.setSuffix(" 秒")
        self.spin_move_trigger.setMinimumWidth(140)
        self.spin_move_trigger.valueChanged.connect(self._validate)
        form.addRow("移动触发等待:", self._make_spin_row(self.spin_move_trigger, 1))

        # 移动概率（0.0~1.0，箭头 0.1）
        self.spin_move_prob = QDoubleSpinBox()
        self.spin_move_prob.setRange(0.0, 1.0)
        self.spin_move_prob.setSingleStep(0.1)
        self.spin_move_prob.setDecimals(2)
        self.spin_move_prob.setSuffix(" (0 ~ 1)")
        self.spin_move_prob.setMinimumWidth(140)
        form.addRow("移动概率:", self._make_spin_row(self.spin_move_prob, 0.1))

        # 移动持续时长（秒）
        self.spin_move_duration = QSpinBox()
        self.spin_move_duration.setRange(1, 3600)
        self.spin_move_duration.setSingleStep(1)
        self.spin_move_duration.setSuffix(" 秒")
        self.spin_move_duration.setMinimumWidth(140)
        form.addRow("移动持续时长:", self._make_spin_row(self.spin_move_duration, 1))

        # 移动速度（像素/帧）
        self.spin_move_speed = QSpinBox()
        self.spin_move_speed.setRange(1, 200)
        self.spin_move_speed.setSingleStep(1)
        self.spin_move_speed.setSuffix(" 像素/帧")
        self.spin_move_speed.setMinimumWidth(140)
        form.addRow("移动速度:", self._make_spin_row(self.spin_move_speed, 1))

        # 长待机触发等待（秒）
        self.spin_long_idle_trigger = QSpinBox()
        self.spin_long_idle_trigger.setRange(1, 36000)
        self.spin_long_idle_trigger.setSingleStep(1)
        self.spin_long_idle_trigger.setSuffix(" 秒")
        self.spin_long_idle_trigger.setMinimumWidth(140)
        self.spin_long_idle_trigger.valueChanged.connect(self._validate)
        form.addRow("长待机触发等待:", self._make_spin_row(self.spin_long_idle_trigger, 1))

        main.addLayout(form)

        # 提示/警告
        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        main.addWidget(self.hint_label)

        main.addStretch(1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_save = QPushButton("保存")
        self.btn_save.setMinimumWidth(100)
        self.btn_save.setFixedHeight(36)
        self.btn_save.clicked.connect(self._on_save)
        btn_row.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setMinimumWidth(100)
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.hide)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch(1)
        main.addLayout(btn_row)

    # ---------- 样式 ----------
    def set_style_config(self, config_dict):
        if not config_dict:
            return
        self.style_config.update(config_dict)
        self._apply_style()

    def _make_spin_row(self, spin, step):
        """把 QSpinBox 包装为 [spin(隐藏自带按钮)] + [▲▼ 独立按钮] 的复合控件。

        解决 QSS 定制 QSpinBox 按钮时的三大痛点：
          1. 光标移到按钮上被识别为文本编辑区（hitTest 错位）
          2. 按钮视觉溢出窗口边界（subcontrol-origin 引发）
          3. 按钮与文本框无间隔
        """
        # 隐藏 QSpinBox 自带按钮，只保留输入框本体
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)

        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)  # ★ spin 与按钮之间 4px 间隙
        h.addWidget(spin, 1)

        # 右侧按钮列
        btn_col = QWidget()
        btn_col.setFixedWidth(26)
        v = QVBoxLayout(btn_col)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)  # ▲ 和 ▼ 之间 2px 间隙

        btn_up = QPushButton("▲")
        btn_up.setObjectName("spin_btn")
        btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_up.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # 点击不抢焦点

        btn_down = QPushButton("▼")
        btn_down.setObjectName("spin_btn")
        btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_down.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        def on_up():
            # 解决 QDoubleSpinBox 浮点累加可能出现的 0.300000000004 问题
            val = spin.value()
            if isinstance(spin, QDoubleSpinBox):
                spin.setValue(round(val + step, spin.decimals()))
            else:
                spin.setValue(val + step)

        def on_down():
            val = spin.value()
            if isinstance(spin, QDoubleSpinBox):
                spin.setValue(round(val - step, spin.decimals()))
            else:
                spin.setValue(val - step)

        btn_up.clicked.connect(on_up)
        btn_down.clicked.connect(on_down)

        v.addWidget(btn_up, 1)
        v.addWidget(btn_down, 1)

        h.addWidget(btn_col)
        return container

    def _apply_style(self):
        s = self.style_config

        def c(k):
            return _qss_color(s.get(k, "transparent"))

        window_bg = c('window_bg')
        text_color = c('text_color')
        btn_bg = c('btn_bg')
        btn_hover = c('btn_hover_bg')
        border = c('border_color')

        # 字号固定 14px：不暴露到 config，避免被改成不可读
        self.setStyleSheet(f"""
            QWidget#container {{
                background-color: {window_bg};
                color: {text_color};
                font-size: 14px;
            }}
            QLabel {{
                color: {text_color};
                font-size: 14px;
                background: transparent;
            }}
            QSpinBox, QDoubleSpinBox {{
                background-color: {btn_bg};
                color: {text_color};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 0px 6px;
                font-size: 14px;
                min-height: 28px;
            }}
            QSpinBox:focus, QDoubleSpinBox:focus {{
                border: 1px solid #5a9bd5;
            }}
            QPushButton {{
                background-color: {btn_bg};
                color: {text_color};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 16px;
                font-size: 14px;
                min-height: 28px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#spin_btn {{
                background-color: {btn_bg};
                color: {text_color};
                border: 1px solid {border};
                border-radius: 3px;
                padding: 0px;
                font-size: 9px;
                min-height: 0px;
            }}
            QPushButton#spin_btn:hover {{
                background-color: {btn_hover};
            }}
            QPushButton#spin_btn:pressed {{
                background-color: {border};
            }}
        """)
        # 标题：加粗 16px（比正文大一级，与样式表统一控制）
        self.title_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {text_color};"
            "background: transparent;"
        )
        # 警告文字：红色 14px
        self.hint_label.setStyleSheet(
            "font-size: 14px; color: #d04040; background: transparent;"
        )

    # ---------- 数据 ----------
    def _load_from_config(self):
        ab = self.pet.config.get("auto_behavior", {})
        self.spin_move_trigger.setValue(int(ab.get("move_trigger_seconds", 7)))
        self.spin_move_prob.setValue(float(ab.get("move_probability", 0.6)))
        self.spin_move_duration.setValue(int(ab.get("move_duration_seconds", 2)))
        self.spin_move_speed.setValue(int(ab.get("move_speed", 20)))
        self.spin_long_idle_trigger.setValue(int(ab.get("long_idle_trigger_seconds", 30)))
        self._validate()

    def _validate(self):
        """长待机触发必须 > 移动触发（设计草案 4.4）。
        实时提示，保存时二次拦截。"""
        move = self.spin_move_trigger.value()
        long_idle = self.spin_long_idle_trigger.value()
        if long_idle <= move:
            self.hint_label.setText(
                f"⚠ 长待机触发等待（{long_idle} 秒）必须大于移动触发等待（{move} 秒）"
            )
            return False
        self.hint_label.setText("")
        return True

    def _on_save(self):
        if not self._validate():
            QMessageBox.warning(
                self, "参数不合规",
                "长待机触发等待必须大于移动触发等待，请调整后重试。",
            )
            return
        ab = self.pet.config.setdefault("auto_behavior", {})
        ab["move_trigger_seconds"] = self.spin_move_trigger.value()
        ab["move_probability"] = round(self.spin_move_prob.value(), 2)
        ab["move_duration_seconds"] = self.spin_move_duration.value()
        ab["move_speed"] = self.spin_move_speed.value()
        ab["long_idle_trigger_seconds"] = self.spin_long_idle_trigger.value()

        ok = self.pet.save_config()
        if ok:
            QMessageBox.information(
                self, "已保存",
                "行为参数已保存并生效。",
            )
            self.hide()
        else:
            QMessageBox.warning(
                self, "保存失败",
                "写入 config.json 失败，请检查文件权限。",
            )

    # ---------- 打开/关闭 ----------
    def show_window(self):
        # ★ 每次显示前从 pet.config 拉最新样式
        try:
            ui = self.pet.config.get("ui_style", {}).get("behavior_window", {})
            if ui:
                self.set_style_config(ui)
        except Exception as e:
            print(f"[warn] behavior_window 样式刷新失败: {e}")

        self._load_from_config()

        screen = _screen_of_widget(self.pet)
        geo = screen.availableGeometry()

        if self.width() > geo.width() or self.height() > geo.height():
            self.resize(
                min(self.width(), geo.width()),
                min(self.height(), geo.height()),
            )

        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + (geo.height() - self.height()) // 2
        rect = _fit_rect_to_screen(QRect(x, y, self.width(), self.height()), screen)
        self.move(rect.left(), rect.top())

        self.show()
        self.raise_()
        self.activateWindow()

    # ---------- 生命周期：停/启自动行为计时器 ----------
    def showEvent(self, event):
        super().showEvent(event)
        # 停用自动行为检测计时器（用户要求"计时器停用"）
        if hasattr(self.pet, "behavior_check_timer"):
            self.pet.behavior_check_timer.stop()

    def hideEvent(self, event):
        super().hideEvent(event)
        # 恢复计时器 + 重置计时基准，避免"刚关窗口就突发长待机"
        if hasattr(self.pet, "behavior_check_timer"):
            self.pet.behavior_check_timer.start(1000)
        if hasattr(self.pet, "touch_user_activity"):
            self.pet.touch_user_activity()

class DesktopPet(QWidget):
    # 新增信号：任意对话历史被修改时触发
    chat_history_updated = pyqtSignal()

    # ========== 状态常量（从 __init__ 上提为类属性） ==========
    STATE_BOOT = "boot"
    STATE_STANDBY = "standby"
    STATE_TOUCH = "touch"
    STATE_DRAG = "drag"
    STATE_MOVE = "move"
    STATE_LONG_IDLE = "long_idle"
    STATE_INSTANT_INTERACT = "instant_interact"
    STATE_CONTINUOUS_INTERACT = "continuous_interact"
    STATE_TALK = "talk"
    STATE_EXIT = "exit"
    # 单次播放型状态：进入这些状态时自动 is_play_once = True
    _ONCE_PLAY_STATES = {
        STATE_BOOT, STATE_TOUCH, STATE_INSTANT_INTERACT, STATE_EXIT,
        # 注意：LONG_IDLE / CONTINUOUS_INTERACT 有子状态机，自己管理 is_play_once
    }

    # ========== 打断动作标识 ==========
    ACT_LEFT_CLICK = "left_click"
    ACT_DRAG = "drag"
    ACT_RIGHT_MENU = "right_menu"
    ACT_EXIT = "exit"
    ACT_TIMER = "timer"
    ACT_OPEN_CHAT = "open_chat"   # 5.5 打开的对话动作（原表外，本次补入）

    # ========== 打断权限表 ==========
    # True  = 动作被接受，进入状态机处理
    # False = 动作被忽略；但拖拽移动窗口、右键弹出菜单等"非动画"副作用仍生效
    _INTERRUPT_RULES = {
        STATE_BOOT: {
            ACT_LEFT_CLICK: False, ACT_DRAG: False, ACT_RIGHT_MENU: False,
            ACT_EXIT: False, ACT_TIMER: False, ACT_OPEN_CHAT: False,
        },
        STATE_STANDBY: {
            ACT_LEFT_CLICK: True, ACT_DRAG: True, ACT_RIGHT_MENU: True,
            ACT_EXIT: True, ACT_TIMER: True, ACT_OPEN_CHAT: True,
        },
        STATE_MOVE: {
            ACT_LEFT_CLICK: True, ACT_DRAG: True, ACT_RIGHT_MENU: True,
            ACT_EXIT: True, ACT_TIMER: True, ACT_OPEN_CHAT: True,
        },
        STATE_LONG_IDLE: {
            ACT_LEFT_CLICK: True, ACT_DRAG: False, ACT_RIGHT_MENU: True,
            ACT_EXIT: True, ACT_TIMER: False, ACT_OPEN_CHAT: True,
        },
        STATE_TOUCH: {
            ACT_LEFT_CLICK: False, ACT_DRAG: False, ACT_RIGHT_MENU: False,
            ACT_EXIT: True, ACT_TIMER: False, ACT_OPEN_CHAT: False,
        },
        STATE_DRAG: {
            ACT_LEFT_CLICK: False, ACT_DRAG: False, ACT_RIGHT_MENU: True,
            ACT_EXIT: True, ACT_TIMER: False, ACT_OPEN_CHAT: True,
        },
        STATE_INSTANT_INTERACT: {
            ACT_LEFT_CLICK: False, ACT_DRAG: False, ACT_RIGHT_MENU: True,
            ACT_EXIT: True, ACT_TIMER: False, ACT_OPEN_CHAT: False,
        },
        STATE_CONTINUOUS_INTERACT: {
            ACT_LEFT_CLICK: True, ACT_DRAG: False, ACT_RIGHT_MENU: False,
            ACT_EXIT: True, ACT_TIMER: False, ACT_OPEN_CHAT: False,
        },
        STATE_TALK: {
            ACT_LEFT_CLICK: True, ACT_DRAG: False, ACT_RIGHT_MENU: False,
            ACT_EXIT: True, ACT_TIMER: False, ACT_OPEN_CHAT: True,
        },
        STATE_EXIT: {
            ACT_LEFT_CLICK: False, ACT_DRAG: False, ACT_RIGHT_MENU: False,
            ACT_EXIT: False, ACT_TIMER: False, ACT_OPEN_CHAT: False,
        },
    }

    def can_interrupt(self, state, action):
        """查询动作能否被状态机接受。False 不代表副作用不发生（详见类注释）。"""
        return self._INTERRUPT_RULES.get(state, {}).get(action, False)

    def __init__(self):
        super().__init__()
        # ========== 加载配置文件 ==========
        self.config = self.load_config(_p("config.json"))

        # ========== 运行时状态（独立于 config.json，避免触发热重载） ==========
        self.runtime_state_path = _p("data/runtime_state.json")
    
        # ========== 配置热重载相关 ==========
        self.config_path = _p("config.json")
        self.config_watcher = QFileSystemWatcher()
        self.config_watcher.addPath(self.config_path)
        self.config_watcher.fileChanged.connect(self._on_config_file_changed)
        self.config_reload_timer = QTimer()
        self.config_reload_timer.setSingleShot(True)
        self.config_reload_timer.timeout.connect(self.reload_config)
        # 对话历史文件重载定时器
        self.history_reload_timer = QTimer()
        self.history_reload_timer.setSingleShot(True)
        self.history_reload_timer.timeout.connect(self.reload_chat_history)

        # ========== 窗口基础设置 ==========
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(self.config["window"]["width"], self.config["window"]["height"])

        # 恢复上次窗口位置（越界自动吸附到屏幕内）
        self._load_and_apply_saved_position()

        # ========== 动画核心变量 ==========
        self.frame_list = []
        self.mask_list = []
        self.current_frame = 0
        self.fps = self.config["animation"]["standby_fps"]

        # ========== 动画定时器 ==========
        self.anim_timer = QTimer()
        self.anim_timer.timeout.connect(self.next_frame)

        self.current_state = self.STATE_BOOT  # 初始状态改为开机

        # ========== 自动行为状态 ==========
        self.LONG_IDLE_START = "start"
        self.LONG_IDLE_LOOP = "loop"
        self.LONG_IDLE_END = "end"
        self.long_idle_sub_state = self.LONG_IDLE_START

        # ========== 互动状态定义 ==========
        self.CONTINUOUS_START = "start"
        self.CONTINUOUS_LOOP = "loop"
        self.CONTINUOUS_END = "end"
        self.continuous_sub_state = self.CONTINUOUS_START
        self.current_interact_config = None  # 保存当前播放的互动动作配置
        self.pending_interact = None        # 待播放互动（退场结束后自动触发）
        self.pending_exit = False           # 待退出标记（退场结束后触发退出）

        # ========== 计时与移动变量 ==========
        self.last_operation_time = 0
        self.move_direction = "right"
        self.is_moving = False
        self.move_timer = QTimer()
        self.behavior_check_timer = QTimer()

        # ========== 拖拽交互变量 ==========
        self.drag_offset = QPoint()
        self.is_dragging = False
        self.press_global_pos = QPoint()
        self.DRAG_THRESHOLD = 5

        # 初始化加载开机动画；加载失败时直接进入默认待机
        boot_ok = self.load_frames(self.config["assets"]["boot_path"])
        if boot_ok:
            self.fps = self.config["animation"]["boot_fps"]
            self.anim_timer.setInterval(int(1000 / self.fps))
            self.anim_timer.start()
            self.is_play_once = True  # 开机动画单次播放
        else:
            print("⚠ 开机素材缺失，跳过开机动画，直接进入默认待机")
            self.is_play_once = False
            # 注意：此时 current_state 还是 STATE_BOOT，切到 STANDBY 会正常执行
            self.switch_state(self.STATE_STANDBY)

        # ========== 启动自动行为检测 ==========
        self.behavior_check_timer.timeout.connect(self.check_auto_behavior)
        self.behavior_check_timer.start(1000)
        
        self.move_timer.timeout.connect(self.update_move_position)
        self.last_operation_time = time.time()

        # ========== 右键菜单 ==========
        self.right_menu = PetRightMenu(self)

        # ========== 对话气泡 ==========
        self.chat_bubble = ChatBubble(self)
        self.chat_bubble.size_changed.connect(self._update_bubble_position)
        # 气泡参数与样式在 __init__ 末尾统一通过 _update_all_ui_from_config() 应用

        # ========== 对话输入栏 ==========
        self.chat_input = ChatInputBar(self)
        self.chat_input.attach_pet(self)
        self.chat_input.send_clicked.connect(self.on_user_send_message)
        self.chat_input.open_advanced.connect(self.show_advanced_chat)
        self.chat_input.close_clicked.connect(self.close_chat)
        self.is_chat_open = False

        # ========== AI请求相关 ==========
        self.ai_worker = None
        self._current_ai_text = ""
        self.prompt_engine = PromptEngine(self.config)
        self.history_manager = ChatHistoryManager(_p("data/chat"))
        self.chat_history = self.history_manager.load_current_history()
        self._is_saving_history = False

        # ========== 故事模式（独立于 chat_history） ==========
        self.story_history = self.history_manager.get_active_history(mode="story")
        self.story_worker = None

        # 监听当前会话历史文件变化
        current_file = self.history_manager.get_current_session_file_path()
        if current_file:
            self.config_watcher.addPath(current_file)

        # ========== 互动选择窗口 ==========
        self.interact_window = InteractWindow(self)

        # ========== 高级对话窗口 ==========
        self.advanced_window = AdvancedChatWindow(self)
        self.chat_history_updated.connect(self.advanced_window.on_history_updated)

        # ========== 行为设置窗口 ==========
        self.behavior_setting_window = BehaviorSettingWindow(self)

        # ========== 系统托盘 ==========
        self.init_tray()
        # 设置窗口不在任务栏显示
        self.setWindowFlag(Qt.WindowType.Tool, True)
        
        # 应用初始 UI 参数与样式
        self._update_all_ui_from_config()

        # ========== 位置保存防抖定时器 ==========
        self._state_save_timer = QTimer()
        self._state_save_timer.setSingleShot(True)
        self._state_save_timer.timeout.connect(self._save_runtime_state)

        # ========== 屏幕变化监听（副屏拔掉后自动救援） ==========
        app = QApplication.instance()
        if app is not None:
            try:
                app.screenRemoved.connect(self._on_screen_removed)
            except Exception as e:
                print(f"⚠ 连接 screenRemoved 失败：{e}")

    # ===================== 运行时状态保存 / 加载 =====================
    def _save_runtime_state(self):
        """保存主窗口当前左上角位置到独立状态文件。失败静默。"""
        try:
            os.makedirs(os.path.dirname(self.runtime_state_path), exist_ok=True)
            with open(self.runtime_state_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"window_pos": [self.x(), self.y()]},
                    f, ensure_ascii=False,
                )
        except Exception as e:
            print(f"⚠ 保存运行时状态失败：{e}")

    def _load_runtime_state(self):
        """读取上次保存的窗口位置。失败返回 None。"""
        try:
            with open(self.runtime_state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            pos = data.get("window_pos")
            if isinstance(pos, list) and len(pos) == 2:
                return QPoint(int(pos[0]), int(pos[1]))
        except Exception:
            pass
        return None

    def _load_and_apply_saved_position(self):
        """加载上次位置并应用（自动夹紧到可用屏幕）。无保存时保持默认位置。"""
        saved = self._load_runtime_state()
        if saved is None:
            return

        # 判断保存位置是否位于某个屏幕上；若是（哪怕部分可见），就用那个屏幕夹紧
        screen = QApplication.screenAt(saved)
        if screen is None:
            # 完全不在任何屏幕上（比如副屏被拔掉）→ 用主屏
            screen = QApplication.primaryScreen()
        if screen is None:
            return

        geo = screen.availableGeometry()
        w = self.config["window"]["width"]
        h = self.config["window"]["height"]
        rect = _fit_rect_to_screen(QRect(saved, QSize(w, h)), screen)
        self.move(rect.left(), rect.top())

    # ===================== 屏幕变化救援 =====================
    def _on_screen_removed(self, screen):
        """某块屏幕被移除后，若宠物中心不在任何屏幕内，自动移回主屏中心。
        延迟 100ms 让操作系统的窗口管理先完成（Windows 有时会先移动窗口）。
        """
        # 判断是否还有"宠物所在的屏幕"：等系统处理完再检查
        QTimer.singleShot(100, self._ensure_pet_on_a_screen)

    def _ensure_pet_on_a_screen(self):
        """确保宠物中心在某个屏幕内。不在则移回主屏中心并保存位置。"""
        center = self.frameGeometry().center()
        if QApplication.screenAt(center) is not None:
            return  # 宠物在某块屏幕上，无需救援

        primary = QApplication.primaryScreen()
        if primary is None:
            return

        geo = primary.availableGeometry()
        w = self.width()
        h = self.height()
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + (geo.height() - h) // 2
        rect = _fit_rect_to_screen(QRect(x, y, w, h), primary)
        self.move(rect.left(), rect.top())
        self._update_bubble_position()
        if self.is_chat_open:
            self._update_chat_input_position()
        self._save_runtime_state()
        print("⚠ 所在屏幕已移除，宠物已移回主屏中心")

    def _rescue_to_screen(self):
        """托盘"回到屏幕内"：把宠物移回主屏中心并保存位置。
        与 _ensure_pet_on_a_screen 不同——这个方法无条件移动（哪怕宠物当前就在屏幕上），
        用于用户把宠物拖到屏幕外或被系统隐藏时的手动救援。
        """
        primary = QApplication.primaryScreen()
        if primary is None:
            return
        geo = primary.availableGeometry()
        w = self.width()
        h = self.height()
        x = geo.x() + (geo.width() - w) // 2
        y = geo.y() + (geo.height() - h) // 2
        rect = _fit_rect_to_screen(QRect(x, y, w, h), primary)
        self.move(rect.left(), rect.top())
        self._update_bubble_position()
        if self.is_chat_open:
            self._update_chat_input_position()
        self._save_runtime_state()
        print("✅ 宠物已移回主屏中心")

    # ===================== 用户操作时间统一收口 =====================
    def touch_user_activity(self):
        """任何用户主动操作都应调用此方法：重置自动行为计时基准。
        后续新增交互入口时，优先调用此方法，不要直接改 last_operation_time。"""
        self.last_operation_time = time.time()

    # ===================== 初始化系统托盘 =====================
    def init_tray(self):
        self.tray = QSystemTrayIcon(self)

        # 优先 ico → 首帧 PNG → 内置绘制图标
        icon_loaded = False
        for icon_path in (_p("data/icon.ico"), _p("assets/desktop_pet.ico"),
                          _p("assets/icon.ico"), _p("assets/tray.ico")):
            if os.path.exists(icon_path):
                self.tray.setIcon(QIcon(icon_path))
                icon_loaded = True
                break
        if not icon_loaded and len(self.frame_list) > 0:
            self.tray.setIcon(QIcon(self.frame_list[0]))
            icon_loaded = True
        if not icon_loaded:
            print("⚠ 未找到任何图标素材，使用内置兜底托盘图标")
            self.tray.setIcon(self._build_default_tray_icon())

        tray_menu = QMenu()
        rescue_action = tray_menu.addAction("重置位置")
        rescue_action.triggered.connect(self._rescue_to_screen)
        tray_menu.addSeparator()
        exit_action = tray_menu.addAction("退出")
        exit_action.triggered.connect(self.start_exit)
        self.tray.setContextMenu(tray_menu)
        self.tray.setToolTip("桌面宠物")
        self.tray.show()

    def _build_default_tray_icon(self):
        """没有任何图标素材时，绘制一个蓝圆点作为托盘图标。"""
        from PyQt6.QtGui import QBrush
        size = 32
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QBrush(QColor(80, 140, 220)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, size - 4, size - 4)
        p.end()
        return QIcon(pix)

    # ===================== 加载配置文件 =====================
    def load_config(self, config_path):
        """加载配置。失败时依次尝试：.bak 备份 → 内置默认。"""
        backup_path = config_path + ".bak"

        # 第一次尝试：主文件
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # 基础结构校验
            if not isinstance(data, dict) or "window" not in data:
                raise ValueError("配置结构不完整")
            return data
        except Exception as e:
            print(f"⚠ config.json 加载失败：{e}")

        # 第二次尝试：.bak 备份
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict) or "window" not in data:
                    raise ValueError("备份配置结构不完整")
                print(f"✅ 已从 {backup_path} 恢复配置")
                # 自动把 .bak 复制回主文件（下次重启直接可用）
                try:
                    with open(config_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"✅ 已自动修复 config.json")
                except Exception as ex:
                    print(f"⚠ 自动修复失败：{ex}")
                return data
            except Exception as e:
                print(f"⚠ config.json.bak 也损坏：{e}")

        # 第三次尝试：内置默认
        print("⚠ 使用内置默认配置启动（原配置文件可能已损坏）")
        return self._get_default_config()

    def _get_default_config(self):
        """最小可用的默认配置。仅当主文件+备份都损坏时使用。"""
        return {
            "window": {"width": 364, "height": 364},
            "ui_style": {},
            "animation": {
                "standby_fps": 16, "touch_fps": 16, "drag_fps": 16,
                "move_fps": 16, "long_idle_fps": 16, "interact_fps": 16,
                "boot_fps": 16, "talk_fps": 16,
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
                "api_config": {
                    "base_url": "",
                    "api_key": "",
                    "model_name": "",
                },
                "model_params": {
                    "temperature": 1.0, "max_tokens": 1000, "story_max_tokens": 5000,
                    "top_p": 1.0, "frequency_penalty": 0.0, "presence_penalty": 0.0,
                    "enable_thinking": False, "reasoning_effort": "high",
                    "context_max_rounds": 30,
                },
                "prompt_config": {
                    "char_name": "桌宠", "user_name": "用户",
                    "global_prompt": "", "character_card": "", "user_card": "",
                    "realtime_prompt": "", "story_prompt": "",
                    "error_tip": "AI 暂时无法回复。",
                },
                "ui_config": {
                    "text_speed_char_per_sec": 4,
                    "bubble_max_width": 320,
                    "bubble_stay_seconds": 5,
                },
                "output_filter": {
                    "rules": [dict(r) for r in _DEFAULT_FILTER_RULES],
                    "strip_result": True,
                    "fallback_to_raw_if_empty": True,
                },
                "timestamp_config": {"enable": False},
            },
        }

    # ===================== 配置读写与热重载 =====================
    def save_config(self):
        """保存配置到磁盘。先备份旧文件，再原子写新文件。"""
        try:
            # 1. 旧文件存在则先备份（旧 .bak 先删掉，只保留一份）
            if os.path.exists(self.config_path):
                try:
                    if os.path.exists(self.config_path + ".bak"):
                        os.remove(self.config_path + ".bak")
                    # 用 shutil.copy 而不用 os.replace——避免"没有 .bak"时写到一半崩溃
                    import shutil
                    shutil.copy(self.config_path, self.config_path + ".bak")
                except Exception as e:
                    print(f"⚠ 备份配置失败（不影响保存）：{e}")

            # 2. 原子写新配置
            tmp_path = self.config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except Exception:
                    pass
            os.replace(tmp_path, self.config_path)
            return True
        except Exception as e:
            print(f"保存配置失败：{e}")
            # 清理残留 tmp
            try:
                if os.path.exists(self.config_path + ".tmp"):
                    os.remove(self.config_path + ".tmp")
            except Exception:
                pass
            return False

    def reload_config(self):
        """重新加载配置文件，并同步更新所有UI控件参数"""
        try:
            new_config = self.load_config(self.config_path)
        except Exception as e:
            print(f"重载配置失败，保留原配置：{e}")
            return

        # 校验通过才替换配置
        self.config = new_config
        self._update_all_ui_from_config()

        # 根据当前状态立即重置定时器频率
        fps_map = {
            self.STATE_STANDBY: "standby_fps",
            self.STATE_DRAG: "drag_fps",
            self.STATE_MOVE: "move_fps",
            self.STATE_LONG_IDLE: "long_idle_fps",
            self.STATE_TALK: "talk_fps",
            self.STATE_BOOT: "boot_fps",
        }
        if self.current_state in fps_map:
            self.fps = self.config["animation"].get(fps_map[self.current_state], 16)
            self.anim_timer.setInterval(int(1000 / self.fps))

        print("配置已重载生效")

    def reload_chat_history(self):
        if self._is_saving_history:
            return
        try:
            new_history = self.history_manager.load_current_history()
            self.chat_history = new_history
            print("✅ 当前对话历史已从文件重载生效")
        except Exception as e:
            print(f"❌ 重载对话历史失败：{e}")

    def create_new_chat_session(self, name="新对话", mode=None):
        """新建对话会话，mode可选realtime/story，默认当前模式"""
        old_file = self.history_manager.get_current_session_file_path()
        if old_file and old_file in self.config_watcher.files():
            self.config_watcher.removePath(old_file)

        # 使用 set_active 避免污染另一模式的状态
        target_mode = mode if mode else self.history_manager.current_mode
        new_id = self.history_manager.create_session(target_mode, name, set_active=True)
        
        if target_mode == "realtime":
            self.chat_history = self.history_manager.load_current_history()
        else:
            self.story_history = self.history_manager.get_active_history(mode="story")

        new_file = self.history_manager.get_current_session_file_path()
        if new_file:
            self.config_watcher.addPath(new_file)
        self.chat_history_updated.emit()
        return new_id

    def switch_chat_mode(self, mode):
        """切换对话模式：realtime / story"""
        old_file = self.history_manager.get_current_session_file_path()
        if old_file and old_file in self.config_watcher.files():
            self.config_watcher.removePath(old_file)

        self.history_manager.switch_mode(mode)
        self.chat_history = self.history_manager.load_current_history()

        new_file = self.history_manager.get_current_session_file_path()
        if new_file:
            self.config_watcher.addPath(new_file)

    def switch_chat_session(self, session_id):
        """切换对话会话（高级窗口调用）"""
        old_file = self.history_manager.get_current_session_file_path()
        if old_file and old_file in self.config_watcher.files():
            self.config_watcher.removePath(old_file)

        self.history_manager.switch_session(session_id)
        self.chat_history = self.history_manager.load_current_history()

        new_file = self.history_manager.get_current_session_file_path()
        if new_file:
            self.config_watcher.addPath(new_file)
        # ★ 通知高级窗口刷新会话列表与消息
        self.chat_history_updated.emit()

    def _update_all_ui_from_config(self):
        """根据最新配置，同步更新所有控件的参数与样式"""
        # 1. 气泡行为参数（尺寸/速度/停留）
        ai_ui = self.config.get("ai_system", {}).get("ui_config", {})
        self.chat_bubble.set_config(
            ai_ui.get("bubble_max_width", 320),
            ai_ui.get("text_speed_char_per_sec", 4),
            ai_ui.get("bubble_stay_seconds", 5)
        )

        # 2. UI 样式（全局，跨模块）
        ui_style = self.config.get("ui_style", {})
        if "bubble" in ui_style:
            self.chat_bubble.set_style(ui_style["bubble"])
        if "chat_input" in ui_style and hasattr(self, "chat_input"):
            self.chat_input.set_style_config(ui_style["chat_input"])
        if "right_menu" in ui_style and hasattr(self, "right_menu"):
            self.right_menu.set_style_config(ui_style["right_menu"])
        if "interact_window" in ui_style and hasattr(self, "interact_window"):
            self.interact_window.set_style_config(ui_style["interact_window"])
        if "advanced_window" in ui_style and hasattr(self, "advanced_window"):
            self.advanced_window.set_style_config(ui_style["advanced_window"])
        if "behavior_window" in ui_style and hasattr(self, "behavior_setting_window"):
            self.behavior_setting_window.set_style_config(ui_style["behavior_window"])

        # 3. 对话状态下重新应用对话帧率（非对话状态下次切换时自动生效）
        if self.current_state == self.STATE_TALK:
            self.fps = self.config["animation"]["talk_fps"]
            self.anim_timer.setInterval(int(1000 / self.fps))

        # 4. 同步更新提示词引擎的配置引用
        self.prompt_engine.config = self.config

    def _on_config_file_changed(self, path):
        if path == self.config_path:
            self.config_reload_timer.start(500)
        elif path == self.history_manager.get_current_session_file_path():
            self.history_reload_timer.start(300)

    # ===================== 加载序列帧 + 逐帧掩码 =====================
    def load_frames(self, folder_path):
        folder_path = _p(folder_path)
        if not os.path.isdir(folder_path):
            print(f"素材目录不存在: {folder_path}")
            return False
            
        # 推导 mask 目录：将路径中的 "/assets/" 替换为 "/mask/"
        mask_dir = folder_path.replace("/assets/", "/mask/").replace("\\assets\\", "\\mask\\")
        if mask_dir == folder_path:
            # 兜底：如果没有 assets 目录，则尝试去同级目录找 mask
            mask_dir = os.path.join(os.path.dirname(os.path.dirname(folder_path)), "mask", os.path.basename(folder_path))
        
        temp_frames = []
        temp_masks = []
        all_files = os.listdir(folder_path)
        png_files = [f for f in all_files if f.lower().endswith(".png") and f.lower() != "preview.png"]
        png_files.sort(key=lambda n: [int(t) if t.isdigit() else t.lower()
                                      for t in re.split(r'(\d+)', n)])
                                      
        for file_name in png_files:
            full_path = os.path.join(folder_path, file_name)
            pixmap = QPixmap(full_path)
            temp_frames.append(pixmap)
            
            # 尝试加载预生成的降采样掩码
            mask_path = os.path.join(mask_dir, file_name)
            mask_img = QImage()
            if os.path.exists(mask_path):
                mask_img = QImage(mask_path)
                
            if mask_img.isNull():
                # 回退兜底：实时提取帧的 Alpha 生成 1/4 灰度掩码
                img = pixmap.toImage()
                if img.format() != QImage.Format.Format_ARGB32:
                    img = img.convertToFormat(QImage.Format.Format_ARGB32)
                
                mw = max(1, img.width() // 4)
                mh = max(1, img.height() // 4)
                scaled = img.scaled(mw, mh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
                
                # 新建一张标准的 ARGB32 图像作为掩码
                mask_img = QImage(mw, mh, QImage.Format.Format_ARGB32)
                for y in range(mh):
                    for x in range(mw):
                        alpha = qAlpha(scaled.pixel(x, y))
                        # Alpha >= 128 视为不透明(白 255)，否则视为透明(黑 0)
                        val = 255 if alpha >= 128 else 0
                        mask_img.setPixel(x, y, qRgb(val, val, val))
                
            temp_masks.append(mask_img)
            
        if len(temp_frames) == 0:
            print(f"目录中无 PNG: {folder_path}")
            return False
            
        self.frame_list = temp_frames
        self.mask_list = temp_masks
        
        # 彻底清理联合掩码，将窗口穿透交还给系统原生像素检测
        self.clearMask()
        return True

    def _is_opaque_at(self, pos):
        """判断鼠标坐标 pos(QPoint) 是否在当前帧的不透明区域内。"""
        if not getattr(self, "mask_list", None) or not self.mask_list:
            return True
        if self.current_frame >= len(self.mask_list):
            return True
        
        mask_img = self.mask_list[self.current_frame]
        if mask_img is None or mask_img.isNull():
            return True
        
        # 确保掩码是标准的 ARGB32，防止 qGray 读取出错
        if mask_img.format() != QImage.Format.Format_ARGB32:
            mask_img = mask_img.convertToFormat(QImage.Format.Format_ARGB32)
        
        win_w = self.width()
        win_h = self.height()
        mw = mask_img.width()
        mh = mask_img.height()
        if win_w <= 0 or win_h <= 0 or mw <= 0 or mh <= 0:
            return True
        
        # 将鼠标坐标按比例映射到 1/4 掩码图坐标
        mx = int(pos.x() * mw / win_w)
        my = int(pos.y() * mh / win_h)
        
        # 越界保护
        mx = max(0, min(mx, mw - 1))
        my = max(0, min(my, mh - 1))
        
        # 掩码是灰度图，白色(255)为不透明，黑色(0)为透明
        from PyQt6.QtGui import qGray
        pixel_val = mask_img.pixel(mx, my)
        gray_val = qGray(pixel_val)
        is_opaque = gray_val > 128
        
        return is_opaque

    # ===================== 状态切换核心方法 =====================
    def switch_state(self, new_state):
        if new_state == self.current_state:
            return
        # 先停止定时器，避免切换过程中触发帧更新
        self.anim_timer.stop()
        self.current_state = new_state
        self.current_frame = 0  # 强制重置到第0帧
        self.is_play_once = new_state in self._ONCE_PLAY_STATES

        ok = True

        if new_state == self.STATE_STANDBY:
            ok = self.load_frames(self.config["assets"]["standby_path"])
            self.fps = self.config["animation"]["standby_fps"]
        elif new_state == self.STATE_DRAG:
            ok = self.load_frames(self.config["assets"]["drag_path"])
            self.fps = self.config["animation"]["drag_fps"]
        elif new_state == self.STATE_MOVE:
            path = (self.config["assets"]["move_right_path"]
                    if self.move_direction == "right"
                    else self.config["assets"]["move_left_path"])
            ok = self.load_frames(path)
            self.fps = self.config["animation"]["move_fps"]
        elif new_state == self.STATE_LONG_IDLE:
            self.fps = self.config["animation"]["long_idle_fps"]
        elif new_state == self.STATE_TALK:
            ok = self.load_frames(self.config["assets"]["talk_path"])
            self.fps = self.config["animation"]["talk_fps"]

        # ===== B2 回落逻辑 =====
        # 目标状态的素材缺失时，回落到默认待机，避免"状态改了但画面还是上一套帧"
        if not ok and new_state != self.STATE_STANDBY:
            print(f"状态 {new_state} 素材缺失，回落到默认待机")
            self.current_state = self.STATE_STANDBY
            self.current_frame = 0
            self.is_play_once = False
            self.fps = self.config["animation"]["standby_fps"]
            if not self.load_frames(self.config["assets"]["standby_path"]):
                print("默认待机素材缺失！保留当前画面，请检查 assets 目录")

        # 重置定时器间隔并重新启动
        self.anim_timer.setInterval(int(1000 / self.fps))
        self.anim_timer.start()
        # 强制立即重绘，显示第0帧
        self.update()

    # ===================== 专用：播放触摸动画（普通/特殊通用） =====================
    def play_touch_animation(self, asset_path):
        # 1. 先停止定时器，锁住状态
        self.anim_timer.stop()
        # 2. 切换状态
        self.current_state = self.STATE_TOUCH
        # 3. 强制重置帧索引为0（关键修复点）
        self.current_frame = 0
        self.is_play_once = True
        # 4. 加载对应素材
        if not self.load_frames(asset_path):
            # 触摸素材缺失 → 直接用默认待机，播放循环
            print(f"触摸素材缺失：{asset_path}，回落到待机")
            self.switch_state(self.STATE_STANDBY)
            self.touch_user_activity()
            return
        self.fps = self.config["animation"]["touch_fps"]
        # 5. 重新启动定时器
        self.anim_timer.setInterval(int(1000 / self.fps))
        self.anim_timer.start()
        # 6. 强制重绘，立即显示第0帧
        self.update()

    # ===================== 通用：播放指定互动动作 =====================
    def play_interact(self, action_config):
        self.touch_user_activity()
        # 当前是持续互动：先播放退场，退场结束后自动播放新动作
        if self.current_state == self.STATE_CONTINUOUS_INTERACT and self.continuous_sub_state != self.CONTINUOUS_END:
            self.pending_interact = action_config
            self.end_continuous_interact()
            return
        # 校验目标素材存在
        base = _p(action_config["path"])
        need = [os.path.join(base, "start")] if action_config["type"] == "continuous" else [base]
        if not all(os.path.isdir(p) for p in need):
            print(f"互动素材缺失：{base}，忽略本次互动")
            self.touch_user_activity()
            return
        # 正常播放新互动
        self.anim_timer.stop()
        self.current_interact_config = action_config
        self.current_frame = 0
        self.is_play_once = False
        if action_config["type"] == "instant":
            self.current_state = self.STATE_INSTANT_INTERACT
            self.is_play_once = True
            self.load_frames(action_config["path"])
            self.fps = action_config.get("fps", 16)
        elif action_config["type"] == "continuous":
            self.current_state = self.STATE_CONTINUOUS_INTERACT
            self.continuous_sub_state = self.CONTINUOUS_START
            self.is_play_once = True
            start_path = os.path.join(action_config["path"], "start")
            self.load_frames(start_path)
            self.fps = action_config.get("fps", 16)
        self.anim_timer.setInterval(int(1000 / self.fps))
        self.anim_timer.start()
        self.update()

    # ===================== 结束持续互动（播放退场） =====================
    def end_continuous_interact(self):
        if self.current_state != self.STATE_CONTINUOUS_INTERACT:
            return
        self.continuous_sub_state = self.CONTINUOUS_END
        end_path = _p(os.path.join(self.current_interact_config["path"], "end"))
        if not self.load_frames(end_path):
            # 退场素材缺失，走"无退场"的快捷退出路径
            print(f"互动退场素材缺失：{end_path}，直接结束互动")
            self.current_interact_config = None
            if self.pending_exit:
                self.pending_exit = False
                self.start_exit()
            elif self.is_chat_open:
                self.switch_state(self.STATE_TALK)
            else:
                self.switch_state(self.STATE_STANDBY)
            return
        self.current_frame = 0
        self.is_play_once = True

    # ===================== 检测点击命中的特殊触摸 =====================
    def check_special_touch(self, click_pos):
        """遍历配置里所有特殊触摸，按顺序匹配。优先 area_ratio，回落 area（绝对像素）。"""
        for touch_item in self.config["assets"]["special_touches"]:
            area = self._get_special_area(touch_item)
            if area is None:
                continue
            x, y, w, h = area
            if x <= click_pos.x() <= x + w and y <= click_pos.y() <= y + h:
                return touch_item["path"]
        return None

    def _get_special_area(self, touch_item):
        """返回特殊触摸区域的绝对像素 (x, y, w, h)。
        优先用相对比例 area_ratio（0~1），回落旧格式绝对 area。
        """
        win_w = self.width()
        win_h = self.height()

        ratio = touch_item.get("area_ratio")
        if isinstance(ratio, dict):
            try:
                return (
                    int(ratio["x"] * win_w),
                    int(ratio["y"] * win_h),
                    int(ratio["width"] * win_w),
                    int(ratio["height"] * win_h),
                )
            except (KeyError, TypeError, ValueError):
                pass

        area = touch_item.get("area")
        if isinstance(area, dict):
            try:
                return (int(area["x"]), int(area["y"]),
                        int(area["width"]), int(area["height"]))
            except (KeyError, TypeError, ValueError):
                pass

        return None

    # ===================== 打断自动行为 =====================
    def interrupt_auto_behavior(self):
        if self.is_moving:
            self.move_timer.stop()
            self.is_moving = False
        if self.current_state == self.STATE_LONG_IDLE:
            self.long_idle_sub_state = self.LONG_IDLE_END
            if not self.load_frames(self.config["assets"]["long_idle_end_path"]):
                print("长待机退场素材缺失，直接回待机")
                self.switch_state(self.STATE_STANDBY)
                return
            self.current_frame = 0
            self.is_play_once = True
        else:
            self.switch_state(self.STATE_STANDBY)

    # ===================== 启动退出流程 =====================
    def start_exit(self):
        # ★ 退出前保存最后一次位置
        self._save_runtime_state()

        # ★ 兜底：当前无任何可播放帧（素材全缺导致状态机无法自愈）
        #   此时绝不能信任权限表——用户必须能关掉程序
        if len(self.frame_list) == 0:
            print("⚠ 当前无动画帧，强制退出程序")
            try:
                self.config_watcher.removePath(self.config_path)
            except Exception:
                pass
            QApplication.instance().quit()
            return

        if not self.can_interrupt(self.current_state, self.ACT_EXIT):
            return
        
        # 停止配置监听
        try:
            self.config_watcher.removePath(self.config_path)
        except Exception:
            pass
        
        if self.current_state == self.STATE_EXIT:
            return
        # 持续互动中：先播放退场，退场结束后再执行退出
        if self.current_state == self.STATE_CONTINUOUS_INTERACT and self.continuous_sub_state != self.CONTINUOUS_END:
            self.pending_exit = True
            self.end_continuous_interact()
            return
        # 立即停止自主移动
        if self.is_moving:
            self.move_timer.stop()
            self.is_moving = False
        # 切换退出状态（开机状态直接终止动画进入退出）
        self.anim_timer.stop()
        self.current_state = self.STATE_EXIT
        self.current_frame = 0
        self.is_play_once = True
        if not self.load_frames(self.config["assets"]["exit_path"]):
            # 无退出动画 → 直接退程序
            print("退出素材缺失，直接退出程序")
            QApplication.instance().quit()
            return
        self.fps = self.config["animation"]["standby_fps"]
        self.anim_timer.setInterval(int(1000 / self.fps))
        self.anim_timer.start()
        self.update()

    # ===================== 显示互动窗口 =====================
    def show_interact_window(self):
        if self.current_state in (self.STATE_BOOT, self.STATE_EXIT):
            return
        self.interact_window.show_at_pet()

    def _update_bubble_position(self):
        """气泡显示在角色顶部居中；上方越界时翻到下方；最后夹紧到屏幕。"""
        bubble_w = self.chat_bubble.width()
        bubble_h = self.chat_bubble.height()

        ideal_x = self.x() + (self.width() - bubble_w) // 2
        ideal_y = self.y() - bubble_h - 5

        # 上方越界 → 翻到下方
        screen = _screen_of_widget(self)
        geo = screen.availableGeometry()
        if ideal_y < geo.top():
            ideal_y = self.y() + self.height() + 5

        rect = _fit_rect_to_screen(QRect(ideal_x, ideal_y, bubble_w, bubble_h), screen)
        self.chat_bubble.move(rect.left(), rect.top())

    def show_bubble_text(self, text):
        """统一气泡显示入口，自动校准位置"""
        self._update_bubble_position()
        self.chat_bubble.show_text_animated(text)

    def _update_chat_input_position(self):
        """输入栏跟随角色底部右对齐；下方越界翻到上方；最后夹紧。"""
        in_w = self.chat_input.width()
        in_h = self.chat_input.height()

        ideal_x = self.x() + self.width() - in_w
        ideal_y = self.y() + self.height() + 5

        screen = _screen_of_widget(self)
        geo = screen.availableGeometry()
        if ideal_y + in_h > geo.bottom():
            ideal_y = self.y() - in_h - 5

        rect = _fit_rect_to_screen(QRect(ideal_x, ideal_y, in_w, in_h), screen)
        self.chat_input.move(rect.left(), rect.top())

    def open_chat(self):
        """打开对话模式：立即打断自动行为 → 显示输入栏 → 切入对话状态"""
        # 1. 统一记录用户操作时间
        self.touch_user_activity()

        # 2. 立即打断自动行为（不播放退场动画，保证即时响应）
        #    长时间待机无需在此手动处理，随后 switch_state 会停止 anim_timer 并替换帧
        if self.is_moving:
            self.move_timer.stop()
            self.is_moving = False

        # 3. 打开输入栏
        self.is_chat_open = True
        self._update_chat_input_position()
        self.chat_input.show()
        self.chat_input.raise_()
        self.chat_input.focus_input()

        # 4. 切换为对话动画（互动中/开机/退出/瞬时互动 时不抢占动画）
        if self.can_interrupt(self.current_state, self.ACT_OPEN_CHAT):
            self.switch_state(self.STATE_TALK)

    def close_chat(self):
        """关闭对话模式，按当前状态决定是否切回待机"""
        self.is_chat_open = False
        self.chat_input.hide()
        self.chat_bubble.hide()
        
        # 中断正在进行的AI请求
        if self.ai_worker and self.ai_worker.isRunning():
            self.ai_worker.stop()
            self.ai_worker.wait(1500)   # 最多等 1.5 秒
        self.ai_worker = None
        
        # 仅当当前是纯对话状态时，才切回待机
        if self.current_state == self.STATE_TALK:
            self.switch_state(self.STATE_STANDBY)
        
        # 重置操作时间，重启自动行为计时
        self.touch_user_activity()

    def show_advanced_chat(self):
        """打开高级对话窗口（居中弹出）"""
        self.touch_user_activity()
        self.advanced_window.show_window()

    def show_behavior_setting(self):
        """打开行为设置窗口（居中弹出）"""
        self.touch_user_activity()
        self.behavior_setting_window.show_window()

    def on_user_send_message(self, text):
        """用户发送消息：禁用两端输入，组装提示词，启动后台AI请求"""
        self.touch_user_activity()
        self.chat_input.set_input_enabled(False)
        # 高级窗口（若已创建）也禁用输入
        if hasattr(self, "advanced_window"):
            self.advanced_window.set_input_enabled(False)
            # ★ 清除上一次的错误提示
            self.advanced_window.clear_realtime_error()

        # 1. 加入对话历史并实时保存到文件（带时间戳）
        now_ts = time.time()
        self.chat_history.append({
            "role": "user",
            "content": text,
            "ts": now_ts,
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts)),
        })
        self._is_saving_history = True
        self.history_manager.save_current_history(self.chat_history)
        QTimer.singleShot(600, lambda: setattr(self, '_is_saving_history', False))
        # ★ 通知高级窗口刷新列表
        self.chat_history_updated.emit()

        # ★ 显示 AI 回复占位气泡（流式实时更新）
        if hasattr(self, "advanced_window"):
            self.advanced_window.begin_ai_streaming(mode="realtime")

        # 2. 获取持续互动的叠加提示词
        extra_prompt = ""
        if self.current_state == self.STATE_CONTINUOUS_INTERACT and self.current_interact_config:
            extra_prompt = self.current_interact_config.get("prompt", "")

        # 3. 用提示词引擎组装完整消息
        messages = self.prompt_engine.build_realtime_messages(
            self.chat_history, extra_prompt
        )

        # ========== 调试输出 ==========
        print("\n" + "="*60)
        print("【调试】本次发送的完整提示词结构：")
        for idx, msg in enumerate(messages):
            preview = msg["content"][:120].replace("\n", " ")
            suffix = "..." if len(msg["content"]) > 120 else ""
            print(f"  [{msg['role']}] {preview}{suffix}")
        print("="*60)
        print("【状态】AI请求已发送，等待模型回复...\n")

        # 4. 创建并启动后台线程
        self.ai_worker = AIRequestWorker(
            self.config["ai_system"]["api_config"],
            self.config["ai_system"]["model_params"],
            messages
        )
        self.ai_worker.reply_chunk_received.connect(self.on_ai_chunk_received)
        self.ai_worker.reply_received.connect(self.on_ai_reply_success)
        self.ai_worker.request_error.connect(self.on_ai_request_error)
        self.ai_worker.request_finished.connect(self.on_ai_request_finished)
        self._current_ai_text = ""
        self.chat_bubble.show_placeholder("…")
        self.ai_worker.start()

    def on_ai_chunk_received(self, chunk):
        """流式收到正文片段：累积并实时更新到高级窗口气泡"""
        self._current_ai_text += chunk
        # ★ 实时显示到高级窗口占位气泡
        if hasattr(self, "advanced_window"):
            self.advanced_window.update_ai_streaming(self._current_ai_text, self.config)

    def on_ai_reply_success(self, reply_text):
        """AI回复成功：过滤后显示气泡、存入历史（带时间戳）、实时落盘"""
        filtered_text = filter_ai_output(reply_text, self.config)

        # 过滤后为空时按配置回落，避免气泡空白
        filter_cfg = self.config["ai_system"].get("output_filter", {})
        if (not filtered_text
                and reply_text.strip()
                and filter_cfg.get("fallback_to_raw_if_empty", True)):
            filtered_text = reply_text.strip()
            print("【提示】过滤后为空，已回落显示原文。"
                  "若原文含思考内容，请检查 config.json → ai_system → output_filter → rules")

        if filtered_text:
            now_ts = time.time()
            self.chat_history.append({
                "role": "assistant",
                "content": filtered_text,
                "ts": now_ts,
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts)),
            })
            self._is_saving_history = True
            self.history_manager.save_current_history(self.chat_history)
            QTimer.singleShot(600, lambda: setattr(self, '_is_saving_history', False))
            # ★ 结束流式（移除占位气泡），再刷新列表加入正式消息
            if hasattr(self, "advanced_window"):
                self.advanced_window.end_ai_streaming()
            self.show_bubble_text(filtered_text)
            # ★ 通知高级窗口刷新列表
            self.chat_history_updated.emit()
            print(f"【状态】AI回复完成，回复长度：{len(filtered_text)} 字\n")
        elif reply_text.strip():
            # 过滤后为空，且 fallback_to_raw_if_empty=False → 提示用户，别静默吞
            print("【警告】AI 返回被完全过滤，且未配置回落显示原文")
            error_tip = self.config["ai_system"]["prompt_config"].get(
                "error_tip", "（无回复）")
            self.show_bubble_text(error_tip)

    def on_ai_request_error(self, error_type, friendly_hint, detail):
        """请求出错：气泡显示角色台词；高级窗口显示分类提示；控制台打印详情"""
        # 结束流式（移除占位气泡）
        if hasattr(self, "advanced_window"):
            self.advanced_window.end_ai_streaming()
            self.advanced_window.show_realtime_error(friendly_hint)
            self.advanced_window._refresh_realtime_messages(scroll_to_bottom=False)

        # 桌面气泡：角色化台词（保持沉浸感）
        error_tip = self.config["ai_system"]["prompt_config"]["error_tip"]
        self.show_bubble_text(error_tip)

        # 控制台：分类信息 + 详细原因
        print(f"【状态】AI请求出错 [{error_type}]：{detail}\n")

    def on_ai_request_finished(self):
        """请求结束：恢复两端输入框可用"""
        self.chat_input.set_input_enabled(True)
        if hasattr(self, "advanced_window"):
            self.advanced_window.set_input_enabled(True)

    # ===================== 故事模式（独立 AI 请求链路） =====================
    def send_story_message(self, text):
        """故事模式发消息：独立 worker，独立回调，不弹桌面气泡。"""
        self.touch_user_activity()
        # 全局互斥：禁用两端所有输入
        self.chat_input.set_input_enabled(False)
        if hasattr(self, "advanced_window"):
            self.advanced_window.set_input_enabled(False)
            # ★ 清除上一次的错误提示
            self.advanced_window.clear_story_error()
        # 故事模式明确隐藏气泡
        self.chat_bubble.hide()

        # 1. 加入故事历史
        now_ts = time.time()
        self.story_history.append({
            "role": "user",
            "content": text,
            "ts": now_ts,
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts)),
        })
        self._is_saving_history = True
        self.history_manager.save_active_history(self.story_history, mode="story")
        QTimer.singleShot(600, lambda: setattr(self, '_is_saving_history', False))
        # 通知高级窗口刷新故事消息区 + 显示占位气泡
        if hasattr(self, "advanced_window"):
            self.advanced_window.on_story_history_updated()
            self.advanced_window.begin_ai_streaming(mode="story")

        # 2. 组装 story messages
        messages = self.prompt_engine.build_story_messages(self.story_history)

        print("\n" + "="*60)
        print("【故事模式】本次发送的提示词结构：")
        for idx, msg in enumerate(messages):
            preview = msg["content"][:120].replace("\n", " ")
            suffix = "..." if len(msg["content"]) > 120 else ""
            print(f"  [{msg['role']}] {preview}{suffix}")
        print("="*60)
        print("【故事模式】请求已发送，等待模型回复...\n")

        # 3. worker（不需要流式片段，一次性 append）
        # 故事模式使用独立的 max_tokens 覆盖
        story_params = dict(self.config["ai_system"]["model_params"])
        story_params["max_tokens"] = int(story_params.get(
            "story_max_tokens",
            story_params.get("max_tokens", 1000)
        ))
        self.story_worker = AIRequestWorker(
            self.config["ai_system"]["api_config"],
            story_params,
            messages
        )
        self.story_worker.reply_chunk_received.connect(self.on_story_chunk_received)
        self.story_worker.reply_received.connect(self.on_story_reply_success)
        self.story_worker.request_error.connect(self.on_story_request_error)
        self.story_worker.request_finished.connect(self.on_story_request_finished)
        self.story_worker.start()

    def on_story_chunk_received(self, chunk):
        """故事模式流式收到片段，实时更新高级窗口"""
        if not hasattr(self, "story_chunks_buffer"):
            self.story_chunks_buffer = ""
        self.story_chunks_buffer += chunk
        if hasattr(self, "advanced_window"):
            self.advanced_window.update_ai_streaming(self.story_chunks_buffer, self.config)

    def on_story_reply_success(self, reply_text):
        """故事模式 AI 回复成功：过滤后追加到 story_history，不显示桌面气泡。"""
        self.story_chunks_buffer = ""   # 清空缓存
        filtered_text = filter_ai_output(reply_text, self.config)
        filter_cfg = self.config["ai_system"].get("output_filter", {})
        if (not filtered_text
                and reply_text.strip()
                and filter_cfg.get("fallback_to_raw_if_empty", True)):
            filtered_text = reply_text.strip()

        if filtered_text:
            now_ts = time.time()
            self.story_history.append({
                "role": "assistant",
                "content": filtered_text,
                "ts": now_ts,
                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts)),
            })
            self._is_saving_history = True
            self.history_manager.save_active_history(self.story_history, mode="story")
            QTimer.singleShot(600, lambda: setattr(self, '_is_saving_history', False))
            # ★ 结束流式（移除占位气泡），再刷新故事消息区
            if hasattr(self, "advanced_window"):
                self.advanced_window.end_ai_streaming()
                self.advanced_window.on_story_history_updated()
            print(f"【故事模式】AI回复完成，回复长度：{len(filtered_text)} 字\n")

    def on_story_request_error(self, error_type, friendly_hint, detail):
        """故事模式请求失败：高级窗口显示提示条，弹窗显示友好提示 + 详情。
        不使用角色报错语（角色台词仅用于实时对话的桌面气泡）。
        """
        if hasattr(self, "advanced_window"):
            self.advanced_window.end_ai_streaming()
            self.advanced_window.show_story_error(friendly_hint)
            self.advanced_window.on_story_history_updated()

        print(f"【故事模式】AI请求出错 [{error_type}]：{detail}\n")

        parent = self.advanced_window if hasattr(self, "advanced_window") else None
        QMessageBox.warning(
            parent, "故事模式请求失败",
            f"{friendly_hint}\n\n详细原因（已打印到控制台）：\n{detail[:300]}"
        )

    def on_story_request_finished(self):
        """故事模式请求结束：恢复两端输入。"""
        self.chat_input.set_input_enabled(True)
        if hasattr(self, "advanced_window"):
            self.advanced_window.set_input_enabled(True)

    # ===================== 切换下一帧 =====================
    def next_frame(self):
        if len(self.frame_list) == 0:
            return
        
        # 处理开机状态：播完自动进入待机
        if self.current_state == self.STATE_BOOT:
            if self.is_play_once and self.current_frame == len(self.frame_list) - 1:
                self.switch_state(self.STATE_STANDBY)
                return
            
        # 处理长时间待机的子状态切换
        if self.current_state == self.STATE_LONG_IDLE:
            if self.is_play_once and self.current_frame == len(self.frame_list) - 1:
                if self.long_idle_sub_state == self.LONG_IDLE_START:
                    # 开场播完 → 进入循环
                    self.long_idle_sub_state = self.LONG_IDLE_LOOP
                    self.load_frames(self.config["assets"]["long_idle_loop_path"])
                    self.current_frame = 0
                    self.is_play_once = False
                elif self.long_idle_sub_state == self.LONG_IDLE_END:
                    # 退场播完 → 回到默认待机
                    self.switch_state(self.STATE_STANDBY)
                return
            
        # 处理持续互动的子状态切换
        if self.current_state == self.STATE_CONTINUOUS_INTERACT:
            if self.is_play_once and self.current_frame == len(self.frame_list) - 1:
                if self.continuous_sub_state == self.CONTINUOUS_START:
                    # 开场播完 → 进入循环
                    self.continuous_sub_state = self.CONTINUOUS_LOOP
                    loop_path = _p(os.path.join(self.current_interact_config["path"], "loop"))
                    self.load_frames(loop_path)
                    self.current_frame = 0
                    self.is_play_once = False
                elif self.continuous_sub_state == self.CONTINUOUS_END:
                    # 退场播完
                    self.current_interact_config = None
                    # 优先级：待退出 > 待播放互动 > 状态回落
                    if self.pending_exit:
                        self.pending_exit = False
                        self.start_exit()
                    elif self.pending_interact is not None:
                        next_action = self.pending_interact
                        self.pending_interact = None
                        self.play_interact(next_action)
                    else:
                        # 对话开启则回对话状态，否则回待机
                        if self.is_chat_open:
                            self.switch_state(self.STATE_TALK)
                        else:
                            self.switch_state(self.STATE_STANDBY)
                    return

        # 处理退出状态
        if self.current_state == self.STATE_EXIT:
            if self.is_play_once and self.current_frame == len(self.frame_list) - 1:
                QApplication.instance().quit()
                return
            
        # 普通单次播放：播完自动切回对应状态
        elif self.is_play_once and self.current_frame == len(self.frame_list) - 1:
            # 对话中触发的触摸/瞬时互动，播完回到对话状态
            if self.is_chat_open and self.current_state in [self.STATE_TOUCH, self.STATE_INSTANT_INTERACT]:
                self.switch_state(self.STATE_TALK)
            else:
                self.switch_state(self.STATE_STANDBY)
            return
        
        # 帧索引递增
        self.current_frame += 1
        if self.current_frame >= len(self.frame_list):
            self.current_frame = 0
        self.update()

    # ===================== 绘制当前帧 =====================
    def paintEvent(self, event):
        if len(self.frame_list) == 0:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.frame_list[self.current_frame])

    # ===================== 鼠标左键按下 =====================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            # 判断是否点在当前帧的透明区域
            if not self._is_opaque_at(pos):
                event.ignore()
                return
                
            self.touch_user_activity()
            if self.is_moving:
                self.move_timer.stop()
                self.is_moving = False
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.press_global_pos = event.globalPosition().toPoint()
            self.is_dragging = False
            event.accept()

    # ===================== 鼠标移动（拖拽窗口） =====================
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            move_distance = (event.globalPosition().toPoint() - self.press_global_pos).manhattanLength()
            if move_distance > self.DRAG_THRESHOLD and not self.is_dragging:
                self.is_dragging = True
                self.touch_user_activity()
                if self.can_interrupt(self.current_state, self.ACT_DRAG):
                    if self.is_moving:
                        self.move_timer.stop()
                        self.is_moving = False
                    self.switch_state(self.STATE_DRAG)
            self.move(event.globalPosition().toPoint() - self.drag_offset)   # 永远执行
            self._update_bubble_position()
            if self.is_chat_open:
                self._update_chat_input_position()
            event.accept()

    # ===================== 鼠标左键松开 =====================
    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # ① 拖拽收尾：不经过权限表，是拖拽自身的一部分
        if self.is_dragging:
            if self.current_state == self.STATE_DRAG:
                self.switch_state(self.STATE_STANDBY)
            self.is_dragging = False
            # ★ 拖拽结束后防抖保存位置（300ms 无新拖拽才落盘）
            if hasattr(self, "_state_save_timer"):
                self._state_save_timer.start(300)
            event.accept()
            return

        # 非拖拽的普通点击，校验掩码
        pos = event.position().toPoint()
        if not self._is_opaque_at(pos):
            event.ignore()
            return

        # ② 权限表过滤：不允许点击的状态直接吞掉
        if not self.can_interrupt(self.current_state, self.ACT_LEFT_CLICK):
            event.accept()
            return

        # ③ 按当前状态执行
        if self.current_state == self.STATE_CONTINUOUS_INTERACT:
            if self.continuous_sub_state == self.CONTINUOUS_LOOP:
                self.end_continuous_interact()
                self.touch_user_activity()
        elif self.current_state == self.STATE_LONG_IDLE:
            self.interrupt_auto_behavior()
        elif self.current_state == self.STATE_STANDBY:
            click_pos = event.position().toPoint()
            special_path = self.check_special_touch(click_pos)
            self.play_touch_animation(special_path or self.config["assets"]["touch_normal_path"])
        elif self.current_state == self.STATE_MOVE:
            self.play_touch_animation(self.config["assets"]["touch_normal_path"])
        elif self.current_state == self.STATE_TALK:
            click_pos = event.position().toPoint()
            special_path = self.check_special_touch(click_pos)
            self.play_touch_animation(special_path or self.config["assets"]["touch_normal_path"])

        event.accept()

    # ===================== 鼠标右键菜单 =====================
    def contextMenuEvent(self, event):
        if self.current_state == self.STATE_EXIT:
            return

        # 右键校验掩码
        if not self._is_opaque_at(event.pos()):
            event.ignore()
            return
    
        self.touch_user_activity()
        if self.can_interrupt(self.current_state, self.ACT_RIGHT_MENU):
            self.interrupt_auto_behavior()
        self.right_menu.show_at_pet()   # 弹出菜单永远执行
        event.accept()

    # ===================== 全向随机移动 =====================
    def start_random_move(self):
        speed = self.config["auto_behavior"]["move_speed"]
        dir_x = random.choice([-1, 1])
        dir_y = random.choice([-1, 1])
        
        self.move_speed_x = dir_x * speed
        self.move_speed_y = dir_y * speed
        self.move_direction = "right" if dir_x > 0 else "left"
        
        self.switch_state(self.STATE_MOVE)
        self.is_moving = True
        self.move_timer.start(16)
        move_duration = int(self.config["auto_behavior"]["move_duration_seconds"] * 1000)
        QTimer.singleShot(move_duration, self.stop_move)

    # ===================== 全向位置更新 =====================
    def update_move_position(self):
        if not self.is_moving:
            return

        # ★ 用宠物当前所在屏幕的可用区域计算边界（而非写死主屏）
        geo = _screen_of_widget(self).availableGeometry()
        left = geo.left()
        top = geo.top()
        right_exclusive = geo.left() + geo.width()     # 右边界（不含）
        bottom_exclusive = geo.top() + geo.height()    # 下边界（不含）

        current_x = self.x()
        current_y = self.y()

        new_x = current_x + self.move_speed_x
        if new_x < left:
            new_x = left
            self.move_speed_x *= -1
            self.move_direction = "right"
            self.load_frames(self.config["assets"]["move_right_path"])
            self.current_frame = 0
        elif new_x + self.width() > right_exclusive:
            new_x = right_exclusive - self.width()
            self.move_speed_x *= -1
            self.move_direction = "left"
            self.load_frames(self.config["assets"]["move_left_path"])
            self.current_frame = 0

        new_y = current_y + self.move_speed_y
        if new_y < top:
            new_y = top
            self.move_speed_y *= -1
        elif new_y + self.height() > bottom_exclusive:
            new_y = bottom_exclusive - self.height()
            self.move_speed_y *= -1

        self.move(new_x, new_y)
        self._update_bubble_position()
        if self.is_chat_open:
            self._update_chat_input_position()

    # ===================== 停止移动 =====================
    def stop_move(self):
        if self.is_moving:
            self.move_timer.stop()
            self.is_moving = False
        if self.current_state == self.STATE_MOVE:
            self.switch_state(self.STATE_STANDBY)

    # ===================== 自动行为检测 =====================
    def check_auto_behavior(self):
        # 新增：菜单/弹窗打开时，暂停所有自动行为检测
        if self.right_menu.isVisible():
            return
        # 对话开启时暂停所有自动行为
        if self.is_chat_open:
            return
        # 兼容后续互动窗口/设置窗口，没创建该窗口时自动跳过判断
        if hasattr(self, "interact_window") and self.interact_window.isVisible():
            return
        if hasattr(self, "behavior_setting_window") and self.behavior_setting_window.isVisible():
            return
        if hasattr(self, "advanced_window") and self.advanced_window.isVisible():
            return
        
        if not self.can_interrupt(self.current_state, self.ACT_TIMER):
            return
        idle_time = time.time() - self.last_operation_time
        
        long_idle_trigger = self.config["auto_behavior"]["long_idle_trigger_seconds"]
        if idle_time >= long_idle_trigger and self.current_state != self.STATE_LONG_IDLE:
            self.enter_long_idle()
            return
        
        move_trigger = self.config["auto_behavior"]["move_trigger_seconds"]
        if idle_time >= move_trigger and self.current_state == self.STATE_STANDBY:
            if random.random() < self.config["auto_behavior"]["move_probability"]:
                self.start_random_move()

    # ===================== 进入长时间待机 =====================
    def enter_long_idle(self):
        if self.is_moving:
            self.move_timer.stop()
            self.is_moving = False
        
        # 先加载素材，避免闪一下上一状态的画面
        self.fps = self.config["animation"]["long_idle_fps"]
        if not self.load_frames(_p(self.config["assets"]["long_idle_start_path"])):
            print("长待机开场素材缺失，回落到默认待机")
            self.switch_state(self.STATE_STANDBY)
            return

        self.switch_state(self.STATE_LONG_IDLE)
        self.long_idle_sub_state = self.LONG_IDLE_START
        self.current_frame = 0
        self.is_play_once = True

if __name__ == "__main__":
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    # 加载托盘/任务栏共用图标
    icon_candidates = [_p("data/icon.ico"), _p("assets/desktop_pet.ico"), _p("assets/icon.ico"), _p("assets/tray.ico")]
    for icon_path in icon_candidates:
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
            print(f"✅ 已加载窗口图标：{icon_path}")
            break
    # 关键修复：关闭任意窗口不退出程序；退出由托盘「退出」按钮触发
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())