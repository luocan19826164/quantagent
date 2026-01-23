// 全局变量
let sessionId = null;
let finalRulesData = null;
let currentModel = "deepseek:deepseek-chat";  // 默认使用 DeepSeek Chat
let currentChatMode = 'collector'; // 'collector' or 'executor' or 'code_agent'

// ==========================================
// 代码 Agent 全局变量
// ==========================================
let codeAgentCurrentProject = null;
let codeAgentCurrentFile = null;
let codeAgentFiles = [];
let codeAgentIsEditing = false;
let codeAgentExecutingTaskId = null;
let codeAgentExecutionStartTime = null;
let codeAgentTimer = null;
// 消息缓存：按项目存储对话历史
let codeAgentMessagesCache = {}; // { projectId: [messages...] }
const MAX_MESSAGES_PER_PROJECT = 200; // 每个项目最多缓存的消息数
// 正在进行的 SSE 流引用（用于切换项目时保持连接）
let codeAgentActiveStream = null; // { botDiv: Element, projectId: string, fullResponse: string }

// 页面加载完成后初始化
// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', () => {
    // 初始化模型选择器为默认值
    const modelSelector = document.getElementById('modelSelector');
    if (modelSelector) {
        modelSelector.value = currentModel;
    }

    initSession();
    // loadModels(); // Assuming this function is defined elsewhere or will be added

    // 定期刷新执行状态 (如果处于执行视图)
    setInterval(() => {
        if (currentChatMode === 'executor') {
            loadExecutionRules();
        }
    }, 5000);
    setupEventListeners();
    checkLoginStatus(); // 检查登录状态
});

// 设置事件监听器
function setupEventListeners() {
    // 发送按钮
    const sendBtn = document.getElementById('sendBtn');
    if (sendBtn) sendBtn.addEventListener('click', sendMessage);

    // 回车发送
    const userInput = document.getElementById('userInput');
    if (userInput) {
        userInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }

    // 生成最终规则按钮
    const finalizeBtn = document.getElementById('finalizeBtn');
    if (finalizeBtn) finalizeBtn.addEventListener('click', finalizeRules);

    // 模型切换
    const modelSelector = document.getElementById('modelSelector');
    if (modelSelector) modelSelector.addEventListener('change', switchModel);
}

