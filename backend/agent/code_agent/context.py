"""
代码 Agent 上下文结构定义
定义 Agent 与 LLM 通信的数据结构
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime
import json


@dataclass
class FileInfo:
    """文件信息"""
    path: str
    content: str = ""
    language: str = "python"
    cursor: Optional[Dict[str, int]] = None  # {"line": 0, "column": 0}
    is_editing: bool = False  # 是否正在编辑（正在编辑的文件保留完整内容）
    original_length: int = 0  # 原始内容长度（用于检测是否被截断）
    is_truncated: bool = False  # 是否被截断


# ==================== Repo Map / Symbol Index ====================

@dataclass
class SymbolInfo:
    """符号详细信息
    
    存储单个符号（类、函数、变量等）的详细信息，
    包括位置、签名、文档字符串等。
    """
    name: str
    symbol_type: Literal["class", "function", "method", "variable", "import", "constant"]
    file_path: str
    line_start: int
    line_end: int = 0
    signature: str = ""  # 函数/方法签名，如 "def foo(a: int, b: str) -> bool"
    docstring: str = ""  # 文档字符串（截取前 200 字符）
    parent: Optional[str] = None  # 父类/父函数名（用于方法）
    decorators: List[str] = field(default_factory=list)  # 装饰器列表
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.symbol_type,
            "file": self.file_path,
            "line": self.line_start,
            "signature": self.signature,
            "docstring": self.docstring[:200] if self.docstring else "",
            "parent": self.parent,
        }


@dataclass
class FileSymbols:
    """单个文件的符号信息"""
    path: str
    language: str = "python"
    symbols: List[SymbolInfo] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)  # 导入的模块/符号
    exports: List[str] = field(default_factory=list)  # 导出的符号（__all__）
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "symbols": [s.to_dict() for s in self.symbols],
            "imports": self.imports,
            "exports": self.exports,
        }


@dataclass
class SymbolIndex:
    """代码符号索引（Repo Map）
    
    提供项目代码结构的全局视图，帮助 LLM 理解代码库：
    - 文件级别的符号映射
    - 符号间的依赖关系
    - 快速符号查找
    
    与 Aider 的 Repo Map 类似，但更轻量。
    """
    # 原有简单字段（兼容）
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    variables: List[str] = field(default_factory=list)
    
    # 新增：详细文件符号映射
    file_symbols: Dict[str, FileSymbols] = field(default_factory=dict)  # path -> FileSymbols
    
    # 新增：符号到文件的反向索引（快速查找）
    symbol_to_files: Dict[str, List[str]] = field(default_factory=dict)  # symbol_name -> [file_paths]
    
    # 新增：文件依赖关系
    dependencies: Dict[str, List[str]] = field(default_factory=dict)  # file -> [imported_files]
    
    def add_file_symbols(self, file_symbols: FileSymbols) -> None:
        """添加文件的符号信息"""
        self.file_symbols[file_symbols.path] = file_symbols
        
        # 更新简单字段（兼容）
        for symbol in file_symbols.symbols:
            if symbol.symbol_type == "class" and symbol.name not in self.classes:
                self.classes.append(symbol.name)
            elif symbol.symbol_type in ("function", "method") and symbol.name not in self.functions:
                self.functions.append(symbol.name)
            elif symbol.symbol_type == "variable" and symbol.name not in self.variables:
                self.variables.append(symbol.name)
            
            # 更新反向索引
            if symbol.name not in self.symbol_to_files:
                self.symbol_to_files[symbol.name] = []
            if file_symbols.path not in self.symbol_to_files[symbol.name]:
                self.symbol_to_files[symbol.name].append(file_symbols.path)
        
        # 更新导入列表
        for imp in file_symbols.imports:
            if imp not in self.imports:
                self.imports.append(imp)
    
    def find_symbol(self, name: str) -> List[SymbolInfo]:
        """根据名称查找符号"""
        results = []
        files = self.symbol_to_files.get(name, [])
        for file_path in files:
            file_sym = self.file_symbols.get(file_path)
            if file_sym:
                for symbol in file_sym.symbols:
                    if symbol.name == name:
                        results.append(symbol)
        return results
    
    def get_file_summary(self, path: str) -> Optional[Dict[str, Any]]:
        """获取文件的符号摘要"""
        file_sym = self.file_symbols.get(path)
        if not file_sym:
            return None
        return file_sym.to_dict()
    
    def to_repo_map_string(self, max_files: int = 20) -> str:
        """生成 Repo Map 字符串（用于发送给 LLM）
        
        格式类似于 Aider 的 repo map：
        ```
        src/utils.py:
          - class Config
          - def load_config(path: str) -> Config
          - def save_config(config: Config, path: str)
        
        src/main.py:
          - def main()
          - class Application
        ```
        """
        lines = []
        for i, (path, file_sym) in enumerate(self.file_symbols.items()):
            if i >= max_files:
                lines.append(f"... 还有 {len(self.file_symbols) - max_files} 个文件")
                break
            
            lines.append(f"{path}:")
            for symbol in file_sym.symbols[:10]:  # 每个文件最多显示 10 个符号
                if symbol.signature:
                    lines.append(f"  - {symbol.signature}")
                else:
                    lines.append(f"  - {symbol.symbol_type} {symbol.name}")
            
            if len(file_sym.symbols) > 10:
                lines.append(f"  ... 还有 {len(file_sym.symbols) - 10} 个符号")
            lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "classes": self.classes,
            "functions": self.functions,
            "imports": self.imports,
            "variables": self.variables,
            "file_count": len(self.file_symbols),
            "total_symbols": sum(len(fs.symbols) for fs in self.file_symbols.values()),
            "files": {
                path: fs.to_dict() 
                for path, fs in list(self.file_symbols.items())[:10]  # 只返回前 10 个文件
            }
        }


@dataclass
class CodeContext:
    """代码上下文"""
    workspace_root: str
    file_tree: List[str] = field(default_factory=list)
    focused_files: List[FileInfo] = field(default_factory=list)  # 活跃文件列表
    symbol_index: Optional[SymbolIndex] = None
    max_files: int = 10  # 最多保留的活跃文件数
    max_content_per_file: int = 10000  # 每个文件最大字符数（从 5000 提升到 10000）
    max_editing_files: int = 3  # 正在编辑的文件数量限制（这些文件保留完整内容）
    
    def add_file(self, path: str, content: str, language: str = "python", is_editing: bool = False):
        """
        添加或更新活跃文件
        
        Args:
            path: 文件路径
            content: 文件内容
            language: 编程语言
            is_editing: 是否正在编辑（正在编辑的文件保留完整内容，不截断）
        """
        original_length = len(content)
        
        # 决定是否截断
        if is_editing:
            # 正在编辑的文件保留完整内容
            truncated_content = content
            is_truncated = False
        elif original_length > self.max_content_per_file:
            # 超过限制，截断并添加提示
            truncated_content = content[:self.max_content_per_file]
            truncated_content += f"\n\n# ... [内容已截断，原始长度: {original_length} 字符，显示前 {self.max_content_per_file} 字符]"
            truncated_content += f"\n# 如需查看完整内容，请使用 read_file 工具"
            is_truncated = True
        else:
            truncated_content = content
            is_truncated = False
        
        # 检查是否已存在
        for f in self.focused_files:
            if f.path == path:
                f.content = truncated_content
                f.is_editing = is_editing
                f.original_length = original_length
                f.is_truncated = is_truncated
                # 如果标记为编辑，将其移到列表末尾（最近使用）
                if is_editing:
                    self.focused_files.remove(f)
                    self.focused_files.append(f)
                return
        
        # 添加新文件
        self.focused_files.append(FileInfo(
            path=path,
            content=truncated_content,
            language=language,
            is_editing=is_editing,
            original_length=original_length,
            is_truncated=is_truncated
        ))
        
        # 保持文件数在限制内
        self._enforce_file_limits()
    
    def mark_as_editing(self, path: str):
        """标记文件为正在编辑状态"""
        for f in self.focused_files:
            if f.path == path:
                f.is_editing = True
                # 移到列表末尾
                self.focused_files.remove(f)
                self.focused_files.append(f)
                return
    
    def _enforce_file_limits(self):
        """
        强制执行文件数量限制
        优先移除非编辑中的旧文件
        """
        # 分离编辑中和非编辑中的文件
        editing_files = [f for f in self.focused_files if f.is_editing]
        non_editing_files = [f for f in self.focused_files if not f.is_editing]
        
        # 如果编辑中的文件超过限制，移除最早的编辑文件
        while len(editing_files) > self.max_editing_files:
            removed = editing_files.pop(0)
            removed.is_editing = False  # 降级为普通文件
            non_editing_files.insert(0, removed)
        
        # 如果总文件数超过限制，优先移除非编辑文件
        total_files = len(editing_files) + len(non_editing_files)
        while total_files > self.max_files and non_editing_files:
            non_editing_files.pop(0)
            total_files -= 1
        
        # 如果还超过限制（不太可能），移除编辑文件
        while total_files > self.max_files and editing_files:
            editing_files.pop(0)
            total_files -= 1
        
        # 重建列表：非编辑文件在前，编辑文件在后
        self.focused_files = non_editing_files + editing_files
    
    def get_file(self, path: str) -> Optional[FileInfo]:
        """获取活跃文件"""
        for f in self.focused_files:
            if f.path == path:
                return f
        return None
    
    def remove_file(self, path: str):
        """移除活跃文件"""
        self.focused_files = [f for f in self.focused_files if f.path != path]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "file_tree": self.file_tree,
            "focused_files": [
                {
                    "path": f.path,
                    "content": f.content,
                    "language": f.language,
                }
                for f in self.focused_files
            ],
            "symbol_index": {
                "classes": self.symbol_index.classes,
                "functions": self.symbol_index.functions,
                "imports": self.symbol_index.imports,
            } if self.symbol_index else None
        }
    
    def to_context_string(self) -> str:
        """转换为 LLM 可读的上下文字符串（仅文件内容，警告在 agent.py 中统一处理）"""
        if not self.focused_files:
            return ""
        
        parts = []
        
        for f in self.focused_files:
            # 构建文件标题，包含状态信息
            status_tags = []
            if f.is_editing:
                status_tags.append("📝编辑中")
            if f.is_truncated:
                status_tags.append(f"⚠️已截断({f.original_length}→{len(f.content)}字符)")
            
            status_str = f" [{', '.join(status_tags)}]" if status_tags else ""
            parts.append(f"\n### {f.path}{status_str}")
            parts.append(f"```{f.language}\n{f.content}\n```")
        
        return "\n".join(parts)
    
    def get_context_summary(self) -> str:
        """获取上下文摘要（用于日志）"""
        editing_count = sum(1 for f in self.focused_files if f.is_editing)
        truncated_count = sum(1 for f in self.focused_files if f.is_truncated)
        return f"{len(self.focused_files)} files ({editing_count} editing, {truncated_count} truncated)"
    
    def get_active_file_paths(self) -> List[str]:
        """获取活跃文件路径列表"""
        return [f.path for f in self.focused_files]


@dataclass
class OutputRecord:
    """执行输出记录"""
    command: str
    exit_code: int
    output: str
    duration_ms: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ProcessInfo:
    """运行中的进程信息"""
    pid: int
    command: str
    start_time: str
    status: Literal["running", "stopped"] = "running"


@dataclass
class ExecutionContext:
    """执行上下文"""
    running_process: Optional[ProcessInfo] = None
    recent_outputs: List[OutputRecord] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "running_process": {
                "pid": self.running_process.pid,
                "command": self.running_process.command,
                "status": self.running_process.status,
            } if self.running_process else None,
            "recent_outputs": [
                {
                    "command": o.command,
                    "exit_code": o.exit_code,
                    "output": o.output[:500] + "..." if len(o.output) > 500 else o.output,
                    "duration_ms": o.duration_ms,
                }
                for o in self.recent_outputs[-5:]  # 只保留最近5条
            ]
        }


@dataclass
class ToolDef:
    """工具定义"""
    name: str
    description: str
    parameters: Optional[Dict[str, Any]] = None


@dataclass
class Decision:
    """历史决策"""
    decision: str
    reason: str


# ==================== 对话历史（新增）====================

@dataclass
class Message:
    """对话消息
    
    用于记录 user/assistant/tool 之间的消息。
    
    去重策略：
    - read_file/write_file 的工具结果在历史中缩略（完整内容在 focused_files）
    - 其他工具结果保留完整
    """
    role: Literal["user", "assistant", "tool"]
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # assistant 消息可能有工具调用
    tool_calls: Optional[List[Dict[str, Any]]] = None
    
    # tool 消息需要关联的 tool_call_id
    tool_call_id: Optional[str] = None
    tool_name: Optional[str] = None
    
    # 去重标记
    is_abbreviated: bool = False  # 是否为缩略内容
    full_content_ref: Optional[str] = None  # 完整内容的引用位置
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "tool_calls": self.tool_calls,
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "is_abbreviated": self.is_abbreviated,
        }


@dataclass
class ConversationHistory:
    """对话历史管理
    
    负责管理当前会话的消息历史，支持：
    - 添加 user/assistant/tool 消息
    - 工具结果去重（与 focused_files 配合）
    - 淘汰旧消息
    
    与 MemoryContext 的区别：
    - ConversationHistory: 短期记忆，当前会话的完整消息
    - MemoryContext: 长期记忆，跨会话的决策摘要
    """
    messages: List[Message] = field(default_factory=list)
    max_messages: int = 50  # 最多保留的消息数
    max_tool_result_chars: int = 2000  # 非文件操作的工具结果最大字符数
    
    def add_user_message(self, content: str):
        """添加用户消息"""
        self.messages.append(Message(
            role="user",
            content=content
        ))
        self._enforce_limits()
    
    def add_assistant_message(self, content: str, tool_calls: List[Dict] = None):
        """添加 assistant 消息"""
        self.messages.append(Message(
            role="assistant",
            content=content,
            tool_calls=tool_calls
        ))
        self._enforce_limits()
    
    def add_tool_result(self, tool_call_id: str, tool_name: str, result: str, 
                        file_path: str = None):
        """添加工具结果（支持去重）
        
        去重策略：
        - read_file: 缩略为引用（完整内容在 focused_files）
        - write_file: 缩略为确认消息
        - 其他工具: 截断保留
        
        Args:
            tool_call_id: 工具调用 ID
            tool_name: 工具名称
            result: 工具执行结果
            file_path: 文件路径（用于 read_file/write_file）
        """
        if tool_name == "read_file" and file_path:
            # 文件内容已在 focused_files 中，只保存引用
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
            # 写入操作只保存确认
            abbreviated = f"[已写入 {file_path}，操作成功]"
            self.messages.append(Message(
                role="tool",
                content=abbreviated,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                is_abbreviated=True
            ))
        elif tool_name == "patch_file" and file_path:
            abbreviated = f"[已修改 {file_path}，操作成功]"
            self.messages.append(Message(
                role="tool",
                content=abbreviated,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                is_abbreviated=True
            ))
        else:
            # 其他工具结果：截断保留
            if len(result) > self.max_tool_result_chars:
                truncated = result[:self.max_tool_result_chars] + f"\n... [截断，原始 {len(result)} 字符]"
            else:
                truncated = result
            self.messages.append(Message(
                role="tool",
                content=truncated,
                tool_call_id=tool_call_id,
                tool_name=tool_name
            ))
        
        self._enforce_limits()
    
    def _enforce_limits(self):
        """淘汰旧消息"""
        if len(self.messages) > self.max_messages:
            # 保留最近的消息，但确保第一条 user 消息不会丢失
            # 简单策略：移除最早的消息
            excess = len(self.messages) - self.max_messages
            self.messages = self.messages[excess:]
    
    def get_recent_messages(self, n: int = 20) -> List[Message]:
        """获取最近 n 条消息"""
        return self.messages[-n:]
    
    def clear(self):
        """清空历史"""
        self.messages = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages": [m.to_dict() for m in self.messages],
            "message_count": len(self.messages)
        }
    
    def to_langchain_messages(self):
        """转换为 LangChain 消息格式
        
        Returns:
            List[BaseMessage]: LangChain 消息列表
        """
        # 延迟导入，避免循环依赖
        from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        
        lc_messages = []
        for msg in self.messages:
            if msg.role == "user":
                lc_messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                if msg.tool_calls:
                    lc_messages.append(AIMessage(
                        content=msg.content,
                        tool_calls=[{
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "args": tc.get("arguments", tc.get("args", {}))
                        } for tc in msg.tool_calls]
                    ))
                else:
                    lc_messages.append(AIMessage(content=msg.content))
            elif msg.role == "tool":
                lc_messages.append(ToolMessage(
                    content=msg.content,
                    tool_call_id=msg.tool_call_id or ""
                ))
        
        return lc_messages


@dataclass
class MemoryContext:
    """记忆上下文
    
    存储长期的、跨会话的决策和项目规范。
    与 ConversationHistory 的区别：
    - ConversationHistory: 短期，存储当前会话的完整对话消息
    - MemoryContext: 长期，存储抽象的决策和经验
    """
    project_conventions: List[str] = field(default_factory=list)
    recent_decisions: List[Decision] = field(default_factory=list)
    decisions: List[Decision] = field(default_factory=list)  # 别名，兼容性
    max_decisions: int = 50  # 最多保留的决策数
    
    def add_decision(self, decision: str, reason: str = "") -> None:
        """添加一条决策记录"""
        d = Decision(decision=decision, reason=reason)
        self.recent_decisions.append(d)
        self.decisions.append(d)
        # 淘汰旧的
        if len(self.recent_decisions) > self.max_decisions:
            self.recent_decisions = self.recent_decisions[-self.max_decisions:]
        if len(self.decisions) > self.max_decisions:
            self.decisions = self.decisions[-self.max_decisions:]
    
    def add_convention(self, convention: str) -> None:
        """添加项目规范"""
        if convention not in self.project_conventions:
            self.project_conventions.append(convention)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_conventions": self.project_conventions,
            "decisions": [
                {"decision": d.decision, "reason": d.reason}
                for d in self.decisions[-10:]  # 只返回最近10条
            ],
            "recent_decisions": [
                {"decision": d.decision, "reason": d.reason}
                for d in self.recent_decisions[-10:]  # 只返回最近10条
            ]
        }


@dataclass
class EnvironmentInfo:
    """环境信息"""
    python_version: str = "3.11"
    installed_packages: List[str] = field(default_factory=list)
    virtual_env: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "python_version": self.python_version,
            "installed_packages": self.installed_packages,
            "virtual_env": self.virtual_env
        }


@dataclass
class SafetyConfig:
    """安全配置"""
    allowed_actions: List[str] = field(default_factory=lambda: ["read", "write", "execute"])
    max_runtime_sec: int = 300  # 默认5分钟
    max_file_size_kb: int = 1024  # 1MB
    restricted_paths: List[str] = field(default_factory=lambda: ["../", "/etc", "/root", "/var"])
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_actions": self.allowed_actions,
            "max_runtime_sec": self.max_runtime_sec,
            "max_file_size_kb": self.max_file_size_kb,
            "restricted_paths": self.restricted_paths
        }


@dataclass
class TaskInfo:
    """任务信息"""
    user_goal: str
    task_type: Literal["generate", "modify", "refactor", "debug", "explain"] = "generate"
    constraints: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_goal": self.user_goal,
            "task_type": self.task_type,
            "constraints": self.constraints
        }


@dataclass
class PlanStep:
    """计划步骤"""
    id: int
    description: str
    status: Literal["pending", "in_progress", "done"] = "pending"


@dataclass
class PlanInfo:
    """执行计划"""
    steps: List[PlanStep] = field(default_factory=list)
    current_step: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [
                {"id": s.id, "description": s.description, "status": s.status}
                for s in self.steps
            ],
            "current_step": self.current_step
        }


@dataclass
class CodeAgentContext:
    """代码 Agent 完整上下文
    
    包含：
    - 元信息（session_id, project_id 等）
    - 任务和计划
    - 代码上下文（focused_files, file_tree）
    - 对话历史（短期，当前会话）
    - 记忆（长期，跨会话的决策摘要）
    - 执行上下文、环境、安全配置等
    """
    
    # 元信息
    session_id: str
    project_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    agent_mode: Literal["code_edit", "debug", "plan", "explain"] = "code_edit"
    
    # 任务
    task: Optional[TaskInfo] = None
    
    # 计划
    plan: Optional[PlanInfo] = None
    
    # 代码上下文
    code_context: Optional[CodeContext] = None
    
    # 对话历史（短期：当前会话的完整消息）
    conversation: Optional[ConversationHistory] = None
    
    # 执行上下文
    execution_context: Optional[ExecutionContext] = None
    
    # 工具
    tools: List[ToolDef] = field(default_factory=list)
    
    # 记忆（长期：跨会话的决策摘要）
    memory: Optional[MemoryContext] = None
    
    # 环境
    environment: Optional[EnvironmentInfo] = None
    
    # 安全
    safety: Optional[SafetyConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于发送给 LLM"""
        return {
            "session_id": self.session_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp,
            "agent_mode": self.agent_mode,
            "task": self.task.to_dict() if self.task else None,
            "plan": self.plan.to_dict() if self.plan else None,
            "code_context": self.code_context.to_dict() if self.code_context else None,
            "conversation": self.conversation.to_dict() if self.conversation else None,
            "execution_context": self.execution_context.to_dict() if self.execution_context else None,
            "tools": [
                {"name": t.name, "description": t.description}
                for t in self.tools
            ],
            "memory": self.memory.to_dict() if self.memory else None,
            "environment": self.environment.to_dict() if self.environment else None,
            "safety": self.safety.to_dict() if self.safety else None,
        }
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# 默认工具列表
DEFAULT_TOOLS = [
    ToolDef(
        name="read_file",
        description="读取指定路径的文件内容",
        parameters={"path": "string"}
    ),
    ToolDef(
        name="write_file",
        description="写入或创建文件",
        parameters={"path": "string", "content": "string"}
    ),
    ToolDef(
        name="list_files",
        description="列出目录下的文件和子目录",
        parameters={"path": "string"}
    ),
    ToolDef(
        name="execute_code",
        description="执行 Python 脚本",
        parameters={"file_path": "string", "timeout_sec": "int"}
    ),
    ToolDef(
        name="search_code",
        description="在项目中搜索代码内容",
        parameters={"query": "string", "file_pattern": "string"}
    ),
]


