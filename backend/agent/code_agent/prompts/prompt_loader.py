"""
Code Agent Prompt 配置加载器
从 YAML 文件加载 prompt 配置，实现代码和 prompt 的分离
"""

import os
import yaml
from typing import Dict, Any, Optional


class CodeAgentPromptLoader:
    """Code Agent Prompt 加载器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化加载器
        
        Args:
            config_path: 配置文件路径，默认为当前目录下的 code_agent_prompt.yaml
        """
        if config_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "code_agent_prompt.yaml")
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载 YAML 配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"无法加载 prompt 配置文件 {self.config_path}: {e}")
    
    def get_step_execution_prompt(self) -> str:
        """
        获取步骤执行的系统提示词
        
        Returns:
            步骤执行系统提示词
        """
        return self.config.get('step_execution_prompt', '')
    
    def get_system_prompt(self) -> str:
        """
        获取通用系统提示词
        
        Returns:
            通用系统提示词
        """
        return self.config.get('system_prompt', '')
    
    def get_mode_guidance(self) -> str:
        """
        获取执行模式选择指导
        
        Returns:
            模式选择指导提示词
        """
        return self.config.get('mode_guidance', '')
    
    def get_greeting(self) -> str:
        """
        获取问候语
        
        Returns:
            问候语
        """
        return self.config.get('greeting', '')
    
    def get_code_template(self, template_name: str) -> Optional[str]:
        """
        获取代码模板
        
        Args:
            template_name: 模板名称，如 'rsi_strategy', 'ma_crossover'
            
        Returns:
            代码模板内容，不存在则返回 None
        """
        templates = self.config.get('code_templates', {})
        return templates.get(template_name)
    
    def get_all_template_names(self) -> list:
        """
        获取所有可用的模板名称
        
        Returns:
            模板名称列表
        """
        templates = self.config.get('code_templates', {})
        return list(templates.keys())
    
    # ==================== Plan 模式步骤执行模板 ====================
    
    def get_step_user_message(self) -> str:
        """获取步骤执行的用户消息模板"""
        return self.config.get('step_user_message', '')
    
    def get_step_system_message(self) -> str:
        """获取步骤执行的系统消息主模板"""
        return self.config.get('step_system_message', '')
    
    def get_project_context(self) -> str:
        """获取项目上下文模板"""
        return self.config.get('project_context', '')
    
    def get_active_files_warning(self) -> str:
        """获取活跃文件警告模板"""
        return self.config.get('active_files_warning', '')
    
    def get_code_context(self) -> str:
        """获取代码上下文模板"""
        return self.config.get('code_context', '')
    
    def get_correction_prompt(self) -> str:
        """获取异常修正提示模板"""
        return self.config.get('correction_prompt', '')
    
    # ==================== 上下文格式化模板 ====================
    
    def get_context_history_decisions(self) -> str:
        """获取历史决策上下文模板"""
        return self.config.get('context_history_decisions', '')
    
    def get_context_project_conventions(self) -> str:
        """获取项目规范上下文模板"""
        return self.config.get('context_project_conventions', '')
    
    def get_context_active_files(self) -> str:
        """获取活跃文件列表上下文模板"""
        return self.config.get('context_active_files', '')
    
    def get_context_repo_map(self) -> str:
        """获取代码结构（Repo Map）上下文模板"""
        return self.config.get('context_repo_map', '')
    
    def get_context_file_content(self) -> str:
        """获取活跃文件内容上下文模板"""
        return self.config.get('context_file_content', '')
    
    def get_context_editing_info(self) -> str:
        """获取活跃文件编辑信息子模板"""
        return self.config.get('context_editing_info', '')
    
    def get_context_more_files_info(self) -> str:
        """获取活跃文件更多文件信息子模板"""
        return self.config.get('context_more_files_info', '')


# 单例模式，避免重复加载配置文件
_prompt_loader_instance = None


def get_code_agent_prompt_loader() -> CodeAgentPromptLoader:
    """获取 CodeAgentPromptLoader 单例"""
    global _prompt_loader_instance
    if _prompt_loader_instance is None:
        _prompt_loader_instance = CodeAgentPromptLoader()
    return _prompt_loader_instance

