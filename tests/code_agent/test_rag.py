"""
RAG 模块测试
测试代码分块、向量化和语义搜索
"""

import pytest
import sys
import os
import tempfile
import shutil
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.rag.chunker import (
    CodeChunk,
    ChunkType,
    CodeChunker
)
from agent.code_agent.rag.embedder import (
    MockEmbedder,
    get_embedder
)
from agent.code_agent.rag.index import (
    CodeIndex,
    SearchResult
)
from agent.code_agent.rag.search import (
    SemanticSearchTool
)


# ============ Fixtures ============

@pytest.fixture
def temp_workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_rag_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_python_code():
    """示例 Python 代码"""
    return '''"""
量化交易策略模块
包含 RSI 策略实现
"""

import pandas as pd
import numpy as np
from typing import List, Optional


class RSIStrategy:
    """RSI 策略类
    
    使用相对强弱指数(RSI)进行交易决策
    """
    
    def __init__(self, period: int = 14, overbought: float = 70, oversold: float = 30):
        """初始化策略参数
        
        Args:
            period: RSI 计算周期
            overbought: 超买阈值
            oversold: 超卖阈值
        """
        self.period = period
        self.overbought = overbought
        self.oversold = oversold
    
    def calculate_rsi(self, prices: pd.Series) -> pd.Series:
        """计算 RSI 指标
        
        Args:
            prices: 价格序列
            
        Returns:
            RSI 值序列
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def generate_signals(self, prices: pd.Series) -> pd.Series:
        """生成交易信号
        
        Args:
            prices: 价格序列
            
        Returns:
            信号序列 (1=买入, -1=卖出, 0=持有)
        """
        rsi = self.calculate_rsi(prices)
        signals = pd.Series(0, index=prices.index)
        signals[rsi < self.oversold] = 1
        signals[rsi > self.overbought] = -1
        return signals


def backtest(strategy, prices: pd.Series, initial_capital: float = 100000) -> dict:
    """回测函数
    
    Args:
        strategy: 策略实例
        prices: 价格数据
        initial_capital: 初始资金
        
    Returns:
        回测结果字典
    """
    signals = strategy.generate_signals(prices)
    # 简化的回测逻辑
    returns = prices.pct_change() * signals.shift(1)
    cumulative_returns = (1 + returns).cumprod()
    
    return {
        "total_return": cumulative_returns.iloc[-1] - 1,
        "sharpe_ratio": returns.mean() / returns.std() * np.sqrt(252),
        "max_drawdown": (cumulative_returns / cumulative_returns.cummax() - 1).min()
    }


if __name__ == "__main__":
    # 测试代码
    prices = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109])
    strategy = RSIStrategy()
    result = backtest(strategy, prices)
    print(result)
'''


@pytest.fixture
def sample_file(temp_workspace, sample_python_code):
    """创建示例 Python 文件"""
    file_path = os.path.join(temp_workspace, "strategy.py")
    with open(file_path, 'w') as f:
        f.write(sample_python_code)
    return file_path


# ============ CodeChunker 测试 ============