# ==================== 符号解析辅助函数 ====================

def parse_python_symbols(file_path: str, content: str) -> FileSymbols:
    """解析 Python 文件的符号信息
    
    使用 Python AST 解析文件，提取类、函数、方法等符号信息。
    
    Args:
        file_path: 文件路径
        content: 文件内容
        
    Returns:
        FileSymbols 对象
    """
    import ast
    
    file_symbols = FileSymbols(path=file_path, language="python")
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        # 解析失败，返回空的符号列表
        return file_symbols
    
    def get_docstring(node) -> str:
        """获取节点的文档字符串"""
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) 
            and node.body 
            and isinstance(node.body[0], ast.Expr) 
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
            return node.body[0].value.value
        return ""
    
    def get_function_signature(node) -> str:
        """获取函数签名"""
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)
        
        sig = f"def {node.name}({', '.join(args)})"
        if node.returns:
            sig += f" -> {ast.unparse(node.returns)}"
        return sig
    
    def get_decorators(node) -> List[str]:
        """获取装饰器列表"""
        decorators = []
        for dec in node.decorator_list:
            try:
                decorators.append(ast.unparse(dec))
            except:
                pass
        return decorators
    
    # 只遍历顶级节点（不递归，避免重复处理）
    for node in ast.iter_child_nodes(tree):
        # 顶级类
        if isinstance(node, ast.ClassDef):
            symbol = SymbolInfo(
                name=node.name,
                symbol_type="class",
                file_path=file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                signature=f"class {node.name}",
                docstring=get_docstring(node),
                decorators=get_decorators(node)
            )
            file_symbols.symbols.append(symbol)
            
            # 类中的方法
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method = SymbolInfo(
                        name=item.name,
                        symbol_type="method",
                        file_path=file_path,
                        line_start=item.lineno,
                        line_end=item.end_lineno or item.lineno,
                        signature=get_function_signature(item),
                        docstring=get_docstring(item),
                        parent=node.name,
                        decorators=get_decorators(item)
                    )
                    file_symbols.symbols.append(method)
        
        # 顶级函数
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbol = SymbolInfo(
                name=node.name,
                symbol_type="function",
                file_path=file_path,
                line_start=node.lineno,
                line_end=node.end_lineno or node.lineno,
                signature=get_function_signature(node),
                docstring=get_docstring(node),
                decorators=get_decorators(node)
            )
            file_symbols.symbols.append(symbol)
        
        # 导入
        elif isinstance(node, ast.Import):
            for alias in node.names:
                file_symbols.imports.append(alias.name)
        
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                file_symbols.imports.append(f"{module}.{alias.name}" if module else alias.name)
    
    # 提取 __all__（导出列表）
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                file_symbols.exports.append(elt.value)
    
    return file_symbols


def build_symbol_index(workspace_root: str, file_paths: List[str] = None) -> SymbolIndex:
    """构建项目的符号索引
    
    Args:
        workspace_root: 工作区根目录
        file_paths: 要解析的文件列表（可选，默认解析所有 .py 文件）
        
    Returns:
        SymbolIndex 对象
    """
    import os
    
    index = SymbolIndex()
    
    if file_paths is None:
        # 自动扫描 Python 文件
        file_paths = []
        for root, dirs, files in os.walk(workspace_root):
            # 跳过常见的忽略目录
            dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.plans'}]
            
            for file in files:
                if file.endswith('.py'):
                    file_paths.append(os.path.join(root, file))
    
    for file_path in file_paths:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 计算相对路径
            rel_path = os.path.relpath(file_path, workspace_root)
            
            file_symbols = parse_python_symbols(rel_path, content)
            index.add_file_symbols(file_symbols)
            
        except Exception as e:
            # 忽略读取/解析错误
            pass
    
    return index

