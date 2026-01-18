"""
Planner - 计划生成器
负责让 LLM 生成结构化的执行计划
"""

import json
import logging
from typing import Optional, Dict, Any, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .models import Plan, PlanStep, PlanStatus


# 计划生成的系统提示词
PLAN_SYSTEM_PROMPT = """你是一个任务规划专家。你的职责是将用户的编程任务分解为清晰、可执行的步骤。

## 输出格式
你必须以 JSON 格式输出执行计划，格式如下：

```json
{
  "analysis": "对任务的简要分析",
  "steps": [
    {
      "description": "步骤描述（具体、可执行）",
      "expected_outcome": "预期结果",
      "tools": ["可能用到的工具"]
    }
  ]
}
```

## 规划原则
1. **原子性**: 每个步骤应该是单一、明确的操作
2. **可验证**: 每个步骤都应该有可验证的预期结果
3. **顺序性**: 步骤之间有清晰的执行顺序
4. **完整性**: 覆盖任务的所有必要操作

## 可用工具
- read_file: 读取文件内容
- write_file: 写入/创建文件
- patch_file: 修改文件的特定部分
- list_directory: 列出目录内容
- shell_exec: 执行 shell 命令
- grep: 搜索代码
- get_file_outline: 获取文件结构大纲

## 示例

用户任务: "创建一个计算 RSI 指标的函数"

你的输出:
```json
{
  "analysis": "需要创建一个新的 Python 文件，实现 RSI 指标计算函数",
  "steps": [
    {
      "description": "查看项目结构，确定文件放置位置",
      "expected_outcome": "了解项目目录结构",
      "tools": ["list_directory"]
    },
    {
      "description": "创建 indicators/rsi.py 文件，实现 RSI 计算函数",
      "expected_outcome": "创建包含 calculate_rsi 函数的文件",
      "tools": ["write_file"]
    },
    {
      "description": "创建测试代码验证 RSI 计算正确性",
      "expected_outcome": "RSI 函数能正确计算指标值",
      "tools": ["write_file", "shell_exec"]
    }
  ]
}
```

## 注意事项
1. 步骤数量通常在 2-8 个之间
2. 避免过于细碎的步骤
3. 考虑错误处理和边界情况
4. 如果任务不明确，第一步可以是"分析现有代码/项目结构"
"""


