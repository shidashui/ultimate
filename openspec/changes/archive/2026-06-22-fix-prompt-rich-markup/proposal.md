# Proposal: 修复 colored_prompt() 返回 rich markup 而非 ANSI

## 问题

`utils/print_tools.py` 的 `colored_prompt()` 返回 `"[primary]You > [/primary]"`（rich markup），但 `prompt_toolkit.PromptSession.prompt()` 不认识 rich markup 语法。用户提示符显示为原始 `[primary]You > [/primary]` 而非着色文本。

## 根因

beautify-cli-io 重构时，`colored_prompt()` 从返回 ANSI 转义码改为返回 rich markup 字符串，但 prompt_toolkit 只接受纯文本或 ANSI 转义码，不解析 rich 语法。

## 修复

用 rich Console 将 markup 渲染成 ANSI 字符串后传给 prompt_toolkit。
