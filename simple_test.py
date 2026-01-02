"""
简单的测试脚本 - 测试重构后的Agent
"""

import requests
import json
import time

BASE_URL = "http://localhost:8080"

def test_agent_smart_extraction():
    """测试AI智能提取状态信息"""
    print("=" * 80)
    print("测试AI智能提取状态信息（重构后）")
    print("=" * 80)
    
    # 1. 初始化会话
    print("\n[步骤1] 初始化会话...")
    response = requests.post(f"{BASE_URL}/api/init")
    data = response.json()
    
    if not data.get('success'):
        print(f"❌ 会话初始化失败: {data.get('error')}")
        return
    
    session_id = data['session_id']
    print(f"✅ 会话初始化成功，Session ID: {session_id}")
    
    # 2. 测试多轮对话 - AI应该能智能提取状态
    test_conversations = [
        {
            "message": "我想做BTC和ETH的现货交易",
            "expected_fields": ["market", "symbols"],
            "description": "测试市场类型和交易对提取"
        },
        {
            "message": "用5分钟K线",
            "expected_fields": ["timeframe"],
            "description": "测试时间周期提取"
        },
        {
            "message": "当RSI低于30且MACD金叉时买入",
            "expected_fields": ["indicators_required", "entry_rules"],
            "description": "测试指标和建仓规则提取"
        },
        {
            "message": "止盈3%，止损2%",
            "expected_fields": ["take_profit", "stop_loss"],
            "description": "测试止盈止损提取"
        },
        {
            "message": "每次最多用20%的资金",
            "expected_fields": ["max_position_ratio"],
            "description": "测试仓位比例提取"
        }
    ]
    
    for i, test_case in enumerate(test_conversations, 1):
        print(f"\n[步骤{i+1}] {test_case['description']}")
        print(f"   用户消息: \"{test_case['message']}\"")
        
        time.sleep(1)  # 避免请求过快
        
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json={
                "session_id": session_id,
                "message": test_case['message']
            }
        )
        
        data = response.json()
        
        if not data.get('success'):
            print(f"   ❌ 对话失败: {data.get('error')}")
            continue
        
        print(f"   ✅ Agent响应: {data['response'][:80]}...")
        
        # 检查状态是否正确更新
        state = data.get('state', {})
        user_req = state.get('user_requirements', {})
        
        print(f"   📊 状态更新:")
        for field in test_case['expected_fields']:
            value = user_req.get(field)
            if value:
                if isinstance(value, list):
                    print(f"      ✅ {field}: {value}")
                else:
                    print(f"      ✅ {field}: {value}")
            else:
                print(f"      ⚠️  {field}: 未提取到")
    
    # 3. 获取最终状态
    print(f"\n[步骤7] 获取最终状态...")
    response = requests.get(f"{BASE_URL}/api/state/{session_id}")
    data = response.json()
    
    if data.get('success'):
        print("✅ 状态获取成功")
        print("\n" + "=" * 80)
        print("最终收集的信息:")
        print("=" * 80)
        
        state = data.get('state', {})
        user_req = state.get('user_requirements', {})
        
        print(f"\n市场类型: {user_req.get('market', '未设置')}")
        print(f"交易对: {user_req.get('symbols', [])}")
        print(f"K线周期: {user_req.get('timeframe', '未设置')}")
        print(f"建仓规则: {user_req.get('entry_rules', '未设置')}")
        print(f"止盈规则: {user_req.get('take_profit', '未设置')}")
        print(f"止损规则: {user_req.get('stop_loss', '未设置')}")
        print(f"最大仓位: {user_req.get('max_position_ratio', '未设置')}")
        print(f"所需指标: {user_req.get('indicators_used', [])}")
        
        print(f"\n完整性: {'✅ 完整' if data.get('is_complete') else '⚠️  不完整'}")
        if not data.get('is_complete'):
            print(f"缺失字段: {data.get('missing_fields', [])}")
        
        print("\n" + "=" * 80)
        print("测试完成！")
        print("=" * 80)
        
        # 评估AI提取效果
        print("\n📈 AI提取效果评估:")
        expected_keys = ['market', 'symbols', 'timeframe', 'entry_rules', 
                        'take_profit', 'stop_loss', 'max_position_ratio']
        extracted_count = sum(1 for key in expected_keys if user_req.get(key))
        print(f"   预期提取字段: {len(expected_keys)}")
        print(f"   成功提取字段: {extracted_count}")
        print(f"   提取成功率: {extracted_count/len(expected_keys)*100:.1f}%")
        
        if extracted_count >= len(expected_keys) * 0.8:
            print("   ✅ AI智能提取效果良好！")
        else:
            print("   ⚠️  AI提取效果有待提升，建议查看日志优化prompt")
    else:
        print(f"❌ 获取状态失败: {data.get('error')}")

if __name__ == "__main__":
    print("\n" + "🚀" * 40)
    print("量化Agent重构测试 - AI智能状态提取")
    print("🚀" * 40 + "\n")
    
    try:
        test_agent_smart_extraction()
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n")

