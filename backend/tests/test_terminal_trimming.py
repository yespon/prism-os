from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.terminal_graph import _trim_message_history


def test_trim_empty_messages():
    assert _trim_message_history([]) == []

def test_trim_short_messages():
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="hello"),
        AIMessage(content="hi there")
    ]
    trimmed = _trim_message_history(messages)
    assert len(trimmed) == 3
    assert trimmed == messages

def test_trim_long_messages_overflow():
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="hello this is a long message to exceed the small token limit of 10"),
        AIMessage(content="response from ai that is also long"),
        HumanMessage(content="second human message")
    ]
    # If max_tokens is 5, only the "second human message" block (~3 tokens) is kept
    trimmed = _trim_message_history(messages, max_tokens=5)
    
    # SystemMessage at position 0 must be kept
    assert isinstance(trimmed[0], SystemMessage)
    # The last block (second human message) must be kept
    assert trimmed[-1].content == "second human message"
    # The intermediate human and ai messages should be trimmed
    assert len(trimmed) == 2

def test_trim_keep_tool_calls_together():
    messages = [
        SystemMessage(content="system prompt"),
        HumanMessage(content="first human message"),
        AIMessage(content="run cmd", tool_calls=[{"name": "execute_command", "args": {"command": "df -h"}, "id": "call_1"}]),
        ToolMessage(content="disk space output", tool_call_id="call_1"),
        AIMessage(content="summary of disk space"),
        HumanMessage(content="second human message")
    ]
    
    # We set a limit that cuts off in the middle of the tool call block
    # Blocks:
    # 1. [Human1] (tokens ~15)
    # 2. [AI_tool, Tool_msg] (tokens ~24)
    # 3. [AI_summary] (tokens ~4)
    # 4. [Human2] (tokens ~3)
    
    # max_tokens=15 fits blocks 4 and 3 (~7 tokens), but block 2 would push it to ~31.
    trimmed = _trim_message_history(messages, max_tokens=15)
    assert isinstance(trimmed[0], SystemMessage)
    assert len(trimmed) == 3
    assert trimmed[1].content == "summary of disk space"
    assert trimmed[2].content == "second human message"

    # max_tokens=48 fits blocks 4, 3, and 2 (~47 tokens), but block 1 (~50 tokens total) will exceed it.
    trimmed_fit_tool = _trim_message_history(messages, max_tokens=48)
    assert isinstance(trimmed_fit_tool[0], SystemMessage)
    assert len(trimmed_fit_tool) == 5
    assert trimmed_fit_tool[1].content == "run cmd"
    assert isinstance(trimmed_fit_tool[2], ToolMessage)
    assert trimmed_fit_tool[3].content == "summary of disk space"
    assert trimmed_fit_tool[4].content == "second human message"
