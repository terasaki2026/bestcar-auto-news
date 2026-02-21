import json
import os
from datetime import datetime, timezone, timedelta

DATA_FILE = "news_data.json"
HISTORY_FILE = "fetch_history.json"
MAX_NEWS = 200
MAX_HISTORY = 10

JST = timezone(timedelta(hours=9))

def serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")

def deserialize_news(item):
    if "date" in item and isinstance(item["date"], str):
        try:
            item["date"] = datetime.fromisoformat(item["date"])
        except ValueError:
            pass
    return item

def load_news():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [deserialize_news(item) for item in data]
    except Exception:
        return []

def save_news(news_list):
    # Sort and take top 200
    news_list.sort(key=lambda x: x.get("date").timestamp() if x.get("date") else 0, reverse=True)
    to_save = news_list[:MAX_NEWS]
    
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(to_save, f, ensure_ascii=False, indent=2, default=serialize_datetime)
    except Exception as e:
        print(f"Error saving news: {e}")

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_history(timestamp_str):
    history = load_history()
    history.insert(0, timestamp_str)
    history = history[:MAX_HISTORY]
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving history: {e}")

def merge_news(old_news, new_news):
    # Use URL as unique key
    seen_urls = set()
    merged = []
    
    # New news first to preserve order if timestamps are same
    for item in new_news + old_news:
        url = item.get("url")
        if url and url not in seen_urls:
            merged.append(item)
            seen_urls.add(url)
            
    merged.sort(key=lambda x: x.get("date").timestamp() if x.get("date") else 0, reverse=True)
    return merged[:MAX_NEWS]
