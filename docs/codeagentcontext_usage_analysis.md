# CodeAgentContext 使用情况全面分析

## 一、CodeAgentContext 字段清单

### 1.1 元信息字段
```python
session_id: str          # 会话 ID
project_id: str          # 项目 ID
timestamp: str           # 时间戳
agent_mode: Literal[...] # Agent 模式（code_edit/debug/plan/explain）
```

### 1.2 任务和计划
```python
task: Optional[TaskInfo]      # 任务信息（user_goal, constraints 等）
plan: Optional[PlanInfo]      # 计划信息（steps, status 等）
```

### 1.3 代码上下文
```python
code_context: Optional[CodeContext]
  - focused_files: List[FileInfo]  # 活跃文件（完整内容）
  - file_tree: List[str]            # 文件树结构
  - symbol_index: Optional[SymbolIndex]  # 符号索引（Repo Map）
```

### 1.4 对话历史
```python
conversation: Optional[ConversationHistory]
  - messages: List[Message]  # user/assistant/tool 消息
  - max_messages: int
```

### 1.5 记忆上下文
```python
memory: Optional[MemoryContext]
  - project_conventions: List[str]  # 项目规范
  - decisions: List[Decision]       # 历史决策（decision + reason）
```

### 1.6 执行上下文
```python
execution_context: Optional[ExecutionContext]
  - current_step: Optional[int]
  - outputs: List[OutputRecord]
  - running_processes: List[ProcessInfo]
```

### 1.7 工具列表
```python
tools: List[ToolDef]  # 工具定义列表
```

### 1.8 环境信息
```python
environment: Optional[EnvironmentInfo]
  - python_version: str
  - installed_packages: List[str]
  - virtual_env: Optional[str]
```

### 1.9 安全配置
```python
safety: Optional[SafetyConfig]
  - allowed_actions: List[str]
  - max_runtime_sec: int
  - max_file_size_kb: int
  - restricted_paths: List[str]
```

---

## 二、当前发送给 LLM 的内容分析

### 2.1 Direct 模式（首次调用）

**消息构建：** `_build_initial_messages(task)`

**实际发送内容：**
```
[SystemMessage]
  - system_prompt（来自 code_agent_prompt.yaml）
    - 能力描述
    - 可用工具列表（硬编码在 prompt 中）
    - 执行模式选择指导
  - mode_guidance（代码中硬编码）
    - Plan 模式使用场景
    - Direct 模式使用场景

[HumanMessage]
  - task（用户输入的任务）
```

**工具绑定：**
```python
tool_definitions = self.tool_registry.get_all_definitions()
response = self.llm.invoke(messages, tools=tool_definitions)
```

**Direct 模式循环中：**
```python
# 每次循环都重新绑定工具
tool_definitions = self.tool_registry.get_all_definitions()
current_response = self.llm.invoke(messages, tools=tool_definitions)
```

### 2.2 Plan 模式（步骤执行）

**消息构建：** `_build_step_messages(step, plan)`

**实际发送内容：**
```
[SystemMessage]
  - step_execution_prompt（来自 code_agent_prompt.yaml）
  - project_context
    - project_name（来自 self.project_name）
    - project_path（来自 self.project_path）
    - tools_description（来自 self._format_tools_description()）
  - active_files_warning（如果有活跃文件）
    - file_count
    - file_list
  - code_context（如果有内容）
    - focused_files 的完整内容（通过 code_context.to_context_string()）

[HumanMessage]
  - task（来自 plan.task）
  - plan_summary（来自 plan.to_summary()）
  - step_id, total_steps
  - step_description
  - expected_outcome
```

**工具绑定：**
```python
tool_definitions = self.tool_registry.get_all_definitions()
response = self.llm.invoke(messages, tools=tool_definitions)
```

---

## 三、CodeAgentContext 字段使用情况对比

