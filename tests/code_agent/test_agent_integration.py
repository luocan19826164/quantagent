"""
Agent 集成测试 - 测试双模式支持和上下文管理
"""

import pytest
import sys
import os
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch, call
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.agent import PlanExecuteAgent
from agent.code_agent.events import ResponseStartEvent, ResponseEndEvent, EventType
from agent.code_agent.tools import CREATE_PLAN_TOOL_NAME
from agent.code_agent.context import ConversationHistory, CodeAgentContext, CodeContext
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


@pytest.fixture
def temp_workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_agent_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_llm_config():
    """模拟 LLM 配置"""
    return {
        "model": "gpt-4",
        "api_key": "test-key",
        "base_url": "https://api.openai.com/v1"
    }


@pytest.fixture
def mock_workspace_manager(temp_workspace):
    """模拟 WorkspaceManager"""
    with patch('agent.code_agent.agent.WorkspaceManager') as mock_ws:
        mock_ws_instance = Mock()
        mock_ws_instance.get_project.return_value = {"name": "test_project"}
        mock_ws_instance.get_project_path.return_value = temp_workspace
        mock_ws_instance.get_file_list.return_value = []
        mock_ws.return_value = mock_ws_instance
        yield mock_ws_instance


class TestAgentContextIntegration:
    """测试 Agent 上下文集成"""
    
    @patch('agent.code_agent.agent.resolve_llm_config')
    def test_agent_initializes_context(self, mock_llm_config, mock_workspace_manager, temp_workspace):
        """测试 Agent 初始化时创建 CodeAgentContext"""
        mock_llm_config.return_value = {
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1"
        }
        
        agent = PlanExecuteAgent(
            user_id=1,
            project_id="test-proj",
            use_sandbox=False
        )
        
        assert agent.context is not None
        assert isinstance(agent.context, CodeAgentContext)
        assert agent.context.conversation is not None
        assert isinstance(agent.context.conversation, ConversationHistory)
        assert agent.context.code_context is not None
    
    @patch('agent.code_agent.agent.resolve_llm_config')
    def test_conversation_history_persists(self, mock_llm_config, mock_workspace_manager, temp_workspace):
        """测试对话历史持续保存"""
        mock_llm_config.return_value = {
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1"
        }
        
        agent = PlanExecuteAgent(
            user_id=1,
            project_id="test-proj",
            use_sandbox=False
        )
        
        # 添加用户消息
        agent.context.conversation.add_user_message("测试消息1")
        
        assert len(agent.context.conversation.messages) == 1
        assert agent.context.conversation.messages[0].content == "测试消息1"
        
        # 再次添加
        agent.context.conversation.add_user_message("测试消息2")
        
        assert len(agent.context.conversation.messages) == 2


class TestAgentModeEvents:
    """测试 Agent 模式事件"""
    
    @patch('agent.code_agent.agent.resolve_llm_config')
    @patch('agent.code_agent.agent.ChatOpenAI')
    def test_chat_stream_sends_response_start(self, mock_chat_openai, mock_llm_config, 
                                               mock_workspace_manager, temp_workspace):
        """测试 chat_stream 发送 response_start 事件"""
        mock_llm_config.return_value = {
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1"
        }
        
        # Mock LLM 响应（Plan 模式）
        mock_response = Mock()
        mock_response.content = ""
        mock_response.tool_calls = [
            {
                "id": "tc1",
                "name": CREATE_PLAN_TOOL_NAME,
                "arguments": {
                    "analysis": "测试分析",
                    "steps": [{"description": "步骤1", "expected_outcome": "结果1", "tools": []}]
                }
            }
        ]
        
        mock_llm_instance = Mock()
        mock_llm_instance.invoke.return_value = mock_response
        mock_chat_openai.return_value = mock_llm_instance
        
        agent = PlanExecuteAgent(
            user_id=1,
            project_id="test-proj",
            use_sandbox=False
        )
        
        # Mock _execute_plan 避免实际执行
        agent._execute_plan = Mock(return_value=iter([]))
        
        # 调用 chat_stream
        events = list(agent.chat_stream("测试任务"))
        
        # 应该包含 response_start 事件
        response_start_events = [e for e in events if e.get("type") == "response_start"]
        assert len(response_start_events) > 0
        assert response_start_events[0]["mode"] in ["plan", "direct"]
        
        # 应该包含 response_end 事件
        response_end_events = [e for e in events if e.get("type") == "response_end"]
        assert len(response_end_events) > 0


class TestCreatePlanToolIntegration:
    """测试 create_plan 工具集成"""
    
    @patch('agent.code_agent.agent.resolve_llm_config')
    def test_create_plan_tool_in_registry(self, mock_llm_config, mock_workspace_manager, temp_workspace):
        """测试 create_plan 工具已注册"""
        mock_llm_config.return_value = {
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1"
        }
        
        agent = PlanExecuteAgent(
            user_id=1,
            project_id="test-proj",
            use_sandbox=False
        )
        
        # 检查工具注册表
        tools = agent.tool_registry.list_tools()
        assert CREATE_PLAN_TOOL_NAME in tools
        
        # 检查工具定义
        definitions = agent.tool_registry.get_all_definitions()
        create_plan_def = next(
            (d for d in definitions if d["function"]["name"] == CREATE_PLAN_TOOL_NAME),
            None
        )
        
        assert create_plan_def is not None
        assert "analysis" in create_plan_def["function"]["parameters"]["properties"]
        assert "steps" in create_plan_def["function"]["parameters"]["properties"]


class TestMemoryContextIntegration:
    """测试 MemoryContext 集成"""
    
    @patch('agent.code_agent.agent.resolve_llm_config')
    def test_memory_context_adds_decisions(self, mock_llm_config, mock_workspace_manager, temp_workspace):
        """测试 MemoryContext 添加决策"""
        mock_llm_config.return_value = {
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1"
        }
        
        agent = PlanExecuteAgent(
            user_id=1,
            project_id="test-proj",
            use_sandbox=False
        )
        
        # 添加决策
        agent.context.memory.add_decision(
            decision="使用 PostgreSQL",
            reason="需要 JSON 字段支持"
        )
        
        assert len(agent.context.memory.decisions) == 1
        assert agent.context.memory.decisions[0].decision == "使用 PostgreSQL"
        
        # 测试 to_dict
        d = agent.context.memory.to_dict()
        assert len(d["decisions"]) == 1

