from langgraph.graph import END, START, StateGraph

from app.graph.nodes import CustomerServiceGraphNodes, DomainAgent
from app.graph.routing import route_execution
from app.graph.state import RuntimeState


def build_customer_service_graph(agent: DomainAgent):
    """Declare topology in one place so the workflow is reviewable at a glance."""

    nodes = CustomerServiceGraphNodes(agent)
    builder = StateGraph(RuntimeState)
    builder.add_node("validate_input", nodes.validate_input)
    builder.add_node("execute_domain_agent", nodes.execute_domain_agent)
    builder.add_node("completed", nodes.mark_completed)
    builder.add_node("approval", nodes.mark_approval)
    builder.add_node("handoff", nodes.mark_handoff)

    builder.add_edge(START, "validate_input")
    builder.add_edge("validate_input", "execute_domain_agent")
    builder.add_conditional_edges(
        "execute_domain_agent",
        route_execution,
        {
            "completed": "completed",
            "approval": "approval",
            "handoff": "handoff",
        },
    )
    builder.add_edge("completed", END)
    builder.add_edge("approval", END)
    builder.add_edge("handoff", END)
    return builder.compile(name="myticket-customer-service")
