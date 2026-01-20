"""
测试 SymbolIndex 扩展（Repo Map）
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from agent.code_agent.context import (
    SymbolIndex, SymbolInfo, FileSymbols,
    parse_python_symbols, build_symbol_index
)


class TestSymbolInfo:
    """测试 SymbolInfo"""
    
    def test_create_symbol(self):
        """测试创建符号"""
        symbol = SymbolInfo(
            name="calculate_rsi",
            symbol_type="function",
            file_path="indicators.py",
            line_start=10,
            line_end=25,
            signature="def calculate_rsi(prices, period=14) -> float"
        )
        
        assert symbol.name == "calculate_rsi"
        assert symbol.symbol_type == "function"
        assert symbol.file_path == "indicators.py"
        assert symbol.line_start == 10
    
    def test_symbol_to_dict(self):
        """测试转换为字典"""
        symbol = SymbolInfo(
            name="MyClass",
            symbol_type="class",
            file_path="test.py",
            line_start=1,
            signature="class MyClass",
            docstring="一个测试类"
        )
        
        d = symbol.to_dict()
        
        assert d["name"] == "MyClass"
        assert d["type"] == "class"
        assert d["file"] == "test.py"
        assert d["signature"] == "class MyClass"


class TestFileSymbols:
    """测试 FileSymbols"""
    
    def test_create_file_symbols(self):
        """测试创建文件符号"""
        symbols = [
            SymbolInfo(
                name="MyClass",
                symbol_type="class",
                file_path="test.py",
                line_start=1
            ),
            SymbolInfo(
                name="my_function",
                symbol_type="function",
                file_path="test.py",
                line_start=10
            )
        ]
        
        file_sym = FileSymbols(
            path="test.py",
            language="python",
            symbols=symbols,
            imports=["pandas", "numpy"],
            exports=["MyClass", "my_function"]
        )
        
        assert file_sym.path == "test.py"
        assert len(file_sym.symbols) == 2
        assert len(file_sym.imports) == 2
        assert len(file_sym.exports) == 2
    
    def test_file_symbols_to_dict(self):
        """测试转换为字典"""
        file_sym = FileSymbols(
            path="test.py",
            symbols=[
                SymbolInfo(name="foo", symbol_type="function", file_path="test.py", line_start=1)
            ]
        )
        
        d = file_sym.to_dict()
        
        assert d["path"] == "test.py"
        assert len(d["symbols"]) == 1


class TestSymbolIndex:
    """测试扩展后的 SymbolIndex"""
    
    def test_create_index(self):
        """测试创建索引"""
        index = SymbolIndex()
        
        assert len(index.classes) == 0
        assert len(index.file_symbols) == 0
        assert len(index.symbol_to_files) == 0
    
    def test_add_file_symbols(self):
        """测试添加文件符号"""
        index = SymbolIndex()
        
        file_sym = FileSymbols(
            path="test.py",
            symbols=[
                SymbolInfo(
                    name="MyClass",
                    symbol_type="class",
                    file_path="test.py",
                    line_start=1
                ),
                SymbolInfo(
                    name="my_function",
                    symbol_type="function",
                    file_path="test.py",
                    line_start=10
                )
            ],
            imports=["pandas"]
        )
        
        index.add_file_symbols(file_sym)
        
        assert len(index.file_symbols) == 1
        assert "MyClass" in index.classes
        assert "my_function" in index.functions
        assert "pandas" in index.imports
        assert "test.py" in index.symbol_to_files["MyClass"]
    
    def test_find_symbol(self):
        """测试查找符号"""
        index = SymbolIndex()
        
        file_sym = FileSymbols(
            path="test.py",
            symbols=[
                SymbolInfo(
                    name="calculate_rsi",
                    symbol_type="function",
                    file_path="test.py",
                    line_start=10
                )
            ]
        )
        
        index.add_file_symbols(file_sym)
        
        results = index.find_symbol("calculate_rsi")
        
        assert len(results) == 1
        assert results[0].name == "calculate_rsi"
    
    def test_get_file_summary(self):
        """测试获取文件摘要"""
        index = SymbolIndex()
        
        file_sym = FileSymbols(
            path="test.py",
            symbols=[
                SymbolInfo(
                    name="MyClass",
                    symbol_type="class",
                    file_path="test.py",
                    line_start=1
                )
            ]
        )
        
        index.add_file_symbols(file_sym)
        
        summary = index.get_file_summary("test.py")
        
        assert summary is not None
        assert summary["path"] == "test.py"
        assert len(summary["symbols"]) == 1
    
    def test_to_repo_map_string(self):
        """测试生成 Repo Map 字符串"""
        index = SymbolIndex()
        
        file_sym = FileSymbols(
            path="test.py",
            symbols=[
                SymbolInfo(
                    name="MyClass",
                    symbol_type="class",
                    file_path="test.py",
                    line_start=1,
                    signature="class MyClass"
                ),
                SymbolInfo(
                    name="my_function",
                    symbol_type="function",
                    file_path="test.py",
                    line_start=10,
                    signature="def my_function() -> None"
                )
            ]
        )
        
        index.add_file_symbols(file_sym)
        
        repo_map = index.to_repo_map_string()
        
        assert "test.py:" in repo_map
        assert "class MyClass" in repo_map
        assert "def my_function" in repo_map
    
    def test_to_dict(self):
        """测试转换为字典"""
        index = SymbolIndex()
        
        file_sym = FileSymbols(
            path="test.py",
            symbols=[
                SymbolInfo(name="foo", symbol_type="function", file_path="test.py", line_start=1)
            ]
        )
        
        index.add_file_symbols(file_sym)
        
        d = index.to_dict()
        
        assert d["file_count"] == 1
        assert d["total_symbols"] == 1
        assert "files" in d


class TestParsePythonSymbols:
    """测试 Python 符号解析"""
    
    def test_parse_simple_class(self):
        """测试解析简单类"""
        code = '''
class MyClass:
    """测试类"""
    pass
'''
        file_sym = parse_python_symbols("test.py", code)
        
        assert len(file_sym.symbols) == 1
        assert file_sym.symbols[0].name == "MyClass"
        assert file_sym.symbols[0].symbol_type == "class"
    
    def test_parse_function(self):
        """测试解析函数"""
        code = '''
def calculate_rsi(prices, period=14):
    """计算 RSI"""
    return 100
'''
        file_sym = parse_python_symbols("test.py", code)
        
        assert len(file_sym.symbols) == 1
        assert file_sym.symbols[0].name == "calculate_rsi"
        assert file_sym.symbols[0].symbol_type == "function"
    
    def test_parse_class_with_methods(self):
        """测试解析类及其方法"""
        code = '''
class DataProcessor:
    def __init__(self, data):
        self.data = data
    
    def process(self):
        return self.data * 2
'''
        file_sym = parse_python_symbols("test.py", code)
        
        # 应该有 1 个类 + 2 个方法
        assert len(file_sym.symbols) >= 1
        class_symbols = [s for s in file_sym.symbols if s.symbol_type == "class"]
        method_symbols = [s for s in file_sym.symbols if s.symbol_type == "method"]
        
        assert len(class_symbols) == 1
        assert len(method_symbols) >= 2
    
    def test_parse_imports(self):
        """测试解析导入"""
        code = '''
import pandas as pd
from typing import List, Dict
'''
        file_sym = parse_python_symbols("test.py", code)
        
        assert len(file_sym.imports) > 0
    
    def test_parse_exports(self):
        """测试解析 __all__"""
        code = '''
__all__ = ['MyClass', 'my_function']

class MyClass:
    pass

def my_function():
    pass
'''
        file_sym = parse_python_symbols("test.py", code)
        
        assert len(file_sym.exports) == 2
        assert "MyClass" in file_sym.exports
        assert "my_function" in file_sym.exports
    
    def test_parse_invalid_syntax(self):
        """测试无效语法"""
        code = '''
def invalid syntax here
'''
        # 应该不会抛出异常，返回空的符号列表
        file_sym = parse_python_symbols("test.py", code)
        
        assert isinstance(file_sym, FileSymbols)
        # 解析失败时应该返回空列表或很少的符号

