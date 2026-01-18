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
    max_content_per_file: int = 5000  # 每个文件最大字符数
    
    def add_file(self, path: str, content: str, language: str = "python"):
        """添加或更新活跃文件"""
        # 检查是否已存在
        for f in self.focused_files:
            if f.path == path:
                f.content = content[:self.max_content_per_file]
                return
        
        # 添加新文件
        self.focused_files.append(FileInfo(
            path=path,
            content=content[:self.max_content_per_file],
            language=language
        ))
        
        # 保持文件数在限制内（移除最早的）
        while len(self.focused_files) > self.max_files:
            self.focused_files.pop(0)
    
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
        """转换为 LLM 可读的上下文字符串"""
        if not self.focused_files:
            return ""
        
        parts = ["## 活跃文件内容（已读取/修改的文件）"]
        for f in self.focused_files:
            parts.append(f"\n### {f.path}")
            parts.append(f"```{f.language}\n{f.content}\n```")
        
        return "\n".join(parts)


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