| 字段 | Direct 模式 | Plan 模式 | 发送方式 | 是否重复 |
|------|------------|----------|---------|---------|
| **元信息** |
| session_id | ❌ 未发送 | ❌ 未发送 | - | - |
| project_id | ❌ 未发送 | ❌ 未发送 | - | - |
| timestamp | ❌ 未发送 | ❌ 未发送 | - | - |
| agent_mode | ❌ 未发送 | ❌ 未发送 | - | - |
| **任务和计划** |
| task | ✅ 已发送 | ✅ 已发送 | HumanMessage | 不重复 |
| plan | ❌ 未发送 | ✅ 已发送 | plan.to_summary() | 不重复 |
| **代码上下文** |
| code_context.focused_files | ❌ 未发送 | ✅ 已发送 | code_context.to_context_string() | 不重复 |
| code_context.file_tree | ❌ 未发送 | ❌ 未发送 | - | - |
| code_context.symbol_index | ❌ 未发送 | ❌ 未发送 | - | - |
| **对话历史** |
| conversation.messages | ❌ 未发送 | ❌ 未发送 | - | - |
| **记忆上下文** |
| memory.project_conventions | ❌ 未发送 | ❌ 未发送 | - | - |
| memory.decisions | ❌ 未发送 | ❌ 未发送 | - | - |
| **执行上下文** |
| execution_context | ❌ 未发送 | ❌ 未发送 | - | - |
| **工具列表** |
| tools | ⚠️ 部分发送 | ⚠️ 部分发送 | tools=tool_definitions | **重复** |
| **环境信息** |
| environment | ❌ 未发送 | ❌ 未发送 | - | - |
| **安全配置** |
| safety | ❌ 未发送 | ❌ 未发送 | - | - |

---

## 四、重复和冗余分析

### 4.1 工具列表重复 ⚠️

**问题：**
1. `CodeAgentContext.tools` 字段定义了工具列表，但**从未被填充**
2. 工具实际通过 `tool_registry.get_all_definitions()` 绑定到 LLM
3. Prompt 中硬编码了工具列表（system_prompt 中的"可用工具"部分）

**重复情况：**
- Prompt 中：硬编码工具列表（create_plan, read_file, write_file 等）
- 工具绑定：`tools=tool_definitions`（动态获取）
- CodeAgentContext.tools：**未使用**

**建议：**
- ❌ **不要**在 CodeAgentContext.tools 中存储工具列表（已通过绑定提供）
- ❌ **不要**在 prompt 中硬编码工具列表（工具绑定已提供完整信息）
- ✅ 工具信息通过 `tools=tool_definitions` 自动提供，LLM 可以看到完整的工具定义

### 4.2 项目信息重复

**当前情况：**
- Plan 模式：通过 `project_context` 模板发送 `project_name` 和 `project_path`
- Direct 模式：**未发送**项目信息

**建议：**
- Direct 模式也应该发送项目信息（至少 project_name）
- CodeAgentContext 中的 `project_id` 可以转换为项目名称发送

### 4.3 代码上下文处理

**当前情况：**
- Plan 模式：通过 `code_context.to_context_string()` 发送完整文件内容
- Direct 模式：**未发送**代码上下文

**问题：**
- Direct 模式中，LLM 无法知道之前读取过哪些文件
- 可能导致重复读取文件

**建议：**
- Direct 模式也应该在后续循环中发送活跃文件列表（至少是文件路径）

---

## 五、缺失但应该发送的内容

### 5.1 对话历史（ConversationHistory）⚠️ **重要缺失**

**当前状态：**
- Direct 模式：通过 `messages` 列表维护，但**只包含当前循环的消息**
- Plan 模式：**完全不包含**对话历史
- CodeAgentContext.conversation：已记录，但**从未发送给 LLM**

**影响：**
- LLM 无法知道之前的对话内容
- 多轮对话时上下文断裂
- Plan 模式执行步骤时，不知道之前的步骤做了什么

**应该发送：**
- Direct 模式：在每次循环中，将 `conversation.to_langchain_messages()` 添加到 messages
- Plan 模式：在 `_build_step_messages()` 中，添加之前的对话历史

### 5.2 记忆上下文（MemoryContext）⚠️ **重要缺失**

**当前状态：**
- CodeAgentContext.memory：已记录决策和项目规范
- **从未发送给 LLM**

**应该发送：**
- 项目规范（project_conventions）：帮助 LLM 遵循项目约定
- 历史决策（decisions）：帮助 LLM 了解之前的决策理由

**发送方式：**
- 作为 SystemMessage 的一部分，在首次调用时发送
- 只发送最近 5-10 条，避免 token 过多

### 5.3 代码上下文（Direct 模式缺失）

**当前状态：**
- Plan 模式：已发送 `focused_files` 内容
- Direct 模式：**未发送**