// 初始化会话
async function initSession() {
    try {
        const response = await fetch('/api/init', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (data.success) {
            sessionId = data.session_id;
            displayBotMessage(data.greeting);

            // 初始化后立即切换到前端选择的模型
            await switchToModel(currentModel);
        } else {
            displayBotMessage('初始化失败: ' + data.error);
        }
    } catch (error) {
        displayBotMessage('初始化失败: ' + error.message);
    }
}

// 切换到指定模型（内部方法，不触发UI事件）
async function switchToModel(modelValue) {
    if (!sessionId) return;

    const [provider, model] = modelValue.split(':');

    try {
        const response = await fetch(`/api/switch-model/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                provider: provider,
                model: model
            })
        });

        const data = await response.json();

        if (data.success) {
            currentModel = modelValue;
        }
    } catch (error) {
        console.error('模型切换失败:', error);
    }
}

// 发送消息
async function sendMessage() {
    const input = document.getElementById('userInput');
    const message = input.value.trim();

    if (!message) return;

    if (!sessionId) {
        alert('会话未初始化，请刷新页面');
        return;
    }

    // 显示用户消息
    displayUserMessage(message);
    input.value = '';

    // 显示加载状态
    const loadingDiv = displayBotMessage('');
    loadingDiv.innerHTML = '<div class="loading">思考中</div>';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                session_id: sessionId,
                message: message
            })
        });

        const data = await response.json();

        // 移除加载消息
        loadingDiv.remove();

        if (data.success) {
            displayBotMessage(data.response);

            // 更新状态面板
            if (data.state) {
                updateStatePanel(data.state, data.is_complete, data.missing_fields);
            }
        } else {
            displayBotMessage('错误: ' + (data.error || '未知错误'));
        }

    } catch (error) {
        loadingDiv.remove();
        displayBotMessage('发送失败: ' + error.message);
    }
}

// 显示用户消息
function displayUserMessage(message) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message user-message';
    messageDiv.innerHTML = `<div class="message-content">${escapeHtml(message)}</div>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// 显示机器人消息
function displayBotMessage(message) {
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message bot-message';
    messageDiv.innerHTML = `<div class="message-content">${formatMessage(message)}</div>`;
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return messageDiv;
}

// 格式化消息（保留换行）
function formatMessage(message) {
    return escapeHtml(message).replace(/\n/g, '<br>');
}

// HTML转义
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 更新状态面板
function updateStatePanel(state, isComplete, missingFields) {
    const stateContent = document.getElementById('stateContent');
    const indicator = document.getElementById('completenessIndicator');
    // 更新完整性指示器
    if (isComplete) {
        indicator.className = 'completeness-indicator complete';
        indicator.textContent = '✅ 已完成';
        document.getElementById('saveRuleBtn').disabled = false; // 启用保存按钮
    } else {
        indicator.className = 'completeness-indicator incomplete';
        indicator.textContent = '⚠️ 未完成';
        document.getElementById('saveRuleBtn').disabled = true;
    }

    // 构建状态显示
    let html = '';

    const requirements = state.user_requirements;

    // 交易所
    if (requirements.exchange) {
        html += createStateItem('交易所', requirements.exchange);
    }

    // 产品类型（需要英文转中文显示）
    if (requirements.product) {
        const productMap = {
            "spot": "现货",
            "contract": "合约",
            "futures": "期货",
            "options": "期权"
        };
        const productDisplay = productMap[requirements.product] || requirements.product;
        html += createStateItem('产品类型', productDisplay);
    }

    // 交易对
    if (requirements.symbols && requirements.symbols.length > 0) {
        html += createStateItem('交易对', requirements.symbols.join(', '));
    }

    // 时间周期
    if (requirements.timeframe) {
        html += createStateItem('K线周期', requirements.timeframe);
    }

    // 建仓规则
    if (requirements.entry_rules) {
        html += createStateItem('建仓规则', requirements.entry_rules);
    }

    // 止盈
    if (requirements.take_profit) {
        html += createStateItem('止盈', requirements.take_profit);
    }

    // 止损
    if (requirements.stop_loss) {
        html += createStateItem('止损', requirements.stop_loss);
    }

    // 仓位比例
    if (requirements.max_position_ratio) {
        html += createStateItem('最大仓位', (requirements.max_position_ratio * 100) + '%');
    }

    // 总本金
    if (requirements.total_capital) {
        html += createStateItem('总本金', '$' + requirements.total_capital);
    }


    // 完成状态
    if (requirements.finish !== undefined) {
        const finishStatus = requirements.finish ?
            '<span style="color: #48bb78; font-weight: bold;">✓ 已完成且可执行</span>' :
            '<span style="color: #ed8936; font-weight: bold;">⚠ 进行中或工具不足</span>';
        html += `<div class="state-item" style="border-left-color: ${requirements.finish ? '#48bb78' : '#ed8936'};">
            <div class="state-item-label">🎯 完成状态</div>
            <div class="state-item-value">${finishStatus}</div>
        </div>`;
    }

    // 执行计划（如果有）
    if (requirements.execute_plan) {
        html += `<div class="state-item" style="border-left-color: #667eea;">
            <div class="state-item-label">📋 执行计划</div>
            <div class="state-item-value">${formatExecutePlan(requirements.execute_plan)}</div>
        </div>`;
    }

    // 缺失字段
    if (missingFields && missingFields.length > 0) {
        html += `<div class="state-item" style="border-left-color: #ffc107;">
            <div class="state-item-label">⚠️ 还需补充</div>
            <div class="state-item-value">${missingFields.join(', ')}</div>
        </div>`;
    }

    if (html) {
        stateContent.innerHTML = html;
    } else {
        stateContent.innerHTML = '<div class="state-loading">等待收集信息...</div>';
    }
}

// 格式化执行计划（将Markdown转换为HTML）
function formatExecutePlan(plan) {
    if (!plan) return '';

    // 简单的Markdown转换
    let html = plan
        .replace(/\n/g, '<br>')
        .replace(/## (\d+\. .+?)(<br>|$)/g, '<strong style="color: #667eea;">$1</strong>$2')
        .replace(/- 调用 Agent工具:/g, '<span style="color: #48bb78;">• Agent工具:</span>')
        .replace(/- 调用 LLM内置能力:/g, '<span style="color: #ed8936;">• LLM内置:</span>')
        .replace(/- IF /g, '<span style="color: #4299e1;">• IF </span>')
        .replace(/- ELSE:/g, '<span style="color: #9f7aea;">• ELSE:</span>')
        .replace(/- (.+?)(<br>|$)/g, '<span style="margin-left: 1em;">• $1</span>$2');

    return '<div style="font-family: monospace; font-size: 12px; line-height: 1.6; padding: 8px; background: #f7fafc; border-radius: 4px; white-space: pre-wrap;">' + html + '</div>';
}

// 创建状态项
function createStateItem(label, value) {
    return `<div class="state-item">
        <div class="state-item-label">${label}</div>
        <div class="state-item-value">${escapeHtml(String(value))}</div>
    </div>`;
}


// 切换模型
async function switchModel(event) {
    if (!sessionId) {
        alert('会话未初始化');
        event.target.value = currentModel;
        return;
    }

    const modelValue = event.target.value;
    const [provider, model] = modelValue.split(':');

    if (currentModel === modelValue) {
        return; // 没有切换
    }

    try {
        const response = await fetch(`/api/switch-model/${sessionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                provider: provider,
                model: model
            })
        });

        const data = await response.json();

        if (data.success) {
            currentModel = modelValue;
            // 静默切换，不显示弹窗
        } else {
            event.target.value = currentModel;
            alert('切换失败: ' + (data.error || '未知错误'));
        }
    } catch (error) {
        event.target.value = currentModel;
        alert('切换失败: ' + error.message);
    }
}

// 生成最终规则
async function finalizeRules() {
    if (!sessionId) {
        alert('会话未初始化');
        return;
    }

    try {
        const response = await fetch(`/api/finalize/${sessionId}`, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            finalRulesData = data.rules;
            showFinalRulesModal(data.rules);
        } else {
            alert('生成失败: ' + (data.error || '规则信息不完整'));
        }

    } catch (error) {
        alert('生成失败: ' + error.message);
    }
}

// 显示最终规则弹窗
function showFinalRulesModal(rules) {
    const modal = document.getElementById('finalRulesModal');
    const jsonDisplay = document.getElementById('finalRulesJson');

    jsonDisplay.textContent = JSON.stringify(rules, null, 2);
    modal.style.display = 'block';
}

// 关闭最终规则弹窗
function closeFinalRulesModal() {
    document.getElementById('finalRulesModal').style.display = 'none';
}

// 下载规则
function downloadRules() {
    if (!finalRulesData) return;

    const dataStr = JSON.stringify(finalRulesData, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });

    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `quant_rules_${Date.now()}.json`;
    link.click();

    URL.revokeObjectURL(url);
}

// 复制规则
function copyRules() {
    if (!finalRulesData) return;

    const dataStr = JSON.stringify(finalRulesData, null, 2);

    navigator.clipboard.writeText(dataStr).then(() => {
        alert('已复制到剪贴板！');
    }).catch(err => {
        console.error('复制失败:', err);
        alert('复制失败');
    });
}

// 点击弹窗外部关闭
window.onclick = function (event) {
    const modal = document.getElementById('finalRulesModal');
    const authModal = document.getElementById('authModal');
    const myRulesModal = document.getElementById('myRulesModal');

    if (event.target === modal) {
        closeFinalRulesModal();
    }
    if (event.target === authModal) {
        closeAuthModal();
    }
    if (event.target === myRulesModal) {
        closeMyRulesModal();
    }
}


// ==========================================
// Agent 切换逻辑
// ==========================================

// 退出全屏模式，返回规则收集页面
function exitFullscreenMode() {
    const appWrapper = document.querySelector('.app-wrapper');
    if (appWrapper) {
        appWrapper.classList.remove('fullscreen-mode');
    }
    switchAgent('collector');
}

function switchAgent(mode) {
    if (mode === currentChatMode) return;

    currentChatMode = mode;

    // 更新导航样式
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));

    const collectorView = document.getElementById('collectorView');
    const executorView = document.getElementById('executorView');
    const codeAgentView = document.getElementById('codeAgentView');
    const ruleDetailView = document.getElementById('ruleDetailView');
    const headerTitle = document.querySelector('.header h1');
    const appWrapper = document.querySelector('.app-wrapper');
    const header = document.querySelector('.header');

    // 切换时先隐藏所有视图
    if (ruleDetailView) ruleDetailView.style.display = 'none';
    currentRuleId = null;  // 重置当前规则ID

    // 隐藏所有主视图
    if (collectorView) collectorView.style.display = 'none';
    if (executorView) executorView.style.display = 'none';
    if (codeAgentView) codeAgentView.style.display = 'none';

    if (mode === 'collector') {
        document.getElementById('navRuleCollector').classList.add('active');
        if (collectorView) collectorView.style.display = 'grid';
        if (headerTitle) headerTitle.innerText = '🤖 量化规则收集 Agent';
        // 显示侧边栏
        if (appWrapper) appWrapper.classList.remove('fullscreen-mode');
    } else if (mode === 'executor') {
        document.getElementById('navRuleExecutor').classList.add('active');
        if (executorView) executorView.style.display = 'grid';
        if (headerTitle) headerTitle.innerText = '⚡ 量化规则执行 Agent';
        loadExecutionRules();
        // 显示侧边栏
        if (appWrapper) appWrapper.classList.remove('fullscreen-mode');
    } else if (mode === 'code_agent') {
        document.getElementById('navCodeAgent').classList.add('active');
        if (codeAgentView) codeAgentView.style.display = 'grid';
        if (headerTitle) headerTitle.innerText = '💻 量化代码 Agent';
        // 隐藏侧边栏，进入全屏模式
        if (appWrapper) appWrapper.classList.add('fullscreen-mode');
        loadCodeAgentProjects();
        // 如果有当前项目，恢复消息
        if (codeAgentCurrentProject) {
            restoreCodeAgentMessages(codeAgentCurrentProject);
        }
    }
}

// ==========================================
// 执行 Agent 逻辑
// ==========================================

async function loadExecutionRules() {
    try {
        const response = await fetch('/api/my_rules');
        const data = await response.json();

        if (data.success) {
            renderExecutionRules(data.rules);
        } else if (data.error === "请先登录") {
            // 如果后端返回未登录，前端需要同步状态
            currentUser = null;
            updateUserInfo();
            renderExecutionRules([]); // 清空列表
        }
    } catch (error) {
        console.error('Failed to load execution rules:', error);
    }
}

function renderExecutionRules(rules) {
    const listElement = document.getElementById('executionRulesList');
    if (rules.length === 0) {
        listElement.innerHTML = '<div class="no-data">暂无已保存策略，请先在收集模型中保存。</div>';
        return;
    }

    listElement.innerHTML = rules.map(rule => {
        const req = rule.content.user_requirements;
        const isRunning = rule.status === 'running';

        return `
            <div class="exec-rule-card">
                <div class="exec-rule-header">
                    <div class="exec-rule-name">${rule.name || (req.symbols.join(', ') + ' (' + req.timeframe + ')')}</div>
                    <span class="exec-status-badge ${isRunning ? 'exec-status-running' : 'exec-status-stopped'}">
                        ${isRunning ? '运行中' : '已停止'}
                    </span>
                </div>
                <div class="exec-details">
                    <p>交易所: ${req.exchange} | 周期: ${req.timeframe}</p>
                    <p>交易标的: ${req.symbols.join(', ')}</p>
                    <p>总本金: $${rule.total_capital || '未设置'}</p>
                    <p>建仓规则: ${req.entry_rules?.substring(0, 50)}...</p>
                </div>
                <div class="exec-actions">
                    <a href="javascript:void(0)" class="detail-link" onclick="showRuleDetail(${rule.id})">查看详情</a>
                    <span style="font-size: 13px; color: #666; margin-left: 15px;">自动执行</span>
                    <label class="switch">
                        <input type="checkbox" ${isRunning ? 'checked' : ''} onchange="toggleRuleExecution(${rule.id}, this.checked)">
                        <span class="slider round"></span>
                    </label>
                </div>
            </div>
        `;
    }).join('');
}

async function toggleRuleExecution(ruleId, shouldStart) {
    try {
        const response = await fetch(`/api/rules/${ruleId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active: shouldStart })
        });
        const data = await response.json();

        if (!data.success) {
            alert('操作失败: ' + data.error);
            loadExecutionRules(); // 恢复状态
        } else {
            loadExecutionRules();
        }
    } catch (error) {
        console.error('Toggle execution error:', error);
    }
}

async function loadOrders() {
    try {
        const response = await fetch('/api/orders');
        const data = await response.json();

        if (data.success) {
            const tableBody = document.getElementById('ordersTableBody');
            if (data.orders.length === 0) {
                tableBody.innerHTML = '<tr><td colspan="6" class="no-data">暂无订单数据</td></tr>';
                return;
            }

            tableBody.innerHTML = data.orders.map(order => `
                <tr>
                    <td>${new Date(order.created_at).toLocaleString()}</td>
                    <td>${order.symbol}</td>
                    <td class="side-${order.side.toLowerCase()}">${order.side === 'buy' ? '做多' : '做空'}</td>
                    <td>$${order.price.toFixed(2)}</td>
                    <td>${order.amount.toFixed(4)}</td>
                    <td class="${order.pnl >= 0 ? 'pnl-plus' : 'pnl-minus'}">${order.pnl >= 0 ? '+' : ''}${order.pnl.toFixed(2)}</td>
                </tr>
            `).join('');
        } else if (data.error === "请先登录") {
            document.getElementById('ordersTableBody').innerHTML = '<tr><td colspan="6" class="no-data">请先登录以查看订单</td></tr>';
        }
    } catch (error) {
        console.error('Failed to load orders:', error);
    }
}

// ==========================================
// 用户认证与保存逻辑
// ==========================================

let currentUser = null;
let pendingSave = false; // 登录后是否自动保存

// 检查登录状态
async function checkLoginStatus() {
    try {
        const response = await fetch('/api/check_status', {
            credentials: 'same-origin'
        });
        const data = await response.json();

        if (data.is_logged_in) {
            currentUser = data.user;
            updateUserInfo();
        } else {
            currentUser = null;
            updateUserInfo();
        }
    } catch (error) {
        console.error('Check status error:', error);
    }
}

// 更新用户信息UI
function updateUserInfo() {
    const userInfo = document.getElementById('userInfo');
    const authBtn = document.getElementById('authBtn');
    const logoutBtn = document.getElementById('logoutBtn');
    const saveRuleBtn = document.getElementById('saveRuleBtn');

    if (currentUser) {
        userInfo.style.display = 'inline-block';
        userInfo.textContent = `👤 ${currentUser.username}`;
        authBtn.style.display = 'none';
        logoutBtn.style.display = 'inline-block';
        // Ensure parent is visible
        userInfo.parentElement.style.display = 'flex';
    } else {
        userInfo.style.display = 'none';
        authBtn.style.display = 'inline-block';
        logoutBtn.style.display = 'none';
    }
}

// 显示认证弹窗
function showAuthModal() {
    document.getElementById('authModal').style.display = 'block';
    // 默认显示登录
    switchAuthMode('login');
}

// 关闭认证弹窗
function closeAuthModal() {
    document.getElementById('authModal').style.display = 'none';
    pendingSave = false;
}

// 切换认证模式
function switchAuthMode(mode) {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const tabs = document.querySelectorAll('.auth-tab');

    if (mode === 'login') {
        loginForm.style.display = 'block';
        registerForm.style.display = 'none';
        tabs[0].classList.add('active');
        tabs[1].classList.remove('active');
    } else {
        loginForm.style.display = 'none';
        registerForm.style.display = 'block';
        tabs[0].classList.remove('active');
        tabs[1].classList.add('active');
    }
}

// 执行登录
async function performLogin() {
    const usernameInput = document.getElementById('loginUsername');
    const passwordInput = document.getElementById('loginPassword');

    if (!usernameInput.value || !passwordInput.value) {
        alert('请输入用户名和密码');
        return;
    }

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: usernameInput.value,
                password: passwordInput.value
            })
        });

        const data = await response.json();
        if (data.success) {
            currentUser = data.user;
            updateUserInfo();
            closeAuthModal();

            // 如果有待处理的保存操作，立即执行
            if (pendingSave) {
                saveRule();
            }
        } else {
            alert('登录失败: ' + data.error);
        }
    } catch (error) {
        alert('登录错误: ' + error.message);
    }
}

