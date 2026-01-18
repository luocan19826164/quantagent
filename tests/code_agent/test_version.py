"""
测试版本管理功能
"""

import pytest
import sys
import os
import tempfile
import shutil
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.tools import (
    VersionManager,
    VersionInfo,
    CreateBackupTool,
    ListVersionsTool,
    RestoreVersionTool,
    GetVersionContentTool
)


@pytest.fixture
def workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_version_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_file(workspace):
    """创建示例文件"""
    content = """def hello():
    print("Hello World")

def add(a, b):
    return a + b
"""
    file_path = os.path.join(workspace, "sample.py")
    with open(file_path, 'w') as f:
        f.write(content)
    return "sample.py"


class TestVersionManager:
    """测试版本管理器"""
    
    def test_create_backup(self, workspace, sample_file):
        """测试创建备份"""
        manager = VersionManager(workspace)
        
        version_info = manager.create_backup(sample_file, "Initial version")
        
        assert version_info is not None
        assert version_info.file_path == sample_file
        assert "Initial version" in version_info.description
        assert version_info.version_id.startswith("v_")
    
    def test_backup_same_content_no_duplicate(self, workspace, sample_file):
        """测试相同内容不会创建重复备份"""
        manager = VersionManager(workspace)
        
        v1 = manager.create_backup(sample_file, "Version 1")
        v2 = manager.create_backup(sample_file, "Version 2")
        
        # 内容相同，应该返回相同版本
        assert v1.version_id == v2.version_id
    
    def test_backup_different_content(self, workspace, sample_file):
        """测试不同内容创建新备份"""
        manager = VersionManager(workspace)
        
        v1 = manager.create_backup(sample_file, "Version 1")
        
        # 修改文件内容
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'a') as f:
            f.write("\n# Modified\n")
        
        # 等待一小段时间确保时间戳不同
        time.sleep(0.1)
        
        v2 = manager.create_backup(sample_file, "Version 2")
        
        # 应该是不同版本
        assert v1.version_id != v2.version_id
    
    def test_list_versions(self, workspace, sample_file):
        """测试列出版本"""
        manager = VersionManager(workspace)
        
        # 创建多个版本
        manager.create_backup(sample_file, "V1")
        
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'w') as f:
            f.write("# Version 2")
        time.sleep(0.1)
        manager.create_backup(sample_file, "V2")
        
        with open(abs_path, 'w') as f:
            f.write("# Version 3")
        time.sleep(0.1)
        manager.create_backup(sample_file, "V3")
        
        versions = manager.list_versions(sample_file)
        
        assert len(versions) == 3
    
    def test_get_version_content(self, workspace, sample_file):
        """测试获取版本内容"""
        manager = VersionManager(workspace)
        
        # 备份原始内容
        v1 = manager.create_backup(sample_file, "Original")
        
        # 修改文件
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'w') as f:
            f.write("# Modified content")
        
        # 获取旧版本内容
        old_content = manager.get_version_content(sample_file, v1.version_id)
        
        assert old_content is not None
        assert "def hello" in old_content
        assert "Modified content" not in old_content
    
    def test_restore_version(self, workspace, sample_file):
        """测试恢复版本"""
        manager = VersionManager(workspace)
        
        # 备份原始内容
        v1 = manager.create_backup(sample_file, "Original")
        original_content = manager.get_version_content(sample_file, v1.version_id)
        
        # 修改文件
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'w') as f:
            f.write("# Completely different content")
        
        # 恢复到原始版本
        success = manager.restore_version(sample_file, v1.version_id)
        
        assert success is True
        
        # 验证内容已恢复
        with open(abs_path, 'r') as f:
            restored_content = f.read()
        
        assert restored_content == original_content
    
    def test_restore_creates_backup(self, workspace, sample_file):
        """测试恢复前创建备份"""
        manager = VersionManager(workspace)
        
        # 备份原始
        v1 = manager.create_backup(sample_file, "Original")
        
        # 修改
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'w') as f:
            f.write("# Modified")
        time.sleep(0.1)
        
        # 恢复（会自动备份当前版本）
        manager.restore_version(sample_file, v1.version_id, create_backup=True)
        
        # 应该有多个版本
        versions = manager.list_versions(sample_file)
        assert len(versions) >= 2
    
    def test_max_versions_cleanup(self, workspace, sample_file):
        """测试超出限制时清理旧版本"""
        manager = VersionManager(workspace)
        manager.MAX_VERSIONS_PER_FILE = 3  # 设置较小的限制
        
        abs_path = os.path.join(workspace, sample_file)
        
        # 创建多个版本
        for i in range(5):
            with open(abs_path, 'w') as f:
                f.write(f"# Version {i}")
            time.sleep(0.1)
            manager.create_backup(sample_file, f"V{i}")
        
        versions = manager.list_versions(sample_file)
        
        # 应该只保留最新的3个
        assert len(versions) == 3


