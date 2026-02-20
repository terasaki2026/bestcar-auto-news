import concurrent.futures
import re
import sys
from datetime import datetime

import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

# User-Agent for requests
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}

# 取得期間設定（直近7日）
FILTER_DAYS = 7


def clean_text(text):
    """HTMLタグを除去し、テキストのみを抽出・整形する。"""
    if not text:
        return ""
    try:
        soup = BeautifulSoup(str(text), "html.parser")
        clean = soup.get_text(separator=" ", strip=True)
        return " ".join(clean.split())
    except Exception:
        return str(text)


def trim_summary(text, limit=200):
    """要約テキストを指定文字数で丸める。"""
    if not text:
        return ""
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def is_within_period(dt):
    """日付が指定期間内か判定する。"""
    if not dt:
        return False

    try:
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        diff = now - dt
        return 0 <= diff.days <= FILTER_DAYS
    except Exception as e:
        print(f"Date check error: {e}")
        return False


def fetch_page_summary(url):
    """個別ページから本文を取得して要約（先頭200文字）を作成する。"""
    if not url:
        return ""

    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200:
            return ""

        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")

        # ノイズになりやすいタグだけ除去
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()

        # 主要コンテンツ候補を優先
        container = soup.select_one("main") or soup.select_one("article") or soup

        text_content = []
        for p in container.find_all("p"):
            t = p.get_text(strip=True)
            if len(t) > 20:
                text_content.append(t)
            if sum(len(x) for x in text_content) > 300:
                break

        return trim_summary(" ".join(text_content), limit=200)
    except Exception:
        return ""


# --- Independent Source Fetchers ---

def fetch_rss(url, source_name):
    """Fetch and parse standard RSS/Atom feeds using feedparser."""
    try:
        feed = feedparser.parse(url)
        news_list = []

        for entry in feed.entries:
            dt = None
            if hasattr(entry, "published"):
                try:
                    dt = date_parser.parse(entry.published)
                except Exception:
                    pass
            elif hasattr(entry, "updated"):
                try:
                    dt = date_parser.parse(entry.updated)
                except Exception:
                    pass

            if dt is None or not is_within_period(dt):
                continue

            summary_raw = ""
            if hasattr(entry, "summary"):
                summary_raw = entry.summary
            elif hasattr(entry, "description"):
                summary_raw = entry.description

            summary = clean_text(summary_raw)
            if len(summary) < 50:
                detail_summary = fetch_page_summary(getattr(entry, "link", ""))
                if detail_summary:
                    summary = detail_summary

            news_list.append(
                {
                    "source": source_name,
                    "title": clean_text(getattr(entry, "title", "No Title")),
                    "url": getattr(entry, "link", ""),
                    "date": dt,
                    "summary": trim_summary(summary, limit=200),
                }
            )

        return news_list
    except Exception as e:
        print(f"Error fetching RSS {source_name}: {e}")
        return []


def fetch_daihatsu():
    """Fetch Daihatsu news from their RSS feed."""
    url = "https://www.daihatsu.com/jp/rss.xml"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")
        news_list = []

        for item in items:
            raw_title = item.find("title").get_text(strip=True) if item.find("title") else ""
            link = item.find("link").get_text(strip=True) if item.find("link") else ""

            dt = None
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})\s*", raw_title)
            if date_match:
                try:
                    dt = date_parser.parse(date_match.group(1))
                except Exception:
                    pass

            if dt is None or not is_within_period(dt):
                continue

            clean_title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", raw_title)
            if not clean_title:
                clean_title = raw_title

            summary = trim_summary(fetch_page_summary(link), limit=200)

            news_list.append(
                {
                    "source": "Daihatsu",
                    "title": clean_text(clean_title),
                    "url": link,
                    "date": dt,
                    "summary": summary,
                }
            )

        return news_list
    except Exception as e:
        print(f"Error fetching Daihatsu: {e}")
        return []


def fetch_suzuki():
    """Fetch Suzuki news from their XML api."""
    url = "https://www.suzuki.co.jp/release/release.xml"
    base_url = "https://www.suzuki.co.jp"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding

        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")
        news_list = []

        for item in items:
            title = item.find("ttl").get_text(strip=True) if item.find("ttl") else "No Title"
            link_rel = item.find("link").get_text(strip=True) if item.find("link") else ""
            date_str = item.find("date").get_text(strip=True) if item.find("date") else ""

            dt = None
            try:
                d_s = date_str.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
                parsed_dt = date_parser.parse(d_s)
                dt = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except Exception:
                pass

            if dt is None or not is_within_period(dt):
                continue

            full_url = base_url + link_rel if link_rel.startswith("/") else link_rel
            summary = trim_summary(fetch_page_summary(full_url), limit=200)

            news_list.append(
                {
                    "source": "Suzuki",
                    "title": clean_text(title),
                    "url": full_url,
                    "date": dt,
                    "summary": summary,
                }
            )

        return news_list
    except Exception as e:
        print(f"Error fetching Suzuki: {e}")
        return []


