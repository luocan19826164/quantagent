# 量化代码 Agent 设计文档

> 版本: 1.0  
> 最后更新: 2026-01-17

## 1. 概述

### 1.1 目标

创建一个专门用于 **Python 量化编程** 的代码生成/编辑 Agent，提供类似 Lovable/Cursor 的交互体验。

### 1.2 核心功能

1. **聊天交互**：用户描述需求，Agent 生成/修改代码（流式输出）
2. **代码面板**：展示代码变更（可展开/折叠）
3. **文件浏览**：查看和编辑项目文件，支持 Python 语法高亮
4. **代码执行**：运行 Python 脚本，实时显示输出
5. **多项目支持**：每个用户可创建多个独立项目

---

## 2. 需求确认摘要

| 需求项 | 决策 |
|--------|------|
| 文件编辑 | ✅ 可编辑 |
| 代码执行 | ✅ MVP 支持（subprocess + 安全限制） |
| 代码存储 | 服务器持久化 `./workspaces/{user_id}/{project_id}/` |
| 量化框架 | 通用 Python（pandas/numpy），后期接入框架 API |
| 与规则 Agent 集成 | ❌ 独立运行 |
| browser_context | ❌ 移除 |
| 代码编辑器 | Prism.js（轻量高亮） |
| Diff 显示 | ❌ 暂不实现 |
| 项目管理 | 多项目 |
| LLM | 复用现有配置，默认 claude-sonnet-4 |

---

## 3. 系统架构

### 3.1 项目结构

```
backend/
├── agent/
│   ├── rule_collect_agent/        # 现有：规则收集
│   └── code_agent/                # 新增：代码生成 Agent
│       ├── __init__.py
│       ├── code_agent.py          # 主 Agent 类
│       ├── workspace_manager.py   # 工作区/项目管理
│       ├── executor.py            # 代码执行器
│       ├── context.py             # 上下文结构定义
│       └── prompts/
│           └── code_agent_prompt.yaml
├── utils/
│   └── llm_config.py              # 复用现有 LLM 配置
└── app.py                         # 添加新路由

frontend/
├── templates/
│   └── index.html                 # 添加代码 Agent 视图
└── static/
    ├── script.js                  # 添加代码 Agent 逻辑
    ├── style.css                  # 添加代码 Agent 样式
    └── lib/
        └── prism.js               # 代码高亮库
```

### 3.2 数据存储结构

```
./workspaces/
├── {user_id}/
│   ├── projects.json              # 项目列表元数据
│   ├── {project_id}/
│   │   ├── .meta.json             # 项目元数据
│   │   ├── main.py
│   │   ├── strategy/
│   │   │   └── rsi.py
│   │   └── utils/
│   │       └── indicators.py
│   └── {project_id_2}/
│       └── ...
```

---

## 4. 前端设计

### 4.1 页面布局

```
+------------------------------------------------------------------+
|侧边栏|                    量化代码 Agent                          |
|------|-----------------------------------------------------------|
|规则收集|  聊天区域        | 代码面板(可折叠) |  文件浏览器         |
|规则执行|  +------------+  |  +------------+  |  +-------------+   |
|代码Agent| | 对话历史   |  |  | 当前变更   |  |  | 📁 项目选择 |   |
|       |  |            |  |  |            |  |  | 📄 main.py  |   |
|       |  |            |  |  |            |  |  | 📁 strategy |   |
|       |  +------------+  |  +------------+  |  |   └ rsi.py  |   |
|       |  | 输入框     |  |  [展开/折叠]    |  +-------------+   |
|       |  | [发送]     |  |                 |  | 文件内容     |   |
|       |  +------------+  |                 |  | (可编辑+高亮)|   |
|       |                  |                 |  | [▶运行][保存]|   |
|       |                  |                 |  +-------------+   |
|       |                  |                 |  | 执行输出     |   |
|       |                  |                 |  | $ python ... |   |
+------------------------------------------------------------------+
```

### 4.2 交互流程

#### 聊天生成代码

```
1. 用户输入："帮我写一个 RSI 策略"
2. Agent 流式返回思考过程和代码
3. 代码面板实时显示生成的代码
4. 生成完成后，文件自动保存到项目目录
5. 文件树刷新，显示新文件
```

#### 执行代码

