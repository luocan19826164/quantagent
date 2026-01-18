"""
语义搜索工具
提供给 Agent 使用的搜索接口
"""

import os
import logging
from typing import List, Dict, Any, Optional

from .index import CodeIndex, SearchResult
from .chunker import CodeChunker
from .embedder import get_embedder

# 导入工具基类
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.base import BaseTool, ToolResult


class SemanticSearchTool(BaseTool):
    """
    语义搜索工具
    
    使用向量相似度在代码库中搜索相关代码
    """
    
    name = "semantic_search"
    description = "使用自然语言语义搜索代码库，找到与查询最相关的代码片段"
    
    def __init__(self, 
                 workspace_path: str,
                 index_path: Optional[str] = None,
                 auto_index: bool = True):
        """
        初始化语义搜索工具
        
        Args:
            workspace_path: 工作区路径
            index_path: 索引存储路径
            auto_index: 是否自动建立索引
        """
        self.workspace_path = workspace_path
        self.index_path = index_path or os.path.join(workspace_path, ".code_index")
        
        # 初始化嵌入器和索引
        self._embedder = get_embedder("mock")  # 默认使用 mock，可以替换
        self._index = CodeIndex(self.index_path, self._embedder)
        
        # 自动索引
        if auto_index and self._index.get_stats()["total_chunks"] == 0:
            self._build_index()
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询（自然语言描述你要找的代码）"
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回的最大结果数（默认 5）",
                    "default": 5
                },
                "file_filter": {
                    "type": "string",
                    "description": "文件路径过滤模式（如 '*.py' 或 'src/*.py'）"
                }
            },
            "required": ["query"]
        }
    
    def execute(self, 
               query: str,
               top_k: int = 5,
               file_filter: Optional[str] = None) -> ToolResult:
        """执行语义搜索"""
        try:
            results = self._index.search(
                query=query,
                top_k=top_k,
                min_score=0.1,
                file_filter=file_filter
            )
            
            if not results:
                return ToolResult(
                    success=True,
                    output="没有找到相关代码",
                    data={"results": [], "count": 0}
                )
            
            # 格式化输出
            output_lines = [f"找到 {len(results)} 个相关代码片段:\n"]
            
            for r in results:
                chunk = r.chunk
                output_lines.append(f"### [{r.rank}] {chunk.file_path}:{chunk.start_line}-{chunk.end_line}")
                output_lines.append(f"**相似度**: {r.score:.2%}")
                
                if chunk.name:
                    output_lines.append(f"**{chunk.chunk_type.value}**: {chunk.name}")
                
                if chunk.signature:
                    output_lines.append(f"**签名**: `{chunk.signature}`")
                
                if chunk.docstring:
                    doc_preview = chunk.docstring[:200] + "..." if len(chunk.docstring) > 200 else chunk.docstring
                    output_lines.append(f"**文档**: {doc_preview}")
                
                # 代码预览（截断）
                code_preview = chunk.content[:500] if len(chunk.content) > 500 else chunk.content
                output_lines.append(f"```python\n{code_preview}\n```\n")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={
                    "results": [r.to_dict() for r in results],
                    "count": len(results)
                }
            )
            
        except Exception as e:
            logging.error(f"Semantic search error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"搜索失败: {str(e)}"
            )
    
    def _build_index(self):
        """构建索引"""
        logging.info(f"Building index for {self.workspace_path}...")
        
        try:
            count = self._index.index_directory(self.workspace_path)
            logging.info(f"Indexed {count} code chunks")
        except Exception as e:
            logging.error(f"Failed to build index: {e}")
    
    def rebuild_index(self) -> int:
        """重建索引"""
        self._index.clear()
        return self._index.index_directory(self.workspace_path)
    
    def update_file(self, file_path: str, content: Optional[str] = None) -> int:
        """更新单个文件的索引"""
        # 先移除旧的
        self._index.remove_file(file_path)
        
        # 重新索引
        abs_path = os.path.join(self.workspace_path, file_path)
        return self._index.index_file(abs_path, content)
    
    def get_index_stats(self) -> Dict[str, Any]:
        """获取索引统计"""
        return self._index.get_stats()


class CodeContextTool(BaseTool):
    """
    代码上下文工具
    
    获取特定函数/类的完整上下文，包括定义、调用关系等
    """
    
    name = "get_code_context"
    description = "获取指定函数或类的完整上下文，包括定义、文档和相关代码"
    
    def __init__(self, 
                 workspace_path: str,
                 code_index: Optional[CodeIndex] = None):
        self.workspace_path = workspace_path
        self._index = code_index
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol_name": {
                    "type": "string",
                    "description": "要查找的符号名称（函数名或类名）"
                },
                "file_path": {
                    "type": "string",
                    "description": "限定搜索的文件路径（可选）"
                }
            },
            "required": ["symbol_name"]
        }
    
    def execute(self, 
               symbol_name: str,
               file_path: Optional[str] = None) -> ToolResult:
        """获取代码上下文"""
        try:
            if not self._index:
                return ToolResult(
                    success=False,
                    error="索引未初始化"
                )
            
            # 搜索符号
            results = self._index.search(
                query=f"function or class named {symbol_name}",
                top_k=10,
                file_filter=file_path
            )
            
            # 过滤匹配的符号
            matches = [
                r for r in results 
                if r.chunk.name and symbol_name.lower() in r.chunk.name.lower()
            ]
            
            if not matches:
                return ToolResult(
                    success=True,
                    output=f"未找到符号: {symbol_name}",
                    data={"found": False}
                )
            
            # 返回最佳匹配
            best_match = matches[0]
            chunk = best_match.chunk
            
            output_lines = [
                f"# {chunk.chunk_type.value}: {chunk.name}",
                f"**文件**: {chunk.file_path}:{chunk.start_line}-{chunk.end_line}",
            ]
            
            if chunk.parent:
                output_lines.append(f"**所属类**: {chunk.parent}")
            
            if chunk.signature:
                output_lines.append(f"**签名**: `{chunk.signature}`")
            
            if chunk.docstring:
                output_lines.append(f"\n**文档字符串**:\n{chunk.docstring}")
            
            output_lines.append(f"\n**代码**:\n```python\n{chunk.content}\n```")
            
            if chunk.imports:
                output_lines.append(f"\n**相关导入**: {', '.join(chunk.imports[:10])}")
            
            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={
                    "found": True,
                    "chunk": chunk.to_dict(),
                    "score": best_match.score
                }
            )
            
        except Exception as e:
            logging.error(f"Get code context error: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"获取上下文失败: {str(e)}"
            )
