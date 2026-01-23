# 对话历史保持优化方案（简化版）

## 问题分析

### 当前问题
用户在同一浏览器会话中切换项目时，对话消息被清空，但实际上：
- ✅ 后端 Agent 实例是缓存的（`code_agent_cache`）
- ✅ Agent 的 `context.conversation` 仍然存在
- ❌ 前端切换项目时调用了 `clearCodeAgentChat()` 清空了 DOM 中的消息

### 问题代码
```javascript
// frontend/static/script.js:1097-1109
async function selectCodeAgentProject(projectId) {
    if (!projectId) {
        codeAgentCurrentProject = null;
        codeAgentFiles = [];
        renderCodeAgentFileTree([]);
        clearCodeAgentEditor();
        return;
    }

    codeAgentCurrentProject = projectId;
    await loadCodeAgentFiles();
    clearCodeAgentChat(); // ❌ 这里清空了所有消息
}
```

### 根本原因
1. **前端消息只存在 DOM 中**：消息通过 `appendCodeAgentMessage()` 添加到 DOM，没有持久化
2. **切换项目时清空**：`clearCodeAgentChat()` 直接清空 DOM，导致消息丢失
3. **后端上下文还在**：Agent 实例的 `context.conversation` 仍然存在，但前端无法恢复显示

## 解决方案

### 核心思路
**前端按项目保存和恢复消息，切换项目时不清空，而是替换为新项目的消息**

### 实现方案

#### 1. 消息存储结构
```javascript
// 全局变量：按项目存储消息
let codeAgentMessagesCache = {}; // { projectId: [messages...] }
```

#### 2. 消息保存时机
- **发送消息时**：保存到缓存
- **接收消息时**：保存到缓存
- **切换项目前**：保存当前项目消息到缓存

#### 3. 消息恢复时机
- **切换项目时**：从缓存恢复新项目的消息
- **页面加载时**：如果有当前项目，恢复消息

#### 4. 消息格式
```javascript
{
  type: 'user' | 'bot',
  content: string, // HTML 内容
  timestamp: string
}
```

## 实现步骤

### Step 1: 添加消息缓存管理函数

```javascript
// 保存当前项目消息到缓存
function saveCodeAgentMessages(projectId) {
    if (!projectId) return;
    
    const container = document.getElementById('codeAgentMessages');
    if (!container) return;
    
    const messages = [];
    container.querySelectorAll('.user-message, .bot-message').forEach(msg => {
        messages.push({
            type: msg.classList.contains('user-message') ? 'user' : 'bot',
            content: msg.innerHTML,
            timestamp: new Date().toISOString()
        });
    });
    
    codeAgentMessagesCache[projectId] = messages;
}

// 从缓存恢复消息
function restoreCodeAgentMessages(projectId) {
    if (!projectId || !codeAgentMessagesCache[projectId]) {
        // 没有缓存，显示默认消息
        const container = document.getElementById('codeAgentMessages');
        if (container) {
            container.innerHTML = '<div class="bot-message">你好！我是量化代码 Agent，可以帮你生成 Python 量化程序。请描述你想要实现的功能。</div>';
        }
        return;
    }
    
    const container = document.getElementById('codeAgentMessages');
    if (!container) return;
    
    container.innerHTML = '';
    codeAgentMessagesCache[projectId].forEach(msg => {
        const div = document.createElement('div');
        div.className = msg.type === 'user' ? 'user-message' : 'bot-message';
        div.innerHTML = msg.content;
        container.appendChild(div);
    });
    
    // 滚动到底部
    scrollToBottom(container);
}
```

### Step 2: 修改项目切换函数

```javascript
async function selectCodeAgentProject(projectId) {
    if (!projectId) {
        // 保存当前项目消息
        if (codeAgentCurrentProject) {
            saveCodeAgentMessages(codeAgentCurrentProject);
        }
        
        codeAgentCurrentProject = null;
        codeAgentFiles = [];
        renderCodeAgentFileTree([]);
        clearCodeAgentEditor();
        return;
    }

    // 保存当前项目消息（如果有）
    if (codeAgentCurrentProject) {
        saveCodeAgentMessages(codeAgentCurrentProject);
    }

    // 切换到新项目
    codeAgentCurrentProject = projectId;
    await loadCodeAgentFiles();
    
    // 恢复新项目的消息（不再清空）
    restoreCodeAgentMessages(projectId);
}
```

