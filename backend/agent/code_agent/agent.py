"""
Plan-Execute Agent 主循环
核心 Agent 实现，负责任务规划和执行

这是 Code Agent 的唯一入口，所有文件变更必须通过工具调用完成。
"""

import os
import json
import logging
import threading
from typing import Dict, Any, List, Optional, Generator, Set
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from .plan import Plan, PlanStep, PlanStatus, StepStatus, StepResult, PlanTracker, Planner, PlanStorage
from .tools import create_tool_registry, ToolRegistry, FunctionCallHandler
from .workspace_manager import WorkspaceManager
from .context import CodeContext
from .prompts.prompt_loader import get_code_agent_prompt_loader
from utils.llm_config import resolve_llm_config


class PlanExecuteAgent:
    """
    Plan-Execute Agent
    
    这是 Code Agent 的统一入口，核心流程：
    1. PLAN: 生成执行计划
    2. APPROVE: 用户审批计划（可选）
    3. EXECUTE: 逐步执行（所有操作通过工具调用）
    4. VERIFY: 验证结果
    
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
        
        # 会话状态
        self.conversation_history: List[Dict] = []
        self.current_plan: Optional[Plan] = None
        self.auto_approve: bool = False
        
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
        
        这是一个便捷方法，等同于 run(task, auto_approve=True)
        
        Args:
            user_input: 用户输入
            
        Yields:
            事件字典:
            - {"type": "token", "content": "..."}
            - {"type": "plan_created", "plan": {...}}
            - {"type": "step_started", "step_id": 1, ...}
            - {"type": "tool_result", ...}
            - {"type": "file_change", "path": "..."}
            - {"type": "done", "file_changes": [...]}
            - {"type": "error", "message": "..."}
        """
        self._cancel_flag.clear()
        all_file_changes = []
        
        try:
            for event in self.run(user_input, auto_approve=True):
                event_type = event.get("type")
                
                # 直接透传大部分事件，前端会处理
                if event_type == "step_completed":
                    files = event.get("files_changed", [])
                    for f in files:
                        if f not in all_file_changes:
                            all_file_changes.append(f)
                            yield {"type": "file_change", "path": f}
                    yield event
                elif event_type == "execution_completed":
                    # 添加汇总的文件变更
                    yield {
                        "type": "plan_completed",
                        "file_changes": all_file_changes,
                        "success": True,
                        "summary": event.get("summary", "")
                    }
                elif event_type == "error":
                    yield {"type": "error", "message": event.get("error", "Unknown error")}
                else:
                    # 直接透传其他事件
                    yield event
                    
        except Exception as e:
            logging.error(f"chat_stream error: {e}", exc_info=True)
            yield {"type": "error", "message": str(e)}
    
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
        yield {"type": "started", "file": file_path}
        
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
                # 前端期望 content 字段
                yield {"type": "stdout", "content": result.data["stdout"]}
            if result.data and result.data.get("stderr"):
                yield {"type": "stderr", "content": result.data["stderr"]}
            # 前端期望 exit 事件
            exit_code = result.data.get("exit_code", 0) if result.data else 0
            logging.info(f"[execute_file] Completed: exit_code={exit_code}")
            yield {
                "type": "exit",
                "exit_code": exit_code,
                "duration": result.data.get("duration", 0) if result.data else 0
            }
        else:
            logging.info(f"[execute_file] Failed: {result.error}")
            yield {"type": "stderr", "content": result.error or "Execution failed"}
            yield {
                "type": "exit",
                "exit_code": result.data.get("exit_code", 1) if result.data else 1,
                "duration": result.data.get("duration", 0) if result.data else 0
            }
    
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
        }
    
    # ==================== 核心执行流程 ====================
    
    def run(self, task: str, auto_approve: bool = False) -> Generator[Dict[str, Any], None, None]:
        """
        执行任务（流式）
        
        Args:
            task: 用户任务描述
            auto_approve: 是否自动审批计划
            
        Yields:
            事件字典
        """
        self.auto_approve = auto_approve
        self._executing = True
        self._cancel_flag.clear()
        
        try:
            # ========== Phase 1: 生成计划 ==========
            yield {"type": "status", "message": "正在分析任务并生成计划..."}
            
            context = self._build_project_context()
            plan = self.planner.create_plan_sync(task, context)
            self.current_plan = plan
            self.tracker.set_plan(plan)
            
            # 持久化保存计划
            self.plan_storage.save_plan(plan)
            
            yield {
                "type": "plan_created",
                "plan": plan.to_dict(),
                "message": f"已生成执行计划，共 {len(plan.steps)} 个步骤"
            }
            
            # ========== Phase 2: 等待审批 ==========
            if not auto_approve:
                plan.status = PlanStatus.AWAITING_APPROVAL
                yield {
                    "type": "awaiting_approval",
                    "plan": plan.to_dict(),
                    "message": "请审批执行计划"
                }
                return  # 等待用户调用 approve_plan 或 reject_plan
            
            # 自动审批模式，继续执行
            yield from self._execute_plan(plan)
            
        except Exception as e:
            logging.error(f"Agent run error: {e}", exc_info=True)
            yield {"type": "error", "error": str(e)}
        finally:
            self._executing = False
    
    def approve_plan(self, modified_plan: Dict = None) -> Generator[Dict[str, Any], None, None]:
        """
        审批计划并开始执行
        
        Args:
            modified_plan: 用户修改后的计划（可选）
        """
        if not self.current_plan:
            yield {"type": "error", "error": "没有待审批的计划"}
            return
        
        if self.current_plan.status != PlanStatus.AWAITING_APPROVAL:
            yield {"type": "error", "error": f"计划状态错误: {self.current_plan.status.value}"}
            return
        
        # 如果用户修改了计划
        if modified_plan:
            try:
                self.current_plan = Plan.from_dict(modified_plan)
                self.tracker.set_plan(self.current_plan)
                yield {"type": "plan_modified", "plan": self.current_plan.to_dict()}
            except Exception as e:
                yield {"type": "error", "error": f"计划格式错误: {e}"}
                return
        
        self._executing = True
        try:
            yield {"type": "plan_approved", "message": "计划已审批，开始执行"}
            yield from self._execute_plan(self.current_plan)
        finally:
            self._executing = False
    
    def reject_plan(self, reason: str = "") -> Generator[Dict[str, Any], None, None]:
        """拒绝计划"""
        if not self.current_plan:
            yield {"type": "error", "error": "没有待审批的计划"}
            return
        
        self.current_plan.status = PlanStatus.CANCELLED
        yield {
            "type": "plan_rejected",
            "reason": reason,
            "message": "计划已取消"
        }
        self.current_plan = None
    
    def cancel_execution(self) -> Dict[str, Any]:
        """取消正在执行的任务"""
        if self.current_plan and self.current_plan.status == PlanStatus.EXECUTING:
            self._cancel_flag.set()
            self.current_plan.status = PlanStatus.CANCELLED
            return {"success": True, "message": "执行已取消"}
        return {"success": False, "message": "没有正在执行的任务"}
    
    def _execute_plan(self, plan: Plan) -> Generator[Dict[str, Any], None, None]:
        """执行计划"""
        plan.status = PlanStatus.EXECUTING
        
        yield {
            "type": "execution_started",
            "plan": plan.to_dict(),
            "message": "开始执行计划"
        }
        
        # 设置当前计划允许的工具
        allowed_tools = self._get_plan_allowed_tools(plan)
        self.function_handler.set_allowed_tools(allowed_tools)
        
        # 逐步执行
        for step in plan.steps:
            # 检查取消标志
            if self._cancel_flag.is_set():
                plan.status = PlanStatus.CANCELLED
                yield {"type": "execution_cancelled", "message": "执行已取消"}
                return
            
            if plan.status == PlanStatus.CANCELLED:
                yield {"type": "execution_cancelled", "message": "执行已取消"}
                return
            
            # 跳过已完成的步骤
            if step.status in (StepStatus.DONE, StepStatus.SKIPPED):
                continue
            
            # 设置当前步骤允许的工具
            step_tools = self._get_step_allowed_tools(step, plan)
            self.function_handler.set_allowed_tools(step_tools)
            
            # 执行步骤
            yield from self._execute_step(step, plan)
            
            # 检查是否需要重新规划（仅警告，不中断执行）
            if self.tracker.should_replan():
                yield {"type": "replan_warning", "message": "检测到执行问题，可能需要关注"}
                # 重置异常计数，继续执行
                self.tracker.anomaly_count = 0
                # 注意：这里不再 break，继续执行剩余步骤
            
            # 检查步骤是否失败
            if step.status == StepStatus.FAILED:
                plan.status = PlanStatus.FAILED
                yield {
                    "type": "execution_failed",
                    "step_id": step.id,
                    "error": step.error,
                    "message": f"Step {step.id} 执行失败"
                }
                return
        
        # 检查是否全部完成
        if plan.is_complete():
            plan.status = PlanStatus.COMPLETED
            # 归档已完成的计划
            self.plan_storage.archive_plan(plan)
            yield {
                "type": "execution_completed",
                "plan": plan.to_dict(),
                "message": "所有步骤执行完成",
                "summary": self._generate_summary(plan)
            }
        elif plan.has_failed():
            plan.status = PlanStatus.FAILED
            # 保存失败状态
            self.plan_storage.save_plan(plan)
            yield {
                "type": "execution_failed",
                "plan": plan.to_dict(),
                "message": "部分步骤执行失败"
            }
    
    def _execute_step(self, step: PlanStep, plan: Plan) -> Generator[Dict[str, Any], None, None]:
        """执行单个步骤"""
        self.tracker.start_step(step.id)
        
        yield {
            "type": "step_started",
            "step_id": step.id,
            "description": step.description,
            "progress": plan.get_progress()
        }
        
        try:
            # 构建步骤执行消息
            messages = self._build_step_messages(step, plan)
            
            # 工具调用循环
            max_iterations = 10
            iteration = 0
            step_response = ""
            all_tool_calls = []
            all_files_changed = []
            
            while iteration < max_iterations:
                # 检查取消标志
                if self._cancel_flag.is_set():
                    step.status = StepStatus.FAILED
                    step.error = "执行被取消"
                    return
                
                iteration += 1
                logging.info(f"Step {step.id} iteration {iteration}")
                
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
                
                # 输出 LLM 响应内容
                if response_content:
                    step_response += response_content + "\n"
                    yield {
                        "type": "step_output",
                        "step_id": step.id,
                        "content": response_content
                    }
                    logging.info(f"Step {step.id}: LLM response: {response_content[:200]}...")
                
                # 检查是否有工具调用
                tool_calls = self.function_handler.parse_tool_calls(response)
                
                if tool_calls:
                    logging.info(f"Step {step.id}: Found {len(tool_calls)} tool calls: {[tc['name'] for tc in tool_calls]}")
                else:
                    logging.info(f"Step {step.id}: No tool calls, step complete")
                
                if not tool_calls:
                    # 没有工具调用，步骤完成
                    break
                
                # 执行工具调用
                yield {
                    "type": "tool_calls",
                    "step_id": step.id,
                    "calls": [{"name": tc["name"], "arguments": tc["arguments"]} for tc in tool_calls]
                }
                
                for tc in tool_calls:
                    logging.info(f"  🔧 Tool: {tc['name']} args: {str(tc['arguments'])[:100]}")
                
                tool_results = self.function_handler.execute_tool_calls(tool_calls)
                all_tool_calls.extend(tool_results)
                
                # 提取变更的文件
                changed_files = self.function_handler.extract_changed_files(tool_results)
                all_files_changed.extend(changed_files)
                
                if changed_files:
                    logging.info(f"  📁 Files changed: {changed_files}")
                
                # 输出工具结果并更新代码上下文
                for tr in tool_results:
                    result = tr["result"]
                    status = "✅" if result.success else "❌"
                    logging.info(f"  {status} {tr['name']}: success={result.success}, error={result.error}")
                    
                    # 更新代码上下文（活跃文件）
                    self._update_code_context(tr["name"], tr["arguments"], result)
                    
                    yield {
                        "type": "tool_result",
                        "step_id": step.id,
                        "tool": tr["name"],
                        "success": result.success,
                        "output": result.output[:500] if result.output else "",
                        "error": result.error
                    }
                
                # 异常检测
                anomaly = self.tracker.detect_anomaly(step_response, tool_calls)
                if anomaly:
                    yield {
                        "type": "anomaly_detected",
                        "step_id": step.id,
                        "anomaly": anomaly
                    }
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
            
            yield {
                "type": "step_completed",
                "step_id": step.id,
                "files_changed": result.files_changed,
                "progress": plan.get_progress()
            }
            
        except Exception as e:
            logging.error(f"Step {step.id} execution error: {e}", exc_info=True)
            self.tracker.fail_step(step.id, str(e))
            yield {
                "type": "step_error",
                "step_id": step.id,
                "error": str(e)
            }
    
    def _get_plan_allowed_tools(self, plan: Plan) -> Set[str]:
        """获取计划级别允许的工具"""
        # 基础工具总是允许
        allowed = {
            "read_file", "list_directory", "grep", "get_file_outline",
            "semantic_search",  # RAG 搜索
        }
        
        # 根据计划类型添加工具
        # 需要创建/写入文件的关键词
        write_keywords = ["创建", "写入", "生成", "实现", "添加", "新增", "编写", "构建"]
        if any(any(kw in s.description for kw in write_keywords) for s in plan.steps):
            allowed.add("write_file")
            allowed.add("patch_file")
        
        # 需要修改文件的关键词
        modify_keywords = ["修改", "更新", "编辑", "调整", "优化", "重构", "整合"]
        if any(any(kw in s.description for kw in modify_keywords) for s in plan.steps):
            allowed.add("write_file")
            allowed.add("patch_file")
        
        if any("删除" in s.description for s in plan.steps):
            allowed.add("delete_file")
        
        # 需要执行命令的关键词
        exec_keywords = ["执行", "运行", "测试", "安装", "验证"]
        if any(any(kw in s.description for kw in exec_keywords) for s in plan.steps):
            allowed.add("shell_exec")
        
        if any("备份" in s.description or "版本" in s.description for s in plan.steps):
            allowed.update(["create_backup", "list_versions", "restore_version"])
        
        return allowed
    
    def _get_step_allowed_tools(self, step: PlanStep, plan: Plan) -> Set[str]:
        """获取步骤级别允许的工具"""
        # 从计划级别开始
        allowed = self._get_plan_allowed_tools(plan)
        
        desc = step.description.lower()
        
        # 判断是否为明确的只读步骤（仅包含只读动词，不包含写入动词）
        readonly_verbs = ["查看", "读取", "检查", "分析", "了解", "确认"]
        write_verbs = ["创建", "写入", "生成", "实现", "添加", "编写", "修改", "更新"]
        
        is_readonly = any(v in desc for v in readonly_verbs)
        has_write = any(v in desc for v in write_verbs)
        
        # 只有纯只读步骤才移除写权限
        if is_readonly and not has_write:
            allowed.discard("write_file")
            allowed.discard("patch_file")
            allowed.discard("delete_file")
        
        return allowed
    
    def _build_step_messages(self, step: PlanStep, plan: Plan) -> List:
        """构建步骤执行消息"""
        # 从配置加载系统提示词
        prompt_loader = get_code_agent_prompt_loader()
        step_execution_prompt = prompt_loader.get_step_execution_prompt()
        
        # 系统消息
        system_content = step_execution_prompt + f"""

## 项目信息
- 项目名称: {self.project_name}
- 项目路径: {self.project_path}

## 可用工具
{self._format_tools_description()}

## 当前步骤允许的工具
{', '.join(self.function_handler.allowed_tools or ['全部'])}
"""
        
        # 步骤提示
        step_prompt = self.tracker.get_step_prompt(step)
        
        # 添加活跃文件警告（放在步骤提示之后、代码内容之前）
        if self.code_context.focused_files:
            active_files = [f.path for f in self.code_context.focused_files]
            step_prompt += f"""

## ⚠️ 活跃文件约束（重要！）
以下 {len(active_files)} 个文件内容已加载到下方上下文中，**不要再调用 read_file 读取它们**：
{chr(10).join(f'- {path}' for path in active_files)}

只有当文件不在此列表中时，才需要调用 read_file。
"""
        
        # 添加代码上下文（文件内容）
        code_context = self._get_relevant_context(step)
        if code_context:
            step_prompt += f"\n\n## 相关代码上下文\n{code_context}"
        
        return [
            SystemMessage(content=system_content),
            HumanMessage(content=step_prompt)
        ]
    
    def _build_project_context(self) -> str:
        """构建项目上下文"""
        context_parts = []
        
        # 文件列表
        files = self.workspace.get_file_list(self.project_id)
        if files:
            context_parts.append(f"项目文件:\n" + "\n".join(f"- {f}" for f in files[:20]))
            if len(files) > 20:
                context_parts.append(f"... 等 {len(files)} 个文件")
        else:
            context_parts.append("项目文件: (空项目)")
        
        return "\n\n".join(context_parts)
    
    def _get_relevant_context(self, step: PlanStep) -> str:
        """
        获取与步骤相关的代码上下文
        
        优先级：
        1. 活跃文件（已读取/修改过的文件，避免重复 read_file）
        2. RAG 语义搜索
        3. 回退：读取最近的文件
        """
        context_parts = []
        
        # 1. 首先添加活跃文件内容（LLM 已经交互过的文件）
        active_files_context = self.code_context.to_context_string()
        if active_files_context:
            context_parts.append(active_files_context)
            logging.info(f"Context: Using {len(self.code_context.focused_files)} active files")
            # 如果已有足够的活跃文件，可能不需要额外搜索
            if len(self.code_context.focused_files) >= 3:
                return "\n\n".join(context_parts)
        
        # 2. 尝试使用 RAG 语义搜索获取额外相关文件
        semantic_tool = self.tool_registry.get("semantic_search")
        if semantic_tool:
            try:
                # 使用步骤描述作为查询
                result = semantic_tool.execute(
                    query=step.description,
                    top_k=3
                )
                if result.success and result.data and result.data.get("count", 0) > 0:
                    context_parts.append(f"## 语义搜索相关代码\n{result.output}")
                    return "\n\n".join(context_parts)
            except Exception as e:
                logging.warning(f"Semantic search failed, falling back: {e}")
        
        # 3. 回退：如果没有活跃文件，读取项目文件
        if not active_files_context:
            files = self.workspace.get_file_list(self.project_id)
            for f in files[:3]:  # 最多3个文件
                if f.endswith('.py'):
                    content = self.workspace.read_file(self.project_id, f)
                    if content and len(content) < 2000:
                        context_parts.append(f"### {f}\n```python\n{content}\n```")
        
        return "\n\n".join(context_parts) if context_parts else ""
    
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
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "has_plan": self.current_plan is not None,
            "plan_status": self.current_plan.status.value if self.current_plan else None,
            "progress": self.current_plan.get_progress() if self.current_plan else None,
            "tracker_summary": self.tracker.get_progress_summary(),
            "is_executing": self._executing,
        }
