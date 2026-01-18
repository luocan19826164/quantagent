"""
代码分块器
将代码文件分割成有意义的块用于向量化
"""

import os
import re
import ast
import logging
from enum import Enum
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field


class ChunkType(Enum):
    """代码块类型"""
    MODULE = "module"           # 模块级（整个文件或导入部分）
    CLASS = "class"             # 类定义
    FUNCTION = "function"       # 函数/方法定义
    METHOD = "method"           # 类方法
    DOCSTRING = "docstring"     # 文档字符串
    COMMENT = "comment"         # 注释块
    CODE_BLOCK = "code_block"   # 代码块（如 if/for/with）
    UNKNOWN = "unknown"         # 未知类型


@dataclass
class CodeChunk:
    """代码块"""
    id: str                         # 唯一标识
    file_path: str                  # 文件路径
    chunk_type: ChunkType           # 块类型
    content: str                    # 代码内容
    start_line: int                 # 起始行
    end_line: int                   # 结束行
    
    # 元数据
    name: Optional[str] = None      # 名称（函数名/类名）
    parent: Optional[str] = None    # 父级名称（类名）
    signature: Optional[str] = None # 签名
    docstring: Optional[str] = None # 文档字符串
    
    # 上下文
    imports: List[str] = field(default_factory=list)    # 相关导入
    references: List[str] = field(default_factory=list) # 引用的符号
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "chunk_type": self.chunk_type.value,
            "content": self.content,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "name": self.name,
            "parent": self.parent,
            "signature": self.signature,
            "docstring": self.docstring,
            "imports": self.imports,
            "references": self.references,
        }
    
    def to_embedding_text(self) -> str:
        """生成用于向量化的文本"""
        parts = []
        
        # 添加类型和名称
        if self.name:
            parts.append(f"{self.chunk_type.value}: {self.name}")
        
        # 添加签名
        if self.signature:
            parts.append(f"signature: {self.signature}")
        
        # 添加文档字符串
        if self.docstring:
            parts.append(f"docstring: {self.docstring}")
        
        # 添加代码内容（截断）
        code = self.content[:1000] if len(self.content) > 1000 else self.content
        parts.append(f"code:\n{code}")
        
        return "\n".join(parts)
    
    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


