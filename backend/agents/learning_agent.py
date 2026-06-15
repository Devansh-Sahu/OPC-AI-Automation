from .base_agent import BaseAgent
from backend.models import AgentRun

class LearningAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("LearningAgent running...")
        state["current_step"] = "learning"
        return state
