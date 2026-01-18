# Code Agent 架构设计 V2

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户接口层                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Web Chat   │  │   API      │  │   CLI       │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Agent 核心层                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Agent Orchestrator                      │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐       │  │
│  │  │  Planner    │  │  Executor   │  │  Reflector  │       │  │
│  │  │ (任务规划)   │  │ (执行循环)  │  │ (反思修正)  │       │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    Context Manager                         │  │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐ │  │
│  │  │ 对话历史  │ │ 代码上下文 │ │ 执行状态  │ │ 记忆存储 │ │  │
│  │  │ 压缩/摘要  │ │ 窗口管理   │ │ 跟踪     │ │ 短期/长期│ │  │
│  │  └───────────┘ └───────────┘ └───────────┘ └──────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        工具层 (Tools)                            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Tool Router & Validator                   ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐     │
│  │ 文件操作     │ 代码理解     │ 执行环境     │ 搜索工具    │     │
│  ├─────────────┼─────────────┼─────────────┼─────────────┤     │
│  │ read_file   │ get_outline │ shell_exec  │ grep        │     │
│  │ write_file  │ find_refs   │ python_exec │ ripgrep     │     │
│  │ patch_file  │ get_symbols │ pip_install │ semantic    │     │
│  │ list_dir    │ get_imports │ run_tests   │ file_search │     │
│  │ delete_file │ analyze_ast │ lint_check  │             │     │
│  │ move_file   │ type_check  │ format_code │             │     │
│  └─────────────┴─────────────┴─────────────┴─────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      代码理解层 (Code Intelligence)              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ AST Parser  │  │ LSP Client  │  │ RAG Engine  │              │
│  │ (tree-sitter)│  │ (pylsp)    │  │ (向量索引)   │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│         │                │                │                      │
│         ▼                ▼                ▼                      │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                      Symbol Index                            ││
│  │  • 函数/类定义  • 导入关系  • 调用图  • 文件依赖             ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       执行沙箱层 (Sandbox)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Docker      │  │ 资源限制    │  │ 网络隔离    │              │
│  │ Container   │  │ (cgroups)   │  │ (可选放行)  │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## 二、核心组件详细设计

### 2.1 Plan-Execute Agent 循环 (带步骤追踪)

```python
class PlanExecuteAgent:
    """
    Plan-Execute 模式的 Agent
    
    核心理念：
    1. 先规划，再执行
    2. 每步执行后强制汇报状态
    3. 严格追踪进度，防止 LLM 飘离
    
    流程:
    ┌────────────────────────────────────────────────┐
    │  User Task                                      │
    └────────────────────────────────────────────────┘
                         │
                         ▼
    ┌────────────────────────────────────────────────┐
    │  Phase 1: PLAN                                  │
    │  • LLM 生成执行计划 (结构化 JSON)              │
    │  • 分解为 N 个步骤                             │
    │  • 用户确认（可选）                            │
    └────────────────────────────────────────────────┘
                         │
                         ▼
    ┌────────────────────────────────────────────────┐
    │  Phase 2: EXECUTE (循环)                        │
    │  for step in plan.steps:                       │
    │    1. 告诉 LLM 当前步骤                        │
    │    2. LLM 执行该步骤 (工具调用)                │
    │    3. 验证执行结果                             │
    │    4. 更新步骤状态                             │
    │    5. 如果失败，触发 REPLAN                    │
    └────────────────────────────────────────────────┘
                         │
                         ▼
    ┌────────────────────────────────────────────────┐
    │  Phase 3: VERIFY                                │
    │  • 检查所有步骤是否完成                        │
    │  • 运行验证（lint/test）                       │
    │  • 生成总结                                    │
    └────────────────────────────────────────────────┘
    """
    
    async def run(self, task: str) -> ExecutionResult:
        # ========== Phase 1: 生成计划 ==========
        plan = await self.create_plan(task)
        self.current_plan = plan
        
        yield {"type": "plan_created", "plan": plan.to_dict()}
        
        # ========== Phase 2: 逐步执行 ==========
        for step in plan.steps:
            # 标记当前步骤
            step.status = "in_progress"
            plan.current_step_id = step.id
            
            yield {
                "type": "step_started", 
                "step_id": step.id,
                "description": step.description,
                "progress": f"{step.id}/{len(plan.steps)}"
            }
            
            # 执行该步骤
            try:
                result = await self.execute_step(step, plan)
                
                # 验证步骤结果
                if not self.validate_step_result(step, result):
                    # 可选：触发重新规划
                    if self.should_replan(step, result):
                        plan = await self.replan(task, plan, step, result.error)
                        continue
                    else:
                        step.status = "failed"
                        yield {"type": "step_failed", "step_id": step.id, "error": result.error}
                        break
                
                step.status = "done"
                step.result = result
                
                yield {
                    "type": "step_completed",
                    "step_id": step.id,
                    "files_changed": result.files_changed
                }
                
            except Exception as e:
                step.status = "failed"
                yield {"type": "step_error", "step_id": step.id, "error": str(e)}
                break
        
        # ========== Phase 3: 验证和总结 ==========
        summary = await self.generate_summary(plan)
        yield {"type": "task_completed", "summary": summary, "plan": plan.to_dict()}
    
    async def create_plan(self, task: str) -> Plan:
        """
        让 LLM 生成结构化的执行计划
        """
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": PLAN_SYSTEM_PROMPT},
                {"role": "user", "content": f"任务: {task}\n\n请生成执行计划。"}
            ],
            response_format={"type": "json_object"}  # 强制 JSON 输出
        )
        
        plan_data = json.loads(response.content)
        return Plan(
            task=task,
            steps=[
                PlanStep(
                    id=i+1,
                    description=s["description"],
                    expected_outcome=s.get("expected_outcome"),
                    tools_needed=s.get("tools", [])
                )
                for i, s in enumerate(plan_data["steps"])
            ]
        )
    
    async def execute_step(self, step: PlanStep, plan: Plan) -> StepResult:
        """
        执行单个步骤 - 这里是关键的"防飘离"机制
        """
        # 构建步骤执行提示词 - 严格限定范围
        prompt = f"""
## 当前任务
{plan.task}

## 执行计划概览
{self.format_plan_overview(plan)}

## ⚠️ 当前步骤 (Step {step.id}/{len(plan.steps)})
【你必须且只能执行这一步】
{step.description}

预期结果: {step.expected_outcome}
可用工具: {step.tools_needed}

## 约束
1. 只执行当前步骤描述的内容
2. 不要提前执行后续步骤
3. 完成后报告结果
4. 如果遇到阻碍，说明原因

## 代码上下文
{self.get_relevant_context(step)}
"""
        
        # 调用 LLM 执行步骤
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": STEP_EXECUTION_PROMPT},
                {"role": "user", "content": prompt}
            ],
            tools=self.tools,
            tool_choice="auto"
        )
        
        # 执行工具调用
        if response.tool_calls:
            tool_results = await self.execute_tools(response.tool_calls)
            return StepResult(
                success=all(r.success for r in tool_results),
                tool_results=tool_results,
                files_changed=self.extract_changed_files(tool_results)
            )
        
        return StepResult(success=True, response=response.content)
    
    def format_plan_overview(self, plan: Plan) -> str:
        """格式化计划概览，显示进度"""
        lines = []
        for step in plan.steps:
            status_icon = {
                "pending": "⬜",
                "in_progress": "🔄",
                "done": "✅",
                "failed": "❌"
            }.get(step.status, "⬜")
            
            lines.append(f"{status_icon} Step {step.id}: {step.description}")
        
        return "\n".join(lines)
```