class TestCodeChunker:
    """测试代码分块器"""
    
    def test_chunk_python_file(self, sample_file, sample_python_code):
        """测试 Python 文件分块"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        assert len(chunks) > 0
        
        # 检查块类型
        chunk_types = [c.chunk_type for c in chunks]
        assert ChunkType.CLASS in chunk_types
        assert ChunkType.FUNCTION in chunk_types or ChunkType.METHOD in chunk_types
    
    def test_chunk_extracts_class(self, sample_file):
        """测试提取类定义"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        class_chunks = [c for c in chunks if c.chunk_type == ChunkType.CLASS]
        
        assert len(class_chunks) >= 1
        
        rsi_class = next((c for c in class_chunks if c.name == "RSIStrategy"), None)
        assert rsi_class is not None
        assert "RSI 策略类" in (rsi_class.docstring or "")
    
    def test_chunk_extracts_methods(self, sample_file):
        """测试提取方法"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        method_chunks = [c for c in chunks if c.chunk_type == ChunkType.METHOD]
        
        method_names = [c.name for c in method_chunks]
        assert "__init__" in method_names
        assert "calculate_rsi" in method_names
        assert "generate_signals" in method_names
    
    def test_chunk_extracts_function(self, sample_file):
        """测试提取函数"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        func_chunks = [c for c in chunks if c.chunk_type == ChunkType.FUNCTION]
        
        func_names = [c.name for c in func_chunks]
        assert "backtest" in func_names
    
    def test_chunk_extracts_signature(self, sample_file):
        """测试提取函数签名"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        backtest_chunk = next(
            (c for c in chunks if c.name == "backtest"),
            None
        )
        
        assert backtest_chunk is not None
        assert backtest_chunk.signature is not None
        assert "strategy" in backtest_chunk.signature
        assert "prices" in backtest_chunk.signature
    
    def test_chunk_extracts_docstring(self, sample_file):
        """测试提取文档字符串"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        rsi_method = next(
            (c for c in chunks if c.name == "calculate_rsi"),
            None
        )
        
        assert rsi_method is not None
        assert rsi_method.docstring is not None
        assert "RSI 指标" in rsi_method.docstring
    
    def test_chunk_extracts_imports(self, sample_file):
        """测试提取导入"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        # 所有块应该有相同的导入信息
        for chunk in chunks:
            if chunk.imports:
                assert "pandas" in chunk.imports or any("pd" in i for i in chunk.imports)
    
    def test_chunk_to_embedding_text(self, sample_file):
        """测试生成嵌入文本"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        for chunk in chunks:
            text = chunk.to_embedding_text()
            
            assert len(text) > 0
            assert chunk.chunk_type.value in text
            
            if chunk.name:
                assert chunk.name in text
    
    def test_chunk_directory(self, temp_workspace, sample_python_code):
        """测试目录分块"""
        # 创建多个文件
        for i in range(3):
            file_path = os.path.join(temp_workspace, f"module_{i}.py")
            with open(file_path, 'w') as f:
                f.write(f"def func_{i}():\n    '''Function {i}'''\n    pass\n")
        
        chunker = CodeChunker()
        chunks = chunker.chunk_directory(temp_workspace)
        
        assert len(chunks) >= 3
        
        # 检查文件路径是相对路径
        for chunk in chunks:
            assert not os.path.isabs(chunk.file_path)
    
    def test_generic_chunking_for_large_file(self, temp_workspace):
        """测试大文件的通用分块"""
        # 创建一个大文件
        lines = [f"# Line {i}\nprint({i})\n" for i in range(200)]
        content = "\n".join(lines)
        
        file_path = os.path.join(temp_workspace, "large_script.py")
        with open(file_path, 'w') as f:
            f.write(content)
        
        chunker = CodeChunker(max_lines=50)
        chunks = chunker.chunk_file(file_path)
        
        # 应该被分成多个块
        assert len(chunks) > 1
    
    def test_syntax_error_fallback(self, temp_workspace):
        """测试语法错误时的回退"""
        # 创建有语法错误的文件
        file_path = os.path.join(temp_workspace, "broken.py")
        with open(file_path, 'w') as f:
            f.write("def broken(\n    pass")  # 语法错误
        
        chunker = CodeChunker()
        chunks = chunker.chunk_file(file_path)
        
        # 应该回退到通用分块
        assert len(chunks) >= 1


# ============ Embedder 测试 ============

class TestEmbedder:
    """测试向量嵌入器"""
    
    def test_mock_embedder_dimensions(self):
        """测试 Mock 嵌入器维度"""
        embedder = MockEmbedder(dimension=384)
        
        assert embedder.dimension == 384
        assert embedder.model_name == "mock-embedder"
    
    def test_mock_embedder_embed(self):
        """测试 Mock 嵌入向量生成"""
        embedder = MockEmbedder(dimension=128)
        
        texts = ["Hello world", "Test embedding"]
        vectors = embedder.embed(texts)
        
        assert vectors.shape == (2, 128)
    
    def test_mock_embedder_deterministic(self):
        """测试 Mock 嵌入器的确定性"""
        embedder = MockEmbedder(dimension=64)
        
        text = "Same text should produce same vector"
        
        vec1 = embedder.embed_single(text)
        vec2 = embedder.embed_single(text)
        
        np.testing.assert_array_almost_equal(vec1, vec2)
    
    def test_mock_embedder_normalized(self):
        """测试向量是否归一化"""
        embedder = MockEmbedder(dimension=128)
        
        vec = embedder.embed_single("Test normalization")
        norm = np.linalg.norm(vec)
        
        assert abs(norm - 1.0) < 1e-6
    
    def test_get_embedder_mock(self):
        """测试获取 Mock 嵌入器"""
        embedder = get_embedder("mock", dimension=256)
        
        assert isinstance(embedder, MockEmbedder)
        assert embedder.dimension == 256
    
    def test_embed_single(self):
        """测试单个文本嵌入"""
        embedder = MockEmbedder()
        
        vec = embedder.embed_single("Single text")
        
        assert vec.shape == (embedder.dimension,)


