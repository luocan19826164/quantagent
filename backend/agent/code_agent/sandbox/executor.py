"""
沙箱执行器
在 Docker 容器中安全执行代码
"""

import os
import time
import logging
import threading
from enum import Enum
from typing import Optional, Dict, Any, List, Generator
from dataclasses import dataclass, field
from datetime import datetime

from .container import DockerManager, ContainerConfig, ContainerInfo, ContainerStatus


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ExecutionConfig:
    """执行配置"""
    # 执行选项
    timeout: int = 300                  # 执行超时（秒）
    enable_network: bool = False        # 是否启用网络
    
    # Python 相关
    python_version: str = "3.11"        # Python 版本
    install_packages: List[str] = field(default_factory=list)  # 需要安装的包
    
    # 资源限制
    memory_limit: str = "512m"          # 内存限制
    cpu_percent: int = 50               # CPU 使用上限百分比
    
    # 输出选项
    capture_stdout: bool = True
    capture_stderr: bool = True
    max_output_size: int = 1024 * 1024  # 最大输出大小（1MB）


@dataclass
class ExecutionResult:
    """执行结果"""
    status: ExecutionStatus
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None
    
    # 时间信息
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # 资源使用
    peak_memory_mb: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "peak_memory_mb": self.peak_memory_mb,
        }


