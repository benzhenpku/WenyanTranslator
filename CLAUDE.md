# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概况

WenyanTranslator（文言发信助手）：Windows 桌面 Tkinter 工具，调用 OpenAI 兼容的 `/chat/completions` 接口把现代汉语译为文言文；可选在微信/QQ 中选中文字后按全局快捷键 `Ctrl+Alt+M` 一键替换。仅用 Python 标准库（无需 pip 安装），目标环境 Windows 10+、Python 3.10+。这是课程作业项目，`README.md` 本身就是提交报告（含测试结果、AI 使用声明），`README.html` 是它的网页版——改功能时要同步更新 README 中的描述、目录树和测试覆盖表，并重新生成 `README.html`：保留其前 99 行手写模板（样式、打印提示、作者信息框），正文由 pandoc 从 README 的"## 一、"开始转换：

```bash
sed -n '/^## 一、/,$p' README.md | pandoc -f gfm -t html5 --no-highlight --wrap=none -o body.html
{ sed -n 1,99p README.html; cat body.html; printf '</body>\n</html>\n'; } > README.new.html && mv README.new.html README.html
```

截图 `<img>` 需手动补回 `style="max-width:100%;border:1px solid #ddd;border-radius:4px;"`。

## 常用命令

```powershell
# 运行（项目根目录）；也可双击 start.bat
pythonw wenyan_translator.pyw
# 需要看报错时用 python 而非 pythonw
python wenyan_translator.pyw

# 全部测试
python -m unittest discover -s tests -v
# 单个测试
python -m unittest tests.test_wenyan_translator.TestRequestTranslation.test_正常请求返回译文 -v
```

测试只导入 `src.core` 和 `src.config_store`，不依赖 tkinter，Linux 上也能跑；但这也意味着测试**覆盖不到 `gui.py`**，改 GUI 后至少要用 `python -c "import ast; ast.parse(open('src/gui.py', encoding='utf-8').read())"` 检查语法（曾因字符串里混入英文双引号导致程序无法启动而测试仍全部通过）。界面文案中的引号用中文引号 `“”`。没有配置 lint/格式化工具。

## 架构

入口 `wenyan_translator.pyw` 把项目根目录加入 `sys.path`，以 `src.xxx` 包形式导入（模块之间也用 `from src.core import ...`），并负责关闭窗口时保存配置。

- **`src/core.py`**：不依赖 GUI。`request_translation` 拼装 `SYSTEM_PROMPT` + 文风说明（`STYLES` 字典，键即界面下拉框选项，测试断言恰好四种）+ 补充要求，用 `urllib` POST，固定 `temperature=0.3`、`reasoning_effort="high"`（README 有实测依据，勿随意改）。所有网络/HTTP/解析/空结果错误统一转换为 `TranslationError`。
- **`src/config_store.py`**：`config.json` 与 `hotkey.log` 位于**项目根目录**（`APP_DIR` = `src` 的父目录）。`load_config` 只接受 `_DEFAULT_CONFIG` 中已有的键，新增配置项必须先加到默认值里。`load_ccswitch_provider` 启动时若存在 `~/.cc-switch/cc-switch.db`，会读取当前 Codex 服务商的地址/模型/Key 并覆盖界面设置。
- **`src/win32_utils.py`**：Win32 结构体只在 `if sys.platform == "win32":` 下定义，因此 `gui.py` 在非 Windows 上无法导入。
- **`src/gui.py`（`WenyanTranslatorApp`）**：HTTP 请求一律放在 daemon 线程中，完成后用 `root.after(0, 回调, result, error)` 交回主线程更新界面——新增耗时操作沿用此模式，不要在后台线程直接操作 Tk 控件。

### 快捷替换流程（跨多个方法、靠 `root.after` 定时串联）

1. `poll_foreground_window` 每 400ms 把最近一个非本程序的前台窗口记到 `last_chat_window`。
2. 后台线程 `hotkey_message_loop` 用 `RegisterHotKey` 注册 `Ctrl+Alt+M`，收到 `WM_HOTKEY` 后 `root.after` 调 `replace_selected_from_chat`（右键菜单"自动替换"走同一入口）。
3. `remember_selected_window`（备份剪贴板、`AttachThreadInput`）→ `activate_window` → `copy_selected_text`（清空剪贴板 + 模拟 Ctrl+C）→ 500ms 后 `read_selected_text` → 后台翻译 → `quick_translation_finished_auto` → `paste_into_selected_window`（Ctrl+A、Ctrl+V）→ `finish_replacement`（解除线程附加、恢复原剪贴板）。
4. `quick_running` 防止重入，每个失败分支都要复位它以及 `selected_*` 状态和剪贴板。各步之间的毫秒延时是为兼容微信/QQ 调出来的。

另有"自动翻译剪贴板"模式：`toggle_clipboard_mode` → `poll_clipboard` 每 600ms 检测剪贴板变化 → `quick_translate`。

## 注意

- `config.json`、`*.log`、`*.lnk` 已 gitignore；`config.json` 含 API Key，不要提交。`examples/config.example.json` 是不含 Key 的字段示例。
- `start.bat` 优先使用作者本机的 `D:\python\pythonw.exe`，找不到时回退到 PATH 中的 `pythonw.exe`。
