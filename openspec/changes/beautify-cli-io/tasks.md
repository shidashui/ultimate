# Tasks: 美化 CLI 输入输出

## 任务清单

### Task 1: 重构 print_tools.py — 迁移到 rich

- [x] **Step 1: 创建 rich Console 实例与统一 Theme**
  - 定义 Theme 映射（primary, success, warning, error, muted, accent, info）
  - 创建全局 `console` 实例
  - 移除旧 ANSI 常量（无外部引用，安全删除）

- [x] **Step 2: 重写所有输出函数**
  - 全部函数内部改用 rich markup 和 `console.print()`
  - `print_section()` → `console.print(Rule(...))`
  - `print_tool_info()` → rich Table
  - `print_context()` → 保留颜色条，用 rich style
  - `get_color()` → 返回 rich style 名称

- [x] **Step 3: 向后兼容验证**
  - agentd/ 4 个文件导入全部通过，无参数修改

### Task 2: 美化 AI 回复渲染

- [x] **Step 1: 在 cli.py 导入 rich.Markdown**
- [x] **Step 2: 修改 AI 回复输出**
  - 在 `handle_user_input()` 中用 `console.print(Markdown(reply))` 渲染
  - 先打印 "Assistant:" 标签，再渲染 Markdown 内容
- [x] **Step 3: 边界情况处理**
  - 空回复：`if reply:` 已有保护

### Task 3: 美化命令输出

- [x] **init_run()** — 升级启动横幅为 rich Panel
- [x] **/help** — 用 rich.Table 排版命令列表
- [x] **/list** — 用 rich.Table 排版会话列表
- [x] **/skills** — 用 rich.Table 排版技能列表
- [x] **/context** — 保留颜色进度条，输出改用 rich style
- [x] **/memory** — 用 Panel 包裹统计信息
- [x] **/bootstrap** — 用 rich.Table 排版文件列表
- [x] **/prompt** — 用 Panel 包裹系统提示词
- [x] **/soul** — 用 Rule + 格式化输出

### Task 4: 清理与验证

- [x] **Step 1: 确认无残留 ANSI 常量引用** — cli.py 不再直接使用旧常量
- [x] **Step 2: 构建验证** — `python -c "from cli.cli import Cli; print('Build OK')"` 通过
- [x] **Step 3: agentd/ 全量导入** — 所有模块导入成功
