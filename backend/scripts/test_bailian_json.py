from app.llm.bailian_client import bailian_chat_client


if __name__ == "__main__":
    result = bailian_chat_client.chat_json(
        system_prompt="你是一个 JSON 测试助手，只输出 JSON。",
        user_prompt='输出 {"ok": true, "message": "百炼模型连接成功"}',
        temperature=0.1,
    )
    print(result)
