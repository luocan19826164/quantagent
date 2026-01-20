# Agent 架构分析与优化方案

## 一、问题概述

当前 `agent.py` 存在以下架构问题：

1. **执行流程过于僵化** - 强制生成 Plan，不够灵活
2. **上下文管理割裂** - 每次任务重建上下文，无法持续继承
3. **冗余的审批流程** - approve/cancel 逻辑未使用
4. **CodeAgentContext 设计闲置** - 完善的上下文结构未被使用

---

## 二、详细问题分析

### 2.1 执行流程问题

**当前流程：**
```
用户输入 → Planner 强制生成 Plan → 逐步执行 Step → 返回结果
```

**问题：**
- 每次用户输入都**强制生成 Plan**，即使是简单问题
- LLM 没有自主权决定"是否需要计划"
- 简单问题也要走完整 Plan 流程（过度工程化）

**Cursor 等工具的流程（推测）：**

> 注：Cursor 界面上显示的 "thought 5s" 应该是 LLM 在调用工具（grep/search）收集信息的过程，而不是一个单独的"思考"阶段。

```
用户输入 → LLM（绑定工具）直接开始响应
         → 如果需要信息 → 调用 grep/read_file 等工具
         → 获取信息后继续响应
         → 如果需要修改文件 → 调用 write_file
         → 循环直到任务完成
```

**关键差异：**
| 方面 | 当前实现 | Cursor 风格（推测）|
|------|----------|-------------------|
| 首次响应 | 强制生成 Plan | LLM 自主决定下一步 |
| 信息收集 | Plan 第一步可能是收集 | LLM 随时调用工具收集 |
| 简单问题 | 也要走 Plan | 直接回答，不需要 Plan |
| 复杂任务 | Plan 是必须的 | LLM 可能自己"心里有计划"但不显式生成 |

**核心区别：** 当前实现是"先规划后执行"的瀑布模式，而 Cursor 更像是"边思考边执行"的**工具调用循环**模式。

### 2.2 上下文管理问题

**当前实现分析：**

```python
# agent.py 第 126 行
self.conversation_history: List[Dict] = []  # 定义了但从未使用！

# agent.py 第 368 行 - 每次 run() 都重建上下文
context = self._build_project_context()
plan = self.planner.create_plan_sync(task, context)
```

**问题：**
1. `conversation_history` 定义了但**从未被填充或读取**
2. 每次 `run()` 调用都重新构建 `_build_project_context()`
3. 多轮对话之间**上下文完全断裂**
4. 用户问第二个问题时，LLM 不知道之前做了什么

**期望的上下文管理（参考 Cursor）：**
```
对话 1: 用户问问题 → LLM 回答 → 保存到上下文
对话 2: 用户问问题 → 加载历史上下文 → LLM 知道之前做了什么 → 回答
对话 N: 上下文持续累积，按策略淘汰旧信息
```

### 2.3 冗余的审批流程

**当前代码中存在但未使用的功能：**

```python
# 这些方法从未被外部调用
def approve_plan(self, modified_plan: Dict = None)
def reject_plan(self, reason: str = "")

# PlanStatus 中未使用的状态
AWAITING_APPROVAL = "awaiting_approval"
```

**实际使用：**
```python
# chat_stream 中总是 auto_approve=True
for event in self.run(user_input, auto_approve=True):
```

**建议：** 删除这些冗余代码，简化流程。

### 2.4 CodeAgentContext 未被使用

**context.py 定义了完善的结构：**

```python
@dataclass
class CodeAgentContext:
    session_id: str
    project_id: str
    task: Optional[TaskInfo] = None          # 任务信息
    plan: Optional[PlanInfo] = None          # 计划信息
    code_context: Optional[CodeContext]      # 代码上下文
    execution_context: Optional[ExecutionContext]  # 执行上下文
    memory: Optional[MemoryContext] = None   # 记忆上下文
    environment: Optional[EnvironmentInfo]   # 环境信息
    safety: Optional[SafetyConfig] = None    # 安全配置
    
    def to_dict(self) -> Dict[str, Any]:     # 转换方法
    def to_json(self) -> str:                # JSON 序列化
```

**实际使用情况：**
- `CodeAgentContext` 类**从未被实例化**
- `to_dict()` 和 `to_json()` **从未被调用**
- agent.py 只用了简单的 `CodeContext`

**设计初衷 vs 实际：**
| 设计 | 实际 |
|------|------|
| 结构化上下文与 LLM 交互 | 手工拼接字符串 |
| MemoryContext 保存决策历史 | 无历史记忆 |
| ExecutionContext 记录执行结果 | 只在步骤内使用 |

---