### 2.2 工具定义 (Function Calling Schema)

```python
TOOLS = [
    # ========== 文件操作 ==========
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容。支持指定行范围以节省 token。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对于项目根目录的文件路径"},
                    "start_line": {"type": "integer", "description": "起始行号（可选）"},
                    "end_line": {"type": "integer", "description": "结束行号（可选）"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "写入文件（覆盖或创建）。仅用于创建新文件或完全重写小文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": "精确修改文件的特定部分。使用 search/replace 模式，比重写整个文件更高效。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "patches": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "search": {"type": "string", "description": "要查找的精确内容（包含足够上下文以保证唯一性）"},
                                "replace": {"type": "string", "description": "替换后的内容"}
                            },
                            "required": ["search", "replace"]
                        }
                    }
                },
                "required": ["path", "patches"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录内容，返回文件/子目录列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "recursive": {"type": "boolean", "default": False},
                    "include_hidden": {"type": "boolean", "default": False}
                }
            }
        }
    },
    
    # ========== Shell 执行 ==========
    {
        "type": "function",
        "function": {
            "name": "shell_exec",
            "description": "执行 shell 命令。用于运行脚本、安装依赖、git 操作等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "cwd": {"type": "string", "description": "工作目录（可选）"},
                    "timeout": {"type": "integer", "default": 60, "description": "超时秒数"},
                    "env": {"type": "object", "description": "额外的环境变量"}
                },
                "required": ["command"]
            }
        }
    },
    
    # ========== 代码搜索 ==========
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "在代码中搜索文本/正则表达式，快速定位相关代码",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "搜索模式（支持正则）"},
                    "path": {"type": "string", "default": ".", "description": "搜索路径"},
                    "include": {"type": "string", "description": "文件类型过滤，如 '*.py'"},
                    "context_lines": {"type": "integer", "default": 2}
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": "语义搜索代码。用于模糊查找功能相关的代码段。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言描述，如 '处理用户登录的代码'"},
                    "top_k": {"type": "integer", "default": 5}
                },
                "required": ["query"]
            }
        }
    },
    
    # ========== 代码理解 ==========
    {
        "type": "function",
        "function": {
            "name": "get_file_outline",
            "description": "获取文件的结构大纲（类、函数、方法列表）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "查找符号的所有引用位置",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "函数名/类名/变量名"},
                    "path": {"type": "string", "description": "可选，限定搜索范围"}
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_definition",
            "description": "获取符号的定义位置和内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "context_file": {"type": "string", "description": "当前文件路径，帮助定位"}
                },
                "required": ["symbol"]
            }
        }
    },
    
    # ========== 代码质量 ==========
    {
        "type": "function",
        "function": {
            "name": "lint_check",
            "description": "运行代码静态检查（pylint/flake8）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录路径"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "运行测试用例",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "测试文件/目录"},
                    "pattern": {"type": "string", "description": "测试函数匹配模式"}
                }
            }
        }
    },
    
    # ========== 任务完成 ==========
    {
        "type": "function",
        "function": {
            "name": "task_complete",
            "description": "标记任务完成，提供总结",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "完成的工作总结"},
                    "files_changed": {"type": "array", "items": {"type": "string"}},
                    "next_steps": {"type": "array", "items": {"type": "string"}, "description": "建议的后续步骤"}
                },
                "required": ["summary"]
            }
        }
    }
]
```

### 2.3 代码索引系统

