# Proposal: 修复 init_run() 中残留的裸 print()

## 问题

`cli/cli.py:61` 的 `print()` 是 beautify-cli-io 重构时遗漏的一行，未迁移到 `console.print()`，导致启动横幅后多一个无格式空行。

## 根因

beautify-cli-io 重构 `init_run()` 时，第 61 行 `print()` 未被替换为 `console.print()`。

## 修复

将 `print()` 改为 `console.print()`。
