"""
代码 Agent 模块
提供 Python 量化代码生成和执行功能

核心类: PlanExecuteAgent (别名 CodeAgent)
- 支持 Plan-Execute 架构，任务规划与执行
- 提供 chat_stream() 流式对话接口
- 通过工具系统执行文件操作和命令
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

# 事件系统
from .events import (
    EventType,
    # 基础事件
    BaseEvent, MessageEvent, ErrorEvent, StatusEvent, TokenEvent,
    FileChangeEvent, AnomalyDetectedEvent, ReplanWarningEvent,
    ResponseStartEvent, ResponseEndEvent,
    # 计划生命周期
    PlanCreatedEvent,
    # 计划执行
    PlanExecutionStartedEvent, PlanExecutionCompletedEvent,
    PlanExecutionFailedEvent, PlanExecutionCancelledEvent,
    # 步骤
    StepStartedEvent, StepCompletedEvent, StepOutputEvent, StepErrorEvent,
    # 工具
    ToolCallsEvent, ToolResultEvent,
    # 文件运行
    FileRunStartedEvent, FileRunStdoutEvent, FileRunStderrEvent, FileRunExitEvent,
)

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
    # Repo Map / Symbol Index
    SymbolIndex,
    SymbolInfo,
    FileSymbols,
    FileInfo,
    ConversationHistory,
    Message,
    # 辅助函数
    parse_python_symbols,
    build_symbol_index,
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
    
    # 事件系统
    'EventType',
    'BaseEvent', 'MessageEvent', 'ErrorEvent', 'StatusEvent', 'TokenEvent',
    'FileChangeEvent', 'AnomalyDetectedEvent', 'ReplanWarningEvent',
    'ResponseStartEvent', 'ResponseEndEvent',
    'PlanCreatedEvent',
    'PlanExecutionStartedEvent', 'PlanExecutionCompletedEvent',
    'PlanExecutionFailedEvent', 'PlanExecutionCancelledEvent',
    'StepStartedEvent', 'StepCompletedEvent', 'StepOutputEvent', 'StepErrorEvent',
    'ToolCallsEvent', 'ToolResultEvent',
    'FileRunStartedEvent', 'FileRunStdoutEvent', 'FileRunStderrEvent', 'FileRunExitEvent',
    
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
    
    # Repo Map / Symbol Index
    'SymbolIndex',
    'SymbolInfo',
    'FileSymbols',
    'FileInfo',
    'ConversationHistory',
    'Message',
    'parse_python_symbols',
    'build_symbol_index',
]
