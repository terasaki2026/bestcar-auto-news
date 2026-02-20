import concurrent.futures
import re
import sys
import time
from datetime import datetime, timedelta, timezone

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


def parse_datetime_safe(value):
    """文字列/struct_time などを datetime に変換する。"""
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, time.struct_time):
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except Exception:
            return None

    try:
        return date_parser.parse(str(value))
    except Exception:
        return None


def extract_entry_datetime(entry):
    """feedparser entry から日付候補を抽出する。"""
    text_keys = ["published", "updated", "created", "issued", "date", "dc_date"]
    parsed_keys = ["published_parsed", "updated_parsed", "created_parsed"]

    for key in text_keys:
        if hasattr(entry, key):
            dt = parse_datetime_safe(getattr(entry, key))
            if dt:
                return dt

    for key in parsed_keys:
        if hasattr(entry, key):
            dt = parse_datetime_safe(getattr(entry, key))
            if dt:
                return dt

    return None


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
        base = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = now - base.astimezone(timezone.utc)
        return timedelta(0) <= diff <= timedelta(days=FILTER_DAYS, hours=23, minutes=59)
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

def _parse_rss_with_headers(url):
    """RSSをUser-Agent付きで取得し、feedparserで解釈する。"""
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def fetch_rss(url, source_name):
    """Fetch and parse standard RSS/Atom feeds using feedparser."""
    try:
        if not url:
            return []

        feed = _parse_rss_with_headers(url)
        if feed.bozo and not feed.entries:
            print(f"RSS parse warning ({source_name}): {feed.bozo_exception}")

        news_list = []

        skipped_no_date = 0
        skipped_out_of_period = 0

        for entry in feed.entries:
            dt = extract_entry_datetime(entry)

            if dt is None:
                skipped_no_date += 1
                continue

            if not is_within_period(dt):
                skipped_out_of_period += 1
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

        if not news_list:
            print(
                f"RSS had no usable items ({source_name}): "
                f"entries={len(feed.entries)}, no_date={skipped_no_date}, out_of_period={skipped_out_of_period}"
            )

        return news_list
    except Exception as e:
        print(f"Error fetching RSS {source_name}: {e}")
        return []


def fetch_rss_with_fallback(urls, source_name):
    """複数RSS URLを順に試し、最初に取得できた結果を返す。"""
    for url in urls:
        news = fetch_rss(url, source_name)
        if news:
            return news
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
        items = soup.select(
            ".newsList li, .news-list-item, .list-news li, .c-newsList__item, "
            ".news-release-list li, .newsrelease-list li, li.news-item"
        )

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

            date_node = item.select_one("time, .date, .c-newsList__date, .news-date")
            dt = None
            if date_node:
                date_str = date_node.get_text(strip=True)
                d_s = date_str.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
                try:
                    dt = date_parser.parse(d_s)
                    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                except Exception:
                    pass

            if dt is None:
                item_text = item.get_text(" ", strip=True)
                m = re.search(r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})", item_text)
                if m:
                    try:
                        dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
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
        (
            "Toyota",
            [
                "https://global.toyota/jp/newsroom/rss.xml",
                "https://global.toyota/jp/newsroom/toyota/feed.xml",
            ],
            "rss_multi",
        ),
        (
            "Honda",
            [
                "https://global.honda/jp/topics/rss.xml",
                "https://global.honda/jp/newsroom/newsroom.xml",
            ],
            "rss_multi",
        ),
        (
            "Mazda",
            [
                "https://newsroom.mazda.com/ja/publicity/release/rss.xml",
                "https://newsroom.mazda.com/ja/rss/news_release.xml",
            ],
            "rss_multi",
        ),
        (
            "Subaru",
            [
                "https://www.subaru.co.jp/press/rss.xml",
                "https://www.subaru.co.jp/news/feed/",
            ],
            "rss_multi",
        ),
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
            elif method == "rss_multi":
                future = executor.submit(fetch_rss_with_fallback, url, name)
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
