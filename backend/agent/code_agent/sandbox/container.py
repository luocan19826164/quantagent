"""
Docker 容器管理
负责容器的生命周期管理
"""

import os
import logging
import time
import threading
from enum import Enum
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

try:
    import docker
    from docker.errors import DockerException, NotFound, APIError
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None
    DockerException = Exception
    NotFound = Exception
    APIError = Exception


class ContainerStatus(Enum):
    """容器状态"""
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    NOT_FOUND = "not_found"


@dataclass
class ContainerConfig:
    """容器配置"""
    # 基础镜像
    image: str = "python:3.11-slim"
    
    # 资源限制
    memory_limit: str = "512m"      # 内存限制
    cpu_quota: int = 50000          # CPU 配额 (50% of one core)
    cpu_period: int = 100000        # CPU 周期
    
    # 网络配置
    network_mode: str = "none"      # 默认禁用网络
    
    # 超时设置
    execution_timeout: int = 300    # 执行超时（秒）
    idle_timeout: int = 600         # 空闲超时（秒）
    
    # 工作目录
    working_dir: str = "/workspace"
    
    # 环境变量
    environment: Dict[str, str] = field(default_factory=dict)
    
    # 额外挂载
    extra_mounts: List[Dict] = field(default_factory=list)
    
    # 安全配置
    read_only_root: bool = False    # 根文件系统只读
    no_new_privileges: bool = True  # 禁止获取新权限
    
    def to_docker_config(self) -> Dict[str, Any]:
        """转换为 Docker API 配置"""
        config = {
            "image": self.image,
            "mem_limit": self.memory_limit,
            "cpu_quota": self.cpu_quota,
            "cpu_period": self.cpu_period,
            "network_mode": self.network_mode,
            "working_dir": self.working_dir,
            "environment": self.environment,
            "detach": True,
            "tty": True,
            "stdin_open": True,
        }
        
        # 安全选项
        security_opt = []
        if self.no_new_privileges:
            security_opt.append("no-new-privileges:true")
        if security_opt:
            config["security_opt"] = security_opt
        
        if self.read_only_root:
            config["read_only"] = True
        
        return config


@dataclass
class ContainerInfo:
    """容器信息"""
    container_id: str
    name: str
    status: ContainerStatus
    created_at: datetime
    last_used_at: datetime
    user_id: int
    project_id: str
    workspace_path: str
    config: ContainerConfig
    
    # 运行时信息
    exit_code: Optional[int] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "container_id": self.container_id,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat(),
            "user_id": self.user_id,
            "project_id": self.project_id,
            "exit_code": self.exit_code,
            "error_message": self.error_message,
        }