// 执行注册
async function performRegister() {
    const usernameInput = document.getElementById('regUsername');
    const passwordInput = document.getElementById('regPassword');

    if (!usernameInput.value || !passwordInput.value) {
        alert('请设置用户名和密码');
        return;
    }

    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: usernameInput.value,
                password: passwordInput.value
            })
        });

        const data = await response.json();
        if (data.success) {
            currentUser = data.user;
            updateUserInfo();
            closeAuthModal();
            alert('注册成功！');

            // 如果有待处理的保存操作，立即执行
            if (pendingSave) {
                saveRule();
            }
        } else {
            alert('注册失败: ' + data.error);
        }
    } catch (error) {
        alert('注册错误: ' + error.message);
    }
}

// 退出登录
async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        currentUser = null;
        updateUserInfo();
    } catch (error) {
        console.error('Logout error:', error);
    }
}

// 保存规则
async function saveRule() {
    // 检查是否登录
    if (!currentUser) {
        pendingSave = true;
        showAuthModal();
        return;
    }

    if (!sessionId) {
        alert('会话未初始化');
        return;
    }

    const strategyName = prompt("请输入策略名称:", "我的策略");
    if (strategyName === null) return; // 用户取消

    try {
        // 直接根据 session_id 保存，不需要前端传 content，后端自己取
        const response = await fetch('/api/save_rule', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                session_id: sessionId,
                name: strategyName
            })
        });

        const data = await response.json();
        if (data.success) {
            alert('✅ 策略已保存到云端');
            pendingSave = false;
        } else {
            alert('保存失败: ' + data.error);
        }
    } catch (error) {
        alert('保存错误: ' + error.message);
    }
}

// ==========================================
// 规则详情页面逻辑
// ==========================================

let currentRuleId = null;

// 显示规则详情
async function showRuleDetail(ruleId) {
    currentRuleId = ruleId;

    // 切换视图
    document.getElementById('executorView').style.display = 'none';
    document.getElementById('collectorView').style.display = 'none';
    document.getElementById('ruleDetailView').style.display = 'block';

    // 更新标题
    document.querySelector('.header h1').innerText = '📋 规则详情';

    // 加载规则详情
    await loadRuleDetail(ruleId);
}

// 返回执行列表
function backToExecutor() {
    currentRuleId = null;
    document.getElementById('ruleDetailView').style.display = 'none';
    document.getElementById('executorView').style.display = 'grid';
    document.querySelector('.header h1').innerText = '⚡ 量化规则执行 Agent';

    // 刷新规则列表
    loadExecutionRules();
}

// 加载规则详情
async function loadRuleDetail(ruleId) {
    const infoContent = document.getElementById('ruleInfoContent');
    const ordersBody = document.getElementById('ruleOrdersTableBody');

    infoContent.innerHTML = '<div class="loading">加载中...</div>';
    ordersBody.innerHTML = '<tr><td colspan="8" class="loading">加载中...</td></tr>';

    try {
        const response = await fetch(`/api/rules/${ruleId}/detail`);
        const data = await response.json();

        if (data.success) {
            renderRuleInfo(data.rule);
            renderRuleOrders(data.orders);
        } else {
            infoContent.innerHTML = '<div class="error">加载失败: ' + data.error + '</div>';
            ordersBody.innerHTML = '<tr><td colspan="8" class="no-data">加载失败</td></tr>';
        }
    } catch (error) {
        infoContent.innerHTML = '<div class="error">加载错误: ' + error.message + '</div>';
        ordersBody.innerHTML = '<tr><td colspan="8" class="no-data">加载错误</td></tr>';
    }
}

