"""
步骤相关事件定义
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from .base import BaseEvent
from .types import EventType


@dataclass
class StepStartedEvent(BaseEvent):
    """步骤开始事件"""
    type: EventType = field(default=EventType.STEP_STARTED)
    step_id: int = 0
    description: str = ""
    progress: Optional[Dict[str, Any]] = None


@dataclass
class StepCompletedEvent(BaseEvent):
    """步骤完成事件"""
    type: EventType = field(default=EventType.STEP_COMPLETED)
    step_id: int = 0
    files_changed: List[str] = field(default_factory=list)
    progress: Optional[Dict[str, Any]] = None


@dataclass
class StepOutputEvent(BaseEvent):
    """步骤输出事件"""
    type: EventType = field(default=EventType.STEP_OUTPUT)
    step_id: int = 0
    content: str = ""


@dataclass
class StepErrorEvent(BaseEvent):
    """步骤错误事件"""
    type: EventType = field(default=EventType.STEP_ERROR)
    step_id: int = 0
    error: str = ""

