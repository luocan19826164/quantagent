"""
工具模块
提供 Agent 可用的工具集
"""

from .base import (
    BaseTool,
    ToolResult,
    ToolDefinition,
    ToolRegistry,
    FunctionCallHandler
)
from .file_ops import (
    ReadFileTool,
    WriteFileTool,
    PatchFileTool,
    ListDirectoryTool,
    DeleteFileTool,
    GetFileOutlineTool
)
from .shell import (
    ShellExecTool,
    GrepTool,
    SandboxShellExecTool,
    process_manager,
    ProcessManager
)
from .version import (
    VersionManager,
    VersionInfo,
    CreateBackupTool,
    ListVersionsTool,
    RestoreVersionTool,
    GetVersionContentTool
)
from .plan_tool import CreatePlanTool, CREATE_PLAN_TOOL_NAME

# RAG 搜索工具（可选导入）
try:
    from ..rag import SemanticSearchTool
    _HAS_RAG = True
except ImportError:
    _HAS_RAG = False
    SemanticSearchTool = None


def create_tool_registry(workspace_path: str, strict_shell: bool = False,
                        enable_version: bool = True,
                        use_sandbox: bool = False,
                        user_id: int = None,
                        project_id: str = None,
                        enable_rag: bool = True) -> ToolRegistry:
    """
    创建并注册所有工具
    
    Args:
        workspace_path: 工作区路径
        strict_shell: 是否使用严格的 shell 命令白名单
        enable_version: 是否启用版本管理工具
        use_sandbox: 是否使用 Docker 沙箱执行 shell 命令
        user_id: 用户 ID（沙箱模式必需）
        project_id: 项目 ID（沙箱模式必需）
        enable_rag: 是否启用 RAG 语义搜索
        
    Returns:
        配置好的 ToolRegistry
    """
    registry = ToolRegistry()
    
    # 计划工具（让 LLM 自主决定是否需要 Plan）
    registry.register(CreatePlanTool())
    
    # 文件操作
    registry.register(ReadFileTool(workspace_path))
    registry.register(WriteFileTool(workspace_path))
    registry.register(PatchFileTool(workspace_path))
    registry.register(ListDirectoryTool(workspace_path))
    registry.register(DeleteFileTool(workspace_path))
    registry.register(GetFileOutlineTool(workspace_path))
    
    # Shell 执行（根据配置选择沙箱或本地）
    if use_sandbox and user_id is not None and project_id is not None:
        registry.register(SandboxShellExecTool(
            workspace_path=workspace_path,
            user_id=user_id,
            project_id=project_id
        ))
    else:
        registry.register(ShellExecTool(workspace_path, strict_mode=strict_shell))
    
    # Grep 搜索（始终可用）
    registry.register(GrepTool(workspace_path))
    
    # RAG 语义搜索（如果可用）
    if enable_rag and _HAS_RAG and SemanticSearchTool is not None:
        try:
            registry.register(SemanticSearchTool(workspace_path))
        except Exception as e:
            import logging
            logging.warning(f"Failed to register SemanticSearchTool: {e}")
    
    # 版本管理
    if enable_version:
        registry.register(CreateBackupTool(workspace_path))
        registry.register(ListVersionsTool(workspace_path))
        registry.register(RestoreVersionTool(workspace_path))
        registry.register(GetVersionContentTool(workspace_path))
    
    return registry


__all__ = [
    # Base
    'BaseTool',
    'ToolResult',
    'ToolDefinition',
    'ToolRegistry',
    'FunctionCallHandler',
    
    # Plan tool (让 LLM 自主决定模式)
    'CreatePlanTool',
    'CREATE_PLAN_TOOL_NAME',
    
    # File operations
    'ReadFileTool',
    'WriteFileTool',
    'PatchFileTool',
    'ListDirectoryTool',
    'DeleteFileTool',
    'GetFileOutlineTool',
    
    # Shell and search
    'ShellExecTool',
    'GrepTool',
    'SandboxShellExecTool',
    'process_manager',
    'ProcessManager',
    
    # Version management
    'VersionManager',
    'VersionInfo',
    'CreateBackupTool',
    'ListVersionsTool',
    'RestoreVersionTool',
    'GetVersionContentTool',
    
    # Factory
    'create_tool_registry',
]

