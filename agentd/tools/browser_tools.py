from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import sys
import requests

BAIDU_SEARCH_URL = "https://www.baidu.com/s"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def baidu_search(query: str, num_results: int = 10, lang: str = "en") -> List[Dict[str, Optional[str]]]:
    """
    在百度上搜索，返回结果列表。
    每个结果包含 title, link, snippet。
    """
    if not query:
        raise ValueError("query 不能为空")

    params = {
        "wd": query,
        "rn": min(max(1, num_results), 20),
        "ie": "utf-8",
    }

    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": lang,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    }

    resp = requests.get(BAIDU_SEARCH_URL, params=params, headers=headers, timeout=10)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = []

    for g in soup.select("div.result"):
        title_el = g.select_one("h3 a")
        link_el = g.select_one("h3 a")
        snippet_el = g.select_one("div.c-abstract")

        if not title_el or not link_el:
            continue

        href = link_el.get("href")
        if not href or href.startswith("/"):  # 过滤无效或内链
            continue

        title = title_el.get_text(strip=True)
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""

        results.append({"title": title, "link": href, "snippet": snippet})
        if len(results) >= num_results:
            break

    return results


def search(query: str, num_results: int = 10, lang: str = "en") -> str:
    results = baidu_search(query, num_results)

    lines = []

    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        link = r.get("link", "")
        snippet = r.get("snippet", "")

        block = f"""[{i}]
                标题: {title}
                链接: {link}
                摘要: {snippet}
                """
        lines.append(block)

    return "\n".join(lines)


def get_webpage(url: str) -> str:
    """
    访问指定URL并返回网页内容。
    """
    if not url:
        # raise ValueError("URL 不能为空")
        return "URL 不能为空"

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        # raise RuntimeError(f"访问网页失败: {e}")
        return f"访问网页失败: {e}"

TOOLS = [
    {
        "name": "web_search",
        "description": (
            "Search the web and return results. "
            "Use for looking up information, news, etc. "
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query.",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return. Default 10.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_webpage",
        "description": (
            "Fetch the content of a webpage given its URL. "
            "Use for retrieving information from specific pages."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the webpage to fetch.",
                },
            },
            "required": ["url"],
        },
    },
]

TOOL_HANDLERS = {
    "web_search": search,
    "get_webpage": get_webpage,
}


if __name__ == "__main__":

    if len(sys.argv) < 2:
        print("用法: python browser.py <查询词> [结果数量]")
        sys.exit(1)

    q = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    for i, item in enumerate(baidu_search(q, num_results=n), start=1):
        print(f"{i}. {item['title']}")
        print(f"   {item['link']}")
        if item["snippet"]:
            print(f"   {item['snippet']}")
        print()
