"""
Agent 事件模块

提供类型安全的事件定义，用于 Agent 与前端通信。
"""

from .types import EventType

# 基础事件
from .base import (
    BaseEvent,
    MessageEvent,
    ErrorEvent,
    StatusEvent,
    TokenEvent,
    FileChangeEvent,
    AnomalyDetectedEvent,
    ReplanWarningEvent,
    ResponseStartEvent,
    ResponseEndEvent,
)

# 计划生命周期事件
from .plan_events import (
    PlanCreatedEvent,
    # PlanCompletedEvent 已合并到 PlanExecutionCompletedEvent
    # 审批相关事件已删除（不使用审批流程）
)

# 步骤事件
from .step_events import (
    StepStartedEvent,
    StepCompletedEvent,
    StepOutputEvent,
    StepErrorEvent,
)

# 执行事件
from .execution_events import (
    # 计划执行
    PlanExecutionStartedEvent,
    PlanExecutionCompletedEvent,
    PlanExecutionFailedEvent,
    PlanExecutionCancelledEvent,
    # 文件运行
    FileRunStartedEvent,
    FileRunStdoutEvent,
    FileRunStderrEvent,
    FileRunExitEvent,
)

# 工具事件
from .tool_events import (
    ToolCallsEvent,
    ToolResultEvent,
)


__all__ = [
    # 枚举
    'EventType',
    
    # 基础事件
    'BaseEvent',
    'MessageEvent',
    'ErrorEvent',
    'StatusEvent',
    'TokenEvent',
    'FileChangeEvent',
    'AnomalyDetectedEvent',
    'ReplanWarningEvent',
    'ResponseStartEvent',
    'ResponseEndEvent',
    
    # 计划生命周期
    'PlanCreatedEvent',
    # PlanCompletedEvent 已合并到 PlanExecutionCompletedEvent
    # 审批相关事件已删除
    
    # 步骤
    'StepStartedEvent',
    'StepCompletedEvent',
    'StepOutputEvent',
    'StepErrorEvent',
    
    # 计划执行
    'PlanExecutionStartedEvent',
    'PlanExecutionCompletedEvent',
    'PlanExecutionFailedEvent',
    'PlanExecutionCancelledEvent',
    
    # 文件运行
    'FileRunStartedEvent',
    'FileRunStdoutEvent',
    'FileRunStderrEvent',
    'FileRunExitEvent',
    
    # 工具
    'ToolCallsEvent',
    'ToolResultEvent',
]

