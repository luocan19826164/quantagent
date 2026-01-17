"""
LLM 配置模块
统一管理 LLM Provider 的优先级和配置解析
支持从环境变量动态读取配置，避免硬编码
"""

import os
import logging
from typing import Dict, Any, List, Optional

# LLM Provider 优先级列表
# 环境变量命名约定: {PROVIDER}_API_KEY, {PROVIDER}_BASE_URL, {PROVIDER}_MODEL
LLM_PROVIDER_PRIORITY = ["OPENROUTER", "DEEPSEEK", "OPENAI"]

# 每个 Provider 默认支持的模型列表（当环境变量未指定时使用）
DEFAULT_MODELS = {
    "OPENROUTER": [
        "anthropic/claude-sonnet-4",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3-opus",
        "anthropic/claude-3-sonnet"
    ],
    "DEEPSEEK": [
        "deepseek-chat",
        "deepseek-coder",
        "deepseek-reasoner"
    ],
    "OPENAI": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo"
    ]
}

# 每个 Provider 的默认 base_url（当环境变量未指定时使用）
DEFAULT_BASE_URLS = {
    "OPENROUTER": "https://openrouter.ai/api/v1",
    "DEEPSEEK": "https://api.deepseek.com/v1",
    "OPENAI": "https://api.openai.com/v1"
}

# 需要额外 headers 的 providers
PROVIDERS_NEEDING_EXTRA_HEADERS = {"OPENROUTER"}


def get_provider_models(provider: str) -> List[str]:
    """
    获取指定 provider 支持的模型列表
    
    Args:
        provider: Provider 名称（大写，如 "OPENROUTER"）
    
    Returns:
        模型名称列表
    """
    # 优先从环境变量读取
    models_env = os.getenv(f"{provider}_MODELS")
    if models_env:
        return [m.strip() for m in models_env.split(",") if m.strip()]
    
    # 使用默认列表
    return DEFAULT_MODELS.get(provider, [])


def get_provider_base_url(provider: str) -> Optional[str]:
    """
    获取指定 provider 的 base_url
    
    Args:
        provider: Provider 名称（大写，如 "OPENROUTER"）
    
    Returns:
        base_url，如果未配置则返回默认值
    """
    base_url = os.getenv(f"{provider}_BASE_URL")
    if base_url:
        return base_url
    
    return DEFAULT_BASE_URLS.get(provider)


def get_supported_models() -> Dict[str, Dict[str, Any]]:
    """
    从环境变量动态构建 SUPPORTED_MODELS 配置
    
    Returns:
        格式与原来的 SUPPORTED_MODELS 相同，但只包含已配置的 providers
    """
    supported = {}
    
    for provider in LLM_PROVIDER_PRIORITY:
        api_key = os.getenv(f"{provider}_API_KEY")
        if not api_key:
            continue  # 未配置的 provider 跳过
        
        base_url = get_provider_base_url(provider)
        models = get_provider_models(provider)
        
        if not base_url:
            logging.warning(f"{provider} API key found but missing BASE_URL config, skipping")
            continue
        
        if not models:
            logging.warning(f"{provider} API key found but no models configured, skipping")
            continue
        
        supported[provider.lower()] = {
            "models": models,
            "api_key_env": f"{provider}_API_KEY",
            "base_url": base_url,
            "needs_extra_headers": provider in PROVIDERS_NEEDING_EXTRA_HEADERS
        }
    
    return supported


def resolve_llm_config(log_prefix: str = "") -> Dict[str, Any]:
    """
    按优先级解析 LLM 配置，返回第一个可用的 provider 配置。
    
    Args:
        log_prefix: 日志前缀，用于区分不同 agent 的日志输出
    
    环境变量命名约定:
      - {PROVIDER}_API_KEY: API 密钥（必填）
      - {PROVIDER}_BASE_URL: API 地址（可选，有默认值）
      - {PROVIDER}_MODEL: 模型名称（必填）
      - {PROVIDER}_MODELS: 支持的模型列表，逗号分隔（可选，有默认值）
    
    OpenRouter 额外支持:
      - OPENROUTER_SITE_URL: 用于统计的站点 URL
      - OPENROUTER_APP_NAME: 用于统计的应用名称
    
    Returns:
        包含 provider, api_key, base_url, model, extra_headers 的配置字典
    """
    for provider in LLM_PROVIDER_PRIORITY:
        api_key = os.getenv(f"{provider}_API_KEY")
        if not api_key:
            continue
        
        base_url = get_provider_base_url(provider)
        model = os.getenv(f"{provider}_MODEL")
        
        if not base_url:
            logging.warning(f"{provider} API key found but missing BASE_URL config, skipping")
            continue
        
        if not model:
            logging.warning(f"{provider} API key found but missing MODEL config, skipping")
            continue
        
        # OpenRouter 需要额外的 headers
        extra_headers = None
        if provider in PROVIDERS_NEEDING_EXTRA_HEADERS:
            extra_headers = {
                "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:8081"),
                "X-Title": os.getenv("OPENROUTER_APP_NAME", "QuantAgent")
            }
        
        prefix = f"{log_prefix} " if log_prefix else ""
        logging.info(f"{prefix}Using {provider} - Model: {model}, Base URL: {base_url}")
        return {
            "provider": provider.lower(),
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "extra_headers": extra_headers
        }
    
    # 兜底：无可用配置
    logging.error("No valid LLM config found! Please check your .env file.")
    return {
        "provider": None,
        "api_key": None,
        "base_url": None,
        "model": None,
        "extra_headers": None
    }


def get_extra_headers(provider: str) -> Optional[Dict[str, str]]:
    """
    获取指定 provider 的额外 headers
    
    Args:
        provider: Provider 名称（小写，如 "openrouter"）
    
    Returns:
        额外的 headers 字典，如果不需要则返回 None
    """
    provider_upper = provider.upper()
    if provider_upper not in PROVIDERS_NEEDING_EXTRA_HEADERS:
        return None
    
    if provider_upper == "OPENROUTER":
        return {
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:8081"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "QuantAgent")
        }
    
    return None

