import json
import logging
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional
from services.llm_client import llm_client
from config.prompts import SYSTEM_PROMPT, TOOL_CALL_SYSTEM_PROMPT
from config.allowed_actions import ALLOWED_ACTIONS
from core.tool_dispatcher import tool_dispatcher

logger = logging.getLogger(__name__)

class AnalyzerState(TypedDict):
    logs: str
    node_id: str
    agent_url: str
    iterations: int
    messages: List[Dict[str, str]]
    final_report: Optional[str]
    severity: Optional[str]
    tokens_used: int

def initialize_analysis(state: AnalyzerState) -> AnalyzerState:
    logger.info(f"[Analyzer] Initializing analysis for node: {state['node_id']}")
    system_message = {"role": "system", "content": SYSTEM_PROMPT.format(logs=state["logs"])}
    state["messages"] = [system_message]
    state["iterations"] = 0
    state["tokens_used"] = 0
    return state

async def analyze_logs(state: AnalyzerState) -> AnalyzerState:
    tools = [
        {
            "type": "function",
            "function": {
                "name": action,
                "description": f"Execute {action} on the node",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": True}
            }
        } for action in ALLOWED_ACTIONS
    ]
    
    logger.info(f"[Analyzer] Calling LLM to analyze logs (node: {state['node_id']}, iteration: {state['iterations'] + 1})")
    response = await llm_client.chat_completion(state["messages"], tools=tools)
    
    if response:
        usage = response.get("usage", {})
        state["tokens_used"] = state.get("tokens_used", 0) + usage.get("total_tokens", 0)
        
    if response and "choices" in response and len(response["choices"]) > 0:
        message = response["choices"][0]["message"]
        state["messages"].append(message)
        
        if message.get("tool_calls"):
            tool_names = [tc["function"]["name"] for tc in message["tool_calls"]]
            logger.info(f"[Analyzer] LLM requested tool execution: {tool_names}")
        else:
            content = message.get("content", "")
            state["final_report"] = content
            
            severity = "WARNING" 
            for line in content.split("\n"):
                if line.startswith("SEVERITY:"):
                    sev_str = line.split(":", 1)[1].strip().upper()
                    if sev_str in ["INFO", "WARNING", "ERROR", "CRITICAL"]:
                        severity = sev_str
                    break
            state["severity"] = severity 
            logger.info(f"[Analyzer] LLM analysis completed. Severity: {severity}. Tokens used so far: {state['tokens_used']}")
            
    state["iterations"] += 1
    return state

async def execute_tools(state: AnalyzerState) -> AnalyzerState:
    last_message = state["messages"][-1]
    tool_calls = last_message.get("tool_calls", [])
    
    for tool_call in tool_calls:
        func = tool_call["function"]
        action = func["name"]
        params = json.loads(func.get("arguments", "{}"))
        
        logger.info(f"[Analyzer] Dispatching tool '{action}' on node '{state['node_id']}' with parameters: {params}")
        try:
            result = await tool_dispatcher.dispatch(state["node_id"], state["agent_url"], action, params)
            tool_res = json.dumps(result.get("result", {}))
            logger.info(f"[Analyzer] Tool '{action}' completed with status: {result.get('status', 'success')}")
        except Exception as e:
            logger.error(f"[Analyzer] Tool '{action}' failed: {e}", exc_info=True)
            tool_res = str(e)
            
        state["messages"].append({
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "name": action,
            "content": tool_res
        })
        
    return state

def route_next_step(state: AnalyzerState) -> str:
    if state["iterations"] >= 3:
        return END
        
    last_message = state["messages"][-1]
    if last_message.get("tool_calls"):
        return "execute"
        
    return END

graph = StateGraph(AnalyzerState)
graph.add_node("init", initialize_analysis)
graph.add_node("analyze", analyze_logs)
graph.add_node("execute", execute_tools)

graph.set_entry_point("init")
graph.add_edge("init", "analyze")
graph.add_conditional_edges("analyze", route_next_step)
graph.add_edge("execute", "analyze")

analyzer = graph.compile()
