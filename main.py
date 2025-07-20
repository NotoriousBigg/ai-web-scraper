import asyncio
import json
import uuid
from asyncio import Semaphore

import google.generativeai as genai
from aioredis import Redis
from bs4 import BeautifulSoup
from cachetools import TTLCache
from google.generativeai import ChatSession
from httpx import AsyncClient
from loguru import logger
from config import GEMINI_API_KEY, REDIS_URI
# Add these at the global level
MAX_CONCURRENT_REQUESTS = 10
request_semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)
cache = TTLCache(maxsize=100, ttl=3600)  # Cache results for 1 hour
rate_limit_delay = 1.0  # Seconds between requests

class RedisManager:
    def __init__(self, redis_url, max_retries=3):
        self.redis_url = redis_url
        self.max_retries = max_retries
        self.client = None
        
    async def get_client(self):
        if not self.client:
            self.client = Redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        return self.client
        
    async def set_with_retry(self, key, value, ex=None):
        for attempt in range(self.max_retries):
            try:
                client = await self.get_client()
                await client.set(key, value, ex=ex)
                return True
            except Exception as e:
                logger.error(f"Redis set error (attempt {attempt + 1}): {e}")
                await asyncio.sleep(1)
        return False

redis_manager = RedisManager(redis_url=REDIS_URI)
RClient = Redis.from_url(REDIS_URI)
genai.configure(api_key=GEMINI_API_KEY)

gemini = genai.GenerativeModel(
    model_name="gemini-1.5-flash-002",
    system_instruction="""
You're an expert in writing Python scraping scripts using BeautifulSoup. 
Given a webpage's HTML, generate Python code to extract specified data from it.
You should stick to the provided html code to you. You not start providing other examples that are not in the code. Make your work perfect.
You are supposed to only return the python code. Remember, Those asking for help know nothing about python. So, your response should be ready to :
1. Get executed and print or save the data as the user requests.
2. Have no errors(Since they can't debug)
3. Your code should have comments in it, for helping junior devs.
    """
)


async def get_web_contents(url: str):
    """Enhanced web content fetching with rate limiting, caching, and retries"""
    cache_key = f"content:{url}"
    if url in cache:
        return cache[url]

    async with request_semaphore:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
            }

            async with AsyncClient(
                    timeout=30,
                    follow_redirects=True,
                    headers=headers,
                    verify=False
            ) as client:
                await asyncio.sleep(rate_limit_delay)
                response = await client.get(url)
                response.raise_for_status()

                content = response.content
                cache[url] = content
                return content

        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

async def get_user_chat(user_id: int) -> ChatSession:
    """Get or create chat session for user"""
    chat_data = await RClient.get(f"chat:{user_id}")

    if chat_data:
        history = json.loads(chat_data)
        return gemini.start_chat(history=history)

    return gemini.start_chat()

async def update_user_history(user_id: int, query: str, response_text: str):
    """Save user interaction to Redis"""
    try:
        history = [
            {"role": "user", "parts": [query]},
            {"role": "model", "parts": [response_text]}
        ]
        current_data = await RClient.get(f"chat:{user_id}")
        current_history = json.loads(current_data) if current_data else []

        updated_history = current_history + history
        if len(updated_history) > 100:
            updated_history = updated_history[-100:]

        await RClient.set(f"chat:{user_id}", json.dumps(updated_history), ex=86400 * 7)
    except Exception as e:
        logger.error(f"Failed to save chat history: {e}")


async def optimus_reply(user_id, message):
    try:
        chat = await get_user_chat(user_id)
        response = chat.send_message(message)
        if isinstance(response, str):
            return response.strip()
        if hasattr(response, 'text'):
            return response.text.strip()
        if hasattr(response, '__await__'):
            result =  response
            return result.text.strip() if hasattr(result, 'text') else str(result).strip()
        return str(response).strip()

    except Exception as e:
        logger.error(f"Gemini error for user {user_id}: {e}")
        return "❌ I ran into an error processing that."


async def parse_html_with_ai(user_id, html_content: bytes, user_prompt: str):
    """Enhanced HTML parsing with chunking and optimization"""
    try:
        soup = BeautifulSoup(html_content, "lxml")
        for script in soup(["script", "style", "meta", "link"]):
            script.decompose()
        max_chunk_size = 30000
        simplified_html = soup.prettify()

        chat = await get_user_chat(user_id)

        if len(simplified_html) > max_chunk_size:
            chunks = [simplified_html[i:i + max_chunk_size]
                      for i in range(0, len(simplified_html), max_chunk_size)]
            results = []

            for chunk in chunks:
                chunk_prompt = f"""
User request:
{user_prompt}

HTML Part {chunks.index(chunk) + 1}/{len(chunks)}:
{chunk}
                """
                try:
                    response = await optimus_reply(user_id, chunk_prompt)
                    results.append(response)
                except Exception as e:
                    logger.error(f"Error processing chunk: {e}")
                    continue

            final_result = "\n".join(results)
        else:
            prompt = f"""
            User request:
            {user_prompt}

            Here is the HTML:
            {simplified_html}
            """
            final_result = await optimus_reply(user_id, prompt)

        await update_user_history(user_id, user_prompt, final_result)
        return final_result

    except asyncio.TimeoutError:
        logger.error(f"Timeout for user {user_id} while processing HTML")
        return "⚠️ Request timed out. Please try with a smaller HTML section."
    except Exception as e:
        logger.error(f"AI failed for user {user_id}: {e}", exc_info=True)
        return "⚠️ I ran into an error. Try rephrasing your question."


def gen_session_id():
    return uuid.uuid4()


async def main():
    urls = ["https://subsplease.org/rss/?r=720"]
    user_id = gen_session_id()

    tasks = []
    for url in urls:
        tasks.append(asyncio.create_task(get_web_contents(url)))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for url, html in zip(urls, results):
        if isinstance(html, Exception):
            logger.error(f"Failed to fetch {url}: {html}")
            continue

        if html:
            try:
                code = await parse_html_with_ai(
                    user_id=user_id,
                    html_content=html,
                    user_prompt="Extract all the necessary data including title, quality, magnet link, date and size"
                )
                print(f"Results for {url}:")
                print(code)
            except Exception as e:
                logger.error(f"Failed to process {url}: {e}")
        else:
            logger.error(f"Failed to fetch content from {url}")


if __name__ == "__main__":
    asyncio.run(main())