"""
Plan 数据模型
定义计划和步骤的数据结构
"""

import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum


def generate_plan_id() -> str:
    """生成唯一的计划ID"""
    return str(uuid.uuid4())[:8]


class StepStatus(str, Enum):
    """步骤状态"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStatus(str, Enum):
    """计划状态"""
    PLANNING = "planning"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class PlanStep:
    """计划步骤"""
    id: int
    description: str
    status: StepStatus = StepStatus.PENDING
    expected_outcome: str = ""
    tools_needed: List[str] = field(default_factory=list)
    
    # 执行记录
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "expected_outcome": self.expected_outcome,
            "tools_needed": self.tools_needed,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "files_changed": self.files_changed,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        return cls(
            id=data["id"],
            description=data["description"],
            status=StepStatus(data.get("status", "pending")),
            expected_outcome=data.get("expected_outcome", ""),
            tools_needed=data.get("tools_needed", []),
        )


@dataclass
class Plan:
    """执行计划"""
    task: str
    steps: List[PlanStep]
    id: str = field(default_factory=generate_plan_id)
    current_step_id: int = 1
    status: PlanStatus = PlanStatus.PLANNING
    
    # 元信息
    created_at: datetime = field(default_factory=datetime.now)
    version: int = 1
    replan_count: int = 0
    
    def get_current_step(self) -> Optional[PlanStep]:
        """获取当前步骤"""
        for step in self.steps:
            if step.id == self.current_step_id:
                return step
        return None
    
    def get_next_pending_step(self) -> Optional[PlanStep]:
        """获取下一个待执行的步骤"""
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                return step
        return None
    
    def advance_to_next_step(self) -> bool:
        """推进到下一步"""
        next_step = self.get_next_pending_step()
        if next_step:
            self.current_step_id = next_step.id
            return True
        return False
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度统计"""
        done = sum(1 for s in self.steps if s.status == StepStatus.DONE)
        failed = sum(1 for s in self.steps if s.status == StepStatus.FAILED)
        total = len(self.steps)
        return {
            "total": total,
            "done": done,
            "failed": failed,
            "pending": total - done - failed,
            "progress_percent": int(done / total * 100) if total > 0 else 0,
            "current_step": self.current_step_id
        }
    
    def is_complete(self) -> bool:
        """检查计划是否完成"""
        return all(
            s.status in (StepStatus.DONE, StepStatus.SKIPPED) 
            for s in self.steps
        )
    
    def has_failed(self) -> bool:
        """检查计划是否失败"""
        return any(s.status == StepStatus.FAILED for s in self.steps)
    
    def to_summary(self) -> str:
        """生成计划摘要（给 LLM 看）"""
        lines = [f"任务: {self.task}", "", "执行计划:"]
        for step in self.steps:
            icon = {
                StepStatus.PENDING: "⬜",
                StepStatus.IN_PROGRESS: "🔄",
                StepStatus.DONE: "✅",
                StepStatus.FAILED: "❌",
                StepStatus.SKIPPED: "⏭️"
            }.get(step.status, "⬜")
            current = " 👈 [当前]" if step.id == self.current_step_id else ""
            lines.append(f"  {icon} Step {step.id}: {step.description}{current}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_id": self.current_step_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "version": self.version,
            "replan_count": self.replan_count,
            "progress": self.get_progress()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        plan = cls(
            task=data["task"],
            steps=[PlanStep.from_dict(s) for s in data["steps"]],
            current_step_id=data.get("current_step_id", 1),
            status=PlanStatus(data.get("status", "planning")),
            version=data.get("version", 1),
            replan_count=data.get("replan_count", 0)
        )
        # 如果有保存的 id，恢复它
        if "id" in data:
            plan.id = data["id"]
        return plan


@dataclass
class StepResult:
    """步骤执行结果"""
    success: bool
    response: str = ""
    files_changed: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response,
            "files_changed": self.files_changed,
            "tool_calls": self.tool_calls,
            "error": self.error
        }

