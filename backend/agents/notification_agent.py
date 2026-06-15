from .base_agent import BaseAgent
from backend.models import AgentRun

class NotificationAgent(BaseAgent):
    async def run(self, state: dict) -> dict:
        self.logger.info("NotificationAgent running...")
        state["current_step"] = "notifying"
        return state
