# Design: 修复 colored_prompt()

在 `print_tools.py` 中新增 `_ansi_render()` 辅助函数，用临时 Console 将 rich markup 渲染为 ANSI 字符串。

`colored_prompt()` 改为调用 `_ansi_render("[primary]You > [/primary]")`。