```python
class CodeIndex:
    """
    代码索引系统 - 提供快速的代码理解能力
    
    索引内容:
    1. 文件结构索引 (file_index)
    2. 符号索引 (symbol_index) - 函数、类、变量定义
    3. 导入关系索引 (import_index)
    4. 向量索引 (vector_index) - 语义搜索
    """
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.file_index = {}      # path -> FileInfo
        self.symbol_index = {}    # symbol_name -> [SymbolInfo]
        self.import_index = {}    # module -> [importing_files]
        self.vector_store = None  # ChromaDB / FAISS
        
    async def build_index(self):
        """构建/更新索引"""
        for file_path in self.iter_python_files():
            await self.index_file(file_path)
    
    async def index_file(self, path: str):
        """索引单个文件"""
        content = read_file(path)
        
        # 1. AST 解析
        tree = ast.parse(content)
        
        # 2. 提取符号
        symbols = self.extract_symbols(tree, path)
        for symbol in symbols:
            self.symbol_index.setdefault(symbol.name, []).append(symbol)
        
        # 3. 提取导入
        imports = self.extract_imports(tree)
        for imp in imports:
            self.import_index.setdefault(imp, []).append(path)
        
        # 4. 向量嵌入 (分块)
        chunks = self.chunk_code(content, path)
        embeddings = await self.embed_chunks(chunks)
        self.vector_store.add(chunks, embeddings)
    
    def search_symbol(self, name: str) -> List[SymbolInfo]:
        """查找符号定义"""
        return self.symbol_index.get(name, [])
    
    def find_references(self, symbol: str) -> List[Reference]:
        """查找符号引用"""
        results = []
        pattern = rf'\b{re.escape(symbol)}\b'
        for path in self.file_index:
            matches = grep(pattern, path)
            results.extend(matches)
        return results
    
    async def semantic_search(self, query: str, top_k: int = 5) -> List[CodeChunk]:
        """语义搜索"""
        query_embedding = await self.embed_text(query)
        return self.vector_store.search(query_embedding, top_k)
    
    def get_file_outline(self, path: str) -> FileOutline:
        """获取文件大纲"""
        content = read_file(path)
        tree = ast.parse(content)
        
        outline = FileOutline(path=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls_info = ClassInfo(
                    name=node.name,
                    line=node.lineno,
                    methods=[m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                )
                outline.classes.append(cls_info)
            elif isinstance(node, ast.FunctionDef) and node.col_offset == 0:
                outline.functions.append(FunctionInfo(
                    name=node.name,
                    line=node.lineno,
                    args=[a.arg for a in node.args.args]
                ))
        return outline
```

### 2.4 上下文管理器

```python
class ContextManager:
    """
    上下文管理器 - 智能管理 LLM 的输入上下文
    
    核心功能:
    1. 动态上下文窗口管理 (不超过 token 限制)
    2. 对话历史压缩/摘要
    3. 相关代码自动引入
    4. 优先级排序
    """
    
    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.conversation_history = []
        self.code_context = {}
        self.summaries = []
        
    def build_context(self, current_task: str) -> Context:
        """构建当前轮次的上下文"""
        context = Context()
        budget = self.max_tokens
        
        # 1. 系统提示 (必须)
        system_prompt = self.get_system_prompt()
        budget -= count_tokens(system_prompt)
        context.add_system(system_prompt)
        
        # 2. 当前任务 (必须)
        budget -= count_tokens(current_task)
        context.add_user(current_task)
        
        # 3. 相关代码上下文 (高优先级)
        relevant_code = self.get_relevant_code(current_task)
        for code_chunk in relevant_code:
            tokens = count_tokens(code_chunk)
            if budget - tokens < 10000:  # 保留空间给历史
                break
            budget -= tokens
            context.add_code_context(code_chunk)
        
        # 4. 对话历史 (按重要性)
        history = self.get_compressed_history(budget)
        context.add_history(history)
        
        return context
    
    def get_relevant_code(self, task: str) -> List[CodeChunk]:
        """获取与任务相关的代码"""
        # 1. 语义搜索
        semantic_results = self.code_index.semantic_search(task, top_k=10)
        
        # 2. 最近编辑的文件
        recent_files = self.get_recent_files()
        
        # 3. 合并并排序
        return self.merge_and_rank(semantic_results, recent_files)
    
    def compress_history(self):
        """压缩对话历史"""
        if len(self.conversation_history) > 20:
            # 将旧的对话总结为摘要
            old_messages = self.conversation_history[:-10]
            summary = self.llm.summarize(old_messages)
            self.summaries.append(summary)
            self.conversation_history = self.conversation_history[-10:]
```

### 2.5 Patch 文件系统

```python
class PatchFileSystem:
    """
    精确的文件修改系统 - 避免每次传输整个文件
    
    支持:
    1. search/replace 精确替换
    2. 行范围修改
    3. 多处修改的原子操作
    4. 修改预览和回滚
    """
    
    def apply_patches(self, path: str, patches: List[Patch]) -> PatchResult:
        """应用补丁"""
        content = self.read_file(path)
        original = content
        
        for patch in patches:
            if patch.search not in content:
                return PatchResult(
                    success=False,
                    error=f"Search string not found: {patch.search[:50]}..."
                )
            
            # 检查唯一性
            if content.count(patch.search) > 1:
                return PatchResult(
                    success=False,
                    error=f"Search string is not unique, found {content.count(patch.search)} occurrences"
                )
            
            content = content.replace(patch.search, patch.replace, 1)
        
        # 创建备份
        self.create_backup(path, original)
        
        # 写入
        self.write_file(path, content)
        
        # 生成 diff 用于显示
        diff = self.generate_diff(original, content, path)
        
        return PatchResult(success=True, diff=diff)
    
    def generate_diff(self, old: str, new: str, path: str) -> str:
        """生成 unified diff"""
        import difflib
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, 
                                     fromfile=f"a/{path}", 
                                     tofile=f"b/{path}")
        return ''.join(diff)
    
    def rollback(self, path: str):
        """回滚到上一版本"""
        backup = self.get_backup(path)
        if backup:
            self.write_file(path, backup)
```

### 2.6 Plan 追踪系统（防飘离核心）

