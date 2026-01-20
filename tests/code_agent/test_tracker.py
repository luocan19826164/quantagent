"""
测试 Plan Tracker（计划追踪器）
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.plan import (
    Plan, PlanStep, PlanTracker, StepStatus, StepResult
)


class TestPlanTracker:
    """测试计划追踪器"""
    
    @pytest.fixture
    def tracker_with_plan(self):
        """创建带计划的追踪器"""
        tracker = PlanTracker()
        plan = Plan(
            task="实现 RSI 计算",
            steps=[
                PlanStep(id=1, description="创建文件结构"),
                PlanStep(id=2, description="实现 RSI 计算逻辑"),
                PlanStep(id=3, description="添加测试用例")
            ]
        )
        tracker.set_plan(plan)
        return tracker
    
    def test_set_plan(self):
        """测试设置计划"""
        tracker = PlanTracker()
        plan = Plan(
            task="测试任务",
            steps=[PlanStep(id=1, description="步骤1")]
        )
        
        tracker.set_plan(plan)
        
        assert tracker.current_plan is not None
        assert tracker.current_plan.task == "测试任务"
    
    def test_start_step(self, tracker_with_plan):
        """测试开始步骤"""
        tracker_with_plan.start_step(1)
        
        step = tracker_with_plan.current_plan.steps[0]
        assert step.status == StepStatus.IN_PROGRESS
        assert tracker_with_plan.current_plan.current_step_id == 1
    
    def test_complete_step(self, tracker_with_plan):
        """测试完成步骤"""
        tracker_with_plan.start_step(1)
        
        result = StepResult(
            success=True,
            response="文件已创建",
            files_changed=["main.py"],
            tool_calls=[{"name": "write_file"}]
        )
        tracker_with_plan.complete_step(1, result)
        
        step = tracker_with_plan.current_plan.steps[0]
        assert step.status == StepStatus.DONE
        assert "main.py" in step.files_changed
    
    def test_fail_step(self, tracker_with_plan):
        """测试步骤失败"""
        tracker_with_plan.start_step(1)
        tracker_with_plan.fail_step(1, "文件权限不足")
        
        step = tracker_with_plan.current_plan.steps[0]
        assert step.status == StepStatus.FAILED
        assert step.error == "文件权限不足"
    
    def test_skip_step(self, tracker_with_plan):
        """测试跳过步骤"""
        tracker_with_plan.skip_step(1, "已经存在")
        
        step = tracker_with_plan.current_plan.steps[0]
        assert step.status == StepStatus.SKIPPED
    
    def test_detect_skip_ahead_anomaly(self, tracker_with_plan):
        """测试检测跳步异常"""
        tracker_with_plan.start_step(1)
        
        # 模拟 LLM 响应中明确提出要跳到步骤 3
        # 使用 tracker._detect_skip_ahead 中定义的触发词
        anomaly = tracker_with_plan.detect_anomaly(
            "我现在要执行 Step 3: 添加测试用例",
            []
        )
        
        assert anomaly is not None
        assert "跳步" in anomaly
    
    def test_detect_loop_anomaly(self, tracker_with_plan):
        """测试检测死循环异常"""
        tracker_with_plan.start_step(1)
        
        # 手动填充 _recent_tool_calls 来触发死循环检测
        tracker_with_plan._recent_tool_calls = [
            "read_file", "read_file", "read_file",
            "read_file", "read_file", "read_file"
        ]
        
        anomaly = tracker_with_plan.detect_anomaly(
            "正在处理",
            []
        )
        
        assert anomaly is not None
        assert "循环" in anomaly or "重复" in anomaly
    
    def test_no_anomaly_for_normal_execution(self, tracker_with_plan):
        """测试正常执行不触发异常"""
        tracker_with_plan.start_step(1)
        
        # 正常的响应，不提及后续步骤内容
        anomaly = tracker_with_plan.detect_anomaly(
            "我正在创建文件结构",
            [{"name": "write_file", "arguments": {"path": "main.py"}}]
        )
        
        # 不应该检测到异常
        assert anomaly is None
    
    def test_get_correction_prompt(self, tracker_with_plan):
        """测试生成修正提示"""
        from unittest.mock import patch
        # 导入模块以重置全局单例
        from agent.code_agent.prompts import prompt_loader
        
        tracker_with_plan.start_step(1)
        anomaly = "跳步警告: 检测到提前执行步骤3"
        
        # 重置单例，强制重新加载配置
        prompt_loader._prompt_loader_instance = None
        
        # mock prompt loader
        with patch('agent.code_agent.prompts.prompt_loader.CodeAgentPromptLoader._load_config') as mock_load:
            # 这里的返回值会作为 loader.config
            mock_load.return_value = {
                "correction_prompt": "Anomaly: {anomaly}, Step: {step_id}"
            }
            
            correction = tracker_with_plan.get_correction_prompt(anomaly)
            
            assert "Anomaly: 跳步警告" in correction
            assert "Step: 1" in correction
    
    def test_progress_summary(self, tracker_with_plan):
        """测试进度摘要"""
        # 完成第一步
        tracker_with_plan.start_step(1)
        tracker_with_plan.complete_step(1, StepResult(
            success=True, 
            response="done",
            tool_calls=[{"name": "write_file"}]
        ))
        
        # 开始第二步
        tracker_with_plan.start_step(2)
        
        summary = tracker_with_plan.get_progress_summary()
        
        assert "progress" in summary
        assert summary["progress"]["total"] == 3
        assert summary["progress"]["done"] == 1
        assert summary["current_step"]["id"] == 2
    
    def test_should_replan_on_multiple_anomalies(self, tracker_with_plan):
        """测试多次异常后需要重新规划"""
        tracker_with_plan.start_step(1)
        
        # 触发多次异常
        for i in range(tracker_with_plan.max_anomalies + 1):
            # 强制设置异常计数
            tracker_with_plan.anomaly_count = i + 1
        
        assert tracker_with_plan.should_replan() is True
    
    def test_should_replan_on_step_failure(self, tracker_with_plan):
        """测试步骤失败后需要重新规划"""
        tracker_with_plan.start_step(1)
        tracker_with_plan.fail_step(1, "错误")
        
        # 步骤失败后应该考虑重新规划
        assert tracker_with_plan.should_replan() is True
    
    def test_no_replan_on_success(self, tracker_with_plan):
        """测试成功执行不需要重新规划"""
        tracker_with_plan.start_step(1)
        tracker_with_plan.complete_step(1, StepResult(
            success=True,
            response="done",
            tool_calls=[]
        ))
        
        tracker_with_plan.start_step(2)
        
        assert tracker_with_plan.should_replan() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
