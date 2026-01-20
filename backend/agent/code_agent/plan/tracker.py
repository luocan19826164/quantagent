"""
Plan Tracker - 计划追踪器
防止 LLM 飘离的核心组件
"""

import re
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from .models import Plan, PlanStep, StepStatus, StepResult
# 避免循环导入，延迟导入 get_code_agent_prompt_loader


class PlanTracker:
    """
    计划追踪器 - 防止 LLM 飘离的核心组件
    
    功能:
    1. 追踪步骤执行状态
    2. 检测异常行为（跳步、偏离、死循环）
    3. 提供进度报告
    4. 生成修正提示词
    """
    
    def __init__(self):
        self.current_plan: Optional[Plan] = None
        self.execution_history: List[Dict[str, Any]] = []
        self.anomaly_count: int = 0
        self.max_anomalies: int = 3  # 连续异常次数阈值
        self._recent_tool_calls: List[str] = []  # 用于死循环检测
    
    def set_plan(self, plan: Plan):
        """设置当前计划"""
        self.current_plan = plan
        self.anomaly_count = 0
        self.execution_history = []
        self._recent_tool_calls = []
        logging.info(f"PlanTracker: Set plan with {len(plan.steps)} steps")
    
    def start_step(self, step_id: int):
        """标记步骤开始"""
        step = self._get_step(step_id)
        if step:
            step.status = StepStatus.IN_PROGRESS
            step.started_at = datetime.now()
            self.current_plan.current_step_id = step_id
            logging.info(f"PlanTracker: Started step {step_id}: {step.description}")
    
    def complete_step(self, step_id: int, result: StepResult):
        """标记步骤完成"""
        step = self._get_step(step_id)
        if step:
            step.status = StepStatus.DONE
            step.completed_at = datetime.now()
            step.result = result.response
            step.files_changed = result.files_changed
            step.tool_calls = result.tool_calls
            
            self.execution_history.append({
                "step_id": step_id,
                "timestamp": datetime.now().isoformat(),
                "result": result.to_dict()
            })
            
            # 记录工具调用（用于死循环检测）
            for tc in result.tool_calls:
                self._recent_tool_calls.append(tc.get("name", ""))
            
            # 步骤成功完成，重置异常计数
            self.anomaly_count = 0
            
            logging.info(f"PlanTracker: Completed step {step_id}")
    
    def fail_step(self, step_id: int, error: str):
        """标记步骤失败"""
        step = self._get_step(step_id)
        if step:
            step.status = StepStatus.FAILED
            step.error = error
            step.completed_at = datetime.now()
            logging.warning(f"PlanTracker: Step {step_id} failed: {error}")
    
    def skip_step(self, step_id: int, reason: str = ""):
        """跳过步骤"""
        step = self._get_step(step_id)
        if step:
            step.status = StepStatus.SKIPPED
            step.result = f"Skipped: {reason}"
            step.completed_at = datetime.now()
            logging.info(f"PlanTracker: Skipped step {step_id}: {reason}")
    
    def detect_anomaly(self, llm_response: str, tool_calls: List[Dict]) -> Optional[str]:
        """
        检测 LLM 响应是否偏离当前步骤
        
        检测类型:
        1. 跳步 - LLM 提前执行后续步骤的内容
        2. 偏离 - LLM 做了计划外的事情
        3. 死循环 - 重复执行相同操作
        4. 工具越权 - 使用了与当前步骤不匹配的工具
        """
        if not self.current_plan:
            return None
        
        current_step = self.current_plan.get_current_step()
        if not current_step:
            return None
        
        anomalies = []
        
        # 1. 检测跳步
        skip_anomaly = self._detect_skip_ahead(llm_response, current_step)
        if skip_anomaly:
            anomalies.append(skip_anomaly)
        
        # 2. 检测死循环
        loop_anomaly = self._detect_loop(tool_calls)
        if loop_anomaly:
            anomalies.append(loop_anomaly)
        
        # 3. 检测工具越权
        tool_anomaly = self._detect_tool_mismatch(tool_calls, current_step)
        if tool_anomaly:
            anomalies.append(tool_anomaly)
        
        # 4. 检测文件操作范围越权
        file_anomaly = self._detect_file_scope_violation(tool_calls, current_step)
        if file_anomaly:
            anomalies.append(file_anomaly)
        
        if anomalies:
            self.anomaly_count += 1
            anomaly_msg = "; ".join(anomalies)
            logging.warning(f"PlanTracker: Anomaly detected ({self.anomaly_count}/{self.max_anomalies}): {anomaly_msg}")
            return anomaly_msg
        
        # 没有异常，重置计数
        self.anomaly_count = 0
        return None
    
    def _detect_tool_mismatch(self, tool_calls: List[Dict], current_step: PlanStep) -> Optional[str]:
        """检测工具调用是否与当前步骤匹配"""
        if not current_step.tools_needed or not tool_calls:
            return None
        
        # 获取当前步骤声明需要的工具
        expected_tools = set(current_step.tools_needed)
        
        # 允许的通用工具（总是可以使用）
        universal_tools = {"read_file", "list_directory", "grep", "semantic_search", "get_file_outline"}
        
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            # 如果使用的工具既不在预期列表中，也不是通用工具
            if tool_name and tool_name not in expected_tools and tool_name not in universal_tools:
                # 检查是否是高风险操作
                if tool_name in ("write_file", "patch_file", "delete_file", "shell_exec"):
                    return f"工具越权: 当前步骤 ({current_step.description[:30]}...) 预期使用 {expected_tools}，但调用了 {tool_name}"
        
        return None
    
    def _detect_file_scope_violation(self, tool_calls: List[Dict], current_step: PlanStep) -> Optional[str]:
        """检测文件操作是否在预期范围内"""
        # 从步骤描述中提取预期的文件模式
        expected_files = self._extract_file_patterns(current_step.description)
        if not expected_files:
            return None
        
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            args = tc.get("arguments", {})
            
            # 只检查写入类操作
            if tool_name in ("write_file", "patch_file", "delete_file"):
                target_path = args.get("path", "")
                if target_path and not self._file_matches_patterns(target_path, expected_files):
                    # 这可能是正常的，只记录警告级别
                    logging.debug(f"File operation on unexpected path: {target_path}, expected patterns: {expected_files}")
        
        return None
    
    def _extract_file_patterns(self, text: str) -> List[str]:
        """从文本中提取文件路径模式"""
        # 匹配常见的文件路径模式
        import re
        patterns = []
        
        # 匹配 .py, .json, .yaml 等文件路径
        file_pattern = r'[\w\-\/\.]+\.(py|json|yaml|yml|txt|md|csv)'
        matches = re.findall(file_pattern, text, re.IGNORECASE)
        
        # 提取完整路径
        path_pattern = r'[\w\-\/\.]+\.(?:py|json|yaml|yml|txt|md|csv)'
        full_paths = re.findall(path_pattern, text, re.IGNORECASE)
        patterns.extend(full_paths)
        
        return list(set(patterns))
    
    def _file_matches_patterns(self, file_path: str, patterns: List[str]) -> bool:
        """检查文件路径是否匹配预期模式"""
        if not patterns:
            return True
        
        file_lower = file_path.lower()
        for pattern in patterns:
            pattern_lower = pattern.lower()
            # 简单匹配：路径包含模式或模式包含路径
            if pattern_lower in file_lower or file_lower.endswith(pattern_lower):
                return True
        
        return False
    
    def _detect_skip_ahead(self, llm_response: str, current_step: PlanStep) -> Optional[str]:
        """检测是否跳步"""
        # 注意：这个检测很容易产生误报（例如分析文件时提到后续步骤要处理的文件名）
        # 只有当 LLM 明确表示要执行后续步骤时才报警
        
        # 检测明确的跳步意图（而不是简单的关键词匹配）
        skip_indicators = [
            "我现在要执行 step",
            "跳到 step",
            "直接执行 step",
            "skip to step",
            "let me do step",
        ]
        
        response_lower = llm_response.lower()
        for indicator in skip_indicators:
            if indicator in response_lower:
                # 检查是否提到了后续步骤的编号
                for step in self.current_plan.steps:
                    if step.id > current_step.id and f"step {step.id}" in response_lower:
                        return f"跳步警告: LLM 试图跳到 Step {step.id}"
        
        # 放宽检测：不再因为简单的关键词匹配而报警
        return None
    
    def _detect_loop(self, tool_calls: List[Dict]) -> Optional[str]:
        """检测死循环"""
        if len(self._recent_tool_calls) < 6:
            return None
        
        # 检查最近的工具调用是否重复
        recent = self._recent_tool_calls[-6:]
        
        # 简单检测：如果最近6次调用完全相同的模式重复2次
        if len(recent) >= 6:
            pattern1 = recent[:3]
            pattern2 = recent[3:6]
            if pattern1 == pattern2:
                return f"死循环警告: 检测到重复的工具调用模式 {pattern1}"
        
        return None
    
    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词（简单实现）"""
        # 提取中文词语和英文单词
        # 过滤掉常见词
        common_words = {'的', '在', '和', '是', '将', '进行', '使用', '创建', '修改', 
                       'the', 'a', 'an', 'is', 'are', 'to', 'for', 'and', 'or'}
        
        # 中文分词（简单按字符）+ 英文单词
        words = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z_][a-zA-Z0-9_]*', text)
        
        # 过滤
        keywords = [w for w in words if len(w) > 2 and w.lower() not in common_words]
        
        return keywords[:5]  # 只取前5个关键词
    
    def should_replan(self) -> bool:
        """判断是否需要重新规划"""
        if not self.current_plan:
            return False
        
        # 连续多次异常
        if self.anomaly_count >= self.max_anomalies:
            logging.info(f"PlanTracker: Should replan due to {self.anomaly_count} anomalies")
            return True
        
        # 当前步骤失败
        current_step = self.current_plan.get_current_step()
        if current_step and current_step.status == StepStatus.FAILED:
            return True
        
        return False
    
    def get_correction_prompt(self, anomaly: str) -> str:
        """生成修正提示词"""
        if not self.current_plan:
            return ""
        
        current_step = self.current_plan.get_current_step()
        if not current_step:
            return ""
        
        from ..prompts.prompt_loader import get_code_agent_prompt_loader
        loader = get_code_agent_prompt_loader()
        template = loader.get_correction_prompt()
        
        return template.format(
            anomaly=anomaly,
            step_id=current_step.id,
            step_description=current_step.description,
            expected_outcome=current_step.expected_outcome or "完成该步骤的操作"
        )
    

    
    def get_progress_summary(self) -> Dict[str, Any]:
        """获取进度摘要"""
        if not self.current_plan:
            return {"status": "no_plan"}
        
        return {
            "plan_status": self.current_plan.status.value,
            "progress": self.current_plan.get_progress(),
            "current_step": self.current_plan.get_current_step().to_dict() if self.current_plan.get_current_step() else None,
            "anomaly_count": self.anomaly_count,
            "execution_history_count": len(self.execution_history)
        }
    
    def _get_step(self, step_id: int) -> Optional[PlanStep]:
        """获取指定步骤"""
        if not self.current_plan:
            return None
        for step in self.current_plan.steps:
            if step.id == step_id:
                return step
        return None