# ============ CodeIndex 测试 ============

class TestCodeIndex:
    """测试代码索引"""
    
    @pytest.fixture
    def index(self, temp_workspace):
        """创建测试索引"""
        index_path = os.path.join(temp_workspace, ".index")
        embedder = MockEmbedder(dimension=128)
        return CodeIndex(index_path, embedder)
    
    def test_index_chunks(self, index, sample_file):
        """测试索引代码块"""
        chunker = CodeChunker()
        chunks = chunker.chunk_file(sample_file)
        
        count = index.index_chunks(chunks)
        
        assert count > 0
        assert index.get_stats()["total_chunks"] == count
    
    def test_index_file(self, index, sample_file):
        """测试索引单个文件"""
        count = index.index_file(sample_file)
        
        assert count > 0
    
    def test_search(self, index, sample_file):
        """测试搜索功能"""
        index.index_file(sample_file)
        
        results = index.search("RSI 计算", top_k=3)
        
        assert len(results) > 0
        assert all(isinstance(r, SearchResult) for r in results)
        assert all(0 <= r.score <= 1 for r in results)
    
    def test_search_returns_relevant_results(self, index, sample_file):
        """测试搜索返回结果（Mock 嵌入器不保证语义相关性）"""
        index.index_file(sample_file)
        
        results = index.search("calculate RSI indicator", top_k=5)
        
        # Mock 嵌入器基于哈希，只验证返回了结果
        # 真实的语义搜索需要使用 OpenAI 或本地模型
        assert len(results) > 0
        
        # 验证结果结构正确
        for r in results:
            assert r.chunk is not None
            assert 0 <= r.score <= 1
            assert r.rank > 0
    
    def test_search_with_file_filter(self, index, temp_workspace):
        """测试带文件过滤的搜索"""
        # 创建多个文件
        file1 = os.path.join(temp_workspace, "module_a.py")
        file2 = os.path.join(temp_workspace, "module_b.py")
        
        with open(file1, 'w') as f:
            f.write("def func_a():\n    '''Function A'''\n    pass\n")
        with open(file2, 'w') as f:
            f.write("def func_b():\n    '''Function B'''\n    pass\n")
        
        index.index_directory(temp_workspace)
        
        results = index.search("function", file_filter="*_a.py")
        
        # 只应该返回 module_a.py 的结果
        for r in results:
            if r.score > 0:
                assert "module_a" in r.chunk.file_path
    
    def test_remove_file(self, index, temp_workspace):
        """测试移除文件"""
        file_path = os.path.join(temp_workspace, "to_remove.py")
        with open(file_path, 'w') as f:
            f.write("def remove_me():\n    pass\n")
        
        index.index_file(file_path)
        initial_count = index.get_stats()["total_chunks"]
        
        removed = index.remove_file(file_path)
        
        assert removed > 0
        assert index.get_stats()["total_chunks"] == initial_count - removed
    
    def test_index_persistence(self, temp_workspace, sample_file):
        """测试索引持久化"""
        index_path = os.path.join(temp_workspace, ".index")
        embedder = MockEmbedder(dimension=128)
        
        # 创建并填充索引
        index1 = CodeIndex(index_path, embedder)
        index1.index_file(sample_file)
        original_count = index1.get_stats()["total_chunks"]
        
        # 创建新索引实例（应该加载已有数据）
        index2 = CodeIndex(index_path, embedder)
        
        assert index2.get_stats()["total_chunks"] == original_count
    
    def test_clear_index(self, index, sample_file):
        """测试清空索引"""
        index.index_file(sample_file)
        assert index.get_stats()["total_chunks"] > 0
        
        index.clear()
        
        assert index.get_stats()["total_chunks"] == 0
    
    def test_no_duplicate_indexing(self, index, sample_file):
        """测试不重复索引"""
        count1 = index.index_file(sample_file)
        count2 = index.index_file(sample_file)  # 再次索引
        
        assert count2 == 0  # 不应该有新增


# ============ SemanticSearchTool 测试 ============

