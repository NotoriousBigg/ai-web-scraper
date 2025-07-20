import asyncio
import json
import uuid
from asyncio import Semaphore

import google.generativeai as genai
from aioredis import Redis
from bs4 import BeautifulSoup
from googlesearch import is_bs4
from playwright.async_api import async_playwright
from cachetools import TTLCache
from google.generativeai import ChatSession
from httpx import AsyncClient
from loguru import logger
from typing import Optional, Tuple
from config import GEMINI_API_KEY, REDIS_URI

MAX_CONCURRENT_REQUESTS = 10
request_semaphore = Semaphore(MAX_CONCURRENT_REQUESTS)
cache = TTLCache(maxsize=100, ttl=3600)  # Cache results for 1 hour
rate_limit_delay = 1.0  # Seconds between requests
ACCEPTED_STATUS_CODES = {200, 201, 202}

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
You're an expert in writing Python scraping scripts using BeautifulSoup and Playwright. 
Given a webpage's HTML, generate Python code to extract specified data from it.
The html passed is from a url. So In your example, you should include the url.
You should stick to the provided html code to you. You not start providing other examples that are not in the code. Make your work perfect.
You are supposed to only return the python code. Remember, Those asking for help know nothing about python. So, your response should be ready to :
1. Get executed and print or save the data as the user requests.
2. Have no errors(Since they can't debug)
3. Your code should have comments in it, for helping junior devs.
    """
)


async def get_with_playwright(url: str) -> Optional[str]:
    """Fetch web content using Playwright with enhanced waiting strategies"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--disable-dev-shm-usage']  # Helps with memory issues
            )

            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                java_script_enabled=True,
            )

            # Add stealth mode scripts
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

            page = await context.new_page()

            # Set common headers
            await page.set_extra_http_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            })

            try:
                # Navigate with timeout and wait until network is idle
                await page.goto(url,
                                wait_until='networkidle',
                                timeout=30000)  # 30 seconds timeout

                # Wait for important states
                await page.wait_for_load_state('domcontentloaded')
                await page.wait_for_load_state('load')

                # Additional waits for dynamic content
                await asyncio.sleep(2)

                # Wait for any AJAX requests to complete
                await page.wait_for_load_state('networkidle', timeout=5000)

                # Try to ensure dynamic content is loaded by scrolling
                await page.evaluate("""
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'smooth'
                    });
                """)

                await asyncio.sleep(1)
                try:
                    await page.wait_for_selector('.content-loaded', timeout=5000)
                except:
                    pass
                content = await page.content()
                if len(content) < 1000:
                    logger.warning(f"Content seems too short for {url}, might not be fully loaded")

                return content

            except TimeoutError:
                logger.error(f"Timeout while loading {url}")
                return await page.content()

            finally:
                await browser.close()

    except Exception as e:
        logger.error(f"Playwright error for {url}: {e}")
        return None


async def get_web_contents(url: str) -> Tuple[Optional[str], bool]:
    """
    Enhanced web content fetching with fallback to Playwright.
    Returns tuple of (content, is_javascript_rendered)
    """
    cache_key = f"content:{url}"
    if url in cache:
        return cache[url], False

    async with request_semaphore:
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }

            async with AsyncClient(
                    timeout=30,
                    follow_redirects=True,
                    headers=headers,
                    verify=False
            ) as client:
                await asyncio.sleep(rate_limit_delay)
                response = await client.get(url)

                if response.status_code in ACCEPTED_STATUS_CODES:
                    content = response.content
                    cache[url] = content
                    return content, False

                # If status code indicates need for JavaScript rendering
                if response.status_code in {403, 401, 503} or response.status_code >= 500:
                    logger.info(f"Switching to Playwright for {url} (Status: {response.status_code})")
                    content = await get_with_playwright(url)
                    if content:
                        cache[url] = content
                        return content, True

                response.raise_for_status()

        except Exception as e:
            logger.warning(f"Regular request failed for {url}: {e}. Trying Playwright...")
            content = await get_with_playwright(url)
            if content:
                cache[url] = content
                return content, True

        return None, False


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


