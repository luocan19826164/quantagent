# Code Agent 集成测试计划

## 1. 测试架构概述

### 1.1 测试层次

```
┌─────────────────────────────────────────────────────────────────┐
│                         测试金字塔                               │
├─────────────────────────────────────────────────────────────────┤
│  Level 3: E2E 测试 (端到端)                                      │
│  ├── 启动完整服务（后端 + 前端）                                  │
│  ├── 使用 Playwright/Selenium 模拟浏览器操作                     │
│  └── 覆盖核心用户场景                                            │
├─────────────────────────────────────────────────────────────────┤
│  Level 2: API 集成测试                                           │
│  ├── Flask 测试客户端（无需启动服务器）                           │
│  ├── 或 HTTP 请求测试（启动服务器）                               │
│  └── 测试 API 端点和业务流程                                     │
├─────────────────────────────────────────────────────────────────┤
│  Level 1: 单元测试 (已完成 144 个)                               │
│  ├── 组件独立测试                                               │
│  └── Mock 外部依赖                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 测试工具栈

| 层级 | 工具 | 用途 |
|------|------|------|
| 单元测试 | pytest + Mock | 组件测试 |
| API 集成测试 | Flask test client / requests | API 测试 |
| E2E 测试 | Playwright | 浏览器自动化 |
| 性能测试 | locust | 负载测试 |

---

## 2. 关键用户场景 (User Stories)

### 2.1 Code Agent 核心场景

#### 场景 1: 创建项目并生成代码
```
用户故事: 作为用户，我想创建一个量化项目并让 AI 生成 RSI 策略代码
步骤:
1. 创建新项目 "my_strategy"
2. 发送消息: "帮我写一个 RSI 策略"
3. AI 生成计划并等待审批
4. 用户审批计划
5. AI 执行计划，生成代码文件
6. 用户查看生成的代码
预期结果: 项目中存在 RSI 策略代码文件
```

#### 场景 2: 修改现有代码
```
用户故事: 作为用户，我想修改已有的策略代码
步骤:
1. 选择已有项目
2. 发送消息: "把 RSI 周期从 14 改成 21"
3. AI 识别需要修改的文件
4. AI 使用 patch 修改代码
5. 用户查看修改后的代码
预期结果: 代码中 RSI 周期变为 21
```

#### 场景 3: 执行代码
```
用户故事: 作为用户，我想运行生成的回测代码
步骤:
1. 选择项目和文件
2. 点击运行
3. 等待执行完成
4. 查看输出结果
预期结果: 显示回测结果（收益率、夏普比率等）
```

#### 场景 4: 代码搜索
```
用户故事: 作为用户，我想找到计算指标的相关代码
步骤:
1. 发送消息: "找到计算 MACD 的代码"
2. AI 使用语义搜索
3. 返回相关代码片段
预期结果: 显示 MACD 相关的代码位置和内容
```

#### 场景 5: 安装依赖
```
用户故事: 作为用户，我想安装 ta-lib 库
步骤:
1. 发送消息: "安装 ta-lib 库"
2. AI 执行 pip install
3. 显示安装结果
预期结果: ta-lib 安装成功
```

### 2.2 错误处理场景

#### 场景 6: 代码执行超时
```
用户故事: 当代码执行时间过长时，用户可以取消
步骤:
1. 运行一个无限循环的代码
2. 等待几秒
3. 点击取消按钮
预期结果: 执行被终止，显示超时信息
```

#### 场景 7: 语法错误处理
```
用户故事: 当生成的代码有语法错误时，AI 应该能修复
步骤:
1. 创建一个有语法错误的文件
2. 发送消息: "运行 main.py"
3. 执行失败，显示错误
4. AI 自动尝试修复
预期结果: 显示错误信息，提供修复建议
```

### 2.3 版本管理场景

#### 场景 8: 代码回滚
```
用户故事: 作为用户，我想回滚到之前的代码版本
步骤:
1. 修改代码多次
2. 查看版本历史
3. 选择某个版本回滚
预期结果: 代码恢复到选择的版本
```

---

## 3. API 集成测试用例

### 3.1 项目管理 API

| 测试ID | API | 方法 | 测试场景 | 预期结果 |
|--------|-----|------|---------|----------|
| API-01 | /api/code-agent/projects | POST | 创建项目 | 201, 返回项目ID |
| API-02 | /api/code-agent/projects | GET | 获取项目列表 | 200, 返回项目数组 |
| API-03 | /api/code-agent/projects/{id} | GET | 获取项目详情 | 200, 返回项目信息 |
| API-04 | /api/code-agent/projects/{id} | DELETE | 删除项目 | 200, 项目被删除 |
| API-05 | /api/code-agent/projects/{id} | POST | 创建重复名称项目 | 400, 名称冲突 |

### 3.2 文件管理 API

| 测试ID | API | 方法 | 测试场景 | 预期结果 |
|--------|-----|------|---------|----------|
| API-10 | /api/code-agent/projects/{id}/files | GET | 获取文件列表 | 200, 返回文件树 |
| API-11 | /api/code-agent/projects/{id}/files/{path} | GET | 读取文件 | 200, 返回文件内容 |
| API-12 | /api/code-agent/projects/{id}/files/{path} | PUT | 保存文件 | 200, 文件已保存 |
| API-13 | /api/code-agent/projects/{id}/files/{path} | DELETE | 删除文件 | 200, 文件已删除 |
| API-14 | /api/code-agent/projects/{id}/files/{path} | GET | 读取不存在文件 | 404, 文件不存在 |

### 3.3 对话 API

| 测试ID | API | 方法 | 测试场景 | 预期结果 |
|--------|-----|------|---------|----------|
| API-20 | /api/code-agent/projects/{id}/chat | POST | 发送消息 | 200, SSE 流式响应 |
| API-21 | /api/code-agent/projects/{id}/chat | POST | 发送空消息 | 400, 参数错误 |
| API-22 | /api/code-agent/projects/{id}/chat | POST | 项目不存在 | 404, 项目不存在 |

### 3.4 代码执行 API

| 测试ID | API | 方法 | 测试场景 | 预期结果 |
|--------|-----|------|---------|----------|
| API-30 | /api/code-agent/projects/{id}/execute | POST | 执行 Python 脚本 | 200, 返回执行结果 |
| API-31 | /api/code-agent/projects/{id}/stop | POST | 停止执行 | 200, 执行已停止 |
| API-32 | /api/code-agent/projects/{id}/status | GET | 获取执行状态 | 200, 返回状态 |
| API-33 | /api/code-agent/projects/{id}/execute | POST | 执行超时 | 200, timeout 状态 |

### 3.5 计划审批 API

| 测试ID | API | 方法 | 测试场景 | 预期结果 |
|--------|-----|------|---------|----------|
| API-40 | /api/code-agent/projects/{id}/plan/approve | POST | 审批计划 | 200, 开始执行 |
| API-41 | /api/code-agent/projects/{id}/plan/reject | POST | 拒绝计划 | 200, 计划已取消 |
| API-42 | /api/code-agent/projects/{id}/plan/cancel | POST | 取消执行 | 200, 执行已取消 |

---

## 4. E2E 测试用例

### 4.1 完整用户流程

```python
# test_e2e_code_agent.py (Playwright)

