# Agent.py 重构方案

## 设计决策总结

| 问题 | 决策 | 说明 |
|------|------|------|
| AwaitingApprovalEvent 定位 | **Plan 专用** | 当前仅用于计划审批，类名改为 `PlanAwaitingApprovalEvent`。如未来需要其他审批场景可泛化 |
| PlanExecution vs FileRun | **明确区分** | 两个独立功能入口：`PlanExecution*` 是计划执行，`FileRun*` 是文件运行 |
| 字段命名统一 | 待确认 | 建议统一使用 `files_changed` |

---

## 一、问题分析

### 1.1 事件类型字符串散落各处

当前代码中存在大量硬编码的事件类型字符串，分布在 `agent.py` 的多个位置：

```python
# 计划生命周期
yield {"type": "plan_created", ...}
yield {"type": "plan_completed", ...}
yield {"type": "plan_approved", ...}
yield {"type": "plan_rejected", ...}
yield {"type": "plan_modified", ...}
yield {"type": "awaiting_approval", ...}  # Plan 审批专用

# 计划执行生命周期（run() -> _execute_plan()）
yield {"type": "execution_started", ...}
yield {"type": "execution_completed", ...}
yield {"type": "execution_failed", ...}
yield {"type": "execution_cancelled", ...}

# 步骤相关
yield {"type": "step_started", ...}
yield {"type": "step_completed", ...}
yield {"type": "step_output", ...}
yield {"type": "step_error", ...}

# 工具相关
yield {"type": "tool_calls", ...}
yield {"type": "tool_result", ...}

# 文件运行（execute_file() 独立功能）
yield {"type": "started", ...}   # 文件开始运行
yield {"type": "stdout", ...}    # 标准输出
yield {"type": "stderr", ...}    # 标准错误
yield {"type": "exit", ...}      # 运行退出

# 其他
yield {"type": "status", ...}
yield {"type": "error", ...}
yield {"type": "file_change", ...}
yield {"type": "token", ...}
yield {"type": "anomaly_detected", ...}
yield {"type": "replan_warning", ...}
```

**问题**：
- 字符串拼写错误难以发现
- IDE 无法提供自动补全
- 重构时容易遗漏

### 1.2 事件数据结构不一致

同一类型的事件，字段名称不统一：

```python
# error 字段不一致
yield {"type": "error", "message": str(e)}      # 用 message
yield {"type": "error", "error": str(e)}        # 用 error

# 文件变更字段不一致
yield {"type": "step_completed", "files_changed": [...]}    # files_changed
yield {"type": "plan_completed", "file_changes": [...]}     # file_changes

# step_id 有时有有时没有
yield {"type": "step_output", "step_id": step.id, "content": ...}
yield {"type": "tool_result", "step_id": step.id, "tool": ...}
```

**问题**：
- 前端需要处理多种字段名
- 容易产生 KeyError
- 难以维护和扩展

### 1.3 缺乏类型安全

返回的 `Dict[str, Any]` 没有类型约束：
- IDE 无法检查字段是否正确
- 运行时才能发现错误
- 文档和代码不同步

---

## 二、重构目标

1. **类型安全**：所有事件类型和数据结构都有明确的类型定义
2. **统一接口**：相同含义的字段使用相同的名称
3. **易于扩展**：新增事件类型时有清晰的模式
4. **向后兼容**：重构后序列化格式与前端兼容

---

## 三、重构方案

### 3.1 新建文件结构

```
backend/agent/code_agent/
├── events/
│   ├── __init__.py          # 导出所有事件类型
│   ├── types.py              # EventType 枚举定义
│   ├── base.py               # 基础事件类
│   ├── plan_events.py        # 计划相关事件
│   ├── step_events.py        # 步骤相关事件
│   ├── execution_events.py   # 执行相关事件
│   └── tool_events.py        # 工具相关事件
```

### 3.2 事件类型枚举 (`events/types.py`)

```python
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
    PLAN_COMPLETED = "plan_completed"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    PLAN_MODIFIED = "plan_modified"
    PLAN_AWAITING_APPROVAL = "awaiting_approval"  # Plan 专用审批
    
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
```

> **设计说明**：`PlanExecution*` 和 `FileRun*` 是两个独立的功能：
> - `PlanExecution*`：用户发起任务 → Agent 生成计划 → 逐步执行计划中的步骤
> - `FileRun*`：用户直接点击"运行"按钮执行某个 Python 文件

