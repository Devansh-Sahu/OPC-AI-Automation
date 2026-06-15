from .base_agent import BaseAgent
from backend.models import AgentRun

class CodingAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("CodingAgent running...")
        state["current_step"] = "coding"
        return state
