import logging
import json
from backend.agents.base_agent import BaseAgent

class TestingAgent(BaseAgent):
    """
    Runs the automated test suite in the Docker Sandbox to verify the code changes.
    Implements self-healing by routing back to CodingAgent on failure.
    """
    
    async def run(self, state: dict) -> dict:
        self.logger.info("TestingAgent running automated tests...")
        state["current_step"] = "testing"
        
        repo_analysis = state.get("repo_analysis", {})
        test_framework = repo_analysis.get("test_framework", "pytest") # default to pytest
        
        # Increment retry counter
        retry_count = state.get("test_retry_count", 0)
        state["test_retry_count"] = retry_count + 1
        
        self.logger.info(f"Test Execution Attempt: {state['test_retry_count']} of 3")
        
        # In a real implementation:
        # 1. Spin up the sandbox container
        # 2. Run the specific test framework command (e.g., `pytest --json-report`)
        # 3. Parse the output JSON to determine pass/fail
        
        # MOCK IMPLEMENTATION FOR DEMONSTRATION
        # We simulate a 70% pass rate on the first try, 90% on subsequent tries
        import random
        pass_rate = 0.7 if state["test_retry_count"] == 1 else 0.9
        tests_passed = random.random() < pass_rate
        
        if tests_passed:
            self.logger.info("All tests passed successfully.")
            state["test_results"] = {
                "passed": True,
                "total_tests": 45,
                "failed_tests": 0,
                "coverage": 87.5,
                "logs": "============================= test session starts ==============================\n... 45 passed in 2.1s"
            }
        else:
            self.logger.warning("Tests failed. Preparing error logs for self-healing.")
            state["test_results"] = {
                "passed": False,
                "total_tests": 45,
                "failed_tests": 2,
                "coverage": 86.0,
                "logs": "FAILED tests/test_core.py::test_edge_case - AssertionError: Expected True, got False"
            }
            # The LangGraph edge logic in workflow.py will route this back to CodingAgent
            
        return state
