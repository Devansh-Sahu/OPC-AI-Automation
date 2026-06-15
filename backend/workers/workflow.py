import logging
from typing import TypedDict, Annotated, Sequence
import operator
from langgraph.graph import StateGraph, END
from backend.core.database import engine
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Import all agents
from backend.agents.repo_discovery_agent import RepoDiscoveryAgent
from backend.agents.issue_discovery_agent import IssueDiscoveryAgent
from backend.agents.repository_analyzer_agent import RepositoryAnalyzerAgent
from backend.agents.code_retrieval_agent import CodeRetrievalAgent
from backend.agents.planning_agent import PlanningAgent
from backend.agents.coding_agent import CodingAgent
from backend.agents.testing_agent import TestingAgent
from backend.agents.review_agent import ReviewAgent
from backend.agents.pr_agent import PRAgent

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """The central state object passed between LangGraph nodes."""
    issue_id: str
    repo_id: str
    current_step: str
    error: str | None
    
    # Context data
    repo_analysis: dict | None
    code_chunks: list[dict] | None
    
    # Generated artifacts
    engineering_plan: dict | None
    code_changes_patch: str | None
    test_results: dict | None
    review_comments: dict | None
    pr_details: dict | None
    
    # Retry/Loop counters
    test_retry_count: int
    review_retry_count: int
    
    # Human in the loop
    user_approved: bool

# Instantiate agent controllers
repo_discovery = RepoDiscoveryAgent()
issue_discovery = IssueDiscoveryAgent()
repo_analyzer = RepositoryAnalyzerAgent()
code_retriever = CodeRetrievalAgent()
planner = PlanningAgent()
coder = CodingAgent()
tester = TestingAgent()
reviewer = ReviewAgent()
pr_creator = PRAgent()

def create_issue_workflow() -> StateGraph:
    """
    Creates the main LangGraph state machine for solving a single issue.
    Workflow: Analyze -> Retrieve -> Plan -> Code -> Test -> Review -> Create PR
    """
    workflow = StateGraph(AgentState)
    
    # Define Nodes
    workflow.add_node("analyze_repo", repo_analyzer.run)
    workflow.add_node("retrieve_code", code_retriever.run)
    workflow.add_node("plan_implementation", planner.run)
    workflow.add_node("generate_code", coder.run)
    workflow.add_node("run_tests", tester.run)
    workflow.add_node("review_code", reviewer.run)
    workflow.add_node("create_pr", pr_creator.run)
    
    # Define simple edges
    workflow.add_edge("analyze_repo", "retrieve_code")
    workflow.add_edge("retrieve_code", "plan_implementation")
    workflow.add_edge("plan_implementation", "generate_code")
    workflow.add_edge("generate_code", "run_tests")
    
    # Define Conditional Edge for Testing (Self-healing loop)
    def check_test_results(state: AgentState):
        if state.get("error"):
            return "failed"
            
        tests = state.get("test_results", {})
        if tests.get("passed", False):
            return "review_code"
            
        if state.get("test_retry_count", 0) >= 3:
            logger.warning("Max test retries reached. Forcing review.")
            return "review_code"
            
        logger.info("Tests failed. Routing back to coding_agent for self-healing.")
        return "generate_code"
        
    workflow.add_conditional_edges(
        "run_tests",
        check_test_results,
        {
            "review_code": "review_code",
            "generate_code": "generate_code",
            "failed": END
        }
    )
    
    workflow.add_edge("review_code", "create_pr")
    workflow.add_edge("create_pr", END)
    
    workflow.set_entry_point("analyze_repo")
    return workflow

async def run_issue_workflow(issue_id: str, repo_id: str, thread_id: str):
    """Executes the workflow for a specific issue using durable Postgres checkpointing."""
    workflow = create_issue_workflow()
    
    # Setup durable checkpointing via Postgres
    async with AsyncPostgresSaver.from_conn_string(engine.url) as checkpointer:
        await checkpointer.setup()
        app = workflow.compile(checkpointer=checkpointer, interrupt_before=["create_pr"])
        
        initial_state = AgentState(
            issue_id=issue_id,
            repo_id=repo_id,
            current_step="pending",
            error=None,
            repo_analysis=None,
            code_chunks=None,
            engineering_plan=None,
            code_changes_patch=None,
            test_results=None,
            review_comments=None,
            pr_details=None,
            test_retry_count=0,
            review_retry_count=0,
            user_approved=False
        )
        
        config = {"configurable": {"thread_id": thread_id}}
        
        logger.info(f"Starting workflow for issue {issue_id}")
        async for event in app.astream(initial_state, config=config):
            for k, v in event.items():
                logger.info(f"Finished step: {k}")
                # We would normally publish to Redis here for WebSocket UI updates
                
        return app
