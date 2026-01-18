"""
Docker 沙箱详细测试
包含单元测试、Mock 测试和集成测试
"""

import pytest
import sys
import os
import time
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch, PropertyMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.sandbox.container import (
    ContainerConfig,
    ContainerStatus,
    ContainerInfo,
    DockerManager,
    DOCKER_AVAILABLE
)
from agent.code_agent.sandbox.executor import (
    ExecutionConfig,
    ExecutionResult,
    ExecutionStatus,
    SandboxExecutor
)


# ============ Fixtures ============

@pytest.fixture
def temp_workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_docker_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_docker_client():
    """Mock Docker 客户端"""
    with patch('agent.code_agent.sandbox.container.docker') as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.ping.return_value = True
        yield mock_client


@pytest.fixture
def docker_manager(temp_workspace, mock_docker_client):
    """创建带 Mock 的 DockerManager"""
    manager = DockerManager(
        workspaces_root=temp_workspace,
        max_containers_per_user=3,
        cleanup_interval=3600  # 禁用自动清理
    )
    manager._client = mock_docker_client
    manager._initialized = True
    return manager


# ============ ContainerConfig 测试 ============

class TestContainerConfig:
    """测试容器配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ContainerConfig()
        
        assert config.image == "python:3.11-slim"
        assert config.memory_limit == "512m"
        assert config.network_mode == "none"
        assert config.execution_timeout == 300
        assert config.no_new_privileges is True
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ContainerConfig(
            image="python:3.12-slim",
            memory_limit="1g",
            cpu_quota=100000,
            network_mode="bridge",
            execution_timeout=600,
            environment={"DEBUG": "1"}
        )
        
        assert config.image == "python:3.12-slim"
        assert config.memory_limit == "1g"
        assert config.cpu_quota == 100000
        assert config.network_mode == "bridge"
        assert config.environment["DEBUG"] == "1"
    
    def test_to_docker_config(self):
        """测试转换为 Docker API 配置"""
        config = ContainerConfig(
            image="python:3.11-slim",
            memory_limit="512m",
            cpu_quota=50000,
            environment={"KEY": "value"}
        )
        
        docker_config = config.to_docker_config()
        
        assert docker_config["image"] == "python:3.11-slim"
        assert docker_config["mem_limit"] == "512m"
        assert docker_config["cpu_quota"] == 50000
        assert docker_config["environment"]["KEY"] == "value"
        assert docker_config["detach"] is True
        assert "security_opt" in docker_config
    
    def test_security_options(self):
        """测试安全选项"""
        config = ContainerConfig(
            no_new_privileges=True,
            read_only_root=True
        )
        
        docker_config = config.to_docker_config()
        
        assert "no-new-privileges:true" in docker_config["security_opt"]
        assert docker_config["read_only"] is True
    
    def test_network_disabled_by_default(self):
        """测试默认禁用网络"""
        config = ContainerConfig()
        docker_config = config.to_docker_config()
        
        assert docker_config["network_mode"] == "none"


# ============ ContainerInfo 测试 ============

class TestContainerInfo:
    """测试容器信息"""
    
    def test_create_info(self):
        """测试创建容器信息"""
        now = datetime.now()
        info = ContainerInfo(
            container_id="abc123",
            name="test_container",
            status=ContainerStatus.RUNNING,
            created_at=now,
            last_used_at=now,
            user_id=1,
            project_id="proj1",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        assert info.container_id == "abc123"
        assert info.status == ContainerStatus.RUNNING
        assert info.user_id == 1
    
    def test_to_dict(self):
        """测试转换为字典"""
        now = datetime.now()
        info = ContainerInfo(
            container_id="abc123",
            name="test_container",
            status=ContainerStatus.RUNNING,
            created_at=now,
            last_used_at=now,
            user_id=1,
            project_id="proj1",
            workspace_path="/workspace",
            config=ContainerConfig(),
            exit_code=0
        )
        
        d = info.to_dict()
        
        assert d["container_id"] == "abc123"
        assert d["status"] == "running"
        assert d["user_id"] == 1
        assert d["exit_code"] == 0


# ============ DockerManager 单元测试 ============

class TestDockerManagerUnit:
    """DockerManager 单元测试（使用 Mock）"""
    
    def test_initialization(self, temp_workspace):
        """测试初始化"""
        manager = DockerManager(
            workspaces_root=temp_workspace,
            max_containers_per_user=5
        )
        
        assert manager.workspaces_root == os.path.abspath(temp_workspace)
        assert manager.max_containers_per_user == 5
        assert manager._initialized is False
    
    def test_is_available_without_docker(self, temp_workspace):
        """测试 Docker 不可用时"""
        with patch('agent.code_agent.sandbox.container.DOCKER_AVAILABLE', False):
            manager = DockerManager(workspaces_root=temp_workspace)
            assert manager.initialize() is False
    
    def test_is_available_with_mock(self, docker_manager, mock_docker_client):
        """测试 Docker 可用"""
        assert docker_manager.is_available() is True
        mock_docker_client.ping.assert_called()
    
    def test_create_container_success(self, docker_manager, mock_docker_client, temp_workspace):
        """测试成功创建容器"""
        # 设置 Mock 返回值
        mock_container = MagicMock()
        mock_container.id = "container_123"
        mock_docker_client.containers.create.return_value = mock_container
        
        info = docker_manager.create_container(
            user_id=1,
            project_id="test_project"
        )
        
        assert info is not None
        assert info.container_id == "container_123"
        assert info.user_id == 1
        assert info.project_id == "test_project"
        assert info.status == ContainerStatus.CREATING
        
        # 验证工作区目录被创建
        workspace_path = os.path.join(temp_workspace, "1", "test_project")
        assert os.path.exists(workspace_path)
    
    def test_create_container_with_custom_config(self, docker_manager, mock_docker_client):
        """测试使用自定义配置创建容器"""
        mock_container = MagicMock()
        mock_container.id = "container_456"
        mock_docker_client.containers.create.return_value = mock_container
        
        config = ContainerConfig(
            image="python:3.12-slim",
            memory_limit="1g",
            network_mode="bridge"
        )
        
        info = docker_manager.create_container(
            user_id=1,
            project_id="proj",
            config=config
        )
        
        assert info is not None
        assert info.config.image == "python:3.12-slim"
        assert info.config.memory_limit == "1g"
        
        # 验证 Docker API 调用参数
        call_kwargs = mock_docker_client.containers.create.call_args[1]
        assert call_kwargs["image"] == "python:3.12-slim"
        assert call_kwargs["mem_limit"] == "1g"
    
    def test_create_container_exceeds_limit(self, docker_manager, mock_docker_client):
        """测试超出用户容器限制"""
        docker_manager.max_containers_per_user = 2
        
        # 创建 Mock 容器
        for i in range(2):
            mock_container = MagicMock()
            mock_container.id = f"container_{i}"
            mock_docker_client.containers.create.return_value = mock_container
            docker_manager.create_container(user_id=1, project_id=f"proj_{i}")
        
        # 第三个应该失败
        mock_container = MagicMock()
        mock_container.id = "container_3"
        mock_docker_client.containers.create.return_value = mock_container
        
        info = docker_manager.create_container(user_id=1, project_id="proj_3")
        
        # 应该返回 None（除非清理了旧容器）
        # 这里因为没有空闲容器可清理，所以返回 None
        assert info is None
    
    def test_start_container_success(self, docker_manager, mock_docker_client):
        """测试成功启动容器"""
        # 先创建容器
        mock_container = MagicMock()
        mock_container.id = "container_start"
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        docker_manager.create_container(user_id=1, project_id="proj")
        
        result = docker_manager.start_container("container_start")
        
        assert result is True
        mock_container.start.assert_called_once()
    
    def test_start_container_not_found(self, docker_manager, mock_docker_client):
        """测试启动不存在的容器"""
        from agent.code_agent.sandbox.container import NotFound
        mock_docker_client.containers.get.side_effect = NotFound("Not found")
        
        result = docker_manager.start_container("nonexistent")
        
        assert result is False
    
    def test_stop_container_success(self, docker_manager, mock_docker_client):
        """测试成功停止容器"""
        mock_container = MagicMock()
        mock_container.id = "container_stop"
        mock_docker_client.containers.get.return_value = mock_container
        
        # 先添加到追踪
        docker_manager._containers["container_stop"] = ContainerInfo(
            container_id="container_stop",
            name="test",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        result = docker_manager.stop_container("container_stop")
        
        assert result is True
        mock_container.stop.assert_called_once()
        assert docker_manager._containers["container_stop"].status == ContainerStatus.STOPPED
    
    def test_remove_container_success(self, docker_manager, mock_docker_client):
        """测试成功删除容器"""
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container
        
        # 先添加到追踪
        docker_manager._containers["container_rm"] = ContainerInfo(
            container_id="container_rm",
            name="test",
            status=ContainerStatus.STOPPED,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        result = docker_manager.remove_container("container_rm")
        
        assert result is True
        mock_container.remove.assert_called_once()
        assert "container_rm" not in docker_manager._containers
    
    def test_get_container_status(self, docker_manager, mock_docker_client):
        """测试获取容器状态"""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container
        
        status = docker_manager.get_container_status("container_id")
        
        assert status == ContainerStatus.RUNNING
    
    def test_get_container_status_mapping(self, docker_manager, mock_docker_client):
        """测试各种容器状态映射"""
        status_tests = [
            ("created", ContainerStatus.CREATING),
            ("running", ContainerStatus.RUNNING),
            ("paused", ContainerStatus.PAUSED),
            ("exited", ContainerStatus.STOPPED),
            ("dead", ContainerStatus.ERROR),
        ]
        
        for docker_status, expected_status in status_tests:
            mock_container = MagicMock()
            mock_container.status = docker_status
            mock_docker_client.containers.get.return_value = mock_container
            
            status = docker_manager.get_container_status("container_id")
            assert status == expected_status, f"Failed for {docker_status}"
    
    def test_get_user_containers(self, docker_manager, mock_docker_client):
        """测试获取用户的所有容器"""
        # 创建多个容器
        for i, user_id in enumerate([1, 1, 2]):
            mock_container = MagicMock()
            mock_container.id = f"container_{i}"
            mock_docker_client.containers.create.return_value = mock_container
            docker_manager.create_container(user_id=user_id, project_id=f"proj_{i}")
        
        user1_containers = docker_manager.get_user_containers(1)
        user2_containers = docker_manager.get_user_containers(2)
        
        assert len(user1_containers) == 2
        assert len(user2_containers) == 1
    
    def test_exec_in_container_success(self, docker_manager, mock_docker_client):
        """测试在容器中执行命令"""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.exec_run.return_value = (0, b"Hello World\n")
        mock_docker_client.containers.get.return_value = mock_container
        
        # 添加容器到追踪
        docker_manager._containers["container_exec"] = ContainerInfo(
            container_id="container_exec",
            name="test",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        result = docker_manager.exec_in_container(
            "container_exec",
            "echo 'Hello World'"
        )
        
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "Hello World" in result["stdout"]
    
    def test_exec_in_container_failure(self, docker_manager, mock_docker_client):
        """测试命令执行失败"""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_container.exec_run.return_value = (1, b"Error: command not found\n")
        mock_docker_client.containers.get.return_value = mock_container
        
        docker_manager._containers["container_fail"] = ContainerInfo(
            container_id="container_fail",
            name="test",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        result = docker_manager.exec_in_container(
            "container_fail",
            "invalid_command"
        )
        
        assert result["success"] is False
        assert result["exit_code"] == 1
    
    def test_exec_starts_stopped_container(self, docker_manager, mock_docker_client):
        """测试执行时自动启动已停止的容器"""
        mock_container = MagicMock()
        mock_container.status = "exited"  # 容器已停止
        mock_container.exec_run.return_value = (0, b"OK")
        mock_docker_client.containers.get.return_value = mock_container
        
        docker_manager._containers["container_stopped"] = ContainerInfo(
            container_id="container_stopped",
            name="test",
            status=ContainerStatus.STOPPED,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        docker_manager.exec_in_container("container_stopped", "echo test")
        
        mock_container.start.assert_called_once()


# ============ DockerManager 清理测试 ============

class TestDockerManagerCleanup:
    """测试容器清理功能"""
    
    def test_cleanup_idle_containers(self, docker_manager, mock_docker_client):
        """测试清理空闲容器"""
        # 创建一个"旧"容器
        old_time = datetime.now() - timedelta(hours=2)
        docker_manager._containers["old_container"] = ContainerInfo(
            container_id="old_container",
            name="old",
            status=ContainerStatus.RUNNING,
            created_at=old_time,
            last_used_at=old_time,  # 2小时前使用
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig(idle_timeout=600)  # 10分钟超时
        )
        
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container
        
        docker_manager._cleanup_idle_containers()
        
        # 容器应该被清理
        assert "old_container" not in docker_manager._containers
    
    def test_cleanup_keeps_active_containers(self, docker_manager, mock_docker_client):
        """测试保留活跃容器"""
        # 创建一个"新"容器
        docker_manager._containers["new_container"] = ContainerInfo(
            container_id="new_container",
            name="new",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),  # 刚刚使用
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig(idle_timeout=600)
        )
        
        docker_manager._cleanup_idle_containers()
        
        # 容器应该保留
        assert "new_container" in docker_manager._containers
    
    def test_cleanup_all_user_containers(self, docker_manager, mock_docker_client):
        """测试清理用户的所有容器"""
        # 创建多个用户的容器
        for i, user_id in enumerate([1, 1, 2]):
            docker_manager._containers[f"container_{i}"] = ContainerInfo(
                container_id=f"container_{i}",
                name=f"test_{i}",
                status=ContainerStatus.RUNNING,
                created_at=datetime.now(),
                last_used_at=datetime.now(),
                user_id=user_id,
                project_id=f"proj_{i}",
                workspace_path="/workspace",
                config=ContainerConfig()
            )
        
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container
        
        docker_manager.cleanup_all(user_id=1)
        
        # 只有用户2的容器应该保留
        assert len(docker_manager._containers) == 1
        assert "container_2" in docker_manager._containers


# ============ DockerManager ensure_container 测试 ============

class TestDockerManagerEnsureContainer:
    """测试 ensure_container 方法"""
    
    def test_ensure_creates_new_container(self, docker_manager, mock_docker_client):
        """测试自动创建新容器"""
        mock_container = MagicMock()
        mock_container.id = "new_container"
        mock_container.status = "running"
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        info = docker_manager.ensure_container(user_id=1, project_id="proj")
        
        assert info is not None
        assert info.container_id == "new_container"
    
    def test_ensure_starts_stopped_container(self, docker_manager, mock_docker_client):
        """测试自动启动已停止的容器"""
        mock_container = MagicMock()
        mock_container.id = "stopped_container"
        # 模拟容器状态：先 exited（停止），调用 start 后变成 running
        # 使用 side_effect 来模拟状态变化
        status_sequence = ["exited", "running"]
        status_index = [0]
        
        def get_status():
            idx = min(status_index[0], len(status_sequence) - 1)
            return status_sequence[idx]
        
        def mock_start():
            status_index[0] += 1
        
        type(mock_container).status = PropertyMock(side_effect=lambda: get_status())
        mock_container.start.side_effect = mock_start
        mock_docker_client.containers.get.return_value = mock_container
        
        # 添加已停止的容器
        docker_manager._containers["stopped_container"] = ContainerInfo(
            container_id="stopped_container",
            name="test",
            status=ContainerStatus.STOPPED,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        info = docker_manager.ensure_container(user_id=1, project_id="proj")
        
        assert info is not None
        # start_container 内部会调用 container.start()
        mock_container.start.assert_called_once()
    
    def test_ensure_returns_running_container(self, docker_manager, mock_docker_client):
        """测试返回已运行的容器"""
        mock_container = MagicMock()
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container
        
        # 添加运行中的容器
        existing = ContainerInfo(
            container_id="running_container",
            name="test",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        docker_manager._containers["running_container"] = existing
        
        info = docker_manager.ensure_container(user_id=1, project_id="proj")
        
        assert info is not None
        assert info.container_id == "running_container"
        # 不应该创建新容器
        mock_docker_client.containers.create.assert_not_called()


# ============ SandboxExecutor 测试 ============

class TestSandboxExecutor:
    """测试沙箱执行器"""
    
    @pytest.fixture
    def executor(self, docker_manager):
        """创建执行器"""
        return SandboxExecutor(docker_manager)
    
    def test_execute_python_success(self, executor, docker_manager, mock_docker_client):
        """测试成功执行 Python 脚本"""
        # 设置 Mock
        mock_container = MagicMock()
        mock_container.id = "exec_container"
        mock_container.status = "running"
        mock_container.exec_run.return_value = (0, b"Script output\n")
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        result = executor.execute_python(
            user_id=1,
            project_id="proj",
            script_path="main.py"
        )
        
        assert result.status == ExecutionStatus.COMPLETED
        assert result.exit_code == 0
        assert "Script output" in result.stdout
    
    def test_execute_python_failure(self, executor, docker_manager, mock_docker_client):
        """测试 Python 执行失败"""
        mock_container = MagicMock()
        mock_container.id = "fail_container"
        mock_container.status = "running"
        mock_container.exec_run.return_value = (1, b"SyntaxError: invalid syntax\n")
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        result = executor.execute_python(
            user_id=1,
            project_id="proj",
            script_path="broken.py"
        )
        
        assert result.status == ExecutionStatus.FAILED
        assert result.exit_code == 1
    
    def test_execute_command(self, executor, docker_manager, mock_docker_client):
        """测试执行 Shell 命令"""
        mock_container = MagicMock()
        mock_container.id = "cmd_container"
        mock_container.status = "running"
        mock_container.exec_run.return_value = (0, b"file1.py\nfile2.py\n")
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        result = executor.execute_command(
            user_id=1,
            project_id="proj",
            command="ls *.py"
        )
        
        assert result.status == ExecutionStatus.COMPLETED
        assert "file1.py" in result.stdout
    
    def test_install_packages(self, executor, docker_manager, mock_docker_client):
        """测试安装 Python 包"""
        mock_container = MagicMock()
        mock_container.id = "pip_container"
        mock_container.status = "running"
        mock_container.exec_run.return_value = (0, b"Successfully installed pandas\n")
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        result = executor.install_packages(
            user_id=1,
            project_id="proj",
            packages=["pandas", "numpy"]
        )
        
        assert result.status == ExecutionStatus.COMPLETED
        assert "Successfully installed" in result.stdout
    
    def test_execution_timeout(self, executor, docker_manager, mock_docker_client):
        """测试执行超时"""
        mock_container = MagicMock()
        mock_container.id = "timeout_container"
        mock_container.status = "running"
        
        # 模拟超时返回
        docker_manager._containers["timeout_container"] = ContainerInfo(
            container_id="timeout_container",
            name="test",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig(execution_timeout=1)
        )
        
        # 直接返回超时结果
        with patch.object(docker_manager, 'exec_in_container') as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Execution timed out after 1s",
                "timed_out": True
            }
            with patch.object(docker_manager, 'ensure_container') as mock_ensure:
                mock_ensure.return_value = docker_manager._containers["timeout_container"]
                
                config = ExecutionConfig(timeout=1)
                result = executor.execute_command(
                    user_id=1,
                    project_id="proj",
                    command="sleep 10",
                    config=config
                )
        
        assert result.status == ExecutionStatus.TIMEOUT
    
    def test_cancel_execution(self, executor, docker_manager, mock_docker_client):
        """测试取消执行"""
        mock_container = MagicMock()
        mock_docker_client.containers.get.return_value = mock_container
        
        docker_manager._containers["cancel_container"] = ContainerInfo(
            container_id="cancel_container",
            name="test",
            status=ContainerStatus.RUNNING,
            created_at=datetime.now(),
            last_used_at=datetime.now(),
            user_id=1,
            project_id="proj",
            workspace_path="/workspace",
            config=ContainerConfig()
        )
        
        result = executor.cancel_execution(user_id=1, project_id="proj")
        
        assert result is True
        mock_container.stop.assert_called()
    
    def test_execution_result_duration(self, executor, docker_manager, mock_docker_client):
        """测试执行结果包含持续时间"""
        mock_container = MagicMock()
        mock_container.id = "duration_container"
        mock_container.status = "running"
        mock_container.exec_run.return_value = (0, b"OK")
        mock_docker_client.containers.create.return_value = mock_container
        mock_docker_client.containers.get.return_value = mock_container
        
        result = executor.execute_command(
            user_id=1,
            project_id="proj",
            command="echo OK"
        )
        
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.duration_seconds >= 0


# ============ ExecutionConfig 测试 ============

class TestExecutionConfig:
    """测试执行配置"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = ExecutionConfig()
        
        assert config.timeout == 300
        assert config.enable_network is False
        assert config.python_version == "3.11"
        assert config.memory_limit == "512m"
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ExecutionConfig(
            timeout=600,
            enable_network=True,
            python_version="3.12",
            install_packages=["pandas", "numpy"],
            memory_limit="1g"
        )
        
        assert config.timeout == 600
        assert config.enable_network is True
        assert "pandas" in config.install_packages
    
    def test_output_truncation_limit(self):
        """测试输出截断限制"""
        config = ExecutionConfig(max_output_size=1024)
        
        assert config.max_output_size == 1024