class TestSemanticSearchTool:
    """测试语义搜索工具"""
    
    @pytest.fixture
    def search_tool(self, temp_workspace, sample_python_code):
        """创建搜索工具"""
        # 创建示例文件
        file_path = os.path.join(temp_workspace, "strategy.py")
        with open(file_path, 'w') as f:
            f.write(sample_python_code)
        
        return SemanticSearchTool(
            workspace_path=temp_workspace,
            auto_index=True
        )
    
    def test_search_execution(self, search_tool):
        """测试搜索执行"""
        result = search_tool.execute(
            query="RSI calculation",
            top_k=3
        )
        
        assert result.success is True
        assert result.data["count"] >= 0
    
    def test_search_returns_formatted_output(self, search_tool):
        """测试搜索返回格式化输出"""
        result = search_tool.execute(
            query="trading strategy",
            top_k=5
        )
        
        assert result.success is True
        
        if result.data["count"] > 0:
            assert "相似度" in result.output
            assert "```python" in result.output
    
    def test_search_with_file_filter(self, search_tool):
        """测试带过滤的搜索"""
        result = search_tool.execute(
            query="function",
            file_filter="*.py"
        )
        
        assert result.success is True
    
    def test_get_index_stats(self, search_tool):
        """测试获取索引统计"""
        stats = search_tool.get_index_stats()
        
        assert "total_chunks" in stats
        assert stats["total_chunks"] > 0
    
    def test_update_file(self, search_tool, temp_workspace):
        """测试更新文件索引"""
        # 创建新文件
        new_file = os.path.join(temp_workspace, "new_module.py")
        with open(new_file, 'w') as f:
            f.write("def new_function():\n    '''New function'''\n    pass\n")
        
        count = search_tool.update_file("new_module.py")
        
        assert count > 0
    
    def test_rebuild_index(self, search_tool):
        """测试重建索引"""
        # 获取初始统计
        initial_stats = search_tool.get_index_stats()
        
        # 重建
        count = search_tool.rebuild_index()
        
        assert count > 0
        assert search_tool.get_index_stats()["total_chunks"] == count


# ============ SearchResult 测试 ============

class TestSearchResult:
    """测试搜索结果"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        chunk = CodeChunk(
            id="test:func",
            file_path="test.py",
            chunk_type=ChunkType.FUNCTION,
            content="def test(): pass",
            start_line=1,
            end_line=1,
            name="test"
        )
        
        result = SearchResult(
            chunk=chunk,
            score=0.85,
            rank=1
        )
        
        d = result.to_dict()
        
        assert d["score"] == 0.85
        assert d["rank"] == 1
        assert d["chunk"]["name"] == "test"


# ============ 集成测试 ============

class TestRAGIntegration:
    """RAG 集成测试"""
    
    def test_full_workflow(self, temp_workspace, sample_python_code):
        """测试完整工作流"""
        # 1. 创建文件
        file_path = os.path.join(temp_workspace, "strategy.py")
        with open(file_path, 'w') as f:
            f.write(sample_python_code)
        
        # 2. 初始化搜索工具
        tool = SemanticSearchTool(
            workspace_path=temp_workspace,
            auto_index=True
        )
        
        # 3. 执行搜索
        result = tool.execute(
            query="如何计算相对强弱指数 RSI",
            top_k=5
        )
        
        assert result.success is True
        
        # 4. 验证找到相关代码
        if result.data["count"] > 0:
            found_names = [
                r["chunk"]["name"] 
                for r in result.data["results"] 
                if r["chunk"].get("name")
            ]
            # 应该找到与 RSI 相关的代码
            assert len(found_names) > 0
    
    def test_multiple_files(self, temp_workspace):
        """测试多文件场景"""
        # 创建多个文件
        files = {
            "indicators.py": '''
def calculate_macd(prices):
    """计算 MACD 指标"""
    pass

def calculate_bollinger(prices):
    """计算布林带"""
    pass
''',
            "strategies.py": '''
class MomentumStrategy:
    """动量策略"""
    def generate_signals(self): pass
''',
            "utils.py": '''
def normalize_prices(prices):
    """价格归一化"""
    pass
'''
        }
        
        for name, content in files.items():
            with open(os.path.join(temp_workspace, name), 'w') as f:
                f.write(content)
        
        # 初始化并搜索
        tool = SemanticSearchTool(workspace_path=temp_workspace)
        
        # 搜索技术指标
        result = tool.execute(query="技术指标计算")
        
        assert result.success is True
        
        # 应该能搜索到多个文件的内容
        if result.data["count"] > 0:
            files_found = set(
                r["chunk"]["file_path"] 
                for r in result.data["results"]
            )
            assert len(files_found) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

