# Ultimate — 自主智能体网关（Autonomous Agent Gateway）

一个基于 LLM 的**自主智能体运行时**，通过多平台消息网关与外部世界交互。

> 它不是"问答机器人"，而是一个**目标驱动的主动执行系统**。用户输入被视为"事件"，而非必须立即响应的指令。

---

## 核心架构

```
用户输入（终端 CLI / 微信 / 语音）
        │
        ▼
  ┌─────────────────────────────────────┐
  │           Gateway                   │  ← 多平台消息网关
  │   收发消息 → 路由到 AgentRunner     │
  └─────────────────────────────────────┘
        │
        ▼
  ┌─────────────────────────────────────┐
  │         AgentRunner                 │  ← LLM 主循环
  │    · 构建 System Prompt             │
  │    · 调用 DeepSeek LLM              │
  │    · 执行工具调用                   │
  │    · 上下文溢出保护                 │
  │    · 会话持久化                     │
  └─────────────────────────────────────┘
        │
        ▼
  ┌─────────────────────────────────────┐
  │     Bootstrap Container             │  ← DI 容器
  │    · MemoryStore (记忆)             │
  │    · SkillsManager (技能发现)       │
  │    · ContextGuard (上下文守护)       │
  │    · 工具注册表                     │
  └─────────────────────────────────────┘
```

### 三大层

| 层 | 路径 | 职责 |
|---|---|---|
| **Agent Runtime (agentd)** | `agentd/` | LLM 循环、系统提示词构建、工具调用、记忆管理、上下文溢出保护、会话管理、技能发现与注入、人格加载 |
| **Gateway (多平台网关)** | `gateway/` | 异步消息网关，注册多个 `BasePlatform` 实例，统一收发消息并路由到 AgentRunner |
| **Platform Adapters (平台适配器)** | `platforms/` | 微信（Weixin SDK）、语音等平台的具体实现 |

---

## 技术栈

| 组件 | 技术选型 |
|---|---|
| 语言 | Python 3.8+ |
| LLM Provider | DeepSeek（`deepseek-v4-pro`） |
| API 协议 | Anthropic Messages API（兼容层） |
| 异步框架 | `asyncio` + `aiohttp` |
| 微信 SDK | 自研 `wx_sdk`（基于 ilink Bot API，AES-128 加解密） |
| 语音编解码 | `pysilk`（SILK → WAV） |
| 计算机视觉（研究模块） | YOLOv11 + MediaPipe + OpenCV |
| 构建 | `hatchling`（wx_sdk 子包） |

---

## 项目结构

```
ultimate_try/
│
├── ultimate.py              # CLI 入口：start / stop / chat / gateway
├── test.py                  # 微信 Echo Bot 测试脚本
├── config.json              # LLM 模型配置
│
├── agentd/                  # 核心 Agent 运行时
│   ├── agent/
│   │   └── runner.py        # AgentRunner — LLM 主循环（同步 + 异步）
│   ├── bootstrap/
│   │   ├── container.py     # DI 容器—服务注册与获取
│   │   └── loader.py        # BootstrapLoader—加载 workspace 配置
│   ├── context/
│   │   ├── context.py       # ContextGuard—三层上下文溢出保护
│   │   └── session.py       # SessionStore—JSONL 会话持久化
│   ├── memory/
│   │   └── memory.py        # MemoryStore—双层记忆（永久 + 每日日志）
│   ├── prompt/
│   │   └── prompts.py       # 8 层系统提示词组装
│   ├── skill/
│   │   └── skill.py         # SkillsManager—技能发现与注入
│   ├── soul/
│   │   └── soul.py          # 人格定义加载
│   └── tools/
│       ├── tool_handlers.py # 工具注册与调度
│       ├── file_tools.py    # 文件操作工具（bash/read/write/edit/list/时间）
│       ├── memory_tools.py  # 记忆工具（写入/搜索）
│       └── browser_tools.py # 网页搜索工具（百度搜索 + 页面抓取）
│
├── gateway/                 # 多平台消息网关
│   ├── gateway.py           # Gateway 框架 — Message/Reply/BasePlatform
│   └── __init__.py
│
├── platforms/               # 平台适配器
│   ├── weixin.py            # WeChatPlatform — 微信适配器
│   ├── voice.py             # VoicePlatform — 语音适配器
│   └── lib/
│       └── wx_sdk/          # 自研微信 SDK
│           └── app/
│               ├── bot.py           # WeixinBot — 机器人主类
│               ├── api.py           # WeixinAPI — HTTP 客户端
│               ├── auth.py          # WeixinAuth — QR 扫码登录
│               ├── monitor.py       # MessageMonitor — 长轮询消息监控
│               ├── cdn.py           # CdnUploader — CDN 加密上传
│               ├── types.py         # 数据结构与枚举
│               ├── utils.py         # 工具函数（AES 加解密等）
│               ├── silk_transcode.py# SILK → WAV 语音转码
│               ├── storage.py       # 账号凭据持久化
│               └── exceptions.py    # 自定义异常
│
├── cli/                     # 终端交互客户端
│   └── cli.py               # Cli — 会话管理 + 上下文监控 + 历史压缩
│
├── config/                  # 配置
│   ├── configs.py           # 路径常量、Bootstrap 配置、上下文限制
│   └── logging_config.py    # 日志配置
│
├── utils/                   # 共享工具
│   ├── clients.py           # Anthropic API 客户端（同步 + 异步）
│   ├── print_tools.py       # ANSI 彩色终端输出
│   └── path_tools.py        # 路径穿越防护
│
├── workspace/               # Agent 启动配置文件
│   ├── IDENTITY.md          # 身份定义—主动系统、目标驱动
│   ├── SOUL.md              # 人格定义—Luna，温和而高效
│   ├── BOOTSTRAP.md         # 启动上下文—系统架构概览
│   ├── MEMORY.md            # 长期记忆
│   ├── TOOLS.md             # 工具使用指南
│   ├── AGENTS.md            # 多 Agent 配置
│   ├── HEARTBEAT.md         # 定时检查指令
│   └── USER.md              # 用户上下文（可选）
│
├── study/                   # 研究模块—计算机视觉感知
│   ├── main.py              # 统一感知系统入口
│   ├── viewer.py            # 实时可视化
│   └── perception/
│       └── video/
│           ├── pipeline.py          # 视频流水线（MOG2 → YOLO → Pose）
│           ├── motion_detector.py   # MOG2 运动检测
│           ├── object_detector.py   # YOLOv11 + ByteTrack 目标检测
│           └── pose_detector.py     # MediaPipe 姿态估计 + 手势识别
│
├── docs/                    # 文档
├── openspec/                # OpenSpec 变更管理
│   ├── changes/             # 活跃变更
│   └── specs/               # 能力规格
│
├── .claude/                 # Claude Code 技能
│   └── skills/
│       ├── comet*/          # Comet 开发工作流
│       └── openspec-*/      # OpenSpec 变更管理
│
└── .weixin-clawbot/         # 微信运行数据
    ├── accounts/            # 账号凭据
    └── received_media/      # 接收的媒体文件
```

