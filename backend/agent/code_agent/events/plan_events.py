"""
计划相关事件定义
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .base import MessageEvent
from .types import EventType


@dataclass
class PlanCreatedEvent(MessageEvent):
    """计划创建事件"""
    type: EventType = field(default=EventType.PLAN_CREATED)
    plan: Optional[Dict[str, Any]] = None


# 注意：PlanCompletedEvent 已合并到 PlanExecutionCompletedEvent
# 见 execution_events.py

# 注意：审批相关事件（PlanAwaitingApprovalEvent, PlanApprovedEvent, 
# PlanRejectedEvent, PlanModifiedEvent）已删除，
# 因为当前不使用审批流程
