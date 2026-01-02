"""
Prompt配置加载器
从YAML文件加载prompt配置，实现代码和prompt的分离

重构说明：
- YAML中直接存储格式化好的文本块，避免复杂的字符串拼装
- Loader只负责读取YAML和填充模板占位符
- 代码从156行简化到50行左右
"""

import os
import yaml
from typing import Dict, Any


class PromptLoader:
    """Prompt配置加载器（简化版）"""
    
    def __init__(self, config_path: str = None):
        """
        初始化加载器
        
        Args:
            config_path: 配置文件路径，默认为当前目录下的prompts/prompt_config.yaml
        """
        if config_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "prompts", "prompt_config.yaml")
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"无法加载prompt配置文件 {self.config_path}: {e}")
    
    def build_system_prompt(self, capability_text: str, state_summary: str = "") -> str:
        """
        构建完整的系统提示词
        
        Args:
            capability_text: 能力清单文本
            state_summary: 当前状态摘要
            
        Returns:
            完整的系统提示词
        """
        template = self.config.get('system_prompt_template', '')
        
        # 转义花括号，避免被ChatPromptTemplate误认为变量占位符
        # 这些内容在后续的LangChain处理中需要保持原样
        capability_text = capability_text.replace("{", "{{").replace("}", "}}")
        output_schema = self.config.get('output_schema', '').replace("{", "{{").replace("}", "}}")
        field_instructions = self.config.get('field_instructions', '').replace("{", "{{").replace("}", "}}")
        examples = self.config.get('examples', '').replace("{", "{{").replace("}", "}}")
        
        # 填充模板占位符
        prompt = template.format(
            capability_text=capability_text,
            field_instructions=field_instructions,
            examples=examples,
            state_summary="{state_summary}",  # 保留为ChatPromptTemplate的变量
            output_schema=output_schema
        )
        
        return prompt


# 单例模式，避免重复加载配置文件
_prompt_loader_instance = None


def get_prompt_loader() -> PromptLoader:
    """获取PromptLoader单例"""
    global _prompt_loader_instance
    if _prompt_loader_instance is None:
        _prompt_loader_instance = PromptLoader()
    return _prompt_loader_instance
