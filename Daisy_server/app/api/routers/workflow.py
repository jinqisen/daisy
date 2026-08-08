from fastapi import APIRouter
from app.workflow.graph import app_graph

router = APIRouter()

@router.get("")
async def get_workflow_graph():
    """
    获取 LangGraph 结构用于前端可视化。
    """
    graph = app_graph.get_graph()
    nodes = []
    edges = []
    
    # 定义节点元数据映射
    NODE_METADATA = {
        "analyze": {"label": "Emotion Analysis", "is_llm": False, "icon": "scan"},
        "analyze_communication_style": {"label": "Comm. Style (Psych Expert)", "is_llm": True, "icon": "bulb"},
        "retrieve": {"label": "Retrieve Memory", "is_llm": False, "icon": "database"},
        "summarize_topic": {"label": "Summarize Topic", "is_llm": True, "icon": "history"},
        "ensure_portrait": {"label": "Ensure Portrait", "is_llm": True, "icon": "user"},
        "analyze_style": {"label": "Style Analysis", "is_llm": False, "icon": "bulb"},
        "agent_thoughts": {"label": "Agent Thoughts (RL/LLM)", "is_llm": True, "icon": "robot"},
        "generate": {"label": "Generate Response", "is_llm": True, "icon": "edit"},
        "save": {"label": "Save & Learn", "is_llm": False, "icon": "save"},
        "fast_generate": {"label": "Fast Generate", "is_llm": True, "icon": "thunderbolt"},
        "standard_generate": {"label": "Standard Generate", "is_llm": True, "icon": "message"},
        "tool_check": {"label": "Tool Check", "is_llm": True, "icon": "tool"},
        "__start__": {"label": "Start", "is_llm": False, "icon": "start"},
        "__end__": {"label": "End", "is_llm": False, "icon": "end"}
    }

    for node_id in graph.nodes:
        node_type = "default"
        if node_id == "__start__":
            node_type = "input"
        elif node_id == "__end__":
            node_type = "output"
            
        metadata = NODE_METADATA.get(node_id, {"label": node_id.replace("_", " ").title(), "is_llm": False})
        
        nodes.append({
            "id": node_id,
            "data": {
                "label": metadata["label"],
                "is_llm": metadata["is_llm"],
                "icon": metadata.get("icon")
            },
            "type": node_type
        })
        
    for edge in graph.edges:
        edges.append({
            "id": f"{edge.source}-{edge.target}",
            "source": edge.source,
            "target": edge.target,
            "animated": True
        })
        
    return {"nodes": nodes, "edges": edges}
