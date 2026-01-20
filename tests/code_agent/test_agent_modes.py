"""
测试 Agent 双模式支持（Plan 模式和 Direct 模式）
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.agent import PlanExecuteAgent
from agent.code_agent.events import ResponseStartEvent, ResponseEndEvent, EventType
from agent.code_agent.tools import CREATE_PLAN_TOOL_NAME
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


@pytest.fixture
def mock_llm():
    """创建模拟 LLM"""
    llm = Mock()
    return llm


@pytest.fixture
def mock_workspace_manager():
    """创建模拟 WorkspaceManager"""
    workspace = Mock()
    workspace.get_project.return_value = {"name": "test_project"}
    workspace.get_project_path.return_value = "/tmp/test_project"
    workspace.get_file_list.return_value = []
    return workspace


@pytest.fixture
def temp_workspace(tmp_path):
    """创建临时工作区"""
    workspace_dir = tmp_path / "test_workspace"
    workspace_dir.mkdir()
    return str(workspace_dir)


class TestAgentModeDetection:
    """测试 Agent 模式检测"""
    
    @patch('agent.code_agent.agent.WorkspaceManager')
    @patch('agent.code_agent.agent.resolve_llm_config')
    def test_detect_plan_mode(self, mock_llm_config, mock_workspace_class, temp_workspace, mock_llm):
        """测试检测 Plan 模式（LLM 调用 create_plan）"""
        # 设置 mock
        mock_llm_config.return_value = {
            "model": "gpt-4",
            "api_key": "test-key",
            "base_url": "https://api.openai.com/v1"
        }
        
        mock_workspace = Mock()
        mock_workspace.get_project.return_value = {"name": "test"}
        mock_workspace.get_project_path.return_value = temp_workspace
        mock_workspace_class.return_value = mock_workspace
        
        # 模拟 LLM 返回 create_plan 工具调用
        mock_response = Mock()
        mock_response.content = ""
        mock_response.tool_calls = [
            {
                "id": "tc1",
                "name": CREATE_PLAN_TOOL_NAME,
                "arguments": {
                    "analysis": "需要创建多个文件",
                    "steps": [
                        {"description": "步骤1", "expected_outcome": "结果1", "tools": ["read_file"]}
                    ]
                }
            }
        ]
        
        mock_llm.invoke.return_value = mock_response
        
        # 创建 agent（需要更多 mock）
        # 注意：这里只是测试模式检测逻辑，实际运行需要完整的依赖
        pass  # 实际测试需要更复杂的 setup
    
    def test_create_plan_tool_in_registry(self, temp_workspace):
        """测试 create_plan 工具已注册到工具注册表"""
        from agent.code_agent.tools import create_tool_registry
        
        registry = create_tool_registry(temp_workspace)
        tools = registry.list_tools()
        
        assert CREATE_PLAN_TOOL_NAME in tools
        
        # 验证工具定义
        definitions = registry.get_all_definitions()
        create_plan_def = next(
            (d for d in definitions if d["function"]["name"] == CREATE_PLAN_TOOL_NAME),
            None
        )
        
        assert create_plan_def is not None
        assert "analysis" in create_plan_def["function"]["parameters"]["properties"]
        assert "steps" in create_plan_def["function"]["parameters"]["properties"]


class TestResponseEvents:
    """测试响应事件"""
    
    def test_response_start_event_plan_mode(self):
        """测试 Plan 模式的响应开始事件"""
        event = ResponseStartEvent(mode="plan")
        d = event.to_dict()
        
        assert d["type"] == "response_start"
        assert d["mode"] == "plan"
    
    def test_response_start_event_direct_mode(self):
        """测试 Direct 模式的响应开始事件"""
        event = ResponseStartEvent(mode="direct")
        d = event.to_dict()
        
        assert d["type"] == "response_start"
        assert d["mode"] == "direct"
    
    def test_response_end_event(self):
        """测试响应结束事件"""
        event = ResponseEndEvent()
        d = event.to_dict()
        
        assert d["type"] == "response_end"


class TestModeGuidance:
    """测试模式选择指导"""
    
    def test_system_prompt_contains_mode_guidance(self):
        """测试系统提示词包含模式选择指导"""
        from agent.code_agent.prompts.prompt_loader import get_code_agent_prompt_loader
        
        loader = get_code_agent_prompt_loader()
        system_prompt = loader.get_system_prompt()
        
        # 应该包含模式选择的指导
        assert "执行模式选择" in system_prompt or "Plan 模式" in system_prompt or "Direct 模式" in system_prompt

