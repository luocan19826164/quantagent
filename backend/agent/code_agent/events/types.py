"""
事件类型枚举定义
"""

from enum import Enum


class EventType(str, Enum):
    """Agent 事件类型枚举
    
    继承 str 使得序列化时自动转为字符串值
    
    事件分类说明：
    - Plan*: 计划的生命周期（创建、审批、修改）
    - PlanExecution*: 计划执行的生命周期（run() 方法触发）
    - Step*: 单个步骤的执行
    - Tool*: 工具调用
    - FileRun*: 独立文件执行（execute_file() 方法触发）
    """
    # === 计划生命周期 ===
    PLAN_CREATED = "plan_created"
    # PLAN_COMPLETED 已合并到 PLAN_EXECUTION_COMPLETED
    
    # === 计划执行生命周期 ===
    # 由 run() -> _execute_plan() 触发，执行整个任务计划（包含多个步骤）
    PLAN_EXECUTION_STARTED = "execution_started"
    PLAN_EXECUTION_COMPLETED = "execution_completed"
    PLAN_EXECUTION_FAILED = "execution_failed"
    PLAN_EXECUTION_CANCELLED = "execution_cancelled"
    
    # === 步骤执行 ===
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_OUTPUT = "step_output"
    STEP_ERROR = "step_error"
    
    # === 工具调用 ===
    TOOL_CALLS = "tool_calls"
    TOOL_RESULT = "tool_result"
    
    # === 文件运行（独立功能）===
    # 由 execute_file() 触发，用户手动运行某个 .py 文件
    # 与计划执行是独立的两个功能入口
    FILE_RUN_STARTED = "started"
    FILE_RUN_STDOUT = "stdout"
    FILE_RUN_STDERR = "stderr"
    FILE_RUN_EXIT = "exit"
    
    # === 通用事件 ===
    STATUS = "status"
    ERROR = "error"
    TOKEN = "token"
    FILE_CHANGE = "file_change"
    ANOMALY_DETECTED = "anomaly_detected"
    REPLAN_WARNING = "replan_warning"
    
    # === 响应模式 ===
    RESPONSE_START = "response_start"  # 响应开始，包含 mode: "direct" | "plan"
    RESPONSE_END = "response_end"      # 响应结束