## 三、优化方案

### 3.1 新的执行流程（工具调用循环模式）

**核心思想：** 不强制生成 Plan，让 LLM 自主决定每一步做什么。

```
┌─────────────────────────────────────────────────────────┐
│                    用户输入                              │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  加载历史上下文 + 构建消息                                │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  LLM 响应（绑定工具：grep, read_file, write_file 等）     │
└─────────────────────────────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
     ┌────────────────┐    ┌────────────────┐
     │  有工具调用？    │    │  无工具调用     │
     │  执行工具       │    │  返回最终响应   │
     │  结果加入上下文  │    └────────────────┘
     └────────────────┘
              │
              ▼
       ┌────────────┐
       │ 继续调用 LLM │ ←─── 循环直到无工具调用
       └────────────┘
```

**这种模式的优点：**
1. LLM 自主决定是否需要收集信息
2. 简单问题直接回答，不走 Plan
3. 复杂任务 LLM 会自然地分步执行
4. 更接近人类的思考方式

### 3.2 持续上下文管理

**核心原则：**
1. 对话历史持续保存
2. 每轮对话结束更新上下文
3. 按策略淘汰旧信息（LRU / 重要性评分）

**方案：扩展现有 CodeAgentContext，而非新建类**

`CodeAgentContext` 已经设计得很完善，但**缺少对话历史**。建议：

```python
# 在 context.py 中添加

@dataclass
class Message:
    """对话消息"""
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: Optional[List[Dict]] = None  # assistant 消息可能有工具调用
    tool_call_id: Optional[str] = None       # tool 消息需要关联的 tool_call_id
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class ConversationHistory:
    """对话历史"""
    messages: List[Message] = field(default_factory=list)
    max_messages: int = 50  # 最多保留的消息数
    
    def add_user_message(self, content: str): ...
    def add_assistant_message(self, content: str, tool_calls: List = None): ...
    def add_tool_result(self, tool_call_id: str, result: str): ...
    
    def to_langchain_messages(self) -> List[BaseMessage]:
        """转换为 LangChain 消息格式"""
    
    def evict_old_messages(self):
        """淘汰旧消息"""

# 扩展 CodeAgentContext
@dataclass
class CodeAgentContext:
    # ... 现有字段 ...
    
    # 新增：对话历史
    conversation: Optional[ConversationHistory] = None
```

**这样做的好处：**
1. 复用现有的 `CodeAgentContext` 设计
2. 所有上下文在一个地方管理
3. `to_dict()` / `to_json()` 可以包含对话历史

### 3.2.2 ConversationHistory 与 MemoryContext 的关系

**现有 MemoryContext（context.py）：**
```python
@dataclass
class MemoryContext:
    """记忆上下文"""
    project_conventions: List[str]      # 项目约定
    recent_decisions: List[Decision]    # 最近决策（decision + reason）
```

**新增 ConversationHistory：**
```python
@dataclass
class ConversationHistory:
    """对话历史"""
    messages: List[Message]  # user/assistant/tool 完整消息
```

**两者不重复，定位不同：**

| | MemoryContext | ConversationHistory |
|---|--------------|---------------------|
| **定位** | 长期记忆（摘要） | 短期记忆（原始消息） |
| **内容** | "决策 + 原因" 的压缩 | 完整的消息记录 |
| **生命周期** | 跨会话持久化 | 当前会话内 |
| **发给 LLM** | 作为背景参考 | 作为消息历史 |
| **大小** | 小（只保留重要决策） | 大（完整对话） |

**关系图：**
```
ConversationHistory (短期)              MemoryContext (长期)
┌───────────────────────────┐          ┌───────────────────────────┐
│ User: "优化这个函数"        │          │ project_conventions:      │
│ AI: 调用 read_file         │    →     │   - "项目使用 pytest"      │
│ Tool: [文件内容]            │   提炼    │   - "代码风格用 black"     │
│ AI: "我用缓存优化了..."     │    →     │                           │
│ User: "好的"               │          │ recent_decisions:         │
│ ...                        │          │   - decision: "使用缓存"   │
└───────────────────────────┘          │     reason: "避免重复计算" │
                                       └───────────────────────────┘
```

**建议的 CodeAgentContext 结构：**
```python
@dataclass
class CodeAgentContext:
    # ... 现有字段 ...
    
    # 短期：当前会话的完整对话（发给 LLM 作为消息历史）
    conversation: Optional[ConversationHistory] = None  # 新增
    
    # 长期：跨会话的决策记忆（作为背景参考，已有但未使用）
    memory: Optional[MemoryContext] = None  # 已有
```