### 3.3 基础事件类 (`events/base.py`)

```python
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from .types import EventType


@dataclass
class BaseEvent:
    """事件基类"""
    type: EventType
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，用于 JSON 序列化"""
        result = asdict(self)
        # EventType 枚举转为字符串
        result["type"] = self.type.value
        # 移除 None 值
        return {k: v for k, v in result.items() if v is not None}


@dataclass
class MessageEvent(BaseEvent):
    """带消息的事件"""
    message: str = ""


@dataclass
class ErrorEvent(BaseEvent):
    """错误事件 - 统一使用 error 字段"""
    type: EventType = field(default=EventType.ERROR)
    error: str = ""
    
    # 兼容旧的 message 字段
    @property
    def message(self) -> str:
        return self.error
```

### 3.4 计划相关事件 (`events/plan_events.py`)

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from .base import BaseEvent, MessageEvent
from .types import EventType


@dataclass
class PlanCreatedEvent(MessageEvent):
    """计划创建事件"""
    type: EventType = field(default=EventType.PLAN_CREATED)
    plan: Optional[Dict[str, Any]] = None


@dataclass
class PlanCompletedEvent(BaseEvent):
    """计划完成事件"""
    type: EventType = field(default=EventType.PLAN_COMPLETED)
    success: bool = True
    summary: str = ""
    file_changes: List[str] = field(default_factory=list)


@dataclass
class PlanAwaitingApprovalEvent(MessageEvent):
    """计划等待审批事件
    
    当前专用于 Plan 审批场景。
    
    扩展说明：如果未来需要其他审批场景（如危险操作确认），
    可以考虑泛化为通用审批事件：
    - 添加 approval_type: str 字段区分场景
    - 使用 payload: Dict 替代固定的 plan 字段
    """
    type: EventType = field(default=EventType.PLAN_AWAITING_APPROVAL)
    plan: Optional[Dict[str, Any]] = None


@dataclass
class PlanApprovedEvent(MessageEvent):
    """计划审批通过事件"""
    type: EventType = field(default=EventType.PLAN_APPROVED)


@dataclass
class PlanRejectedEvent(MessageEvent):
    """计划拒绝事件"""
    type: EventType = field(default=EventType.PLAN_REJECTED)
    reason: str = ""


@dataclass
class PlanModifiedEvent(BaseEvent):
    """计划修改事件"""
    type: EventType = field(default=EventType.PLAN_MODIFIED)
    plan: Optional[Dict[str, Any]] = None
```

### 3.5 步骤相关事件 (`events/step_events.py`)

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from .base import BaseEvent
from .types import EventType


@dataclass
class StepStartedEvent(BaseEvent):
    """步骤开始事件"""
    type: EventType = field(default=EventType.STEP_STARTED)
    step_id: int = 0
    description: str = ""
    progress: Optional[Dict[str, Any]] = None


@dataclass
class StepCompletedEvent(BaseEvent):
    """步骤完成事件"""
    type: EventType = field(default=EventType.STEP_COMPLETED)
    step_id: int = 0
    files_changed: List[str] = field(default_factory=list)
    progress: Optional[Dict[str, Any]] = None


@dataclass
class StepOutputEvent(BaseEvent):
    """步骤输出事件"""
    type: EventType = field(default=EventType.STEP_OUTPUT)
    step_id: int = 0
    content: str = ""


@dataclass
class StepErrorEvent(BaseEvent):
    """步骤错误事件"""
    type: EventType = field(default=EventType.STEP_ERROR)
    step_id: int = 0
    error: str = ""
```

### 3.6 执行相关事件 (`events/execution_events.py`)

事件分为两组：
- **计划执行事件 (PlanExecution\*)**: 由 `run()` → `_execute_plan()` 触发，执行整个任务计划
- **文件运行事件 (FileRun\*)**: 由 `execute_file()` 触发，用户手动运行单个 Python 文件

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from .base import BaseEvent, MessageEvent
from .types import EventType


# ============================================================
# 计划执行事件 (Plan Execution)
# 场景：用户发起任务 → Agent 生成计划 → 执行计划中的多个步骤
# ============================================================