class TestVersionTools:
    """测试版本管理工具"""
    
    def test_create_backup_tool(self, workspace, sample_file):
        """测试创建备份工具"""
        tool = CreateBackupTool(workspace)
        
        result = tool.execute(path=sample_file, description="Test backup")
        
        assert result.success is True
        assert "version_id" in result.data
    
    def test_create_backup_nonexistent_file(self, workspace):
        """测试备份不存在的文件"""
        tool = CreateBackupTool(workspace)
        
        result = tool.execute(path="nonexistent.py")
        
        assert result.success is False
        assert "不存在" in result.error
    
    def test_list_versions_tool(self, workspace, sample_file):
        """测试列出版本工具"""
        # 先创建一个备份
        CreateBackupTool(workspace).execute(path=sample_file)
        
        tool = ListVersionsTool(workspace)
        result = tool.execute(path=sample_file)
        
        assert result.success is True
        assert result.data["count"] >= 1
    
    def test_list_versions_empty(self, workspace):
        """测试列出空版本"""
        tool = ListVersionsTool(workspace)
        
        result = tool.execute(path="no_versions.py")
        
        assert result.success is True
        assert result.data["count"] == 0
    
    def test_restore_version_tool(self, workspace, sample_file):
        """测试恢复版本工具"""
        # 创建备份
        backup_result = CreateBackupTool(workspace).execute(path=sample_file)
        version_id = backup_result.data["version_id"]
        
        # 修改文件
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'w') as f:
            f.write("# Changed")
        
        # 恢复
        tool = RestoreVersionTool(workspace)
        result = tool.execute(path=sample_file, version_id=version_id)
        
        assert result.success is True
        assert sample_file in result.files_changed
    
    def test_restore_invalid_version(self, workspace, sample_file):
        """测试恢复无效版本"""
        tool = RestoreVersionTool(workspace)
        
        result = tool.execute(path=sample_file, version_id="invalid_version")
        
        assert result.success is False
    
    def test_get_version_content_tool(self, workspace, sample_file):
        """测试获取版本内容工具"""
        # 创建备份
        backup_result = CreateBackupTool(workspace).execute(path=sample_file)
        version_id = backup_result.data["version_id"]
        
        tool = GetVersionContentTool(workspace)
        result = tool.execute(path=sample_file, version_id=version_id)
        
        assert result.success is True
        assert "def hello" in result.output
        assert result.data["line_count"] > 0


class TestVersionIntegration:
    """版本管理集成测试"""
    
    def test_workflow_backup_modify_restore(self, workspace, sample_file):
        """测试完整工作流：备份 -> 修改 -> 恢复"""
        # 1. 读取原始内容
        abs_path = os.path.join(workspace, sample_file)
        with open(abs_path, 'r') as f:
            original = f.read()
        
        # 2. 创建备份
        backup_tool = CreateBackupTool(workspace)
        backup_result = backup_tool.execute(path=sample_file, description="Before changes")
        assert backup_result.success
        version_id = backup_result.data["version_id"]
        
        # 3. 修改文件（模拟 Agent 修改）
        with open(abs_path, 'w') as f:
            f.write("# Completely rewritten\nprint('new code')")
        
        # 4. 验证文件已变更
        with open(abs_path, 'r') as f:
            modified = f.read()
        assert modified != original
        
        # 5. 恢复到原始版本
        restore_tool = RestoreVersionTool(workspace)
        restore_result = restore_tool.execute(path=sample_file, version_id=version_id)
        assert restore_result.success
        
        # 6. 验证已恢复
        with open(abs_path, 'r') as f:
            restored = f.read()
        assert restored == original
    
    def test_version_persistence(self, workspace, sample_file):
        """测试版本信息持久化"""
        # 使用第一个 manager 创建备份
        manager1 = VersionManager(workspace)
        v1 = manager1.create_backup(sample_file, "Test")
        
        # 创建新的 manager 实例（模拟重启）
        manager2 = VersionManager(workspace)
        versions = manager2.list_versions(sample_file)
        
        # 版本信息应该仍然存在
        assert len(versions) == 1
        assert versions[0].version_id == v1.version_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