```python
@dataclass
class PlanStep:
    """计划步骤"""
    id: int
    description: str
    status: Literal["pending", "in_progress", "done", "failed", "skipped"] = "pending"
    expected_outcome: str = ""
    tools_needed: List[str] = field(default_factory=list)
    
    # 执行记录
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)
    tool_calls: List[Dict] = field(default_factory=list)


@dataclass  
class Plan:
    """执行计划"""
    task: str
    steps: List[PlanStep]
    current_step_id: int = 1
    status: Literal["planning", "executing", "completed", "failed", "cancelled"] = "planning"
    
    # 元信息
    created_at: datetime = field(default_factory=datetime.now)
    version: int = 1  # 重新规划时版本+1
    replan_count: int = 0
    
    def get_current_step(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.id == self.current_step_id:
                return step
        return None
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度统计"""
        done = sum(1 for s in self.steps if s.status == "done")
        failed = sum(1 for s in self.steps if s.status == "failed")
        return {
            "total": len(self.steps),
            "done": done,
            "failed": failed,
            "pending": len(self.steps) - done - failed,
            "progress_percent": int(done / len(self.steps) * 100) if self.steps else 0,
            "current_step": self.current_step_id
        }
    
    def to_summary(self) -> str:
        """生成计划摘要（给 LLM 看）"""
        lines = [f"任务: {self.task}", "", "执行计划:"]
        for step in self.steps:
            icon = {"pending": "⬜", "in_progress": "🔄", "done": "✅", "failed": "❌"}.get(step.status, "⬜")
            current = " 👈 [当前]" if step.id == self.current_step_id else ""
            lines.append(f"  {icon} Step {step.id}: {step.description}{current}")
        return "\n".join(lines)


class PlanTracker:
    """
    计划追踪器 - 防止 LLM 飘离的核心组件
    
    功能:
    1. 追踪步骤执行状态
    2. 检测异常行为（跳步、偏离、死循环）
    3. 提供进度报告
    4. 触发重新规划
    """
    
    def __init__(self):
        self.current_plan: Optional[Plan] = None
        self.execution_history: List[Dict] = []
        self.anomaly_count: int = 0
        
    def set_plan(self, plan: Plan):
        self.current_plan = plan
        self.anomaly_count = 0
        
    def start_step(self, step_id: int):
        """标记步骤开始"""
        step = self._get_step(step_id)
        if step:
            step.status = "in_progress"
            step.started_at = datetime.now()
            self.current_plan.current_step_id = step_id
    
    def complete_step(self, step_id: int, result: Dict):
        """标记步骤完成"""
        step = self._get_step(step_id)
        if step:
            step.status = "done"
            step.completed_at = datetime.now()
            step.result = result.get("response")
            step.files_changed = result.get("files_changed", [])
            step.tool_calls = result.get("tool_calls", [])
            
            self.execution_history.append({
                "step_id": step_id,
                "timestamp": datetime.now().isoformat(),
                "result": result
            })
    
    def fail_step(self, step_id: int, error: str):
        """标记步骤失败"""
        step = self._get_step(step_id)
        if step:
            step.status = "failed"
            step.error = error
            step.completed_at = datetime.now()
    
    def detect_anomaly(self, llm_response: str, expected_step: PlanStep) -> Optional[str]:
        """
        检测 LLM 响应是否偏离当前步骤
        
        检测类型:
        1. 跳步 - LLM 提前执行后续步骤
        2. 偏离 - LLM 做了计划外的事情
        3. 死循环 - 重复执行相同操作
        4. 放弃 - LLM 说"我做不到"但实际上可以
        """
        anomalies = []
        
        # 1. 检测是否提及后续步骤的内容
        for step in self.current_plan.steps:
            if step.id > expected_step.id:
                if self._mentions_step_content(llm_response, step):
                    anomalies.append(f"跳步警告: 提前涉及 Step {step.id} 的内容")
        
        # 2. 检测是否执行了未预期的文件修改
        unexpected_files = self._detect_unexpected_files(llm_response, expected_step)
        if unexpected_files:
            anomalies.append(f"偏离警告: 修改了未预期的文件 {unexpected_files}")
        
        # 3. 检测死循环
        if self._detect_loop():
            anomalies.append("死循环警告: 检测到重复执行相同操作")
        
        if anomalies:
            self.anomaly_count += 1
            return "; ".join(anomalies)
        
        return None
    
    def should_replan(self) -> bool:
        """判断是否需要重新规划"""
        if not self.current_plan:
            return False
        
        # 连续多次异常
        if self.anomaly_count >= 3:
            return True
        
        # 当前步骤失败且无法恢复
        current_step = self.current_plan.get_current_step()
        if current_step and current_step.status == "failed":
            return True
        
        return False
    
    def get_correction_prompt(self, anomaly: str) -> str:
        """生成修正提示词"""
        return f"""
⚠️ 检测到执行偏离:
{anomaly}

请严格按照当前步骤执行:
- 当前步骤: Step {self.current_plan.current_step_id}
- 步骤描述: {self.current_plan.get_current_step().description}

不要执行其他步骤的内容。如果当前步骤有困难，请说明原因而不是跳过。
"""
    
    def _get_step(self, step_id: int) -> Optional[PlanStep]:
        if not self.current_plan:
            return None
        for step in self.current_plan.steps:
            if step.id == step_id:
                return step
        return None
```

### 2.7 防飘离策略总结

| 策略 | 实现方式 |
|------|----------|
| **强制结构化计划** | LLM 必须先输出 JSON 格式的计划 |
| **步骤隔离执行** | 每次只告诉 LLM 当前步骤，屏蔽细节 |
| **进度追踪** | 每步执行前后更新状态，生成进度报告 |
| **异常检测** | 检查 LLM 是否跳步、偏离、死循环 |
| **修正机制** | 检测到偏离时，注入修正提示词 |
| **重新规划** | 连续失败或严重偏离时，重新生成计划 |
| **上下文裁剪** | 只提供当前步骤相关的代码上下文 |
| **Token 预算** | 限制每步的 token 消耗，防止无限输出 |

## 三、关键缺失功能（审查补充）

### 🔴 3.1 人机交互控制（关键！）

当前设计假设 Agent 全自动执行，缺少用户干预能力：