class CodeChunker:
    """
    代码分块器
    
    将 Python 代码文件分割成语义有意义的块：
    - 类定义
    - 函数定义
    - 方法定义
    - 模块级代码
    """
    
    # 分块配置
    MIN_CHUNK_LINES = 3         # 最小块行数
    MAX_CHUNK_LINES = 100       # 最大块行数
    OVERLAP_LINES = 2           # 块之间的重叠行数
    
    def __init__(self, 
                 min_lines: int = MIN_CHUNK_LINES,
                 max_lines: int = MAX_CHUNK_LINES,
                 overlap: int = OVERLAP_LINES):
        self.min_lines = min_lines
        self.max_lines = max_lines
        self.overlap = overlap
    
    def chunk_file(self, file_path: str, content: Optional[str] = None) -> List[CodeChunk]:
        """
        对文件进行分块
        
        Args:
            file_path: 文件路径
            content: 文件内容（可选，如果不提供则读取文件）
            
        Returns:
            CodeChunk 列表
        """
        if content is None:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                logging.error(f"Failed to read file {file_path}: {e}")
                return []
        
        # 检查文件类型
        if file_path.endswith('.py'):
            return self._chunk_python(file_path, content)
        else:
            # 非 Python 文件使用简单分块
            return self._chunk_generic(file_path, content)
    
    def _chunk_python(self, file_path: str, content: str) -> List[CodeChunk]:
        """对 Python 文件进行 AST 分块"""
        chunks = []
        lines = content.split('\n')
        
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            logging.warning(f"Syntax error in {file_path}: {e}, falling back to generic chunking")
            return self._chunk_generic(file_path, content)
        
        # 提取导入
        imports = self._extract_imports(tree)
        
        # 提取模块级文档字符串
        module_docstring = ast.get_docstring(tree)
        if module_docstring:
            chunks.append(CodeChunk(
                id=f"{file_path}:module_doc",
                file_path=file_path,
                chunk_type=ChunkType.DOCSTRING,
                content=module_docstring,
                start_line=1,
                end_line=len(module_docstring.split('\n')),
                name="module_docstring",
                docstring=module_docstring,
                imports=imports
            ))
        
        # 遍历顶级节点
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                chunks.extend(self._process_class(file_path, node, lines, imports))
            elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                chunk = self._process_function(file_path, node, lines, imports)
                if chunk:
                    chunks.append(chunk)
        
        # 如果没有提取到任何块，使用通用分块
        if not chunks:
            return self._chunk_generic(file_path, content)
        
        return chunks
    
    def _process_class(self, file_path: str, node: ast.ClassDef, 
                      lines: List[str], imports: List[str]) -> List[CodeChunk]:
        """处理类定义"""
        chunks = []
        
        class_name = node.name
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        
        # 类代码
        class_content = '\n'.join(lines[start_line-1:end_line])
        class_docstring = ast.get_docstring(node)
        
        # 生成类签名
        bases = [self._node_to_string(base) for base in node.bases]
        signature = f"class {class_name}({', '.join(bases)})" if bases else f"class {class_name}"
        
        # 添加类块
        chunks.append(CodeChunk(
            id=f"{file_path}:{class_name}",
            file_path=file_path,
            chunk_type=ChunkType.CLASS,
            content=class_content,
            start_line=start_line,
            end_line=end_line,
            name=class_name,
            signature=signature,
            docstring=class_docstring,
            imports=imports
        ))
        
        # 处理类方法
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._process_function(
                    file_path, item, lines, imports, 
                    parent=class_name, is_method=True
                )
                if chunk:
                    chunks.append(chunk)
        
        return chunks
    
    def _process_function(self, file_path: str, node, lines: List[str],
                         imports: List[str], parent: Optional[str] = None,
                         is_method: bool = False) -> Optional[CodeChunk]:
        """处理函数/方法定义"""
        func_name = node.name
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        
        # 检查最小行数
        if end_line - start_line + 1 < self.min_lines:
            return None
        
        # 函数代码
        func_content = '\n'.join(lines[start_line-1:end_line])
        func_docstring = ast.get_docstring(node)
        
        # 生成签名
        signature = self._generate_function_signature(node)
        
        # 提取引用
        references = self._extract_references(node)
        
        chunk_type = ChunkType.METHOD if is_method else ChunkType.FUNCTION
        chunk_id = f"{file_path}:{parent}.{func_name}" if parent else f"{file_path}:{func_name}"
        
        return CodeChunk(
            id=chunk_id,
            file_path=file_path,
            chunk_type=chunk_type,
            content=func_content,
            start_line=start_line,
            end_line=end_line,
            name=func_name,
            parent=parent,
            signature=signature,
            docstring=func_docstring,
            imports=imports,
            references=references
        )
    
    def _generate_function_signature(self, node) -> str:
        """生成函数签名"""
        args = []
        
        # 位置参数
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._node_to_string(arg.annotation)}"
            args.append(arg_str)
        
        # *args
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        
        # **kwargs
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        
        # 返回类型
        return_type = ""
        if node.returns:
            return_type = f" -> {self._node_to_string(node.returns)}"
        
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)}){return_type}"
    
    def _extract_imports(self, tree: ast.Module) -> List[str]:
        """提取导入语句"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}")
        return imports
    
    def _extract_references(self, node) -> List[str]:
        """提取函数中引用的名称"""
        references = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                references.append(child.id)
            elif isinstance(child, ast.Attribute):
                # 简单处理属性访问
                if isinstance(child.value, ast.Name):
                    references.append(f"{child.value.id}.{child.attr}")
        return list(set(references))[:20]  # 限制数量
    
    def _node_to_string(self, node) -> str:
        """将 AST 节点转换为字符串"""
        try:
            return ast.unparse(node)
        except:
            return str(node)
    
    def _chunk_generic(self, file_path: str, content: str) -> List[CodeChunk]:
        """通用分块（基于行数）"""
        chunks = []
        lines = content.split('\n')
        total_lines = len(lines)
        
        if total_lines <= self.max_lines:
            # 文件较小，作为单个块
            chunks.append(CodeChunk(
                id=f"{file_path}:full",
                file_path=file_path,
                chunk_type=ChunkType.MODULE,
                content=content,
                start_line=1,
                end_line=total_lines,
                name=os.path.basename(file_path)
            ))
        else:
            # 按行数分块
            start = 0
            chunk_index = 0
            
            while start < total_lines:
                end = min(start + self.max_lines, total_lines)
                chunk_content = '\n'.join(lines[start:end])
                
                chunks.append(CodeChunk(
                    id=f"{file_path}:chunk_{chunk_index}",
                    file_path=file_path,
                    chunk_type=ChunkType.CODE_BLOCK,
                    content=chunk_content,
                    start_line=start + 1,
                    end_line=end,
                    name=f"chunk_{chunk_index}"
                ))
                
                # 如果已经到达文件末尾，退出循环
                if end >= total_lines:
                    break
                
                # 下一个块的起始位置（带重叠）
                start = end - self.overlap
                chunk_index += 1
        
        return chunks
    
    def chunk_directory(self, dir_path: str, 
                       extensions: List[str] = ['.py']) -> List[CodeChunk]:
        """
        对目录进行分块
        
        Args:
            dir_path: 目录路径
            extensions: 要处理的文件扩展名
            
        Returns:
            所有文件的 CodeChunk 列表
        """
        all_chunks = []
        
        for root, dirs, files in os.walk(dir_path):
            # 跳过隐藏目录和常见忽略目录
            dirs[:] = [d for d in dirs if not d.startswith('.') 
                      and d not in ('__pycache__', 'node_modules', 'venv', '.git')]
            
            for file in files:
                if any(file.endswith(ext) for ext in extensions):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, dir_path)
                    
                    chunks = self.chunk_file(file_path)
                    # 更新路径为相对路径
                    for chunk in chunks:
                        chunk.file_path = relative_path
                        chunk.id = chunk.id.replace(file_path, relative_path)
                    
                    all_chunks.extend(chunks)
        
        return all_chunks