**工作流程：**
1. `ConversationHistory` 记录当前会话的所有消息
2. 会话结束时，从对话中**提炼**重要决策到 `MemoryContext`
3. 下次会话开始时，`MemoryContext` 提供历史背景
4. 两者都发给 LLM，但方式不同：
   - `conversation` → 作为消息历史（HumanMessage/AIMessage/ToolMessage）
   - `memory` → 作为系统提示的一部分（背景信息）

### 3.2.1 上下文去重策略（重要）

**问题：** `ConversationHistory` 和 `CodeAgentContext` 中的内容可能重复。

**典型场景：**
```
用户: "读取 config.py"
LLM: 调用 read_file("config.py")
工具返回: { content: "... 500行代码 ..." }

此时文件内容出现在两个地方：
1. ConversationHistory.messages 中的 tool result
2. CodeAgentContext.code_context.focused_files 中
```

**核心原则：**
1. **`focused_files` 的 content 不截断** - 保持完整内容
2. **`read_file` 工具首次返回不截断** - LLM 必须看到完整内容才能正确决策
3. **`messages` 历史中截断/引用** - 因为完整内容已在 focused_files 中

**去重策略：**

| 数据类型 | 首次返回 | messages 历史中 | focused_files 中 |
|---------|---------|----------------|-----------------|
| **read_file 结果** | ✅ 完整 | 📝 缩略引用 | ✅ 完整 |
| **write_file 结果** | ✅ 完整确认 | 📝 缩略引用 | ✅ 完整 |
| **grep 结果** | ✅ 完整 | ✅ 完整 | ❌ 不存储 |
| **shell_exec 结果** | ✅ 完整 | 📝 截断 | ✅ execution_context |
| **LLM 文本响应** | - | ✅ 完整 | ❌ 不存储 |

**为什么首次返回不能截断？**
- LLM 第一次读取文件时，必须看到完整内容才能：
  - 理解代码结构
  - 找到需要修改的位置
  - 做出正确的决策
- 如果首次就截断，LLM 可能基于不完整信息做出错误判断

**边界情况：大文件处理**

如果文件非常大（如 50000 行），完整存储会超出 token 限制。处理策略：

| 文件大小 | 策略 |
|---------|------|
| **< 500 行** | 完整存储，无需特殊处理 |
| **500-2000 行** | 完整存储，但可能需要控制 focused_files 数量 |
| **> 2000 行** | 提示 LLM 使用分段读取 |

```python
def read_file(path: str, start_line: int = None, end_line: int = None) -> str:
    """
    读取文件内容。
    
    对于大文件（>2000行），建议使用 start_line 和 end_line 参数
    分段读取，而不是一次读取全部内容。
    """
    content = Path(path).read_text()
    lines = content.split('\n')
    total_lines = len(lines)
    
    # 如果指定了范围，返回指定部分
    if start_line is not None or end_line is not None:
        start = start_line or 0
        end = end_line or total_lines
        return '\n'.join(lines[start:end])
    
    # 如果文件太大，返回摘要 + 提示
    if total_lines > 2000:
        preview = '\n'.join(lines[:100])  # 前 100 行预览
        return f"""文件较大（{total_lines} 行），以下是前 100 行预览：

{preview}

... [文件共 {total_lines} 行]

提示：请使用 read_file(path, start_line=X, end_line=Y) 分段读取特定部分。
"""
    
    return content
```

**focused_files 总量控制：**

```python
@dataclass
class CodeContext:
    max_total_chars: int = 100000  # focused_files 总字符数限制
    
    def add_file(self, path: str, content: str, ...):
        # 检查总量
        current_total = sum(len(f.content) for f in self.focused_files)
        
        if current_total + len(content) > self.max_total_chars:
            # 淘汰最旧的非编辑文件
            self._evict_oldest_files(needed_space=len(content))
        
        # 添加文件...
```

**实现方式：**