```
1. 用户在文件面板点击 "▶ 运行"
2. 显示执行状态："运行中..."
3. 输出区域流式显示 stdout/stderr
4. 执行完成显示状态和耗时
```

---

## 5. 代码执行设计

### 5.1 MVP 方案：subprocess + 安全限制

```
┌─────────────────────────────────────────────────────────────┐
│                      执行流程                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户点击 "▶ 运行"                                           │
│       ↓                                                     │
│  POST /api/code-agent/projects/{pid}/execute                │
│       ↓                                                     │
│  后端验证：                                                  │
│    ├─ 文件路径在用户工作区内                                  │
│    ├─ 文件是 .py 文件                                        │
│    └─ 用户有执行权限                                         │
│       ↓                                                     │
│  创建 subprocess：                                           │
│    ├─ cwd = 项目目录                                         │
│    ├─ timeout = 30s                                         │
│    └─ python = 系统 Python 或项目 venv                       │
│       ↓                                                     │
│  SSE 流式返回：                                              │
│    ├─ stdout → type: "stdout"                               │
│    ├─ stderr → type: "stderr"                               │
│    └─ 完成 → type: "done", exit_code, duration              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 执行控制与安全限制

| 限制项 | 值 | 说明 |
|--------|-----|------|
| 执行超时 | 可配置：1分钟/5分钟(默认)/30分钟/无限制 | 用户可选，回测可能需要较长时间 |
| 手动停止 | ✅ 支持 | 用户可随时点击"停止"终止执行 |
| 输出长度 | 100KB | 防止输出爆炸 |
| 文件路径 | 仅用户工作区 | 防止读写系统文件 |
| 网络访问 | 允许 | 量化需要获取行情数据 |
| 并发执行 | 每用户 1 个 | 防止资源耗尽 |
| 文件大小 | 1MB | 单文件最大 |

### 5.3 后续升级：Docker 隔离（Phase 2）

```
未来方案：
- 每个用户/项目一个 Docker 容器
- 容器内预装 Python + 常用量化库
- 通过 Docker API 管理生命周期
- 空闲自动释放资源
```

---

## 6. API 设计

### 6.1 项目管理

```
GET    /api/code-agent/projects                    # 获取用户所有项目
POST   /api/code-agent/projects                    # 创建新项目
GET    /api/code-agent/projects/{project_id}       # 获取项目详情
DELETE /api/code-agent/projects/{project_id}       # 删除项目
```

### 6.2 文件操作

```
GET    /api/code-agent/projects/{pid}/files        # 获取文件树
GET    /api/code-agent/projects/{pid}/files/{path} # 获取文件内容
PUT    /api/code-agent/projects/{pid}/files/{path} # 保存文件
POST   /api/code-agent/projects/{pid}/files/{path} # 创建文件
DELETE /api/code-agent/projects/{pid}/files/{path} # 删除文件
```

### 6.3 聊天与代码生成

```
POST   /api/code-agent/projects/{pid}/chat         # 发送消息（SSE 流式）
GET    /api/code-agent/projects/{pid}/history      # 获取聊天历史
```

### 6.4 代码执行

```
POST   /api/code-agent/projects/{pid}/execute      # 执行代码（SSE 流式）
POST   /api/code-agent/projects/{pid}/stop         # 停止执行
```

---

## 7. Agent 上下文结构

针对 Python 量化场景的简化上下文：

```python
@dataclass
class CodeAgentContext:
    """代码 Agent 上下文"""
    
    # === 元信息 ===
    session_id: str
    project_id: str
    timestamp: str
    agent_mode: Literal["code_edit", "debug", "plan", "explain"]
    
    # === 任务信息 ===
    task: TaskInfo  # user_goal, task_type, constraints
    
    # === 执行计划 ===
    plan: PlanInfo  # steps[], current_step
    
    # === 代码上下文 ===
    code_context: CodeContext
    #   - workspace_root: str
    #   - file_tree: List[str]
    #   - focused_file: FileInfo
    #   - symbol_index: SymbolIndex (classes, functions, imports)
    
    # === 执行上下文 ===
    execution_context: ExecutionContext
    #   - running_process: Optional[ProcessInfo]
    #   - recent_outputs: List[OutputRecord]
    
    # === 工具定义 ===
    tools: List[ToolDef]
    #   - read_file, write_file, list_files, execute_code, search_code
    
    # === 记忆 ===
    memory: MemoryContext
    #   - project_conventions: List[str]
    #   - recent_decisions: List[Decision]
    
    # === 环境 ===
    environment: EnvironmentInfo
    #   - python_version, installed_packages
    
    # === 安全 ===
    safety: SafetyConfig
    #   - allowed_actions, max_runtime_sec, max_file_size
