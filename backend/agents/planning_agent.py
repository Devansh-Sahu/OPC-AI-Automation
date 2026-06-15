from .base_agent import BaseAgent
from backend.models import AgentRun

class PlanningAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("PlanningAgent running...")
        state["current_step"] = "planning"
        return state
