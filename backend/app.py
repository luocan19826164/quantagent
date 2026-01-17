"""
Flask后端应用
提供API接口与前端交互
"""

from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import uuid
import os
import json
import logging
from dotenv import load_dotenv

from agent import SessionManager, QuantRuleCollectorAgent
from agent.execution_agent import QuantExecutionAgent
import database  # 引入数据库模块

# 先加载环境变量，再导入配置模块
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

# 从环境变量动态加载支持的模型配置
from utils.llm_config import get_supported_models, get_extra_headers

# 支持的模型配置（从环境变量动态读取）
SUPPORTED_MODELS = get_supported_models()
# Debug: Print loaded keys (masked)
print(f"DEBUG: OPENAI_API_KEY present: {'OPENAI_API_KEY' in os.environ}")
print(f"DEBUG: DEEPSEEK_API_KEY present: {'DEEPSEEK_API_KEY' in os.environ}")
print(f"DEBUG: DEEPSEEK_API_KEY value len: {len(os.environ.get('DEEPSEEK_API_KEY', ''))}")

app = Flask(
    __name__,
    template_folder='../frontend/templates',
    static_folder='../frontend/static'
)
app.secret_key = os.getenv("SECRET_KEY", "quant-agent-secret-key-2024")

# 屏蔽心跳接口的访问日志
class PollingLogFilter(logging.Filter):
    def filter(self, record):
        if hasattr(record, 'args') and len(record.args) > 0:
            request_line = str(record.args[0])
            if '/api/my_rules' in request_line or '/api/orders' in request_line:
                return 0
        return 1

logging.getLogger('werkzeug').addFilter(PollingLogFilter())
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 7  # 7 days
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # 允许同站点请求携带 cookie
CORS(app, supports_credentials=True)

# 全局会话管理器
session_manager = SessionManager()
# Agent实例缓存
agent_cache = {}
# 执行Agent
execution_agent = None


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/init', methods=['POST'])
def init_session():
    """初始化会话"""
    try:
        # 生成会话ID
        session_id = str(uuid.uuid4())
        
        # 创建状态
        state = session_manager.create_session(session_id)
        
        # 创建Agent
        agent = QuantRuleCollectorAgent(state)
        agent_cache[session_id] = agent
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "message": "会话初始化成功",
            "greeting": "你好！我是量化策略顾问助手。\n\n我可以帮你设计和完善量化交易策略。请告诉我你的策略想法，我会引导你逐步完善细节。\n\n比如你可以说：\n- 我想做一个趋势跟踪策略\n- 我想在RSI超卖时买入\n- 我想做均线金叉策略\n\n请开始描述你的策略吧！"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/chat', methods=['POST'])
def chat():
    """处理对话"""
    try:
        data = request.json
        session_id = data.get('session_id')
        user_message = data.get('message')
        
        if not session_id or not user_message:
            return jsonify({
                "success": False,
                "error": "缺少session_id或message参数"
            }), 400
        
        # 获取Agent
        agent = agent_cache.get(session_id)
        if not agent:
            # 尝试重建Agent
            state = session_manager.get_session(session_id)
            if not state:
                return jsonify({
                    "success": False,
                    "error": "会话不存在，请重新初始化"
                }), 404
            agent = QuantRuleCollectorAgent(state)
            agent_cache[session_id] = agent
        
        # 处理消息
        result = agent.chat(user_message)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/state/<session_id>', methods=['GET'])
