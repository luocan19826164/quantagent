"""
向量嵌入器
将代码块转换为向量表示
"""

import os
import logging
import hashlib
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import numpy as np

# 尝试导入可选依赖
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None


class EmbeddingProvider(ABC):
    """向量嵌入提供者基类"""
    
    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """模型名称"""
        pass
    
    @abstractmethod
    def embed(self, texts: List[str]) -> np.ndarray:
        """
        将文本转换为向量
        
        Args:
            texts: 文本列表
            
        Returns:
            numpy 数组，形状为 (len(texts), dimension)
        """
        pass
    
    def embed_single(self, text: str) -> np.ndarray:
        """嵌入单个文本"""
        return self.embed([text])[0]


class OpenAIEmbedder(EmbeddingProvider):
    """使用 OpenAI API 的向量嵌入器"""
    
    DEFAULT_MODEL = "text-embedding-3-small"
    DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: str = DEFAULT_MODEL):
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package not installed. Run: pip install openai")
        
        self._model = model
        self._dimension = self.DIMENSIONS.get(model, 1536)
        
        # 初始化客户端
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        
        self._client = OpenAI(**kwargs) if kwargs else OpenAI()
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def model_name(self) -> str:
        return self._model
    
    def embed(self, texts: List[str]) -> np.ndarray:
        """使用 OpenAI API 获取向量"""
        if not texts:
            return np.array([])
        
        # 清理文本
        texts = [t.replace("\n", " ").strip() for t in texts]
        
        try:
            response = self._client.embeddings.create(
                input=texts,
                model=self._model
            )
            
            embeddings = [item.embedding for item in response.data]
            return np.array(embeddings)
            
        except Exception as e:
            logging.error(f"OpenAI embedding error: {e}")
            raise


class LocalEmbedder(EmbeddingProvider):
    """使用本地模型的向量嵌入器（基于 sentence-transformers）"""
    
    DEFAULT_MODEL = "all-MiniLM-L6-v2"
    
    def __init__(self, model_name: str = DEFAULT_MODEL):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers not installed. "
                "Run: pip install sentence-transformers"
            )
        
        self._model_name = model_name
        self._model = SentenceTransformer(model_name)
        self._dimension = self._model.get_sentence_embedding_dimension()
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    def embed(self, texts: List[str]) -> np.ndarray:
        """使用本地模型获取向量"""
        if not texts:
            return np.array([])
        
        embeddings = self._model.encode(texts, show_progress_bar=False)
        return np.array(embeddings)


class MockEmbedder(EmbeddingProvider):
    """
    Mock 嵌入器（用于测试）
    基于文本哈希生成确定性的伪向量
    """
    
    def __init__(self, dimension: int = 384):
        self._dimension = dimension
    
    @property
    def dimension(self) -> int:
        return self._dimension
    
    @property
    def model_name(self) -> str:
        return "mock-embedder"
    
    def embed(self, texts: List[str]) -> np.ndarray:
        """生成基于哈希的伪向量"""
        embeddings = []
        
        for text in texts:
            # 使用文本哈希生成确定性向量
            hash_bytes = hashlib.sha256(text.encode()).digest()
            # 扩展哈希到所需维度
            np.random.seed(int.from_bytes(hash_bytes[:4], 'big'))
            vec = np.random.randn(self._dimension)
            # 归一化
            vec = vec / np.linalg.norm(vec)
            embeddings.append(vec)
        
        return np.array(embeddings)


def get_embedder(provider: str = "auto", **kwargs) -> EmbeddingProvider:
    """
    获取向量嵌入器
    
    Args:
        provider: 提供者名称 ("openai", "local", "mock", "auto")
        **kwargs: 传递给嵌入器的参数
        
    Returns:
        EmbeddingProvider 实例
    """
    if provider == "openai":
        return OpenAIEmbedder(**kwargs)
    
    elif provider == "local":
        return LocalEmbedder(**kwargs)
    
    elif provider == "mock":
        return MockEmbedder(**kwargs)
    
    elif provider == "auto":
        # 自动选择最佳可用提供者
        # 1. 检查 OpenAI API Key
        if OPENAI_AVAILABLE and os.getenv("OPENAI_API_KEY"):
            logging.info("Using OpenAI embedder")
            return OpenAIEmbedder(**kwargs)
        
        # 2. 尝试本地模型
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            logging.info("Using local sentence-transformers embedder")
            return LocalEmbedder(**kwargs)
        
        # 3. 回退到 Mock
        logging.warning("No embedding provider available, using mock embedder")
        return MockEmbedder(**kwargs)
    
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")
