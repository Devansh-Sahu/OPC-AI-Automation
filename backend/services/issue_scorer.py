import logging
from backend.models.issue import Issue

logger = logging.getLogger(__name__)

class IssueScorer:
    
    # Labels that indicate a beginner issue (we skip these)
    JUNIOR_LABELS = {
        "good first issue", "beginner", "help wanted", "easy", 
        "documentation", "docs", "typo", "minor", "trivial"
    }
    
    # Labels that indicate complex technical issues
    SENIOR_LABELS = {
        "performance", "memory leak", "race condition", "concurrency",
        "security", "vulnerability", "regression", "critical",
        "architecture", "refactoring", "technical debt"
    }
    
    def classify_complexity_tier(self, labels: list[str], title: str, body: str) -> str:
        """Classify issue into JUNIOR, SENIOR, STAFF, INNOVATION, or SKIP."""
        labels_lower = [l.lower() for l in (labels or [])]
        title_lower = title.lower() if title else ""
        body_lower = body.lower() if body else ""
        
        # 1. Filter out beginner issues
        if any(jl in labels_lower for jl in self.JUNIOR_LABELS):
            return "SKIP"
            
        if "good first issue" in title_lower or "typo" in title_lower:
            return "SKIP"

        # 2. Check for INNOVATION / RFC
        if "rfc" in title_lower or "design doc" in title_lower or "proposal" in title_lower:
            return "INNOVATION"
            
        # 3. Check for STAFF level (distributed systems, consensus, major security)
        staff_keywords = ["distributed", "consensus", "cve", "split brain", "data loss", "corruption"]
        if any(kw in title_lower or kw in body_lower for kw in staff_keywords):
            return "STAFF"
            
        # 4. Check for SENIOR level
        if any(sl in labels_lower for sl in self.SENIOR_LABELS):
            return "SENIOR"
            
        senior_keywords = ["race condition", "deadlock", "memory leak", "oom", "segfault", "bottleneck"]
        if any(kw in title_lower or kw in body_lower for kw in senior_keywords):
            return "SENIOR"
            
        # Default fallback for unlabelled but long issues might be SENIOR, else SKIP
        if len(body_lower) > 1000 and "stack trace" in body_lower:
            return "SENIOR"
            
        return "SKIP"

    def score_issue(self, issue: dict, repo_score: float) -> dict:
        """Calculate numerical scores for the issue."""
        body_length = len(issue.get("body") or "")
        labels = issue.get("labels") or []
        
        difficulty = 5.0
        if "stack trace" in (issue.get("body") or "").lower():
            difficulty += 2.0
        if len(labels) > 3:
            difficulty += 1.0
            
        difficulty = min(10.0, max(1.0, difficulty))
        
        merge_prob = 50.0  # Default base probability
        if "regression" in labels:
            merge_prob += 20.0 # Regressions are usually highly desired fixes
            
        merge_prob = min(100.0, max(0.0, merge_prob))
        
        engagement = min(100.0, (body_length / 2000.0) * 100)
        
        composite = (difficulty * 4) + (merge_prob * 0.4) + (repo_score * 0.2)
        
        return {
            "difficulty_score": round(difficulty, 2),
            "merge_probability": round(merge_prob, 2),
            "engagement_score": round(engagement, 2),
            "composite_score": round(composite, 2)
        }

issue_scorer = IssueScorer()
