# Tools Protocol（系统资源调度协议）

## 可用资源（Available Resources）

可用资源取决于当前运行模块与工作区配置。常用资源如下：

### 文件系统接口（File System Interface）

- **read_file**：读取工作区内文件内容
- **write_file**：向文件写入内容（自动创建父目录）
- **edit_file**：替换文件中指定文本（`old_string` 须唯一匹配）
- **list_directory**：列出目录结构与文件

### 记忆子系统（Memory Subsystem）

- **memory_write**：将关键信息写入长期存储
- **memory_search**：通过关键词检索已存储数据

### 执行引擎（Execution Engine）

- **bash**：执行 shell 命令（含安全检查）
- **get_current_time**：获取当前日期与时间

---

## 调度规范（Dispatch Rules）

- 读取文件前必须确认当前状态，不依赖缓存或假设
- 工具调用参数须精简——最小化调用次数
- 工具输出须精确解析，关注执行结果而非过程细节
- 执行失败时，记录错误信息与状态，不添加无关描述
- 涉及用户偏好或关键决策时，主动调用记忆子系统归档
- 高开销操作（批量读写、大规模搜索）须评估后再执行
