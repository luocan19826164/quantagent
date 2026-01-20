"""
Plan-Execute Agent 主循环
核心 Agent 实现，负责任务规划和执行

这是 Code Agent 的唯一入口，所有文件变更必须通过工具调用完成。
"""

import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Generator
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from .plan import Plan, PlanStep, PlanStatus, StepStatus, StepResult, PlanTracker, Planner, PlanStorage
from .tools import create_tool_registry, ToolRegistry, FunctionCallHandler, CREATE_PLAN_TOOL_NAME
from .workspace_manager import WorkspaceManager
from .context import (
    CodeContext, CodeAgentContext, ConversationHistory, 
    MemoryContext, ExecutionContext, OutputRecord
)
from .prompts.prompt_loader import get_code_agent_prompt_loader
from .events import (
    EventType,
    # 基础事件
    ErrorEvent, StatusEvent, FileChangeEvent, AnomalyDetectedEvent, ReplanWarningEvent,
    ResponseStartEvent, ResponseEndEvent,
    # 计划生命周期
    PlanCreatedEvent,
    # 计划执行
    PlanExecutionStartedEvent, PlanExecutionCompletedEvent,
    PlanExecutionFailedEvent, PlanExecutionCancelledEvent,
    # 步骤
    StepStartedEvent, StepCompletedEvent, StepOutputEvent, StepErrorEvent,
    # 工具
    ToolCallsEvent, ToolResultEvent,
    # 文件运行
    FileRunStartedEvent, FileRunStdoutEvent, FileRunStderrEvent, FileRunExitEvent,
)
from utils.llm_config import resolve_llm_config


