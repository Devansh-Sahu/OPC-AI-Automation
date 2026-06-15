import logging

logger = logging.getLogger(__name__)

class CostTracker:
    def __init__(self):
        # Pricing per 1M tokens (USD)
        self.PRICING = {
            "gemini-2.5-flash": {"input": 0.0, "output": 0.0}, # Free tier assumption
            "qwen3:14b": {"input": 0.0, "output": 0.0},        # Local Ollama assumption
            "default": {"input": 0.0, "output": 0.0}
        }
        
    def calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated cost in USD based on token usage."""
        model_pricing = self.PRICING.get(model, self.PRICING["default"])
        input_cost = (prompt_tokens / 1_000_000) * model_pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * model_pricing["output"]
        total_cost = input_cost + output_cost
        
        logger.debug(f"Cost calculated for {model}: ${total_cost:.6f} ({prompt_tokens} in, {completion_tokens} out)")
        return total_cost

cost_tracker = CostTracker()
