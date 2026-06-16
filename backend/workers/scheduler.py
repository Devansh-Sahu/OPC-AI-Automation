import asyncio
import logging
from backend.core.config import settings
from backend.core.database import AsyncSessionLocal
from backend.agents.repo_discovery_agent import RepoDiscoveryAgent
from backend.agents.issue_discovery_agent import IssueDiscoveryAgent

logger = logging.getLogger(__name__)

async def run_discovery_loop():
    logger.info("Starting autonomous discovery loop...")
    
    while True:
        try:
            async with AsyncSessionLocal() as db:
                # 1. Discover new repositories
                repo_agent = RepoDiscoveryAgent()
                logger.info("Running Repo Discovery...")
                await repo_agent.run()
                
                # 2. Discover new issues in tracked repositories
                issue_agent = IssueDiscoveryAgent()
                logger.info("Running Issue Discovery...")
                await issue_agent.run()
                
        except Exception as e:
            logger.error(f"Error in discovery loop: {e}")
            
        # Sleep until the next interval
        sleep_time = settings.ISSUE_DISCOVERY_INTERVAL_HOURS * 3600
        logger.info(f"Discovery complete. Sleeping for {sleep_time} seconds...")
        await asyncio.sleep(sleep_time)

async def start_scheduler():
    await run_discovery_loop()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(start_scheduler())
