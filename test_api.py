"""
API测试脚本
测试后端API是否正常工作
"""

import requests
import json
import time

BASE_URL = "http://localhost:5001"

def test_health():
    """测试基础接口"""
    print("=" * 60)
    print("1. 测试基础接口")
    print("=" * 60)
    
    # 测试主页
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("✅ 主页访问正常")
        else:
            print(f"❌ 主页访问失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        return False
    
    # 测试指标接口
    try:
        response = requests.get(f"{BASE_URL}/api/indicators")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 获取指标列表成功，共 {len(data['indicators'])} 个指标")
        else:
            print(f"❌ 获取指标失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取指标失败: {e}")
    
    # 测试市场配置接口
    try:
        response = requests.get(f"{BASE_URL}/api/markets")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 获取市场配置成功")
            print(f"   - 市场类型: {len(data['markets'])} 个")
            print(f"   - 交易对: {len(data['symbols'])} 个")
            print(f"   - 时间周期: {len(data['timeframes'])} 个")
        else:
            print(f"❌ 获取市场配置失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 获取市场配置失败: {e}")
    
    return True

def test_agent_flow():
    """测试Agent对话流程"""
    print("\n" + "=" * 60)
    print("2. 测试Agent对话流程")
    print("=" * 60)
    
    # 初始化会话
    print("\n[步骤1] 初始化会话...")
    try:
        response = requests.post(f"{BASE_URL}/api/init")
        data = response.json()
        
        if not data.get('success'):
            print(f"❌ 会话初始化失败: {data.get('error')}")
            return False
        
        session_id = data['session_id']
        print(f"✅ 会话初始化成功")
        print(f"   Session ID: {session_id}")
        print(f"   欢迎消息: {data['greeting'][:50]}...")
        
    except Exception as e:
        print(f"❌ 会话初始化失败: {e}")
        return False
    
    # 测试对话
    test_messages = [
        "我想做一个趋势跟踪策略，当价格突破30日均线时买入",
        "我想交易BTC和ETH",
        "使用1小时K线",
        "止盈5%，止损2%",
        "最大仓位30%"
    ]
    
    for i, msg in enumerate(test_messages, 1):
        print(f"\n[步骤{i+1}] 发送消息: {msg}")
        time.sleep(1)  # 避免请求过快
        
        try:
            response = requests.post(
                f"{BASE_URL}/api/chat",
                json={
                    "session_id": session_id,
                    "message": msg
                }
            )
            data = response.json()
            
            if data.get('success'):
                print(f"✅ Agent响应成功")
                print(f"   响应: {data['response'][:100]}...")
                if data.get('is_complete'):
                    print(f"   ✅ 规则信息已完整")
                else:
                    print(f"   ⚠️ 还需补充: {', '.join(data.get('missing_fields', []))}")
            else:
                print(f"❌ 对话失败: {data.get('error')}")
                
        except Exception as e:
            print(f"❌ 发送消息失败: {e}")
    
    # 获取状态
    print(f"\n[步骤7] 获取最终状态...")
    try:
        response = requests.get(f"{BASE_URL}/api/state/{session_id}")
        data = response.json()
        
        if data.get('success'):
            print("✅ 状态获取成功")
            print(f"\n{data['summary']}")
            
            if data['is_complete']:
                print("\n[步骤8] 生成最终规则...")
                response = requests.post(f"{BASE_URL}/api/finalize/{session_id}")
                result = response.json()
                
                if result.get('success'):
                    print("✅ 最终规则生成成功！")
                    print("\n最终规则配置:")
                    print(json.dumps(result['rules'], indent=2, ensure_ascii=False))
                else:
                    print(f"❌ 生成最终规则失败: {result.get('error')}")
        else:
            print(f"❌ 获取状态失败: {data.get('error')}")
            
    except Exception as e:
        print(f"❌ 获取状态失败: {e}")
    
    return True

def main():
    print("\n" + "🚀" * 30)
    print("量化规则收集 Agent - API测试")
    print("🚀" * 30 + "\n")
    
    # 测试基础接口
    if not test_health():
        print("\n❌ 基础接口测试失败，请检查服务器是否正常启动")
        return
    
    # 测试Agent流程
    test_agent_flow()
    
    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print(f"\n💡 现在可以打开浏览器访问: {BASE_URL}")
    print("   在Web界面中与Agent进行交互\n")

if __name__ == "__main__":
    main()

