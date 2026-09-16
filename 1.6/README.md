# 轻量级桌面日程管理软件（v1.6.0）

一个开箱即用的 Windows 桌面日程管理工具，**单文件 .exe**，双击即可运行，
无需安装 Python 或任何运行环境。

- 技术栈：Python 3 + tkinter + Pillow + matplotlib（LaTeX 渲染）+ tkcalendar（日历）
- 数据存储：本地 JSON，统一存放于 `<程序目录>\data\` 子文件夹；外部工具 exe 放 `tools\`
- 目标系统：Windows 10 / 11；应用自带图标（`256x256.ico`）
- 体积上限：exe + 依赖 **< 100MB**（当前约 48MB）

**v1.6.0 变更**：
- **模块化**：`schedule_app.py` 拆为 `schedapp/` 包（paths / model / winapi / render_md · render_latex / tabs / dialogs / app）
- **工具功能**：`tools/` 文件夹放外部 exe 或 **.lnk 快捷方式**，「工具」页一键启动，可选**以管理员身份启动**
- **便签 IDE**：`data/notes/` 分类（子文件夹，空分类也显示）+ 多便签 + 代码行标 + 帮助键
- **日历**：tkcalendar 月历，**周期日程与事件按起止区间逐日展开标记**，点选查看当日
- **Markdown 渲染**：标题/粗体/斜体/划线/行内代码/代码块/列表 → tk.Text tag
- **LaTeX 渲染**：`$...$` 悬停弹出 matplotlib 公式图；**渲染失败会弹窗提示原因**
- 事件截止偏移分钟（起始 12:00 + 截止 150 → 14:30）；日程模板列表（DIY）；快捷时间可 DIY
  且作用于光标所在字段；添加/子日程对话框自动适配大小（确认键不再被遮挡）
- **启动即提权**：双击启动自动以管理员权限运行（UAC，可用环境变量 `DSH_SCHED_SKIP_ELEVATE=1` 跳过）
- **打包附带快捷方式**：`dist\日程管理.lnk`

---

## 一、使用说明

### 主界面：「今日 / 进行中」
添加日程（标题/备注/开始/截止/周期；快捷时间；模板）、完成/作废/修改/删除、
🚩标记/📌置顶、子日程、详情双击。红行=已过期、黄行=24h 内到期、剩余时间列实时刷新。

### 历史记录
三类（已完成/作废/过期）+ 类别/日期（含30天以上）筛选 + 关键词搜索 +
**📋 复制为模板**（修改日期后保存为新常规日程）+ 导出 CSV。

### 便签（类 IDE）
- 左侧：分类（子文件夹）+ 笔记（.txt）树；「＋笔记」「＋分类」「删除」「刷新」
- 右侧：行号 + 编辑器；「MD 渲染」开关、Σ 符号、📋 句子、❓ 帮助
- **Markdown**：`# 标题`、`**粗体**`、`*斜体*`、`~~划线~~`、`` `行内代码` ``、
  ` ```代码块``` `、`- / 1.` 列表
- **LaTeX**：输入 `$x^2$`、`$\frac{a}{b}$` 等，鼠标悬停弹出公式图（matplotlib）
- 「📂 打开文件」（.txt/.md/.py）、「🏠 默认」返回默认便签、关闭自动保存

### 日历
tkcalendar 月历页：有日程/历史记录的日期以颜色标记（青=进行中、绿=完成、紫=作废、红=过期），
点选日期在右侧列出当日全部日程。

### 工具
`<程序目录>\tools\` 下的 exe 会出现在「工具」页，选中后「▶ 启动」，可重新扫描/打开文件夹。

### 符号小窗 & 句子粘贴板（全局热键）
默认 Ctrl+Shift+G（符号）/ Ctrl+Shift+S（句子），在其他软件中也能唤起并直接输入光标处；
设置中可 DIY 热键与符号列表。

### 画板
24 色 / 橡皮（打洞）/ 粗细 / 清空 / 存 PNG / 打开图片作底图 / 白板。

### 设置中心（⚙）
深色模式、半透明（0.7~1.0，背景图在主窗口后方完整不透明透出）、背景图片、符号/句子热键与符号列表、
开机自启动（失败自动 UAC 提权，写 HKCU+HKLM）、托盘待机、导出 CSV、打开数据文件夹。

### 添加日程增强
- **模板**：顶部模板下拉直接套用；「💾 存为模板」「🗑 删模板」（存于 `data/templates.json`）
- **快捷时间 DIY**：「管理快捷时间」可增删条目（存于 `data/quicktimes.json`）；
  快捷时间作用于**光标所在字段**（开始或截止）
- **事件偏移分钟**：设了开始时间后，截止栏填纯数字（如 `150`）= 开始后 150 分钟

---

## 二、数据文件位置

| 路径 | 内容 |
|---|---|
| `<程序目录>\data\` | schedule.json / settings.json / notes\（便签 IDE）/ symbols.json / snippets.json / templates.json / quicktimes.json / background.png / latex_cache\ |
| `<程序目录>\tools\` | 外部工具 exe（工具页调用） |
| `256x256.ico` | 应用图标（打包附带） |

- 首次运行自动创建 `data\`；旧版散落文件自动迁移；`--data-dir DIR` 可指定其它目录
- 关闭程序后可直接编辑 JSON；损坏自动备份 `.bak`；旧版数据自动补齐新字段

---

## 三、如何从源码运行

```bash
pip install pillow matplotlib tkcalendar
python schedule_app.py                 # 正常启动
python schedule_app.py --data-dir DIR  # 便携模式
python schedule_app.py --selftest      # 逻辑自测（10 组）
python schedule_app.py --smoke         # GUI 冒烟 + 托盘/热键测试
```

---

## 四、如何自己打包 .exe

```bash
pip install pyinstaller pillow matplotlib tkcalendar
pyinstaller --onefile --windowed --name 日程管理 --icon 256x256.ico \
  --add-data "256x256.ico;." schedule_app.py
```

> miniforge/conda 的 Python 需附带 tcl/tk 运行时（见 `日程管理.spec`）：
> `--add-binary "<conda>\Library\bin\tcl86t.dll;."`、`tk86t.dll`，
> `--add-data "<conda>\Library\lib\tcl8.6;tcl"`、`tk8.6;tk`。

产物：`dist\日程管理.exe`（约 48 MB，上限 100MB 以内）。

---

## 五、验收对照

| 验收项 | 结果 |
|---|---|
| 模块化拆分（schedapp 包） | ✅ |
| 工具页 / 便签 IDE(分类+行标+帮助) / 日历 / MD 渲染 / LaTeX 悬停 / 偏移分钟 / 模板 / 快捷时间DIY | ✅ v1.6.0 |
| 背景缩放置顶修复 / 全局输入送达 / 前台切换修复 | ✅ v1.6.0 |
| exe + 依赖 < 100MB | ✅ 约 48 MB |
