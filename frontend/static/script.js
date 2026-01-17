// 全局变量
let sessionId = null;
let finalRulesData = null;
let currentModel = "openrouter:anthropic/claude-sonnet-4";
let currentChatMode = 'collector'; // 'collector' or 'executor'

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

function switchAgent(mode) {
    if (mode === currentChatMode) return;

    currentChatMode = mode;

    // 更新导航样式
    document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));

    const collectorView = document.getElementById('collectorView');
    const executorView = document.getElementById('executorView');
    const ruleDetailView = document.getElementById('ruleDetailView');
    const headerTitle = document.querySelector('.header h1');

    // 切换时先隐藏所有视图
    if (ruleDetailView) ruleDetailView.style.display = 'none';
    currentRuleId = null;  // 重置当前规则ID

    if (mode === 'collector') {
        document.getElementById('navRuleCollector').classList.add('active');
        if (collectorView) collectorView.style.display = 'grid';
        if (executorView) executorView.style.display = 'none';
        if (headerTitle) headerTitle.innerText = '🤖 量化规则收集 Agent';
    } else {
        document.getElementById('navRuleExecutor').classList.add('active');
        if (collectorView) collectorView.style.display = 'none';
        if (executorView) executorView.style.display = 'grid';
        if (headerTitle) headerTitle.innerText = '⚡ 量化规则执行 Agent';
        loadExecutionRules();
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

