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
        self._current_task: Optional[str] = None  # 当前任务（用于创建 Plan）
        
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
    
    def reset(self):
        """重置执行状态"""
        self._cancel_flag.clear()
    
    # ==================== 核心执行流程 ====================
    
    def run(self, task: str) -> Generator[Dict[str, Any], None, None]:
        """执行任务 (Unified Architecture)"""
        self.reset()
        self._executing = True
        self._current_task = task  # 保存任务信息，用于创建 Plan
        
        try:
            # 1. 初始化对话历史
            self.context.conversation.add_user_message(task)
            
            # 2. 进入统一执行循环
            yield from self._execute_loop()
            
        except Exception as e:
            logging.error(f"Agent run error: {e}", exc_info=True)
            yield ErrorEvent(error=str(e)).to_dict()
        finally:
            self._executing = False
    
    def _execute_loop(self) -> Generator[Dict[str, Any], None, None]:
        """
        统一执行循环 (Unified Loop)
        
        处理 Direct 和 Plan 两种模式，支持动态切换。
        """
        iteration = 0
        max_iterations = 50
        
        last_plan_id = None
        last_step_id = None
        
        yield ResponseStartEvent(mode="unified").to_dict()
        
        while iteration < max_iterations and self._executing:
            iteration += 1
            
            # --- 1. 状态监测与事件触发 ---
            
            # 检测 Plan 变更 (Direct -> Plan)
            if self.current_plan and self.current_plan.id != last_plan_id:
                yield PlanExecutionStartedEvent(plan=self.current_plan.to_dict()).to_dict()
                last_plan_id = self.current_plan.id
                
            # 检测 Step 变更
            current_step = self.current_plan.get_current_step() if self.current_plan else None
            current_step_id = current_step.id if current_step else None
            
            if current_step_id != last_step_id:
                if current_step:
                    self.tracker.start_step(current_step.id)
                    yield StepStartedEvent(
                        step_id=current_step.id,
                        description=current_step.description
                    ).to_dict()
                last_step_id = current_step_id
                
            # --- 2. 构建消息 ---
            
            system_msg = self._build_dynamic_system_message()
            messages = [SystemMessage(content=system_msg)]
            messages.extend(self.context.conversation.to_langchain_messages())
            
            # --- 3. 调用 LLM ---
            
            tool_definitions = self.tool_registry.get_all_definitions()
            response = self.llm.invoke(messages, tools=tool_definitions)
            
            response_content = response.content or ""
            step_id = current_step.id if current_step else 0
            
            if response_content:
                yield StepOutputEvent(step_id=step_id, content=response_content).to_dict()
            
            # --- 4. 处理工具调用 ---
            
            tool_calls = self.function_handler.parse_tool_calls(response)
        
            # 记录 Assistant 消息
            self.context.conversation.add_assistant_message(
                content=response_content,
                tool_calls=[{"id": tc["id"], "name": tc["name"], "args": tc["arguments"]} for tc in tool_calls] if tool_calls else None
            )
            
            if tool_calls:
                # 记录事件
                yield ToolCallsEvent(
                    step_id=step_id,
                    calls=[{"name": tc["name"], "arguments": tc["arguments"]} for tc in tool_calls]
                ).to_dict()
                
                # 执行工具
                tool_results = self.function_handler.execute_tool_calls(tool_calls)
            
                # 处理结果（统一处理，包括 create_plan）
                yield from self._handle_tool_results(tool_results, step_id)
            else:
                # --- 5. 无工具调用 (结束或推进) ---
                if self._is_done(response_content):
                    break
                
                # Plan Mode: 无工具调用时，完成当前步骤并推进
                if self.current_plan and current_step:
                    # 收集当前步骤的文件变更（已在工具调用时记录到 step.files_changed）
                    step_files_changed = current_step.files_changed.copy() if current_step.files_changed else []
                    
                    # 完成当前步骤
                    self.current_plan.complete_step(
                        current_step.id,
                        result=response_content,
                        files_changed=step_files_changed
                    )
                    yield StepCompletedEvent(
                        step_id=current_step.id,
                        files_changed=current_step.files_changed,
                        progress=self.current_plan.get_progress()
                    ).to_dict()
                    
                    # 检查计划是否完成
                    if self.current_plan.is_complete():
                        self.current_plan.status = PlanStatus.COMPLETED
                        self.plan_storage.archive_plan(self.current_plan)
                        summary = self._generate_summary(self.current_plan)
                        
                        # 记录决策
                        self.context.memory.add_decision(
                            decision=f"完成任务: {self.current_plan.task}",
                            reason=summary
                        )
                        
                        yield PlanExecutionCompletedEvent(
                            plan=self.current_plan.to_dict(),
                            message="所有步骤执行完成",
                            summary=summary,
                            success=True,
                            file_changes=list(set([f for step in self.current_plan.steps for f in step.files_changed]))
                        ).to_dict()
                        break
                    
                    # 推进到下一步
                    if self.current_plan.advance_to_next_step():
                        # 还有下一步，继续循环
                        logging.info(f"Plan: Advanced to step {self.current_plan.current_step_id}")
                        continue
                    else:
                        # 没有下一步了，但步骤状态可能不一致，检查一下
                        if self.current_plan.is_complete():
                            # 所有步骤已完成
                            self.current_plan.status = PlanStatus.COMPLETED
                            yield PlanExecutionCompletedEvent(
                                plan=self.current_plan.to_dict(),
                                message="所有步骤执行完成",
                                summary=self._generate_summary(self.current_plan),
                                success=True,
                                file_changes=list(set([f for step in self.current_plan.steps for f in step.files_changed]))
                            ).to_dict()
                        break
                else:
                    # Direct Mode: 无工具调用且无计划 = 任务完成
                    break

    def _build_dynamic_system_message(self) -> str:
        """
        构建动态系统提示词
        根据当前状态（是否有 Plan，处于哪一步）动态组装 System Prompt。
        """
        prompt_loader = get_code_agent_prompt_loader()
        parts = []
        
        # 1. 基础系统提示词（根据模式选择）
        if self.current_plan and self.current_plan.status == PlanStatus.EXECUTING:
            # Plan 模式：使用步骤执行提示词
            parts.append(prompt_loader.get_step_execution_prompt())
        else:
            # Direct 模式：使用通用系统提示词
            parts.append(prompt_loader.get_system_prompt())
        
        # 2. 项目上下文
        project_context_template = prompt_loader.get_project_context()
        if project_context_template:
            parts.append(project_context_template.format(
                project_name=self.project_name,
                project_path=self.project_path,
                tools_description=self._format_tools_description()
            ))
                
        # 3. 计划状态与当前步骤 (Plan Mode)
        if self.current_plan and self.current_plan.status == PlanStatus.EXECUTING:
            current_step = self.current_plan.get_current_step()
            if current_step:
                # 3a. 计划概览
                plan_summary = self.current_plan.to_summary()
                plan_status_template = prompt_loader.get_plan_status_template()
                if plan_status_template:
                    parts.append(plan_status_template.format(
                        current_step_id=current_step.id,
                        total_steps=len(self.current_plan.steps),
                        plan_summary=plan_summary
                    ))
                
                # 3b. 当前步骤专注指令
                step_context_template = prompt_loader.get_current_step_context_template()
                if step_context_template:
                    parts.append(step_context_template.format(
                        current_step_id=current_step.id,
                        step_description=current_step.description,
                        expected_outcome=current_step.expected_outcome or "完成此步骤"
                    ))
        
        # 4. 动态上下文摘要 (Always)
        context_summary = self._build_context_for_llm(
            include_conversation=False,
            include_code_content=True
        )
        if context_summary:
            parts.append(f"## 当前上下文\n{context_summary}")
            
        # 5. 模式指导 (Direct Mode Only)
        if not self.current_plan:
            mode_guidance = prompt_loader.get_mode_guidance()
            if mode_guidance:
                parts.append(mode_guidance)
                
        return "\n\n".join(parts)
    
    def _handle_tool_results(self, tool_results: List[Dict], step_id: int) -> Generator[Dict[str, Any], None, None]:
        """
        统一处理工具执行结果
        
        包括：
        1. create_plan 工具：创建 Plan 并设置状态
        2. 其他工具：更新上下文、记录历史
        """
        for tr in tool_results:
            result = tr["result"]
            tool_name = tr["name"]
            
            # 特殊处理：create_plan 工具（Direct -> Plan 转换）
            if tool_name == CREATE_PLAN_TOOL_NAME and result.success:
                yield from self._handle_create_plan(tr, result)
            else:
                # 普通工具处理
                yield from self._handle_regular_tool(tr, result, step_id)
    
    def _handle_create_plan(self, tool_result: Dict, result: Any) -> Generator[Dict[str, Any], None, None]:
        """
        处理 create_plan 工具调用
        
        从 Direct 模式转换到 Plan 模式
        """
        plan_data = result.data.get("plan") if result.data else None
        if not plan_data:
            logging.warning("CreatePlanTool returned no plan data")
            return
        
        # 构建 Plan 对象
        steps = []
        for i, step_data in enumerate(plan_data.get("steps", [])):
            steps.append(PlanStep(
                id=i + 1,
                description=step_data.get("description", ""),
                expected_outcome=step_data.get("expected_outcome", ""),
                tools_needed=step_data.get("tools", []),
                status=StepStatus.PENDING
            ))
        
        plan = Plan(
            task=self._current_task or plan_data.get("analysis", "执行任务"),
            steps=steps,
            status=PlanStatus.PLANNING
        )
        
        # 设置 Plan 状态（关键：触发模式切换）
        self.current_plan = plan
        self.tracker.set_plan(plan)
        plan.status = PlanStatus.EXECUTING  # 立即进入执行状态
        
        # 持久化保存计划
        self.plan_storage.save_plan(plan)
        
        # 发送 PlanCreatedEvent
        analysis = plan_data.get("analysis", "")
        yield PlanCreatedEvent(
            plan=plan.to_dict(),
            message=f"已生成执行计划，共 {len(plan.steps)} 个步骤\n\n分析: {analysis}"
        ).to_dict()
        
        # 记录工具结果到对话历史
        self.context.conversation.add_tool_result(
            tool_call_id=tool_result["tool_call_id"],
            tool_name=CREATE_PLAN_TOOL_NAME,
            result=result.to_message(),
            file_path=None
        )
        
        # 发送工具结果事件
        yield ToolResultEvent(
            step_id=0,
            tool=CREATE_PLAN_TOOL_NAME,
            success=result.success,
            output=result.output[:500] if result.output else "",
            error=result.error
        ).to_dict()
        
        logging.info(f"Agent: Transitioned from Direct to Plan mode (plan_id={plan.id})")
    
    def _handle_regular_tool(self, tool_result: Dict, result: Any, step_id: int) -> Generator[Dict[str, Any], None, None]:
        """
        处理普通工具调用
        
        更新代码上下文、记录对话历史、发送事件
        """
        tool_name = tool_result["name"]
        tool_args = tool_result["arguments"]
        
        # 更新代码上下文
        self._update_code_context(tool_name, tool_args, result)
            
        # 记录到对话历史
        file_path = tool_args.get("path") or tool_args.get("file_path")
        self.context.conversation.add_tool_result(
            tool_call_id=tool_result["tool_call_id"],
            tool_name=tool_name,
            result=result.to_message()[:500],  # 截断，完整内容在 focused_files 中
            file_path=file_path
        )
        
        # 发送工具结果事件
        yield ToolResultEvent(
            step_id=step_id,
            tool=tool_name,
            success=result.success,
            output=result.output[:500] if result.output else "",
            error=result.error
        ).to_dict()
        
        # 如果是文件操作工具，发送文件变更事件
        if tool_name in ("write_file", "patch_file", "delete_file") and result.success:
            changed_path = tool_args.get("path") or tool_args.get("file_path")
            if changed_path:
                yield FileChangeEvent(path=changed_path).to_dict()
        
                # 如果是 Plan 模式，记录文件变更到当前步骤
                if self.current_plan:
                    current_step = self.current_plan.get_current_step()
                    if current_step and changed_path not in current_step.files_changed:
                        current_step.files_changed.append(changed_path)
    
    def _is_done(self, response_content: str = "") -> bool:
        """
        判断任务是否完成
        
        Args:
            response_content: LLM 响应内容（可用于判断是否明确表示完成）
        
        Returns:
            True 如果任务应该结束
        """
        # 检查取消标志
        if self._cancel_flag.is_set():
            if self.current_plan:
                self.current_plan.status = PlanStatus.CANCELLED
            return True
        
        # Plan 模式：检查是否失败
        if self.current_plan:
            if self.current_plan.has_failed():
                return True
            # Plan 完成检查在无工具调用时处理
            return False
        
        # Direct 模式：无工具调用 = 完成（在调用处判断）
        return False
    
    def cancel_execution(self) -> Dict[str, Any]:
        """取消正在执行的任务"""
        if self.current_plan and self.current_plan.status == PlanStatus.EXECUTING:
            self._cancel_flag.set()
            self.current_plan.status = PlanStatus.CANCELLED
            return {"success": True, "message": "执行已取消"}
        return {"success": False, "message": "没有正在执行的任务"}
    
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
    