// 渲染规则信息
function renderRuleInfo(rule) {
    const infoContent = document.getElementById('ruleInfoContent');
    const statusBadge = document.getElementById('ruleStatusBadge');
    const titleElement = document.getElementById('ruleDetailTitle');

    const req = rule.content.user_requirements || {};
    const runtimeStatus = rule.content.runtime_status || {};
    const isRunning = rule.status === 'running';

    // 更新标题和状态
    titleElement.textContent = `📋 ${rule.name || '规则 #' + rule.id}`;
    statusBadge.className = `exec-status-badge ${isRunning ? 'exec-status-running' : 'exec-status-stopped'}`;
    statusBadge.textContent = isRunning ? '运行中' : '已停止';

    // 产品类型映射
    const productMap = { "spot": "现货", "contract": "合约", "futures": "期货", "options": "期权" };

    // 构建紧凑型信息网格
    let html = `
        <!-- 第一行：5个字段 -->
        <div class="info-row row-5">
            <div class="info-item">
                <span class="info-label">规则ID</span>
                <span class="info-value">#${rule.id}</span>
            </div>
            <div class="info-item">
                <span class="info-label">交易所</span>
                <span class="info-value">${req.exchange || '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">产品类型</span>
                <span class="info-value">${productMap[req.product] || req.product || '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">交易对</span>
                <span class="info-value">${req.symbols ? req.symbols.join(', ') : '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">K线周期</span>
                <span class="info-value">${req.timeframe || '-'}</span>
            </div>
        </div>
        <!-- 第二行：5个字段 -->
        <div class="info-row row-5">
            <div class="info-item">
                <span class="info-label">总本金</span>
                <span class="info-value">$${rule.total_capital || '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">最大仓位</span>
                <span class="info-value">${req.max_position_ratio ? (req.max_position_ratio * 100) + '%' : '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">止盈规则</span>
                <span class="info-value">${req.take_profit || '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">止损规则</span>
                <span class="info-value">${req.stop_loss || '-'}</span>
            </div>
            <div class="info-item">
                <span class="info-label">创建时间</span>
                <span class="info-value">${rule.created_at ? new Date(rule.created_at).toLocaleString() : '-'}</span>
            </div>
        </div>
        <!-- 第三行：建仓规则 -->
        <div class="info-row row-full">
            <div class="info-item">
                <span class="info-label">建仓规则</span>
                <span class="info-value">${req.entry_rules || '-'}</span>
            </div>
        </div>
    `;

    // 执行计划（如果有）
    if (req.execute_plan) {
        html += `
        <div class="info-row row-full">
            <div class="info-item">
                <span class="info-label">执行计划</span>
                <span class="info-value execute-plan">${formatExecutePlan(req.execute_plan)}</span>
            </div>
        </div>
        `;
    }

    // 运行时状态（如果有）
    if (Object.keys(runtimeStatus).length > 0) {
        html += `
        <div class="info-row row-full">
            <div class="info-item">
                <span class="info-label">运行时状态</span>
                <span class="info-value"><pre>${JSON.stringify(runtimeStatus, null, 2)}</pre></span>
            </div>
        </div>
        `;
    }

    infoContent.innerHTML = html;
}

// 渲染规则相关订单
function renderRuleOrders(orders) {
    const tableBody = document.getElementById('ruleOrdersTableBody');

    if (!orders || orders.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="8" class="no-data">暂无订单数据</td></tr>';
        return;
    }

    tableBody.innerHTML = orders.map(order => `
        <tr>
            <td>${order.order_id || order.id}</td>
            <td>${order.created_at ? new Date(order.created_at).toLocaleString() : '-'}</td>
            <td>${order.symbol}</td>
            <td class="side-${order.side.toLowerCase()}">${order.side === 'buy' ? '买入' : '卖出'}</td>
            <td>$${order.price ? order.price.toFixed(2) : '-'}</td>
            <td>${order.amount ? order.amount.toFixed(6) : '-'}</td>
            <td><span class="order-status-${order.status}">${order.status === 'open' ? '持仓中' : '已平仓'}</span></td>
            <td class="${order.pnl >= 0 ? 'pnl-plus' : 'pnl-minus'}">${order.pnl != null ? (order.pnl >= 0 ? '+' : '') + order.pnl.toFixed(2) + '%' : '-'}</td>
        </tr>
    `).join('');
}

// ==========================================
// 代码 Agent 逻辑
// ==========================================

// 加载项目列表
async function loadCodeAgentProjects() {
    try {
        const response = await fetch('/api/code-agent/projects');
        const data = await response.json();

        if (data.success) {
            renderCodeAgentProjects(data.projects);
        } else {
            console.error('加载项目失败:', data.error);
        }
    } catch (error) {
        console.error('加载项目错误:', error);
    }
}

// 渲染项目选择器
function renderCodeAgentProjects(projects) {
    const selector = document.getElementById('projectSelector');
    if (!selector) return;

    let options = '<option value="">选择项目...</option>';
    projects.forEach(project => {
        options += `<option value="${project.id}">${project.name}</option>`;
    });
    selector.innerHTML = options;

    // 如果当前有选中的项目，保持选中
    if (codeAgentCurrentProject) {
        selector.value = codeAgentCurrentProject;
    }
}

// 创建新项目
async function createCodeAgentProject() {
    const name = prompt('请输入项目名称:', '新量化项目');
    if (!name) return;

    try {
        const response = await fetch('/api/code-agent/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name })
        });

        const data = await response.json();
        if (data.success) {
            codeAgentCurrentProject = data.project.id;
            await loadCodeAgentProjects();
            document.getElementById('projectSelector').value = codeAgentCurrentProject;
            await loadCodeAgentFiles();
            // 新项目没有历史消息，显示默认消息
            restoreCodeAgentMessages(codeAgentCurrentProject);
        } else {
            alert('创建失败: ' + data.error);
        }
    } catch (error) {
        alert('创建错误: ' + error.message);
    }
}

// 选择项目
async function selectCodeAgentProject(projectId) {
    console.log('selectCodeAgentProject:', projectId, 'current:', codeAgentCurrentProject);
    
    if (!projectId) {
        // 保存当前项目消息（如果有）
        if (codeAgentCurrentProject) {
            saveCodeAgentMessages(codeAgentCurrentProject);
        }
        
        codeAgentCurrentProject = null;
        codeAgentFiles = [];
        renderCodeAgentFileTree([]);
        clearCodeAgentEditor();
        // 清除流引用（如果切换到了空项目）
        codeAgentActiveStream = null;
        return;
    }

    // 保存当前项目消息（如果有，且切换到不同项目）
    if (codeAgentCurrentProject && codeAgentCurrentProject !== projectId) {
        console.log('Switching from project', codeAgentCurrentProject, 'to', projectId);
        // 先保存当前项目的消息（从DOM读取，但只保存当前项目的）
        saveCodeAgentMessages(codeAgentCurrentProject);
        
        // 注意：不清除流引用，即使切换到不同项目
        // 因为后端流还在继续，用户可能想看到结果
        // 流会在完成后自动清除，或者在恢复消息时重新关联
        if (codeAgentActiveStream && codeAgentActiveStream.projectId !== projectId) {
            console.log('Stream is for old project, but keeping reference for now');
        }
    }

    // 切换到新项目
    codeAgentCurrentProject = projectId;
    await loadCodeAgentFiles();
    
    // 恢复新项目的消息
    // restoreCodeAgentMessages 会检查流是否是当前项目的
    // 如果是，不清空DOM；如果不是，清空DOM后恢复
    console.log('Restoring messages for project', projectId, 'cache:', codeAgentMessagesCache[projectId]?.length || 0);
    restoreCodeAgentMessages(projectId);
}

// 删除项目
async function deleteCodeAgentProject() {
    if (!codeAgentCurrentProject) {
        alert('请先选择一个项目');
        return;
    }

    if (!confirm('确定要删除这个项目吗？所有文件将被删除。')) {
        return;
    }

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}`, {
            method: 'DELETE'
        });

        const data = await response.json();
        if (data.success) {
            codeAgentCurrentProject = null;
            codeAgentFiles = [];
            await loadCodeAgentProjects();
            renderCodeAgentFileTree([]);
            clearCodeAgentEditor();
        } else {
            alert('删除失败: ' + data.error);
        }
    } catch (error) {
        alert('删除错误: ' + error.message);
    }
}

// 加载项目文件
async function loadCodeAgentFiles() {
    if (!codeAgentCurrentProject) return;

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/files`);
        const data = await response.json();

        if (data.success) {
            codeAgentFiles = data.files;
            renderCodeAgentFileTree(data.files);
        } else {
            console.error('加载文件失败:', data.error);
        }
    } catch (error) {
        console.error('加载文件错误:', error);
    }
}

// 渲染文件树（支持嵌套结构）
function renderCodeAgentFileTree(files) {
    const container = document.getElementById('fileTree');
    if (!container) return;

    if (files.length === 0) {
        container.innerHTML = '<div class="file-tree-placeholder">暂无文件，开始对话生成代码</div>';
        return;
    }

    // 递归渲染树节点
    function renderNode(node, level = 0) {
        // node.path 已经是完整的相对路径（如 "dir1/file1.py"）
        const filePath = node.path || node.name;
        const isDir = node.type === 'directory' || node.type === 'dir' || (node.children && node.children.length > 0);
        const icon = isDir ? '📁' : '📄';
        const selectedClass = (codeAgentCurrentFile === filePath) ? 'selected' : '';
        const typeClass = isDir ? 'dir' : '';
        const hasChildren = isDir && node.children && node.children.length > 0;
        const indent = level * 20; // 每级缩进 20px
        
        let html = `<div class="file-tree-item ${typeClass} ${selectedClass}" 
                     style="padding-left: ${indent + 16}px;"
                     data-path="${filePath}"
                     data-level="${level}">`;
        
        // 目录展开/折叠按钮
        if (isDir && hasChildren) {
            html += `<span class="tree-toggle" onclick="toggleTreeNode(event, this)" data-expanded="true">▼</span>`;
        } else if (isDir) {
            html += `<span class="tree-toggle tree-toggle-empty"></span>`;
        } else {
            html += `<span class="tree-toggle"></span>`;
        }
        
        // 文件图标和名称
        html += `<span class="file-icon">${icon}</span>`;
        html += `<span class="file-name" ${!isDir ? `onclick="selectCodeAgentFile('${filePath}')"` : ''}>${node.name}</span>`;
        html += `</div>`;
        
        // 递归渲染子节点
        if (hasChildren) {
            html += `<div class="tree-children" data-parent="${filePath}">`;
            node.children.forEach(child => {
                html += renderNode(child, level + 1);
            });
            html += `</div>`;
        }
        
        return html;
    }

    let html = '';
    files.forEach(file => {
        html += renderNode(file, 0);
    });

    container.innerHTML = html;
}

