import asyncio
import time
import logging

logger = logging.getLogger(__name__)

class GitHubRateLimiter:
    def __init__(self):
        self.remaining = 5000
        self.reset_time = time.time() + 3600
        self.lock = asyncio.Lock()
        self.etag_cache = {}
        
    async def wait_if_needed(self):
        async with self.lock:
            if self.remaining <= 10:
                sleep_time = self.reset_time - time.time()
                if sleep_time > 0:
                    logger.warning(f"GitHub API rate limit critical. Sleeping for {sleep_time} seconds.")
                    await asyncio.sleep(sleep_time + 1)
                    self.remaining = 5000 # Assume reset after sleep
                    
    def update_from_headers(self, headers: dict):
        if 'X-RateLimit-Remaining' in headers:
            self.remaining = int(headers['X-RateLimit-Remaining'])
        if 'X-RateLimit-Reset' in headers:
            self.reset_time = float(headers['X-RateLimit-Reset'])
            
    def get_etag(self, url: str) -> str | None:
        return self.etag_cache.get(url, {}).get('etag')
        
    def set_etag(self, url: str, etag: str, data: dict):
        self.etag_cache[url] = {'etag': etag, 'data': data}

rate_limiter = GitHubRateLimiter()
