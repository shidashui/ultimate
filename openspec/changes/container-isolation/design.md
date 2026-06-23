## 架构决策

**方案**: AgentRunner 构造时创建自己的 `Container` 实例；通过 `contextvars.ContextVar` 让工具函数能访问"当前"容器。

```
AgentRunner(session_id="abc")        AgentRunner(session_id="xyz")
  │                                    │
  └─ Container()                       └─ Container()
       │                                    │
       ├─ ContextGuard(...)                  ├─ ContextGuard(...)
       ├─ MemoryStore(WORKSPACE_DIR)         ├─ MemoryStore(WORKSPACE_DIR)
       ├─ SkillsManager(WORKSPACE_DIR)       ├─ SkillsManager(WORKSPACE_DIR)
       └─ ProviderRouter(...)                └─ ProviderRouter(...)
```

**备选方案（不采用）**:
- 线程局部 (`threading.local`): 不适用于 asyncio 并发模型，多个协程共享同一线程
- AgentRunner 直接 `new` 依赖（无 Container）: 会丢失依赖注册/查找的灵活性，工具函数适配成本更高

## ContextVar 机制

```python
# agentd/bootstrap/context.py (新增)
import contextvars

_current_container: contextvars.ContextVar = contextvars.ContextVar("current_container")

def set_current_container(c): ...
def get_current_container(): ...
```

工具函数从 `container.get("memory_store")` 改为 `get_current_container().get("memory_store")`。

## 变更文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `agentd/bootstrap/context.py` | **新建** | ContextVar 存储/获取当前容器 |
| `agentd/bootstrap/container.py` | 修改 | Container 支持 session_id，移除全局单例 |
| `agentd/bootstrap/__init__.py` | 修改 | 移除 `container` 导出，新增 contextvar helpers |
| `agentd/agent/runner.py` | 修改 | __init__ 创建 Container，设置 contextvar |
| `agentd/tools/memory_tools.py` | 修改 | 通过 contextvar 获取 MemoryStore |
| `agentd/tools/skill_tools.py` | 修改 | 通过 contextvar 获取 SkillsManager |
| `cli/cli.py` | 修改 | 适配新 AgentRunner 接口（去掉 container 直接访问） |
| `tests/test_container_isolation.py` | **新建** | per-session 隔离测试 |

## 测试策略

- **单元测试**: 两个 AgentRunner 实例的 container 互相独立，contextvar 正确传播
- **回归测试**: 现有 56 个测试全部保持通过
