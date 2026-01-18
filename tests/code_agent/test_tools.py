"""
测试工具层
"""

import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.tools import (
    ToolRegistry,
    ToolResult,
    ReadFileTool,
    WriteFileTool,
    PatchFileTool,
    ListDirectoryTool,
    GetFileOutlineTool,
    ShellExecTool,
    GrepTool,
    create_tool_registry
)


@pytest.fixture
def workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_tools_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_file(workspace):
    """创建示例文件"""
    content = '''def hello():
    print("Hello World")

def add(a, b):
    return a + b

class Calculator:
    def multiply(self, x, y):
        return x * y
'''
    file_path = os.path.join(workspace, "sample.py")
    with open(file_path, 'w') as f:
        f.write(content)
    return "sample.py"


class TestToolRegistry:
    """测试工具注册表"""
    
    def test_create_registry(self, workspace):
        """测试创建注册表"""
        registry = create_tool_registry(workspace)
        
        tools = registry.list_tools()
        
        assert "read_file" in tools
        assert "write_file" in tools
        assert "patch_file" in tools
        assert "shell_exec" in tools
        assert "grep" in tools
    
    def test_get_tool(self, workspace):
        """测试获取工具"""
        registry = create_tool_registry(workspace)
        
        tool = registry.get("read_file")
        
        assert tool is not None
        assert tool.name == "read_file"
    
    def test_get_all_definitions(self, workspace):
        """测试获取所有工具定义"""
        registry = create_tool_registry(workspace)
        
        definitions = registry.get_all_definitions()
        
        assert len(definitions) > 0
        assert all(d["type"] == "function" for d in definitions)


class TestReadFileTool:
    """测试读取文件工具"""
    
    def test_read_existing_file(self, workspace, sample_file):
        """测试读取存在的文件"""
        tool = ReadFileTool(workspace)
        
        result = tool.execute(path=sample_file)
        
        assert result.success is True
        assert "def hello" in result.output
        assert "Calculator" in result.output
    
    def test_read_nonexistent_file(self, workspace):
        """测试读取不存在的文件"""
        tool = ReadFileTool(workspace)
        
        result = tool.execute(path="nonexistent.py")
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    def test_read_with_line_range(self, workspace, sample_file):
        """测试读取指定行范围"""
        tool = ReadFileTool(workspace)
        
        result = tool.execute(path=sample_file, start_line=1, end_line=3)
        
        assert result.success is True
        assert "def hello" in result.output
        # 不应该包含后面的内容
        assert "Calculator" not in result.output
    
    def test_path_traversal_blocked(self, workspace):
        """测试路径穿越被阻止"""
        tool = ReadFileTool(workspace)
        
        result = tool.execute(path="../../../etc/passwd")
        
        assert result.success is False
        assert "traversal" in result.error.lower()


class TestWriteFileTool:
    """测试写入文件工具"""
    
    def test_write_new_file(self, workspace):
        """测试写入新文件"""
        tool = WriteFileTool(workspace)
        
        result = tool.execute(
            path="new_file.py",
            content="print('Hello')"
        )
        
        assert result.success is True
        
        # 验证文件存在
        assert os.path.exists(os.path.join(workspace, "new_file.py"))
    
    def test_write_creates_directory(self, workspace):
        """测试自动创建目录"""
        tool = WriteFileTool(workspace)
        
        result = tool.execute(
            path="subdir/nested/file.py",
            content="# nested file"
        )
        
        assert result.success is True
        assert os.path.exists(os.path.join(workspace, "subdir/nested/file.py"))
    
    def test_overwrite_existing_file(self, workspace, sample_file):
        """测试覆盖现有文件"""
        tool = WriteFileTool(workspace)
        
        result = tool.execute(
            path=sample_file,
            content="# new content"
        )
        
        assert result.success is True
        
        # 验证内容已更改
        with open(os.path.join(workspace, sample_file)) as f:
            content = f.read()
        assert content == "# new content"


