"""Minimal CLI showcasing memblocks library usage."""

import asyncio
from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings


async def main():
    config = MemBlocksConfig(
        llm_settings=LLMSettings(
            default=LLMTaskSettings(provider="groq", model="openai/gpt-oss-20b"),
            retrieval=LLMTaskSettings(provider="groq", model="openai/gpt-oss-20b"),
        )
    )

    client = MemBlocksClient(config)

    user_id = input("Enter user ID: ").strip() or "default_user"
    user = await client.get_or_create_user(user_id)

    block_name = input("Block name: ").strip() or "My Memory"
    block = await client.create_block(user_id=user_id, name=block_name)

    session = await client.create_session(user_id=user_id, block_id=block.id)

    print("\nChat started. Type 'quit' to exit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break

        context = await block.retrieve(user_input)
        memory_window = await session.get_memory_window()

        system_parts = ["You are a helpful assistant."]
        summary = await session.get_recursive_summary()
        if summary:
            system_parts.append(f"<Summary>\n{summary}\n</Summary>")
        memory_str = context.to_prompt_string()
        if memory_str:
            system_parts.append(memory_str)

        system_prompt = "\n\n".join(system_parts)
        messages = (
            [{"role": "system", "content": system_prompt}]
            + memory_window
            + [{"role": "user", "content": user_input}]
        )

        response = await client.conversation_llm.chat(messages=messages)
        print(f"Assistant: {response}\n")

        await session.add(user_msg=user_input, ai_response=response)

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())