// 切换树节点展开/折叠
function toggleTreeNode(event, toggleBtn) {
    event.stopPropagation();
    const item = toggleBtn.closest('.file-tree-item');
    const children = item.nextElementSibling;
    
    if (children && children.classList.contains('tree-children')) {
        const isExpanded = toggleBtn.getAttribute('data-expanded') === 'true';
        if (isExpanded) {
            children.style.display = 'none';
            toggleBtn.textContent = '▶';
            toggleBtn.setAttribute('data-expanded', 'false');
        } else {
            children.style.display = 'block';
            toggleBtn.textContent = '▼';
            toggleBtn.setAttribute('data-expanded', 'true');
        }
    }
}

// 选择文件
async function selectCodeAgentFile(filePath) {
    if (!codeAgentCurrentProject) return;

    codeAgentCurrentFile = filePath;

    // 更新文件树选中状态
    document.querySelectorAll('.file-tree-item').forEach(item => {
        item.classList.remove('selected');
        if (item.dataset.path === filePath) {
            item.classList.add('selected');
        }
    });

    // 加载文件内容
    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/files/${encodeURIComponent(filePath)}`);
        const data = await response.json();

        if (data.success) {
            displayCodeAgentFile(filePath, data.content);
        } else {
            console.error('加载文件失败:', data.error);
        }
    } catch (error) {
        console.error('加载文件错误:', error);
    }
}

// 显示文件内容
function displayCodeAgentFile(filePath, content) {
    const fileName = document.getElementById('currentFileName');
    const codeDisplay = document.getElementById('codeDisplay');
    const codeTextarea = document.getElementById('codeTextarea');

    if (fileName) fileName.textContent = filePath;

    // 确定语言类型
    const ext = filePath.split('.').pop().toLowerCase();
    const langMap = {
        'py': 'python',
        'js': 'javascript',
        'json': 'json',
        'yaml': 'yaml',
        'yml': 'yaml',
        'md': 'markdown',
        'txt': 'plaintext'
    };
    const language = langMap[ext] || 'plaintext';

    if (codeDisplay) {
        codeDisplay.className = `code-display language-${language}`;
        codeDisplay.textContent = content;
        // 使用 Prism.js 高亮
        if (window.Prism) {
            Prism.highlightElement(codeDisplay);
        }
    }

    if (codeTextarea) {
        codeTextarea.value = content;
    }

    // 默认显示高亮视图
    exitCodeAgentEditMode();
}

// 进入编辑模式
function enterCodeAgentEditMode() {
    codeAgentIsEditing = true;

    const codeDisplay = document.getElementById('codeDisplay');
    const codeTextarea = document.getElementById('codeTextarea');
    const editBtn = document.getElementById('editFileBtn');
    const saveBtn = document.getElementById('saveFileBtn');
    const cancelBtn = document.getElementById('cancelEditBtn');

    if (codeDisplay) codeDisplay.style.display = 'none';
    if (codeTextarea) codeTextarea.style.display = 'block';
    if (editBtn) editBtn.style.display = 'none';
    if (saveBtn) saveBtn.style.display = 'inline-block';
    if (cancelBtn) cancelBtn.style.display = 'inline-block';
}

// 退出编辑模式
function exitCodeAgentEditMode() {
    codeAgentIsEditing = false;

    const codeDisplay = document.getElementById('codeDisplay');
    const codeTextarea = document.getElementById('codeTextarea');
    const editBtn = document.getElementById('editFileBtn');
    const saveBtn = document.getElementById('saveFileBtn');
    const cancelBtn = document.getElementById('cancelEditBtn');

    if (codeDisplay) codeDisplay.style.display = 'block';
    if (codeTextarea) codeTextarea.style.display = 'none';
    if (editBtn) editBtn.style.display = 'inline-block';
    if (saveBtn) saveBtn.style.display = 'none';
    if (cancelBtn) cancelBtn.style.display = 'none';
}

// 保存文件
async function saveCodeAgentFile() {
    if (!codeAgentCurrentProject || !codeAgentCurrentFile) return;

    const textarea = document.getElementById('codeTextarea');
    if (!textarea) return;

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/files/${encodeURIComponent(codeAgentCurrentFile)}`, {
            method: 'PUT',  // 使用 PUT 方法
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: textarea.value })
        });

        const data = await response.json();
        if (data.success) {
            // 更新高亮显示
            displayCodeAgentFile(codeAgentCurrentFile, textarea.value);
        } else {
            alert('保存失败: ' + data.error);
        }
    } catch (error) {
        alert('保存错误: ' + error.message);
    }
}

// 取消编辑
function cancelCodeAgentEdit() {
    // 重新加载文件内容
    if (codeAgentCurrentFile) {
        selectCodeAgentFile(codeAgentCurrentFile);
    }
}

// 清空编辑器
function clearCodeAgentEditor() {
    codeAgentCurrentFile = null;
    const fileName = document.getElementById('currentFileName');
    const codeDisplay = document.getElementById('codeDisplay');
    const codeTextarea = document.getElementById('codeTextarea');

    if (fileName) fileName.textContent = '未选择文件';
    if (codeDisplay) {
        codeDisplay.className = 'code-display';
        codeDisplay.textContent = '';
    }
    if (codeTextarea) codeTextarea.value = '';

    exitCodeAgentEditMode();
}

// 保存当前项目消息到缓存
function saveCodeAgentMessages(projectId) {
    if (!projectId) return;
    
    const container = document.getElementById('codeAgentMessages');
    if (!container) return;
    
    // 从DOM读取消息（但只保存当前项目的）
    // 如果缓存中已有该项目的消息，先合并（避免丢失）
    const existingCache = codeAgentMessagesCache[projectId] || [];
    const domMessages = [];
    
    container.querySelectorAll('.user-message, .bot-message').forEach(msg => {
        domMessages.push({
            type: msg.classList.contains('user-message') ? 'user' : 'bot',
            content: msg.innerHTML,
            timestamp: new Date().toISOString()
        });
    });
    
    // 合并缓存和DOM消息（去重，优先使用DOM中的最新消息）
    // 如果DOM中有消息，使用DOM的；否则使用缓存的
    const messages = domMessages.length > 0 ? domMessages : existingCache;
    
    // 限制消息数量
    if (messages.length > MAX_MESSAGES_PER_PROJECT) {
        messages.splice(0, messages.length - MAX_MESSAGES_PER_PROJECT);
    }
    
    codeAgentMessagesCache[projectId] = messages;
}

