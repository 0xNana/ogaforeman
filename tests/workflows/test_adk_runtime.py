from app.agents.adk_runtime import build_site_update_workflow


def test_site_update_graph_contains_native_fanout_and_join() -> None:
    async def execute() -> dict[str, str]:
        return {"status": "completed"}

    workflow = build_site_update_workflow(execute, timeout_seconds=10)

    assert workflow.graph is not None
    names = {node.name for node in workflow.graph.nodes}
    assert {
        "progress_node",
        "blocker_node",
        "material_node",
        "merge_branch_results",
        "merge_actions",
        "compose_actions",
        "evaluate_policy",
        "project_daily_log",
        "emit_activity",
    } <= names

    branch_edges = [
        edge
        for edge in workflow.graph.edges
        if edge.from_node.name == "interpret_and_route"
    ]
    assert {edge.to_node.name for edge in branch_edges} == {
        "progress_node",
        "blocker_node",
        "material_node",
    }