```python
@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    
    # 标记是否为缩略内容（用于后续消息构建）
    is_abbreviated: bool = False
    full_content_ref: Optional[str] = None  # 如 "focused_files[config.py]"

class ConversationHistory:
    def add_tool_result_for_history(self, tool_call_id: str, tool_name: str, 
                                     result: str, file_path: str = None):
        """
        添加工具结果到历史记录（用于后续对话）
        注意：这是添加到"历史"中的缩略版本，不是首次返回给 LLM 的内容
        """
        
        if tool_name == "read_file" and file_path:
            # 文件内容已在 focused_files 中，历史只保存引用
            abbreviated = f"[已读取 {file_path}，完整内容见 focused_files]"
            self.messages.append(Message(
                role="tool",
                content=abbreviated,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                is_abbreviated=True,
                full_content_ref=f"focused_files[{file_path}]"
            ))
            
        elif tool_name == "write_file" and file_path:
            abbreviated = f"[已写入 {file_path}，操作成功]"
            self.messages.append(Message(
                role="tool",
                content=abbreviated,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                is_abbreviated=True
            ))
            
        elif tool_name == "shell_exec":
            # shell 结果可能很长，截断保留
            max_len = 2000
            if len(result) > max_len:
                truncated = result[:max_len] + f"\n... [截断，完整输出 {len(result)} 字符]"
            else:
                truncated = result
            self.messages.append(Message(
                role="tool",
                content=truncated,
                tool_call_id=tool_call_id,
                tool_name=tool_name
            ))
            
        else:
            # grep 等其他工具：通常结果较短，完整保留
            self.messages.append(Message(
                role="tool",
                content=result,
                tool_call_id=tool_call_id,
                tool_name=tool_name
            ))
```

**关键区分：首次返回 vs 历史记录**

```python
class Agent:
    def _execute_tool(self, tool_call):
        """执行工具调用"""
        tool_name = tool_call.name
        result = self.tool_registry.execute(tool_call)
        
        # 1. 首次返回给 LLM：完整内容（不截断！）
        yield ToolResultEvent(
            tool_call_id=tool_call.id,
            tool_name=tool_name,
            result=result  # 完整内容，LLM 需要看到全部
        )
        
        # 2. 如果是文件操作，更新 focused_files（完整内容）
        if tool_name == "read_file":
            file_path = tool_call.arguments["path"]
            self.agent_context.code_context.add_file(
                path=file_path,
                content=result,  # 完整内容！
                is_editing=False
            )
        
        # 3. 添加到历史记录（缩略版本，供后续对话使用）
        self.agent_context.conversation.add_tool_result_for_history(
            tool_call_id=tool_call.id,
            tool_name=tool_name,
            result=result,
            file_path=tool_call.arguments.get("path")
        )
```

**发送给 LLM 时的消息构建：**

```python
def _build_messages(self) -> List[BaseMessage]:
    messages = []
    
    # 1. System 消息：包含 code_context（文件内容在这里）
    system_content = self._build_system_prompt()
    system_content += "\n\n## 当前代码上下文\n"
    system_content += self.agent_context.code_context.to_context_string()
    messages.append(SystemMessage(content=system_content))
    
    # 2. 对话历史：工具结果是缩略的，避免重复
    for msg in self.agent_context.conversation.messages:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content, tool_calls=msg.tool_calls))
        elif msg.role == "tool":
            # 缩略内容，LLM 知道完整内容在 system 消息的 code_context 中
            messages.append(ToolMessage(content=msg.content, tool_call_id=msg.tool_call_id))
    
    return messages
```

**示例：实际发送给 LLM 的消息结构**

```
[System Message]
你是一个代码助手...

## 当前代码上下文
### config.py
```python
# 完整的 500 行代码在这里
DATABASE_URL = "..."
...
```

[Human Message]
读取 config.py 并告诉我数据库配置

[AI Message]
好的，让我读取这个文件。
tool_calls: [{ name: "read_file", args: { path: "config.py" } }]

[Tool Message]  ← 这里是缩略的！
[已读取 config.py，内容见 code_context.focused_files]

[AI Message]
根据 config.py 的内容，数据库配置是...
```

**这样做的好处：**
1. **节省 token**：文件内容只出现一次（在 system 消息中）
2. **避免不一致**：只有一个"真实来源"
3. **LLM 能理解**：通过引用知道去哪里找完整内容

### 3.3 简化后的 Agent 结构

```python
class CodeAgent:
    def __init__(self, ...):
        # 使用完整的 CodeAgentContext（跨多轮对话持续）
        self.agent_context = CodeAgentContext(
            session_id=session_id,
            project_id=project_id,
            code_context=CodeContext(workspace_root=project_path),
            execution_context=ExecutionContext(),
            memory=MemoryContext(),
            conversation=ConversationHistory(),  # 新增：对话历史
        )
        
        # 工具注册（包含 create_plan）
        self.tools = [read_file, write_file, grep, shell_exec, create_plan, ...]
        
    def chat_stream(self, user_input: str):
        """主入口 - 双模式支持"""
        
        # 1. 添加用户消息到对话历史
        self.agent_context.conversation.add_user_message(user_input)
        
        # 2. 构建发送给 LLM 的消息
        messages = self._build_messages()
        
        # 3. 第一次 LLM 调用
        response = self.llm.invoke(messages, tools=self.tools)
        
        # 4. 检查是否是 Plan 模式
        plan_call = find_tool_call(response, "create_plan")
        
        if plan_call:
            # Plan 模式
            yield {"type": "response_start", "mode": "plan"}
            yield from self._execute_plan_mode(plan_call)
        else:
            # 普通模式（工具调用循环）
            yield {"type": "response_start", "mode": "direct"}
            yield from self._execute_direct_mode(response)
        
        # 5. 淘汰旧上下文
        self.agent_context.conversation.evict_old_messages()
    
    def _build_messages(self) -> List[BaseMessage]:
        """构建发送给 LLM 的消息"""
        messages = []
        
        # 系统消息（包含代码上下文）
        system_content = self._build_system_prompt()
        system_content += "\n\n" + self.agent_context.code_context.to_context_string()
        messages.append(SystemMessage(content=system_content))
        
        # 对话历史
        messages.extend(self.agent_context.conversation.to_langchain_messages())
        
        return messages
```