class DockerManager:
    """
    Docker 容器管理器
    
    功能:
    1. 容器生命周期管理（创建、启动、停止、删除）
    2. 资源限制和监控
    3. 自动清理空闲容器
    4. 容器池管理
    """
    
    CONTAINER_PREFIX = "quantagent_sandbox_"
    
    def __init__(self, 
                 workspaces_root: str = "./workspaces",
                 max_containers_per_user: int = 3,
                 cleanup_interval: int = 60):
        """
        初始化 Docker 管理器
        
        Args:
            workspaces_root: 工作区根目录
            max_containers_per_user: 每用户最大容器数
            cleanup_interval: 清理检查间隔（秒）
        """
        self.workspaces_root = os.path.abspath(workspaces_root)
        self.max_containers_per_user = max_containers_per_user
        self.cleanup_interval = cleanup_interval
        
        # 容器追踪
        self._containers: Dict[str, ContainerInfo] = {}
        self._lock = threading.Lock()
        
        # Docker 客户端
        self._client: Optional[Any] = None
        self._initialized = False
        
        # 清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()
        
        logging.info(f"DockerManager initialized with workspaces_root={workspaces_root}")
    
    def initialize(self) -> bool:
        """
        初始化 Docker 连接
        
        Returns:
            是否成功初始化
        """
        if not DOCKER_AVAILABLE:
            logging.error("Docker SDK not installed. Run: pip install docker")
            return False
        
        try:
            self._client = docker.from_env()
            # 测试连接
            self._client.ping()
            self._initialized = True
            
            # 启动清理线程
            self._start_cleanup_thread()
            
            logging.info("Docker connection established")
            return True
            
        except DockerException as e:
            logging.error(f"Failed to connect to Docker: {e}")
            return False
    
    def is_available(self) -> bool:
        """检查 Docker 是否可用"""
        if not self._initialized:
            return self.initialize()
        
        try:
            self._client.ping()
            return True
        except:
            self._initialized = False
            return False
    
    def create_container(self, 
                        user_id: int,
                        project_id: str,
                        config: Optional[ContainerConfig] = None) -> Optional[ContainerInfo]:
        """
        创建容器
        
        Args:
            user_id: 用户ID
            project_id: 项目ID
            config: 容器配置
            
        Returns:
            ContainerInfo 或 None
        """
        if not self.is_available():
            logging.error("Docker not available")
            return None
        
        config = config or ContainerConfig()
        
        # 检查用户容器数量限制
        user_containers = self.get_user_containers(user_id)
        if len(user_containers) >= self.max_containers_per_user:
            logging.warning(f"User {user_id} has reached max containers limit")
            # 尝试清理空闲容器
            self._cleanup_idle_containers(user_id)
            
            user_containers = self.get_user_containers(user_id)
            if len(user_containers) >= self.max_containers_per_user:
                return None
        
        # 准备工作区路径
        workspace_path = os.path.join(self.workspaces_root, str(user_id), project_id)
        os.makedirs(workspace_path, exist_ok=True)
        
        # 容器名称
        container_name = f"{self.CONTAINER_PREFIX}{user_id}_{project_id}_{int(time.time())}"
        
        try:
            # Docker 配置
            docker_config = config.to_docker_config()
            docker_config["name"] = container_name
            
            # 挂载工作区
            docker_config["volumes"] = {
                workspace_path: {
                    "bind": config.working_dir,
                    "mode": "rw"
                }
            }
            
            # 添加额外挂载
            for mount in config.extra_mounts:
                docker_config["volumes"][mount["source"]] = {
                    "bind": mount["target"],
                    "mode": mount.get("mode", "ro")
                }
            
            # 创建容器
            container = self._client.containers.create(**docker_config)
            
            # 创建容器信息
            now = datetime.now()
            info = ContainerInfo(
                container_id=container.id,
                name=container_name,
                status=ContainerStatus.CREATING,
                created_at=now,
                last_used_at=now,
                user_id=user_id,
                project_id=project_id,
                workspace_path=workspace_path,
                config=config
            )
            
            with self._lock:
                self._containers[container.id] = info
            
            logging.info(f"Container created: {container_name} ({container.id[:12]})")
            return info
            
        except DockerException as e:
            logging.error(f"Failed to create container: {e}")
            return None
    
    def start_container(self, container_id: str) -> bool:
        """启动容器"""
        if not self.is_available():
            return False
        
        try:
            container = self._client.containers.get(container_id)
            container.start()
            
            with self._lock:
                if container_id in self._containers:
                    self._containers[container_id].status = ContainerStatus.RUNNING
                    self._containers[container_id].last_used_at = datetime.now()
            
            logging.info(f"Container started: {container_id[:12]}")
            return True
            
        except NotFound:
            logging.error(f"Container not found: {container_id}")
            with self._lock:
                if container_id in self._containers:
                    self._containers[container_id].status = ContainerStatus.NOT_FOUND
            return False
            
        except DockerException as e:
            logging.error(f"Failed to start container: {e}")
            return False
    
    def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """停止容器"""
        if not self.is_available():
            return False
        
        try:
            container = self._client.containers.get(container_id)
            container.stop(timeout=timeout)
            
            with self._lock:
                if container_id in self._containers:
                    self._containers[container_id].status = ContainerStatus.STOPPED
            
            logging.info(f"Container stopped: {container_id[:12]}")
            return True
            
        except NotFound:
            return True  # 已经不存在
            
        except DockerException as e:
            logging.error(f"Failed to stop container: {e}")
            return False
    
    def remove_container(self, container_id: str, force: bool = False) -> bool:
        """删除容器"""
        if not self.is_available():
            return False
        
        try:
            container = self._client.containers.get(container_id)
            container.remove(force=force)
            
            with self._lock:
                if container_id in self._containers:
                    del self._containers[container_id]
            
            logging.info(f"Container removed: {container_id[:12]}")
            return True
            
        except NotFound:
            with self._lock:
                if container_id in self._containers:
                    del self._containers[container_id]
            return True
            
        except DockerException as e:
            logging.error(f"Failed to remove container: {e}")
            return False
    
    def get_container_status(self, container_id: str) -> ContainerStatus:
        """获取容器状态"""
        if not self.is_available():
            return ContainerStatus.ERROR
        
        try:
            container = self._client.containers.get(container_id)
            status_map = {
                "created": ContainerStatus.CREATING,
                "running": ContainerStatus.RUNNING,
                "paused": ContainerStatus.PAUSED,
                "exited": ContainerStatus.STOPPED,
                "dead": ContainerStatus.ERROR,
            }
            return status_map.get(container.status, ContainerStatus.ERROR)
            
        except NotFound:
            return ContainerStatus.NOT_FOUND
            
        except DockerException:
            return ContainerStatus.ERROR
    
    def get_container_info(self, container_id: str) -> Optional[ContainerInfo]:
        """获取容器信息"""
        with self._lock:
            info = self._containers.get(container_id)
            if info:
                # 更新实时状态
                info.status = self.get_container_status(container_id)
            return info
    
    def get_user_containers(self, user_id: int) -> List[ContainerInfo]:
        """获取用户的所有容器"""
        with self._lock:
            return [c for c in self._containers.values() if c.user_id == user_id]
    
    def get_project_container(self, user_id: int, project_id: str) -> Optional[ContainerInfo]:
        """获取项目的容器"""
        with self._lock:
            for info in self._containers.values():
                if info.user_id == user_id and info.project_id == project_id:
                    info.status = self.get_container_status(info.container_id)
                    return info
            return None
    
    def ensure_container(self, 
                        user_id: int,
                        project_id: str,
                        config: Optional[ContainerConfig] = None) -> Optional[ContainerInfo]:
        """
        确保容器存在并运行
        
        如果容器不存在则创建，如果存在但未运行则启动
        """
        # 查找现有容器
        info = self.get_project_container(user_id, project_id)
        
        if info:
            # 检查状态
            if info.status == ContainerStatus.RUNNING:
                info.last_used_at = datetime.now()
                return info
            elif info.status in (ContainerStatus.STOPPED, ContainerStatus.PAUSED):
                if self.start_container(info.container_id):
                    return self.get_container_info(info.container_id)
            elif info.status in (ContainerStatus.NOT_FOUND, ContainerStatus.ERROR):
                # 删除无效记录，重新创建
                self.remove_container(info.container_id, force=True)
        
        # 创建新容器
        info = self.create_container(user_id, project_id, config)
        if info:
            self.start_container(info.container_id)
            return self.get_container_info(info.container_id)
        
        return None
    
    def exec_in_container(self, 
                         container_id: str,
                         command: str,
                         timeout: Optional[int] = None,
                         workdir: Optional[str] = None,
                         environment: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        在容器中执行命令
        
        Args:
            container_id: 容器ID
            command: 要执行的命令
            timeout: 超时时间（秒）
            workdir: 工作目录
            environment: 环境变量
            
        Returns:
            执行结果字典
        """
        if not self.is_available():
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Docker not available",
                "timed_out": False
            }
        
        try:
            container = self._client.containers.get(container_id)
            
            # 检查容器状态
            if container.status != "running":
                container.start()
                time.sleep(0.5)  # 等待启动
            
            # 更新最后使用时间
            with self._lock:
                if container_id in self._containers:
                    self._containers[container_id].last_used_at = datetime.now()
            
            # 执行命令
            exec_config = {
                "cmd": ["sh", "-c", command],
                "stdout": True,
                "stderr": True,
                "stream": False,
            }
            if workdir:
                exec_config["workdir"] = workdir
            if environment:
                exec_config["environment"] = environment
            
            # 使用超时包装
            result = {"success": False, "exit_code": -1, "stdout": "", "stderr": "", "timed_out": False}
            
            def run_exec():
                nonlocal result
                try:
                    exit_code, output = container.exec_run(**exec_config)
                    
                    # 解析输出
                    if isinstance(output, bytes):
                        output = output.decode('utf-8', errors='replace')
                    
                    result = {
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "stdout": output,
                        "stderr": "",
                        "timed_out": False
                    }
                except Exception as e:
                    result = {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": str(e),
                        "timed_out": False
                    }
            
            # 获取配置的超时时间
            info = self._containers.get(container_id)
            effective_timeout = timeout or (info.config.execution_timeout if info else 300)
            
            thread = threading.Thread(target=run_exec)
            thread.start()
            thread.join(timeout=effective_timeout)
            
            if thread.is_alive():
                # 超时，尝试终止
                result = {
                    "success": False,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Execution timed out after {effective_timeout}s",
                    "timed_out": True
                }
                # 注意：这里不能直接终止正在执行的命令
                # 可能需要停止并重启容器
            
            return result
            
        except NotFound:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Container not found",
                "timed_out": False
            }
            
        except DockerException as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "timed_out": False
            }
    
    def get_container_logs(self, 
                          container_id: str,
                          tail: int = 100,
                          since: Optional[datetime] = None) -> str:
        """获取容器日志"""
        if not self.is_available():
            return ""
        
        try:
            container = self._client.containers.get(container_id)
            logs = container.logs(
                tail=tail,
                since=since,
                timestamps=True
            )
            return logs.decode('utf-8', errors='replace')
            
        except (NotFound, DockerException):
            return ""
    
    def get_container_stats(self, container_id: str) -> Dict[str, Any]:
        """获取容器资源使用统计"""
        if not self.is_available():
            return {}
        
        try:
            container = self._client.containers.get(container_id)
            stats = container.stats(stream=False)
            
            # 解析统计信息
            memory_stats = stats.get("memory_stats", {})
            cpu_stats = stats.get("cpu_stats", {})
            
            return {
                "memory_usage": memory_stats.get("usage", 0),
                "memory_limit": memory_stats.get("limit", 0),
                "cpu_percent": self._calculate_cpu_percent(stats),
                "network_rx": stats.get("networks", {}).get("eth0", {}).get("rx_bytes", 0),
                "network_tx": stats.get("networks", {}).get("eth0", {}).get("tx_bytes", 0),
            }
            
        except (NotFound, DockerException):
            return {}
    
    def _calculate_cpu_percent(self, stats: Dict) -> float:
        """计算 CPU 使用百分比"""
        try:
            cpu_delta = (stats["cpu_stats"]["cpu_usage"]["total_usage"] - 
                        stats["precpu_stats"]["cpu_usage"]["total_usage"])
            system_delta = (stats["cpu_stats"]["system_cpu_usage"] - 
                           stats["precpu_stats"]["system_cpu_usage"])
            
            if system_delta > 0 and cpu_delta > 0:
                cpu_count = len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
                return (cpu_delta / system_delta) * cpu_count * 100.0
        except (KeyError, ZeroDivisionError):
            pass
        return 0.0
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        
        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True
        )
        self._cleanup_thread.start()
    
    def _cleanup_loop(self):
        """清理循环"""
        while not self._stop_cleanup.is_set():
            try:
                self._cleanup_idle_containers()
            except Exception as e:
                logging.error(f"Cleanup error: {e}")
            
            self._stop_cleanup.wait(self.cleanup_interval)
    
    def _cleanup_idle_containers(self, user_id: Optional[int] = None):
        """清理空闲容器"""
        now = datetime.now()
        to_remove = []
        
        with self._lock:
            for cid, info in self._containers.items():
                # 过滤用户
                if user_id is not None and info.user_id != user_id:
                    continue
                
                # 检查空闲时间
                idle_time = (now - info.last_used_at).total_seconds()
                if idle_time > info.config.idle_timeout:
                    to_remove.append(cid)
        
        for cid in to_remove:
            logging.info(f"Cleaning up idle container: {cid[:12]}")
            self.stop_container(cid)
            self.remove_container(cid)
    
    def cleanup_all(self, user_id: Optional[int] = None):
        """清理所有容器（或指定用户的容器）"""
        with self._lock:
            container_ids = [
                cid for cid, info in self._containers.items()
                if user_id is None or info.user_id == user_id
            ]
        
        for cid in container_ids:
            self.stop_container(cid)
            self.remove_container(cid, force=True)
    
    def shutdown(self):
        """关闭管理器"""
        logging.info("Shutting down DockerManager...")
        
        # 停止清理线程
        self._stop_cleanup.set()
        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
        
        # 清理所有容器
        self.cleanup_all()
        
        logging.info("DockerManager shutdown complete")