# ============ ExecutionResult 测试 ============

class TestExecutionResult:
    """测试执行结果"""
    
    def test_success_result(self):
        """测试成功结果"""
        result = ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            exit_code=0,
            stdout="Hello World",
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        
        assert result.status == ExecutionStatus.COMPLETED
        assert result.exit_code == 0
    
    def test_failure_result(self):
        """测试失败结果"""
        result = ExecutionResult(
            status=ExecutionStatus.FAILED,
            exit_code=1,
            stderr="Error occurred",
            error="Script failed"
        )
        
        assert result.status == ExecutionStatus.FAILED
        assert result.error == "Script failed"
    
    def test_to_dict(self):
        """测试转换为字典"""
        now = datetime.now()
        result = ExecutionResult(
            status=ExecutionStatus.COMPLETED,
            exit_code=0,
            stdout="output",
            started_at=now,
            completed_at=now,
            duration_seconds=1.5
        )
        
        d = result.to_dict()
        
        assert d["status"] == "completed"
        assert d["exit_code"] == 0
        assert d["duration_seconds"] == 1.5


# ============ 集成测试（需要真实 Docker）============

@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker not available")
class TestDockerIntegration:
    """Docker 集成测试（需要真实 Docker 环境）"""
    
    @pytest.fixture
    def real_docker_manager(self, temp_workspace):
        """创建真实的 DockerManager"""
        manager = DockerManager(
            workspaces_root=temp_workspace,
            max_containers_per_user=2,
            cleanup_interval=3600
        )
        if not manager.initialize():
            pytest.skip("Docker not available")
        yield manager
        manager.cleanup_all()
    
    @pytest.mark.slow
    def test_real_container_lifecycle(self, real_docker_manager):
        """测试真实的容器生命周期"""
        # 创建容器
        info = real_docker_manager.create_container(
            user_id=999,
            project_id="integration_test"
        )
        
        assert info is not None
        assert info.status == ContainerStatus.CREATING
        
        # 启动容器
        assert real_docker_manager.start_container(info.container_id)
        
        # 检查状态
        status = real_docker_manager.get_container_status(info.container_id)
        assert status == ContainerStatus.RUNNING
        
        # 停止容器
        assert real_docker_manager.stop_container(info.container_id)
        
        # 删除容器
        assert real_docker_manager.remove_container(info.container_id)
    
    @pytest.mark.slow
    def test_real_command_execution(self, real_docker_manager):
        """测试真实的命令执行"""
        # 确保容器存在
        info = real_docker_manager.ensure_container(
            user_id=999,
            project_id="exec_test"
        )
        
        assert info is not None
        
        # 执行命令
        result = real_docker_manager.exec_in_container(
            info.container_id,
            "python -c 'print(1+1)'"
        )
        
        assert result["success"] is True
        assert result["exit_code"] == 0
        assert "2" in result["stdout"]
        
        # 清理
        real_docker_manager.remove_container(info.container_id, force=True)
    
    @pytest.mark.slow
    def test_real_python_execution(self, real_docker_manager, temp_workspace):
        """测试真实的 Python 脚本执行"""
        executor = SandboxExecutor(real_docker_manager)
        
        # 创建测试脚本
        workspace_path = os.path.join(temp_workspace, "999", "python_test")
        os.makedirs(workspace_path, exist_ok=True)
        
        script_content = """
import sys
print(f"Python version: {sys.version}")
print("Hello from sandbox!")
"""
        with open(os.path.join(workspace_path, "test.py"), 'w') as f:
            f.write(script_content)
        
        result = executor.execute_python(
            user_id=999,
            project_id="python_test",
            script_path="test.py"
        )
        
        assert result.status == ExecutionStatus.COMPLETED
        assert "Hello from sandbox!" in result.stdout
        
        # 清理
        real_docker_manager.cleanup_all(user_id=999)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

