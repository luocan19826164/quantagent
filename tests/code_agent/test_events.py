"""
测试新事件类型
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.events import (
    ResponseStartEvent, ResponseEndEvent, EventType
)


class TestResponseStartEvent:
    """测试 ResponseStartEvent"""
    
    def test_create_plan_mode(self):
        """测试创建 Plan 模式事件"""
        event = ResponseStartEvent(mode="plan")
        
        assert event.type == EventType.RESPONSE_START
        assert event.mode == "plan"
    
    def test_create_direct_mode(self):
        """测试创建 Direct 模式事件"""
        event = ResponseStartEvent(mode="direct")
        
        assert event.type == EventType.RESPONSE_START
        assert event.mode == "direct"
    
    def test_default_mode(self):
        """测试默认模式"""
        event = ResponseStartEvent()
        
        assert event.mode == "direct"  # 默认值
    
    def test_to_dict(self):
        """测试转换为字典"""
        event = ResponseStartEvent(mode="plan")
        d = event.to_dict()
        
        assert d["type"] == "response_start"
        assert d["mode"] == "plan"


class TestResponseEndEvent:
    """测试 ResponseEndEvent"""
    
    def test_create_event(self):
        """测试创建事件"""
        event = ResponseEndEvent()
        
        assert event.type == EventType.RESPONSE_END
    
    def test_to_dict(self):
        """测试转换为字典"""
        event = ResponseEndEvent()
        d = event.to_dict()
        
        assert d["type"] == "response_end"


class TestEventType:
    """测试 EventType 枚举"""
    
    def test_response_start_exists(self):
        """测试 RESPONSE_START 存在"""
        assert hasattr(EventType, "RESPONSE_START")
        assert EventType.RESPONSE_START.value == "response_start"
    
    def test_response_end_exists(self):
        """测试 RESPONSE_END 存在"""
        assert hasattr(EventType, "RESPONSE_END")
        assert EventType.RESPONSE_END.value == "response_end"