```python
class HumanInTheLoop:
    """
    人机协作控制
    
    用户应该能够：
    1. 审批/拒绝计划
    2. 修改计划步骤
    3. 中途暂停/取消
    4. 手动执行某步骤
    5. 跳过某步骤
    """
    
    async def request_plan_approval(self, plan: Plan) -> ApprovalResult:
        """
        请求用户审批计划
        
        Returns:
            - approved: 批准执行
            - rejected: 拒绝，重新规划
            - modified: 用户修改了计划
        """
        yield {"type": "plan_review", "plan": plan.to_dict(), "awaiting_approval": True}
        
        # 等待用户响应（WebSocket 或轮询）
        user_decision = await self.wait_for_user_decision(timeout=300)
        
        if user_decision.action == "approve":
            return ApprovalResult(approved=True)
        elif user_decision.action == "reject":
            return ApprovalResult(approved=False, reason=user_decision.reason)
        elif user_decision.action == "modify":
            return ApprovalResult(approved=True, modified_plan=user_decision.new_plan)
    
    async def checkpoint(self, step: PlanStep, result: StepResult):
        """
        步骤完成后的检查点
        
        允许用户：
        - 继续执行下一步
        - 重试当前步骤
        - 跳过后续步骤
        - 取消整个任务
        """
        if self.auto_mode:
            return CheckpointAction.CONTINUE
        
        yield {
            "type": "checkpoint",
            "step_id": step.id,
            "result": result.to_dict(),
            "options": ["continue", "retry", "skip", "cancel"]
        }
        
        return await self.wait_for_checkpoint_decision()


# 前端需要的交互界面
HUMAN_IN_LOOP_EVENTS = {
    "plan_review": "显示计划，等待用户批准/修改",
    "step_preview": "执行前预览将要执行的操作",
    "checkpoint": "步骤完成后检查点",
    "confirmation": "危险操作确认（如删除文件）",
    "input_required": "需要用户提供额外信息"
}
```

### 🔴 3.2 Git 版本控制（关键！）

量化代码必须有版本管理：

```python
class GitIntegration:
    """
    Git 集成 - 代码变更必须有版本控制
    
    功能:
    1. 每次任务完成后自动 commit
    2. 支持回滚到任意版本
    3. 分支管理（实验性策略用分支）
    4. 查看变更历史
    """
    
    def __init__(self, project_path: str):
        self.repo = git.Repo(project_path)
    
    def auto_commit(self, message: str, files: List[str] = None):
        """任务完成后自动提交"""
        if files:
            self.repo.index.add(files)
        else:
            self.repo.git.add(A=True)
        
        self.repo.index.commit(f"[CodeAgent] {message}")
    
    def create_checkpoint(self, name: str) -> str:
        """创建检查点（用于回滚）"""
        tag_name = f"checkpoint_{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.repo.create_tag(tag_name)
        return tag_name
    
    def rollback(self, target: str):
        """回滚到指定提交/标签"""
        self.repo.git.checkout(target, force=True)
    
    def get_diff(self, file_path: str = None) -> str:
        """获取变更 diff"""
        if file_path:
            return self.repo.git.diff('HEAD', file_path)
        return self.repo.git.diff('HEAD')
    
    def get_history(self, limit: int = 20) -> List[CommitInfo]:
        """获取提交历史"""
        return [
            CommitInfo(
                hash=c.hexsha[:8],
                message=c.message,
                author=c.author.name,
                date=c.committed_datetime,
                files_changed=list(c.stats.files.keys())
            )
            for c in self.repo.iter_commits(max_count=limit)
        ]
    
    def create_branch(self, name: str):
        """创建分支（用于实验性策略）"""
        self.repo.create_head(name)
    
    def switch_branch(self, name: str):
        """切换分支"""
        self.repo.heads[name].checkout()


# 工具定义
GIT_TOOLS = [
    {
        "name": "git_commit",
        "description": "提交当前变更",
        "parameters": {"message": "string"}
    },
    {
        "name": "git_diff",
        "description": "查看文件变更",
        "parameters": {"file_path": "string (optional)"}
    },
    {
        "name": "git_history",
        "description": "查看提交历史",
        "parameters": {"limit": "int"}
    },
    {
        "name": "git_rollback",
        "description": "回滚到指定版本",
        "parameters": {"target": "string (commit hash or tag)"}
    }
]
```

### 🔴 3.3 量化领域工具（核心！）

这是**量化编程平台**，必须有领域特定工具：

