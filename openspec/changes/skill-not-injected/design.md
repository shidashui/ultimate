## 方案

在 `Container.initialize()` 中 `SkillsManager` 实例化后添加 `discover()` 调用。

### 变更点

```python
# agentd/bootstrap/container.py
skills_mgr = SkillsManager(WORKSPACE_DIR)
skills_mgr.discover()           # ← 新增
```

### 风险

- `discover()` 内部遍历文件系统，但当前各扫描路径已验证存在；异常已被 `_scan_dir` 内部 try/except 覆盖
- 无侵入性，一行追加，不影响其他初始化流程

### 验证方式

- 启动后 `skills_mgr.skills` 非空，包含 `workspace/skills/` 下的技能
- `skills_mgr.format_skill_registry()` 返回技能列表而非 "(无可用技能)"
