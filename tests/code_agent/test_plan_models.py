"""
测试 Plan 数据模型
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.plan.models import (
    Plan, PlanStep, PlanStatus, StepStatus, StepResult
)


class TestPlanStep:
    """测试 PlanStep"""
    
    def test_create_step(self):
        """测试创建步骤"""
        step = PlanStep(
            id=1,
            description="读取文件内容",
            expected_outcome="获取文件信息"
        )
        
        assert step.id == 1
        assert step.description == "读取文件内容"
        assert step.status == StepStatus.PENDING
        assert step.expected_outcome == "获取文件信息"
    
    def test_step_to_dict(self):
        """测试步骤转字典"""
        step = PlanStep(
            id=1,
            description="测试步骤",
            tools_needed=["read_file", "grep"]
        )
        
        d = step.to_dict()
        
        assert d["id"] == 1
        assert d["description"] == "测试步骤"
        assert d["status"] == "pending"
        assert "read_file" in d["tools_needed"]
    
    def test_step_from_dict(self):
        """测试从字典创建步骤"""
        data = {
            "id": 2,
            "description": "写入文件",
            "status": "done",
            "expected_outcome": "文件创建成功"
        }
        
        step = PlanStep.from_dict(data)
        
        assert step.id == 2
        assert step.status == StepStatus.DONE


class TestPlan:
    """测试 Plan"""
    
    def test_create_plan(self):
        """测试创建计划"""
        plan = Plan(
            task="创建 RSI 计算函数",
            steps=[
                PlanStep(id=1, description="分析需求"),
                PlanStep(id=2, description="编写代码"),
                PlanStep(id=3, description="测试验证")
            ]
        )
        
        assert plan.task == "创建 RSI 计算函数"
        assert len(plan.steps) == 3
        assert plan.status == PlanStatus.PLANNING
    
    def test_get_current_step(self):
        """测试获取当前步骤"""
        plan = Plan(
            task="测试任务",
            steps=[
                PlanStep(id=1, description="步骤1"),
                PlanStep(id=2, description="步骤2")
            ],
            current_step_id=2
        )
        
        current = plan.get_current_step()
        
        assert current is not None
        assert current.id == 2
        assert current.description == "步骤2"
    
    def test_get_progress(self):
        """测试进度计算"""
        plan = Plan(
            task="测试任务",
            steps=[
                PlanStep(id=1, description="步骤1", status=StepStatus.DONE),
                PlanStep(id=2, description="步骤2", status=StepStatus.DONE),
                PlanStep(id=3, description="步骤3", status=StepStatus.PENDING),
                PlanStep(id=4, description="步骤4", status=StepStatus.PENDING)
            ]
        )
        
        progress = plan.get_progress()
        
        assert progress["total"] == 4
        assert progress["done"] == 2
        assert progress["pending"] == 2
        assert progress["progress_percent"] == 50
    
    def test_is_complete(self):
        """测试完成检查"""
        plan = Plan(
            task="测试",
            steps=[
                PlanStep(id=1, description="s1", status=StepStatus.DONE),
                PlanStep(id=2, description="s2", status=StepStatus.DONE)
            ]
        )
        
        assert plan.is_complete() is True
        
        plan.steps.append(PlanStep(id=3, description="s3", status=StepStatus.PENDING))
        assert plan.is_complete() is False
    
    def test_has_failed(self):
        """测试失败检查"""
        plan = Plan(
            task="测试",
            steps=[
                PlanStep(id=1, description="s1", status=StepStatus.DONE),
                PlanStep(id=2, description="s2", status=StepStatus.FAILED)
            ]
        )
        
        assert plan.has_failed() is True
    
    def test_to_summary(self):
        """测试生成摘要"""
        plan = Plan(
            task="创建策略",
            steps=[
                PlanStep(id=1, description="分析", status=StepStatus.DONE),
                PlanStep(id=2, description="编码", status=StepStatus.IN_PROGRESS)
            ],
            current_step_id=2
        )
        
        summary = plan.to_summary()
        
        assert "创建策略" in summary
        assert "✅" in summary  # done
        assert "🔄" in summary  # in_progress
        assert "👈 [当前]" in summary
    
    def test_plan_serialization(self):
        """测试计划序列化/反序列化"""
        original = Plan(
            task="测试序列化",
            steps=[
                PlanStep(id=1, description="步骤1", tools_needed=["read_file"]),
                PlanStep(id=2, description="步骤2")
            ],
            current_step_id=1,
            version=2
        )
        
        # 序列化
        data = original.to_dict()
        
        # 反序列化
        restored = Plan.from_dict(data)
        
        assert restored.task == original.task
        assert len(restored.steps) == len(original.steps)
        assert restored.version == 2


class TestStepResult:
    """测试 StepResult"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = StepResult(
            success=True,
            response="文件已创建",
            files_changed=["main.py"]
        )
        
        assert result.success is True
        assert "main.py" in result.files_changed
    
    def test_failure_result(self):
        """测试失败结果"""
        result = StepResult(
            success=False,
            error="文件不存在"
        )
        
        assert result.success is False
        assert result.error == "文件不存在"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

