import concurrent.futures
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

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

FILTER_DAYS = 7

RSS_SOURCES = {
    "Toyota": [
        "https://global.toyota/export/jp/allnews_rss.xml",
        "https://global.toyota/jp/newsroom/rss.xml",
    ],
    "Honda": [
        "https://www.honda.co.jp/RSS/news.xml",
        "https://www.honda.co.jp/RSS/all.xml",
    ],
    "Mazda": [
        "https://newsroom.mazda.com/ja/rss/news_release.xml",
        "https://newsroom.mazda.com/ja/publicity/release/rss.xml",
    ],
    "Subaru": [
        "https://www.subaru.co.jp/news/feed/",
        "https://www.subaru.co.jp/press/rss.xml",
    ],
}

def clean_text(text):
    if not text:
        return ""
    try:
        text = re.sub(r"\s*（別ウィンドウで開く）\s*", "", str(text))
        soup = BeautifulSoup(text, "html.parser")
        clean = soup.get_text(separator=" ", strip=True)
        return " ".join(clean.split())
    except Exception:
        return str(text)

def trim_summary(text, limit=200):
    cleaned = clean_text(text)
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."

def parse_datetime_safe(value):
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

def normalize_date_text(text):
    return str(text).replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")

def extract_entry_datetime(entry):
    for key in ["published", "updated", "created", "issued", "date", "dc_date"]:
        dt = parse_datetime_safe(getattr(entry, key, None))
        if dt: return dt
    for key in ["published_parsed", "updated_parsed", "created_parsed"]:
        dt = parse_datetime_safe(getattr(entry, key, None))
        if dt: return dt
    return None

def is_within_period(dt):
    if not dt: return False
    try:
        aware_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone(timedelta(hours=9)))
        now_utc = datetime.now(timezone.utc)
        diff = now_utc - aware_dt.astimezone(timezone.utc)
        return timedelta(hours=-12) <= diff <= timedelta(days=FILTER_DAYS, hours=23)
    except Exception:
        return False

def fetch_page_summary(url):
    if not url: return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code != 200: return ""
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")
        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
            tag.decompose()
        container = soup.select_one("main") or soup.select_one("article") or soup
        text_content = []
        total_len = 0
        for p in container.find_all("p"):
            t = p.get_text(strip=True)
            if len(t) > 20:
                text_content.append(t)
                total_len += len(t)
            if total_len > 300: break
        return trim_summary(" ".join(text_content), limit=200)
    except Exception:
        return ""

def _parse_rss_with_headers(url):
    url = url.rstrip("/")
    headers = HEADERS.copy()
    headers.update({
        "Accept": "application/rss+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
        "Referer": "https://www.google.com/",
    })
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return feedparser.parse(resp.content)

def fetch_rss(url, source_name):
    try:
        if not url: return []
        feed = _parse_rss_with_headers(url)
        news_list = []
        for entry in feed.entries:
            dt = extract_entry_datetime(entry)
            if dt is None or not is_within_period(dt): continue
            summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
            summary = clean_text(summary_raw)
            if len(summary) < 50:
                detail_summary = fetch_page_summary(getattr(entry, "link", ""))
                if detail_summary: summary = detail_summary
            news_list.append({
                "source": source_name,
                "title": clean_text(getattr(entry, "title", "No Title")),
                "url": getattr(entry, "link", ""),
                "date": dt,
                "summary": trim_summary(summary, limit=200),
            })
        return news_list
    except Exception:
        return []

def fetch_rss_with_fallback(urls, source_name):
    for url in urls:
        news = fetch_rss(url, source_name)
        if news: return news
    if source_name == "Subaru": return fetch_subaru_html()
    if source_name == "Mitsubishi Motors": return fetch_mitsubishi()
    return []

def fetch_daihatsu():
    url = "https://www.daihatsu.com/jp/rss.xml"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "xml")
        news_list = []
        for item in soup.find_all("item"):
            title = item.find("title").get_text(strip=True) if item.find("title") else ""
            link = item.find("link").get_text(strip=True) if item.find("link") else ""
            dt = None
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})\s*", title)
            if date_match: dt = parse_datetime_safe(date_match.group(1))
            if dt is None or not is_within_period(dt): continue
            clean_title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", title) or title
            news_list.append({
                "source": "Daihatsu",
                "title": clean_text(clean_title),
                "url": link,
                "date": dt,
                "summary": trim_summary(fetch_page_summary(link), limit=200),
            })
        return news_list
    except Exception:
        return []

