"""
测试 create_plan 工具
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.tools.plan_tool import CreatePlanTool, CREATE_PLAN_TOOL_NAME
from agent.code_agent.tools.base import ToolResult


class TestCreatePlanTool:
    """测试 CreatePlanTool"""
    
    def test_tool_name(self):
        """测试工具名称"""
        tool = CreatePlanTool()
        assert tool.name == "create_plan"
        assert tool.name == CREATE_PLAN_TOOL_NAME
    
    def test_get_definition(self):
        """测试获取工具定义"""
        tool = CreatePlanTool()
        definition = tool.get_definition()
        
        assert definition.name == "create_plan"
        assert "创建执行计划" in definition.description
        assert "analysis" in definition.parameters["properties"]
        assert "steps" in definition.parameters["properties"]
    
    def test_get_parameters_schema(self):
        """测试参数 schema"""
        tool = CreatePlanTool()
        schema = tool.get_parameters_schema()
        
        assert schema["type"] == "object"
        assert "analysis" in schema["properties"]
        assert "steps" in schema["properties"]
        assert schema["properties"]["steps"]["type"] == "array"
    
    def test_execute_valid_plan(self):
        """测试执行有效计划"""
        tool = CreatePlanTool()
        
        steps = [
            {
                "description": "读取配置文件",
                "expected_outcome": "获取配置信息",
                "tools": ["read_file"]
            },
            {
                "description": "修改配置",
                "expected_outcome": "配置已更新",
                "tools": ["write_file"]
            }
        ]
        
        result = tool.execute(
            analysis="需要修改配置文件",
            steps=steps
        )
        
        assert result.success is True
        assert "已创建执行计划" in result.output
        assert result.data is not None
        assert "plan" in result.data
        assert len(result.data["plan"]["steps"]) == 2
    
    def test_execute_empty_steps(self):
        """测试空步骤列表"""
        tool = CreatePlanTool()
        
        result = tool.execute(analysis="测试", steps=[])
        
        assert result.success is False
        assert "至少一个步骤" in result.error
    
    def test_execute_missing_description(self):
        """测试缺少 description 的步骤"""
        tool = CreatePlanTool()
        
        steps = [
            {
                "expected_outcome": "结果"
            }
        ]
        
        result = tool.execute(analysis="测试", steps=steps)
        
        assert result.success is False
        assert "缺少 description" in result.error
    
    def test_execute_invalid_steps_type(self):
        """测试无效的 steps 类型"""
        tool = CreatePlanTool()
        
        result = tool.execute(analysis="测试", steps="not a list")
        
        assert result.success is False
    
    def test_to_openai_format(self):
        """测试转换为 OpenAI 格式"""
        tool = CreatePlanTool()
        definition = tool.get_definition()
        openai_format = definition.to_openai_format()
        
        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "create_plan"
        assert "parameters" in openai_format["function"]

