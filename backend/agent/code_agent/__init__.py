"""
代码 Agent 模块
提供 Python 量化代码生成和执行功能

注意：CodeAgent 已废弃，请使用 PlanExecuteAgent
PlanExecuteAgent 提供了向后兼容的 chat_stream() 接口
"""

# Plan-Execute Agent（唯一推荐使用的 Agent）
from .agent import PlanExecuteAgent

# 向后兼容：CodeAgent 作为 PlanExecuteAgent 的别名
CodeAgent = PlanExecuteAgent

# Plan 系统
from .plan import (
    Plan,
    PlanStep,
    PlanStatus,
    StepStatus,
    StepResult,
    PlanTracker,
    Planner
)

# 工具系统
from .tools import (
    BaseTool,
    ToolResult,
    ToolRegistry,
    FunctionCallHandler,
    create_tool_registry
)

# 工作区管理
from .workspace_manager import WorkspaceManager

# 代码执行器
from .executor import CodeExecutor, executor, ExecutionStatus, ExecutionResult

# 上下文定义
from .context import (
    CodeAgentContext,
    CodeContext,
    TaskInfo,
    PlanInfo,
    ExecutionContext,
    MemoryContext,
    EnvironmentInfo,
    SafetyConfig,
    DEFAULT_TOOLS,
)

__all__ = [
    # 主 Agent（唯一推荐）
    'PlanExecuteAgent',
    
    # 向后兼容别名
    'CodeAgent',
    
    # Plan 系统
    'Plan',
    'PlanStep',
    'PlanStatus',
    'StepStatus',
    'StepResult',
    'PlanTracker',
    'Planner',
    
    # 工具系统
    'BaseTool',
    'ToolResult',
    'ToolRegistry',
    'FunctionCallHandler',
    'create_tool_registry',
    
    # 工作区
    'WorkspaceManager',
    
    # 执行器
    'CodeExecutor',
    'executor',
    'ExecutionStatus',
    'ExecutionResult',
    
    # 上下文
    'CodeAgentContext',
    'CodeContext',
    'TaskInfo',
    'PlanInfo',
    'ExecutionContext',
    'MemoryContext',
    'EnvironmentInfo',
    'SafetyConfig',
    'DEFAULT_TOOLS',
]
