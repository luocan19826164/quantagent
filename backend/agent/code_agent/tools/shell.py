"""
Shell 执行工具
支持本地执行和 Docker 沙箱执行
支持流式输出和进程终止
"""

import os
import subprocess
import threading
import logging
import signal
import time
from typing import Dict, Any, Optional, Generator, Callable

from .base import BaseTool, ToolResult


# 全局进程管理器，用于跟踪和终止运行中的进程
class ProcessManager:
    """管理运行中的进程，支持终止"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._processes = {}  # {process_id: subprocess.Popen}
            cls._instance._lock = threading.Lock()
        return cls._instance
    
    def register(self, process_id: str, process: subprocess.Popen):
        """注册一个进程"""
        with self._lock:
            self._processes[process_id] = process
            logging.info(f"ProcessManager: Registered process {process_id} (PID: {process.pid})")
    
    def unregister(self, process_id: str):
        """注销一个进程"""
        with self._lock:
            if process_id in self._processes:
                del self._processes[process_id]
                logging.info(f"ProcessManager: Unregistered process {process_id}")
    
    def terminate(self, process_id: str) -> bool:
        """终止一个进程"""
        with self._lock:
            if process_id in self._processes:
                process = self._processes[process_id]
                try:
                    # 先尝试优雅终止
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # 强制杀死
                        process.kill()
                        process.wait()
                    logging.info(f"ProcessManager: Terminated process {process_id}")
                    del self._processes[process_id]
                    return True
                except Exception as e:
                    logging.error(f"ProcessManager: Failed to terminate {process_id}: {e}")
                    return False
        return False
    
    def is_running(self, process_id: str) -> bool:
        """检查进程是否在运行"""
        with self._lock:
            if process_id in self._processes:
                return self._processes[process_id].poll() is None
        return False
    
    def get_all_running(self) -> list:
        """获取所有运行中的进程 ID"""
        with self._lock:
            return [pid for pid, p in self._processes.items() if p.poll() is None]


# 全局单例
process_manager = ProcessManager()


class ShellExecTool(BaseTool):
    """执行 Shell 命令"""
    
    name = "shell_exec"
    description = "执行 shell 命令。用于运行脚本、安装依赖、查看系统信息等。"
    
    # 危险命令黑名单
    BLOCKED_COMMANDS = [
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=",
        ":(){:|:&};:",  # fork bomb
        "> /dev/sda",
        "chmod -R 777 /",
    ]
    
    # 允许的命令白名单前缀（可选，严格模式）
    ALLOWED_PREFIXES = [
        "python", "pip", "pip3",
        "ls", "cat", "head", "tail", "grep", "find", "wc",
        "mkdir", "touch", "cp", "mv",
        "echo", "pwd", "cd",
        "git",
    ]
    
    def __init__(self, workspace_path: str, strict_mode: bool = False):
        self.workspace_path = workspace_path
        self.strict_mode = strict_mode  # 严格模式只允许白名单命令
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（相对于项目根目录），默认为项目根目录"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 60",
                    "default": 60
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str, cwd: str = None, timeout: int = 60) -> ToolResult:
        # 安全检查
        safety_check = self._check_command_safety(command)
        if not safety_check["safe"]:
            return ToolResult(
                success=False,
                error=f"命令被阻止: {safety_check['reason']}"
            )
        
        # 确定工作目录
        if cwd:
            if ".." in cwd:
                return ToolResult(success=False, error="Invalid cwd: path traversal not allowed")
            work_dir = os.path.join(self.workspace_path, cwd)
        else:
            work_dir = self.workspace_path
        
        if not os.path.exists(work_dir):
            return ToolResult(success=False, error=f"Directory not found: {cwd or '.'}")
        
        try:
            logging.info(f"ShellExecTool: Executing '{command}' in {work_dir}")
            
            result = subprocess.run(
                command,
                shell=True,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )
            
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode
            
            # 截断过长的输出
            max_output = 10000
            if len(stdout) > max_output:
                stdout = stdout[:max_output] + f"\n... (输出已截断，共 {len(result.stdout)} 字符)"
            if len(stderr) > max_output:
                stderr = stderr[:max_output] + f"\n... (错误输出已截断，共 {len(result.stderr)} 字符)"
            
            output_parts = []
            if stdout:
                output_parts.append(f"标准输出:\n{stdout}")
            if stderr:
                output_parts.append(f"标准错误:\n{stderr}")
            output_parts.append(f"退出码: {exit_code}")
            
            return ToolResult(
                success=(exit_code == 0),
                output="\n\n".join(output_parts),
                error=stderr if exit_code != 0 else None,
                data={
                    "exit_code": exit_code,
                    "stdout": stdout,
                    "stderr": stderr
                }
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                error=f"命令执行超时 ({timeout} 秒)"
            )
        except Exception as e:
            return ToolResult(success=False, error=f"命令执行失败: {e}")
    
    def execute_stream(self, command: str, process_id: str, cwd: str = None, 
                       timeout: int = 300) -> Generator[Dict[str, Any], None, None]:
        """
        流式执行命令，实时输出
        
        Args:
            command: 要执行的命令
            process_id: 进程标识符（用于终止）
            cwd: 工作目录
            timeout: 超时秒数
            
        Yields:
            {"type": "stdout", "data": "..."}
            {"type": "stderr", "data": "..."}
            {"type": "exit", "code": 0, "duration": 1.5}
            {"type": "error", "message": "..."}
        """
        # 安全检查
        safety_check = self._check_command_safety(command)
        if not safety_check["safe"]:
            yield {"type": "error", "message": f"命令被阻止: {safety_check['reason']}"}
            return
        
        # 确定工作目录
        if cwd:
            if ".." in cwd:
                yield {"type": "error", "message": "Invalid cwd: path traversal not allowed"}
                return
            work_dir = os.path.join(self.workspace_path, cwd)
        else:
            work_dir = self.workspace_path
        
        if not os.path.exists(work_dir):
            yield {"type": "error", "message": f"Directory not found: {cwd or '.'}"}
            return
        
        start_time = time.time()
        process = None
        
        try:
            logging.info(f"ShellExecTool: Starting streaming execution '{command}' in {work_dir}")
            yield {"type": "started", "command": command, "process_id": process_id}
            
            # 使用 Popen 进行流式输出
            process = subprocess.Popen(
                command,
                shell=True,
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )
            
            # 注册进程
            process_manager.register(process_id, process)
            
            # 用线程读取 stderr（非阻塞）
            stderr_lines = []
            def read_stderr():
                for line in iter(process.stderr.readline, ''):
                    if line:
                        stderr_lines.append(line)
            
            stderr_thread = threading.Thread(target=read_stderr, daemon=True)
            stderr_thread.start()
            
            # 主线程读取 stdout
            for line in iter(process.stdout.readline, ''):
                # 检查超时
                if time.time() - start_time > timeout:
                    process.terminate()
                    yield {"type": "error", "message": f"命令执行超时 ({timeout} 秒)"}
                    return
                
                # 检查是否被终止
                if not process_manager.is_running(process_id):
                    yield {"type": "terminated", "message": "进程已被用户终止"}
                    return
                
                if line:
                    yield {"type": "stdout", "data": line.rstrip('\n')}
            
            # 等待进程结束
            process.wait()
            stderr_thread.join(timeout=1)
            
            # 输出 stderr
            for line in stderr_lines:
                yield {"type": "stderr", "data": line.rstrip('\n')}
            
            duration = time.time() - start_time
            exit_code = process.returncode
            
            yield {
                "type": "exit", 
                "code": exit_code, 
                "duration": round(duration, 2),
                "success": exit_code == 0
            }
            
        except Exception as e:
            logging.error(f"ShellExecTool streaming error: {e}")
            yield {"type": "error", "message": str(e)}
        
        finally:
            # 清理
            process_manager.unregister(process_id)
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=2)
                except:
                    process.kill()
    
    def _check_command_safety(self, command: str) -> Dict[str, Any]:
        """检查命令安全性"""
        command_lower = command.lower().strip()
        
        # 检查黑名单
        for blocked in self.BLOCKED_COMMANDS:
            if blocked in command_lower:
                return {"safe": False, "reason": f"包含危险命令模式: {blocked}"}
        
        # 检查危险操作
        if "sudo" in command_lower:
            return {"safe": False, "reason": "不允许使用 sudo"}
        
        # 严格模式：检查白名单
        if self.strict_mode:
            first_word = command_lower.split()[0] if command_lower else ""
            if not any(first_word.startswith(prefix) for prefix in self.ALLOWED_PREFIXES):
                return {"safe": False, "reason": f"命令 '{first_word}' 不在允许列表中"}
        
        return {"safe": True, "reason": None}


class GrepTool(BaseTool):
    """代码搜索"""
    
    name = "grep"
    description = "在代码中搜索文本或正则表达式，快速定位相关代码"
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "搜索模式（支持正则表达式）"
                },
                "path": {
                    "type": "string",
                    "description": "搜索路径（相对于项目根目录），默认为整个项目",
                    "default": "."
                },
                "include": {
                    "type": "string",
                    "description": "文件类型过滤，如 '*.py'",
                    "default": "*.py"
                },
                "context_lines": {
                    "type": "integer",
                    "description": "显示匹配行前后的行数",
                    "default": 2
                }
            },
            "required": ["pattern"]
        }
    
    def execute(self, pattern: str, path: str = ".", 
                include: str = "*.py", context_lines: int = 2) -> ToolResult:
        # 安全检查
        if ".." in path:
            return ToolResult(success=False, error="Invalid path: path traversal not allowed")
        
        search_path = os.path.join(self.workspace_path, path)
        
        if not os.path.exists(search_path):
            return ToolResult(success=False, error=f"Path not found: {path}")
        
        try:
            # 构建 grep 命令
            # 使用 grep -r 进行递归搜索
            cmd = [
                "grep", "-r", "-n",  # 递归、显示行号
                f"--include={include}",
                f"-C{context_lines}",  # 上下文行数
                "-E",  # 扩展正则
                pattern,
                search_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.workspace_path
            )
            
            output = result.stdout
            
            if not output:
                return ToolResult(
                    success=True,
                    output=f"未找到匹配 '{pattern}' 的内容",
                    data={"matches": 0}
                )
            
            # 处理输出，将绝对路径转为相对路径
            lines = output.split('\n')
            processed_lines = []
            for line in lines:
                if line.startswith(self.workspace_path):
                    line = line[len(self.workspace_path)+1:]
                processed_lines.append(line)
            
            output = '\n'.join(processed_lines)
            
            # 截断过长的输出
            max_output = 8000
            if len(output) > max_output:
                output = output[:max_output] + f"\n... (结果已截断)"
            
            # 统计匹配数
            match_count = len([l for l in processed_lines if l and not l.startswith('--')])
            
            return ToolResult(
                success=True,
                output=f"搜索 '{pattern}' 结果 ({match_count} 处匹配):\n\n{output}",
                data={"matches": match_count, "pattern": pattern}
            )
            
        except subprocess.TimeoutExpired:
            return ToolResult(success=False, error="搜索超时")
        except Exception as e:
            return ToolResult(success=False, error=f"搜索失败: {e}")


class SandboxShellExecTool(BaseTool):
    """
    在 Docker 沙箱中执行 Shell 命令
    
    安全保证：
    - 所有命令在隔离的 Docker 容器中执行
    - 文件系统隔离（只挂载工作区）
    - 网络隔离（可配置）
    - 资源限制（CPU、内存、执行时间）
    """
    
    name = "shell_exec"
    description = "在安全沙箱中执行 shell 命令。用于运行脚本、安装依赖、测试代码等。"
    
    def __init__(self, workspace_path: str, user_id: int, project_id: str,
                 sandbox_executor=None):
        """
        初始化沙箱 Shell 工具
        
        Args:
            workspace_path: 工作区路径
            user_id: 用户 ID
            project_id: 项目 ID
            sandbox_executor: SandboxExecutor 实例（可选，懒加载）
        """
        self.workspace_path = workspace_path
        self.user_id = user_id
        self.project_id = project_id
        self._sandbox_executor = sandbox_executor
    
    @property
    def sandbox_executor(self):
        """懒加载 SandboxExecutor"""
        if self._sandbox_executor is None:
            try:
                from ..sandbox import DockerManager, SandboxExecutor
                docker_manager = DockerManager(base_workspace_path=os.path.dirname(self.workspace_path))
                self._sandbox_executor = SandboxExecutor(docker_manager)
            except Exception as e:
                logging.warning(f"Failed to initialize sandbox executor: {e}")
                return None
        return self._sandbox_executor
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的 shell 命令"
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 300（5分钟）",
                    "default": 300
                },
                "enable_network": {
                    "type": "boolean",
                    "description": "是否启用网络（用于 pip install 等）",
                    "default": False
                }
            },
            "required": ["command"]
        }
    
    def execute(self, command: str, timeout: int = 300, 
                enable_network: bool = False) -> ToolResult:
        """在沙箱中执行命令"""
        
        # 检查沙箱是否可用
        if self.sandbox_executor is None:
            logging.warning("Sandbox not available, falling back to local execution")
            # 回退到本地执行（带安全检查）
            return self._fallback_execute(command, timeout)
        
        try:
            from ..sandbox import ExecutionConfig
            
            config = ExecutionConfig(
                timeout=timeout,
                enable_network=enable_network,
            )
            
            result = self.sandbox_executor.execute_command(
                user_id=self.user_id,
                project_id=self.project_id,
                command=command,
                config=config
            )
            
            output_parts = []
            if result.stdout:
                output_parts.append(f"标准输出:\n{result.stdout}")
            if result.stderr:
                output_parts.append(f"标准错误:\n{result.stderr}")
            output_parts.append(f"退出码: {result.exit_code}")
            output_parts.append(f"执行时间: {result.duration_seconds:.2f}s")
            
            return ToolResult(
                success=result.exit_code == 0,
                output="\n\n".join(output_parts),
                error=result.error if result.exit_code != 0 else None,
                data={
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "duration": result.duration_seconds,
                    "sandbox": True
                }
            )
            
        except Exception as e:
            logging.error(f"Sandbox execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"沙箱执行失败: {e}"
            )
    
    def _fallback_execute(self, command: str, timeout: int) -> ToolResult:
        """回退到本地执行（带安全检查）"""
        # 使用普通 ShellExecTool 的安全检查
        local_tool = ShellExecTool(self.workspace_path, strict_mode=True)
        return local_tool.execute(command, timeout=timeout)

