"""
集成测试配置和 Fixtures
"""

import os
import sys
import pytest
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))


@pytest.fixture(scope="function")
def app():
    """创建 Flask 应用（测试模式）- 每个测试函数独立"""
    # 设置测试环境变量
    os.environ['FLASK_ENV'] = 'testing'
    
    # 使用临时数据库文件 - 每个测试独立
    temp_db = tempfile.mktemp(suffix='.db', prefix='test_quantagent_')
    os.environ['DATABASE_PATH'] = temp_db
    
    # 使用临时工作区目录 - 必须在 import app 之前设置
    temp_workspace = tempfile.mkdtemp(prefix='test_workspace_')
    os.environ['CODE_AGENT_WORKSPACE_ROOT'] = temp_workspace
    
    # 强制重新加载 workspace_manager 模块以使用新的环境变量
    if 'agent.code_agent.workspace_manager' in sys.modules:
        del sys.modules['agent.code_agent.workspace_manager']
    if 'agent.code_agent' in sys.modules:
        del sys.modules['agent.code_agent']
    
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['SECRET_KEY'] = 'test-secret-key'
    
    # 初始化数据库
    import database
    database.DB_PATH = temp_db
    database.init_db()
    
    yield flask_app
    
    # 清理临时文件
    if os.path.exists(temp_db):
        try:
            os.remove(temp_db)
        except:
            pass
    if os.path.exists(temp_workspace):
        shutil.rmtree(temp_workspace, ignore_errors=True)


@pytest.fixture
def client(app):
    """Flask 测试客户端（未登录）"""
    return app.test_client()


@pytest.fixture
def authenticated_client(app):
    """已登录的 Flask 测试客户端"""
    import database
    
    # 创建测试用户
    test_username = "test_user_integration"
    test_password = "test_password_123"
    
    # 尝试创建用户（可能已存在）
    try:
        database.create_user(test_username, test_password)
    except Exception:
        pass  # 用户可能已存在
    
    # 创建客户端并登录
    client = app.test_client()
    
    with client.session_transaction() as sess:
        # 直接设置 session（模拟登录）
        user = database.verify_user(test_username, test_password)
        if user:
            sess['user_id'] = user['id']
            sess['username'] = user['username']
        else:
            # 如果验证失败，手动设置一个测试用户 ID
            sess['user_id'] = 1
            sess['username'] = test_username
    
    yield client


@pytest.fixture
def temp_workspace():
    """创建临时工作区"""
    temp_dir = tempfile.mkdtemp(prefix="test_integration_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_llm():
    """Mock LLM，避免真实 API 调用"""
    with patch('langchain_openai.ChatOpenAI') as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        
        # 模拟基本响应
        mock_response = MagicMock()
        mock_response.content = "我来帮你完成这个任务。"
        mock_response.tool_calls = []
        mock_instance.invoke.return_value = mock_response
        
        yield mock_instance


@pytest.fixture
def mock_docker():
    """Mock Docker，避免需要真实 Docker"""
    with patch('agent.code_agent.sandbox.container.docker') as mock:
        mock_client = MagicMock()
        mock.from_env.return_value = mock_client
        mock_client.ping.return_value = True
        
        mock_container = MagicMock()
        mock_container.id = "test_container_123"
        mock_container.status = "running"
        mock_container.exec_run.return_value = (0, b"Success")
        mock_client.containers.create.return_value = mock_container
        mock_client.containers.get.return_value = mock_container
        
        yield mock_client


@pytest.fixture
def sample_project_data():
    """示例项目数据"""
    return {
        "name": "test_strategy",
        "description": "Test project for integration testing"
    }


@pytest.fixture
def sample_python_file():
    """示例 Python 文件内容"""
    return '''"""
RSI 策略示例
"""

import pandas as pd

def calculate_rsi(prices, period=14):
    """计算 RSI 指标"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

if __name__ == "__main__":
    prices = pd.Series([100, 102, 101, 103, 105, 104, 106])
    rsi = calculate_rsi(prices)
    print(f"RSI: {rsi.iloc[-1]:.2f}")
'''


def get_project_id_from_response(data):
    """从 API 响应中提取 project_id"""
    # 支持多种可能的返回格式
    if 'project_id' in data:
        return data['project_id']
    if 'id' in data:
        return data['id']
    if 'project' in data:
        project = data['project']
        if isinstance(project, dict):
            return project.get('id') or project.get('project_id')
    return None
