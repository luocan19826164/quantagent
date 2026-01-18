"""
版本备份工具
简单的文件版本管理，支持备份和恢复
"""

import os
import json
import shutil
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from .base import BaseTool, ToolResult


@dataclass
class VersionInfo:
    """版本信息"""
    version_id: str           # 版本ID (时间戳+hash前6位)
    file_path: str            # 原文件路径
    timestamp: str            # ISO格式时间戳
    description: str          # 版本描述
    file_size: int            # 文件大小
    content_hash: str         # 内容hash
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'VersionInfo':
        return cls(**data)


class VersionManager:
    """
    版本管理器
    
    存储结构:
    workspace/
    └── .versions/
        ├── index.json           # 版本索引
        └── backups/
            ├── v_20240117_abc123.py
            └── v_20240117_def456.py
    """
    
    VERSION_DIR = ".versions"
    BACKUP_DIR = "backups"
    INDEX_FILE = "index.json"
    MAX_VERSIONS_PER_FILE = 20  # 每个文件最多保留版本数
    
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        self.version_dir = os.path.join(workspace_path, self.VERSION_DIR)
        self.backup_dir = os.path.join(self.version_dir, self.BACKUP_DIR)
        self.index_path = os.path.join(self.version_dir, self.INDEX_FILE)
        
        # 确保目录存在
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # 加载索引
        self._index = self._load_index()
    
    def _load_index(self) -> Dict[str, List[Dict]]:
        """加载版本索引"""
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_index(self):
        """保存版本索引"""
        with open(self.index_path, 'w', encoding='utf-8') as f:
            json.dump(self._index, f, ensure_ascii=False, indent=2)
    
    def _compute_hash(self, content: str) -> str:
        """计算内容hash"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _generate_version_id(self, content_hash: str) -> str:
        """生成版本ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"v_{timestamp}_{content_hash[:6]}"
    
    def create_backup(self, file_path: str, description: str = "") -> Optional[VersionInfo]:
        """
        创建文件备份
        
        Args:
            file_path: 相对于workspace的文件路径
            description: 版本描述
            
        Returns:
            VersionInfo 或 None
        """
        abs_path = os.path.join(self.workspace_path, file_path)
        
        if not os.path.exists(abs_path):
            return None
        
        # 读取文件内容
        with open(abs_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        content_hash = self._compute_hash(content)
        
        # 检查是否与最新版本相同（避免重复备份）
        if file_path in self._index and self._index[file_path]:
            latest = self._index[file_path][-1]
            if latest.get("content_hash") == content_hash:
                # 内容未变化，不创建新版本
                return VersionInfo.from_dict(latest)
        
        # 生成版本ID和备份文件名
        version_id = self._generate_version_id(content_hash)
        _, ext = os.path.splitext(file_path)
        backup_filename = f"{version_id}{ext}"
        backup_path = os.path.join(self.backup_dir, backup_filename)
        
        # 复制文件到备份目录
        shutil.copy2(abs_path, backup_path)
        
        # 创建版本信息
        version_info = VersionInfo(
            version_id=version_id,
            file_path=file_path,
            timestamp=datetime.now().isoformat(),
            description=description or f"Backup before modification",
            file_size=os.path.getsize(abs_path),
            content_hash=content_hash
        )
        
        # 更新索引
        if file_path not in self._index:
            self._index[file_path] = []
        self._index[file_path].append(version_info.to_dict())
        
        # 清理旧版本
        self._cleanup_old_versions(file_path)
        
        self._save_index()
        
        return version_info
    
    def _cleanup_old_versions(self, file_path: str):
        """清理超出限制的旧版本"""
        if file_path not in self._index:
            return
        
        versions = self._index[file_path]
        if len(versions) <= self.MAX_VERSIONS_PER_FILE:
            return
        
        # 删除最旧的版本
        to_remove = versions[:-self.MAX_VERSIONS_PER_FILE]
        self._index[file_path] = versions[-self.MAX_VERSIONS_PER_FILE:]
        
        for v in to_remove:
            _, ext = os.path.splitext(v["file_path"])
            backup_filename = f"{v['version_id']}{ext}"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            if os.path.exists(backup_path):
                os.remove(backup_path)
    
    def list_versions(self, file_path: str) -> List[VersionInfo]:
        """列出文件的所有版本"""
        if file_path not in self._index:
            return []
        return [VersionInfo.from_dict(v) for v in self._index[file_path]]
    
    def get_version_content(self, file_path: str, version_id: str) -> Optional[str]:
        """获取指定版本的内容"""
        if file_path not in self._index:
            return None
        
        for v in self._index[file_path]:
            if v["version_id"] == version_id:
                _, ext = os.path.splitext(file_path)
                backup_filename = f"{version_id}{ext}"
                backup_path = os.path.join(self.backup_dir, backup_filename)
                
                if os.path.exists(backup_path):
                    with open(backup_path, 'r', encoding='utf-8') as f:
                        return f.read()
        return None
    
    def restore_version(self, file_path: str, version_id: str, 
                       create_backup: bool = True) -> bool:
        """
        恢复到指定版本
        
        Args:
            file_path: 文件路径
            version_id: 要恢复的版本ID
            create_backup: 恢复前是否备份当前版本
            
        Returns:
            是否成功
        """
        content = self.get_version_content(file_path, version_id)
        if content is None:
            return False
        
        abs_path = os.path.join(self.workspace_path, file_path)
        
        # 恢复前备份当前版本
        if create_backup and os.path.exists(abs_path):
            self.create_backup(file_path, f"Backup before restore to {version_id}")
        
        # 写入恢复的内容
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return True
    
    def get_diff_summary(self, file_path: str, version_id: str) -> Optional[Dict]:
        """获取版本与当前文件的差异摘要"""
        old_content = self.get_version_content(file_path, version_id)
        if old_content is None:
            return None
        
        abs_path = os.path.join(self.workspace_path, file_path)
        if not os.path.exists(abs_path):
            return {"status": "file_deleted", "old_lines": len(old_content.splitlines())}
        
        with open(abs_path, 'r', encoding='utf-8') as f:
            new_content = f.read()
        
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        return {
            "old_lines": len(old_lines),
            "new_lines": len(new_lines),
            "lines_added": max(0, len(new_lines) - len(old_lines)),
            "lines_removed": max(0, len(old_lines) - len(new_lines)),
            "same_content": old_content == new_content
        }


# ============ 工具类 ============

class CreateBackupTool(BaseTool):
    """创建文件备份工具"""
    
    name = "create_backup"
    description = "创建文件备份，在修改文件前自动保存当前版本"
    
    def __init__(self, workspace_path: str):
        self.version_manager = VersionManager(workspace_path)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "要备份的文件路径（相对于项目根目录）"
                },
                "description": {
                    "type": "string",
                    "description": "版本描述（可选）"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str, description: str = "") -> ToolResult:
        try:
            version_info = self.version_manager.create_backup(path, description)
            
            if version_info is None:
                return ToolResult(
                    success=False,
                    error=f"无法备份文件: {path} (文件不存在)"
                )
            
            return ToolResult(
                success=True,
                output=f"已创建备份: {version_info.version_id}",
                data={
                    "version_id": version_info.version_id,
                    "timestamp": version_info.timestamp,
                    "file_size": version_info.file_size
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ListVersionsTool(BaseTool):
    """列出文件版本历史工具"""
    
    name = "list_versions"
    description = "列出文件的所有历史版本"
    
    def __init__(self, workspace_path: str):
        self.version_manager = VersionManager(workspace_path)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径（相对于项目根目录）"
                }
            },
            "required": ["path"]
        }
    
    def execute(self, path: str) -> ToolResult:
        try:
            versions = self.version_manager.list_versions(path)
            
            if not versions:
                return ToolResult(
                    success=True,
                    output=f"文件 {path} 没有历史版本",
                    data={"versions": [], "count": 0}
                )
            
            # 格式化输出
            lines = [f"文件 {path} 的历史版本 ({len(versions)} 个):"]
            for v in reversed(versions):  # 最新的在前
                lines.append(f"  - {v.version_id}: {v.description} ({v.file_size} bytes)")
            
            return ToolResult(
                success=True,
                output="\n".join(lines),
                data={
                    "versions": [v.to_dict() for v in versions],
                    "count": len(versions)
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class RestoreVersionTool(BaseTool):
    """恢复文件到指定版本工具"""
    
    name = "restore_version"
    description = "将文件恢复到指定的历史版本"
    
    def __init__(self, workspace_path: str):
        self.version_manager = VersionManager(workspace_path)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "version_id": {
                    "type": "string",
                    "description": "要恢复的版本ID"
                },
                "backup_current": {
                    "type": "boolean",
                    "description": "恢复前是否备份当前版本（默认 true）"
                }
            },
            "required": ["path", "version_id"]
        }
    
    def execute(self, path: str, version_id: str, backup_current: bool = True) -> ToolResult:
        try:
            success = self.version_manager.restore_version(path, version_id, backup_current)
            
            if not success:
                return ToolResult(
                    success=False,
                    error=f"无法恢复版本 {version_id}（版本不存在或已损坏）"
                )
            
            return ToolResult(
                success=True,
                output=f"已将 {path} 恢复到版本 {version_id}",
                data={
                    "restored_version": version_id,
                    "backup_created": backup_current
                },
                files_changed=[path]
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class GetVersionContentTool(BaseTool):
    """获取指定版本内容工具"""
    
    name = "get_version_content"
    description = "获取文件指定版本的内容"
    
    def __init__(self, workspace_path: str):
        self.version_manager = VersionManager(workspace_path)
    
    def get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径"
                },
                "version_id": {
                    "type": "string",
                    "description": "版本ID"
                }
            },
            "required": ["path", "version_id"]
        }
    
    def execute(self, path: str, version_id: str) -> ToolResult:
        try:
            content = self.version_manager.get_version_content(path, version_id)
            
            if content is None:
                return ToolResult(
                    success=False,
                    error=f"无法获取版本 {version_id} 的内容"
                )
            
            return ToolResult(
                success=True,
                output=content,
                data={
                    "version_id": version_id,
                    "content_length": len(content),
                    "line_count": len(content.splitlines())
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))

