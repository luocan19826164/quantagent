"""
工具相关事件定义
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .base import BaseEvent
from .types import EventType


@dataclass
class ToolCallsEvent(BaseEvent):
    """工具调用事件"""
    type: EventType = field(default=EventType.TOOL_CALLS)
    step_id: int = 0
    calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolResultEvent(BaseEvent):
    """工具结果事件"""
    type: EventType = field(default=EventType.TOOL_RESULT)
    step_id: int = 0
    tool: str = ""
    success: bool = True
    output: str = ""
    error: Optional[str] = None

