// 全局变量
let sessionId = null;
let finalRulesData = null;
let currentModel = "deepseek:deepseek-chat";

// 页面加载完成后初始化
// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initSession();
    loadIndicators();
    setupEventListeners();
    checkLoginStatus(); // 检查登录状态
});

// 设置事件监听器
function setupEventListeners() {
    // 发送按钮
    document.getElementById('sendBtn').addEventListener('click', sendMessage);
    
    // 回车发送
    document.getElementById('userInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // 重置按钮
    document.getElementById('resetBtn').addEventListener('click', resetSession);
    
    // 生成最终规则按钮
    document.getElementById('finalizeBtn').addEventListener('click', finalizeRules);
    
    // 模型切换
    document.getElementById('modelSelector').addEventListener('change', switchModel);
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
    const finalizeBtn = document.getElementById('finalizeBtn');
    
    // 更新完整性指示器
    if (isComplete) {
        indicator.className = 'completeness-indicator complete';
        indicator.textContent = '✅ 已完成';
        indicator.textContent = '✅ 已完成';
        finalizeBtn.disabled = false;
        document.getElementById('saveRuleBtn').disabled = false; // 启用保存按钮
    } else {
        indicator.className = 'completeness-indicator incomplete';
        indicator.textContent = '⚠️ 未完成';
        indicator.textContent = '⚠️ 未完成';
        finalizeBtn.disabled = true;
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
    
    // 使用的指标
    if (state.execution_logic && state.execution_logic.indicators_used.length > 0) {
        html += createStateItem('技术指标', state.execution_logic.indicators_used.join(', '));
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

// 加载指标列表
async function loadIndicators() {
    try {
        const response = await fetch('/api/indicators');
        const data = await response.json();
        
        if (data.success) {
            const content = document.getElementById('indicatorsContent');
            let html = '';
            
            data.indicators.forEach(ind => {
                html += `<div class="indicator-item">
                    <div class="indicator-name">${ind.name}</div>
                    <div class="indicator-full-name">${ind.full_name}</div>
                    <div class="indicator-desc">${ind.description}</div>
                    <div class="indicator-example">${ind.example}</div>
                </div>`;
            });
            
            content.innerHTML = html;
        }
    } catch (error) {
        console.error('加载指标失败:', error);
    }
}

// 切换指标面板
function toggleIndicators() {
    const section = document.querySelector('.indicators-section');
    const content = document.getElementById('indicatorsContent');
    
    if (content.style.display === 'none') {
        content.style.display = 'block';
        section.classList.remove('collapsed');
    } else {
        content.style.display = 'none';
        section.classList.add('collapsed');
    }
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

// 重置会话
async function resetSession() {
    if (!confirm('确定要重置会话吗？这将清空所有对话和收集的信息。')) {
        return;
    }
    
    try {
        if (sessionId) {
            await fetch(`/api/reset/${sessionId}`, {
                method: 'POST'
            });
        }
        
        // 清空聊天记录
        document.getElementById('chatMessages').innerHTML = '';
        
        // 清空状态面板
        document.getElementById('stateContent').innerHTML = '<div class="state-loading">等待收集信息...</div>';
        document.getElementById('completenessIndicator').className = 'completeness-indicator incomplete';
        document.getElementById('completenessIndicator').textContent = '未完成';
        document.getElementById('finalizeBtn').disabled = true;
        
        // 重新初始化
        await initSession();
        
    } catch (error) {
        alert('重置失败: ' + error.message);
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
window.onclick = function(event) {
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
// 用户认证与保存逻辑
// ==========================================

let currentUser = null;
let pendingSave = false; // 登录后是否自动保存

// 检查登录状态
async function checkLoginStatus() {
    try {
        const response = await fetch('/api/check_status');
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
    const myRulesBtn = document.getElementById('myRulesBtn');
    const saveRuleBtn = document.getElementById('saveRuleBtn');
    
    if (currentUser) {
        userInfo.style.display = 'inline';
        userInfo.textContent = `👤 ${currentUser.username}`;
        authBtn.style.display = 'none';
        logoutBtn.style.display = 'inline-block';
        myRulesBtn.style.display = 'inline-block';
    } else {
        userInfo.style.display = 'none';
        authBtn.style.display = 'inline-block';
        logoutBtn.style.display = 'none';
        myRulesBtn.style.display = 'none';
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
            headers: {'Content-Type': 'application/json'},
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
            headers: {'Content-Type': 'application/json'},
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
    
    try {
        // 直接根据 session_id 保存，不需要前端传 content，后端自己取
        const response = await fetch('/api/save_rule', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                session_id: sessionId
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

// 显示我的策略
async function showMyRules() {
    const modal = document.getElementById('myRulesModal');
    const list = document.getElementById('rulesList');
    modal.style.display = 'block';
    
    list.innerHTML = '<div class="loading">加载中...</div>';
    
    try {
        const response = await fetch('/api/my_rules');
        const data = await response.json();
        
        if (data.success) {
            if (data.rules.length === 0) {
                list.innerHTML = '<div class="no-data">暂无保存的策略</div>';
                return;
            }
            
            let html = '';
            data.rules.forEach(rule => {
                // 确保content是对象
                let content = rule.content;
                if (typeof content === 'string') {
                    try { content = JSON.parse(content); } catch(e) {}
                }
                
                // 提取关键信息
                const req = content.user_requirements || {};
                const summary = `${req.exchange || '未指定'} | ${req.product || ''} | ${req.symbols ? req.symbols.join(',') : ''} | ${req.timeframe || ''}`;
                
                html += `
                <div class="rule-card">
                    <div class="rule-header">
                        <span class="rule-id">策略 #${rule.id}</span>
                        <span class="rule-date">${new Date(rule.created_at).toLocaleString()}</span>
                    </div>
                    <div class="rule-summary">${summary}</div>
                    <div class="rule-details">
                         ${req.entry_rules ? '<div>建仓: ' + req.entry_rules + '</div>' : ''}
                    </div>
                </div>
                `;
            });
            list.innerHTML = html;
        } else {
            list.innerHTML = '加载失败: ' + data.error;
        }
    } catch (error) {
        list.innerHTML = '加载错误: ' + error.message;
    }
}

function closeMyRulesModal() {
    document.getElementById('myRulesModal').style.display = 'none';
}