**关键改进：**
1. 使用现有的 `CodeAgentContext`，避免重复设计
2. 在 `CodeAgentContext` 中添加 `ConversationHistory` 
3. 支持 Plan 和 Direct 两种模式
4. 通过 `response_start` 事件告知前端是哪种模式

### 3.4 删除冗余代码

需要删除的代码：
- `approve_plan()` 方法
- `reject_plan()` 方法  
- `PlanStatus.AWAITING_APPROVAL` 状态
- 所有 `auto_approve` 相关逻辑

### 3.5 激活 CodeAgentContext

**核心改动：** 在 `agent.py` 的 `__init__` 中实例化 `CodeAgentContext`，并在与 LLM 交互时使用其 `to_dict()` / `to_json()` 方法。

详见 3.3 节的代码示例。

**额外建议：** 可以利用 `CodeAgentContext` 的结构化输出，将完整上下文以 JSON 形式发送给 LLM：

```python
def _build_context_for_llm(self) -> str:
    """构建发送给 LLM 的上下文（可选的 JSON 模式）"""
    return self.agent_context.to_json()
```

---

## 四、实施计划

### Phase 1: 清理冗余代码（1-2h）
- [ ] 删除 `approve_plan()`、`reject_plan()` 方法
- [ ] 删除 `auto_approve` 参数和逻辑
- [ ] 简化 `run()` 方法流程
- [ ] 删除 `AWAITING_APPROVAL` 状态

### Phase 2: 实现持续上下文（3-4h）
- [ ] 在 context.py 中添加 `Message` 和 `ConversationHistory` 类
- [ ] 在 `CodeAgentContext` 中添加 `conversation` 字段
- [ ] 实现上下文淘汰策略
- [ ] 实现上下文去重（历史缩略，focused_files 完整）
- [ ] 修改 `chat_stream()` 使用持续上下文

### Phase 3: 实现双模式支持（4-6h）
- [ ] 添加 `create_plan` 工具
- [ ] 实现模式判断逻辑（根据是否调用 create_plan）
- [ ] 添加 `response_start` 事件（含 mode 字段）
- [ ] 实现 `_execute_plan_mode()` 和 `_execute_direct_mode()`

### Phase 4: 激活 CodeAgentContext（2-3h）
- [ ] 重构 agent.py 使用完整的 `CodeAgentContext`
- [ ] 实现 `MemoryContext` 记忆功能
- [ ] 实现 `ExecutionContext` 跟踪

### Phase 5: 扩展 SymbolIndex（4-6h）🆕
- [ ] 新增 `SymbolInfo` 数据类（含签名、行号、文档）
- [ ] 扩展 `SymbolIndex`：添加 `symbols_by_file` 和 `dependencies`
- [ ] 实现代码解析（可用 tree-sitter 或 AST/正则）
- [ ] 实现 `to_repo_map_string()` 方法
- [ ] 在 agent.py 中使用 symbol_index（当前未使用）

---

## 五、工具调用循环模式详解

### 5.1 与 ReAct 模式的关系

ReAct（Reasoning + Acting）是学术上的一种 Agent 模式，但实际产品中可能简化为：

**学术 ReAct：**
```
Thought: 我需要先了解项目结构...
Action: list_directory(path=".")
Observation: [main.py, utils/, ...]
Thought: 看到有 utils 目录...
```

**实际产品（如 Cursor）可能的实现：**
```
LLM 直接调用工具，不需要显式输出 "Thought"
界面上显示 "thinking..." 只是表示 LLM 在处理中
工具调用结果自动加入上下文，LLM 继续响应
```

**关键点：** Cursor 的 "thought 5s" 显示的可能就是 LLM 调用 grep/search 等工具的过程，而不是一个独立的"思考阶段"。

### 5.2 上下文窗口管理