class PlanExecuteAgent:
    """
    Plan-Execute Agent
    
    这是 Code Agent 的统一入口，核心流程：
    1. PLAN: 生成执行计划
    2. EXECUTE: 逐步执行（所有操作通过工具调用）
    3. VERIFY: 验证结果
    
    安全保证：
    - 所有文件变更必须通过工具调用
    - 步骤级权限控制
    - 异常行为检测
    """
    
    def __init__(self, user_id: int, project_id: str, use_sandbox: bool = False, 
                 llm_config: Dict[str, Any] = None):
        """
        初始化 Agent
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            use_sandbox: 是否使用 Docker 沙箱执行（默认 False，仅在有 Docker 时启用）
            llm_config: 可选的 LLM 配置，如果不传则使用默认优先级
        """
        self.user_id = user_id
        self.project_id = project_id
        self.use_sandbox = use_sandbox
        
        # 工作区管理
        self.workspace = WorkspaceManager(user_id)
        project = self.workspace.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        self.project_name = project["name"]
        self.project_path = self.workspace.get_project_path(project_id)
        
        # 初始化 LLM（优先使用传入的配置）
        if llm_config is None:
            llm_config = resolve_llm_config("[CodeAgent]")
        else:
            logging.info(f"[CodeAgent] Using custom LLM config - Model: {llm_config.get('model')}")
        
        llm_kwargs = {
            "model": llm_config["model"],
            "temperature": 0.2,
            "api_key": llm_config["api_key"],
            "base_url": llm_config["base_url"],
            "streaming": True,  # 启用流式
        }
        if llm_config.get("extra_headers"):
            llm_kwargs["default_headers"] = llm_config["extra_headers"]
        
        self.llm = ChatOpenAI(**llm_kwargs)
        
        # 工具系统（带沙箱支持）
        self.tool_registry = create_tool_registry(
            self.project_path, 
            use_sandbox=use_sandbox,
            user_id=user_id,
            project_id=project_id
        )
        self.function_handler = FunctionCallHandler(self.tool_registry)
        
        # 计划系统
        self.planner = Planner(self.llm)
        self.tracker = PlanTracker()
        
        # 代码上下文（活跃文件追踪）
        self.code_context = CodeContext(
            workspace_root=self.project_path,
            max_files=10,
            max_content_per_file=5000
        )
        self._init_code_context()
        
        # 计划持久化存储
        plans_path = os.path.join(self.project_path, ".plans")
        self.plan_storage = PlanStorage(plans_path)
        
        # 统一上下文管理（新增）
        self.context = CodeAgentContext(
            session_id=f"{user_id}_{project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            project_id=project_id,
            code_context=self.code_context,
            conversation=ConversationHistory(max_messages=50),
            memory=MemoryContext(),
            execution_context=ExecutionContext()
        )
        
        # 会话状态
        self.current_plan: Optional[Plan] = None
        
        # 尝试恢复未完成的计划
        self._try_restore_plan()
        
        # 执行控制
        self._cancel_flag = threading.Event()
        self._executing = False
        
        logging.info(f"PlanExecuteAgent initialized for user {user_id}, project {project_id}")
    
    def _try_restore_plan(self):
        """尝试恢复未完成的计划"""
        if self.plan_storage.has_unfinished_plan():
            plan = self.plan_storage.load_current_plan()
            if plan:
                self.current_plan = plan
                self.tracker.set_plan(plan)
                logging.info(f"Restored unfinished plan: {plan.id}")
    
    def _init_code_context(self):
        """初始化代码上下文，加载文件树"""
        try:
            file_tree = []
            for root, dirs, files in os.walk(self.project_path):
                # 跳过隐藏目录和缓存目录
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                for f in files:
                    if f.startswith('.') or f.endswith('.pyc'):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, f), self.project_path)
                    file_tree.append(rel_path)
            
            self.code_context.file_tree = sorted(file_tree)
            logging.info(f"Code context initialized with {len(file_tree)} files")
        except Exception as e:
            logging.warning(f"Failed to init code context: {e}")
    
    def _update_code_context(self, tool_name: str, tool_args: Dict, result: Any):
        """
        工具调用后更新代码上下文
        
        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            result: 工具执行结果
        """
        if not result or not result.success:
            return
        
        try:
            if tool_name == "read_file":
                # 读取文件后添加到活跃文件（非编辑状态，可截断）
                path = tool_args.get("path", "")
                content = result.data.get("content", "") if result.data else ""
                self.code_context.add_file(path, content, is_editing=False)
                logging.info(f"Code context: Added file '{path}' ({len(content)} chars)")
                
            elif tool_name == "write_file":
                # 写入文件后更新活跃文件（标记为编辑状态，保留完整内容）
                path = tool_args.get("path", "")
                content = tool_args.get("content", "")
                self.code_context.add_file(path, content, is_editing=True)
                # 更新文件树
                if path not in self.code_context.file_tree:
                    self.code_context.file_tree.append(path)
                    self.code_context.file_tree.sort()
                logging.info(f"Code context: Updated file '{path}' (editing)")
                
            elif tool_name == "patch_file":
                # patch 后更新活跃文件（标记为编辑状态，保留完整内容）
                path = tool_args.get("path", "")
                new_content = result.data.get("new_content", "") if result.data else ""
                if new_content:
                    self.code_context.add_file(path, new_content, is_editing=True)
                    logging.info(f"Code context: Patched file '{path}' (editing)")
                    
            elif tool_name == "delete_file":
                # 删除文件后从上下文移除
                path = tool_args.get("path", "")
                self.code_context.remove_file(path)
                if path in self.code_context.file_tree:
                    self.code_context.file_tree.remove(path)
                logging.info(f"Code context: Removed file '{path}'")
                
        except Exception as e:
            logging.warning(f"Failed to update code context: {e}")
    
    # ==================== 公开 API（兼容原 CodeAgent）====================
    
    def chat_stream(self, user_input: str) -> Generator[Dict[str, Any], None, None]:
        """
        流式聊天接口（兼容原 CodeAgent.chat_stream）
        
        LLM 会自主决定执行模式（Plan 或 Direct）。
        
        Args:
            user_input: 用户输入
            
        Yields:
            事件字典:
            - {"type": "response_start", "mode": "plan"|"direct"}
            - {"type": "plan_created", "plan": {...}}  # 仅 Plan 模式
            - {"type": "step_started", "step_id": 1, ...}
            - {"type": "tool_result", ...}
            - {"type": "file_change", "path": "..."}
            - {"type": "response_end"}
            - {"type": "error", "message": "..."}
        """
        self._cancel_flag.clear()
        all_file_changes = []
        
        # 记录用户消息到对话历史
        self.context.conversation.add_user_message(user_input)
        
        try:
            for event in self.run(user_input):
                event_type = event.get("type")
                
                # 收集文件变更
                if event_type == EventType.STEP_COMPLETED.value:
                    files = event.get("files_changed", [])
                    for f in files:
                        if f not in all_file_changes:
                            all_file_changes.append(f)
                            yield FileChangeEvent(path=f).to_dict()
                    yield event
                elif event_type == EventType.FILE_CHANGE.value:
                    path = event.get("path")
                    if path and path not in all_file_changes:
                        all_file_changes.append(path)
                    yield event
                elif event_type == EventType.PLAN_EXECUTION_COMPLETED.value:
                    # 补充文件变更列表
                    event_file_changes = event.get("file_changes", [])
                    for f in event_file_changes:
                        if f not in all_file_changes:
                            all_file_changes.append(f)
                    yield PlanExecutionCompletedEvent(
                        plan=event.get("plan"),
                        message=event.get("message", ""),
                        summary=event.get("summary", ""),
                        success=event.get("success", True),
                        file_changes=all_file_changes
                    ).to_dict()
                elif event_type == EventType.ERROR.value:
                    yield ErrorEvent(error=event.get("error", "Unknown error")).to_dict()
                else:
                    # 直接透传其他事件（包括 response_start, response_end）
                    yield event
            
            # 发送响应结束事件
            yield ResponseEndEvent().to_dict()
                    
        except Exception as e:
            logging.error(f"chat_stream error: {e}", exc_info=True)
            yield ErrorEvent(error=str(e)).to_dict()
            yield ResponseEndEvent().to_dict()
    
    def execute_file(self, file_path: str, timeout: str = "5min") -> Generator[Dict[str, Any], None, None]:
        """
        执行文件（流式）
        
        Args:
            file_path: 相对于项目的文件路径
            timeout: 超时设置
            
        Yields:
            执行输出事件
        """
        # 解析超时
        timeout_seconds = self._parse_timeout(timeout)
        logging.info(f"[execute_file] Starting: {file_path}, timeout: {timeout_seconds}s")
        
        # 先发送开始事件
        yield FileRunStartedEvent(file=file_path).to_dict()
        
        # 使用 shell_exec 工具执行
        result = self.tool_registry.execute(
            "shell_exec",
            command=f"python {file_path}",
            timeout=timeout_seconds
        )
        
        # 打印调试信息
        logging.info(f"[execute_file] Result: success={result.success}, error={result.error}")
        if result.data:
            logging.info(f"[execute_file] Data keys: {list(result.data.keys())}")
            stdout = result.data.get("stdout", "")
            stderr = result.data.get("stderr", "")
            logging.info(f"[execute_file] stdout length: {len(stdout)}, stderr length: {len(stderr)}")
            if stdout:
                logging.info(f"[execute_file] stdout preview: {stdout[:200]}...")
        
        if result.success:
            if result.data and result.data.get("stdout"):
                yield FileRunStdoutEvent(content=result.data["stdout"]).to_dict()
            if result.data and result.data.get("stderr"):
                yield FileRunStderrEvent(content=result.data["stderr"]).to_dict()
            exit_code = result.data.get("exit_code", 0) if result.data else 0
            logging.info(f"[execute_file] Completed: exit_code={exit_code}")
            yield FileRunExitEvent(
                exit_code=exit_code,
                duration=result.data.get("duration", 0) if result.data else 0
            ).to_dict()
        else:
            logging.info(f"[execute_file] Failed: {result.error}")
            yield FileRunStderrEvent(content=result.error or "Execution failed").to_dict()
            yield FileRunExitEvent(
                exit_code=result.data.get("exit_code", 1) if result.data else 1,
                duration=result.data.get("duration", 0) if result.data else 0
            ).to_dict()
    
    def stop_execution(self) -> bool:
        """停止执行"""
        self._cancel_flag.set()
        return True
    
    def is_executing(self) -> bool:
        """检查是否正在执行"""
        return self._executing
    
    def get_context_summary(self) -> Dict[str, Any]:
        """获取上下文摘要（兼容原 CodeAgent）"""
        files = self.workspace.get_file_list(self.project_id)
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "file_count": len(files) if files else 0,
            "is_executing": self.is_executing(),
            "has_plan": self.current_plan is not None,
            "plan_status": self.current_plan.status.value if self.current_plan else None,
            # 新增：完整上下文信息
            "context": self.context.to_dict() if self.context else None,
        }
    
    # ==================== 核心执行流程 ====================
    
    def run(self, task: str) -> Generator[Dict[str, Any], None, None]:
        """
        执行任务（流式）
        
        LLM 自主决定执行模式：
        - 如果 LLM 调用 create_plan 工具 → Plan 模式（生成计划后逐步执行）
        - 如果 LLM 直接调用其他工具 → Direct 模式（工具调用循环）
        
        Args:
            task: 用户任务描述
            
        Yields:
            事件字典
        """
        self._executing = True
        self._cancel_flag.clear()
        
        try:
            yield StatusEvent(message="正在分析任务...").to_dict()
            
            # ========== 第一次 LLM 调用：让 LLM 决定模式 ==========
            messages = self._build_initial_messages(task)
            tool_definitions = self.tool_registry.get_all_definitions()
            
            response = self.llm.invoke(messages, tools=tool_definitions)
            
            # 解析工具调用
            tool_calls = self.function_handler.parse_tool_calls(response)
            
            # 检查是否调用了 create_plan
            create_plan_call = None
            other_tool_calls = []
            
            for tc in tool_calls:
                if tc["name"] == CREATE_PLAN_TOOL_NAME:
                    create_plan_call = tc
                else:
                    other_tool_calls.append(tc)
            
            if create_plan_call:
                # ========== Plan 模式（多步骤计划）==========
                logging.info(f"Agent: LLM chose Plan mode")
                yield from self._execute_plan_mode(task, create_plan_call, messages, response)
            else:
                # ========== Direct 模式（统一为单步骤 Plan）==========
                logging.info(f"Agent: LLM chose Direct mode (converted to single-step plan)")
                yield from self._execute_direct_as_plan(task, response, messages, tool_calls)
            
        except Exception as e:
            logging.error(f"Agent run error: {e}", exc_info=True)
            yield ErrorEvent(error=str(e)).to_dict()
        finally:
            self._executing = False
    
    def _build_initial_messages(self, task: str) -> List:
        """
        构建首次 LLM 调用的消息（Direct 和 Plan 模式共用）
        
        包含：
        - 系统提示词（从 YAML 加载）
        - 模式选择指导（从 YAML 加载）
        - 上下文摘要（记忆、规范、活跃文件、Repo Map）
        - 对话历史（如果有）
        """
        # 加载系统提示词和模式选择指导（从 YAML）
        prompt_loader = get_code_agent_prompt_loader()
        system_prompt = prompt_loader.get_system_prompt()
        mode_guidance = prompt_loader.get_mode_guidance()
        
        # 构建上下文摘要（不包含代码完整内容，避免首次调用 token 过多）
        context_summary = self._build_context_for_llm(
            include_conversation=False,
            include_code_content=False  # 首次调用不包含完整代码内容
        )
        
        # 组装系统消息
        system_content = system_prompt
        if mode_guidance:
            system_content += f"\n\n{mode_guidance}"
        if context_summary:
            system_content += f"\n\n## 当前上下文\n{context_summary}"
        
        messages = [SystemMessage(content=system_content)]
        
        # 添加对话历史（如果有）
        if self.context.conversation and self.context.conversation.messages:
            # 只添加最近的对话历史，避免 token 过多
            recent_messages = self.context.conversation.get_recent_messages(n=10)
            if recent_messages:
                history = ConversationHistory(messages=recent_messages).to_langchain_messages()
                messages.extend(history)
                logging.info(f"Context: Added {len(recent_messages)} recent conversation messages")
        
        # 添加当前用户消息
        messages.append(HumanMessage(content=task))
        
        return messages
    
    def _execute_plan_mode(self, task: str, create_plan_call: Dict, 
                           messages: List, initial_response) -> Generator[Dict[str, Any], None, None]:
        """执行 Plan 模式"""
        yield ResponseStartEvent(mode="plan").to_dict()
        
        # 从工具调用中提取计划数据
        plan_args = create_plan_call.get("arguments", {})
        analysis = plan_args.get("analysis", "")
        steps_data = plan_args.get("steps", [])
        
        # 构建 Plan 对象
        steps = []
        for i, step_data in enumerate(steps_data):
            steps.append(PlanStep(
                id=i + 1,
                description=step_data.get("description", ""),
                expected_outcome=step_data.get("expected_outcome", ""),
                tools_needed=step_data.get("tools", [])
            ))
        
        plan = Plan(
            task=task,
            steps=steps,
            status=PlanStatus.PLANNING
        )
        
        self.current_plan = plan
        self.tracker.set_plan(plan)
        
        # 持久化保存计划
        self.plan_storage.save_plan(plan)
        
        yield PlanCreatedEvent(
            plan=plan.to_dict(),
            message=f"已生成执行计划，共 {len(plan.steps)} 个步骤\n\n分析: {analysis}"
        ).to_dict()
        
        # 执行计划
        yield from self._execute_plan(plan)
    
    def _execute_direct_as_plan(self, task: str, initial_response, 
                                messages: List, initial_tool_calls: List) -> Generator[Dict[str, Any], None, None]:
        """
        将 Direct 模式转换为单步骤 Plan 并执行
        
        统一执行流程：Direct 模式 = 单步骤 Plan
        """
        yield ResponseStartEvent(mode="direct").to_dict()
        
        # 创建隐式单步骤 Plan
        step = PlanStep(
            id=1,
            description=task,  # 直接用 task 作为步骤描述
            expected_outcome="完成任务",
            status=StepStatus.PENDING
        )
        
        plan = Plan(
            task=task,
            steps=[step],
            status=PlanStatus.PLANNING
        )
        
        self.current_plan = plan
        self.tracker.set_plan(plan)
        
        # Direct 模式不发送 PlanCreatedEvent（因为是隐式的）
        # 直接开始执行
        
        # 执行计划（单步骤）
        yield from self._execute_plan(plan, initial_response=initial_response, 
                                     initial_tool_calls=initial_tool_calls, 
                                     initial_messages=messages)
    
    def cancel_plan_execution(self) -> Dict[str, Any]:
        """取消正在执行的计划"""
        if self.current_plan and self.current_plan.status == PlanStatus.EXECUTING:
            self._cancel_flag.set()
            self.current_plan.status = PlanStatus.CANCELLED
            return {"success": True, "message": "计划执行已取消"}
        return {"success": False, "message": "没有正在执行的计划"}
    
    def _execute_plan(self, plan: Plan, 
                     initial_response=None, 
                     initial_tool_calls: List = None,
                     initial_messages: List = None) -> Generator[Dict[str, Any], None, None]:
        """
        执行计划
        
        Args:
            plan: 执行计划
            initial_response: 初始 LLM 响应（Direct 模式需要）
            initial_tool_calls: 初始工具调用列表（Direct 模式需要）
            initial_messages: 初始消息列表（Direct 模式需要）
        """
        plan.status = PlanStatus.EXECUTING
        
        yield PlanExecutionStartedEvent(
            plan=plan.to_dict(),
            message="开始执行计划"
        ).to_dict()
        
        # 逐步执行
        for step_idx, step in enumerate(plan.steps):
            # 检查取消标志
            if self._cancel_flag.is_set():
                plan.status = PlanStatus.CANCELLED
                yield PlanExecutionCancelledEvent(message="执行已取消").to_dict()
                return
            
            if plan.status == PlanStatus.CANCELLED:
                yield PlanExecutionCancelledEvent(message="执行已取消").to_dict()
                return
            
            # 跳过已完成的步骤
            if step.status in (StepStatus.DONE, StepStatus.SKIPPED):
                continue
            
            # 执行步骤
            # 如果是 Direct 模式（单步骤 Plan）且是第一步，传入初始响应
            is_direct_mode = (len(plan.steps) == 1 and initial_response is not None)
            yield from self._execute_step(
                step, plan,
                initial_response=initial_response if (is_direct_mode and step_idx == 0) else None,
                initial_tool_calls=initial_tool_calls if (is_direct_mode and step_idx == 0) else None,
                initial_messages=initial_messages if (is_direct_mode and step_idx == 0) else None
            )
            
            # 检查是否需要重新规划（仅警告，不中断执行）
            if self.tracker.should_replan():
                yield ReplanWarningEvent(message="检测到执行问题，可能需要关注").to_dict()
                # 重置异常计数，继续执行
                self.tracker.anomaly_count = 0
                # 注意：这里不再 break，继续执行剩余步骤
            
            # 检查步骤是否失败
            if step.status == StepStatus.FAILED:
                plan.status = PlanStatus.FAILED
                yield PlanExecutionFailedEvent(
                    step_id=step.id,
                    error=step.error,
                    message=f"Step {step.id} 执行失败"
                ).to_dict()
                return
        
        # 检查是否全部完成
        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
            # 归档已完成的计划
            self.plan_storage.archive_plan(plan)
            summary = self._generate_summary(plan)
            
            # 判断是否为 Direct 模式（单步骤 Plan）
            is_direct_mode = (len(plan.steps) == 1)
            
            # 记录执行决策到 MemoryContext
            if is_direct_mode:
                # Direct 模式：记录为 Direct 模式完成
                all_file_changes = []
                for step in plan.steps:
                    all_file_changes.extend(step.files_changed)
                if all_file_changes:
                    self.context.memory.add_decision(
                        decision=f"Direct 模式完成: {plan.task[:50]}...",
                        reason=f"修改了文件: {', '.join(all_file_changes[:5])}"
                    )
            else:
                # Plan 模式：记录为计划完成
                self.context.memory.add_decision(
                    decision=f"完成任务: {plan.task}",
                    reason=summary
                )
            
            # 计算文件变更
            all_file_changes = []
            for step in plan.steps:
                all_file_changes.extend(step.files_changed)
            
            # Direct 模式：计算迭代次数（通过 tool_calls 数量估算）
            if is_direct_mode and plan.steps[0].tool_calls:
                iteration_count = len([tc for tc in plan.steps[0].tool_calls if isinstance(tc, dict)])
                direct_summary = f"Direct 模式执行完成，共 {iteration_count} 轮对话"
            else:
                direct_summary = summary
            
            yield PlanExecutionCompletedEvent(
                plan=plan.to_dict(),
                message="所有步骤执行完成" if not is_direct_mode else "任务完成",
                summary=direct_summary if is_direct_mode else summary,
                success=True,
                file_changes=list(set(all_file_changes))
            ).to_dict()
        elif plan.has_failed():
            plan.status = PlanStatus.FAILED
            # 保存失败状态
            self.plan_storage.save_plan(plan)
            
            # 记录失败到 MemoryContext
            self.context.memory.add_decision(
                decision=f"任务失败: {plan.task}",
                reason="部分步骤执行失败"
            )
            
            yield PlanExecutionFailedEvent(
                plan=plan.to_dict(),
                message="部分步骤执行失败"
            ).to_dict()
    
    def _execute_step(self, step: PlanStep, plan: Plan,
                     initial_response=None,
                     initial_tool_calls: List = None,
                     initial_messages: List = None) -> Generator[Dict[str, Any], None, None]:
        """
        执行单个步骤
        
        Args:
            step: 计划步骤
            plan: 执行计划
            initial_response: 初始 LLM 响应（Direct 模式需要）
            initial_tool_calls: 初始工具调用列表（Direct 模式需要）
            initial_messages: 初始消息列表（Direct 模式需要）
        """
        self.tracker.start_step(step.id)
        
        yield StepStartedEvent(
            step_id=step.id,
            description=step.description,
            progress=plan.get_progress()
        ).to_dict()
        
        try:
            # 构建步骤执行消息
            is_direct_mode = (initial_response is not None)
            if is_direct_mode:
                # Direct 模式：使用初始消息（已经包含对话历史）
                messages = initial_messages.copy() if initial_messages else []
            else:
                # Plan 模式：构建步骤消息
                messages = self._build_step_messages(step, plan)
            
            # 工具调用循环
            max_iterations = 15 if is_direct_mode else 10  # Direct 模式允许更多迭代
            iteration = 0
            step_response = ""
            all_tool_calls = []
            all_files_changed = []
            
            # Direct 模式：先处理初始工具调用
            if is_direct_mode and initial_tool_calls:
                current_response = initial_response
                current_tool_calls = initial_tool_calls
                # 过滤掉 create_plan（Direct 模式中不应该调用）
                current_tool_calls = [tc for tc in current_tool_calls if tc["name"] != CREATE_PLAN_TOOL_NAME]
            else:
                current_response = None
                current_tool_calls = None
            
            while iteration < max_iterations:
                # 检查取消标志
                if self._cancel_flag.is_set():
                    step.status = StepStatus.FAILED
                    step.error = "执行被取消"
                    return
                
                iteration += 1
                logging.info(f"Step {step.id} iteration {iteration}")
                
                # 如果是第一次迭代且是 Direct 模式，使用初始响应
                if iteration == 1 and is_direct_mode and current_response is not None:
                    response = current_response
                    response_content = response.content or ""
                else:
                    # 获取可用工具定义
                    tool_definitions = self.tool_registry.get_all_definitions()
                    logging.debug(f"Available tools: {[t['function']['name'] for t in tool_definitions]}")
                    
                    # 调用 LLM（使用 invoke 确保工具调用被正确获取）
                    # 流式模式下工具调用可能无法正确解析，改用非流式调用
                    response = self.llm.invoke(
                        messages,
                        tools=tool_definitions
                    )
                    
                    response_content = response.content or ""
                    current_response = response
                
                # 输出 LLM 响应内容
                if response_content:
                    step_response += response_content + "\n"
                    yield StepOutputEvent(
                        step_id=step.id,
                        content=response_content
                    ).to_dict()
                    logging.info(f"Step {step.id}: LLM response: {response_content[:200]}...")
                
                # 检查是否有工具调用
                if iteration == 1 and is_direct_mode and current_tool_calls is not None:
                    # Direct 模式第一次迭代：使用初始工具调用
                    tool_calls = current_tool_calls
                else:
                    tool_calls = self.function_handler.parse_tool_calls(response)
                    current_tool_calls = tool_calls
                
                if tool_calls:
                    logging.info(f"Step {step.id}: Found {len(tool_calls)} tool calls: {[tc['name'] for tc in tool_calls]}")
                else:
                    logging.info(f"Step {step.id}: No tool calls, step complete")
                
                if not tool_calls:
                    # 没有工具调用，步骤完成
                    break
                
                # Direct 模式：过滤掉 create_plan（不应该在 Direct 模式中调用）
                if is_direct_mode:
                    tool_calls = [tc for tc in tool_calls if tc["name"] != CREATE_PLAN_TOOL_NAME]
                    if not tool_calls:
                        # 如果过滤后没有工具调用，步骤完成
                        break
                
                # 执行工具调用
                yield ToolCallsEvent(
                    step_id=step.id,
                    calls=[{"name": tc["name"], "arguments": tc["arguments"]} for tc in tool_calls]
                ).to_dict()
                
                for tc in tool_calls:
                    logging.info(f"  🔧 Tool: {tc['name']} args: {str(tc['arguments'])[:100]}")
                
                tool_results = self.function_handler.execute_tool_calls(tool_calls)
                all_tool_calls.extend(tool_results)
                
                # 提取变更的文件
                changed_files = self.function_handler.extract_changed_files(tool_results)
                all_files_changed.extend(changed_files)
                
                if changed_files:
                    logging.info(f"  📁 Files changed: {changed_files}")
                
                # 记录 assistant 消息（包含工具调用）
                self.context.conversation.add_assistant_message(
                    content=response_content or "",
                    tool_calls=[{"id": tc["id"], "name": tc["name"], "args": tc["arguments"]} for tc in tool_calls]
                )
                
                # 输出工具结果并更新代码上下文
                for tr in tool_results:
                    result = tr["result"]
                    status = "✅" if result.success else "❌"
                    logging.info(f"  {status} {tr['name']}: success={result.success}, error={result.error}")
                    
                    # 更新代码上下文（活跃文件）
                    self._update_code_context(tr["name"], tr["arguments"], result)
                    
                    # 记录工具结果到对话历史
                    file_path = tr["arguments"].get("path") or tr["arguments"].get("file_path")
                    self.context.conversation.add_tool_result(
                        tool_call_id=tr["tool_call_id"],
                        tool_name=tr["name"],
                        result=result.to_message()[:500],  # 截断，完整内容在 focused_files 中
                        file_path=file_path
                    )
                    
                    yield ToolResultEvent(
                        step_id=step.id,
                        tool=tr["name"],
                        success=result.success,
                        output=result.output[:500] if result.output else "",
                        error=result.error
                    ).to_dict()
                
                # 异常检测（Plan 模式才有，Direct 模式跳过）
                if not is_direct_mode:
                    anomaly = self.tracker.detect_anomaly(step_response, tool_calls)
                    if anomaly:
                        yield AnomalyDetectedEvent(
                            step_id=step.id,
                            anomaly=anomaly
                        ).to_dict()
                        # 添加修正提示
                        correction = self.tracker.get_correction_prompt(anomaly)
                        messages.append(HumanMessage(content=correction))
                
                # 添加工具结果到消息
                # LangChain AIMessage 期望的 tool_calls 格式: {"id": str, "name": str, "args": dict}
                messages.append(AIMessage(
                    content=response_content or "",
                    tool_calls=[{
                        "id": tc["id"],
                        "name": tc["name"],
                        "args": tc["arguments"]
                    } for tc in tool_calls]
                ))
                
                for tr in tool_results:
                    messages.append(ToolMessage(
                        content=tr["result"].to_message(),
                        tool_call_id=tr["tool_call_id"]
                    ))
            
            # 步骤完成
            result = StepResult(
                success=True,
                response=step_response,
                files_changed=list(set(all_files_changed)),
                tool_calls=[{"name": tc["name"], "arguments": tc.get("arguments", {})} for tc in all_tool_calls]
            )
            
            self.tracker.complete_step(step.id, result)
            
            # 持久化更新步骤状态
            self.plan_storage.update_step_status(
                plan.id, step.id, StepStatus.DONE, result
            )
            
            yield StepCompletedEvent(
                step_id=step.id,
                files_changed=result.files_changed,
                progress=plan.get_progress()
            ).to_dict()
            
        except Exception as e:
            logging.error(f"Step {step.id} execution error: {e}", exc_info=True)
            self.tracker.fail_step(step.id, str(e))
            yield StepErrorEvent(
                step_id=step.id,
                error=str(e)
            ).to_dict()
    

    
    def _build_step_messages(self, step: PlanStep, plan: Plan) -> List:
        """
        构建步骤执行消息（Plan 模式）
        
        使用统一的上下文构建方法，与 Direct 模式保持一致。
        """
        prompt_loader = get_code_agent_prompt_loader()
        
        # 1. 基础系统提示词（Plan 模式特有）
        step_execution_prompt = prompt_loader.get_step_execution_prompt()
        
        # 2. 项目上下文（Plan 模式特有）
        project_context_template = prompt_loader.get_project_context()
        project_context = project_context_template.format(
            project_name=self.project_name,
            project_path=self.project_path,
            tools_description=self._format_tools_description()
        )
        
        # 3. 统一的上下文摘要（包含代码完整内容，Plan 模式需要）
        context_summary = self._build_context_for_llm(
            include_conversation=False,  # 对话历史单独添加
            include_code_content=True    # Plan 模式需要完整代码内容
        )
        
        # 组装系统消息
        system_template = prompt_loader.get_step_system_message()
        final_system_content = system_template.format(
            step_execution_prompt=step_execution_prompt,
            project_context=project_context,
            active_files_warning="",  # 已包含在 context_summary 中
            code_context=context_summary if context_summary else ""
        )
        
        messages = [SystemMessage(content=final_system_content)]
        
        # 4. 添加对话历史（统一处理，与 Direct 模式一致）
        if self.context.conversation and self.context.conversation.messages:
            # 只添加最近的对话历史，避免 token 过多
            recent_messages = self.context.conversation.get_recent_messages(n=10)
            if recent_messages:
                history = ConversationHistory(messages=recent_messages).to_langchain_messages()
                messages.extend(history)
                logging.info(f"Context: Added {len(recent_messages)} recent conversation messages to step {step.id}")
        
        # 5. 用户消息（当前步骤）
        user_message_template = prompt_loader.get_step_user_message()
        user_message = user_message_template.format(
            task=plan.task,
            plan_summary=plan.to_summary(),
            step_id=step.id,
            total_steps=len(plan.steps),
            step_description=step.description,
            expected_outcome=step.expected_outcome or "完成该步骤的操作"
        )
        messages.append(HumanMessage(content=user_message))
        
        return messages
    
    
    def _build_context_for_llm(self, include_conversation: bool = False, 
                                include_code_content: bool = True) -> str:
        """
        构建发送给 LLM 的上下文摘要（统一方法，Direct 和 Plan 模式共用）
        
        所有格式化文本都从 YAML 模板加载，代码只负责数据填充。
        
        Args:
            include_conversation: 是否包含对话历史（通常通过 messages 单独添加）
            include_code_content: 是否包含代码文件完整内容（Plan 模式需要，Direct 模式可选）
        
        Returns:
            格式化的上下文字符串
        """
        prompt_loader = get_code_agent_prompt_loader()
        parts = []
        
        # 1. 记忆上下文（历史决策）- 高优先级
        if self.context.memory and self.context.memory.decisions:
            recent_decisions = self.context.memory.decisions[-5:]  # 最近 5 条
            if recent_decisions:
                decisions_list = "\n".join(f"- **{d.decision}**: {d.reason}" for d in recent_decisions)
                template = prompt_loader.get_context_history_decisions()
                parts.append(template.format(decisions_list=decisions_list))
                parts.append("")  # 空行分隔
        
        # 2. 项目规范
        if self.context.memory and self.context.memory.project_conventions:
            recent_conventions = self.context.memory.project_conventions[-5:]  # 最近 5 条
            if recent_conventions:
                conventions_list = "\n".join(f"- {conv}" for conv in recent_conventions)
                template = prompt_loader.get_context_project_conventions()
                parts.append(template.format(conventions_list=conventions_list))
                parts.append("")
        
        # 3. 活跃文件列表（所有模式都需要）
        if self.context.code_context and self.context.code_context.focused_files:
            files = [f.path for f in self.context.code_context.focused_files]
            editing_count = sum(1 for f in self.context.code_context.focused_files if f.is_editing)
            
            # 构建文件列表（只提取数据，不包含提示文本）
            file_list = "\n".join(f"- {path}" for path in files[:15])  # 最多显示 15 个
            
            # 使用 YAML 模板格式化编辑信息和更多文件信息（不硬编码文本）
            editing_info = ""
            if editing_count > 0:
                editing_template = prompt_loader.get_context_editing_info()
                editing_info = editing_template.format(editing_count=editing_count) + "\n"
            
            more_files_info = ""
            if len(files) > 15:
                more_files_template = prompt_loader.get_context_more_files_info()
                more_files_info = more_files_template.format(more_files_count=len(files) - 15)
            
            template = prompt_loader.get_context_active_files()
            parts.append(template.format(
                file_count=len(files),
                editing_info=editing_info,
                file_list=file_list,
                more_files_info=more_files_info
            ))
            parts.append("")
        
        # 4. 符号索引（Repo Map）- 帮助快速了解项目结构
        if (self.context.code_context and 
            self.context.code_context.symbol_index and
            self.context.code_context.symbol_index.file_symbols):
            repo_map = self.context.code_context.symbol_index.to_repo_map_string(max_files=20)
            if repo_map:
                template = prompt_loader.get_context_repo_map()
                parts.append(template.format(repo_map_content=repo_map))
                parts.append("")
        
        # 5. 代码文件完整内容（Plan 模式需要，Direct 模式可选）
        if include_code_content and self.context.code_context:
            active_files_context = self.context.code_context.to_context_string()
            if active_files_context:
                template = prompt_loader.get_context_file_content()
                parts.append(template.format(file_content=active_files_context))
                logging.info(f"Context: Including {len(self.context.code_context.focused_files)} active files content")
        
        return "\n".join(parts) if parts else ""
    
    def _format_tools_description(self) -> str:
        """格式化工具描述"""
        tools = self.tool_registry.list_tools()
        return "\n".join(f"- {t}" for t in tools)
    
    def _generate_summary(self, plan: Plan) -> str:
        """生成执行总结"""
        completed = [s for s in plan.steps if s.status == StepStatus.DONE]
        files_changed = set()
        for s in completed:
            files_changed.update(s.files_changed)
        
        summary_parts = [
            f"任务: {plan.task}",
            f"完成步骤: {len(completed)}/{len(plan.steps)}",
        ]
        
        if files_changed:
            summary_parts.append(f"修改文件: {', '.join(files_changed)}")
        
        return "\n".join(summary_parts)
    
    def _parse_timeout(self, timeout: str) -> int:
        """解析超时字符串"""
        timeout = timeout.lower().strip()
        if timeout.endswith("min"):
            return int(timeout[:-3]) * 60
        elif timeout.endswith("s"):
            return int(timeout[:-1])
        elif timeout.endswith("h"):
            return int(timeout[:-1]) * 3600
        else:
            return int(timeout)
