from ddgs import DDGS
import logging

logging.basicConfig(
    filename="logs/ai_backend.log",
    filemode="a",  # 'a' appends new logs; 'w' overwrites each run
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s - %(message)s",
    datefmt="%H:%M %d %B",
    encoding="utf-8",
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


from openai import OpenAI

openaiclient = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

MODEL_NAME = "all-minilm:l6-v2"
# COLLECTION_NAME = "ui_elements"
VECTORDB_PATH = "data/vectordb/ui_vector_db2"
import chromadb
import json


from typing import Literal

# vectordb path for querying ui


def query_ui(
    question: str,
    top_k: int = 5,
    view: Literal["desktop", "mobile"] = "desktop",
    collection: str = "ui_elements",
) -> str:

    try:
        logger.info("✅ [QUERYING UI] question: %s", question)
        client = chromadb.PersistentClient(path=VECTORDB_PATH)
        collection = client.get_collection(collection)

        response = openaiclient.embeddings.create(input=question, model=MODEL_NAME)
        embedding = [emb.embedding for emb in response.data]
        
        results = collection.query(
            query_embeddings=embedding, n_results=top_k, where={"view": view}
        )

        matches = []
        for doc, meta, dist in zip(
            results["documents"][0], results["metadatas"][0], results["distances"][0]
        ):
            meta = dict(meta)
            matches.append({"score": round(1 - dist, 3), "text": doc, **meta})

        result = ""
        for data in matches:
            for x in data:
                if x == "size" or x == "position":
                    data[x] = json.loads(data[x])
                result +=  f"{x} : {data[x]}|"
                # print(f"{x} : {data[x]}")
            result += "\n"

        logger.info("✅ [QUERIED UI OK]:\n[RESULTS] : %s", result)
        return result

    except Exception as e:
        logger.exception(e)
        return "query_ui failed : " + str(e)