```python
QUANT_TOOLS = [
    # ========== 数据获取 ==========
    {
        "name": "fetch_market_data",
        "description": "获取市场行情数据（K线、Tick等）",
        "parameters": {
            "symbol": "string (e.g., 'BTC/USDT', 'AAPL')",
            "timeframe": "string (e.g., '1h', '1d')",
            "start_date": "string (ISO format)",
            "end_date": "string (ISO format)",
            "source": "string (binance/yfinance/ccxt)"
        }
    },
    {
        "name": "fetch_crypto_data",
        "description": "获取加密货币数据（通过 CCXT）",
        "parameters": {
            "exchange": "string (binance/okx/bybit)",
            "symbol": "string",
            "timeframe": "string"
        }
    },
    {
        "name": "fetch_stock_data",
        "description": "获取股票数据（通过 yfinance）",
        "parameters": {
            "symbol": "string",
            "period": "string (1d/5d/1mo/1y)"
        }
    },
    
    # ========== 指标计算 ==========
    {
        "name": "calculate_indicator",
        "description": "计算技术指标",
        "parameters": {
            "indicator": "string (RSI/MACD/MA/BOLL/ATR/...)",
            "data_variable": "string (变量名)",
            "params": "object (指标参数)"
        }
    },
    
    # ========== 回测 ==========
    {
        "name": "run_backtest",
        "description": "运行策略回测",
        "parameters": {
            "strategy_file": "string (策略文件路径)",
            "start_date": "string",
            "end_date": "string",
            "initial_capital": "number",
            "commission": "number"
        }
    },
    {
        "name": "get_backtest_report",
        "description": "获取回测报告（收益率、夏普比等）",
        "parameters": {
            "backtest_id": "string"
        }
    },
    
    # ========== 可视化 ==========
    {
        "name": "plot_chart",
        "description": "生成图表（K线图、收益曲线等）",
        "parameters": {
            "chart_type": "string (candlestick/line/equity_curve)",
            "data_variable": "string",
            "indicators": "array (叠加的指标)",
            "output_path": "string"
        }
    },
    
    # ========== 策略模板 ==========
    {
        "name": "use_strategy_template",
        "description": "使用策略模板生成代码",
        "parameters": {
            "template": "string (ma_cross/rsi_mean_reversion/breakout/...)",
            "params": "object (模板参数)"
        }
    }
]


class QuantToolkit:
    """量化工具包"""
    
    async def fetch_market_data(self, symbol: str, timeframe: str, 
                                 start_date: str, end_date: str,
                                 source: str = "yfinance") -> pd.DataFrame:
        """获取行情数据"""
        if source == "yfinance":
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=start_date, end=end_date, interval=timeframe)
            return df
        elif source == "ccxt":
            import ccxt
            exchange = getattr(ccxt, self.config.exchange)()
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=start_date)
            return self._ohlcv_to_dataframe(ohlcv)
    
    def calculate_indicator(self, indicator: str, data: pd.DataFrame, 
                           **params) -> pd.Series:
        """计算技术指标"""
        import talib
        
        indicator_map = {
            "RSI": lambda: talib.RSI(data['close'], **params),
            "MACD": lambda: talib.MACD(data['close'], **params),
            "MA": lambda: talib.SMA(data['close'], **params),
            "EMA": lambda: talib.EMA(data['close'], **params),
            "BOLL": lambda: talib.BBANDS(data['close'], **params),
            "ATR": lambda: talib.ATR(data['high'], data['low'], data['close'], **params),
        }
        
        if indicator.upper() in indicator_map:
            return indicator_map[indicator.upper()]()
        raise ValueError(f"Unknown indicator: {indicator}")
    
    async def run_backtest(self, strategy_file: str, **params) -> BacktestResult:
        """运行回测"""
        # 支持多种回测引擎
        if self.backtest_engine == "backtrader":
            return await self._run_backtrader(strategy_file, **params)
        elif self.backtest_engine == "vectorbt":
            return await self._run_vectorbt(strategy_file, **params)
        else:
            return await self._run_simple_backtest(strategy_file, **params)
```

### 🔴 3.4 Docker 沙箱隔离（修订）

```python
class DockerSandbox:
    """
    Docker 沙箱 - 隔离用户代码执行，保护宿主机
    
    设计理念：
    1. 每个用户/项目在独立容器中执行
    2. LLM 可以在容器内自由 pip install
    3. 宿主机完全隔离，不受影响
    4. 资源限制防止滥用
    """
    
    # 基础镜像（预装常用量化库）
    BASE_IMAGE = "quantagent/python-sandbox:latest"
    
    # Dockerfile 示例
    DOCKERFILE = """
    FROM python:3.11-slim
    
    # 预装常用库（加速用户体验）
    RUN pip install --no-cache-dir \
        pandas numpy scipy \
        yfinance ccxt ta-lib \
        matplotlib plotly \
        requests python-dotenv
    
    # 创建工作目录
    WORKDIR /workspace
    
    # 非 root 用户运行
    RUN useradd -m sandbox
    USER sandbox
    """
    
    def __init__(self, user_id: int, project_id: str):
        self.user_id = user_id
        self.project_id = project_id
        self.container_name = f"quant_sandbox_{user_id}_{project_id}"
        self.client = docker.from_env()
    
    def get_or_create_container(self) -> Container:
        """获取或创建容器"""
        try:
            container = self.client.containers.get(self.container_name)
            if container.status != "running":
                container.start()
            return container
        except docker.errors.NotFound:
            return self._create_container()
    
    def _create_container(self) -> Container:
        """创建新容器"""
        # 项目目录路径
        project_path = f"/data/workspaces/{self.user_id}/{self.project_id}"
        
        container = self.client.containers.run(
            self.BASE_IMAGE,
            name=self.container_name,
            detach=True,
            tty=True,
            
            # 资源限制
            mem_limit="2g",           # 内存限制 2GB
            cpu_period=100000,
            cpu_quota=50000,          # CPU 限制 50%
            
            # 文件系统
            volumes={
                project_path: {"bind": "/workspace", "mode": "rw"}
            },
            working_dir="/workspace",
            
            # 网络策略
            network_mode="bridge",    # 允许网络（用于 pip install、数据API）
            
            # 安全
            read_only=False,          # 允许写入 /workspace
            security_opt=["no-new-privileges"],
            
            # 自动清理
            auto_remove=False,        # 保留容器复用
        )
        return container
    
    def exec_shell(self, command: str, timeout: int = 60) -> ExecResult:
        """在容器内执行 shell 命令"""
        container = self.get_or_create_container()
        
        try:
            exit_code, output = container.exec_run(
                cmd=["bash", "-c", command],
                workdir="/workspace",
                demux=True,
                timeout=timeout
            )
            
            stdout = output[0].decode() if output[0] else ""
            stderr = output[1].decode() if output[1] else ""
            
            return ExecResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                success=(exit_code == 0)
            )
        except Exception as e:
            return ExecResult(exit_code=-1, stderr=str(e), success=False)
    
    def exec_python(self, file_path: str, timeout: int = 300) -> Generator:
        """在容器内执行 Python 文件（流式输出）"""
        container = self.get_or_create_container()
        
        exec_id = container.client.api.exec_create(
            container.id,
            cmd=["python", file_path],
            workdir="/workspace",
            stdout=True,
            stderr=True,
            tty=False
        )
        
        output = container.client.api.exec_start(exec_id, stream=True, demux=True)
        
        for stdout, stderr in output:
            if stdout:
                yield {"type": "stdout", "content": stdout.decode()}
            if stderr:
                yield {"type": "stderr", "content": stderr.decode()}
        
        # 获取退出码
        result = container.client.api.exec_inspect(exec_id)
        yield {"type": "exit", "exit_code": result["ExitCode"]}
    
    def pip_install(self, package: str) -> ExecResult:
        """在容器内安装包（无需白名单，容器隔离保证安全）"""
        return self.exec_shell(f"pip install {package}", timeout=120)
    
    def cleanup(self):
        """清理容器（用户删除项目时调用）"""
        try:
            container = self.client.containers.get(self.container_name)
            container.stop()
            container.remove()
        except docker.errors.NotFound:
            pass
    
    def get_status(self) -> Dict:
        """获取容器状态"""
        try:
            container = self.client.containers.get(self.container_name)
            stats = container.stats(stream=False)
            return {
                "status": container.status,
                "memory_usage_mb": stats["memory_stats"]["usage"] / 1024 / 1024,
                "cpu_percent": self._calculate_cpu_percent(stats)
            }
        except docker.errors.NotFound:
            return {"status": "not_created"}


# 容器池管理（可选优化）
class ContainerPool:
    """
    容器池 - 预创建容器，减少冷启动时间
    
    策略：
    1. 维护 N 个空闲容器
    2. 用户请求时分配一个
    3. 用户完成后回收（清理状态）
    """
    
    def __init__(self, pool_size: int = 5):
        self.pool_size = pool_size
        self.available = queue.Queue()
        self.in_use = {}
    
    def acquire(self, user_id: int) -> Container:
        """获取一个容器"""
        if not self.available.empty():
            container = self.available.get()
            self.in_use[user_id] = container
            return container
        else:
            # 创建新容器
            return self._create_pooled_container()
    
    def release(self, user_id: int):
        """归还容器"""
        container = self.in_use.pop(user_id, None)
        if container:
            self._reset_container(container)
            self.available.put(container)
```

