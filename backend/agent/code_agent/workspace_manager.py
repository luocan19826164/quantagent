"""
工作区管理器
负责管理用户的项目、文件读写等操作
"""

import os
import json
import uuid
import shutil
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

# 默认工作区根目录
_DEFAULT_WORKSPACE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 
    "workspaces"
)


def get_workspace_root() -> str:
    """获取工作区根目录（支持运行时更新）"""
    return os.environ.get("CODE_AGENT_WORKSPACE_ROOT", _DEFAULT_WORKSPACE_ROOT)


class WorkspaceManager:
    """工作区管理器"""
    
    def __init__(self, user_id: int):
        """
        初始化工作区管理器
        
        Args:
            user_id: 用户ID
        """
        self.user_id = user_id
        workspace_root = get_workspace_root()
        self.user_workspace = os.path.join(workspace_root, str(user_id))
        self.projects_file = os.path.join(self.user_workspace, "projects.json")
        
        # 确保用户工作区目录存在
        os.makedirs(self.user_workspace, exist_ok=True)
        
        # 初始化项目列表文件
        if not os.path.exists(self.projects_file):
            self._save_projects_metadata([])
    
    # ==================== 项目管理 ====================
    
    def list_projects(self) -> List[Dict[str, Any]]:
        """获取用户所有项目列表"""
        return self._load_projects_metadata()
    
    def create_project(self, name: str, description: str = "") -> Dict[str, Any]:
        """
        创建新项目
        
        Args:
            name: 项目名称
            description: 项目描述
            
        Returns:
            项目信息字典
        """
        project_id = str(uuid.uuid4())[:8]
        project_path = os.path.join(self.user_workspace, project_id)
        
        # 创建项目目录
        os.makedirs(project_path, exist_ok=True)
        
        # 创建项目元数据
        project_meta = {
            "id": project_id,
            "name": name,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        
        # 保存项目内部元数据
        meta_file = os.path.join(project_path, ".meta.json")
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(project_meta, f, ensure_ascii=False, indent=2)
        
        # 创建默认的 main.py
        main_file = os.path.join(project_path, "main.py")
        with open(main_file, "w", encoding="utf-8") as f:
            f.write('"""\n量化策略主程序\n"""\n\nimport pandas as pd\nimport numpy as np\n\n\ndef main():\n    print("Hello, Quant!")\n\n\nif __name__ == "__main__":\n    main()\n')
        
        # 更新项目列表
        projects = self._load_projects_metadata()
        projects.append(project_meta)
        self._save_projects_metadata(projects)
        
        logging.info(f"Created project {project_id} for user {self.user_id}")
        return project_meta
    
    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目详情"""
        projects = self._load_projects_metadata()
        for p in projects:
            if p["id"] == project_id:
                return p
        return None
    
    def delete_project(self, project_id: str) -> bool:
        """删除项目"""
        project_path = self._get_project_path(project_id)
        if not project_path or not os.path.exists(project_path):
            return False
        
        # 删除项目目录
        shutil.rmtree(project_path)
        
        # 更新项目列表
        projects = self._load_projects_metadata()
        projects = [p for p in projects if p["id"] != project_id]
        self._save_projects_metadata(projects)
        
        logging.info(f"Deleted project {project_id} for user {self.user_id}")
        return True
    
    def update_project(self, project_id: str, name: str = None, description: str = None) -> Optional[Dict[str, Any]]:
        """更新项目信息"""
        projects = self._load_projects_metadata()
        for p in projects:
            if p["id"] == project_id:
                if name:
                    p["name"] = name
                if description is not None:
                    p["description"] = description
                p["updated_at"] = datetime.now().isoformat()
                self._save_projects_metadata(projects)
                
                # 同时更新项目内部元数据
                project_path = self._get_project_path(project_id)
                if project_path:
                    meta_file = os.path.join(project_path, ".meta.json")
                    with open(meta_file, "w", encoding="utf-8") as f:
                        json.dump(p, f, ensure_ascii=False, indent=2)
                
                return p
        return None
    
    # ==================== 文件操作 ====================
    
    def get_file_tree(self, project_id: str) -> List[Dict[str, Any]]:
        """
        获取项目文件树
        
        Returns:
            文件树列表，每个元素包含 name, path, type (file/dir)
        """
        project_path = self._get_project_path(project_id)
        if not project_path:
            return []
        
        return self._build_file_tree(project_path, "")
    
    def get_file_list(self, project_id: str) -> List[str]:
        """获取项目所有文件路径（扁平列表）"""
        project_path = self._get_project_path(project_id)
        if not project_path:
            return []
        
        files = []
        for root, dirs, filenames in os.walk(project_path):
            # 忽略隐藏文件和目录
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for filename in filenames:
                if not filename.startswith('.'):
                    rel_path = os.path.relpath(os.path.join(root, filename), project_path)
                    files.append(rel_path)
        return sorted(files)
    
    def read_file(self, project_id: str, file_path: str) -> Optional[str]:
        """
        读取文件内容
        
        Args:
            project_id: 项目ID
            file_path: 相对于项目根目录的文件路径
            
        Returns:
            文件内容，如果文件不存在返回 None
        """
        full_path = self._get_safe_file_path(project_id, file_path)
        if not full_path or not os.path.isfile(full_path):
            return None
        
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logging.error(f"Error reading file {file_path}: {e}")
            return None
    
    def write_file(self, project_id: str, file_path: str, content: str) -> bool:
        """
        写入文件内容（创建或覆盖）
        
        Args:
            project_id: 项目ID
            file_path: 相对于项目根目录的文件路径
            content: 文件内容
            
        Returns:
            是否成功
        """
        full_path = self._get_safe_file_path(project_id, file_path)
        if not full_path:
            return False
        
        # 检查文件大小限制（1MB）
        if len(content.encode("utf-8")) > 1024 * 1024:
            logging.warning(f"File too large: {file_path}")
            return False
        
        try:
            # 确保父目录存在
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            # 更新项目更新时间
            self._touch_project(project_id)
            return True
        except Exception as e:
            logging.error(f"Error writing file {file_path}: {e}")
            return False
    
    def create_file(self, project_id: str, file_path: str, content: str = "") -> bool:
        """创建新文件"""
        full_path = self._get_safe_file_path(project_id, file_path)
        if not full_path:
            return False
        
        if os.path.exists(full_path):
            logging.warning(f"File already exists: {file_path}")
            return False
        
        return self.write_file(project_id, file_path, content)
    
    def delete_file(self, project_id: str, file_path: str) -> bool:
        """删除文件"""
        full_path = self._get_safe_file_path(project_id, file_path)
        if not full_path or not os.path.exists(full_path):
            return False
        
        try:
            if os.path.isfile(full_path):
                os.remove(full_path)
            else:
                shutil.rmtree(full_path)
            
            self._touch_project(project_id)
            return True
        except Exception as e:
            logging.error(f"Error deleting file {file_path}: {e}")
            return False
    
    def rename_file(self, project_id: str, old_path: str, new_path: str) -> bool:
        """重命名/移动文件"""
        old_full = self._get_safe_file_path(project_id, old_path)
        new_full = self._get_safe_file_path(project_id, new_path)
        
        if not old_full or not new_full:
            return False
        
        if not os.path.exists(old_full):
            return False
        
        try:
            os.makedirs(os.path.dirname(new_full), exist_ok=True)
            shutil.move(old_full, new_full)
            self._touch_project(project_id)
            return True
        except Exception as e:
            logging.error(f"Error renaming file {old_path} to {new_path}: {e}")
            return False
    
    def create_directory(self, project_id: str, dir_path: str) -> bool:
        """创建目录"""
        full_path = self._get_safe_file_path(project_id, dir_path)
        if not full_path:
            return False
        
        try:
            os.makedirs(full_path, exist_ok=True)
            return True
        except Exception as e:
            logging.error(f"Error creating directory {dir_path}: {e}")
            return False
    
    # ==================== 辅助方法 ====================
    
    def get_project_path(self, project_id: str) -> Optional[str]:
        """获取项目绝对路径（公开方法）"""
        return self._get_project_path(project_id)
    
    def _get_project_path(self, project_id: str) -> Optional[str]:
        """获取项目绝对路径"""
        # 验证项目存在
        project = self.get_project(project_id)
        if not project:
            return None
        
        project_path = os.path.join(self.user_workspace, project_id)
        if not os.path.isdir(project_path):
            return None
        
        # 使用 realpath 解析符号链接，确保路径一致性
        return os.path.realpath(project_path)
    
    def _get_safe_file_path(self, project_id: str, file_path: str) -> Optional[str]:
        """
        获取安全的文件绝对路径（防止路径遍历攻击）
        """
        project_path = self._get_project_path(project_id)
        if not project_path:
            return None
        
        # 使用 realpath 解析符号链接，确保路径一致性
        project_path_real = os.path.realpath(project_path)
        
        # 规范化路径
        full_path = os.path.normpath(os.path.join(project_path_real, file_path))
        
        # 确保路径在项目目录内（防止 ../ 攻击）
        # 添加路径分隔符确保精确匹配，避免 /abc 匹配 /abcdef
        if not (full_path == project_path_real or 
                full_path.startswith(project_path_real + os.sep)):
            logging.warning(f"Path traversal attempt: {file_path}")
            return None
        
        return full_path
    
    def _build_file_tree(self, base_path: str, rel_path: str) -> List[Dict[str, Any]]:
        """递归构建文件树"""
        result = []
        current_path = os.path.join(base_path, rel_path) if rel_path else base_path
        
        try:
            entries = sorted(os.listdir(current_path))
        except PermissionError:
            return result
        
        for entry in entries:
            # 忽略隐藏文件
            if entry.startswith('.'):
                continue
            
            entry_rel_path = os.path.join(rel_path, entry) if rel_path else entry
            entry_full_path = os.path.join(current_path, entry)
            
            if os.path.isdir(entry_full_path):
                result.append({
                    "name": entry,
                    "path": entry_rel_path,
                    "type": "dir",
                    "children": self._build_file_tree(base_path, entry_rel_path)
                })
            else:
                result.append({
                    "name": entry,
                    "path": entry_rel_path,
                    "type": "file",
                    "size": os.path.getsize(entry_full_path)
                })
        
        return result
    
    def _load_projects_metadata(self) -> List[Dict[str, Any]]:
        """加载项目列表元数据"""
        if not os.path.exists(self.projects_file):
            return []
        
        try:
            with open(self.projects_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    
    def _save_projects_metadata(self, projects: List[Dict[str, Any]]):
        """保存项目列表元数据"""
        with open(self.projects_file, "w", encoding="utf-8") as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)
    
    def _touch_project(self, project_id: str):
        """更新项目的更新时间"""
        projects = self._load_projects_metadata()
        for p in projects:
            if p["id"] == project_id:
                p["updated_at"] = datetime.now().isoformat()
                break
        self._save_projects_metadata(projects)