async def test_create_project_and_generate_code():
    """E2E: 创建项目并生成代码"""
    # 1. 打开应用
    await page.goto("http://localhost:5001")
    
    # 2. 切换到 Code Agent
    await page.click("#navCodeAgent")
    
    # 3. 创建项目
    await page.click("#createProjectBtn")
    await page.fill("#projectNameInput", "test_strategy")
    await page.click("#confirmCreateBtn")
    
    # 4. 发送消息
    await page.fill("#codeAgentInput", "帮我写一个简单的 RSI 策略")
    await page.click("#sendCodeAgentBtn")
    
    # 5. 等待计划生成
    await page.wait_for_selector(".plan-approval-dialog")
    
    # 6. 审批计划
    await page.click("#approvePlanBtn")
    
    # 7. 等待执行完成
    await page.wait_for_selector(".execution-complete", timeout=60000)
    
    # 8. 验证文件生成
    file_tree = await page.query_selector_all(".file-tree-item")
    assert len(file_tree) > 0
```

### 4.2 测试场景清单

| E2E-ID | 场景 | 前置条件 | 操作步骤 | 验证点 |
|--------|------|---------|---------|--------|
| E2E-01 | 首页加载 | 无 | 访问首页 | 页面正常显示 |
| E2E-02 | 切换到 Code Agent | 首页 | 点击导航 | Code Agent 视图显示 |
| E2E-03 | 创建项目 | Code Agent 视图 | 创建新项目 | 项目出现在列表 |
| E2E-04 | 发送消息 | 有项目 | 输入并发送 | 显示 AI 响应 |
| E2E-05 | 查看生成代码 | AI 生成代码后 | 点击文件 | 代码编辑器显示 |
| E2E-06 | 执行代码 | 有 Python 文件 | 点击运行 | 显示执行结果 |
| E2E-07 | 停止执行 | 代码正在运行 | 点击停止 | 执行终止 |

---

## 5. 测试环境配置

### 5.1 测试数据库
```python
# conftest.py
@pytest.fixture
def test_db():
    """使用独立的测试数据库"""
    test_db_path = "test_quant.db"
    # 初始化测试数据库
    yield test_db_path
    # 清理
    os.remove(test_db_path)
```

### 5.2 Mock LLM
```python
@pytest.fixture
def mock_llm():
    """Mock LLM 响应，避免真实 API 调用"""
    with patch("langchain_openai.ChatOpenAI") as mock:
        mock.return_value.invoke.return_value = MockResponse(
            content="我来帮你创建 RSI 策略...",
            tool_calls=[...]
        )
        yield mock
```

### 5.3 Docker 环境
```python
@pytest.fixture
def docker_sandbox():
    """确保 Docker 可用"""
    if not is_docker_available():
        pytest.skip("Docker not available")
    yield
    cleanup_test_containers()
```

---

## 6. 执行策略

### 6.1 CI/CD 集成
```yaml
# .github/workflows/test.yml
jobs:
  unit-test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/code_agent/ -v

  api-integration-test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/integration/api/ -v

  e2e-test:
    runs-on: ubuntu-latest
    services:
      docker:
    steps:
      - run: playwright install
      - run: pytest tests/e2e/ -v
```

### 6.2 测试执行顺序
1. **单元测试** - 每次提交必须通过
2. **API 集成测试** - 每次 PR 必须通过
3. **E2E 测试** - 发布前必须通过

### 6.3 测试覆盖率目标
| 层级 | 目标覆盖率 |
|------|-----------|
| 单元测试 | > 80% |
| API 测试 | 100% 端点 |
| E2E 测试 | 核心场景 100% |

---

## 7. 测试报告

### 7.1 报告格式
```bash
# 生成 HTML 报告
pytest --html=report.html --self-contained-html

# 生成覆盖率报告
pytest --cov=backend --cov-report=html
```

### 7.2 关键指标
- 测试通过率
- 代码覆盖率
- 执行时间
- 失败用例详情