```python
class ContextWindow:
    max_tokens: int = 128000  # 模型上下文限制
    
    def fit_context(self, messages: List[Message]) -> List[Message]:
        """确保上下文不超过限制"""
        total_tokens = sum(m.tokens for m in messages)
        
        while total_tokens > self.max_tokens * 0.8:  # 留 20% 余量
            # 优先移除旧的非关键消息
            removed = self._evict_oldest_non_critical()
            total_tokens -= removed.tokens
```

### 5.3 工具调用循环

```python
async def tool_loop(self, max_iterations=20):
    """工具调用循环，直到 LLM 不再调用工具"""
    for i in range(max_iterations):
        response = await self.llm.invoke(self.context.to_messages())
        
        if not response.tool_calls:
            # 没有工具调用，返回最终响应
            return response.content
        
        # 执行工具调用
        for tool_call in response.tool_calls:
            result = await self.execute_tool(tool_call)
            self.context.add_tool_result(tool_call.id, result)
```

---

## 六、问题与建议汇总

| 问题 | 严重程度 | 建议 |
|------|---------|------|
| 强制 Plan 模式 | 高 | 添加 create_plan 工具，让 LLM 自主决定 |
| 上下文断裂 | 高 | 在 CodeAgentContext 中添加 ConversationHistory |
| 冗余审批流程 | 中 | 直接删除 approve/reject 相关代码 |
| CodeAgentContext 闲置 | 中 | 在 agent.py 中实例化并使用 |

---

## 七、Plan 模式的复杂性分析（重点）

> 根据观察，Cursor 对于简单问题不生成 Plan，但复杂问题会生成 Plan，且 Plan 的界面交互与普通响应完全不同。这里需要深入分析。

### 7.1 核心问题：如何知道 LLM 返回的是 Plan？

这是整个架构设计中最复杂的问题之一。可能的实现方式：

**方式 A：LLM 自主决定 + 结构化输出**
```
System Prompt 中告诉 LLM：
- 如果任务简单，直接执行并回答
- 如果任务复杂，先输出一个 JSON 格式的 Plan

问题：
- 如何可靠地解析？LLM 输出可能不稳定
- 流式输出时，如何提前知道是 Plan 还是普通响应？
```

**方式 B：LLM 调用 "create_plan" 工具**
```python
# 定义一个特殊的工具
def create_plan(steps: List[Step]) -> Plan:
    """当任务复杂时，LLM 调用此工具创建计划"""
    pass

# LLM 的决策过程：
# 1. 分析任务复杂度
# 2. 简单任务 → 直接调用 read_file/write_file 等工具
# 3. 复杂任务 → 调用 create_plan 工具

优点：
- 通过工具调用明确区分是否是 Plan
- 前端可以根据 tool_call.name == "create_plan" 切换 UI 模式
```

**方式 C：两阶段调用**
```
第一次 LLM 调用（判断阶段）：
  Prompt: "分析这个任务，返回 {mode: 'direct' | 'plan'}"
  
根据返回的 mode：
  - direct → 进入工具调用循环模式
  - plan → 进入 Plan 生成和执行模式

问题：
- 多一次 LLM 调用，延迟增加
- 但这样逻辑最清晰
```

### 7.2 Plan 模式 vs 普通模式的界面差异

| 方面 | 普通响应模式 | Plan 模式 |
|------|-------------|-----------|
| 界面展示 | 流式文本 + 穿插的工具调用 | 计划步骤列表 + 逐步执行进度 |
| 用户交互 | 被动观看 | 可能可以修改/确认计划 |
| 执行控制 | LLM 自主决定何时结束 | 按步骤执行，每步有明确边界 |
| 进度感知 | 不清楚还要多久 | 清楚知道"第 2/5 步" |
| 错误处理 | LLM 自行处理 | 可以回滚到某一步 |

### 7.3 前端如何区分两种模式？

**关键挑战：** 前端需要在收到响应的早期就知道是哪种模式，以便渲染正确的 UI。

**可能的事件流设计：**

```python
# 普通响应模式的事件流
yield {"type": "response_start", "mode": "direct"}
yield {"type": "token", "content": "让我来..."}
yield {"type": "tool_call", "tool": "read_file", ...}
yield {"type": "tool_result", ...}
yield {"type": "token", "content": "根据文件内容..."}
yield {"type": "response_end"}

# Plan 模式的事件流
yield {"type": "response_start", "mode": "plan"}
yield {"type": "plan_created", "plan": {"steps": [...]}}
yield {"type": "step_start", "step_index": 0, "step": {...}}
yield {"type": "tool_call", ...}
yield {"type": "tool_result", ...}
yield {"type": "step_complete", "step_index": 0}
yield {"type": "step_start", "step_index": 1, ...}
...
yield {"type": "plan_complete"}
```

