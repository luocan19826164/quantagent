"""
代码 Agent 主类
负责与 LLM 交互，生成和修改代码
"""

import os
import re
import json
import logging
from typing import Dict, Any, List, Optional, Generator
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from .context import (
    CodeAgentContext, CodeContext, TaskInfo, PlanInfo, PlanStep,
    ExecutionContext, MemoryContext, EnvironmentInfo, SafetyConfig,
    FileInfo, SymbolIndex, DEFAULT_TOOLS, OutputRecord
)
from .workspace_manager import WorkspaceManager
from .executor import executor, ExecutionResult
from utils.llm_config import resolve_llm_config


class CodeAgent:
    """代码 Agent"""
    
    def __init__(self, user_id: int, project_id: str):
        """
        初始化代码 Agent
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
        """
        self.user_id = user_id
        self.project_id = project_id
        
        # 工作区管理器
        self.workspace = WorkspaceManager(user_id)
        
        # 验证项目存在
        project = self.workspace.get_project(project_id)
        if not project:
            raise ValueError(f"Project not found: {project_id}")
        
        self.project_name = project["name"]
        self.project_path = self.workspace.get_project_path(project_id)
        
        # 对话记忆
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output"
        )
        
        # 初始化 LLM
        llm_config = resolve_llm_config("[CodeAgent]")
        
        llm_kwargs = {
            "model": llm_config["model"],
            "temperature": 0.2,  # 代码生成用较低温度
            "api_key": llm_config["api_key"],
            "base_url": llm_config["base_url"],
            "streaming": True,
        }
        if llm_config["extra_headers"]:
            llm_kwargs["default_headers"] = llm_config["extra_headers"]
        
        self.llm = ChatOpenAI(**llm_kwargs)
        
        # 上下文
        self.context = self._build_initial_context()
        
        # 执行历史
        self.execution_history: List[OutputRecord] = []
        
        logging.info(f"CodeAgent initialized for user {user_id}, project {project_id}")
    
    def _build_initial_context(self) -> CodeAgentContext:
        """构建初始上下文"""
        return CodeAgentContext(
            session_id=f"{self.user_id}_{self.project_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            project_id=self.project_id,
            code_context=CodeContext(
                workspace_root=self.project_path,
                file_tree=self.workspace.get_file_list(self.project_id)
            ),
            execution_context=ExecutionContext(),
            tools=DEFAULT_TOOLS,
            memory=MemoryContext(
                project_conventions=["使用 type hints", "函数需要 docstring"]
            ),
            environment=EnvironmentInfo(),
            safety=SafetyConfig()
        )
    
    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        return f"""你是一个专业的 Python 量化编程助手。你的任务是帮助用户编写、修改和调试量化交易相关的代码。

## 当前项目信息
- 项目名称: {self.project_name}
- 项目路径: {self.project_path}
- 文件列表: {', '.join(self.context.code_context.file_tree) if self.context.code_context else '(空)'}

## 你的能力
1. **代码生成**: 根据用户需求生成 Python 代码
2. **代码修改**: 修改现有代码，添加功能或修复bug
3. **代码解释**: 解释代码的功能和逻辑
4. **调试帮助**: 分析错误信息，提供解决方案

## 输出格式
当你需要创建或修改文件时，请使用以下格式：

```python:文件路径
代码内容
```

例如：
```python:strategy/rsi.py
import pandas as pd

def calculate_rsi(prices, period=14):
    # RSI 计算逻辑
    pass
```

## 注意事项
1. 生成的代码应该清晰、可读、有适当的注释
2. 使用 type hints 提高代码可读性
3. 考虑错误处理和边界情况
4. 量化代码应考虑性能，优先使用 pandas/numpy 向量化操作
5. 不要生成可能造成安全风险的代码（如文件系统遍历、网络攻击等）

## 可用工具
你可以使用以下工具来完成任务：
- read_file: 读取文件内容
- write_file: 写入/创建文件
- list_files: 列出目录文件
- execute_code: 执行 Python 脚本

当你需要执行工具时，请在回复中明确说明需要执行的操作。
"""

    def chat(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入（非流式）
        
        Args:
            user_input: 用户输入
            
        Returns:
            包含回复和文件变更的字典
        """
        try:
            # 构建消息
            messages = [
                SystemMessage(content=self._build_system_prompt()),
            ]
            
            # 添加历史消息
            mem_vars = self.memory.load_memory_variables({})
            chat_history = mem_vars.get("chat_history", [])
            messages.extend(chat_history)
            
            # 添加用户消息
            messages.append(HumanMessage(content=user_input))
            
            # 调用 LLM
            response = self.llm.invoke(messages)
            reply = response.content
            
            # 解析文件变更
            file_changes = self._parse_file_changes(reply)
            
            # 应用文件变更
            applied_changes = []
            for change in file_changes:
                success = self.workspace.write_file(
                    self.project_id,
                    change["path"],
                    change["content"]
                )
                if success:
                    applied_changes.append(change["path"])
                    logging.info(f"Applied change to {change['path']}")
            
            # 更新上下文
            self.context.code_context.file_tree = self.workspace.get_file_list(self.project_id)
            
            # 保存到记忆
            self.memory.save_context(
                {"input": user_input},
                {"output": reply}
            )
            
            return {
                "reply": reply,
                "file_changes": applied_changes,
                "success": True
            }
            
        except Exception as e:
            logging.error(f"Chat error: {e}")
            return {
                "reply": f"抱歉，处理您的请求时出错：{str(e)}",
                "file_changes": [],
                "success": False
            }
    
    def chat_stream(self, user_input: str) -> Generator[Dict[str, Any], None, None]:
        """
        流式处理用户输入
        
        Yields:
            字典格式的事件:
            - {"type": "token", "content": "..."}
            - {"type": "file_change", "path": "...", "content": "..."}
            - {"type": "done", "file_changes": [...]}
            - {"type": "error", "message": "..."}
        """
        try:
            # 构建消息
            messages = [
                SystemMessage(content=self._build_system_prompt()),
            ]
            
            # 添加历史消息
            mem_vars = self.memory.load_memory_variables({})
            chat_history = mem_vars.get("chat_history", [])
            messages.extend(chat_history)
            
            # 添加用户消息
            messages.append(HumanMessage(content=user_input))
            
            # 流式调用 LLM
            full_response = ""
            for chunk in self.llm.stream(messages):
                if chunk.content:
                    full_response += chunk.content
                    yield {"type": "token", "content": chunk.content}
            
            # 解析文件变更
            file_changes = self._parse_file_changes(full_response)
            
            # 应用文件变更
            applied_changes = []
            for change in file_changes:
                success = self.workspace.write_file(
                    self.project_id,
                    change["path"],
                    change["content"]
                )
                if success:
                    applied_changes.append(change["path"])
                    yield {"type": "file_change", "path": change["path"]}
                    logging.info(f"Applied change to {change['path']}")
            
            # 更新上下文
            self.context.code_context.file_tree = self.workspace.get_file_list(self.project_id)
            
            # 保存到记忆
            self.memory.save_context(
                {"input": user_input},
                {"output": full_response}
            )
            
            yield {
                "type": "done",
                "file_changes": applied_changes,
                "success": True
            }
            
        except Exception as e:
            logging.error(f"Chat stream error: {e}")
            yield {"type": "error", "message": str(e)}
    
    def _parse_file_changes(self, response: str) -> List[Dict[str, str]]:
        """
        从 LLM 回复中解析文件变更
        
        解析格式：
        ```python:文件路径
        代码内容
        ```
        """
        changes = []
        
        # 匹配带路径的代码块
        pattern = r'```(?:python|py)?:([^\n]+)\n(.*?)```'
        matches = re.findall(pattern, response, re.DOTALL)
        
        for path, content in matches:
            path = path.strip()
            content = content.strip()
            
            # 安全检查：路径不能包含 ..
            if '..' in path or path.startswith('/'):
                logging.warning(f"Skipping unsafe path: {path}")
                continue
            
            changes.append({
                "path": path,
                "content": content
            })
        
        return changes
    
    def execute_file(self, file_path: str, timeout: str = "5min") -> Generator[Dict[str, Any], None, None]:
        """
        执行文件（流式）
        
        Args:
            file_path: 相对于项目的文件路径
            timeout: 超时设置
            
        Yields:
            执行输出事件
        """
        yield from executor.execute_stream(
            user_id=self.user_id,
            project_path=self.project_path,
            file_path=file_path,
            timeout=timeout
        )
    
    def stop_execution(self) -> bool:
        """停止执行"""
        return executor.stop(self.user_id)
    
    def is_executing(self) -> bool:
        """检查是否正在执行"""
        return executor.is_running(self.user_id)
    
    def get_file_content(self, file_path: str) -> Optional[str]:
        """获取文件内容"""
        return self.workspace.read_file(self.project_id, file_path)
    
    def save_file(self, file_path: str, content: str) -> bool:
        """保存文件"""
        success = self.workspace.write_file(self.project_id, file_path, content)
        if success:
            self.context.code_context.file_tree = self.workspace.get_file_list(self.project_id)
        return success
    
    def get_file_tree(self) -> List[Dict[str, Any]]:
        """获取文件树"""
        return self.workspace.get_file_tree(self.project_id)
    
    def get_context_summary(self) -> Dict[str, Any]:
        """获取上下文摘要"""
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "file_count": len(self.context.code_context.file_tree) if self.context.code_context else 0,
            "is_executing": self.is_executing()
        }