// 从缓存恢复消息
function restoreCodeAgentMessages(projectId) {
    const container = document.getElementById('codeAgentMessages');
    if (!container) {
        console.error('codeAgentMessages container not found in restoreCodeAgentMessages');
        return;
    }
    
    // 检查是否有正在进行的流，且流是针对当前项目的
    const hasActiveStreamForCurrentProject = codeAgentActiveStream && 
                                              codeAgentActiveStream.projectId === projectId;
    
    console.log('restoreCodeAgentMessages:', {
        projectId,
        hasStream: !!codeAgentActiveStream,
        streamProjectId: codeAgentActiveStream?.projectId,
        hasActiveStreamForCurrentProject,
        cacheLength: codeAgentMessagesCache[projectId]?.length || 0
    });
    
    // 如果没有缓存，显示默认消息
    if (!projectId || !codeAgentMessagesCache[projectId] || codeAgentMessagesCache[projectId].length === 0) {
        console.log('No cache for project', projectId, '- showing default message');
        // 如果有正在进行的流（当前项目的），不清空DOM（保留流式消息）
        if (!hasActiveStreamForCurrentProject) {
            container.innerHTML = '<div class="bot-message">你好！我是量化代码 Agent，可以帮你生成 Python 量化程序。请描述你想要实现的功能。</div>';
        }
        return;
    }
    
    // 如果有正在进行的流，且流是针对当前项目的，不清空 DOM，只追加新消息
    // 这样可以保证流式消息继续显示
    if (hasActiveStreamForCurrentProject) {
        console.log('Has active stream for current project - appending messages');
        // 检查缓存中的消息是否已经在 DOM 中
        const existingMessages = Array.from(container.querySelectorAll('.user-message, .bot-message'));
        const cachedMessages = codeAgentMessagesCache[projectId];
        
        // 只追加缓存中但不在 DOM 中的消息
        if (cachedMessages) {
            cachedMessages.forEach((msg, index) => {
                if (index >= existingMessages.length) {
                    const div = document.createElement('div');
                    div.className = msg.type === 'user' ? 'user-message' : 'bot-message';
                    div.innerHTML = msg.content;
                    container.appendChild(div);
                }
            });
        }
        
        // 检查流引用的 botDiv 是否还在 DOM 中
        if (codeAgentActiveStream && codeAgentActiveStream.botDiv) {
            if (!container.contains(codeAgentActiveStream.botDiv)) {
                console.log('botDiv not in DOM, recreating from stream');
                // botDiv 不在 DOM 中，重新创建并追加
                const newBotDiv = document.createElement('div');
                newBotDiv.className = 'bot-message';
                newBotDiv.innerHTML = formatCodeAgentMessage(codeAgentActiveStream.fullResponse || '');
                container.appendChild(newBotDiv);
                codeAgentActiveStream.botDiv = newBotDiv;
            }
        }
    } else {
        // 没有正在进行的流，或者流是其他项目的，正常恢复（清空后恢复）
        console.log('No active stream - clearing and restoring', codeAgentMessagesCache[projectId].length, 'messages');
        container.innerHTML = '';
        codeAgentMessagesCache[projectId].forEach(msg => {
            const div = document.createElement('div');
            div.className = msg.type === 'user' ? 'user-message' : 'bot-message';
            div.innerHTML = msg.content;
            container.appendChild(div);
        });
        
        // 如果流是其他项目的，但流还在进行中，尝试恢复 botDiv
        if (codeAgentActiveStream && codeAgentActiveStream.projectId !== projectId) {
            console.log('Stream is for different project, but keeping it active');
            // 在恢复的消息后追加一个空的 botDiv，用于接收流式消息
            const botDiv = document.createElement('div');
            botDiv.className = 'bot-message';
            botDiv.innerHTML = formatCodeAgentMessage(codeAgentActiveStream.fullResponse || '');
            container.appendChild(botDiv);
            codeAgentActiveStream.botDiv = botDiv;
            // 更新流引用的项目ID（因为用户切换回来了）
            codeAgentActiveStream.projectId = projectId;
        }
    }
    
    // 滚动到底部
    scrollToBottom(container);
}

// 清空聊天记录（保留，但不再在切换项目时调用）
function clearCodeAgentChat() {
    const container = document.getElementById('codeAgentMessages');
    if (container) {
        container.innerHTML = '<div class="bot-message">你好！我是量化代码 Agent，可以帮你生成 Python 量化程序。请描述你想要实现的功能。</div>';
    }
    // 同时清空缓存
    if (codeAgentCurrentProject) {
        codeAgentMessagesCache[codeAgentCurrentProject] = [];
    }
}

// 发送消息给代码 Agent（SSE 流式）
async function sendCodeAgentMessage() {
    const input = document.getElementById('codeAgentInput');
    const sendBtn = document.getElementById('codeAgentSendBtn');
    const message = input.value.trim();

    if (!message) return;

    if (!codeAgentCurrentProject) {
        alert('请先选择或创建一个项目');
        return;
    }

    console.log('sendCodeAgentMessage:', {
        project: codeAgentCurrentProject,
        message: message.substring(0, 50) + '...'
    });

    // 显示用户消息
    const userDiv = appendCodeAgentMessage('user', message);
    if (!userDiv) {
        console.error('Failed to append user message');
        return;
    }
    
    input.value = '';
    input.disabled = true;
    sendBtn.disabled = true;

    // 创建 bot 消息容器
    const botDiv = appendCodeAgentMessage('bot', '');
    if (!botDiv) {
        console.error('Failed to append bot message');
        input.disabled = false;
        sendBtn.disabled = false;
        return;
    }
    
    let fullResponse = '';
    let codeChanges = [];
    
    // 记录正在进行的流
    codeAgentActiveStream = {
        botDiv: botDiv,
        projectId: codeAgentCurrentProject,
        fullResponse: fullResponse
    };
    
    console.log('Stream started for project', codeAgentCurrentProject);

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });

        if (!response.ok) {
            const error = await response.json();
            const errorMsg = '错误: ' + (error.error || '未知错误');
            botDiv.innerHTML = formatCodeAgentMessage(errorMsg);
            // 更新缓存中的 bot 消息
            updateBotMessageInCache(botDiv, errorMsg);
            // 清除流引用
            codeAgentActiveStream = null;
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // 处理 SSE 事件
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        // 处理新的事件类型
                        if (data.type === 'status') {
                            // 状态消息
                            fullResponse += `💬 ${data.message}\n`;
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'execution_started') {
                            // 执行开始
                            fullResponse += `\n🚀 **开始执行计划**\n`;
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'plan_created') {
                            // 显示计划
                            fullResponse += `\n📋 **执行计划** (共 ${data.plan.steps.length} 步):\n`;
                            data.plan.steps.forEach((step, idx) => {
                                fullResponse += `${idx + 1}. ${step.description}\n`;
                            });
                            fullResponse += '\n';
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'step_started') {
                            // 步骤开始
                            fullResponse += `\n🔄 **Step ${data.step_id}**: ${data.description}\n`;
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'step_output') {
                            // 步骤输出内容
                            fullResponse += data.content;
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'tool_calls') {
                            // 工具调用
                            fullResponse += '\n  🔧 工具调用: ';
                            fullResponse += data.calls.map(c => c.name).join(', ') + '\n';
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'tool_result') {
                            // 工具执行结果
                            const icon = data.success ? '✅' : '❌';
                            fullResponse += `  ${icon} ${data.tool}`;
                            if (data.error) {
                                fullResponse += `: ${data.error}`;
                            }
                            fullResponse += '\n';
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';

                            // 如果是文件写入操作，实时刷新文件列表
                            if (data.success && ['write_file', 'patch_file', 'delete_file'].includes(data.tool)) {
                                loadCodeAgentFiles();
                            }
                        } else if (data.type === 'step_completed') {
                            // 步骤完成
                            const progress = data.progress;
                            fullResponse += `  ✅ 完成 (${progress.done}/${progress.total})\n`;
                            if (data.files_changed && data.files_changed.length > 0) {
                                fullResponse += `  📁 文件变更: ${data.files_changed.join(', ')}\n`;
                                codeChanges.push(...data.files_changed.map(f => ({ path: f })));
                                // 实时刷新文件列表
                                loadCodeAgentFiles();
                            }
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'step_error') {
                            // 步骤错误
                            fullResponse += `  ❌ 错误: ${data.error}\n`;
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'plan_completed') {
                            // 计划完成
                            fullResponse += `\n🎉 **计划执行完成！**\n`;
                            if (data.summary) {
                                fullResponse += data.summary + '\n';
                            }
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse);
                        } else if (data.type === 'content') {
                            // 旧的 content 类型兼容
                            fullResponse += data.content;
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse) + '<span class="typing-cursor"></span>';
                        } else if (data.type === 'code_change') {
                            codeChanges.push(data.change);
                        } else if (data.type === 'done') {
                            // 完成，移除光标
                            botDiv.innerHTML = formatCodeAgentMessage(fullResponse);
                            // 更新缓存中的 bot 消息
                            updateBotMessageInCache(botDiv, fullResponse);
                            // 更新流引用
                            if (codeAgentActiveStream) {
                                codeAgentActiveStream.fullResponse = fullResponse;
                            }
                        } else if (data.type === 'error') {
                            botDiv.innerHTML = formatCodeAgentMessage('错误: ' + data.error);
                            // 更新缓存中的 bot 消息
                            updateBotMessageInCache(botDiv, '错误: ' + data.error);
                            // 更新流引用
                            if (codeAgentActiveStream) {
                                codeAgentActiveStream.fullResponse = '错误: ' + data.error;
                            }
                        }
                        
                        // 更新流引用中的 fullResponse
                        if (codeAgentActiveStream && codeAgentActiveStream.botDiv === botDiv) {
                            codeAgentActiveStream.fullResponse = fullResponse;
                        }

                        // 滚动到底部 (多重保障)
                        scrollToBottom(botDiv.parentElement);

                    } catch (e) {
                        console.error('Parse SSE error:', e, line);
                    }
                }
            }
        }

        // 显示代码变更
        if (codeChanges.length > 0) {
            displayCodeChanges(codeChanges);
        }

        // 刷新文件列表
        await loadCodeAgentFiles();

        // 如果有新文件，自动选择第一个
        if (codeChanges.length > 0 && !codeAgentCurrentFile) {
            selectCodeAgentFile(codeChanges[0].path);
        }

    } catch (error) {
        botDiv.innerHTML = formatCodeAgentMessage('发送失败: ' + error.message);
        // 更新缓存中的 bot 消息
        updateBotMessageInCache(botDiv, '发送失败: ' + error.message);
        // 更新流引用
        if (codeAgentActiveStream) {
            codeAgentActiveStream.fullResponse = '发送失败: ' + error.message;
        }
    } finally {
        // 清除流引用
        codeAgentActiveStream = null;
        input.disabled = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

// 更新缓存中的 bot 消息（用于流式消息）
function updateBotMessageInCache(botDiv, content) {
    if (!codeAgentCurrentProject || !codeAgentMessagesCache[codeAgentCurrentProject]) {
        return;
    }
    
    const messages = codeAgentMessagesCache[codeAgentCurrentProject];
    // 找到最后一条 bot 消息（应该就是当前这条）
    for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].type === 'bot') {
            messages[i].content = formatCodeAgentMessage(content);
            break;
        }
    }
}

