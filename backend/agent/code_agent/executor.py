"""
代码执行器
负责安全地执行用户的 Python 代码
"""

import os
import sys
import signal
import subprocess
import threading
import logging
from typing import Dict, Any, Optional, Generator, Callable
from datetime import datetime
from dataclasses import dataclass
from enum import Enum


class ExecutionStatus(Enum):
    """执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    STOPPED = "stopped"


@dataclass
class ExecutionResult:
    """执行结果"""
    status: ExecutionStatus
    exit_code: Optional[int] = None
    output: str = ""
    error: str = ""
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "exit_code": self.exit_code,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class CodeExecutor:
    """代码执行器"""
    
    # 超时选项（秒）
    TIMEOUT_OPTIONS = {
        "1min": 60,
        "5min": 300,
        "30min": 1800,
        "unlimited": None  # 无限制
    }
    
    # 默认超时
    DEFAULT_TIMEOUT = "5min"
    
    # 最大输出长度（字节）
    MAX_OUTPUT_SIZE = 100 * 1024  # 100KB
    
    def __init__(self):
        """初始化执行器"""
        # 存储正在运行的进程 {user_id: process}
        self._running_processes: Dict[int, subprocess.Popen] = {}
        self._lock = threading.Lock()
    
    def execute(
        self,
        user_id: int,
        project_path: str,
        file_path: str,
        timeout: str = DEFAULT_TIMEOUT,
        python_path: str = None
    ) -> ExecutionResult:
        """
        同步执行 Python 脚本
        
        Args:
            user_id: 用户ID（用于并发控制）
            project_path: 项目绝对路径
            file_path: 相对于项目的文件路径
            timeout: 超时设置
            python_path: Python 解释器路径（可选）
            
        Returns:
            ExecutionResult
        """
        # 检查并发限制
        with self._lock:
            if user_id in self._running_processes:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error="已有正在运行的进程，请先停止"
                )
        
        # 验证文件
        full_path = os.path.join(project_path, file_path)
        if not os.path.isfile(full_path):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=f"文件不存在: {file_path}"
            )
        
        if not file_path.endswith('.py'):
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error="只能执行 .py 文件"
            )
        
        # 确定 Python 路径
        if not python_path:
            python_path = sys.executable
        
        # 获取超时时间
        timeout_sec = self.TIMEOUT_OPTIONS.get(timeout)
        
        # 记录开始时间
        start_time = datetime.now()
        
        try:
            # 创建子进程
            process = subprocess.Popen(
                [python_path, file_path],
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # 行缓冲
                env={**os.environ, "PYTHONUNBUFFERED": "1"}  # 禁用缓冲
            )
            
            # 注册进程
            with self._lock:
                self._running_processes[user_id] = process
            
            try:
                # 等待完成
                stdout, stderr = process.communicate(timeout=timeout_sec)
                
                # 计算耗时
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # 截断输出
                if len(stdout) > self.MAX_OUTPUT_SIZE:
                    stdout = stdout[:self.MAX_OUTPUT_SIZE] + "\n... [输出被截断]"
                if len(stderr) > self.MAX_OUTPUT_SIZE:
                    stderr = stderr[:self.MAX_OUTPUT_SIZE] + "\n... [输出被截断]"
                
                return ExecutionResult(
                    status=ExecutionStatus.COMPLETED if process.returncode == 0 else ExecutionStatus.FAILED,
                    exit_code=process.returncode,
                    output=stdout,
                    error=stderr,
                    duration_ms=duration_ms
                )
                
            except subprocess.TimeoutExpired:
                # 超时，终止进程
                process.kill()
                process.wait()
                
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    exit_code=-1,
                    error=f"执行超时（{timeout}）",
                    duration_ms=duration_ms
                )
                
        except Exception as e:
            logging.error(f"Execution error: {e}")
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(e)
            )
        finally:
            # 清理进程记录
            with self._lock:
                if user_id in self._running_processes:
                    del self._running_processes[user_id]
    
    def execute_stream(
        self,
        user_id: int,
        project_path: str,
        file_path: str,
        timeout: str = DEFAULT_TIMEOUT,
        python_path: str = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        流式执行 Python 脚本
        
        Yields:
            字典格式的事件:
            - {"type": "start", "command": "..."}
            - {"type": "stdout", "data": "..."}
            - {"type": "stderr", "data": "..."}
            - {"type": "done", "exit_code": 0, "duration_ms": 123}
            - {"type": "error", "message": "..."}
        """
        # 检查并发限制
        with self._lock:
            if user_id in self._running_processes:
                yield {"type": "error", "message": "已有正在运行的进程，请先停止"}
                return
        
        # 验证文件
        full_path = os.path.join(project_path, file_path)
        if not os.path.isfile(full_path):
            yield {"type": "error", "message": f"文件不存在: {file_path}"}
            return
        
        if not file_path.endswith('.py'):
            yield {"type": "error", "message": "只能执行 .py 文件"}
            return
        
        # 确定 Python 路径
        if not python_path:
            python_path = sys.executable
        
        # 获取超时时间
        timeout_sec = self.TIMEOUT_OPTIONS.get(timeout)
        
        # 记录开始时间
        start_time = datetime.now()
        command = f"python {file_path}"
        
        yield {"type": "start", "command": command}
        
        try:
            # 创建子进程
            process = subprocess.Popen(
                [python_path, file_path],
                cwd=project_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )
            
            # 注册进程
            with self._lock:
                self._running_processes[user_id] = process
            
            # 用于收集输出
            output_size = 0
            truncated = False
            
            # 使用线程读取 stderr
            stderr_output = []
            def read_stderr():
                for line in process.stderr:
                    stderr_output.append(line)
            
            stderr_thread = threading.Thread(target=read_stderr)
            stderr_thread.start()
            
            try:
                # 流式读取 stdout
                for line in process.stdout:
                    # 检查是否被停止
                    with self._lock:
                        if user_id not in self._running_processes:
                            yield {"type": "stopped", "message": "执行已停止"}
                            return
                    
                    # 检查超时
                    if timeout_sec:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        if elapsed > timeout_sec:
                            process.kill()
                            yield {"type": "timeout", "message": f"执行超时（{timeout}）"}
                            return
                    
                    # 检查输出大小
                    output_size += len(line.encode('utf-8'))
                    if output_size > self.MAX_OUTPUT_SIZE:
                        if not truncated:
                            yield {"type": "stdout", "data": "... [输出被截断]\n"}
                            truncated = True
                        continue
                    
                    yield {"type": "stdout", "data": line}
                
                # 等待进程结束
                process.wait()
                stderr_thread.join(timeout=5)
                
                # 输出 stderr
                for line in stderr_output:
                    yield {"type": "stderr", "data": line}
                
                # 计算耗时
                duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                yield {
                    "type": "done",
                    "exit_code": process.returncode,
                    "duration_ms": duration_ms,
                    "success": process.returncode == 0
                }
                
            except Exception as e:
                process.kill()
                yield {"type": "error", "message": str(e)}
                
        except Exception as e:
            logging.error(f"Execution error: {e}")
            yield {"type": "error", "message": str(e)}
        finally:
            # 清理进程记录
            with self._lock:
                if user_id in self._running_processes:
                    del self._running_processes[user_id]
    
    def stop(self, user_id: int) -> bool:
        """
        停止用户正在执行的进程
        
        Args:
            user_id: 用户ID
            
        Returns:
            是否成功停止
        """
        with self._lock:
            if user_id not in self._running_processes:
                return False
            
            process = self._running_processes[user_id]
            try:
                process.terminate()
                # 给进程一点时间优雅退出
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                
                del self._running_processes[user_id]
                logging.info(f"Stopped execution for user {user_id}")
                return True
            except Exception as e:
                logging.error(f"Error stopping process: {e}")
                return False
    
    def is_running(self, user_id: int) -> bool:
        """检查用户是否有正在运行的进程"""
        with self._lock:
            return user_id in self._running_processes
    
    def get_running_info(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取运行中进程的信息"""
        with self._lock:
            if user_id not in self._running_processes:
                return None
            
            process = self._running_processes[user_id]
            return {
                "pid": process.pid,
                "status": "running"
            }


# 全局执行器实例
executor = CodeExecutor()

