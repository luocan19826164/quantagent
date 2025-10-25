// 全局变量
let sessionId = null;
let finalRulesData = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    initSession();
    loadIndicators();
    setupEventListeners();
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
        } else {
            displayBotMessage('初始化失败: ' + data.error);
        }
    } catch (error) {
        displayBotMessage('初始化失败: ' + error.message);
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
        finalizeBtn.disabled = false;
    } else {
        indicator.className = 'completeness-indicator incomplete';
        indicator.textContent = '⚠️ 未完成';
        finalizeBtn.disabled = true;
    }
    
    // 构建状态显示
    let html = '';
    
    const requirements = state.user_requirements;
    
    // 市场类型
    if (requirements.market) {
        html += createStateItem('市场类型', requirements.market);
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
    if (event.target === modal) {
        closeFinalRulesModal();
    }
}