// 追加聊天消息
function appendCodeAgentMessage(type, message) {
    const container = document.getElementById('codeAgentMessages');
    if (!container) {
        console.error('codeAgentMessages container not found');
        return null;
    }
    
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
        
        // 限制消息数量
        if (codeAgentMessagesCache[codeAgentCurrentProject].length > MAX_MESSAGES_PER_PROJECT) {
            codeAgentMessagesCache[codeAgentCurrentProject].shift(); // 移除最早的消息
        }
    } else {
        console.warn('appendCodeAgentMessage: codeAgentCurrentProject is null');
    }
    
    return div;
}

// 格式化代码 Agent 消息（支持 Markdown）
function formatCodeAgentMessage(message) {
    if (!message) return '';

    // 先处理代码块（避免内部内容被其他规则处理）
    const codeBlocks = [];
    let formatted = message.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const placeholder = `__CODE_BLOCK_${codeBlocks.length}__`;
        codeBlocks.push(`<pre><code class="language-${lang || 'plaintext'}">${escapeHtml(code)}</code></pre>`);
        return placeholder;
    });

    // 转义 HTML（代码块已经单独处理）
    formatted = escapeHtml(formatted);

    // 恢复代码块占位符
    codeBlocks.forEach((block, i) => {
        formatted = formatted.replace(`__CODE_BLOCK_${i}__`, block);
    });

    // 处理标题 ## xxx
    formatted = formatted.replace(/^## (.+)$/gm, '<strong style="font-size: 1.1em;">$1</strong>');
    formatted = formatted.replace(/^### (.+)$/gm, '<strong>$1</strong>');

    // 处理粗体 **text**
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // 处理斜体 *text* （但不匹配 ** 粗体）
    formatted = formatted.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

    // 处理行内代码 `code`
    formatted = formatted.replace(/`([^`]+)`/g, '<code style="background: rgba(255,255,255,0.1); padding: 2px 6px; border-radius: 3px;">$1</code>');

    // 处理列表项 - item
    formatted = formatted.replace(/^- (.+)$/gm, '• $1');

    // 处理换行
    formatted = formatted.replace(/\n/g, '<br>');

    return formatted;
}

// 辅助：鲁棒的滚动到底部函数
function scrollToBottom(container) {
    if (!container) return;

    // 立即尝试滚动
    container.scrollTop = container.scrollHeight;

    // 稍后再次滚动以确保渲染完成
    requestAnimationFrame(() => {
        container.scrollTop = container.scrollHeight;

        // 双重保障，防止图片或复杂内容渲染延迟
        setTimeout(() => {
            container.scrollTop = container.scrollHeight;
        }, 50);
    });
}

// 显示代码变更
function displayCodeChanges(changes) {
    const panel = document.getElementById('codePanelContent');
    if (!panel) return;

    let html = '';
    changes.forEach(change => {
        html += `
            <div class="code-change-item">
                <div class="code-change-header">${change.path}</div>
                <div class="code-change-content">
                    <pre><code class="language-python">${escapeHtml(change.content)}</code></pre>
                </div>
            </div>
        `;
    });

    panel.innerHTML = html;

    // Prism 高亮
    if (window.Prism) {
        panel.querySelectorAll('code').forEach(block => {
            Prism.highlightElement(block);
        });
    }
}

// 切换代码面板
function toggleCodePanel() {
    const panel = document.querySelector('.code-panel-section');
    const btn = document.getElementById('togglePanelBtn');

    if (panel) {
        panel.classList.toggle('collapsed');
        if (btn) {
            btn.textContent = panel.classList.contains('collapsed') ? '展开' : '收起';
        }
    }
}

// ==========================================
// 代码执行功能
// ==========================================

// 运行代码（SSE 流式）
async function runCodeAgentCode() {
    if (!codeAgentCurrentProject || !codeAgentCurrentFile) {
        alert('请先选择要执行的文件');
        return;
    }

    if (codeAgentExecutingTaskId) {
        alert('已有代码在执行中');
        return;
    }

    const timeoutSelect = document.getElementById('executionTimeout');
    const timeout = timeoutSelect ? timeoutSelect.value : '300';

    // 根据超时值转换格式
    let timeoutStr = '5min';
    const timeoutNum = parseInt(timeout);
    if (timeoutNum === 60) timeoutStr = '1min';
    else if (timeoutNum === 300) timeoutStr = '5min';
    else if (timeoutNum === 1800) timeoutStr = '30min';
    else if (timeoutNum === 0) timeoutStr = 'unlimited';

    codeAgentExecutingTaskId = 'running';
    codeAgentExecutionStartTime = Date.now();
    startExecutionTimer();
    updateExecutionStatus('running', '执行中...');

    const outputContainer = document.getElementById('executionOutput');
    if (outputContainer) outputContainer.innerHTML = '';

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                file_path: codeAgentCurrentFile,
                timeout: timeoutStr
            })
        });

        if (!response.ok) {
            const error = await response.json();
            updateExecutionStatus('error', error.error || '执行失败');
            codeAgentExecutingTaskId = null;
            stopExecutionTimer();
            return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // 处理 SSE 数据
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleExecutionEvent(data);
                    } catch (e) {
                        // 忽略解析错误
                    }
                }
            }
        }
    } catch (error) {
        console.error('执行错误:', error);
        updateExecutionStatus('error', '执行失败: ' + error.message);
    } finally {
        stopExecutionTimer();
        codeAgentExecutingTaskId = null;
    }
}

// 停止执行
async function stopCodeAgentExecution() {
    if (!codeAgentExecutingTaskId || !codeAgentCurrentProject) return;

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/stop`, {
            method: 'POST'
        });

        const data = await response.json();
        if (data.success) {
            updateExecutionStatus('error', '已停止');
        } else {
            console.error('停止失败:', data.error);
        }
    } catch (error) {
        console.error('停止错误:', error);
    }
}

// 处理执行事件
function handleExecutionEvent(data) {
    const outputContainer = document.getElementById('executionOutput');
    if (!outputContainer) return;

    if (data.type === 'stdout' || data.type === 'stderr') {
        const line = document.createElement('div');
        line.className = `output-line output-${data.type}`;
        line.textContent = data.content;
        outputContainer.appendChild(line);
        outputContainer.scrollTop = outputContainer.scrollHeight;
    } else if (data.type === 'exit') {
        stopExecutionTimer();
        codeAgentExecutingTaskId = null;

        if (data.exit_code === 0) {
            updateExecutionStatus('success', `完成 (${formatDuration(data.duration)})`);
        } else if (data.exit_code === -1) {
            updateExecutionStatus('error', '超时终止');
        } else {
            updateExecutionStatus('error', `退出码: ${data.exit_code}`);
        }
    } else if (data.type === 'error') {
        stopExecutionTimer();
        codeAgentExecutingTaskId = null;
        updateExecutionStatus('error', data.content);
    }
}

// 更新执行状态
function updateExecutionStatus(status, message) {
    const statusDiv = document.getElementById('executionStatus');
    const runBtn = document.getElementById('runCodeBtn');
    const stopBtn = document.getElementById('stopCodeBtn');

    if (statusDiv) {
        statusDiv.className = `execution-status ${status}`;
        statusDiv.innerHTML = `<span>${message}</span><span id="executionTimer"></span>`;
    }

    if (status === 'running') {
        if (runBtn) runBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
    } else {
        if (runBtn) runBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
    }
}