**应该发送：**
- 至少发送活跃文件列表（文件路径）
- 如果文件数量少，可以发送完整内容

### 5.4 符号索引（SymbolIndex）⚠️ **未使用**

**当前状态：**
- CodeAgentContext.code_context.symbol_index：已构建，但**从未发送**

**应该发送：**
- Repo Map 摘要（通过 `symbol_index.to_repo_map_string()`）
- 帮助 LLM 快速了解项目结构，减少不必要的文件读取

---

## 六、Direct 模式 vs Plan 模式对比

### 6.1 消息构建差异

| 方面 | Direct 模式 | Plan 模式 |
|------|------------|----------|
| **首次调用** | `_build_initial_messages()` | `_build_initial_messages()` |
| **后续调用** | 在循环中动态添加消息 | `_build_step_messages()` |
| **系统提示词** | system_prompt + mode_guidance | step_execution_prompt + project_context |
| **代码上下文** | ❌ 未发送 | ✅ 发送完整内容 |
| **对话历史** | ⚠️ 部分（当前循环） | ❌ 未发送 |
| **项目信息** | ❌ 未发送 | ✅ 发送 |
| **工具绑定** | ✅ 每次循环都绑定 | ✅ 每次调用都绑定 |

### 6.2 问题总结

**Direct 模式问题：**
1. ❌ 缺少项目信息
2. ❌ 缺少代码上下文（活跃文件）
3. ⚠️ 对话历史不完整（只包含当前循环）
4. ❌ 缺少记忆上下文

**Plan 模式问题：**
1. ❌ 缺少对话历史（不知道之前的步骤做了什么）
2. ❌ 缺少记忆上下文
3. ❌ 缺少符号索引

---

## 七、提示词与 CodeAgentContext 的重合度分析

### 7.1 当前 Prompt 内容

**system_prompt（首次调用）：**
- 能力描述
- **可用工具列表（硬编码）** ← 与工具绑定重复
- 执行模式选择指导
- 重要约束

**step_execution_prompt（Plan 模式）：**
- 能力描述
- 输出要求
- 重要约束
- 避免重复读取文件警告
- 代码规范

### 7.2 重合度分析

| Prompt 内容 | CodeAgentContext 对应字段 | 重合度 | 建议 |
|------------|-------------------------|--------|------|
| 可用工具列表 | tools（未使用） | ⚠️ 重复 | 删除 prompt 中的硬编码，工具绑定已提供 |
| 项目信息 | project_id, project_name | ❌ 不重合 | Prompt 中 Plan 模式有，Direct 模式缺失 |
| 代码上下文 | code_context.focused_files | ❌ 不重合 | Prompt 中 Plan 模式有，Direct 模式缺失 |
| 对话历史 | conversation.messages | ❌ 不重合 | Prompt 中完全没有，应该添加 |
| 项目规范 | memory.project_conventions | ❌ 不重合 | Prompt 中完全没有，应该添加 |
| 历史决策 | memory.decisions | ❌ 不重合 | Prompt 中完全没有，应该添加 |

---

## 八、优化建议

### 8.1 应该发送的字段（按优先级）

#### 高优先级（必须发送）

1. **conversation.messages** ⚠️
   - **原因：** 多轮对话的核心，LLM 必须知道之前的对话
   - **发送方式：** `conversation.to_langchain_messages()` 添加到 messages
   - **去重：** 工具结果已缩略，避免与 focused_files 重复

2. **memory.decisions** ⚠️
   - **原因：** 帮助 LLM 了解之前的决策理由，避免重复决策
   - **发送方式：** 作为 SystemMessage 的一部分，只发送最近 5-10 条
   - **格式：** "历史决策：\n- 决策1: 原因1\n- 决策2: 原因2"

3. **code_context.focused_files（Direct 模式）** ⚠️
   - **原因：** 避免重复读取文件
   - **发送方式：** 至少发送文件路径列表，如果文件少可以发送内容

#### 中优先级（建议发送）

4. **memory.project_conventions**
   - **原因：** 帮助 LLM 遵循项目规范
   - **发送方式：** 作为 SystemMessage 的一部分
   - **格式：** "项目规范：\n- 规范1\n- 规范2"

