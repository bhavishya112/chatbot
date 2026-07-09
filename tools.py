from ddgs import DDGS
import logging

logging.basicConfig(
    filename="tools.log",
    filemode="a",  # 'a' appends new logs; 'w' overwrites the file each run
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M %d %B",
)

logger = logging.getLogger(__name__)


def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web and return formatted results.

    Args:
        query: Search query
        num_results: Number of results to return

    Returns:
        Formatted string containing search results.
    """

    logger.info("✅Starting Web Search")
    num_results = int(num_results)
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))

        if not results:
            return "No search results found."

        output = []

        for i, result in enumerate(results, start=1):
            title = result.get("title", "No title")
            body = result.get("body", "")
            href = result.get("href", "")

            output.append(f"""Result {i}
                            Title: {title}
                            URL: {href}
                            Snippet: {body}
                            """)

        result = "\n".join(output)
        logger.info("✅Web Search Ended")
        logger.info("[RESULT-WEB SEARCH] : \n%s", result)
        if len(result) // 4 > 500:  # token limit bhi to bachani h dost
            return summarize(result, query)
        return result

    except Exception as e:
        logger.exception(e)
        return f"Search failed: {e}"


from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
)


def summarize(text: str, query: str | None = None) -> str:
    """
    Summarize the given text using DeepSeek-R1:1.5B running on Ollama.

    Args:
        text: The text to summarize.
        query: Optional instruction to focus the summary.

    Returns:
        A summary string.
    """
    logger.info("✅Starting Summarizer")
    prompt = text + "\n\nGet useful and important details from the text."

    if query:
        prompt += f"\n\nFocus the summary according to this query:\n{query}"

    response = client.chat.completions.create(
        # model="deepseek-r1:1.5b",
        model="ibm/granite4.1:3b",
        messages=[
            {
                "role": "system",
                "content": (
                    """
                  You are dad of an expert summarizer. Your primary rule: preserve ALL website references, links, and URLs exactly as they appear in the source text. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Always keep each URL directly attached to the specific point, fact, or information it supports. 
                - Do not move URLs to the bottom or into a separate references section. 
                - Do not paraphrase, shorten, or omit URLs. 
                - If a summary point mentions a source, include the URL inline with that point.
                    """
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0.2,
    )
    logger.info("✅Done Summarizing")
    summary = response.choices[0].message.content.strip()
    logger.info("[SUMMARY] : \n%s", summary)
    return summary