### Step 3: 修改消息追加函数

```javascript
function appendCodeAgentMessage(type, message) {
    const container = document.getElementById('codeAgentMessages');
    const div = document.createElement('div');
    div.className = type === 'user' ? 'user-message' : 'bot-message';
    div.innerHTML = formatCodeAgentMessage(message);
    container.appendChild(div);
    scrollToBottom(container);
    
    // 保存到缓存
    if (codeAgentCurrentProject) {
        if (!codeAgentMessagesCache[codeAgentCurrentProject]) {
            codeAgentMessagesCache[codeAgentCurrentProject] = [];
        }
        codeAgentMessagesCache[codeAgentCurrentProject].push({
            type: type,
            content: div.innerHTML,
            timestamp: new Date().toISOString()
        });
    }
    
    return div;
}
```

### Step 4: 页面加载时恢复消息

```javascript
// 在 DOMContentLoaded 或项目选择后
if (codeAgentCurrentProject) {
    restoreCodeAgentMessages(codeAgentCurrentProject);
}
```

## 优化点

### 1. 使用 LocalStorage 持久化（可选）
如果希望刷新页面后也能恢复，可以使用 LocalStorage：

```javascript
// 保存到 LocalStorage
function saveCodeAgentMessagesToStorage(projectId) {
    if (!projectId) return;
    const key = `code_agent_messages_${projectId}`;
    localStorage.setItem(key, JSON.stringify(codeAgentMessagesCache[projectId] || []));
}

// 从 LocalStorage 恢复
function loadCodeAgentMessagesFromStorage(projectId) {
    if (!projectId) return;
    const key = `code_agent_messages_${projectId}`;
    const stored = localStorage.getItem(key);
    if (stored) {
        codeAgentMessagesCache[projectId] = JSON.parse(stored);
    }
}
```

### 2. 消息数量限制
避免缓存过多消息：

```javascript
const MAX_MESSAGES_PER_PROJECT = 100;

function saveCodeAgentMessages(projectId) {
    // ... 保存逻辑 ...
    
    // 限制消息数量
    if (codeAgentMessagesCache[projectId].length > MAX_MESSAGES_PER_PROJECT) {
        codeAgentMessagesCache[projectId] = codeAgentMessagesCache[projectId].slice(-MAX_MESSAGES_PER_PROJECT);
    }
}
```

## 实施清单

- [ ] 添加 `codeAgentMessagesCache` 全局变量
- [ ] 实现 `saveCodeAgentMessages()` 函数
- [ ] 实现 `restoreCodeAgentMessages()` 函数
- [ ] 修改 `selectCodeAgentProject()` 函数（保存 + 恢复，不再清空）
- [ ] 修改 `appendCodeAgentMessage()` 函数（保存到缓存）
- [ ] 页面加载时恢复消息（可选）
- [ ] 测试：切换项目后消息是否保持

## 预期效果

1. ✅ 切换项目时，当前项目消息保存到缓存
2. ✅ 切换到新项目时，恢复新项目的消息
3. ✅ 切换回原项目时，消息完整恢复
4. ✅ 在同一浏览器会话中，消息不会丢失

## 注意事项

1. **消息格式**：确保 HTML 内容正确保存和恢复
2. **内存管理**：限制每个项目的消息数量，避免内存溢出
3. **时间戳**：可选，用于排序或显示时间
4. **向后兼容**：如果缓存中没有消息，显示默认欢迎消息

## 总结

这是一个**简单的前端优化**，只需要：
- 添加消息缓存机制
- 修改项目切换逻辑（保存 + 恢复）
- 修改消息追加逻辑（同步到缓存）

**工作量**：1-2 小时
**风险**：低
**效果**：完美解决切换项目消息丢失问题
