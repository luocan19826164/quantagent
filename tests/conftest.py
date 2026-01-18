"""
Pytest 配置和共享 fixtures
"""

import os
import sys
import pytest
import tempfile
import shutil

# 添加 backend 到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


@pytest.fixture
def temp_workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_workspace_")
    yield temp_dir
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_python_file(temp_workspace):
    """创建示例 Python 文件"""
    content = '''"""示例模块"""

import pandas as pd
import numpy as np


class DataProcessor:
    """数据处理器"""
    
    def __init__(self, data):
        self.data = data
    
    def process(self):
        """处理数据"""
        return self.data * 2


def calculate_rsi(prices, period=14):
    """计算 RSI 指标"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def main():
    print("Hello World")


if __name__ == "__main__":
    main()
'''
    file_path = os.path.join(temp_workspace, "sample.py")
    with open(file_path, 'w') as f:
        f.write(content)
    return file_path