**核心：** 需要在第一个事件中就告诉前端是哪种模式（`mode: "direct" | "plan"`）

### 7.4 何时生成 Plan？决策逻辑

```
用户输入分类：
├── 简单问答 → 直接回答，无需工具
│   例："这个函数是做什么的？"
│
├── 简单操作 → 工具调用循环，无需 Plan
│   例："把这个变量名从 foo 改成 bar"
│   例："读取 config.py 的内容"
│
├── 中等复杂 → 边界模糊，LLM 自行决定
│   例："给这个函数添加错误处理"
│   例："优化这段代码的性能"
│
└── 复杂任务 → 需要 Plan
    例："实现一个用户认证系统"
    例："重构整个模块的架构"
    例："修复这个涉及多个文件的 bug"
```

**LLM 判断依据可能包括：**
1. 任务描述的长度和复杂度
2. 涉及的文件数量（需要先分析）
3. 是否涉及多个相互依赖的修改
4. 用户是否明确要求"分步骤"

### 7.5 实现方案对比

| 方案 | 复杂度 | 可靠性 | 延迟 | 推荐度 |
|------|--------|--------|------|--------|
| A: 结构化输出自动解析 | 中 | 低 | 低 | ⭐⭐ |
| B: create_plan 工具 | 中 | 高 | 低 | ⭐⭐⭐⭐ |
| C: 两阶段调用 | 高 | 高 | 高 | ⭐⭐⭐ |
| D: 混合方案（推荐） | 高 | 高 | 中 | ⭐⭐⭐⭐⭐ |

**推荐方案 D（混合方案）：**

```python
class Agent:
    def chat_stream(self, user_input: str):
        # 工具列表包含 create_plan
        tools = [
            read_file, write_file, grep, shell_exec,
            create_plan,  # 特殊工具：创建执行计划
        ]
        
        # 第一次 LLM 调用
        response = self.llm.invoke(messages, tools=tools)
        
        # 检查 LLM 是否调用了 create_plan
        plan_call = find_tool_call(response, "create_plan")
        
        if plan_call:
            # Plan 模式
            yield {"type": "response_start", "mode": "plan"}
            plan = plan_call.arguments
            yield {"type": "plan_created", "plan": plan}
            yield from self._execute_plan(plan)
        else:
            # 普通模式（工具调用循环）
            yield {"type": "response_start", "mode": "direct"}
            yield from self._tool_loop(response)
```

### 7.6 create_plan 工具的设计

```python
from pydantic import BaseModel
from typing import List

class PlanStep(BaseModel):
    """计划中的单个步骤"""
    index: int
    title: str
    description: str
    expected_tools: List[str]  # 预期使用的工具

class Plan(BaseModel):
    """执行计划"""
    goal: str
    steps: List[PlanStep]
    estimated_complexity: str  # low/medium/high

# 作为 LLM 工具
def create_plan(plan: Plan) -> str:
    """
    当任务复杂，需要多个步骤完成时，调用此工具创建执行计划。
    
    使用场景：
    - 任务涉及多个文件的修改
    - 任务有多个相互依赖的子任务
    - 任务需要先分析再实施
    
    不应使用场景：
    - 简单的代码修改
    - 单文件操作
    - 简单问答
    """
    return f"计划已创建，共 {len(plan.steps)} 个步骤"
```

---

## 八、与当前实现的对比

### 8.1 当前实现的问题（重新审视）

```python
# 当前 agent.py 的问题：

# 问题 1：强制 Plan，没有判断逻辑
def run(self, task: str, ...):
    plan = self.planner.create_plan_sync(task, context)  # 每次都生成 Plan
    # 没有判断任务是否需要 Plan

# 问题 2：没有 create_plan 工具的概念
# LLM 没有选择权，被动接受"必须生成 Plan"

# 问题 3：前端无法区分模式
# 缺少 {"type": "response_start", "mode": "plan|direct"}
```

### 8.2 需要修改的核心点

| 修改点 | 当前状态 | 目标状态 |
|--------|---------|---------|
| Plan 生成 | 强制生成 | LLM 通过工具决定是否生成 |
| 模式区分 | 无 | 事件流第一个事件标明模式 |
| 上下文 | 每次重建 | 持续继承 |
| 工具列表 | 固定 | 包含 create_plan 工具 |

---

## 九、实施路线图（精简版）

> 详细步骤见第四章