def fetch_suzuki():
    url = "https://www.suzuki.co.jp/release/release.xml"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "xml")
        news_list = []
        for item in soup.find_all("item"):
            title = item.find("ttl").get_text(strip=True) if item.find("ttl") else "No Title"
            link_rel = item.find("link").get_text(strip=True) if item.find("link") else ""
            date_str = item.find("date").get_text(strip=True) if item.find("date") else ""
            dt = parse_datetime_safe(normalize_date_text(date_str))
            if dt: dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            if dt is None or not is_within_period(dt): continue
            full_url = urljoin("https://www.suzuki.co.jp", link_rel)
            news_list.append({
                "source": "Suzuki",
                "title": clean_text(title),
                "url": full_url,
                "date": dt,
                "summary": trim_summary(fetch_page_summary(full_url), limit=200),
            })
        return news_list
    except Exception:
        return []

def fetch_mitsubishi():
    try:
        resp = requests.get("https://www.mitsubishi-motors.com/jp/newsroom/index.html", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")
        news_list = []
        for item in soup.select(".m_newsMedia__item"):
            link_node = item.select_one("a.m_newsMedia__link")
            if not link_node: continue
            title_node = item.select_one(".m_newsMedia__text")
            title = title_node.get_text(strip=True) if title_node else "No Title"
            link = urljoin("https://www.mitsubishi-motors.com", link_node.get("href"))
            date_node = item.select_one("time.m_newsMedia__time")
            dt = parse_datetime_safe(normalize_date_text(date_node.get("datetime") or date_node.get_text(strip=True))) if date_node else None
            if dt is None or not is_within_period(dt): continue
            news_list.append({
                "source": "Mitsubishi Motors",
                "title": clean_text(title),
                "url": link,
                "date": dt,
                "summary": trim_summary(fetch_page_summary(link), limit=200),
            })
        return news_list
    except Exception:
        return []

def fetch_subaru_html():
    try:
        resp = requests.get("https://www.subaru.co.jp/news/", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")
        news_list = []
        for item in soup.select(".section_news-list li, .news-list li, ul li"):
            link_node = item.select_one("a")
            if not link_node or not link_node.get("href"): continue
            m = re.search(r"(\d{4}[/年]\d{1,2}[/月]\d{1,2})", item.get_text(" ", strip=True))
            dt = parse_datetime_safe(normalize_date_text(m.group(1))) if m else None
            if dt is None or not is_within_period(dt): continue
            link = urljoin("https://www.subaru.co.jp", link_node.get("href"))
            news_list.append({
                "source": "Subaru",
                "title": clean_text(link_node.get_text(strip=True)),
                "url": link,
                "date": dt,
                "summary": trim_summary(fetch_page_summary(link), limit=200)
            })
        return news_list
    except Exception:
        return []

def fetch_nissan():
    try:
        resp = requests.get("https://global.nissannews.com/ja-JP/channels/news", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        news_list = []
        for item in soup.select("div.release-item"):
            title_node = item.select_one("div.title a")
            if not title_node: continue
            link = urljoin("https://global.nissannews.com", title_node.get("href"))
            date_node = item.select_one("time.pub-date")
            dt = parse_datetime_safe(date_node.get("datetime")) if date_node else None
            if dt is None: dt = parse_datetime_safe(normalize_date_text(date_node.get_text(strip=True))) if date_node else None
            if dt is None or not is_within_period(dt): continue
            news_list.append({
                "source": "Nissan",
                "title": clean_text(title_node.get_text(strip=True)),
                "url": link,
                "date": dt,
                "summary": trim_summary(fetch_page_summary(link), limit=200),
            })
        return news_list
    except Exception:
        return []

def collect_news():
    sources = [
        ("Toyota", RSS_SOURCES["Toyota"], "rss_multi"),
        ("Honda", RSS_SOURCES["Honda"], "rss_multi"),
        ("Mazda", RSS_SOURCES["Mazda"], "rss_multi"),
        ("Subaru", RSS_SOURCES["Subaru"], "rss_multi"),
        ("Daihatsu", "", "daihatsu"),
        ("Suzuki", "", "suzuki"),
        ("Mitsubishi Motors", "", "mitsubishi"),
        ("Nissan", "", "nissan"),
    ]
    all_news = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {}
        for name, data, method in sources:
            if method == "rss_multi": future = executor.submit(fetch_rss_with_fallback, data, name)
            elif method == "daihatsu": future = executor.submit(fetch_daihatsu)
            elif method == "suzuki": future = executor.submit(fetch_suzuki)
            elif method == "mitsubishi": future = executor.submit(fetch_mitsubishi)
            elif method == "nissan": future = executor.submit(fetch_nissan)
            else: continue
            future_map[future] = name
        for future in concurrent.futures.as_completed(future_map):
            try:
                all_news.extend(future.result())
            except Exception:
                pass
    all_news.sort(key=lambda item: item.get("date").timestamp() if item.get("date") else 0, reverse=True)
    return all_news

if __name__ == "__main__":
    items = collect_news()
    print(f"Collected {len(items)} items.")
    for item in items:
        print(f"[{item['source']}] {item['date'].strftime('%Y-%m-%d')} - {item['title']}")