async def parse_html_with_ai(user_id, url, html_content, user_prompt, is_js_rendered):
    """Enhanced HTML parsing with chunking and optimization"""
    try:
        soup = BeautifulSoup(html_content, "lxml")
        for script in soup(["script", "style", "meta", "link"]):
            script.decompose()
        max_chunk_size = 30000
        simplified_html = soup.prettify()

        js_context = "\nNote: This content was rendered using Playwright with JavaScript enabled." if is_js_rendered else ""

        chat = await get_user_chat(user_id)

        if len(simplified_html) > max_chunk_size:
            chunks = [simplified_html[i:i + max_chunk_size]
                      for i in range(0, len(simplified_html), max_chunk_size)]
            results = []

            for chunk in chunks:
                chunk_prompt = f"""
From URL: {url}
User request:
{user_prompt}

HTML Part {chunks.index(chunk) + 1}/{len(chunks)}:
{chunk}
{js_context}
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
From url: {url}
User request:
{user_prompt}

Here is the HTML:
{simplified_html}.

{js_context}
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


# async def main():
#     urls = ["https://tv.kresswell.me/tv"]
#     user_id = gen_session_id()
#
#     for url in urls:
#         try:
#             content, is_js_rendered = await get_web_contents(url)
#             if content:
#                 code = await parse_html_with_ai(
#                     user_id=user_id,
#                     url=url,
#                     html_content=content,
#                     user_prompt="Extract all the necessary tv data from this page.Display them in a table in the terminal",
#                     is_js_rendered=is_js_rendered
#                 )
#                 print(f"Results for {url}:")
#                 print(code)
#             else:
#                 logger.error(f"Failed to fetch content from {url}")
#
#         except Exception as e:
#             logger.error(f"Failed to process {url}: {e}")

async def cli_main():
    """Command-line interface for the web scraper"""
    print("\n=== Web Scraper CLI ===\n")
    url = str(input("[+] Enter the url you want to scrape: ")).strip()
    if not url:
        print("[-] Error: URL cannot be empty")
        return
    is_js = str(
        input("[+] Does this website use JavaScript to render its elements? (Yes/No)(default=No): ")).lower()
    expected = ["yes", "y", "no", "n"]

    if is_js not in expected:
        print("[!] You entered an invalid value. Proceeding with the default value (No)")
        is_js = "no"
    prompt = str(
        input("[+] What data would you like to extract? (e.g., 'Extract all product prices and names'): ")).strip()
    if not prompt:
        print("[-] Error: Prompt cannot be empty")
        return

    print("\n[*] Starting scraping process...")

    try:
        user_id = gen_session_id()
        print("[*] Fetching webpage content...", end='\r')
        if is_js in ["yes", "y"]:
            content = await get_with_playwright(url)
            is_js_rendered = True
        else:
            content, is_js_rendered = await get_web_contents(url)

        if not content:
            print("[-] Error: Failed to fetch content from the URL")
            return

        print("[+] Content fetched successfully!")
        print("[*] Analyzing content with AI...", end='\r')
        code = await parse_html_with_ai(
            user_id=user_id,
            html_content=content,
            user_prompt=prompt,
            is_js_rendered=is_js_rendered,
            url=url
        )

        print("\n[+] Analysis complete!\n")
        print("=== Results ===\n")
        print(code)
        save = input("\n[?] Would you like to save the generated scraping code? (yes/no): ").lower()
        if save in ['y', 'yes']:
            filename = input("[+] Enter filename to save (default: scraper.py): ").strip() or "scraper.py"
            try:
                with open(filename, 'w') as f:
                    f.write("from playwright.async_api import async_playwright\n")
                    f.write("from bs4 import BeautifulSoup\n")
                    f.write("import asyncio\n\n")
                    f.write(code)
                    f.write("\n\nif __name__ == '__main__':\n    asyncio.run(main())")
                print(f"[+] Code saved to {filename}")
            except Exception as e:
                print(f"[-] Error saving file: {e}")

    except KeyboardInterrupt:
        print("\n[-] Operation cancelled by user")
    except Exception as e:
        print(f"[-] An error occurred: {e}")
    another = input("\n[?] Would you like to scrape another URL? (yes/no): ").lower()
    if another in ['y', 'yes']:
        await cli_main()
    else:
        print("\n[+] Thank you for using Web Scraper CLI!\n")

if __name__ == "__main__":
    asyncio.run(cli_main())