class Planner:
    """
    计划生成器
    """
    
    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
    
    async def create_plan(self, task: str, context: str = "") -> Plan:
        """
        生成执行计划
        
        Args:
            task: 用户任务描述
            context: 额外上下文（如项目结构、相关代码）
            
        Returns:
            Plan 对象
        """
        # 构建提示词
        user_prompt = f"任务: {task}"
        if context:
            user_prompt += f"\n\n项目上下文:\n{context}"
        user_prompt += "\n\n请生成执行计划（JSON 格式）。"
        
        messages = [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            # 调用 LLM
            response = await self.llm.ainvoke(messages)
            content = response.content
            
            # 解析 JSON
            plan_data = self._parse_plan_json(content)
            
            # 构建 Plan 对象
            steps = []
            for i, step_data in enumerate(plan_data.get("steps", [])):
                steps.append(PlanStep(
                    id=i + 1,
                    description=step_data.get("description", ""),
                    expected_outcome=step_data.get("expected_outcome", ""),
                    tools_needed=step_data.get("tools", [])
                ))
            
            plan = Plan(
                task=task,
                steps=steps,
                status=PlanStatus.AWAITING_APPROVAL
            )
            
            logging.info(f"Planner: Created plan with {len(steps)} steps")
            return plan
            
        except Exception as e:
            logging.error(f"Planner: Failed to create plan: {e}")
            # 返回一个简单的默认计划
            return Plan(
                task=task,
                steps=[
                    PlanStep(
                        id=1,
                        description=f"执行任务: {task}",
                        expected_outcome="任务完成"
                    )
                ],
                status=PlanStatus.AWAITING_APPROVAL
            )
    
    def create_plan_sync(self, task: str, context: str = "") -> Plan:
        """
        同步版本的计划生成
        """
        user_prompt = f"任务: {task}"
        if context:
            user_prompt += f"\n\n项目上下文:\n{context}"
        user_prompt += "\n\n请生成执行计划（JSON 格式）。"
        
        messages = [
            SystemMessage(content=PLAN_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        
        try:
            response = self.llm.invoke(messages)
            content = response.content
            plan_data = self._parse_plan_json(content)
            
            steps = []
            for i, step_data in enumerate(plan_data.get("steps", [])):
                steps.append(PlanStep(
                    id=i + 1,
                    description=step_data.get("description", ""),
                    expected_outcome=step_data.get("expected_outcome", ""),
                    tools_needed=step_data.get("tools", [])
                ))
            
            plan = Plan(
                task=task,
                steps=steps,
                status=PlanStatus.AWAITING_APPROVAL
            )
            
            logging.info(f"Planner: Created plan with {len(steps)} steps")
            return plan
            
        except Exception as e:
            logging.error(f"Planner: Failed to create plan: {e}")
            return Plan(
                task=task,
                steps=[
                    PlanStep(
                        id=1,
                        description=f"执行任务: {task}",
                        expected_outcome="任务完成"
                    )
                ],
                status=PlanStatus.AWAITING_APPROVAL
            )
    
    async def replan(self, original_task: str, failed_plan: Plan, 
                     failed_step: PlanStep, error: str) -> Plan:
        """
        重新规划（当原计划失败时）
        
        Args:
            original_task: 原始任务
            failed_plan: 失败的计划
            failed_step: 失败的步骤
            error: 错误信息
            
        Returns:
            新的 Plan 对象
        """
        context = f"""
原始计划已失败，需要重新规划。

失败信息:
- 失败步骤: Step {failed_step.id} - {failed_step.description}
- 错误原因: {error}

已完成的步骤:
{self._format_completed_steps(failed_plan)}

请制定新的计划来完成剩余任务，考虑失败的原因并避免同样的问题。
"""
        
        new_plan = await self.create_plan(original_task, context)
        new_plan.version = failed_plan.version + 1
        new_plan.replan_count = failed_plan.replan_count + 1
        
        logging.info(f"Planner: Replanned (version {new_plan.version})")
        return new_plan
    
    def _parse_plan_json(self, content: str) -> Dict[str, Any]:
        """
        从 LLM 响应中解析 JSON（增强版）
        
        多重尝试策略：
        1. 直接解析
        2. 提取 JSON 代码块
        3. 提取大括号内容
        4. 修复常见格式错误后重试
        5. 最后尝试从文本中提取步骤
        """
        import re
        
        # 尝试直接解析
        try:
            parsed = json.loads(content)
            if self._validate_plan_structure(parsed):
                return parsed
        except json.JSONDecodeError:
            pass
        
        # 尝试提取 JSON 代码块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            json_str = json_match.group(1).strip()
            try:
                parsed = json.loads(json_str)
                if self._validate_plan_structure(parsed):
                    return parsed
            except json.JSONDecodeError:
                # 尝试修复常见错误
                fixed = self._fix_json_errors(json_str)
                try:
                    parsed = json.loads(fixed)
                    if self._validate_plan_structure(parsed):
                        return parsed
                except json.JSONDecodeError:
                    pass
        
        # 尝试找到 { } 包围的内容
        brace_match = re.search(r'\{[\s\S]*\}', content)
        if brace_match:
            json_str = brace_match.group(0)
            try:
                parsed = json.loads(json_str)
                if self._validate_plan_structure(parsed):
                    return parsed
            except json.JSONDecodeError:
                fixed = self._fix_json_errors(json_str)
                try:
                    parsed = json.loads(fixed)
                    if self._validate_plan_structure(parsed):
                        return parsed
                except json.JSONDecodeError:
                    pass
        
        # 最后尝试：从文本中提取步骤
        steps = self._extract_steps_from_text(content)
        if steps:
            logging.warning("Planner: Using text extraction fallback")
            return {"steps": steps}
        
        logging.warning("Planner: Failed to parse plan JSON, using empty fallback")
        return {"steps": []}
    
    def _validate_plan_structure(self, data: Dict) -> bool:
        """验证计划结构是否有效"""
        if not isinstance(data, dict):
            return False
        
        steps = data.get("steps", [])
        if not isinstance(steps, list) or len(steps) == 0:
            return False
        
        # 检查步骤是否有基本结构
        for step in steps:
            if not isinstance(step, dict):
                return False
            if "description" not in step:
                return False
        
        return True
    
    def _fix_json_errors(self, json_str: str) -> str:
        """尝试修复常见的 JSON 格式错误"""
        import re
        
        fixed = json_str
        
        # 修复尾部逗号
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        
        # 修复缺少引号的键
        fixed = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed)
        
        # 修复单引号
        fixed = fixed.replace("'", '"')
        
        return fixed
    
    def _extract_steps_from_text(self, content: str) -> List[Dict]:
        """从纯文本中提取步骤（最后的 fallback）"""
        import re
        
        steps = []
        
        # 匹配数字列表项
        # 如 "1. xxx" 或 "Step 1: xxx"
        patterns = [
            r'(?:^|\n)\s*(\d+)[.)\s]+(.+?)(?=\n\s*\d+[.)\s]|\n\n|$)',
            r'(?:^|\n)\s*Step\s*(\d+)[:\s]+(.+?)(?=\n\s*Step\s*\d+|\n\n|$)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            if matches:
                for _, desc in matches:
                    desc = desc.strip()
                    if desc and len(desc) > 5:  # 过滤太短的
                        steps.append({
                            "description": desc,
                            "expected_outcome": "",
                            "tools": []
                        })
                break
        
        return steps
    
    def _format_completed_steps(self, plan: Plan) -> str:
        """格式化已完成的步骤"""
        completed = [s for s in plan.steps if s.status.value == "done"]
        if not completed:
            return "（无）"
        
        lines = []
        for step in completed:
            lines.append(f"- Step {step.id}: {step.description}")
            if step.result:
                lines.append(f"  结果: {step.result[:100]}...")
        
        return "\n".join(lines)