5. **code_context.symbol_index（Repo Map）**
   - **原因：** 帮助 LLM 快速了解项目结构
   - **发送方式：** 通过 `symbol_index.to_repo_map_string(max_files=20)`
   - **时机：** 首次调用时发送

6. **project_name, project_path（Direct 模式）**
   - **原因：** 提供项目上下文
   - **发送方式：** 添加到 SystemMessage

#### 低优先级（可选）

7. **execution_context.current_step**
   - **原因：** Plan 模式中，LLM 可能想知道当前步骤
   - **发送方式：** 已在 step_user_message 中通过 step_id 提供

8. **environment.python_version**
   - **原因：** 某些任务可能需要知道 Python 版本
   - **发送方式：** 仅在需要时发送

### 8.2 不应该发送的字段

1. **tools** ❌
   - **原因：** 已通过 `tools=tool_definitions` 绑定，无需在 prompt 中重复

2. **session_id, project_id, timestamp** ❌
   - **原因：** 对 LLM 决策无帮助，只是元数据

3. **agent_mode** ❌
   - **原因：** 已通过 mode_guidance 在 prompt 中说明

4. **safety** ❌
   - **原因：** 安全限制应该在工具层面实现，不需要告诉 LLM

5. **execution_context.outputs, running_processes** ❌
   - **原因：** 执行细节，LLM 不需要知道

### 8.3 Prompt 优化建议

#### 建议 1：删除重复的工具列表

**当前：**
```yaml
## 可用工具
- **create_plan**: 为复杂任务创建执行计划
- **read_file**: 读取文件内容
...
```

**建议：**
```yaml
## 可用工具
工具已通过函数调用绑定，你可以直接使用。主要工具包括：
- create_plan: 创建执行计划（复杂任务使用）
- read_file, write_file, patch_file: 文件操作
- grep, shell_exec: 搜索和执行
- 其他工具请参考函数定义
```

**理由：** 工具绑定已提供完整的工具定义（包括参数、描述），prompt 中的列表是冗余的。

#### 建议 2：添加上下文说明部分

**新增到 system_prompt：**
```yaml
## 上下文信息

系统会为你提供以下上下文信息：

1. **对话历史**：之前的对话消息（user/assistant/tool），帮助你了解上下文
2. **活跃文件**：已加载到上下文中的文件，无需再次读取
3. **历史决策**：之前的重要决策和原因，帮助你保持一致性
4. **项目规范**：项目的编码规范和约定
5. **代码结构**：项目的符号索引（Repo Map），帮助你快速了解项目结构

请充分利用这些上下文信息，避免重复操作。
```

#### 建议 3：统一 Direct 和 Plan 模式的上下文

**问题：** 当前两种模式的上下文差异很大

**建议：**
- Direct 模式也应该发送项目信息、活跃文件列表
- Plan 模式也应该发送对话历史、记忆上下文
- 两种模式共享相同的上下文构建逻辑

---

## 九、实施优先级

### Phase 1：核心缺失（必须修复）

1. ✅ **发送对话历史**
   - Direct 模式：在循环中添加 `conversation.to_langchain_messages()`
   - Plan 模式：在 `_build_step_messages()` 中添加对话历史

2. ✅ **发送记忆上下文**
   - 在 SystemMessage 中添加 `memory.decisions` 和 `memory.project_conventions`
   - 只发送最近 5-10 条，避免 token 过多

3. ✅ **Direct 模式发送代码上下文**
   - 至少发送活跃文件列表
   - 如果文件数量 ≤ 3，发送完整内容

### Phase 2：优化改进（建议实施）

4. ✅ **发送符号索引（Repo Map）**
   - 首次调用时发送 `symbol_index.to_repo_map_string()`
   - 帮助 LLM 快速了解项目结构

5. ✅ **统一上下文构建**
   - 创建 `_build_context_for_llm()` 方法
   - Direct 和 Plan 模式共享相同的上下文构建逻辑

6. ✅ **优化 Prompt**
   - 删除硬编码的工具列表
   - 添加上下文说明部分

### Phase 3：可选优化

7. ⚠️ **环境信息**（仅在需要时）
8. ⚠️ **执行上下文摘要**（Plan 模式可能需要）

---

## 十、总结

### 10.1 核心问题

1. **对话历史未发送** ⚠️ **最严重**
   - 导致多轮对话上下文断裂
   - Direct 和 Plan 模式都存在