class SandboxExecutor:
    """
    沙箱执行器
    
    提供安全的代码执行环境，支持：
    1. Python 脚本执行
    2. Shell 命令执行
    3. 包安装
    4. 流式输出
    """
    
    # 预置的 Docker 镜像
    DEFAULT_IMAGES = {
        "3.9": "python:3.9-slim",
        "3.10": "python:3.10-slim",
        "3.11": "python:3.11-slim",
        "3.12": "python:3.12-slim",
    }
    
    # 预装的量化库
    QUANT_PACKAGES = [
        "pandas",
        "numpy",
        "matplotlib",
        "scipy",
        "ta-lib",
    ]
    
    def __init__(self, docker_manager: DockerManager):
        """
        初始化执行器
        
        Args:
            docker_manager: Docker 管理器实例
        """
        self.docker_manager = docker_manager
        
        # 执行追踪
        self._executions: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def execute_python(self,
                      user_id: int,
                      project_id: str,
                      script_path: str,
                      config: Optional[ExecutionConfig] = None) -> ExecutionResult:
        """
        执行 Python 脚本
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            script_path: 脚本路径（相对于工作区）
            config: 执行配置
            
        Returns:
            ExecutionResult
        """
        config = config or ExecutionConfig()
        
        # 构建命令
        command = f"python {script_path}"
        
        return self._execute(user_id, project_id, command, config)
    
    def execute_command(self,
                       user_id: int,
                       project_id: str,
                       command: str,
                       config: Optional[ExecutionConfig] = None) -> ExecutionResult:
        """
        执行 Shell 命令
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            command: Shell 命令
            config: 执行配置
            
        Returns:
            ExecutionResult
        """
        config = config or ExecutionConfig()
        return self._execute(user_id, project_id, command, config)
    
    def execute_code(self,
                    user_id: int,
                    project_id: str,
                    code: str,
                    config: Optional[ExecutionConfig] = None) -> ExecutionResult:
        """
        执行 Python 代码片段
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            code: Python 代码
            config: 执行配置
            
        Returns:
            ExecutionResult
        """
        config = config or ExecutionConfig()
        
        # 将代码写入临时文件并执行
        # 使用 here-doc 风格避免引号问题
        escaped_code = code.replace("'", "'\"'\"'")
        command = f"python -c '{escaped_code}'"
        
        return self._execute(user_id, project_id, command, config)
    
    def install_packages(self,
                        user_id: int,
                        project_id: str,
                        packages: List[str],
                        config: Optional[ExecutionConfig] = None) -> ExecutionResult:
        """
        安装 Python 包
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            packages: 包列表
            config: 执行配置
            
        Returns:
            ExecutionResult
        """
        config = config or ExecutionConfig()
        
        # 需要网络来安装包
        config.enable_network = True
        
        # 构建 pip 命令
        packages_str = " ".join(packages)
        command = f"pip install --no-cache-dir {packages_str}"
        
        return self._execute(user_id, project_id, command, config)
    
    def execute_stream(self,
                      user_id: int,
                      project_id: str,
                      command: str,
                      config: Optional[ExecutionConfig] = None) -> Generator[Dict[str, Any], None, None]:
        """
        流式执行命令
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            command: 命令
            config: 执行配置
            
        Yields:
            输出事件
        """
        config = config or ExecutionConfig()
        execution_id = f"{user_id}_{project_id}_{int(time.time())}"
        
        yield {"type": "started", "execution_id": execution_id}
        
        # 确保容器存在
        container_config = self._build_container_config(config)
        container_info = self.docker_manager.ensure_container(user_id, project_id, container_config)
        
        if not container_info:
            yield {
                "type": "error",
                "error": "Failed to create container"
            }
            return
        
        yield {"type": "container_ready", "container_id": container_info.container_id[:12]}
        
        # 执行命令
        result = self.docker_manager.exec_in_container(
            container_info.container_id,
            command,
            timeout=config.timeout
        )
        
        # 输出结果
        if result.get("stdout"):
            yield {"type": "stdout", "data": result["stdout"]}
        
        if result.get("stderr"):
            yield {"type": "stderr", "data": result["stderr"]}
        
        # 完成事件
        yield {
            "type": "completed",
            "exit_code": result.get("exit_code", -1),
            "success": result.get("success", False),
            "timed_out": result.get("timed_out", False)
        }
    
    def _execute(self,
                user_id: int,
                project_id: str,
                command: str,
                config: ExecutionConfig) -> ExecutionResult:
        """内部执行方法"""
        
        result = ExecutionResult(status=ExecutionStatus.PREPARING)
        result.started_at = datetime.now()
        
        try:
            # 确保容器存在
            container_config = self._build_container_config(config)
            container_info = self.docker_manager.ensure_container(user_id, project_id, container_config)
            
            if not container_info:
                result.status = ExecutionStatus.FAILED
                result.error = "Failed to create/start container"
                return result
            
            # 如果需要安装包，先安装
            if config.install_packages:
                packages_str = " ".join(config.install_packages)
                install_result = self.docker_manager.exec_in_container(
                    container_info.container_id,
                    f"pip install --no-cache-dir {packages_str}",
                    timeout=120
                )
                if not install_result.get("success"):
                    result.status = ExecutionStatus.FAILED
                    result.error = f"Package installation failed: {install_result.get('stderr')}"
                    return result
            
            # 执行命令
            result.status = ExecutionStatus.RUNNING
            
            exec_result = self.docker_manager.exec_in_container(
                container_info.container_id,
                command,
                timeout=config.timeout
            )
            
            # 更新结果
            result.exit_code = exec_result.get("exit_code", -1)
            result.stdout = exec_result.get("stdout", "")
            result.stderr = exec_result.get("stderr", "")
            
            # 截断过长的输出
            if len(result.stdout) > config.max_output_size:
                result.stdout = result.stdout[:config.max_output_size] + "\n... [output truncated]"
            if len(result.stderr) > config.max_output_size:
                result.stderr = result.stderr[:config.max_output_size] + "\n... [output truncated]"
            
            if exec_result.get("timed_out"):
                result.status = ExecutionStatus.TIMEOUT
                result.error = f"Execution timed out after {config.timeout}s"
            elif exec_result.get("success"):
                result.status = ExecutionStatus.COMPLETED
            else:
                result.status = ExecutionStatus.FAILED
                result.error = result.stderr or "Execution failed"
            
            # 获取资源使用情况
            try:
                stats = self.docker_manager.get_container_stats(container_info.container_id)
                if stats:
                    result.peak_memory_mb = stats.get("memory_usage", 0) / (1024 * 1024)
            except:
                pass
            
        except Exception as e:
            logging.error(f"Execution error: {e}", exc_info=True)
            result.status = ExecutionStatus.FAILED
            result.error = str(e)
        
        finally:
            result.completed_at = datetime.now()
            if result.started_at:
                result.duration_seconds = (result.completed_at - result.started_at).total_seconds()
        
        return result
    
    def _build_container_config(self, exec_config: ExecutionConfig) -> ContainerConfig:
        """构建容器配置"""
        # 选择镜像
        image = self.DEFAULT_IMAGES.get(
            exec_config.python_version,
            f"python:{exec_config.python_version}-slim"
        )
        
        # 网络模式
        network_mode = "bridge" if exec_config.enable_network else "none"
        
        # CPU 配额
        cpu_quota = exec_config.cpu_percent * 1000  # 转换为微秒
        
        return ContainerConfig(
            image=image,
            memory_limit=exec_config.memory_limit,
            cpu_quota=cpu_quota,
            network_mode=network_mode,
            execution_timeout=exec_config.timeout,
        )
    
    def cancel_execution(self, user_id: int, project_id: str) -> bool:
        """
        取消执行
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            
        Returns:
            是否成功
        """
        container_info = self.docker_manager.get_project_container(user_id, project_id)
        if container_info:
            # 停止并重启容器来终止执行
            self.docker_manager.stop_container(container_info.container_id)
            return True
        return False
    
    def get_execution_status(self, user_id: int, project_id: str) -> Dict[str, Any]:
        """获取执行状态"""
        container_info = self.docker_manager.get_project_container(user_id, project_id)
        
        if not container_info:
            return {"status": "no_container"}
        
        return {
            "status": container_info.status.value,
            "container_id": container_info.container_id[:12],
            "last_used": container_info.last_used_at.isoformat(),
        }