class TestPatchFileTool:
    """测试补丁文件工具"""
    
    def test_simple_patch(self, workspace, sample_file):
        """测试简单补丁"""
        tool = PatchFileTool(workspace)
        
        result = tool.execute(
            path=sample_file,
            patches=[{
                "search": 'print("Hello World")',
                "replace": 'print("Hello Python")'
            }]
        )
        
        assert result.success is True
        
        # 验证内容已更改
        with open(os.path.join(workspace, sample_file)) as f:
            content = f.read()
        assert 'print("Hello Python")' in content
    
    def test_patch_not_found(self, workspace, sample_file):
        """测试补丁内容不存在"""
        tool = PatchFileTool(workspace)
        
        result = tool.execute(
            path=sample_file,
            patches=[{
                "search": "nonexistent content",
                "replace": "replacement"
            }]
        )
        
        assert result.success is False
        assert "not found" in result.error.lower()
    
    def test_multiple_patches(self, workspace, sample_file):
        """测试多个补丁"""
        tool = PatchFileTool(workspace)
        
        result = tool.execute(
            path=sample_file,
            patches=[
                {"search": "Hello World", "replace": "Hello Universe"},
                {"search": "return a + b", "replace": "return a + b + 1"}
            ]
        )
        
        assert result.success is True
        assert result.data["patches_applied"] == 2


class TestListDirectoryTool:
    """测试列出目录工具"""
    
    def test_list_directory(self, workspace, sample_file):
        """测试列出目录"""
        tool = ListDirectoryTool(workspace)
        
        result = tool.execute(path=".")
        
        assert result.success is True
        assert "sample.py" in result.output
    
    def test_list_empty_directory(self, workspace):
        """测试列出空目录"""
        # 创建空子目录
        os.makedirs(os.path.join(workspace, "empty_dir"))
        
        tool = ListDirectoryTool(workspace)
        result = tool.execute(path="empty_dir")
        
        assert result.success is True
        assert "为空" in result.output


class TestGetFileOutlineTool:
    """测试文件大纲工具"""
    
    def test_get_outline(self, workspace, sample_file):
        """测试获取文件大纲"""
        tool = GetFileOutlineTool(workspace)
        
        result = tool.execute(path=sample_file)
        
        assert result.success is True
        assert "hello" in result.output
        assert "add" in result.output
        assert "Calculator" in result.output
        assert "multiply" in result.output
    
    def test_outline_nonpython_file(self, workspace):
        """测试非 Python 文件"""
        # 创建非 Python 文件
        with open(os.path.join(workspace, "readme.md"), 'w') as f:
            f.write("# README")
        
        tool = GetFileOutlineTool(workspace)
        result = tool.execute(path="readme.md")
        
        assert result.success is False
        assert "Python" in result.error


class TestShellExecTool:
    """测试 Shell 执行工具"""
    
    def test_simple_command(self, workspace):
        """测试简单命令"""
        tool = ShellExecTool(workspace)
        
        result = tool.execute(command="echo 'hello'")
        
        assert result.success is True
        assert "hello" in result.output
    
    def test_command_with_exit_code(self, workspace):
        """测试命令退出码"""
        tool = ShellExecTool(workspace)
        
        result = tool.execute(command="exit 1")
        
        assert result.success is False
        assert result.data["exit_code"] == 1
    
    def test_dangerous_command_blocked(self, workspace):
        """测试危险命令被阻止"""
        tool = ShellExecTool(workspace)
        
        result = tool.execute(command="sudo rm -rf /")
        
        assert result.success is False
        assert "阻止" in result.error or "不允许" in result.error
    
    def test_timeout(self, workspace):
        """测试超时"""
        tool = ShellExecTool(workspace)
        
        result = tool.execute(command="sleep 10", timeout=1)
        
        assert result.success is False
        assert "超时" in result.error


class TestGrepTool:
    """测试 Grep 搜索工具"""
    
    def test_grep_found(self, workspace, sample_file):
        """测试搜索找到"""
        tool = GrepTool(workspace)
        
        result = tool.execute(pattern="def hello")
        
        assert result.success is True
        assert "def hello" in result.output
    
    def test_grep_not_found(self, workspace, sample_file):
        """测试搜索未找到"""
        tool = GrepTool(workspace)
        
        result = tool.execute(pattern="nonexistent_function")
        
        assert result.success is True
        assert "未找到" in result.output
    
    def test_grep_regex(self, workspace, sample_file):
        """测试正则搜索"""
        tool = GrepTool(workspace)
        
        result = tool.execute(pattern="def \\w+\\(")
        
        assert result.success is True
        # 应该匹配多个函数定义
        assert result.data["matches"] >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

