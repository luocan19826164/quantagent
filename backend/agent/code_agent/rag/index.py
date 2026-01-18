"""
代码向量索引
存储和检索代码块向量
"""

import os
import json
import logging
import pickle
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np

from .chunker import CodeChunk, CodeChunker
from .embedder import EmbeddingProvider, get_embedder


@dataclass
class SearchResult:
    """搜索结果"""
    chunk: CodeChunk
    score: float               # 相似度分数 (0-1)
    rank: int                  # 排名
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk": self.chunk.to_dict(),
            "score": self.score,
            "rank": self.rank
        }


class CodeIndex:
    """
    代码向量索引
    
    功能:
    1. 索引代码块
    2. 向量相似度搜索
    3. 持久化存储
    4. 增量更新
    """
    
    INDEX_FILE = "code_index.pkl"
    META_FILE = "code_index_meta.json"
    
    def __init__(self, 
                 index_path: str,
                 embedder: Optional[EmbeddingProvider] = None):
        """
        初始化索引
        
        Args:
            index_path: 索引存储路径
            embedder: 向量嵌入器
        """
        self.index_path = index_path
        self.embedder = embedder or get_embedder("auto")
        
        # 索引数据
        self._chunks: List[CodeChunk] = []
        self._vectors: Optional[np.ndarray] = None
        self._chunk_id_map: Dict[str, int] = {}  # chunk_id -> index
        
        # 元数据
        self._meta = {
            "created_at": None,
            "updated_at": None,
            "total_chunks": 0,
            "embedder_model": self.embedder.model_name,
            "dimension": self.embedder.dimension,
            "indexed_files": []
        }
        
        # 确保目录存在
        os.makedirs(index_path, exist_ok=True)
        
        # 尝试加载已有索引
        self._load_index()
    
    def index_chunks(self, chunks: List[CodeChunk], batch_size: int = 50) -> int:
        """
        索引代码块
        
        Args:
            chunks: 代码块列表
            batch_size: 批处理大小
            
        Returns:
            新增的块数量
        """
        if not chunks:
            return 0
        
        # 过滤已存在的块
        new_chunks = [c for c in chunks if c.id not in self._chunk_id_map]
        
        if not new_chunks:
            logging.info("No new chunks to index")
            return 0
        
        logging.info(f"Indexing {len(new_chunks)} new chunks...")
        
        # 批量生成向量
        all_vectors = []
        for i in range(0, len(new_chunks), batch_size):
            batch = new_chunks[i:i+batch_size]
            texts = [c.to_embedding_text() for c in batch]
            vectors = self.embedder.embed(texts)
            all_vectors.append(vectors)
        
        new_vectors = np.vstack(all_vectors)
        
        # 更新索引
        start_idx = len(self._chunks)
        for i, chunk in enumerate(new_chunks):
            self._chunk_id_map[chunk.id] = start_idx + i
        
        self._chunks.extend(new_chunks)
        
        if self._vectors is None:
            self._vectors = new_vectors
        else:
            self._vectors = np.vstack([self._vectors, new_vectors])
        
        # 更新元数据
        self._meta["updated_at"] = datetime.now().isoformat()
        self._meta["total_chunks"] = len(self._chunks)
        
        # 更新已索引文件列表
        indexed_files = set(self._meta["indexed_files"])
        for chunk in new_chunks:
            indexed_files.add(chunk.file_path)
        self._meta["indexed_files"] = list(indexed_files)
        
        # 保存索引
        self._save_index()
        
        logging.info(f"Indexed {len(new_chunks)} chunks, total: {len(self._chunks)}")
        return len(new_chunks)
    
    def index_file(self, file_path: str, content: Optional[str] = None) -> int:
        """索引单个文件"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(file_path, content)
        return self.index_chunks(chunks)
    
    def index_directory(self, dir_path: str, extensions: List[str] = ['.py']) -> int:
        """索引整个目录"""
        chunker = CodeChunker()
        chunks = chunker.chunk_directory(dir_path, extensions)
        return self.index_chunks(chunks)
    
    def search(self, 
              query: str,
              top_k: int = 5,
              min_score: float = 0.0,
              file_filter: Optional[str] = None) -> List[SearchResult]:
        """
        语义搜索
        
        Args:
            query: 搜索查询
            top_k: 返回的最大结果数
            min_score: 最小相似度阈值
            file_filter: 文件路径过滤（支持通配符）
            
        Returns:
            SearchResult 列表
        """
        if self._vectors is None or len(self._chunks) == 0:
            return []
        
        # 生成查询向量
        query_vector = self.embedder.embed_single(query)
        
        # 计算余弦相似度
        scores = self._cosine_similarity(query_vector, self._vectors)
        
        # 应用文件过滤
        if file_filter:
            mask = self._apply_file_filter(file_filter)
            scores = scores * mask
        
        # 获取 top_k 结果
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        results = []
        for rank, idx in enumerate(top_indices):
            score = float(scores[idx])
            if score < min_score:
                break
            
            results.append(SearchResult(
                chunk=self._chunks[idx],
                score=score,
                rank=rank + 1
            ))
        
        return results
    
    def search_by_file(self, file_path: str) -> List[CodeChunk]:
        """获取文件的所有块"""
        return [c for c in self._chunks if c.file_path == file_path]
    
    def remove_file(self, file_path: str) -> int:
        """从索引中移除文件"""
        indices_to_remove = [
            i for i, c in enumerate(self._chunks) 
            if c.file_path == file_path
        ]
        
        if not indices_to_remove:
            return 0
        
        # 移除块
        for i in sorted(indices_to_remove, reverse=True):
            chunk = self._chunks.pop(i)
            del self._chunk_id_map[chunk.id]
        
        # 移除向量
        mask = np.ones(len(self._vectors), dtype=bool)
        mask[indices_to_remove] = False
        self._vectors = self._vectors[mask] if any(mask) else None
        
        # 重建 ID 映射
        self._chunk_id_map = {c.id: i for i, c in enumerate(self._chunks)}
        
        # 更新元数据
        self._meta["total_chunks"] = len(self._chunks)
        if file_path in self._meta["indexed_files"]:
            self._meta["indexed_files"].remove(file_path)
        
        self._save_index()
        
        return len(indices_to_remove)
    
    def _cosine_similarity(self, query: np.ndarray, vectors: np.ndarray) -> np.ndarray:
        """计算余弦相似度"""
        # 归一化
        query_norm = query / (np.linalg.norm(query) + 1e-9)
        vectors_norm = vectors / (np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9)
        
        # 点积 = 余弦相似度（已归一化）
        return np.dot(vectors_norm, query_norm)
    
    def _apply_file_filter(self, pattern: str) -> np.ndarray:
        """应用文件过滤"""
        import fnmatch
        mask = np.zeros(len(self._chunks))
        for i, chunk in enumerate(self._chunks):
            if fnmatch.fnmatch(chunk.file_path, pattern):
                mask[i] = 1.0
        return mask
    
    def _save_index(self):
        """保存索引到磁盘"""
        # 保存主索引
        index_data = {
            "chunks": [c.to_dict() for c in self._chunks],
            "vectors": self._vectors
        }
        
        index_file = os.path.join(self.index_path, self.INDEX_FILE)
        with open(index_file, 'wb') as f:
            pickle.dump(index_data, f)
        
        # 保存元数据
        meta_file = os.path.join(self.index_path, self.META_FILE)
        with open(meta_file, 'w') as f:
            json.dump(self._meta, f, indent=2)
        
        logging.debug(f"Index saved to {self.index_path}")
    
    def _load_index(self) -> bool:
        """从磁盘加载索引"""
        index_file = os.path.join(self.index_path, self.INDEX_FILE)
        meta_file = os.path.join(self.index_path, self.META_FILE)
        
        if not os.path.exists(index_file):
            self._meta["created_at"] = datetime.now().isoformat()
            return False
        
        try:
            # 加载元数据
            if os.path.exists(meta_file):
                with open(meta_file, 'r') as f:
                    self._meta = json.load(f)
            
            # 检查嵌入模型是否匹配
            if self._meta.get("embedder_model") != self.embedder.model_name:
                logging.warning(
                    f"Embedder model mismatch: index={self._meta.get('embedder_model')}, "
                    f"current={self.embedder.model_name}. Rebuilding index..."
                )
                return False
            
            # 加载索引
            with open(index_file, 'rb') as f:
                index_data = pickle.load(f)
            
            # 重建块对象
            from .chunker import ChunkType
            self._chunks = []
            for chunk_dict in index_data["chunks"]:
                chunk_dict["chunk_type"] = ChunkType(chunk_dict["chunk_type"])
                self._chunks.append(CodeChunk(**chunk_dict))
            
            self._vectors = index_data["vectors"]
            
            # 重建 ID 映射
            self._chunk_id_map = {c.id: i for i, c in enumerate(self._chunks)}
            
            logging.info(f"Loaded index with {len(self._chunks)} chunks")
            return True
            
        except Exception as e:
            logging.error(f"Failed to load index: {e}")
            return False
    
    def clear(self):
        """清空索引"""
        self._chunks = []
        self._vectors = None
        self._chunk_id_map = {}
        self._meta["total_chunks"] = 0
        self._meta["indexed_files"] = []
        self._meta["updated_at"] = datetime.now().isoformat()
        self._save_index()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            "total_chunks": len(self._chunks),
            "total_files": len(self._meta.get("indexed_files", [])),
            "embedder_model": self._meta.get("embedder_model"),
            "dimension": self._meta.get("dimension"),
            "created_at": self._meta.get("created_at"),
            "updated_at": self._meta.get("updated_at"),
        }