### 🟡 3.5 依赖管理（简化版）

由于有 Docker 隔离，依赖管理可以大大简化：

```python
class DependencyManager:
    """
    依赖管理器
    
    功能:
    1. 管理 requirements.txt
    2. 虚拟环境管理
    3. 依赖冲突检测
    4. 安全的 pip install
    """
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.requirements_path = os.path.join(project_path, "requirements.txt")
        self.venv_path = os.path.join(project_path, ".venv")
    
    def get_installed_packages(self) -> Dict[str, str]:
        """获取已安装的包"""
        result = subprocess.run(
            [self.pip_path, "list", "--format=json"],
            capture_output=True, text=True
        )
        packages = json.loads(result.stdout)
        return {p["name"]: p["version"] for p in packages}
    
    def install_package(self, package: str, version: str = None) -> InstallResult:
        """安装包（带安全检查）"""
        # 安全检查：只允许白名单内的包
        if not self._is_allowed_package(package):
            return InstallResult(success=False, error=f"Package {package} is not in whitelist")
        
        spec = f"{package}=={version}" if version else package
        result = subprocess.run(
            [self.pip_path, "install", spec],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            self._update_requirements(package, version)
            return InstallResult(success=True)
        return InstallResult(success=False, error=result.stderr)
    
    def _is_allowed_package(self, package: str) -> bool:
        """检查包是否在白名单中"""
        ALLOWED_PACKAGES = {
            # 数据处理
            "pandas", "numpy", "scipy",
            # 量化
            "yfinance", "ccxt", "ta-lib", "backtrader", "vectorbt",
            # 可视化
            "matplotlib", "plotly", "mplfinance",
            # 机器学习
            "scikit-learn", "xgboost", "lightgbm",
            # 工具
            "requests", "python-dotenv", "pyyaml",
        }
        return package.lower() in ALLOWED_PACKAGES


# 工具定义
DEPENDENCY_TOOLS = [
    {
        "name": "pip_install",
        "description": "安装 Python 包（仅限白名单内的包）",
        "parameters": {
            "package": "string",
            "version": "string (optional)"
        }
    },
    {
        "name": "pip_list",
        "description": "列出已安装的包",
        "parameters": {}
    },
    {
        "name": "check_dependencies",
        "description": "检查项目依赖是否满足",
        "parameters": {}
    }
]
```

### 🔴 3.5 可观测性/监控

```python
class AgentObservability:
    """
    Agent 可观测性
    
    监控内容:
    1. Token 消耗
    2. 执行时间
    3. 工具调用统计
    4. 错误率
    5. 任务成功率
    """
    
    def __init__(self):
        self.metrics = {
            "total_tokens": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_cost_usd": 0.0,
            "tool_calls": defaultdict(int),
            "errors": [],
            "task_history": []
        }
    
    def record_llm_call(self, usage: TokenUsage, model: str):
        """记录 LLM 调用"""
        self.metrics["total_tokens"] += usage.total_tokens
        self.metrics["prompt_tokens"] += usage.prompt_tokens
        self.metrics["completion_tokens"] += usage.completion_tokens
        
        # 计算费用
        cost = self._calculate_cost(usage, model)
        self.metrics["total_cost_usd"] += cost
    
    def record_tool_call(self, tool_name: str, duration_ms: int, success: bool):
        """记录工具调用"""
        self.metrics["tool_calls"][tool_name] += 1
        
    def get_session_summary(self) -> Dict:
        """获取会话统计摘要"""
        return {
            "token_usage": {
                "total": self.metrics["total_tokens"],
                "prompt": self.metrics["prompt_tokens"],
                "completion": self.metrics["completion_tokens"]
            },
            "estimated_cost_usd": round(self.metrics["total_cost_usd"], 4),
            "tool_calls": dict(self.metrics["tool_calls"]),
            "error_count": len(self.metrics["errors"]),
            "tasks_completed": len([t for t in self.metrics["task_history"] if t["success"]])
        }
    
    def export_logs(self, format: str = "json") -> str:
        """导出执行日志"""
        pass


# 前端显示的统计面板
OBSERVABILITY_UI = """
┌─────────────────────────────────────┐
│        📊 Agent 统计面板            │
├─────────────────────────────────────┤
│ Token 消耗: 15,234 / 128,000       │
│ 预估费用: $0.0456                   │
│ 任务进度: 3/5 步骤完成              │
│ 工具调用: read_file(5), shell(2)   │
│ 错误次数: 1                         │
└─────────────────────────────────────┘
"""
```

