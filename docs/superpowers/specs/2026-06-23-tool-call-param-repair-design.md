---
comet_change: tool-call-param-repair
role: technical-design
canonical_spec: openspec
archived-with: 2026-06-23-tool-call-param-repair
status: final
---

# Tool Call Parameter Validation & Auto-Repair — 技术设计

## 架构

```
process_tool_call(name, tool_input)
  │
  ├─ 1. 查 handler + schema
  │     handler = self.container.tools_handlers.get(name)
  │     schema  = self.container.tools_schemas.get(name)
  │
  ├─ 2. validate_and_repair(tool_input, schema, handler)
  │     │
  │     ├─ 从 schema 取每个参数的类型 → 类型强转
  │     ├─ tool_input 中不在 schema 的 key → 删除
  │     ├─ 从 inspect.signature(handler) 取默认值 → 填充缺失参数
  │     ├─ 必填参数缺失 → 返回诊断错误
  │     └─ 返回 (repaired_input, warnings[])
  │
  ├─ 3. warnings 非空 → logger.warning(...)
  │
  ├─ 4. handler(**repaired_input)
  │
  └─ 5. 现有 try/except 作为兜底安全网
```

## 分层职责

| 层 | 模块 | 职责 |
|----|------|------|
| Schema 源 | `agentd/tools/registry.py` | `get_tool_schema(name)` — 返回参数类型定义 |
| 暴露 | `agentd/bootstrap/container.py` | `tools_schemas` 属性 — 聚合所有 tool schema |
| 修复引擎 | `agentd/tools/param_repair.py` | `validate_and_repair()` — 纯函数，类型强转 + 过滤 + 填默认值 |
| 调用点 | `agentd/agent/runner.py` | `process_tool_call()` — 调用 repair 后再 handler(**input) |

## 组件

### ToolRegistry 新增 (`agentd/tools/registry.py`)

```python
def get_tool_schema(self, name: str) -> dict | None:
    """返回 {param_name: {type, description}, ...} 或 None"""
    for tool in self._tools:
        if tool["name"] == name:
            return tool["input_schema"]["properties"]
    return None
```

### Container 新增 (`agentd/bootstrap/container.py`)

```python
@property
def tools_schemas(self) -> dict:
    """{tool_name: {param: {type, description}}}"""
    return {t["name"]: t["input_schema"]["properties"] for t in self.tools}
```

### validate_and_repair (`agentd/tools/param_repair.py`)

```python
def validate_and_repair(
    tool_input: dict,
    schema: dict[str, dict],     # {"param": {"type": "integer", ...}}
    handler: callable,
) -> tuple[dict, list[str]]:     # (repaired_input, warnings)
```

## 修复策略

| 场景 | 检测方式 | 修复 | 示例 |
|------|---------|------|------|
| `str` → `int` | schema `type: "integer"` | `int()` 强转 | `timeout: "30"` → `30` |
| `int` → `str` | schema `type: "string"` | `str()` 强转 | `command: 123` → `"123"` |
| `float` → `int` | schema `type: "integer"` | `int()` 截断 | `timeout: 3.7` → `3` |
| 多余参数 | key 不在 schema | 删除 + warning | `{cmd, extra}` → `{cmd}` |
| 缺失可选参数 | 有默认值（inspect） | 填入默认值 | `{}` → `{timeout: 30}` |
| 缺失必填参数 | 无默认值 | **报错** | `No required param 'command' for 'bash'` |
| 强转失败 | `int("abc")` → ValueError | **报错** | `"abc" is not a valid integer for 'timeout'` |
| 空必填字符串 | type=string, required, 值="" | **报错** | `Parameter 'command' must be non-empty` |
| 已合法 | 无需修复 | 原样返回 | no-op |

## 错误处理

- 修复失败 → 返回诊断错误字符串，包含具体参数名和问题
- `validate_and_repair` 返回 `({}, ["error1", "error2"])` 表示不可修复
- 现有 `try/except TypeError` 保留作为兜底安全网（repair 之后不太可能触发）
- `except Exception` 保持不变

## 边界条件

| 输入 | 行为 |
|------|------|
| `tool_input = {}` + 全部有默认值 | 全部填充 |
| `tool_input = {}` + 有必填参数 | 列出所有缺失参数 |
| 同时有多个问题 | 逐个修复，warning 累计 |
| 无参数工具（get_current_time） | no-op，直接透传 |
| schema 为 None（未知 tool） | 跳过 repair，走 Unknown tool 错误 |

## 测试策略

| 层级 | 文件 | 覆盖 |
|------|------|------|
| 单元 | `tests/test_param_repair.py` | 每个修复策略独立测试（~12 case） |
| 集成 | 同上 | `process_tool_call` 端到端 malformed input |
| 回归 | 全部现有 | 68 个现有测试保持通过 |

### 关键测试用例

1. `str "30"` → `int 30`（coerce）
2. `int 42` → `str "42"`（coerce）
3. float → int 截断
4. 多余 key 删除
5. 缺失 timeout → 填默认 30
6. 缺失 command → 报错（必填）
7. `timeout: "abc"` → 报错（无法强转）
8. 空 `{}` + get_current_time（无参数工具）→ no-op
9. 已合法输入 → 不变
10. 同时多个问题 → 全部修复 + 全部 warning

## 风险

| 风险 | 缓解 |
|------|------|
| 类型强转改变语义（`float→int` 丢精度） | 记录 warning，模型可看到修复后的输入差异 |
| Registry schema 与实际 handler 不一致 | inspect 只取默认值不做类型判断，以 schema 为准 |
| 修复掩盖了模型 prompt 质量问题 | WARNING 日志 + 运营可聚合修复频率 |