def get_state(session_id):
    """获取当前状态"""
    try:
        state = session_manager.get_session(session_id)
        if not state:
            return jsonify({
                "success": False,
                "error": "会话不存在"
            }), 404
        
        is_complete, missing_fields = state.check_completeness()
        
        return jsonify({
            "success": True,
            "state": state.to_dict(),
            "is_complete": is_complete,
            "missing_fields": missing_fields,
            "summary": state.get_summary()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/rules/<int:rule_id>/toggle', methods=['POST'])
def toggle_rule(rule_id):
    """开启或停止规则执行"""
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "请先登录"}), 401
        
    try:
        data = request.json
        active = data.get('active', False)
        
        global execution_agent
        if execution_agent is None:
            execution_agent = QuantExecutionAgent(database)
            
        if active:
            success = execution_agent.start_rule_execution(rule_id)
        else:
            success = execution_agent.stop_rule_execution(rule_id)
            
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/rules/<int:rule_id>/detail', methods=['GET'])
def get_rule_detail(rule_id):
    """获取规则详情及其相关订单"""
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "请先登录"}), 401
        
    try:
        conn = database.get_db_connection()
        c = conn.cursor()
        
        # 获取规则详情（验证用户权限）
        c.execute('''
            SELECT * FROM saved_rules 
            WHERE id = ? AND user_id = ?
        ''', (rule_id, session['user_id']))
        rule_row = c.fetchone()
        
        if not rule_row:
            conn.close()
            return jsonify({"success": False, "error": "规则不存在或无权限访问"}), 404
        
        # 获取该规则的所有订单
        c.execute('''
            SELECT * FROM orders 
            WHERE rule_id = ?
            ORDER BY created_at DESC
        ''', (rule_id,))
        order_rows = c.fetchall()
        conn.close()
        
        # 构建规则信息
        rule = {
            "id": rule_row['id'],
            "name": rule_row['name'],
            "content": json.loads(rule_row['rule_content']),
            "total_capital": rule_row['total_capital'],
            "status": rule_row['status'],
            "created_at": rule_row['created_at']
        }
        
        # 构建订单列表
        orders = []
        for r in order_rows:
            orders.append({
                "id": r['id'],
                "order_id": r['order_id'],
                "symbol": r['symbol'],
                "side": r['side'],
                "amount": r['amount'],
                "price": r['price'],
                "status": r['status'],
                "pnl": r['pnl'],
                "created_at": r['created_at']
            })
        
        return jsonify({
            "success": True,
            "rule": rule,
            "orders": orders
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/orders', methods=['GET'])
def get_orders():
    """获取订单历史"""
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "请先登录"}), 401
        
    try:
        conn = database.get_db_connection()
        c = conn.cursor()
        c.execute('''
            SELECT o.*, r.rule_content 
            FROM orders o
            JOIN saved_rules r ON o.rule_id = r.id
            WHERE r.user_id = ?
            ORDER BY o.created_at DESC
        ''', (session['user_id'],))
        rows = c.fetchall()
        conn.close()
        
        orders = []
        for r in rows:
            orders.append({
                "id": r['id'],
                "rule_id": r['rule_id'],
                "symbol": r['symbol'],
                "side": r['side'],
                "amount": r['amount'],
                "price": r['price'],
                "status": r['status'],
                "pnl": r['pnl'],
                "created_at": r['created_at']
            })
        return jsonify({"success": True, "orders": orders})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/finalize/<session_id>', methods=['POST'])
