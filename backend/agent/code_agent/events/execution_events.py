"""
执行相关事件定义

事件分为两组：
- 计划执行事件 (PlanExecution*): 由 run() → _execute_plan() 触发，执行整个任务计划
- 文件运行事件 (FileRun*): 由 execute_file() 触发，用户手动运行单个 Python 文件
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from .base import BaseEvent, MessageEvent
from .types import EventType


# ============================================================
# 计划执行事件 (Plan Execution)
# 场景：用户发起任务 → Agent 生成计划 → 执行计划中的多个步骤
# ============================================================

@dataclass
class PlanExecutionStartedEvent(MessageEvent):
    """计划执行开始事件
    
    触发时机：_execute_plan() 开始执行
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_STARTED)
    plan: Optional[Dict[str, Any]] = None


@dataclass
class PlanExecutionCompletedEvent(MessageEvent):
    """计划执行完成事件
    
    触发时机：所有步骤执行完成
    
    注意：此事件同时用于内部 (_execute_plan) 和外部 (chat_stream) 通信，
    file_changes 字段在 chat_stream 中会汇总所有步骤的文件变更。
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_COMPLETED)
    plan: Optional[Dict[str, Any]] = None
    summary: str = ""
    success: bool = True
    file_changes: List[str] = field(default_factory=list)


@dataclass
class PlanExecutionFailedEvent(MessageEvent):
    """计划执行失败事件
    
    触发时机：某个步骤执行失败
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_FAILED)
    plan: Optional[Dict[str, Any]] = None
    step_id: Optional[int] = None
    error: str = ""


@dataclass
class PlanExecutionCancelledEvent(MessageEvent):
    """计划执行取消事件
    
    触发时机：用户取消执行或检测到取消标志
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_CANCELLED)


# ============================================================
# 文件运行事件 (File Run)
# 场景：用户点击"运行"按钮，直接执行某个 .py 文件
# 这是一个独立功能，与计划执行无关
# ============================================================

@dataclass
class FileRunStartedEvent(BaseEvent):
    """文件运行开始事件
    
    触发时机：execute_file() 开始执行
    """
    type: EventType = field(default=EventType.FILE_RUN_STARTED)
    file: str = ""


@dataclass
class FileRunStdoutEvent(BaseEvent):
    """文件运行标准输出事件"""
    type: EventType = field(default=EventType.FILE_RUN_STDOUT)
    content: str = ""


@dataclass
class FileRunStderrEvent(BaseEvent):
    """文件运行标准错误事件"""
    type: EventType = field(default=EventType.FILE_RUN_STDERR)
    content: str = ""


@dataclass
class FileRunExitEvent(BaseEvent):
    """文件运行退出事件
    
    触发时机：Python 脚本执行完成
    """
    type: EventType = field(default=EventType.FILE_RUN_EXIT)
    exit_code: int = 0
    duration: float = 0.0

