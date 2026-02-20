import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from datetime import datetime, timedelta, timezone
import concurrent.futures
import traceback
import sys
import re

# User-Agent for requests
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# 取得期間設定（直近7日）
FILTER_DAYS = 7

def clean_text(text):
    if not text:
        return ""
    try:
        soup = BeautifulSoup(str(text), "html.parser")
        clean = soup.get_text(separator=" ", strip=True)
        return " ".join(clean.split())
    except:
        return str(text)

def is_within_period(dt):
    if not dt:
        return False
    try:
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if dt.tzinfo is None and now.tzinfo is not None:
             now = now.replace(tzinfo=None)
        diff = now - dt
        return diff.days <= FILTER_DAYS
    except Exception as e:
        print(f"Date check error: {e}")
        return False

def fetch_page_summary(url):
    if not url:
        return ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        if resp.status_code != 200:
            return ""
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")

        for tag in soup():
            tag.decompose()
        
        text_content = ""
        paragraphs = soup.find_all("p")
        for p in paragraphs:
            t = p.get_text(strip=True)
            if len(t) > 20:
                text_content += t + " "
                if len(text_content) > 300: break
        
        return clean_text(text_content)
    except Exception as e:
        return ""

def fetch_rss(url, source_name):
    try:
        feed = feedparser.parse(url)
        news_list =[]
        for entry in feed.entries:
            dt = None
            if hasattr(entry, "published"):
                try:
                    dt = date_parser.parse(entry.published)
                except:
                    pass
            elif hasattr(entry, "updated"):
                try:
                    dt = date_parser.parse(entry.updated)
                except:
                    pass
            
            if dt is None:
                continue
            if not is_within_period(dt):
                continue

            summary_raw = ""
            if hasattr(entry, "summary"):
                summary_raw = entry.summary
            elif hasattr(entry, "description"):
                summary_raw = entry.description
            
            summary = clean_text(summary_raw)
            if len(summary) < 50:
                 detail_summary = fetch_page_summary(entry.link)
                 if detail_summary:
                     summary = detail_summary

            summary = summary
            if len(summary) >= 200: summary += "..."
            
            news_list.append({
                "source": source_name,
                "title": clean_text(entry.title),
                "url": entry.link,
                "date": dt,
                "summary": summary
            })
        return news_list
    except Exception as e:
        print(f"Error fetching RSS {source_name}: {e}")
        return[]

def fetch_daihatsu():
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
                except:
                    pass
            if dt is None:
                continue
            if not is_within_period(dt):
                continue
            
            clean_title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*\\s*", "", raw_title)
            if not clean_title:
                clean_title = raw_title
            
            summary = fetch_page_summary(link)
            if len(summary) >= 200:
                summary += "..."
            
            news_list.append({
                "source": "Daihatsu",
                "title": clean_text(clean_title),
                "url": link,
                "date": dt,
                "summary": summary
            })
        return news_list
    except Exception as e:
        print(f"Error fetching Daihatsu: {e}")
        return[]

def fetch_suzuki():
    url = "https://www.suzuki.co.jp/release/release.xml"
    base_url = "https://www.suzuki.co.jp"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "xml")
        items = soup.find_all("item")
        news_list =[]
        for item in items:
            title = item.find("ttl").get_text(strip=True) if item.find("ttl") else "No Title"
            link_rel = item.find("link").get_text(strip=True) if item.find("link") else ""
            date_str = item.find("date").get_text(strip=True) if item.find("date") else ""
            dt = None
            try:
                d_s = date_str.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
                parsed_dt = date_parser.parse(d_s)
                dt = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            except:
                pass
            if dt is None:
                continue
            if not is_within_period(dt):
                continue
            
            full_url = base_url + link_rel if link_rel.startswith("/") else link_rel
            summary = fetch_page_summary(full_url)
            if len(summary) >= 200: summary += "..."
            news_list.append({
                "source": "Suzuki",
                "title": clean_text(title),
                "url": full_url,
                "date": dt,
                "summary": summary
            })
        return news_list
    except Exception as e:
        print(f"Error fetching Suzuki: {e}")
        return[]

def fetch_mitsubishi():
    url = "https://www.mitsubishi-motors.com/jp/newsroom/newsrelease/"
    base_url = "https://www.mitsubishi-motors.com"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding
        soup = BeautifulSoup(resp.content, "html.parser")
        news_list =[]
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
                except:
                    pass
            if dt is None or not is_within_period(dt):
                continue
                
            summary = fetch_page_summary(link)
            if len(summary) >= 200: 
                summary += "..."

            news_list.append({
                "source": "Mitsubishi Motors",
                "title": clean_text(title),
                "url": link,
                "date": dt,
                "summary": summary
            })
        return news_list
    except Exception as e:
        print(f"Error fetching Mitsubishi: {e}")
        return[]

def fetch_nissan():
    url = "https://global.nissannews.com/ja-JP/channels/news"
    base_domain = "https://global.nissannews.com"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        items = soup.select("div.release-item")
        news_list =[]
        for item in items:
            title_node = item.select_one("div.title a")
            if not title_node:
                continue
            title = title_node.get_text(strip=True)
            link = title_node.get("href")
            if link and link.startswith("/"):
                link = base_domain + link
            elif link and not link.startswith("http"):
                 pass 
            date_node = item.select_one("time.pub-date")
            dt = None
            if date_node:
                dt_attr = date_node.get("datetime")
                if dt_attr:
                    try:
                        dt = date_parser.parse(dt_attr)
                    except:
                        pass
                if dt is None:
                    try:
                        d_text = date_node.get_text(strip=True)
                        d_text = d_text.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
                        parsed_dt = date_parser.parse(d_text)
                        dt = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                    except:
                        pass
            if dt is None:
                continue
            if not is_within_period(dt):
                continue
            summary = fetch_page_summary(link)
            if len(summary) >= 200: summary += "..."
            news_list.append({
                "source": "Nissan",
                "title": clean_text(title),
                "url": link,
                "date": dt,
                "summary": summary
            })
        return news_list
    except Exception as e:
        print(f"Error fetching Nissan: {e}")
        return []

def collect_news():
    sources =
    
    all_news =[]
    
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
            future_map = name
            
        for future in concurrent.futures.as_completed(future_map):
            name = future_map
            try:
                news = future.result()
                all_news.extend(news)
                print(f"Fetched {len(news)} items from {name}")
            except Exception as e:
                print(f"Failed to collect from {name}: {e}")
                
    def get_timestamp(n):
        d = n
        if d.tzinfo:
            return d.timestamp()
        else:
            return d.timestamp()

    all_news.sort(key=get_timestamp, reverse=True)
    return all_news

if __name__ == "__main__":
    import sys
    try:
        if sys.stdout.encoding.lower() == 'cp932':
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    items = collect_news()
    print(f"Collected {len(items)} items (Past {FILTER_DAYS} days).")
    for i in items:
         try:
            print(f"[{i}] {i.strftime('%Y-%m-%d')} - {i}")
         except:
            pass