# 桌面宠物制作器 (Desktop Pet Maker)
一款面向零基础用户的 GIF 制式桌面宠物可视化制作工具。
通过可视化界面导入 GIF、配置参数、框选交互区域，即可一键封装导出独立可运行的 Windows 桌面宠物。

## ✨ 核心特性
- **纯 PyQt6 开发**：无复杂渲染库依赖，轻量稳定。
- **GIF 拆帧与掩码**：自动提取序列帧，并生成 1/4 尺寸的逐帧掩码，实现稳定的点击穿透判定。
- **一键封装**：基于预编译的运行时模板，生成免安装的成品 `.exe`。
- **AI 对话支持**：支持接入大语言模型接口，实现流式气泡对话与独立的故事模式。

> 详细功能说明请查阅 Releases 内的说明书 `Manual.pdf`。
> 前往下载入口：https://github.com/ShinyKairos/dpetmaker/releases

> ⚠️ 重要提示
本仓库仅包含程序源码。如需体验完整动画演示效果，请前往 Releases 下载 `resources.zip`，解压后将里面的 `assets` 和 `mask` 文件夹放到 `pet_runtime.py` 同级目录，重启桌宠程序即可加载动画与掩码；缺少动画素材时，桌宠仅托盘运行，属于预设兜底逻辑，并非故障。
`resources.zip` 内的 `maker_test` 目录，存放用于测试制作器流程的 GIF/PNG 素材，仅作上手验证使用，不是程序运行必需文件。
部分素材来源于网络，若存在侵权，请联系作者删除。素材不跟随MIT开源，仅作演示试用，禁止商用。

## 🚀 快速开始
### 1. 环境准备
请使用 Python **3.10 / 3.11**，在项目根目录执行以下命令创建虚拟环境并安装依赖：
```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 启动制作器（开发模式）
```bash
python editor/main.py
```

### 3. 启动桌宠运行时（开发模式）
```bash
python pet_runtime.py
```

## 📦 打包与分发
> 提示：如果已经准备好 `runtime_template`，可跳过第一步。

1. **打包桌宠运行时**
```bash
pyinstaller --noconsole --onedir --name pet_runtime pet_runtime.py
```
打包完成后，将输出目录 `dist/pet_runtime/` 完整复制到 `editor/data/runtime_template/`。

2. **打包制作器本体**
```bash
pyinstaller --noconsole --onedir --name dpetmaker editor/main.py
```
打包完成后：
- 将 `editor/data/` 复制至 `dist/dpetmaker/`
- 在 `dist/dpetmaker/` 手动新建 `save/` 文件夹
完成后该目录即可作为分发包。

## 📁 项目目录结构
```
├─ pet_runtime.py                 # 桌宠运行时代码
├─ config.json                    # 桌宠全局配置文件
└─ editor/                        # 桌宠制作器源码
   ├─ core/                       # 业务核心逻辑
   ├─ ui/                         # 界面代码
   └─ data/
       └─ runtime_template/       # 预编译运行时模板，用于一键封装
```

## 📄 开源协议
本项目基于 [MIT License](LICENSE) 开源。

## 🤝 贡献说明
- 本项目为个人业余、AI辅助开发作品，精力有限，不保证长期持续维护，
Bug 反馈、功能建议欢迎提交 Issue。
- 想要修改、新增功能：请 Fork 仓库，改动完成后提交 Pull Request。
所有符合协议、合理的改进都欢迎合并。
