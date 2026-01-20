"""
工具基类和 Function Calling 处理
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
import json
import logging


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    data: Optional[Dict[str, Any]] = None  # 结构化数据（如文件内容）
    files_changed: List[str] = field(default_factory=list)  # 变更的文件列表
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "data": self.data,
            "files_changed": self.files_changed
        }
    
    def to_message(self) -> str:
        """转换为给 LLM 看的消息"""
        if self.success:
            return self.output
        else:
            return f"错误: {self.error}"


@dataclass
class ToolDefinition:
    """工具定义（OpenAI Function Calling 格式）"""
    name: str
    description: str
    parameters: Dict[str, Any]
    
    def to_openai_format(self) -> Dict[str, Any]:
        """转换为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


class BaseTool(ABC):
    """工具基类"""
    
    name: str = ""
    description: str = ""
    
    @abstractmethod
    def get_parameters_schema(self) -> Dict[str, Any]:
        """获取参数 JSON Schema"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具"""
        pass
    
    def get_definition(self) -> ToolDefinition:
        """获取工具定义"""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.get_parameters_schema()
        )


class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool):
        """注册工具"""
        self._tools[tool.name] = tool
        logging.debug(f"ToolRegistry: Registered tool '{tool.name}'")
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def execute(self, name: str, **kwargs) -> ToolResult:
        """执行工具"""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {name}"
            )
        
        try:
            return tool.execute(**kwargs)
        except Exception as e:
            logging.error(f"ToolRegistry: Tool '{name}' execution failed: {e}")
            return ToolResult(
                success=False,
                error=str(e)
            )
    
    def get_all_definitions(self) -> List[Dict[str, Any]]:
        """获取所有工具的 OpenAI 格式定义"""
        return [
            tool.get_definition().to_openai_format()
            for tool in self._tools.values()
        ]
    
    def list_tools(self) -> List[str]:
        """列出所有工具名称"""
        return list(self._tools.keys())


class FunctionCallHandler:
    """
    Function Calling 处理器
    处理 LLM 返回的工具调用
    """
    
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
    
    def parse_tool_calls(self, response) -> List[Dict[str, Any]]:
        """
        解析 LLM 响应中的工具调用
        
        支持多种格式:
        1. LangChain 标准格式: {"name": str, "args": dict, "id": str}
        2. OpenAI 格式: {"id": str, "function": {"name": str, "arguments": str}}
        3. Claude/Anthropic 格式: {"type": "tool_use", "id": str, "name": str, "input": dict}
        
        Args:
            response: LLM 响应对象
            
        Returns:
            工具调用列表，每个元素包含 id, name, arguments
        """
        tool_calls = []
        
        if hasattr(response, 'tool_calls') and response.tool_calls:
            for tc in response.tool_calls:
                try:
                    # LangChain 统一格式: {"name": str, "args": dict, "id": str, "type": "tool_call"}
                    # 无论底层是 OpenAI、Claude 还是其他模型，LangChain 都会转换成这个格式
                    if isinstance(tc, dict):
                        tc_id = tc.get('id', '')
                        tc_name = tc.get('name', '')
                        tc_args = tc.get('args', {})
                    else:
                        # 兼容对象格式（某些版本可能返回对象）
                        tc_id = getattr(tc, 'id', '') or ''
                        tc_name = getattr(tc, 'name', '')
                        tc_args = getattr(tc, 'args', {})
                    
                    if tc_name:
                        tool_calls.append({
                            "id": tc_id,
                            "name": tc_name,
                            "arguments": tc_args
                        })
                except Exception as e:
                    logging.warning(f"Error parsing tool call: {e}, tc={tc}")
        
        return tool_calls
    
    def execute_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        执行工具调用
        
        Args:
            tool_calls: 工具调用列表
            
        Returns:
            执行结果列表
        """
        results = []
        
        for tc in tool_calls:
            name = tc.get("name")
            args = tc.get("arguments", {})
            tc_id = tc.get("id")
            
            if "error" in tc:
                results.append({
                    "tool_call_id": tc_id,
                    "name": name,
                    "result": ToolResult(success=False, error=tc["error"])
                })
                continue
            

            
            logging.info(f"FunctionCallHandler: Executing tool '{name}' with args: {args}")
            result = self.registry.execute(name, **args)
            
            results.append({
                "tool_call_id": tc_id,
                "name": name,
                "arguments": args,
                "result": result
            })
        
        return results
    
    def format_tool_results_for_llm(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        格式化工具结果，准备发送给 LLM
        
        Args:
            results: execute_tool_calls 的返回值
            
        Returns:
            LLM 消息格式的结果列表
        """
        messages = []
        
        for r in results:
            result: ToolResult = r["result"]
            messages.append({
                "role": "tool",
                "tool_call_id": r["tool_call_id"],
                "name": r["name"],
                "content": result.to_message()
            })
        
        return messages
    
    def extract_changed_files(self, results: List[Dict[str, Any]]) -> List[str]:
        """从工具执行结果中提取变更的文件"""
        changed_files = []
        
        for r in results:
            name = r.get("name", "")
            args = r.get("arguments", {})
            result: ToolResult = r.get("result")
            
            if not result or not result.success:
                continue
            
            # 写入文件的操作
            if name in ("write_file", "patch_file"):
                path = args.get("path")
                if path:
                    changed_files.append(path)
        
        return changed_files

