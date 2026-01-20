"""
基础事件类定义
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from .types import EventType


@dataclass
class BaseEvent:
    """事件基类"""
    type: EventType
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于 JSON 序列化"""
        result = asdict(self)
        # EventType 枚举转为字符串
        result["type"] = self.type.value
        # 移除 None 值
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class MessageEvent(BaseEvent):
    """带消息的事件"""
    message: str = ""


@dataclass
class ErrorEvent(BaseEvent):
    """错误事件 - 统一使用 error 字段"""
    type: EventType = field(default=EventType.ERROR)
    error: str = ""
    
    # 兼容旧的 message 字段
    @property
    def message(self) -> str:
        return self.error


@dataclass
class StatusEvent(MessageEvent):
    """状态事件"""
    type: EventType = field(default=EventType.STATUS)


@dataclass
class TokenEvent(BaseEvent):
    """Token 流式事件"""
    type: EventType = field(default=EventType.TOKEN)
    content: str = ""


@dataclass
class FileChangeEvent(BaseEvent):
    """文件变更事件"""
    type: EventType = field(default=EventType.FILE_CHANGE)
    path: str = ""


@dataclass
class AnomalyDetectedEvent(BaseEvent):
    """异常检测事件"""
    type: EventType = field(default=EventType.ANOMALY_DETECTED)
    step_id: int = 0
    anomaly: str = ""


@dataclass
class ReplanWarningEvent(MessageEvent):
    """重新规划警告事件"""
    type: EventType = field(default=EventType.REPLAN_WARNING)


@dataclass
class ResponseStartEvent(BaseEvent):
    """响应开始事件
    
    用于告知前端当前响应的模式，以便渲染正确的 UI：
    - mode="direct": 普通模式，流式文本 + 工具调用
    - mode="plan": 计划模式，显示计划步骤 + 逐步执行
    """
    type: EventType = field(default=EventType.RESPONSE_START)
    mode: str = "direct"  # "direct" | "plan"


@dataclass
class ResponseEndEvent(BaseEvent):
    """响应结束事件"""
    type: EventType = field(default=EventType.RESPONSE_END)

