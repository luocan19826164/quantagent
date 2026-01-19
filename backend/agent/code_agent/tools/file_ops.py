"""
文件操作工具
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional

from .base import BaseTool, ToolResult


class ReadFileTool(BaseTool):
    """读取文件内容"""
    
    name = "read_file"
    description = "读取指定文件的内容。支持指定行范围以节省 token。"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于项目根目录的文件路径"
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（可选，从1开始）"
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号（可选）"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str, start_line: int = None, end_line: int = None) -> ToolResult:
        # 安全检查
        if ".." in path or path.startswith("/"):
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        full_path = os.path.join(self.workspace_path, path)
        
        if not os.path.exists(full_path):
            return ToolResult(success=False, error=f"File not found: {path}")
        
        if not os.path.isfile(full_path):
            return ToolResult(success=False, error=f"Not a file: {path}")
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 行范围处理
            if start_line is not None or end_line is not None:
                start = (start_line - 1) if start_line else 0
                end = end_line if end_line else len(lines)
                lines = lines[start:end]
                line_info = f" (lines {start_line or 1}-{end_line or len(lines)})"
            else:
                line_info = ""
            
            content = ''.join(lines)
            
            return ToolResult(
                success=True,
                output=f"文件内容{line_info}:\n```\n{content}\n```",
                data={"content": content, "path": path, "line_count": len(lines)}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to read file: {e}")


class WriteFileTool(BaseTool):
    """写入文件"""
    
    name = "write_file"
    description = "创建或覆盖文件。用于创建新文件或完全重写文件。"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于项目根目录的文件路径"
                },
                "content": {
                    "type": "string",
                    "description": "文件内容"
                }
            },
            "required": ["path", "content"]
        }
    
    def execute(self, path: str, content: str) -> ToolResult:
        # 安全检查
        if ".." in path or path.startswith("/"):
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        full_path = os.path.join(self.workspace_path, path)
        
        try:
            # 创建目录
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # 写入文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return ToolResult(
                success=True,
                output=f"文件已写入: {path} ({len(content)} 字符)",
                data={"path": path, "size": len(content)}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to write file: {e}")


class PatchFileTool(BaseTool):
    """修改文件的特定部分"""
    
    name = "patch_file"
    description = "精确修改文件的特定部分。使用 search/replace 模式，比重写整个文件更高效。"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于项目根目录的文件路径"
                },
                "patches": {
                    "type": "array",
                    "description": "修改列表",
                    "items": {
                        "type": "object",
                        "properties": {
                            "search": {
                                "type": "string",
                                "description": "要查找的精确内容（包含足够上下文以保证唯一性）"
                            },
                            "replace": {
                                "type": "string",
                                "description": "替换后的内容"
                            }
                        },
                        "required": ["search", "replace"]
                    }
                }
            },
            "required": ["path", "patches"]
        }
    
    def execute(self, path: str, patches: List[Dict[str, str]]) -> ToolResult:
        # 安全检查
        if ".." in path or path.startswith("/"):
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        full_path = os.path.join(self.workspace_path, path)
        
        if not os.path.exists(full_path):
            return ToolResult(success=False, error=f"File not found: {path}")
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original = content
            applied = []
            errors = []
            
            for i, patch in enumerate(patches):
                search = patch.get("search", "")
                replace = patch.get("replace", "")
                
                if not search:
                    errors.append(f"Patch {i+1}: empty search string")
                    continue
                
                # 检查是否存在
                if search not in content:
                    errors.append(f"Patch {i+1}: search string not found")
                    continue
                
                # 检查唯一性
                count = content.count(search)
                if count > 1:
                    errors.append(f"Patch {i+1}: search string not unique ({count} occurrences)")
                    continue
                
                # 应用补丁
                content = content.replace(search, replace, 1)
                applied.append(f"Patch {i+1}: applied")
            
            if not applied:
                return ToolResult(
                    success=False,
                    error=f"No patches applied. Errors: {'; '.join(errors)}"
                )
            
            # 写入文件
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            output = f"文件已修改: {path}\n" + "\n".join(applied)
            if errors:
                output += f"\n警告: {'; '.join(errors)}"
            
            return ToolResult(
                success=True,
                output=output,
                data={
                    "path": path, 
                    "patches_applied": len(applied), 
                    "errors": errors,
                    "new_content": content  # 返回更新后的完整内容，用于更新上下文
                }
            )
            
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to patch file: {e}")


class ListDirectoryTool(BaseTool):
    """列出目录内容"""
    
    name = "list_directory"
    description = "列出目录内容，返回文件和子目录列表"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于项目根目录的目录路径",
                    "default": "."
                },
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归列出子目录",
                    "default": False
                }
            }
        }
    
    def execute(self, path: str = ".", recursive: bool = False) -> ToolResult:
        # 安全检查
        if ".." in path:
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        full_path = os.path.join(self.workspace_path, path)
        
        if not os.path.exists(full_path):
            return ToolResult(success=False, error=f"Directory not found: {path}")
        
        if not os.path.isdir(full_path):
            return ToolResult(success=False, error=f"Not a directory: {path}")
        
        try:
            items = []
            
            if recursive:
                for root, dirs, files in os.walk(full_path):
                    rel_root = os.path.relpath(root, self.workspace_path)
                    for d in dirs:
                        if not d.startswith('.'):
                            items.append(f"📁 {os.path.join(rel_root, d)}/")
                    for f in files:
                        if not f.startswith('.'):
                            items.append(f"📄 {os.path.join(rel_root, f)}")
            else:
                for item in sorted(os.listdir(full_path)):
                    if item.startswith('.'):
                        continue
                    item_path = os.path.join(full_path, item)
                    if os.path.isdir(item_path):
                        items.append(f"📁 {item}/")
                    else:
                        items.append(f"📄 {item}")
            
            output = f"目录 '{path}' 内容:\n" + "\n".join(items) if items else f"目录 '{path}' 为空"
            
            return ToolResult(
                success=True,
                output=output,
                data={"path": path, "items": items, "count": len(items)}
            )
            
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to list directory: {e}")


class DeleteFileTool(BaseTool):
    """删除文件"""
    
    name = "delete_file"
    description = "删除指定文件"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于项目根目录的文件路径"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str) -> ToolResult:
        # 安全检查
        if ".." in path or path.startswith("/"):
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        full_path = os.path.join(self.workspace_path, path)
        
        if not os.path.exists(full_path):
            return ToolResult(success=False, error=f"File not found: {path}")
        
        if not os.path.isfile(full_path):
            return ToolResult(success=False, error=f"Not a file: {path}")
        
        try:
            os.remove(full_path)
            return ToolResult(
                success=True,
                output=f"文件已删除: {path}",
                data={"path": path}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to delete file: {e}")


class GetFileOutlineTool(BaseTool):
    """获取文件结构大纲"""
    
    name = "get_file_outline"
    description = "获取 Python 文件的结构大纲（类、函数、方法列表）"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对于项目根目录的 Python 文件路径"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str) -> ToolResult:
        import ast
        
        # 安全检查
        if ".." in path or path.startswith("/"):
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        full_path = os.path.join(self.workspace_path, path)
        
        if not os.path.exists(full_path):
            return ToolResult(success=False, error=f"File not found: {path}")
        
        if not path.endswith('.py'):
            return ToolResult(success=False, error="Only Python files are supported")
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            
            outline = []
            imports = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        imports.append(f"{module}.{alias.name}")
            
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.ClassDef):
                    methods = []
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef):
                            args = [a.arg for a in item.args.args]
                            methods.append(f"    def {item.name}({', '.join(args)}) [line {item.lineno}]")
                    
                    outline.append(f"class {node.name}: [line {node.lineno}]")
                    outline.extend(methods)
                    
                elif isinstance(node, ast.FunctionDef):
                    args = [a.arg for a in node.args.args]
                    outline.append(f"def {node.name}({', '.join(args)}) [line {node.lineno}]")
            
            output_parts = [f"文件大纲: {path}\n"]
            
            if imports:
                output_parts.append("导入:")
                output_parts.append("  " + ", ".join(imports[:10]))
                if len(imports) > 10:
                    output_parts.append(f"  ... 等 {len(imports)} 个导入")
            
            output_parts.append("\n结构:")
            output_parts.extend(outline if outline else ["  (空文件)"])
            
            return ToolResult(
                success=True,
                output="\n".join(output_parts),
                data={"path": path, "imports": imports, "outline": outline}
            )
            
        except SyntaxError as e:
            return ToolResult(success=False, error=f"Python syntax error: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to parse file: {e}")