def fetch_mitsubishi():
    """
    Fetch Mitsubishi Motors news from their official HTML page.
    APIを使わず、直接ニュースリリース一覧ページをスクレイピングする。
    """
    url = "https://www.mitsubishi-motors.com/jp/newsroom/newsrelease/"
    base_url = "https://www.mitsubishi-motors.com"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")

        news_list = []
        items = soup.select(".newsList li, .news-list-item, .list-news li, .c-newsList__item")

        for item in items:
            title_node = item.select_one("a")
            if not title_node:
                continue

            title = title_node.get_text(strip=True)
            link = title_node.get("href")
            if not link or link.startswith("javascript"):
                continue

            if link.startswith("/"):
                link = base_url + link

            date_node = item.select_one("time, .date, .c-newsList__date")
            dt = None
            if date_node:
                date_str = date_node.get_text(strip=True)
                d_s = date_str.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
                try:
                    dt = date_parser.parse(d_s)
                    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                except Exception:
                    pass

            if dt is None or not is_within_period(dt):
                continue

            summary = trim_summary(fetch_page_summary(link), limit=200)

            news_list.append(
                {
                    "source": "Mitsubishi Motors",
                    "title": clean_text(title),
                    "url": link,
                    "date": dt,
                    "summary": summary,
                }
            )

        return news_list
    except Exception as e:
        print(f"Error fetching Mitsubishi: {e}")
        return []


def fetch_nissan():
    """Fetch Nissan Global news (JP) by scraping the HTML list."""
    url = "https://global.nissannews.com/ja-JP/channels/news"
    base_domain = "https://global.nissannews.com"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")

        items = soup.select("div.release-item")
        news_list = []

        for item in items:
            title_node = item.select_one("div.title a")
            if not title_node:
                continue

            title = title_node.get_text(strip=True)
            link = title_node.get("href")

            if link and link.startswith("/"):
                link = base_domain + link
            elif not link:
                continue

            date_node = item.select_one("time.pub-date")
            dt = None
            if date_node:
                dt_attr = date_node.get("datetime")
                if dt_attr:
                    try:
                        dt = date_parser.parse(dt_attr)
                    except Exception:
                        pass

                if dt is None:
                    try:
                        d_text = date_node.get_text(strip=True)
                        d_text = d_text.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
                        parsed_dt = date_parser.parse(d_text)
                        dt = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    except Exception:
                        pass

            if dt is None or not is_within_period(dt):
                continue

            summary = trim_summary(fetch_page_summary(link), limit=200)

            news_list.append(
                {
                    "source": "Nissan",
                    "title": clean_text(title),
                    "url": link,
                    "date": dt,
                    "summary": summary,
                }
            )

        return news_list
    except Exception as e:
        print(f"Error fetching Nissan: {e}")
        return []


# --- Main Coordinator ---

def collect_news():
    """
    Collects news from all sources in parallel.
    Returns: List of dictionaries sorted by date (newest first).
    """
    sources = [
        ("Toyota", "https://global.toyota/jp/newsroom/rss.xml", "rss"),
        ("Honda", "https://global.honda/jp/topics/rss.xml", "rss"),
        ("Mazda", "https://newsroom.mazda.com/ja/publicity/release/rss.xml", "rss"),
        ("Subaru", "https://www.subaru.co.jp/press/rss.xml", "rss"),
        ("Daihatsu", "", "daihatsu"),
        ("Suzuki", "", "suzuki"),
        ("Mitsubishi Motors", "", "mitsubishi"),
        ("Nissan", "", "nissan"),
    ]

    all_news = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {}
        for name, url, method in sources:
            if method == "rss":
                future = executor.submit(fetch_rss, url, name)
            elif method == "daihatsu":
                future = executor.submit(fetch_daihatsu)
            elif method == "suzuki":
                future = executor.submit(fetch_suzuki)
            elif method == "mitsubishi":
                future = executor.submit(fetch_mitsubishi)
            elif method == "nissan":
                future = executor.submit(fetch_nissan)
            else:
                continue

            future_map[future] = name

        for future in concurrent.futures.as_completed(future_map):
            name = future_map[future]
            try:
                news = future.result()
                all_news.extend(news)
                print(f"Fetched {len(news)} items from {name}")
            except Exception as e:
                print(f"Failed to collect from {name}: {e}")

    def get_timestamp(item):
        d = item.get("date")
        if not d:
            return 0
        return d.timestamp()

    all_news.sort(key=get_timestamp, reverse=True)
    return all_news


if __name__ == "__main__":
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() == "cp932":
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    items = collect_news()
    print(f"Collected {len(items)} items (Past {FILTER_DAYS} days).")
    for item in items:
        try:
            print(f"[{item['source']}] {item['date'].strftime('%Y-%m-%d')} - {item['title']}")
        except Exception:
            pass