2. **记忆上下文未发送** ⚠️ **严重**
   - LLM 无法利用历史决策
   - 可能导致重复决策或不一致

3. **Direct 模式缺少代码上下文** ⚠️ **严重**
   - 可能导致重复读取文件
   - 无法利用已加载的文件内容

4. **工具列表重复** ⚠️ **中等**
   - Prompt 中硬编码，工具绑定已提供
   - 建议删除 prompt 中的列表

### 10.2 优化方向

1. **充分利用 CodeAgentContext**
   - conversation.messages → 发送对话历史
   - memory → 发送决策和规范
   - code_context → 发送活跃文件和符号索引

2. **统一两种模式**
   - Direct 和 Plan 模式应该共享相同的上下文构建逻辑
   - 避免重复代码

3. **优化 Prompt**
   - 删除重复的工具列表
   - 添加上下文说明，让 LLM 知道如何使用这些信息

4. **控制 Token 消耗**
   - 对话历史：只发送最近 10-20 条
   - 记忆：只发送最近 5-10 条决策
   - 符号索引：只发送前 20 个文件的摘要
   - 代码上下文：大文件只发送路径，小文件发送内容

---

## 十一、代码改动建议（仅参考，不实施）

### 11.1 新增方法：`_build_context_for_llm()`

```python
def _build_context_for_llm(self, include_conversation: bool = True) -> str:
    """构建发送给 LLM 的上下文摘要"""
    parts = []
    
    # 1. 记忆上下文（历史决策）
    if self.context.memory and self.context.memory.decisions:
        recent = self.context.memory.decisions[-5:]
        parts.append("### 历史决策")
        for d in recent:
            parts.append(f"- {d.decision}: {d.reason}")
    
    # 2. 项目规范
    if self.context.memory and self.context.memory.project_conventions:
        parts.append("### 项目规范")
        for conv in self.context.memory.project_conventions[-5:]:
            parts.append(f"- {conv}")
    
    # 3. 活跃文件列表（Direct 模式）
    if self.context.code_context and self.context.code_context.focused_files:
        files = [f.path for f in self.context.code_context.focused_files]
        parts.append(f"### 活跃文件 ({len(files)} 个)")
        parts.append("\n".join(f"- {path}" for path in files[:10]))
    
    # 4. 符号索引（Repo Map）
    if (self.context.code_context and 
        self.context.code_context.symbol_index and
        self.context.code_context.symbol_index.file_symbols):
        parts.append("### 代码结构")
        parts.append(self.context.code_context.symbol_index.to_repo_map_string(max_files=20))
    
    return "\n".join(parts) if parts else ""
```

### 11.2 修改 `_build_initial_messages()`

```python
def _build_initial_messages(self, task: str) -> List:
    """构建首次 LLM 调用的消息"""
    prompt_loader = get_code_agent_prompt_loader()
    system_prompt = prompt_loader.get_system_prompt()
    
    # 添加上下文摘要
    context_summary = self._build_context_for_llm(include_conversation=False)
    if context_summary:
        system_prompt += f"\n\n## 当前上下文\n{context_summary}"
    
    messages = [SystemMessage(content=system_prompt + mode_guidance)]
    
    # 添加对话历史
    if self.context.conversation and self.context.conversation.messages:
        history = self.context.conversation.to_langchain_messages()
        messages.extend(history)
    
    messages.append(HumanMessage(content=task))
    return messages
```

### 11.3 修改 `_build_step_messages()`

```python
def _build_step_messages(self, step: PlanStep, plan: Plan) -> List:
    # ... 现有代码 ...
    
    messages = [SystemMessage(content=final_system_content)]
    
    # 添加对话历史（新增）
    if self.context.conversation and self.context.conversation.messages:
        recent = self.context.conversation.get_recent_messages(n=10)
        history = ConversationHistory(messages=recent).to_langchain_messages()
        messages.extend(history)
    
    messages.append(HumanMessage(content=user_message))
    return messages
```

### 11.4 修改 Direct 模式循环

```python
# 在 _execute_direct_mode() 的循环中
# 首次调用后，后续调用应该包含对话历史
# 当前代码已经在 messages 中累积，但缺少 conversation 中的历史
```

---

**分析完成。以上是全面的 CodeAgentContext 使用情况分析，包括问题识别、重复分析、缺失内容、优化建议等。**

