"""
测试指定模型的连通性 - 输出到文件
"""
import sys
sys.path.insert(0, 'G:/Trae-Project/werewolf-ville')

from llm import _client, _REQUEST_TIMEOUT

# 要测试的模型列表
models = [
    "MiniMax-M2.5",
    "MiniMax-M2.7",
    "Qwen3-Flash",
    "glm-4.5-air",
]

results = []
results.append("=" * 60)
results.append("模型连通性测试")
results.append("=" * 60)

for model in models:
    results.append(f"\n[测试模型] {model}")
    results.append("-" * 50)
    
    try:
        response = _client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "你是一个AI助手。"},
                {"role": "user", "content": "请用一句话介绍自己。"}
            ],
            max_tokens=50,
            temperature=0.7,
            timeout=_REQUEST_TIMEOUT
        )
        if response and response.choices:
            text = response.choices[0].message.content.strip()
            results.append(f"✓ 成功: {text[:100]}..." if len(text) > 100 else f"✓ 成功: {text}")
        else:
            results.append("✗ 失败: 返回空响应")
    except Exception as e:
        results.append(f"✗ 失败: {str(e)}")

results.append("\n" + "=" * 60)
results.append("测试完成")
results.append("=" * 60)

# 写入文件
with open("model_test_results.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(results))

print("测试完成，结果已保存到 model_test_results.txt")