from ddgs import DDGS


def google_search(query: str, num_results: int = 5) -> str:
    """
    Search the web and return formatted results.

    Args:
        query: Search query
        num_results: Number of results to return

    Returns:
        Formatted string containing search results.
    """
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

        return "\n".join(output)

    except Exception as e:
        return f"Search failed: {e}"