---

## Agent 身份与人格

### 身份 — 自主智能体

| 维度 | 描述 |
|---|---|
| 角色 | 自主执行系统，而非问答助手 |
| 核心驱动 | **目标驱动** > 问题驱动 |
| 核心输出 | **行动** > 对话 |
| 运行方式 | **状态驱动** > 指令驱动 |
| 用户角色 | 输入来源之一，不是唯一控制者 |

### 人格 — Luna

- **直接性优先** — 先给明确答案或行动，再补充说明
- **温度次要** — 克制地表达关心，不将情感置于任务之上
- **好奇功能化** — 仅在与任务相关时才提问
- **高效优先** — 拒绝冗余表达和套话

---

## 快速开始

### 环境要求

- Python 3.8+
- 有效的 DeepSeek API Key（或兼容 Anthropic API 的 LLM 端点）

### 安装

```bash
# 安装依赖
pip install anthropic aiohttp pycryptodome beautifulsoup4 requests qrcode[pil]

# 视觉模块（可选）
pip install ultralytics mediapipe opencv-python numpy

# 语音转码（可选）
pip install pysilk
```

### 配置

编辑 `config.json`：

```json
{
    "model": {
        "provider": "deepseek",
        "name": "deepseek-v4-pro",
        "api_key": "your-api-key-here",
        "base_url": "https://api.deepseek.com/anthropic"
    }
}
```

### 运行

```bash
# 交互式聊天模式
python ultimate.py chat

# 启动消息网关（微信 / 语音平台）
python ultimate.py gateway

# 启动后台服务
python ultimate.py start

# 停止服务
python ultimate.py stop
```

---

## 核心特性

| 特性 | 描述 |
|---|---|
| **主动执行** | Agent 自主推进目标，不等待用户每一步指令 |
| **多平台** | 终端 + 微信 + 语音共享同一个 Agent 内核 |
| **多层次记忆** | 永久记忆（MEMORY.md）+ 每日日志 + TF-IDF 召回 |
| **上下文保护** | 3 级溢出防护：截断 → LLM 摘要 → 报错 |
| **技能发现** | 自动扫描目录发现技能定义（SKILL.md） |
| **工具调用** | 文件操作、脚本执行、记忆读写、网页搜索 |
| **会话管理** | 按用户隔离会话，JSONL 持久化，Anthropic 协议重构 |
| **微信原生** | 自研 SDK 覆盖登录/消息/媒体/CDN 加密全链路 |
| **视觉感知** | YOLOv11 检测 + MediaPipe 姿态 + 运动检测流水线 |

---

## 微信 SDK（wx_sdk）

位于 `platforms/lib/wx_sdk/`，基于微信官方 ilink Bot API，覆盖：

- QR 扫码登录（自动刷新过期二维码，最多重试 3 次）
- 长轮询消息接收（自动退避 + 会话过期处理）
- 文本/图片/文件/视频消息发送
- CDN 媒体上传（AES-128-ECB 加密）
- 语音 SILK → WAV 解码
- 输入状态指示器

---

## 感知系统（研究模块）

位于 `study/`，一个计算机视觉研究项目：

- **三阶段流水线**：运动检测（MOG2）→ 目标检测（YOLOv11 + ByteTrack）→ 姿态估计（MediaPipe）
- **节流机制**：仅在有运动时才运行重负载检测器
- **手势识别**：举手、挥臂、交叉手臂
- **支持多种输入**：摄像头、视频文件、RTSP 流
- **运行模式**：可视化窗口模式 / 无头模式

---

## 开发工作流

本项目使用 **OpenSpec + Comet 双星开发流程**：

- **OpenSpec** — 定义"做什么"（变更管理、spec 生命周期）
- **Comet** — 定义"怎么做"（阶段化开发：开启 → 设计 → 构建 → 验证 → 归档）

所有变更经过完整的 brainstorm → design → build → verify → archive 生命周期。

---

## 项目状态

**WIP** — 持续开发中的自主智能体系统。
