from .base_agent import BaseAgent
from backend.models import AgentRun

class TestingAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("TestingAgent running...")
        state["current_step"] = "testing"
        return state
