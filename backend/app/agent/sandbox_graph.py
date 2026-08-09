import logging
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from deerflow.models.factory import create_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class SandboxState(TypedDict):
    session_id: str
    tenant_id: str
    user_id: str
    model_name: str
    mode: Literal["sandbox"]
    messages: Annotated[list[AnyMessage], add_messages]
    skill_instructions: str

# ---------------------------------------------------------------------------
# Mock Tools
# ---------------------------------------------------------------------------

@tool
async def execute_command(command: str, host_index: int = -1) -> str:
    """Execute a shell command. In Sandbox mode, this is simulated."""
    logger.info(f"[Sandbox] Mocking execute_command: {command}")
    return f"[Sandbox Mock] Successfully executed command:\n$ {command}\n\n(Simulated output: command executed successfully in sandbox environment.)"

@tool
async def read_file(path: str, max_lines: int = 200, host_index: int = -1) -> str:
    """Read the contents of a file."""
    return f"[Sandbox Mock] Successfully read file: {path} (max_lines={max_lines})\n(Simulated output: file contents...)"

@tool
async def write_file(path: str, content: str, host_index: int = -1) -> str:
    """Write contents to a file."""
    return f"[Sandbox Mock] Successfully wrote to file: {path}"

@tool
async def grep_search(pattern: str, path: str = ".", max_results: int = 50, max_size_mb: int = 10, host_index: int = -1) -> str:
    """Search for a pattern in files using grep."""
    return f"[Sandbox Mock] Successfully searched for {pattern} in {path}"

sandbox_tools = [execute_command, read_file, write_file, grep_search]

# ---------------------------------------------------------------------------
# Graph Nodes
# ---------------------------------------------------------------------------

async def intent_node(state: SandboxState) -> dict:
    """The main conversational node. Infuses skill instructions."""
    model_name = state.get("model_name") or "gpt-4o"
    llm = create_chat_model(name=model_name)
    llm_with_tools = llm.bind_tools(sandbox_tools)

    sys_prompt = "You are a helpful AI Agent operating in a Sandbox Environment."
    
    instructions = state.get("skill_instructions")
    if instructions:
        sys_prompt += f"\n\nYou are currently executing the following SKILL INSTRUCTIONS:\n{instructions}\n\nStrictly follow these instructions."
        
    sys_prompt += "\n\nNote: You are in a Sandbox. Any terminal commands you execute will be safely mocked and simulated."

    messages = [SystemMessage(content=sys_prompt)] + state["messages"]
    response = await llm_with_tools.ainvoke(messages)
    
    return {"messages": [response]}
        
execute_node = ToolNode(sandbox_tools)

# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------

def _route_after_intent(state: SandboxState) -> str:
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls: # type: ignore
        return "execute"
    return END

# ---------------------------------------------------------------------------
# Graph Builder
# ---------------------------------------------------------------------------

def build_sandbox_graph() -> StateGraph:
    workflow = StateGraph(SandboxState)
    
    workflow.add_node("intent", intent_node)
    workflow.add_node("execute", execute_node)
    
    workflow.add_edge(START, "intent")
    workflow.add_conditional_edges("intent", _route_after_intent)
    workflow.add_edge("execute", "intent")
    
    return workflow

memory = MemorySaver()
sandbox_graph = build_sandbox_graph().compile(checkpointer=memory)