@dataclass
class PlanExecutionStartedEvent(MessageEvent):
    """计划执行开始事件
    
    触发时机：_execute_plan() 开始执行
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_STARTED)
    plan: Optional[Dict[str, Any]] = None


@dataclass
class PlanExecutionCompletedEvent(MessageEvent):
    """计划执行完成事件
    
    触发时机：所有步骤执行完成
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_COMPLETED)
    plan: Optional[Dict[str, Any]] = None
    summary: str = ""


@dataclass
class PlanExecutionFailedEvent(MessageEvent):
    """计划执行失败事件
    
    触发时机：某个步骤执行失败
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_FAILED)
    plan: Optional[Dict[str, Any]] = None
    step_id: Optional[int] = None
    error: str = ""


@dataclass
class PlanExecutionCancelledEvent(MessageEvent):
    """计划执行取消事件
    
    触发时机：用户取消执行或检测到取消标志
    """
    type: EventType = field(default=EventType.PLAN_EXECUTION_CANCELLED)


# ============================================================
# 文件运行事件 (File Run)
# 场景：用户点击"运行"按钮，直接执行某个 .py 文件
# 这是一个独立功能，与计划执行无关
# ============================================================

@dataclass
class FileRunStartedEvent(BaseEvent):
    """文件运行开始事件
    
    触发时机：execute_file() 开始执行
    """
    type: EventType = field(default=EventType.FILE_RUN_STARTED)
    file: str = ""


@dataclass
class FileRunStdoutEvent(BaseEvent):
    """文件运行标准输出事件"""
    type: EventType = field(default=EventType.FILE_RUN_STDOUT)
    content: str = ""


@dataclass
class FileRunStderrEvent(BaseEvent):
    """文件运行标准错误事件"""
    type: EventType = field(default=EventType.FILE_RUN_STDERR)
    content: str = ""


@dataclass
class FileRunExitEvent(BaseEvent):
    """文件运行退出事件
    
    触发时机：Python 脚本执行完成
    """
    type: EventType = field(default=EventType.FILE_RUN_EXIT)
    exit_code: int = 0
    duration: float = 0.0
```

### 3.7 工具相关事件 (`events/tool_events.py`)

```python
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from .base import BaseEvent
from .types import EventType


@dataclass
class ToolCall:
    """单个工具调用"""
    name: str
    arguments: Dict[str, Any]


@dataclass
class ToolCallsEvent(BaseEvent):
    """工具调用事件"""
    type: EventType = field(default=EventType.TOOL_CALLS)
    step_id: int = 0
    calls: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolResultEvent(BaseEvent):
    """工具结果事件"""
    type: EventType = field(default=EventType.TOOL_RESULT)
    step_id: int = 0
    tool: str = ""
    success: bool = True
    output: str = ""
    error: Optional[str] = None
```

### 3.8 通用事件 (`events/base.py` 补充)

```python
@dataclass
class StatusEvent(MessageEvent):
    """状态事件"""
    type: EventType = field(default=EventType.STATUS)


@dataclass
class TokenEvent(BaseEvent):
    """Token 流式事件"""
    type: EventType = field(default=EventType.TOKEN)
    content: str = ""


@dataclass
class FileChangeEvent(BaseEvent):
    """文件变更事件"""
    type: EventType = field(default=EventType.FILE_CHANGE)
    path: str = ""


@dataclass
class AnomalyDetectedEvent(BaseEvent):
    """异常检测事件"""
    type: EventType = field(default=EventType.ANOMALY_DETECTED)
    step_id: int = 0
    anomaly: str = ""


@dataclass
class ReplanWarningEvent(MessageEvent):
    """重新规划警告事件"""
    type: EventType = field(default=EventType.REPLAN_WARNING)
```

---

## 四、重构后的 Agent 代码示例

### 4.1 导入和初始化

```python
from .events import (
    EventType,
    # 计划生命周期事件
    PlanCreatedEvent, PlanCompletedEvent, PlanAwaitingApprovalEvent,
    PlanApprovedEvent, PlanRejectedEvent, PlanModifiedEvent,
    # 计划执行事件
    PlanExecutionStartedEvent, PlanExecutionCompletedEvent, 
    PlanExecutionFailedEvent, PlanExecutionCancelledEvent,
    # 步骤事件
    StepStartedEvent, StepCompletedEvent, StepOutputEvent, StepErrorEvent,
    # 工具事件
    ToolCallsEvent, ToolResultEvent,
    # 文件运行事件（独立功能）
    FileRunStartedEvent, FileRunStdoutEvent, FileRunStderrEvent, FileRunExitEvent,
    # 通用事件
    StatusEvent, ErrorEvent, TokenEvent, FileChangeEvent,
    AnomalyDetectedEvent, ReplanWarningEvent,
)
```

### 4.2 重构前后对比

**重构前**：
```python
yield {"type": "error", "message": str(e)}
yield {"type": "plan_created", "plan": plan.to_dict(), "message": "..."}
yield {"type": "step_completed", "step_id": step.id, "files_changed": [...]}
```

**重构后**：
```python
yield ErrorEvent(error=str(e)).to_dict()
yield PlanCreatedEvent(plan=plan.to_dict(), message="...").to_dict()
yield StepCompletedEvent(step_id=step.id, files_changed=[...]).to_dict()
```

### 4.3 类型检查优势

```python
# IDE 会提示错误：StepCompletedEvent 没有 file_changes 参数
yield StepCompletedEvent(step_id=1, file_changes=[...])  # ❌ 错误

# 正确写法
yield StepCompletedEvent(step_id=1, files_changed=[...])  # ✅ 正确
```

---

## 五、迁移步骤

### Phase 1: 创建事件模块（不影响现有代码）
1. 创建 `events/` 目录和所有事件类
2. 添加单元测试验证序列化格式兼容

### Phase 2: 逐步迁移 Agent 代码
1. 先迁移 `execute_file` 方法（较简单）
2. 迁移 `run` 方法
3. 迁移 `_execute_plan` 和 `_execute_step`
4. 迁移其他方法

### Phase 3: 清理
1. 移除旧的字典字面量
2. 更新文档
3. 验证前端兼容性

---

## 六、测试计划

### 6.1 单元测试

```python
def test_event_serialization():
    """测试事件序列化格式"""
    event = PlanCreatedEvent(
        plan={"id": "123", "steps": []},
        message="计划已创建"
    )
    result = event.to_dict()
    
    assert result["type"] == "plan_created"
    assert result["plan"]["id"] == "123"
    assert result["message"] == "计划已创建"


def test_error_event_compatibility():
    """测试错误事件向后兼容"""
    event = ErrorEvent(error="Something went wrong")
    result = event.to_dict()
    
    assert result["type"] == "error"
    assert result["error"] == "Something went wrong"
    # 兼容旧字段
    assert event.message == "Something went wrong"
```

### 6.2 集成测试

- 运行现有的 E2E 测试
- 验证前端能正确解析所有事件类型

---

## 七、风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 前端兼容性 | 中 | 保持序列化格式不变，新增字段可选 |
| 性能影响 | 低 | dataclass 创建开销可忽略 |
| 遗漏事件类型 | 低 | 全量搜索 `"type":` 确保覆盖 |

---

## 八、预期收益

1. **代码质量**：类型安全，IDE 支持更好
2. **可维护性**：事件定义集中管理
3. **可扩展性**：新增事件类型有清晰模式
4. **文档化**：dataclass 自带文档价值
5. **测试友好**：事件对象更容易断言

---

## 九、待确认问题

1. ~~**事件命名**：`FILE_EXEC_STARTED` vs `STARTED` - 是否需要更明确的命名？~~
   - ✅ 已确认：使用 `FILE_RUN_*` 前缀区分，与 `PLAN_EXECUTION_*` 明确区分

2. **字段统一**：`files_changed` vs `file_changes` - 统一使用哪个？
   - 建议：统一使用 `files_changed`（更符合语法，表示"已变更的文件"）

3. **Optional 字段**：是否所有可选字段都需要在序列化时移除？
   - 建议：移除 `None` 值，保持 JSON 简洁

4. **前端对接**：是否需要同步更新前端类型定义？
   - 取决于前端是否有 TypeScript 类型定义

---

## 十、时间估算

| 阶段 | 预估时间 |
|------|----------|
| Phase 1: 创建事件模块 | 2h |
| Phase 2: 迁移代码 | 3h |
| Phase 3: 测试和清理 | 2h |
| **总计** | **7h** |