```

### 7.1 完整 JSON Schema

```json
{
  "session_id": "uuid",
  "project_id": "uuid",
  "timestamp": "2026-01-17T12:00:00Z",
  "agent_mode": "code_edit",
  
  "task": {
    "user_goal": "生成一个 RSI 策略",
    "task_type": "generate",
    "constraints": ["使用 pandas", "支持多标的"]
  },
  
  "plan": {
    "steps": [
      {"id": 1, "description": "创建策略文件", "status": "done"},
      {"id": 2, "description": "实现 RSI 计算", "status": "in_progress"},
      {"id": 3, "description": "添加信号生成", "status": "pending"}
    ],
    "current_step": 2
  },
  
  "code_context": {
    "workspace_root": "./workspaces/user_123/project_456/",
    "file_tree": [
      "main.py",
      "strategy/rsi.py",
      "utils/indicators.py"
    ],
    "focused_file": {
      "path": "strategy/rsi.py",
      "content": "import pandas as pd\n...",
      "language": "python",
      "cursor": {"line": 10, "column": 0}
    },
    "symbol_index": {
      "classes": ["RSIStrategy"],
      "functions": ["calculate_rsi", "generate_signals"],
      "imports": ["pandas", "numpy"]
    }
  },
  
  "execution_context": {
    "running_process": null,
    "recent_outputs": [
      {
        "command": "python main.py",
        "exit_code": 0,
        "output": "RSI: 45.32\nSignal: BUY",
        "duration_ms": 320
      }
    ]
  },
  
  "tools": [
    {"name": "read_file", "description": "读取文件内容"},
    {"name": "write_file", "description": "写入或创建文件"},
    {"name": "list_files", "description": "列出目录内容"},
    {"name": "execute_code", "description": "执行 Python 脚本"},
    {"name": "search_code", "description": "搜索代码内容"}
  ],
  
  "memory": {
    "project_conventions": [
      "使用 type hints",
      "函数需要 docstring"
    ],
    "recent_decisions": [
      {"decision": "使用 pandas 计算指标", "reason": "性能更好"}
    ]
  },
  
  "environment": {
    "python_version": "3.11",
    "installed_packages": ["pandas", "numpy", "requests"]
  },
  
  "safety": {
    "allowed_actions": ["read", "write", "execute"],
    "max_runtime_sec": 30,
    "max_file_size_kb": 1024,
    "restricted_paths": ["../", "/etc", "/root"]
  }
}
```

---

## 8. 开发计划

### Phase 1: 基础框架（本次实现）

- [x] 设计文档
- [ ] 创建 `code_agent/` 目录结构
- [ ] 实现 `WorkspaceManager`（项目/文件管理）
- [ ] 实现 `CodeAgent` 主类
- [ ] 实现代码执行器 `Executor`
- [ ] 前端三栏布局
- [ ] 聊天功能（流式）
- [ ] 文件浏览和编辑（Prism.js 高亮）
- [ ] 代码执行（流式输出）

### Phase 2: 增强功能

- [ ] Docker 隔离执行
- [ ] Diff 显示
- [ ] 代码补全
- [ ] 项目模板
- [ ] 依赖管理（pip install）

### Phase 3: 量化集成

- [ ] 接入量化框架 API
- [ ] 回测结果可视化
- [ ] 策略性能分析

---

## 9. 数据库变更

新增表（如果需要持久化聊天历史）：

```sql
-- 代码项目表
CREATE TABLE code_projects (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    workspace_path TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 代码聊天历史表
CREATE TABLE code_chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    role TEXT NOT NULL,  -- 'user' or 'assistant'
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES code_projects(id)
);
```

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 代码执行安全 | 高 | 超时限制、路径限制、后续 Docker |
| 大文件处理 | 中 | 文件大小限制 1MB |
| LLM 生成错误代码 | 中 | 提供执行反馈，用户可编辑 |
| 并发执行资源 | 中 | 每用户限制 1 个执行进程 |

---

**文档完成，准备开始编码实现。**
