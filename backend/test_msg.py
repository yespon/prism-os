import asyncio

from deerflow.models.factory import create_chat_model


async def run_probe():
    llm = create_chat_model("gpt-4o")
    from app.agent.terminal_tools import terminal_tools_list
    llm_with_tools = llm.bind_tools(terminal_tools_list)
    res = await llm_with_tools.ainvoke("run top command")
    print("DICT:", res.dict())
    
if __name__ == "__main__":
    asyncio.run(run_probe())
