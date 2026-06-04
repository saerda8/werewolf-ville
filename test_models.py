"""
测试所有绑定的模型是否正常工作
"""
import sys
sys.path.insert(0, 'G:/Trae-Project/werewolf-ville')

from llm import get_model_for_agent, chat_for_agent

# 测试的角色列表（4个NPC）
agents = [
    "Arthur Burton",      # GLM-5
    "Isabella Rodriguez", # Kimi-K2.5
    "Maria Lopez",        # mimo-v2-flash-studio
    "Sam Moore",          # deepseek-v4-flash
]

print("=" * 60)
print("模型连通性测试")
print("=" * 60)

for agent_name in agents:
    model = get_model_for_agent(agent_name)
    print(f"\n[{agent_name}] -> 模型: {model}")
    print("-" * 50)
    
    try:
        response = chat_for_agent(
            agent_name,
            "你是一个小镇居民。",
            "请用一句话介绍自己。"
        )
        if response:
            print(f"✓ 成功: {response[:100]}..." if len(response) > 100 else f"✓ 成功: {response}")
        else:
            print("✗ 失败: 返回空响应")
    except Exception as e:
        print(f"✗ 失败: {e}")

print("\n" + "=" * 60)
print("测试完成")
print("=" * 60)