def finalize_rules(session_id):
    """完成规则收集，获取最终配置"""
    try:
        state = session_manager.get_session(session_id)
        if not state:
            return jsonify({
                "success": False,
                "error": "会话不存在"
            }), 404
        
        is_complete, missing_fields = state.check_completeness()
        
        if not is_complete:
            return jsonify({
                "success": False,
                "error": "规则信息不完整",
                "missing_fields": missing_fields
            }), 400
        
        # 生成执行逻辑分析
        agent = agent_cache.get(session_id)
        if agent:
            # 基于收集的信息生成执行步骤
            state.set_analysis(f"基于用户需求生成的量化策略执行逻辑")
            
            # 生成执行步骤
            steps = []
            
            # 步骤1: 数据获取
            steps.append(f"获取{state.user_requirements['symbols']}的{state.user_requirements['timeframe']}K线数据")
            
            # 步骤2: 指标计算
            if state.execution_logic['indicators_used']:
                steps.append(f"计算技术指标: {', '.join(state.execution_logic['indicators_used'])}")
            
            # 步骤3: 信号判断
            steps.append(f"判断建仓信号: {state.user_requirements['entry_rules']}")
            
            # 步骤4: 仓位管理
            steps.append(f"按最大仓位比例 {state.user_requirements['max_position_ratio']} 开仓")
            
            # 步骤5: 风险管理
            steps.append(f"设置止盈: {state.user_requirements['take_profit']}, 止损: {state.user_requirements['stop_loss']}")
            
            for step in steps:
                state.add_execution_step(step)
        
        final_rules = state.to_dict()
        
        return jsonify({
            "success": True,
            "rules": final_rules,
            "message": "规则收集完成！这份配置可用于后续的执行Agent。"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/reset/<session_id>', methods=['POST'])
def reset_session(session_id):
    """重置会话"""
    try:
        # 删除Agent
        if session_id in agent_cache:
            del agent_cache[session_id]
        
        # 删除状态
        session_manager.delete_session(session_id)
        
        return jsonify({
            "success": True,
            "message": "会话已重置"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/indicators', methods=['GET'])
def get_indicators():
    """获取所有可用指标（从 @tool 注解自动提取）"""
    from tool.capability_manifest import get_indicators_for_api
    indicators = get_indicators_for_api()
    return jsonify({
        "success": True,
        "indicators": indicators
    })


@app.route('/api/markets', methods=['GET'])
def get_markets():
    """获取市场配置（从 tools_catalog 常量读取）"""
    from tool.tools_catalog import SUPPORTED_MARKETS, SUPPORTED_SYMBOLS, SUPPORTED_TIMEFRAMES
    # 转换时间周期为前端期望的 {value, label} 格式
    label_map = {
        "1m": "1分钟", "5m": "5分钟", "15m": "15分钟", "30m": "30分钟",
        "1h": "1小时", "4h": "4小时", "1d": "日线", "1w": "周线", "1M": "月线"
    }
    timeframes = [{"value": v, "label": label_map.get(v, v)} for v in SUPPORTED_TIMEFRAMES]
    return jsonify({
        "success": True,
        "markets": SUPPORTED_MARKETS,
        "symbols": SUPPORTED_SYMBOLS,
        "timeframes": timeframes
    })


@app.route('/api/models', methods=['GET'])
def get_available_models():
    """获取所有可用的模型列表"""
    models = []
    for provider, config in SUPPORTED_MODELS.items():
        models.append({
            "provider": provider,
            "models": config["models"],
            "base_url": config["base_url"]
        })
    return jsonify({
        "success": True,
        "models": models
    })


@app.route('/api/switch-model/<session_id>', methods=['POST'])
def switch_model(session_id):
    """切换模型"""
    try:
        data = request.json
        provider = data.get('provider')
        model_name = data.get('model')
        
        if not provider or not model_name:
            return jsonify({
                "success": False,
                "error": "缺少provider或model参数"
            }), 400
        
        # 验证模型
        if provider not in SUPPORTED_MODELS:
            return jsonify({
                "success": False,
                "error": f"不支持的提供商: {provider}"
            }), 400
        
        if model_name not in SUPPORTED_MODELS[provider]["models"]:
            return jsonify({
                "success": False,
                "error": f"不支持的模型: {model_name}"
            }), 400
        
        # 获取Agent
        agent = agent_cache.get(session_id)
        if not agent:
            return jsonify({
                "success": False,
                "error": "会话不存在"
            }), 404
        
        # 获取API密钥
        provider_config = SUPPORTED_MODELS[provider]
        api_key = os.getenv(provider_config["api_key_env"])
        if not api_key:
            return jsonify({
                "success": False,
                "error": f"未配置{provider_config['api_key_env']}环境变量"
            }), 400
        
        # 切换模型
        base_url = provider_config["base_url"]
        
        # 获取额外的 headers（如果需要）
        extra_headers = get_extra_headers(provider)
        
        agent.switch_model(model_name, api_key, base_url, extra_headers)
        
        return jsonify({
            "success": True,
            "message": f"已切换模型到 {model_name}",
            "current_model": agent.get_current_model_info()
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/model-info/<session_id>', methods=['GET'])
def get_model_info(session_id):
    """获取当前使用的模型信息"""
    try:
        agent = agent_cache.get(session_id)
        if not agent:
            return jsonify({
                "success": False,
                "error": "会话不存在"
            }), 404
        
        return jsonify({
            "success": True,
            "model_info": agent.get_current_model_info()
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==========================================
# 用户认证与规则保存 API
# ==========================================

@app.route('/api/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({"success": False, "error": "用户名和密码不能为空"}), 400
            
        user_id = database.create_user(username, password)
        if not user_id:
            return jsonify({"success": False, "error": "用户名已存在"}), 400
            
        # 注册成功自动登录
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        
        return jsonify({
            "success": True, 
            "message": "注册成功",
            "user": {"id": user_id, "username": username}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        user = database.verify_user(username, password)
        if not user:
            return jsonify({"success": False, "error": "用户名或密码错误"}), 401
            
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        
        return jsonify({
            "success": True, 
            "message": "登录成功",
            "user": {"id": user['id'], "username": user['username']}
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/check_status', methods=['GET'])
def check_status():
    """检查登录状态"""
    if 'user_id' in session:
        return jsonify({
            "success": True, 
            "is_logged_in": True,
            "user": {"id": session['user_id'], "username": session['username']}
        })
    return jsonify({"success": True, "is_logged_in": False})

@app.route('/api/logout', methods=['POST'])
def logout():
    """退出登录"""
    session.clear()
    return jsonify({"success": True, "message": "已退出登录"})

@app.route('/api/save_rule', methods=['POST'])
def save_rule_api():
    """保存规则"""
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "请先登录"}), 401
        
    try:
        data = request.json
        # 支持直接传全部规则，或者只传session_id让后端去取
        rule_content = data.get('rule_content')
        session_id = data.get('session_id')
        
        if not rule_content and session_id:
            # 如果只传了session_id，尝试从内存获取当前状态
            state = session_manager.get_session(session_id)
            if state:
                # 验证完整性
                is_complete, _ = state.check_completeness()
                if not is_complete:
                    return jsonify({"success": False, "error": "策略信息尚未完善，请继续补充必要信息后再保存"}), 400
                rule_content = state.to_dict()
        
        if not rule_content:
            return jsonify({"success": False, "error": "缺少规则内容"}), 400
            
        strategy_name = data.get('name')
        rule_id = database.save_rule(session['user_id'], rule_content, name=strategy_name)
        if not rule_id:
            return jsonify({"success": False, "error": "保存失败"}), 500
            
        return jsonify({
            "success": True, 
            "message": "规则保存成功",
            "rule_id": rule_id
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/my_rules', methods=['GET'])
def get_my_rules():
    """获取我的规则列表"""
    if 'user_id' not in session:
        return jsonify({"success": False, "error": "请先登录"}), 401
        
    try:
        rules = database.get_user_rules(session['user_id'])
        # 补充状态信息
        for r in rules:
            conn = database.get_db_connection()
            c = conn.cursor()
            c.execute('SELECT status, total_capital FROM saved_rules WHERE id = ?', (r['id'],))
            row = c.fetchone()
            conn.close()
            if row:
                r['status'] = row['status']
                r['total_capital'] = row['total_capital']
                
        return jsonify({"success": True, "rules": rules})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def resume_running_rules():
    """恢复之前标记为 running 的策略执行"""
    global execution_agent
    try:
        conn = database.get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM saved_rules WHERE status = 'running'")
        running_rules = c.fetchall()
        conn.close()
        
        if running_rules:
            logging.info(f"Found {len(running_rules)} running rules to resume")
            if execution_agent is None:
                execution_agent = QuantExecutionAgent(database)
            
            for rule in running_rules:
                rule_id = rule['id']
                success = execution_agent.start_rule_execution(rule_id)
                if success:
                    logging.info(f"✅ Resumed rule {rule_id}")
                else:
                    logging.warning(f"⚠️ Failed to resume rule {rule_id}")
        else:
            logging.info("No running rules to resume")
    except Exception as e:
        logging.error(f"Error resuming running rules: {e}")


if __name__ == '__main__':
    # 初始化数据库
    try:
        database.init_db()
    except Exception as e:
        print(f"❌ 数据库初始化失败: {e}")
    
    # 从环境变量获取 debug 模式，默认为 False
    # 标准 Flask 做法是检查 FLASK_DEBUG 环境变量 (1/True/true 为开启)
    flask_debug = os.environ.get('FLASK_DEBUG', '0').lower() in ['1', 'true', 'on']
    
    # 恢复运行中的策略
    # 逻辑：
    # 1. 如果不是 DEBUG 模式 -> 直接运行 (生产环境单进程)
    # 2. 如果是 DEBUG 模式 -> 仅在 reloader 子进程 (WERKZEUG_RUN_MAIN='true') 中运行，跳过主进程
    if not flask_debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        resume_running_rules()
        
    app.run(
        host='0.0.0.0',
        port=8081,
        debug=flask_debug
    )

