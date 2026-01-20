"""
create_plan 工具
用于让 LLM 自主决定是否需要生成执行计划

当 LLM 认为任务复杂、需要多个步骤时，会调用此工具生成计划。
Agent 检测到此工具调用后，会进入 Plan 模式。
"""

import json
import logging
from typing import Dict, Any, List
from .base import BaseTool, ToolResult


class CreatePlanTool(BaseTool):
    """
    创建执行计划工具
    
    LLM 调用此工具来生成结构化的执行计划。
    这是一个"元工具"，它不直接执行操作，而是告诉 Agent 进入 Plan 模式。
    
    使用场景：
    - 复杂任务（需要多个步骤）
    - 涉及多个文件的修改
    - 需要用户了解整体计划的情况
    
    不应使用的场景：
    - 简单的文件读取
    - 单一操作的任务
    - 问答类请求
    """
    
    name = "create_plan"
    description = """创建执行计划。当任务复杂、需要多个步骤时使用此工具。

何时使用：
- 任务需要 2 个以上步骤
- 需要修改多个文件
- 涉及创建新功能或重构

何时不使用：
- 简单的代码解释或问答
- 只需要读取文件
- 单一的小修改

调用此工具后，系统会按照计划逐步执行。"""

    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "analysis": {
                    "type": "string",
                    "description": "对任务的简要分析，说明为什么需要这个计划"
                },
                "steps": {
                    "type": "array",
                    "description": "执行步骤列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {
                                "type": "string",
                                "description": "步骤描述（具体、可执行）"
                            },
                            "expected_outcome": {
                                "type": "string",
                                "description": "预期结果"
                            },
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "可能用到的工具名称"
                            }
                        },
                        "required": ["description"]
                    }
                }
            },
            "required": ["analysis", "steps"]
        }
    
    def execute(self, analysis: str = "", steps: List[Dict] = None, **kwargs) -> ToolResult:
        """
        执行工具
        
        注意：此工具的 execute 主要用于验证参数格式。
        实际的计划创建由 Agent 的 run() 方法处理。
        """
        if not steps:
            return ToolResult(
                success=False,
                error="计划必须包含至少一个步骤"
            )
        
        if not isinstance(steps, list) or len(steps) == 0:
            return ToolResult(
                success=False,
                error="steps 必须是非空数组"
            )
        
        # 验证每个步骤的格式
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                return ToolResult(
                    success=False,
                    error=f"步骤 {i+1} 格式错误，必须是对象"
                )
            if "description" not in step:
                return ToolResult(
                    success=False,
                    error=f"步骤 {i+1} 缺少 description 字段"
                )
        
        # 返回成功，实际的计划会由 Agent 处理
        plan_data = {
            "analysis": analysis,
            "steps": steps
        }
        
        logging.info(f"CreatePlanTool: Plan created with {len(steps)} steps")
        
        return ToolResult(
            success=True,
            output=f"已创建执行计划，共 {len(steps)} 个步骤",
            data={"plan": plan_data}
        )


# 工具名称常量，用于检测
CREATE_PLAN_TOOL_NAME = "create_plan"

