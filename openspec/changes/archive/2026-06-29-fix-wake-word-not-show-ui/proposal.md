## Why

语音唤醒词识别成功后，Tauri 窗口未弹出（保持隐藏），用户无法看见交互界面。事件链路完整（Python 端正确发出 `wake_event`，Rust ws.rs 收到后执行了 `handle.get_window("main").map(|w| w.show())`），但 `.map()` 返回的 `Result` 被 `let _` 静默丢弃，无法捕获 `show()`/`set_focus()` 可能因线程上下文发出的错误。

## What Changes

- 修改 `ui/src-tauri/src/ws.rs` 中 wake 事件处理：将 `.map(|w| ...)` 改为显式的 `if let Some(window)` + 错误日志记录
- 确保 `show()` 和 `set_focus()` 的返回结果被检查，失败时输出 error 日志

## Capabilities

### New Capabilities
<!-- 无新 capability -->

### Modified Capabilities
<!-- 无 spec 级需求变更 -->

## Impact

- `ui/src-tauri/src/ws.rs` — 仅修改 wake 分支的窗口操作逻辑（≤ 5 行）
