from langgraph.graph import StateGraph
from typing import TypedDict, Any

class WorkflowState(TypedDict):
    current_step: str
    data: dict[str, Any]

def build_workflow():
    graph = StateGraph(WorkflowState)
    return graph
