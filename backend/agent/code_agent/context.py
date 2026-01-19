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
    

@dataclass
class SymbolIndex:
    """代码符号索引"""
    classes: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    variables: List[str] = field(default_factory=list)


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
        
        parts = ["## 活跃文件内容"]
        
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


@dataclass
class MemoryContext:
    """记忆上下文"""
    project_conventions: List[str] = field(default_factory=list)
    recent_decisions: List[Decision] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_conventions": self.project_conventions,
            "recent_decisions": [
                {"decision": d.decision, "reason": d.reason}
                for d in self.recent_decisions[-10:]  # 只保留最近10条
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
    """代码 Agent 完整上下文"""
    
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
    
    # 执行上下文
    execution_context: Optional[ExecutionContext] = None
    
    # 工具
    tools: List[ToolDef] = field(default_factory=list)
    
    # 记忆
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

