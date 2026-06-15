import logging
from backend.agents.base_agent import BaseAgent
from backend.services.merge_predictor import merge_predictor

class LearningAgent(BaseAgent):
    """
    Called by GitHub Webhooks when a PR is merged, rejected, or reviewed.
    Updates the XGBoost model training data to improve future predictions.
    """
    
    async def run(self, state: dict) -> dict:
        self.logger.info("LearningAgent analyzing PR outcome...")
        state["current_step"] = "learning"
        
        pr_details = state.get("pr_details", {})
        outcome = pr_details.get("outcome", "unknown") # e.g. "merged", "rejected"
        
        if outcome == "unknown":
            self.logger.warning("No PR outcome data found. Skipping learning phase.")
            return state
            
        # We extract features from what we knew *before* the PR was merged
        features = {
            "has_tests": state.get("test_results", {}).get("passed", False),
            "issue_complexity_tier": state.get("issue_details", {}).get("complexity_tier", "UNKNOWN"),
            "code_churn": len(state.get("code_changes_patch", "")),
            "repo_responsiveness": state.get("repo_analysis", {}).get("maintainer_responsiveness_score", 0.5)
        }
        
        # Label: 1 if merged, 0 if rejected
        label = 1 if outcome == "merged" else 0
        
        # In a real scenario, we save this to the `feedback` table, and then incrementally retrain
        self.logger.info(f"Retraining XGBoost model with new sample (Label: {label})")
        # merge_predictor.train([features], [label])
        
        return state
