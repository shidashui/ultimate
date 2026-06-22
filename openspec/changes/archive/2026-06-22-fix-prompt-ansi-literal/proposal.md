# Proposal: 修复 ANSI 转义码被字面显示

## 问题

prompt 显示为 `^[[1;36mYou > ^[[0m` — ANSI 转义码被当作普通字符输出。

## 根因

`_ansi_render()` 用 rich `Console.capture()` 生成 ANSI 字符串传给 `prompt_toolkit`，但 prompt_toolkit 3.x 不会自动解析裸 ANSI 字符串，需要通过 `FormattedText` / `HTML` / `ANSI` 包装。

## 修复

废弃 rich→ANSI 方式。`colored_prompt()` 改用 `prompt_toolkit.formatted_text.FormattedText` 原生样式。
