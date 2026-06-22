# Tab Completion Spec

## ADDED Requirements

### Requirement: Tab 补全 REPL 命令

用户在 REPL 中输入以 `/` 开头的命令时，按 Tab 键应弹出补全候选列表。

- **补全词表**: `/new`, `/list`, `/switch`, `/context`, `/compact`, `/soul`, `/skills`, `/memory`, `/search`, `/prompt`, `/bootstrap`, `/help`, `/quit`, `/exit`
- **触发条件**: 输入以 `/` 开头时自动激活补全
- **历史记录**: 无需额外配置，PromptSession 自带

#### Scenario: 输入 / 后按 Tab 显示全部命令

```
You > /<Tab>
/new       /list      /switch    /context   /compact
/soul      /skills    /memory    /search    /prompt
/bootstrap /help      /quit      /exit
```

#### Scenario: 输入 /s 后按 Tab 补全

```
You > /s<Tab>
→ 补全为 /search（或者显示 /soul /search /skills 候选列表）
```

#### Scenario: 补全后继续输入参数

```
You > /switch <Tab> 无需补全，保持当前输入
```

### Future: Tab 补全技能名称（当前版本暂不做）

当前 command 数少，skill 补全价值低。等 skill 数量增长后再加。

- **补全来源**: `SkillsManager.skills` 动态获取
- **实现方式**: 在 `REPL_COMMANDS` 基础上拼接 `[f"/{s['name']}" for s in skills_mgr.skills]`
- **触发条件**: 输入 `/` 后匹配到未注册命令时，尝试匹配 skill 名

### Requirement: 不影响非补全输入

用户输入不以 `/` 开头的普通文本时，Tab 无任何补全行为，按 Tab 跳出 4 空格或保持原有行为。
