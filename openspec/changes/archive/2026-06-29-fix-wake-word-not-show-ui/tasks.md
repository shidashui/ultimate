# Tasks: fix-wake-word-not-show-ui

## Task 1: 修复 ws.rs 中 wake 事件窗口操作

- [x] 将 `handle.get_window("main").map(|w| w.show())` 改为 `if let Some(window)` + 显式 `window.show()` 并检查结果
- [x] 相同处理 `set_focus()`
- [x] show/set_focus 失败时输出 `eprintln!` 错误日志

## 验证标准

- [x] `cargo build` 编译通过（ws.rs 改动）
- [x] 代码审查确认 `.map()` 改为显式 `if let Some` + 错误检查
