## Context

Tauri 窗口的 `visible` 配置为 `false`（`tauri.conf.json:21`），初始隐藏。唤醒后通过 ws.rs 的 `wake` 事件分支调用 `window.show()` 和 `window.set_focus()` 弹出窗口。

当前代码使用 `.map(|w| w.show())` + `let _` 丢弃结果。Tauri 的 `show()` 和 `set_focus()` 返回 `Result<(), Error>`，若窗口已被销毁或线程上下文失效，错误被静默忽略，窗口不会弹出。

## Goals / Non-Goals

**Goals:**
- 唤醒时保证窗口 popup
- 窗口操作失败时输出明确日志

**Non-Goals:**
- 不改变窗口生命周期策略
- 不改变事件链路其它部分

## Decisions

| 决策 | 选择 | 理由 |
|------|------|------|
| 窗口操作方式 | `if let Some(window)` + 显式检查 `Result` | 替代 `map` 链式调用，错误可感知 |
| 错误处理 | `eprintln!` 输出到 stderr | Rust 端的标准日志方式，与已有 `println!` 风格一致 |

## Risks / Trade-offs

无显著风险。改动范围 ≤ 5 行。