// 启动执行计时器
function startExecutionTimer() {
    codeAgentTimer = setInterval(() => {
        const timerSpan = document.getElementById('executionTimer');
        if (timerSpan && codeAgentExecutionStartTime) {
            const elapsed = Date.now() - codeAgentExecutionStartTime;
            timerSpan.textContent = ` (${formatDuration(elapsed / 1000)})`;
        }
    }, 1000);
}

// 停止执行计时器
function stopExecutionTimer() {
    if (codeAgentTimer) {
        clearInterval(codeAgentTimer);
        codeAgentTimer = null;
    }
}

// 格式化时长
function formatDuration(seconds) {
    if (seconds < 60) {
        return `${seconds.toFixed(1)}秒`;
    } else if (seconds < 3600) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}分${secs}秒`;
    } else {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        return `${hours}时${mins}分`;
    }
}

// ==========================================
// 代码 Agent 事件监听器
// ==========================================

// 在 DOMContentLoaded 中初始化代码 Agent 事件监听器
document.addEventListener('DOMContentLoaded', () => {
    // 项目选择器
    const projectSelector = document.getElementById('projectSelector');
    if (projectSelector) {
        projectSelector.addEventListener('change', (e) => selectCodeAgentProject(e.target.value));
    }

    // 创建项目按钮
    const createProjectBtn = document.getElementById('createProjectBtn');
    if (createProjectBtn) {
        createProjectBtn.addEventListener('click', createCodeAgentProject);
    }

    // 删除项目按钮
    const deleteProjectBtn = document.getElementById('deleteProjectBtn');
    if (deleteProjectBtn) {
        deleteProjectBtn.addEventListener('click', deleteCodeAgentProject);
    }

    // 聊天发送按钮
    const codeAgentSendBtn = document.getElementById('codeAgentSendBtn');
    if (codeAgentSendBtn) {
        codeAgentSendBtn.addEventListener('click', sendCodeAgentMessage);
    }

    // 聊天输入框回车发送
    const codeAgentInput = document.getElementById('codeAgentInput');
    if (codeAgentInput) {
        codeAgentInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendCodeAgentMessage();
            }
        });
    }

    // 编辑文件按钮
    const editFileBtn = document.getElementById('editFileBtn');
    if (editFileBtn) {
        editFileBtn.addEventListener('click', enterCodeAgentEditMode);
    }

    // 保存文件按钮
    const saveFileBtn = document.getElementById('saveFileBtn');
    if (saveFileBtn) {
        saveFileBtn.addEventListener('click', saveCodeAgentFile);
    }

    // 取消编辑按钮
    const cancelEditBtn = document.getElementById('cancelEditBtn');
    if (cancelEditBtn) {
        cancelEditBtn.addEventListener('click', cancelCodeAgentEdit);
    }

    // 切换代码面板按钮
    const togglePanelBtn = document.getElementById('togglePanelBtn');
    if (togglePanelBtn) {
        togglePanelBtn.addEventListener('click', toggleCodePanel);
    }

    // 运行代码按钮
    const runCodeBtn = document.getElementById('runCodeBtn');
    if (runCodeBtn) {
        runCodeBtn.addEventListener('click', runCodeAgentCode);
    }

    // 停止执行按钮
    const stopCodeBtn = document.getElementById('stopCodeBtn');
    if (stopCodeBtn) {
        stopCodeBtn.addEventListener('click', stopCodeAgentExecution);
    }

    // 命令输入框回车执行
    const commandInput = document.getElementById('commandInput');
    if (commandInput) {
        commandInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                executeCommandStream(commandInput.value);
                commandInput.value = '';
            }
        });
    }

    // 清空输出按钮
    const clearOutputBtn = document.getElementById('clearOutputBtn');
    if (clearOutputBtn) {
        clearOutputBtn.addEventListener('click', clearExecutionOutput);
    }
});

// ==========================================
// Shell 命令流式执行
// ==========================================

// 当前正在执行的命令进程 ID
let currentCommandProcessId = null;
let commandEventSource = null;

/**
 * 流式执行 shell 命令
 */
async function executeCommandStream(command) {
    if (!command || !command.trim()) return;
    if (!codeAgentCurrentProject) {
        alert('请先选择一个项目');
        return;
    }

    const outputContainer = document.getElementById('executionOutput');
    const commandSpinner = document.getElementById('commandSpinner');
    const stopBtn = document.getElementById('stopCodeBtn');
    const timeout = parseInt(document.getElementById('executionTimeout')?.value || '300');

    // 显示命令
    appendExecutionOutput('command', `$ ${command}`);

    // 显示加载状态
    if (commandSpinner) commandSpinner.style.display = 'inline';
    if (stopBtn) stopBtn.disabled = false;

    // 启动计时器
    codeAgentExecutionStartTime = Date.now();
    startExecutionTimer();
    updateExecutionStatus('running', '执行中...');

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/run-command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command, timeout })
        });

        // 获取进程 ID
        currentCommandProcessId = response.headers.get('X-Process-Id');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // 处理 SSE 格式的数据
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleCommandEvent(data);
                    } catch (e) {
                        console.error('解析命令事件失败:', e);
                    }
                }
            }
        }

    } catch (error) {
        console.error('命令执行错误:', error);
        appendExecutionOutput('stderr', `错误: ${error.message}`);
    } finally {
        if (commandSpinner) commandSpinner.style.display = 'none';
        stopExecutionTimer();
        currentCommandProcessId = null;
        if (stopBtn) stopBtn.disabled = true;
    }
}

/**
 * 处理命令执行事件
 */
function handleCommandEvent(data) {
    switch (data.type) {
        case 'started':
            console.log('命令开始执行:', data.command, 'process_id:', data.process_id);
            currentCommandProcessId = data.process_id;
            break;

        case 'stdout':
            appendExecutionOutput('stdout', data.data);
            break;

        case 'stderr':
            appendExecutionOutput('stderr', data.data);
            break;

        case 'exit':
            const exitClass = data.success ? 'exit-success' : 'exit-error';
            appendExecutionOutput(exitClass, `[退出码: ${data.code}, 耗时: ${data.duration}秒]`);
            updateExecutionStatus(data.success ? 'success' : 'error',
                `${data.success ? '完成' : '失败'} (${formatDuration(data.duration)})`);
            break;

        case 'terminated':
            appendExecutionOutput('terminated', `[进程已终止] ${data.message}`);
            updateExecutionStatus('error', '已终止');
            break;

        case 'error':
            appendExecutionOutput('stderr', `错误: ${data.message}`);
            updateExecutionStatus('error', data.message);
            break;
    }
}

/**
 * 追加执行输出
 */
function appendExecutionOutput(type, text) {
    const outputContainer = document.getElementById('executionOutput');
    if (!outputContainer) return;

    // 移除占位符
    const placeholder = outputContainer.querySelector('.output-placeholder');
    if (placeholder) placeholder.remove();

    const line = document.createElement('div');
    line.className = `output-line output-${type}`;
    line.textContent = text;
    outputContainer.appendChild(line);

    // 自动滚动到底部
    outputContainer.scrollTop = outputContainer.scrollHeight;
}

/**
 * 清空执行输出
 */
function clearExecutionOutput() {
    const outputContainer = document.getElementById('executionOutput');
    if (outputContainer) {
        outputContainer.innerHTML = '<div class="output-placeholder">运行代码或执行命令，输出将实时显示在这里...</div>';
    }
}

/**
 * 终止当前命令
 */
async function terminateCurrentCommand() {
    if (!currentCommandProcessId) {
        console.log('没有正在运行的命令');
        return;
    }

    try {
        const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/terminate-command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ process_id: currentCommandProcessId })
        });

        const data = await response.json();
        if (data.success) {
            appendExecutionOutput('terminated', '[命令已被用户终止]');
        } else {
            console.error('终止失败:', data.message);
        }
    } catch (error) {
        console.error('终止命令错误:', error);
    }
}

// 修改停止按钮行为，支持终止命令
const originalStopCodeAgentExecution = typeof stopCodeAgentExecution === 'function' ? stopCodeAgentExecution : null;
async function stopCodeAgentExecution() {
    // 如果有正在执行的命令，先终止命令
    if (currentCommandProcessId) {
        await terminateCurrentCommand();
    }

    // 然后调用原有的停止逻辑（如果存在）
    if (codeAgentExecutingTaskId && originalStopCodeAgentExecution) {
        // 原有逻辑
        try {
            const response = await fetch(`/api/code-agent/projects/${codeAgentCurrentProject}/stop`, {
                method: 'POST'
            });
            const data = await response.json();
            if (data.success) {
                updateExecutionStatus('error', '已停止');
            }
        } catch (error) {
            console.error('停止错误:', error);
        }
    }

    stopExecutionTimer();
    const stopBtn = document.getElementById('stopCodeBtn');
    if (stopBtn) stopBtn.disabled = true;
}