| 阶段 | 内容 | 预估时间 |
|------|------|---------|
| Phase 1 | 清理冗余代码（approve/reject） | 1-2h |
| Phase 2 | 实现持续上下文（ConversationHistory） | 3-4h |
| Phase 3 | 实现双模式支持（create_plan 工具） | 4-6h |
| Phase 4 | 激活 CodeAgentContext | 2-3h |

**总计：约 10-15 小时**

---

## 十、Aider 调研：Repo Map（必须补充）

> 基于对 Aider 开源项目的调研，以下是当前方案**缺失但必须有**的关键特性。

### 10.1 Repo Map（代码结构映射）

**Aider 的实现：**
- 使用 tree-sitter 解析整个代码库
- 生成文件/函数/类/依赖关系的结构化映射
- 帮助 LLM 快速理解项目结构，而不需要读取所有文件内容

**当前已有的字段（未使用）：**

```python
# context.py 已有！
@dataclass
class SymbolIndex:
    """代码符号索引"""
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    variables: List[str] = field(default_factory=list)

@dataclass
class CodeContext:
    symbol_index: Optional[SymbolIndex] = None  # 已存在但从未使用！
```

**现有 SymbolIndex 的不足：**

| 方面 | 现有 SymbolIndex | Aider RepoMap |
|------|-----------------|---------------|
| 粒度 | 只有名称列表 | 有签名、行号、文档 |
| 组织方式 | 全局列表 | 按文件分组 |
| 依赖关系 | ❌ 没有 | ✅ 有 |

**建议：扩展现有 SymbolIndex，而非新建类**

```python
@dataclass
class SymbolInfo:
    """代码符号详细信息（新增）"""
    name: str
    type: Literal["class", "function", "method", "variable"]
    file_path: str
    line_start: int
    line_end: int
    signature: str  # 如 "def foo(x: int) -> bool"
    docstring: Optional[str] = None

@dataclass
class SymbolIndex:
    """代码符号索引（扩展）"""
    # 保留原有字段（向后兼容）
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    variables: List[str] = field(default_factory=list)
    
    # 新增：详细符号信息（按文件分组）
    symbols_by_file: Dict[str, List[SymbolInfo]] = field(default_factory=dict)
    
    # 新增：依赖关系
    dependencies: Dict[str, List[str]] = field(default_factory=dict)  # {file: [imported_files]}
    
    def get_file_summary(self, file_path: str) -> str:
        """获取文件的符号摘要（用于发送给 LLM）"""
        symbols = self.symbols_by_file.get(file_path, [])
        lines = [f"# {file_path}"]
        for s in symbols:
            lines.append(f"  {s.type}: {s.signature}")
        return "\n".join(lines)
    
    def to_repo_map_string(self) -> str:
        """生成完整的 repo map 字符串"""
        ...
```

**使用场景：**
- Plan 阶段：LLM 通过 symbol_index 快速判断需要修改哪些文件
- 工具调用：减少不必要的 read_file 调用
- 节省 token：符号摘要比完整文件内容小得多

**示例输出（发送给 LLM）：**
```
# backend/agent/code_agent/agent.py
  class: PlanExecuteAgent
  function: def __init__(self, project_path, user_id, ...)
  function: def run(self, task, auto_approve) -> Generator
  function: def chat_stream(self, user_input) -> Generator
  
# backend/agent/code_agent/context.py
  class: CodeContext
  class: CodeAgentContext
  function: def to_dict(self) -> Dict
```

---

## 十一、待确认问题

1. **create_plan 工具的 prompt 如何设计？** 如何让 LLM 准确判断何时使用
2. **Plan 执行中的错误处理？** 是否允许回滚、跳过、重试
3. **前端 UI 设计？** Plan 模式需要完全不同的组件
4. **是否需要用户确认 Plan？** Cursor 似乎是自动执行的

---

## 十一、总结

### 核心洞察

**Plan 模式的复杂性远超最初的理解：**

1. **不是"有没有 Plan"的问题**，而是"何时需要 Plan"+"如何让 LLM 自主决定"
2. **前端需要在响应早期就知道模式**，以便渲染正确的 UI
3. **create_plan 作为工具**是一个优雅的解决方案，让 LLM 有选择权

### 架构决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Plan 触发方式 | LLM 调用 create_plan 工具 | 让 LLM 自主决定，无需额外判断调用 |
| 模式通知 | 首个事件包含 mode 字段 | 前端可立即切换 UI |
| 上下文管理 | 持续继承 + 淘汰策略 | 符合生产级要求 |

### 风险提示

1. **LLM 判断不准确** - 可能简单任务也生成 Plan，需要优化 prompt
2. **前端改动较大** - 需要支持两种完全不同的 UI 模式
3. **调试困难** - 模式切换增加了系统复杂度
