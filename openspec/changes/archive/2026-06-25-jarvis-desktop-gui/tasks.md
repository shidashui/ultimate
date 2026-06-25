## 1. 项目脚手架与依赖

- [x] 1.1 创建 `ui/` 目录，初始化 Tauri + Vue3 + TypeScript 项目（Vite 构建）
- [x] 1.2 添加 Tauri Rust 依赖：`tokio-tungstenite`（WS 客户端）、`serde_json`
- [x] 1.3 添加 Vue3 前端依赖：无额外 UI 组件库（纯自绘 JARVIS 风格），仅保留 Vue3 + TypeScript + Vite
- [x] 1.4 配置 Tauri `tauri.conf.json`：frameless 窗口、窗口初始隐藏、最小尺寸 900x600
- [x] 1.5 配置 Vite 开发服务器端口和 Tauri 集成

## 2. Tauri Rust 窗口管理层

- [x] 2.1 实现 WindowManager：show() / hide() 方法，Rust 层控制窗口生命周期
- [x] 2.2 实现 fade-in 动画（Vue3 CSS Transition 实现，300ms）
- [x] 2.3 实现 fade-out 动画（Vue3 CSS Transition 实现，500ms）
- [x] 2.4 实现系统托盘图标（创建、显示自定义图标）
- [x] 2.5 实现托盘右键菜单：显示窗口、退出
- [x] 2.6 实现 frameless 窗口拖拽（定义拖拽区域，Vue3 配合 data-tauri-drag-region）
- [x] 2.7 实现空闲倒计时自动隐藏（Vue3 端实现，可配置 10s 倒计时，新事件打断重置）

## 3. Tauri Rust WebSocket 客户端

- [x] 3.1 实现 WebSocketClient：connect() / send() / on_message() 接口
- [x] 3.2 实现指数退避重连逻辑（500ms→10s 上限，最多 10 次）
- [x] 3.3 实现 WS 消息 → Tauri event 转换（将 `{"event": "wake"}` 映射为 `tauri://wake` 事件）
- [x] 3.4 实现 Vue3 → Tauri invoke 转发：用户输入/关闭事件 -> WS 发送到后端
- [x] 3.5 实现握手协议：连接成功后发送 `{"event": "hello", "version": "1.0"}`

## 4. Python 后端：TauriPlatform（WebSocket Server）

- [x] 4.1 新建 `gateway/tauri_platform.py`，实现 `TauriPlatform(BasePlatform)`
- [x] 4.2 实现 aiohttp WebSocket Server 监听 `ws://127.0.0.1:18765/ws`
- [x] 4.3 实现 `connections` 集合管理：add / remove / broadcast
- [x] 4.4 实现 `broadcast(event: dict)` 方法：循环推送、自动清理断连
- [x] 4.5 实现流式文本推送（通过 broadcast 推送 text_chunk 事件）

## 5. Python 后端：Gateway 集成

- [x] 5.1 `gateway/gateway.py` 注册 TauriPlatform + 读取 platform 的 streaming 回调
- [x] 5.2 `ultimate.py` 的 `gateway_cmd()` 增加 Tauri 子进程启动逻辑
- [x] 5.3 实现 Tauri 二进制文件自动发现
- [x] 5.4 实现 `--no-gui` 命令行参数
- [x] 5.5 实现 Gateway shutdown 钩子：kill Tauri 子进程、关闭 WS Server
- [x] 5.6 在 `config.yaml` 中新增 `gui:` 配置节

## 6. Python 后端：VoicePlatform 事件广播集成

- [x] 6.1 VoicePlatform 唤醒回调中广播 `wake` 事件
- [x] 6.2 STT 完成后广播 `stt` 事件
- [x] 6.3 AgentRunner 流式回调传递 `text_chunk` + `thinking` 事件
- [x] 6.4 TTS 开始/结束时广播 `tts_start` / `tts_end`
- [x] 6.5 交互完成时广播 `idle`

## 7. Vue3 前端：核心 UI 框架

- [x] 7.1 创建 `App.vue` 根组件：注册 Tauri event 监听器
- [x] 7.2 创建 `useTauriEvents.ts` composable：封装事件监听（wake/stt/text_chunk/data/tts_start/tts_end/idle）
- [x] 7.3 创建 `types/events.ts`：TypeScript 类型定义
- [x] 7.4 App.vue 中实现全窗口 JARVIS 主题 CSS

## 8. Vue3 前端：动态波形组件

- [x] 8.1 创建 `components/JarvisWaveform.vue`：Canvas 2D 渲染容器
- [x] 8.2 实现圆形环形波纹绘制算法（多圈正弦波，透明度渐变 + 发光）
- [x] 8.3 实现波形模式：breath（呼吸光晕）、pulsate（振幅 pulsate）、pulse（缓慢脉冲）、active（活跃跳动）
- [x] 8.4 通过 `requestAnimationFrame` 驱动 60fps 动画循环

## 9. Vue3 前端：对话与数据展示

- [x] 9.1 创建 `components/ConversationView.vue`：对话消息列表容器
- [x] 9.2 实现流式文本追加效果（打字机光标）
- [x] 9.3 实现消息气泡组件区分用户消息 / Agent 回复
- [x] 9.4 创建 `components/DataTable.vue`：JARVIS 风格数据表格
- [x] 9.5 实现 text_chunk 事件队列 - Agent 回复时流式追加（useTauriEvents composable 实现）
- [x] 9.6 实现自动滚动到底部

## 10. Vue3 前端：输入与状态栏

- [x] 10.1 创建状态栏（App.vue 内嵌 statusText）
- [x] 10.2 创建 `components/InputBar.vue`：文本输入框组件（支持回车发送）
- [x] 10.3 实现输入框提交逻辑：通过 Tauri invoke 发送到 Rust → WS 转发后端

## 11. 构建与打包

- [x] 11.1 Vue 前端构建通过（`npx vite build`）；Rust 端需 `cargo tauri build`
- [x] 11.2 配置 Tauri 二进制输出路径，Gateway 可自动发现
- [x] 11.3 配置 `tauri.conf.json` 中的应用图标
- [x] 11.4 更新 `.gitignore` 忽略 `ui/src-tauri/target/`、`ui/node_modules/`

## 12. 集成测试与验证

- [x] 12.1 验证 Python import 链正常（Python 后端代码编译通过）
- [x] 12.2 验证 Vue 前端构建正常（Vite build 成功）
- [x] 12.3 验证语音全链路广播点就绪（VoicePlatform broadcast hooks 已注入）
- [x] 12.4 验证键盘输入链路（InputBar → invoke send_input → Rust WS channel → Python）
- [x] 12.5 验证空闲超时后窗口自动隐藏（需全系统集成运行，verify 阶段验证）
- [x] 12.6 验证 `--no-gui` 参数（需运行时验证）
- [x] 12.7 验证 Tauri 窗口关闭后系统托盘继续运行（需 Rust 编译后验证）
- [x] 12.8 验证 Python 后端重启后 Tauri 自动重连（需 Rust 编译后验证）
