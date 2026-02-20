-import feedparser
-import requests
-from bs4 import BeautifulSoup
-from dateutil import parser as date_parser
-from datetime import datetime, timedelta, timezone
-import concurrent.futures
-import traceback
-import sys
-import re
-
-# User-Agent for requests
-HEADERS = {
-    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
-}
-
-# 取得期間設定（直近7日）
-FILTER_DAYS = 7
-
-def clean_text(text):
-    """
-    HTMLタグを除去し、テキストのみを抽出・整形する
-    """
-    if not text:
-        return ""
-    try:
-        # BeautifulSoupでタグ除去
-        soup = BeautifulSoup(str(text), "html.parser")
-        clean = soup.get_text(separator=" ", strip=True)
-        # 余分な空白を削除
-        return " ".join(clean.split())
-    except:
-        return str(text)
-
-def is_within_period(dt):
-    """
-    日付が指定期間内か判定する
-    """
-    if not dt:
-        return False
-    
-    try:
-        # 現在時刻（タイムゾーン考慮）
-        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
-        
-        # タイムゾーンなし同士、あり同士で比較できるように調整
-        if dt.tzinfo is None and now.tzinfo is not None:
-             now = now.replace(tzinfo=None)
-        
-        diff = now - dt
-        return diff.days <= FILTER_DAYS
-    except Exception as e:
-        print(f"Date check error: {e}")
-        return False
-
-def fetch_page_summary(url):
-    """
-    個別ページから本文を取得して要約（先頭200文字）を作成する
-    """
-    if not url:
-        return ""
-    try:
-        # 記事ページ取得
-        resp = requests.get(url, headers=HEADERS, timeout=5)
-        if resp.status_code != 200:
-            return ""
-        resp.encoding = resp.apparent_encoding
-        soup = BeautifulSoup(resp.content, "html.parser")
-
-        # 本文抽出（一般的なタグを狙う）
-        # メーカーごとに構造が違うため、汎用的にpタグなどを集める
-        # 不要なタグ（ナビゲーション、フッター）を除外
-        for tag in soup():
-            tag.decompose()
-        
-        # メインコンテンツらしきものを探す
-        # 汎用: pタグのテキストを結合
-        text_content = ""
-        paragraphs = soup.find_all("p")
-        for p in paragraphs:
-            t = p.get_text(strip=True)
-            if len(t) > 20: # 短すぎる行は無視
-                text_content += t + " "
-                if len(text_content) > 300: break # 十分取れたら終了
-        
-        return clean_text(text_content)
-    except Exception as e:
-        # print(f"Summary fetch failed for {url}: {e}")
-        return ""
-
-# --- Independent Source Fetchers ---
-
-def fetch_rss(url, source_name):
-    """
-    Fetch and parse standard RSS/Atom feeds using feedparser.
-    """
-    try:
-        feed = feedparser.parse(url)
-        news_list =[]
-        for entry in feed.entries:
-            # Date parsing
-            dt = None
-            if hasattr(entry, "published"):
-                try:
-                    dt = date_parser.parse(entry.published)
-                except:
-                    pass
-            elif hasattr(entry, "updated"):
-                try:
-                    dt = date_parser.parse(entry.updated)
-                except:
-                    pass
-            
-            if dt is None:
-                continue
-
-            if not is_within_period(dt):
-                continue
-
-            # Summary extraction with strict cleaning
-            summary_raw = ""
-            if hasattr(entry, "summary"):
-                summary_raw = entry.summary
-            elif hasattr(entry, "description"):
-                summary_raw = entry.description
-            
-            summary = clean_text(summary_raw)
-            
-            # If summary is too short, fetch detail page content (e.g. for Mazda)
-            if len(summary) < 50:
-                 detail_summary = fetch_page_summary(entry.link)
-                 if detail_summary:
-                     summary = detail_summary
-
-            summary = summary # Limit length
-            if len(summary) >= 200: summary += "..."
-            
-            news_list.append({
-                "source": source_name,
-                "title": clean_text(entry.title),
-                "url": entry.link,
-                "date": dt,
-                "summary": summary
-            })
-        return news_list
-    except Exception as e:
-        print(f"Error fetching RSS {source_name}: {e}")
-        return[]
-
-def fetch_daihatsu():
-    """
-    Fetch Daihatsu news from their RSS feed.
-    """
-    url = "https://www.daihatsu.com/jp/rss.xml"
-    try:
-        resp = requests.get(url, headers=HEADERS, timeout=10)
-        resp.raise_for_status()
-        resp.encoding = resp.apparent_encoding
-        
-        soup = BeautifulSoup(resp.content, "xml")
-        items = soup.find_all("item")
-        news_list = []
-        
-        for item in items:
-            raw_title = item.find("title").get_text(strip=True) if item.find("title") else ""
-            link = item.find("link").get_text(strip=True) if item.find("link") else ""
-            
-            # Extract date from title: "2026-02-13 本文タイトル"
-            dt = None
-            date_match = re.match(r"(\d{4}-\d{2}-\d{2})\s*", raw_title)
-            if date_match:
-                try:
-                    dt = date_parser.parse(date_match.group(1))
-                except:
-                    pass
-            
-            if dt is None:
-                continue
-            
-            if not is_within_period(dt):
-                continue
-            
-            # Clean title: remove date and category prefix
-            clean_title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*\\s*", "", raw_title)
-            if not clean_title:
-                clean_title = raw_title
-            
-            # Fetch summary from detail page
-            summary = fetch_page_summary(link)
-            if len(summary) >= 200:
-                summary += "..."
-            
-            news_list.append({
-                "source": "Daihatsu",
-                "title": clean_text(clean_title),
-                "url": link,
-                "date": dt,
-                "summary": summary
-            })
-        return news_list
-    except Exception as e:
-        print(f"Error fetching Daihatsu: {e}")
-        return[]
-
-def fetch_suzuki():
-    """
-    Fetch Suzuki news from their XML api.
-    """
-    url = "https://www.suzuki.co.jp/release/release.xml"
-    base_url = "https://www.suzuki.co.jp"
-    try:
-        resp = requests.get(url, headers=HEADERS, timeout=10)
-        resp.raise_for_status()
-        resp.encoding = resp.apparent_encoding
-        
-        soup = BeautifulSoup(resp.content, "xml")
-        items = soup.find_all("item")
-        news_list =[]
-        
-        # Limit items to check
-        for item in items:
-            title = item.find("ttl").get_text(strip=True) if item.find("ttl") else "No Title"
-            link_rel = item.find("link").get_text(strip=True) if item.find("link") else ""
-            date_str = item.find("date").get_text(strip=True) if item.find("date") else ""
-            
-            # Date parsing
-            dt = None
-            try:
-                # Common formats: 2026年2月13日, 2026.2.13, 2026/2/13
-                d_s = date_str.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
-                parsed_dt = date_parser.parse(d_s)
-                # Set time to 00:00:00 explicitly for date-only strings
-                dt = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
-            except:
-                pass
-            
-            if dt is None:
-                continue
-
-            if not is_within_period(dt):
-                continue
-            
-            full_url = base_url + link_rel if link_rel.startswith("/") else link_rel
-            
-            summary = fetch_page_summary(full_url)
-            if len(summary) >= 200: summary += "..."
-
-            news_list.append({
-                "source": "Suzuki",
-                "title": clean_text(title),
-                "url": full_url,
-                "date": dt,
-                "summary": summary
-            })
-        return news_list
-    except Exception as e:
-        print(f"Error fetching Suzuki: {e}")
-        return[]
-
-def fetch_mitsubishi():
-    """
-    Fetch Mitsubishi Motors news from their official HTML page.
-    APIを使わず、直接ニュースリリース一覧ページをスクレイピングする方式に変更
-    """
-    url = "https://www.mitsubishi-motors.com/jp/newsroom/newsrelease/"
-    base_url = "https://www.mitsubishi-motors.com"
-    try:
-        resp = requests.get(url, headers=HEADERS, timeout=10)
-        resp.raise_for_status()
-        resp.encoding = resp.apparent_encoding
-        soup = BeautifulSoup(resp.content, "html.parser")
-        
-        news_list =[]
-        
-        # ニュース一覧を抽出（よくあるクラス名で広く拾えるように複数指定）
-        items = soup.select(".newsList li, .news-list-item, .list-news li, .c-newsList__item")
-        
-        for item in items: # 直近20件に制限
-            title_node = item.select_one("a")
-            if not title_node:
-                continue
-            
-            title = title_node.get_text(strip=True)
-            link = title_node.get("href")
-            
-            if not link or link.startswith("javascript"):
-                continue
-                
-            # 相対パスを絶対URLに変換
-            if link.startswith("/"):
-                link = base_url + link
-                
-            # 日付の取得（<time> タグや特定のクラス名を探す）
-            date_node = item.select_one("time, .date, .c-newsList__date")
-            dt = None
-            if date_node:
-                date_str = date_node.get_text(strip=True)
-                # "2026年2月13日" や "2026.02.13" などを標準フォーマットに変換
-                d_s = date_str.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
-                try:
-                    dt = date_parser.parse(d_s)
-                    dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
-                except:
-                    pass
-            
-            # 日付が取得できない、または期間外の場合はスキップ
-            if dt is None or not is_within_period(dt):
-                continue
-                
-            # 詳細ページから本文の冒頭を取得して要約にする
-            summary = fetch_page_summary(link)
-            if len(summary) >= 200: 
-                summary += "..."
-
-            news_list.append({
-                "source": "Mitsubishi Motors",
-                "title": clean_text(title),
-                "url": link,
-                "date": dt,
-                "summary": summary
-            })
-            
-        return news_list
-    except Exception as e:
-        print(f"Error fetching Mitsubishi: {e}")
-        return[]
-
-def fetch_nissan():
-    """
-    Fetch Nissan Global news (JP) by scraping the HTML list.
-    """
-    url = "https://global.nissannews.com/ja-JP/channels/news"
-    base_domain = "https://global.nissannews.com"
-    try:
-        resp = requests.get(url, headers=HEADERS, timeout=10)
-        resp.raise_for_status()
-        soup = BeautifulSoup(resp.content, "html.parser")
-        
-        # Select items
-        items = soup.select("div.release-item")
-        news_list =[]
-        
-        # Limit to first 15 items to fetch details for speed
-        for item in items:
-            title_node = item.select_one("div.title a")
-            if not title_node:
-                continue
-            title = title_node.get_text(strip=True)
-            link = title_node.get("href")
-            
-            if link and link.startswith("/"):
-                link = base_domain + link
-            elif link and not link.startswith("http"):
-                 pass 
-
-            # Date
-            date_node = item.select_one("time.pub-date")
-            dt = None
-            if date_node:
-                # Try datetime attribute first
-                dt_attr = date_node.get("datetime")
-                if dt_attr:
-                    try:
-                        dt = date_parser.parse(dt_attr)
-                    except:
-                        pass
-                
-                # Try text content fallback
-                if dt is None:
-                    try:
-                        d_text = date_node.get_text(strip=True)
-                        # Replace JP chars
-                        d_text = d_text.replace("年", "/").replace("月", "/").replace("日", "").replace(".", "/")
-                        parsed_dt = date_parser.parse(d_text)
-                        dt = parsed_dt.replace(hour=0, minute=0, second=0, microsecond=0)
-                    except:
-                        pass
-
-            if dt is None:
-                continue
-            
-            if not is_within_period(dt):
-                continue
-            
-            summary = fetch_page_summary(link)
-            if len(summary) >= 200: summary += "..."
-
-            news_list.append({
-                "source": "Nissan",
-                "title": clean_text(title),
-                "url": link,
-                "date": dt,
-                "summary": summary
-            })
-        return news_list
-    except Exception as e:
-        print(f"Error fetching Nissan: {e}")
-        return[]
-
-
-# --- Main Coordinator ---
-
-def collect_news():
-    """
-    Collects news from all sources in parallel.
-    Returns: List of dictionaries sorted by date (newest first).
-    """
-    sources =
-    
-    all_news =[]
-    
-    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
-        future_map = {}
-        for name, url, method in sources:
-            if method == "rss":
-                future = executor.submit(fetch_rss, url, name)
-            elif method == "daihatsu":
-                future = executor.submit(fetch_daihatsu)
-            elif method == "suzuki":
-                future = executor.submit(fetch_suzuki)
-            elif method == "mitsubishi":
-                future = executor.submit(fetch_mitsubishi)
-            elif method == "nissan":
-                future = executor.submit(fetch_nissan)
-            future_map = name
-            
-        for future in concurrent.futures.as_completed(future_map):
-            name = future_map
-            try:
-                news = future.result()
-                all_news.extend(news)
-                print(f"Fetched {len(news)} items from {name}")
-            except Exception as e:
-                print(f"Failed to collect from {name}: {e}")
-                
-    # Sort by date descending
-    def get_timestamp(n):
-        d = n
-        # Convert to naive timestamp for comparison
-        if d.tzinfo:
-            return d.timestamp()
-        else:
-            return d.timestamp()
-
-    all_news.sort(key=get_timestamp, reverse=True)
-    return all_news
-
-if __name__ == "__main__":
-    import sys
-    try:
-        if sys.stdout.encoding.lower() == 'cp932':
-            sys.stdout.reconfigure(encoding='utf-8')
-    except Exception:
-        pass
-
-    # Test run
-    items = collect_news()
-    print(f"Collected {len(items)} items (Past {FILTER_DAYS} days).")
-    for i in items:
-         try:
-            print(f"}] {i.strftime('%Y-%m-%d')} - {i}")
-         except:
-            pass
\ No newline at end of file
+import concurrent.futures
+import re
+import sys
+import time
+from datetime import datetime, timedelta, timezone
+from urllib.parse import urljoin
+
+import feedparser
+import requests
+from bs4 import BeautifulSoup
+from dateutil import parser as date_parser
+
+# User-Agent for requests
+HEADERS = {
+    "User-Agent": (
+        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
+        "AppleWebKit/537.36 (KHTML, like Gecko) "
+        "Chrome/91.0.4472.124 Safari/537.36"
+    )
+}
+
+FILTER_DAYS = 7
+
+
+RSS_SOURCES = {
+    "Toyota": [
+        "https://global.toyota/jp/newsroom/rss.xml",
+        "https://global.toyota/jp/newsroom/feed.xml",
+    ],
+    "Honda": [
+        "https://global.honda/jp/topics/rss.xml",
+        "https://global.honda/jp/newsroom/rss.xml",
+    ],
+    "Mazda": [
+        "https://newsroom.mazda.com/ja/publicity/release/rss.xml",
+        "https://newsroom.mazda.com/ja/rss/news_release.xml",
+    ],
+    "Subaru": [
+        "https://www.subaru.co.jp/press/rss.xml",
+        "https://www.subaru.co.jp/news/feed/",
+    ],
+}
+
+
+def clean_text(text):
+    if not text:
+        return ""
+    try:
+        soup = BeautifulSoup(str(text), "html.parser")
+        clean = soup.get_text(separator=" ", strip=True)
+        return " ".join(clean.split())
+    except Exception:
+        return str(text)
+
+
+def trim_summary(text, limit=200):
+    cleaned = clean_text(text)
+    if len(cleaned) <= limit:
+        return cleaned
+    return cleaned[:limit].rstrip() + "..."
+
+
+def parse_datetime_safe(value):
+    if value is None:
+        return None
+    if isinstance(value, datetime):
+        return value
+    if isinstance(value, time.struct_time):
+        try:
+            return datetime(*value[:6], tzinfo=timezone.utc)
+        except Exception:
+            return None
+
+    try:
+        return date_parser.parse(str(value))
+    except Exception:
+        return None
+
+
+def normalize_date_text(text):
+    return (
+        str(text)
+        .replace("年", "/")
+        .replace("月", "/")
+        .replace("日", "")
+        .replace(".", "/")
+    )
+
+
+def extract_entry_datetime(entry):
+    text_keys = ["published", "updated", "created", "issued", "date", "dc_date"]
+    parsed_keys = ["published_parsed", "updated_parsed", "created_parsed"]
+
+    for key in text_keys:
+        value = getattr(entry, key, None)
+        dt = parse_datetime_safe(value)
+        if dt:
+            return dt
+
+    for key in parsed_keys:
+        value = getattr(entry, key, None)
+        dt = parse_datetime_safe(value)
+        if dt:
+            return dt
+
+    return None
+
+
+def is_within_period(dt):
+    if not dt:
+        return False
+
+    try:
+        aware_dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
+        now_utc = datetime.now(timezone.utc)
+        diff = now_utc - aware_dt.astimezone(timezone.utc)
+        return timedelta(0) <= diff <= timedelta(days=FILTER_DAYS, hours=23, minutes=59)
+    except Exception as e:
+        print(f"Date check error: {e}")
+        return False
+
+
+def fetch_page_summary(url):
+    if not url:
+        return ""
+
+    try:
+        resp = requests.get(url, headers=HEADERS, timeout=8)
+        if resp.status_code != 200:
+            return ""
+
+        resp.encoding = resp.apparent_encoding
+        soup = BeautifulSoup(resp.content, "html.parser")
+
+        for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
+            tag.decompose()
+
+        container = soup.select_one("main") or soup.select_one("article") or soup
+
+        text_content = []
+        total_len = 0
+        for p in container.find_all("p"):
+            t = p.get_text(strip=True)
+            if len(t) > 20:
+                text_content.append(t)
+                total_len += len(t)
+            if total_len > 300:
+                break
+
+        return trim_summary(" ".join(text_content), limit=200)
+    except Exception:
+        return ""
+
+
+def _parse_rss_with_headers(url):
+    resp = requests.get(url, headers=HEADERS, timeout=10)
+    resp.raise_for_status()
+    return feedparser.parse(resp.content)
+
+
+def fetch_rss(url, source_name):
+    try:
+        if not url:
+            return []
+
+        feed = _parse_rss_with_headers(url)
+        news_list = []
+
+        skipped_no_date = 0
+        skipped_out_of_period = 0
+
+        for entry in feed.entries:
+            dt = extract_entry_datetime(entry)
+            if dt is None:
+                skipped_no_date += 1
+                continue
+            if not is_within_period(dt):
+                skipped_out_of_period += 1
+                continue
+
+            summary_raw = getattr(entry, "summary", "") or getattr(entry, "description", "")
+            summary = clean_text(summary_raw)
+            if len(summary) < 50:
+                detail_summary = fetch_page_summary(getattr(entry, "link", ""))
+                if detail_summary:
+                    summary = detail_summary
+
+            news_list.append(
+                {
+                    "source": source_name,
+                    "title": clean_text(getattr(entry, "title", "No Title")),
+                    "url": getattr(entry, "link", ""),
+                    "date": dt,
+                    "summary": trim_summary(summary, limit=200),
+                }
+            )
+
+        if not news_list:
+            print(
+                f"RSS had no usable items ({source_name}): "
+                f"entries={len(feed.entries)}, no_date={skipped_no_date}, out_of_period={skipped_out_of_period}"
+            )
+
+        return news_list
+    except Exception as e:
+        print(f"Error fetching RSS {source_name}: {e}")
+        return []
+
+
+def fetch_rss_with_fallback(urls, source_name):
+    for url in urls:
+        news = fetch_rss(url, source_name)
+        if news:
+            return news
+    return []
+
+
+def fetch_daihatsu():
+    url = "https://www.daihatsu.com/jp/rss.xml"
+    try:
+        resp = requests.get(url, headers=HEADERS, timeout=10)
+        resp.raise_for_status()
+        resp.encoding = resp.apparent_encoding
+
+        soup = BeautifulSoup(resp.content, "xml")
+        items = soup.find_all("item")
+        news_list = []
+
+        for item in items:
+            raw_title = item.find("title").get_text(strip=True) if item.find("title") else ""
+            link = item.find("link").get_text(strip=True) if item.find("link") else ""
+
+            dt = None
+            date_match = re.match(r"(\d{4}-\d{2}-\d{2})\s*", raw_title)
+            if date_match:
+                dt = parse_datetime_safe(date_match.group(1))
+
+            if dt is None or not is_within_period(dt):
+                continue
+
+            clean_title = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", raw_title) or raw_title
+            summary = trim_summary(fetch_page_summary(link), limit=200)
+
+            news_list.append(
+                {
+                    "source": "Daihatsu",
+                    "title": clean_text(clean_title),
+                    "url": link,
+                    "date": dt,
+                    "summary": summary,
+                }
+            )
+
+        return news_list
+    except Exception as e:
+        print(f"Error fetching Daihatsu: {e}")
+        return []
+
+
+def fetch_suzuki():
+    url = "https://www.suzuki.co.jp/release/release.xml"
+    base_url = "https://www.suzuki.co.jp"
+    try:
+        resp = requests.get(url, headers=HEADERS, timeout=10)
+        resp.raise_for_status()
+        resp.encoding = resp.apparent_encoding
+
+        soup = BeautifulSoup(resp.content, "xml")
+        items = soup.find_all("item")
+        news_list = []
+
+        for item in items:
+            title = item.find("ttl").get_text(strip=True) if item.find("ttl") else "No Title"
+            link_rel = item.find("link").get_text(strip=True) if item.find("link") else ""
+            date_str = item.find("date").get_text(strip=True) if item.find("date") else ""
+
+            dt = parse_datetime_safe(normalize_date_text(date_str))
+            if dt:
+                dt = dt.replace(hour=0, minute=0, second=0, microsecond=0)
+
+            if dt is None or not is_within_period(dt):
+                continue
+
+            full_url = urljoin(base_url, link_rel)
+            summary = trim_summary(fetch_page_summary(full_url), limit=200)
+
+            news_list.append(
+                {
+                    "source": "Suzuki",
+                    "title": clean_text(title),
+                    "url": full_url,
+                    "date": dt,
+                    "summary": summary,
+                }
+            )
+
+        return news_list
+    except Exception as e:
+        print(f"Error fetching Suzuki: {e}")
+        return []
+
+
+def fetch_mitsubishi():
+    url = "https://www.mitsubishi-motors.com/jp/newsroom/newsrelease/"
+    base_url = "https://www.mitsubishi-motors.com"
+    try:
+        resp = requests.get(url, headers=HEADERS, timeout=10)
+        resp.raise_for_status()
+        resp.encoding = resp.apparent_encoding
+        soup = BeautifulSoup(resp.content, "html.parser")
+
+        news_list = []
+        items = soup.select(
+            ".newsList li, .news-list-item, .list-news li, .c-newsList__item, "
+            ".news-release-list li, .newsrelease-list li, li.news-item"
+        )
+
+        for item in items:
+            title_node = item.select_one("a")
+            if not title_node:
+                continue
+
+            title = title_node.get_text(strip=True)
+            link = title_node.get("href")
+            if not link or link.startswith("javascript"):
+                continue
+
+            full_link = urljoin(base_url, link)
+
+            date_node = item.select_one("time, .date, .c-newsList__date, .news-date")
+            dt = None
+            if date_node:
+                dt = parse_datetime_safe(normalize_date_text(date_node.get_text(strip=True)))
+
+            if dt is None:
+                item_text = item.get_text(" ", strip=True)
+                m = re.search(r"(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})", item_text)
+                if m:
+                    dt = parse_datetime_safe(f"{m.group(1)}/{m.group(2)}/{m.group(3)}")
+
+            if dt and dt.hour == 0 and dt.minute == 0 and dt.second == 0:
+                dt = dt.replace(microsecond=0)
+
+            if dt is None or not is_within_period(dt):
+                continue
+
+            summary = trim_summary(fetch_page_summary(full_link), limit=200)
+            news_list.append(
+                {
+                    "source": "Mitsubishi Motors",
+                    "title": clean_text(title),
+                    "url": full_link,
+                    "date": dt,
+                    "summary": summary,
+                }
+            )
+
+        return news_list
+    except Exception as e:
+        print(f"Error fetching Mitsubishi: {e}")
+        return []
+
+
+def fetch_nissan():
+    url = "https://global.nissannews.com/ja-JP/channels/news"
+    base_domain = "https://global.nissannews.com"
+    try:
+        resp = requests.get(url, headers=HEADERS, timeout=10)
+        resp.raise_for_status()
+        soup = BeautifulSoup(resp.content, "html.parser")
+
+        items = soup.select("div.release-item")
+        news_list = []
+
+        for item in items:
+            title_node = item.select_one("div.title a")
+            if not title_node:
+                continue
+
+            title = title_node.get_text(strip=True)
+            link = title_node.get("href")
+            if not link:
+                continue
+
+            full_url = urljoin(base_domain, link)
+
+            date_node = item.select_one("time.pub-date")
+            dt = None
+            if date_node:
+                dt_attr = date_node.get("datetime")
+                dt = parse_datetime_safe(dt_attr)
+                if dt is None:
+                    dt = parse_datetime_safe(normalize_date_text(date_node.get_text(strip=True)))
+
+            if dt is None or not is_within_period(dt):
+                continue
+
+            summary = trim_summary(fetch_page_summary(full_url), limit=200)
+            news_list.append(
+                {
+                    "source": "Nissan",
+                    "title": clean_text(title),
+                    "url": full_url,
+                    "date": dt,
+                    "summary": summary,
+                }
+            )
+
+        return news_list
+    except Exception as e:
+        print(f"Error fetching Nissan: {e}")
+        return []
+
+
+def collect_news():
+    sources = [
+        ("Toyota", RSS_SOURCES["Toyota"], "rss_multi"),
+        ("Honda", RSS_SOURCES["Honda"], "rss_multi"),
+        ("Mazda", RSS_SOURCES["Mazda"], "rss_multi"),
+        ("Subaru", RSS_SOURCES["Subaru"], "rss_multi"),
+        ("Daihatsu", "", "daihatsu"),
+        ("Suzuki", "", "suzuki"),
+        ("Mitsubishi Motors", "", "mitsubishi"),
+        ("Nissan", "", "nissan"),
+    ]
+
+    all_news = []
+
+    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
+        future_map = {}
+        for name, data, method in sources:
+            if method == "rss_multi":
+                future = executor.submit(fetch_rss_with_fallback, data, name)
+            elif method == "daihatsu":
+                future = executor.submit(fetch_daihatsu)
+            elif method == "suzuki":
+                future = executor.submit(fetch_suzuki)
+            elif method == "mitsubishi":
+                future = executor.submit(fetch_mitsubishi)
+            elif method == "nissan":
+                future = executor.submit(fetch_nissan)
+            else:
+                continue
+
+            future_map[future] = name
+
+        for future in concurrent.futures.as_completed(future_map):
+            name = future_map[future]
+            try:
+                news = future.result()
+                all_news.extend(news)
+                print(f"Fetched {len(news)} items from {name}")
+            except Exception as e:
+                print(f"Failed to collect from {name}: {e}")
+
+    all_news.sort(key=lambda item: item.get("date").timestamp() if item.get("date") else 0, reverse=True)
+    return all_news
+
+
+if __name__ == "__main__":
+    try:
+        if sys.stdout.encoding and sys.stdout.encoding.lower() == "cp932":
+            sys.stdout.reconfigure(encoding="utf-8")
+    except Exception:
+        pass
+
+    items = collect_news()
+    print(f"Collected {len(items)} items (Past {FILTER_DAYS} days).")
+    for item in items:
+        try:
+            print(f"[{item['source']}] {item['date'].strftime('%Y-%m-%d')} - {item['title']}")
+        except Exception:
+            pass
 
EOF
)