### 🔴 3.6 会话持久化

```python
class SessionPersistence:
    """
    会话持久化
    
    功能:
    1. 保存/恢复任务状态
    2. 保存执行历史
    3. 断点续执行
    """
    
    def save_session(self, session_id: str, state: AgentState):
        """保存会话状态"""
        data = {
            "session_id": session_id,
            "created_at": state.created_at.isoformat(),
            "updated_at": datetime.now().isoformat(),
            "task": state.task,
            "plan": state.plan.to_dict() if state.plan else None,
            "conversation_history": state.conversation_history,
            "execution_history": state.execution_history,
            "context_summary": state.context.to_summary()
        }
        
        # 存储到数据库
        self.db.sessions.upsert(session_id, data)
    
    def restore_session(self, session_id: str) -> AgentState:
        """恢复会话状态"""
        data = self.db.sessions.get(session_id)
        if not data:
            raise SessionNotFound(session_id)
        
        state = AgentState()
        state.task = data["task"]
        state.plan = Plan.from_dict(data["plan"]) if data["plan"] else None
        state.conversation_history = data["conversation_history"]
        # ...
        
        return state
    
    def list_sessions(self, user_id: int) -> List[SessionInfo]:
        """列出用户的所有会话"""
        pass
    
    def resume_task(self, session_id: str) -> Generator:
        """从断点恢复执行"""
        state = self.restore_session(session_id)
        
        if state.plan and state.plan.status == "executing":
            # 找到未完成的步骤，继续执行
            current_step = state.plan.get_current_step()
            if current_step and current_step.status == "in_progress":
                yield {"type": "resuming", "step_id": current_step.id}
                # 继续执行...
```

### 🟡 3.7 缺失功能优先级总结

| 优先级 | 功能 | 原因 |
|--------|------|------|
| 🔴 P0 | **人机交互控制** | 用户必须能控制 Agent，不能完全自动 |
| 🔴 P0 | **Git 版本控制** | 量化代码必须有版本管理，支持回滚 |
| 🔴 P0 | **量化工具包** | 这是量化平台的核心价值 |
| 🔴 P1 | **依赖管理** | 项目必须能管理依赖 |
| 🟡 P1 | **可观测性** | 需要监控 token 消耗和错误 |
| 🟡 P1 | **会话持久化** | 支持断点续执行 |
| 🟢 P2 | 多模型支持 | 不同任务用不同模型 |
| 🟢 P2 | 协作功能 | 多用户项目（后期） |

## 四、实现路线图（修订版）

### Phase 0: Agent 核心框架 (1周) 🔴
- [ ] Plan-Execute Agent 主循环
- [ ] Plan 追踪系统（防飘离）
- [ ] 人机交互控制（计划审批、检查点、取消）
- [ ] Function Calling 标准化处理

### Phase 1: 核心工具层 (1-2周) 🔴
- [ ] Shell 执行工具 (基础版，宿主机执行)
- [ ] Patch/搜索替换文件修改
- [ ] Grep/Ripgrep 代码搜索
- [ ] 简单版本备份（快照/回滚）
- [ ] 文件大纲提取（简单 AST）

### Phase 2: Docker 沙箱隔离 (1-2周) 🔴
- [ ] Docker 容器管理（创建/销毁/复用）
- [ ] 用户隔离（每用户独立容器或容器池）
- [ ] Shell 命令在容器内执行（pip install 等）
- [ ] Python 代码在容器内执行
- [ ] 资源限制（CPU、内存、磁盘）
- [ ] 网络策略（允许访问数据API，禁止其他）
- [ ] 文件系统挂载（项目目录映射）

### Phase 3: 代码理解 + RAG 语义搜索 (2-3周)
- [ ] 代码分块（简单 AST 辅助，按函数/类切分）
- [ ] 向量化存储（ChromaDB / FAISS）
- [ ] 语义搜索工具（自然语言 → 相关代码）
- [ ] 增量索引更新（文件变更时）
- [ ] 相关代码自动引入上下文

### Phase 4: 上下文管理 + 可观测性 (1-2周)
- [ ] 上下文窗口管理（Token 预算）
- [ ] 对话历史压缩/摘要
- [ ] Token 消耗统计
- [ ] 执行日志
- [ ] 会话持久化（断点续执行）

## 四、技术选型

| 组件 | 推荐方案 | 备选 |
|------|----------|------|
| AST 解析 | tree-sitter | ast (Python内置) |
| LSP | pylsp + jedi | pyright |
| 向量数据库 | ChromaDB | FAISS, Qdrant |
| Embedding | text-embedding-3-small | Cohere, BGE |
| 沙箱 | Docker | gVisor, Firecracker |
| 代码搜索 | ripgrep | grep |

## 五、文件结构（重构后）

```
backend/agent/code_agent/
├── __init__.py
├── agent.py              # Agent 主循环
├── context/
│   ├── __init__.py
│   ├── manager.py        # 上下文管理器
│   ├── compressor.py     # 历史压缩
│   └── window.py         # 窗口管理
├── tools/
│   ├── __init__.py
│   ├── base.py           # 工具基类
│   ├── file_ops.py       # 文件操作工具
│   ├── shell.py          # Shell 执行
│   ├── search.py         # 搜索工具
│   └── code_intel.py     # 代码理解工具
├── index/
│   ├── __init__.py
│   ├── ast_parser.py     # AST 解析
│   ├── symbol_index.py   # 符号索引
│   ├── vector_store.py   # 向量存储
│   └── lsp_client.py     # LSP 客户端
├── sandbox/
│   ├── __init__.py
│   ├── executor.py       # 代码执行器
│   └── docker.py         # Docker 沙箱
├── llm/
│   ├── __init__.py
│   ├── client.py         # LLM 客户端
│   └── function_call.py  # Function Calling 处理
└── prompts/
    ├── system.yaml
    └── tools.yaml
```

