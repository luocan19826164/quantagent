"""
测试 ConversationHistory 和 Message
"""

import pytest
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.context import (
    Message, ConversationHistory, CodeAgentContext, CodeContext
)
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage


class TestMessage:
    """测试 Message 类"""
    
    def test_create_user_message(self):
        """测试创建用户消息"""
        msg = Message(role="user", content="读取 config.py")
        
        assert msg.role == "user"
        assert msg.content == "读取 config.py"
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert isinstance(msg.timestamp, str)
    
    def test_create_assistant_message_with_tool_calls(self):
        """测试创建带工具调用的 assistant 消息"""
        tool_calls = [
            {"id": "tc1", "name": "read_file", "args": {"path": "config.py"}}
        ]
        msg = Message(
            role="assistant",
            content="好的，我来读取",
            tool_calls=tool_calls
        )
        
        assert msg.role == "assistant"
        assert msg.content == "好的，我来读取"
        assert len(msg.tool_calls) == 1
        assert msg.tool_calls[0]["name"] == "read_file"
    
    def test_create_tool_message(self):
        """测试创建工具消息"""
        msg = Message(
            role="tool",
            content="文件内容...",
            tool_call_id="tc1"
        )
        
        assert msg.role == "tool"
        assert msg.tool_call_id == "tc1"
        assert msg.tool_calls is None
    
    def test_to_dict(self):
        """测试转换为字典"""
        msg = Message(role="user", content="测试")
        d = msg.to_dict()
        
        assert d["role"] == "user"
        assert d["content"] == "测试"
        assert "timestamp" in d


class TestConversationHistory:
    """测试 ConversationHistory 类"""
    
    def test_create_empty_history(self):
        """测试创建空历史"""
        history = ConversationHistory()
        
        assert len(history.messages) == 0
        assert history.max_messages == 50
    
    def test_add_user_message(self):
        """测试添加用户消息"""
        history = ConversationHistory()
        
        history.add_user_message("读取 config.py")
        
        assert len(history.messages) == 1
        assert history.messages[0].role == "user"
        assert history.messages[0].content == "读取 config.py"
    
    def test_add_assistant_message(self):
        """测试添加 assistant 消息"""
        history = ConversationHistory()
        
        history.add_assistant_message("好的，我来读取")
        
        assert len(history.messages) == 1
        assert history.messages[0].role == "assistant"
        assert history.messages[0].content == "好的，我来读取"
    
    def test_add_assistant_message_with_tool_calls(self):
        """测试添加带工具调用的 assistant 消息"""
        history = ConversationHistory()
        
        tool_calls = [{"id": "tc1", "name": "read_file", "args": {"path": "config.py"}}]
        history.add_assistant_message("好的", tool_calls=tool_calls)
        
        assert len(history.messages) == 1
        assert history.messages[0].tool_calls is not None
        assert len(history.messages[0].tool_calls) == 1
    
    def test_add_tool_result(self):
        """测试添加工具结果（read_file 会缩略）"""
        history = ConversationHistory()
        
        history.add_tool_result(
            tool_call_id="tc1",
            tool_name="read_file",
            result="文件内容...",
            file_path="config.py"
        )
        
        assert len(history.messages) == 1
        assert history.messages[0].role == "tool"
        assert history.messages[0].tool_call_id == "tc1"
        # read_file 的结果会被缩略为引用
        assert "已读取 config.py" in history.messages[0].content
        assert history.messages[0].is_abbreviated is True
    
    def test_add_tool_result_other_tool(self):
        """测试添加其他工具结果（不缩略）"""
        history = ConversationHistory()
        
        history.add_tool_result(
            tool_call_id="tc2",
            tool_name="grep",
            result="搜索结果...",
            file_path=None
        )
        
        assert len(history.messages) == 1
        assert history.messages[0].role == "tool"
        assert history.messages[0].content == "搜索结果..."
        assert history.messages[0].is_abbreviated is False
    
    def test_to_langchain_messages(self):
        """测试转换为 LangChain 消息"""
        history = ConversationHistory()
        history.add_user_message("读取文件")
        history.add_assistant_message("好的", tool_calls=[{"id": "tc1", "name": "read_file", "args": {}}])
        history.add_tool_result("tc1", "read_file", "内容")
        
        messages = history.to_langchain_messages()
        
        assert len(messages) == 3
        assert isinstance(messages[0], HumanMessage)
        assert isinstance(messages[1], AIMessage)
        assert isinstance(messages[2], ToolMessage)
    
    def test_evict_old_messages(self):
        """测试淘汰旧消息（通过 _enforce_limits 自动触发）"""
        history = ConversationHistory(max_messages=3)
        
        # 添加超过限制的消息（每次 add 都会自动调用 _enforce_limits）
        history.add_user_message("消息1")
        history.add_user_message("消息2")
        history.add_user_message("消息3")
        history.add_user_message("消息4")  # 添加第4条时会触发淘汰
        
        # 应该只保留最新的 3 条
        assert len(history.messages) == 3
        assert history.messages[0].content == "消息2"  # 最旧的消息被淘汰
        assert history.messages[-1].content == "消息4"  # 最新的消息保留
    
    def test_to_dict(self):
        """测试转换为字典"""
        history = ConversationHistory()
        history.add_user_message("测试")
        history.add_assistant_message("回复")
        
        d = history.to_dict()
        
        assert d["message_count"] == 2
        assert len(d["messages"]) == 2
    
    def test_full_conversation_flow(self):
        """测试完整对话流程"""
        history = ConversationHistory()
        
        # 用户消息
        history.add_user_message("修改 config.py 的数据库配置")
        
        # Assistant 消息（带工具调用）
        history.add_assistant_message(
            "好的，我先读取文件",
            tool_calls=[{"id": "tc1", "name": "read_file", "args": {"path": "config.py"}}]
        )
        
        # 工具结果
        history.add_tool_result("tc1", "read_file", "DB_HOST=localhost...", "config.py")
        
        # 再次 assistant 消息
        history.add_assistant_message("现在我来修改配置")
        
        assert len(history.messages) == 4
        assert history.messages[0].role == "user"
        assert history.messages[1].role == "assistant"
        assert history.messages[2].role == "tool"
        assert history.messages[3].role == "assistant"


class TestCodeAgentContextWithConversation:
    """测试 CodeAgentContext 与 ConversationHistory 的集成"""
    
    def test_context_with_conversation(self):
        """测试上下文包含对话历史"""
        code_context = CodeContext(workspace_root="/test")
        conversation = ConversationHistory()
        conversation.add_user_message("测试消息")
        
        context = CodeAgentContext(
            session_id="test-123",
            project_id="proj-456",
            code_context=code_context,
            conversation=conversation
        )
        
        assert context.conversation is not None
        assert len(context.conversation.messages) == 1
    
    def test_context_to_dict_includes_conversation(self):
        """测试 to_dict 包含对话历史"""
        code_context = CodeContext(workspace_root="/test")
        conversation = ConversationHistory()
        conversation.add_user_message("测试")
        
        context = CodeAgentContext(
            session_id="test-123",
            project_id="proj-456",
            code_context=code_context,
            conversation=conversation
        )
        
        d = context.to_dict()
        
        assert "conversation" in d
        assert d["conversation"]["message_count"] == 1

