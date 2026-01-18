"""
E2E 测试配置和 Fixtures
"""

import os
import sys
import pytest
import subprocess
import time
import tempfile
import shutil
import signal
import socket
from typing import Generator

# Playwright imports
from playwright.sync_api import Page, Browser, BrowserContext, Playwright

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

# 测试服务器端口（使用默认 Flask 端口）
TEST_PORT = 8081
TEST_BASE_URL = f"http://localhost:{TEST_PORT}"


def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """等待服务器启动"""
    import requests
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code in [200, 302]:
                return True
        except:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="session")
def test_environment():
    """设置测试环境变量"""
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="e2e_test_")
    temp_db = os.path.join(temp_dir, "test.db")
    temp_workspace = os.path.join(temp_dir, "workspaces")
    os.makedirs(temp_workspace, exist_ok=True)
    
    env = {
        "FLASK_ENV": "testing",
        "DATABASE_PATH": temp_db,
        "CODE_AGENT_WORKSPACE_ROOT": temp_workspace,
        "FLASK_DEBUG": "0",
    }
    
    yield env, temp_dir
    
    # 清理临时目录
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def flask_server(test_environment) -> Generator[str, None, None]:
    """启动 Flask 测试服务器"""
    env, temp_dir = test_environment
    
    # 检查端口是否已被占用
    if is_port_in_use(TEST_PORT):
        print(f"Port {TEST_PORT} already in use, assuming server is running")
        yield TEST_BASE_URL
        return
    
    # 构建完整环境变量
    full_env = os.environ.copy()
    full_env.update(env)
    
    # 启动 Flask 服务器
    backend_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'backend')
    
    # 使用 nohup 和 & 启动后台进程
    process = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=backend_dir,
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        preexec_fn=os.setsid if hasattr(os, 'setsid') else None
    )
    
    # 等待服务器启动
    if not wait_for_server(TEST_BASE_URL, timeout=30):
        # 读取输出用于调试
        try:
            output, _ = process.communicate(timeout=2)
            print(f"Server output: {output.decode() if output else 'None'}")
        except:
            pass
        process.terminate()
        pytest.fail(f"Flask server failed to start on {TEST_BASE_URL}")
    
    print(f"Flask server started on {TEST_BASE_URL}")
    yield TEST_BASE_URL
    
    # 停止服务器
    try:
        if hasattr(os, 'killpg'):
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=10)
    except:
        process.kill()


@pytest.fixture(scope="session")
def browser_context_args():
    """浏览器上下文参数"""
    return {
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
    }


@pytest.fixture(scope="session")
def test_user(test_environment, flask_server):
    """创建测试用户并返回凭据"""
    env, temp_dir = test_environment
    
    # 初始化数据库并创建用户
    import database
    database.DB_PATH = env["DATABASE_PATH"]
    
    username = "e2e_test_user"
    password = "e2e_test_password"
    
    try:
        database.create_user(username, password)
    except:
        pass  # 用户可能已存在
    
    return {"username": username, "password": password}


@pytest.fixture
def logged_in_page(page: Page, flask_server: str, test_user: dict) -> Page:
    """已登录的页面"""
    # 访问首页
    page.goto(flask_server)
    
    # 等待页面加载
    page.wait_for_load_state("networkidle", timeout=10000)
    
    # 检查是否需要登录
    login_form = page.locator("#loginForm")
    if login_form.is_visible(timeout=3000):
        # 填写登录表单
        page.fill("#username", test_user["username"])
        page.fill("#password", test_user["password"])
        page.click("#loginBtn")
        
        # 等待登录完成
        page.wait_for_load_state("networkidle", timeout=10000)
    
    return page


@pytest.fixture
def code_agent_page(logged_in_page: Page) -> Page:
    """切换到 Code Agent 页面"""
    page = logged_in_page
    
    # 点击 Code Agent 导航
    nav_btn = page.locator("#navCodeAgent")
    try:
        if nav_btn.is_visible(timeout=2000):
            nav_btn.click()
            page.wait_for_timeout(500)  # 等待视图切换
    except:
        pass  # 可能导航按钮不存在
    
    return page


# Playwright 配置
@pytest.fixture(scope="session")
def browser_type_launch_args():
    """浏览器启动参数"""
    return {
        "headless": True,  # 无头模式运行
        "slow_mo": 50,     # 放慢操作便于调试
    }


def pytest_configure(config):
    """Pytest 配置"""
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
