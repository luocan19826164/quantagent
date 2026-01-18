"""
计划状态持久化存储
支持计划和执行状态的保存与恢复
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from .models import Plan, PlanStep, PlanStatus, StepStatus, StepResult


class PlanStorage:
    """
    计划状态存储管理器
    
    将计划和执行状态持久化到文件系统，支持：
    1. 保存/加载计划
    2. 更新步骤状态
    3. 恢复中断的执行
    4. 执行历史记录
    """
    
    def __init__(self, storage_path: str):
        """
        初始化存储管理器
        
        Args:
            storage_path: 存储路径（通常是工作区的 .plans 目录）
        """
        self.storage_path = storage_path
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        os.makedirs(self.storage_path, exist_ok=True)
        os.makedirs(os.path.join(self.storage_path, "history"), exist_ok=True)
    
    def _get_plan_path(self, plan_id: str) -> str:
        """获取计划文件路径"""
        return os.path.join(self.storage_path, f"{plan_id}.json")
    
    def _get_current_path(self) -> str:
        """获取当前活动计划的路径"""
        return os.path.join(self.storage_path, "current.json")
    
    def save_plan(self, plan: Plan) -> bool:
        """
        保存计划
        
        Args:
            plan: 计划对象
            
        Returns:
            是否保存成功
        """
        try:
            plan_data = plan.to_dict()
            plan_data["saved_at"] = datetime.now().isoformat()
            
            # 保存到计划文件
            plan_path = self._get_plan_path(plan.id)
            with open(plan_path, 'w', encoding='utf-8') as f:
                json.dump(plan_data, f, ensure_ascii=False, indent=2)
            
            # 更新当前计划引用
            current_data = {
                "plan_id": plan.id,
                "task": plan.task,
                "status": plan.status.value,
                "updated_at": datetime.now().isoformat()
            }
            with open(self._get_current_path(), 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            
            logging.debug(f"Plan saved: {plan.id}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to save plan: {e}")
            return False
    
    def load_plan(self, plan_id: str) -> Optional[Plan]:
        """
        加载计划
        
        Args:
            plan_id: 计划ID
            
        Returns:
            计划对象，不存在则返回 None
        """
        try:
            plan_path = self._get_plan_path(plan_id)
            if not os.path.exists(plan_path):
                return None
            
            with open(plan_path, 'r', encoding='utf-8') as f:
                plan_data = json.load(f)
            
            return Plan.from_dict(plan_data)
            
        except Exception as e:
            logging.error(f"Failed to load plan {plan_id}: {e}")
            return None
    
    def load_current_plan(self) -> Optional[Plan]:
        """加载当前活动计划"""
        try:
            current_path = self._get_current_path()
            if not os.path.exists(current_path):
                return None
            
            with open(current_path, 'r', encoding='utf-8') as f:
                current_data = json.load(f)
            
            plan_id = current_data.get("plan_id")
            if not plan_id:
                return None
            
            return self.load_plan(plan_id)
            
        except Exception as e:
            logging.error(f"Failed to load current plan: {e}")
            return None
    
    def update_step_status(self, plan_id: str, step_id: int, 
                          status: StepStatus, result: StepResult = None) -> bool:
        """
        更新步骤状态
        
        Args:
            plan_id: 计划ID
            step_id: 步骤ID
            status: 新状态
            result: 步骤结果（可选）
            
        Returns:
            是否更新成功
        """
        plan = self.load_plan(plan_id)
        if not plan:
            return False
        
        # 查找并更新步骤
        for step in plan.steps:
            if step.id == step_id:
                step.status = status
                if result:
                    step.files_changed = result.files_changed
                    step.error = result.error if not result.success else None
                break
        
        return self.save_plan(plan)
    
    def archive_plan(self, plan: Plan) -> bool:
        """
        归档已完成的计划
        
        Args:
            plan: 计划对象
            
        Returns:
            是否归档成功
        """
        try:
            # 保存到历史目录
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            history_path = os.path.join(
                self.storage_path, "history", 
                f"{plan.id}_{timestamp}.json"
            )
            
            plan_data = plan.to_dict()
            plan_data["archived_at"] = datetime.now().isoformat()
            
            with open(history_path, 'w', encoding='utf-8') as f:
                json.dump(plan_data, f, ensure_ascii=False, indent=2)
            
            # 删除活动计划文件
            plan_path = self._get_plan_path(plan.id)
            if os.path.exists(plan_path):
                os.remove(plan_path)
            
            # 清除当前计划引用
            current_path = self._get_current_path()
            if os.path.exists(current_path):
                with open(current_path, 'r', encoding='utf-8') as f:
                    current_data = json.load(f)
                if current_data.get("plan_id") == plan.id:
                    os.remove(current_path)
            
            logging.info(f"Plan archived: {plan.id}")
            return True
            
        except Exception as e:
            logging.error(f"Failed to archive plan: {e}")
            return False
    
    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取执行历史
        
        Args:
            limit: 返回的最大记录数
            
        Returns:
            历史记录列表
        """
        history = []
        history_path = os.path.join(self.storage_path, "history")
        
        try:
            files = sorted(
                Path(history_path).glob("*.json"),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )[:limit]
            
            for f in files:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                    history.append({
                        "id": data.get("id"),
                        "task": data.get("task"),
                        "status": data.get("status"),
                        "created_at": data.get("created_at"),
                        "archived_at": data.get("archived_at"),
                        "step_count": len(data.get("steps", []))
                    })
        except Exception as e:
            logging.error(f"Failed to get history: {e}")
        
        return history
    
    def has_unfinished_plan(self) -> bool:
        """检查是否有未完成的计划"""
        plan = self.load_current_plan()
        if not plan:
            return False
        
        return plan.status in (PlanStatus.EXECUTING, PlanStatus.AWAITING_APPROVAL)
    
    def clear_current(self) -> bool:
        """清除当前计划"""
        try:
            current_path = self._get_current_path()
            if os.path.exists(current_path):
                os.remove(current_path)
            return True
        except Exception as e:
            logging.error(f"Failed to clear current plan: {e}")
            return False

