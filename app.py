-import streamlit as st
-import pandas as pd
-from datetime import datetime
-import time
-from collectors import collect_news
-
-# Page Config
-st.set_page_config(
-    page_title="BestCar Auto News",
-    page_icon="🚗",
-    layout="wide",
-    initial_sidebar_state="expanded"
-)
-
-# --- Simple Authentication ---
-# Secrets（Streamlit Cloud）またはデフォルト値を使用
-try:
-    VALID_ID = st.secrets["credentials"]["user_id"]
-    VALID_PW = st.secrets["credentials"]["password"]
-except Exception:
-    # ローカル実行時のフォールバック
-    VALID_ID = "bestcar"
-    VALID_PW = "bestcar2026"
-
-if "authenticated" not in st.session_state:
-    st.session_state["authenticated"] = False
-
-if not st.session_state["authenticated"]:
-    col1, col2, col3 = st.columns([1, 2, 1])
-    with col2:
-        st.title("🔒 Login to BestCar Auto News")
-        with st.form("login_form"):
-            st.caption("関係者専用アクセス")
-            user_id = st.text_input("ID")
-            password = st.text_input("Password", type="password")
-            submitted = st.form_submit_button("Login")
-            
-            if submitted:
-                if user_id == VALID_ID and password == VALID_PW:
-                    st.session_state["authenticated"] = True
-                    st.rerun()
-                else:
-                    st.error("IDまたはパスワードが間違っています")
-    
-    if not st.session_state["authenticated"]:
-        st.stop()
-
-# Custom CSS for Cards
-st.markdown("""
-<style>
-    .news-card {
-        background-color: #ffffff;
-        border-radius: 12px;
-        padding: 20px;
-        margin-bottom: 20px;
-        box_shadow: 0 4px 6px rgba(0,0,0,0.1);
-        transition: transform 0.2s;
-        border: 1px solid #f0f0f0;
-    }
-    .news-card:hover {
-        transform: translateY(-2px);
-        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
-    }
-    .news-source {
-        font-size: 0.8rem;
-        color: #666;
-        font_weight: 600;
-        text-transform: uppercase;
-        margin-bottom: 5px;
-        display: inline-block;
-        padding: 2px 8px;
-        background-color: #f5f5f5;
-        border-radius: 4px;
-    }
-    .news-date {
-        font-size: 0.8rem;
-        color: #999;
-        float: right;
-    }
-    .news-title {
-        font-size: 1.2rem;
-        font-weight: 700;
-        margin: 10px 0;
-        color: #333;
-        line-height: 1.4;
-    }
-    .news-title a {
-        text-decoration: none;
-        color: #333;
-    }
-    .news-title a:hover {
-        color: #e63946;
-    }
-    .news-summary {
-        font-size: 0.95rem;
-        color: #555;
-        margin-bottom: 15px;
-        line-height: 1.5;
-    }
-    .read-more-btn {
-        display: inline-block;
-        padding: 8px 16px;
-        background-color: #e63946;
-        color: white !important;
-        text-decoration: none;
-        border-radius: 6px;
-        font-size: 0.9rem;
-        transition: background-color 0.2s;
-    }
-    .read-more-btn:hover {
-        background-color: #d62828;
-    }
-    /* Dark mode adjustments */
-    @media (prefers-color-scheme: dark) {
-        .news-card {
-            background-color: #262730;
-            border-color: #333;
-        }
-        .news-title {
-            color: #fff;
-        }
-        .news-title a {
-            color: #fff;
-        }
-        .news-summary {
-            color: #ddd;
-        }
-        .news-source {
-            background-color: #333;
-            color: #ccc;
-        }
-    }
-</style>
-""", unsafe_allow_html=True)
-
-# Data Loading with Cache
-@st.cache_data(ttl=600, show_spinner=False)
-def load_data():
-    return collect_news()
-
-# Header
-st.title("🚗 BestCar Auto News (仮)")
-st.markdown("自動車メーカー各社の最新ニュースをまとめてチェックできるダッシュボード")
-
-# Load Data
-with st.spinner("ニュースを取得中..."):
-    news_items = load_data()
-
-if not news_items:
-    st.warning("ニュースを取得できませんでした。ネットワーク接続を確認するか、しばらく待ってから再読み込みしてください。")
-    st.stop()
-
-# Sidebar Filters
-st.sidebar.header("フィルタ設定")
-
-# Source Filter
-all_sources = sorted(list(set(item['source'] for item in news_items)))
-selected_sources = st.sidebar.multiselect(
-    "ソース選択",
-    options=all_sources,
-    default=all_sources
-)
-
-# Keyword Search
-search_query = st.sidebar.text_input("キーワード検索", placeholder="例: EV, SUV...")
-
-# Manual Refresh
-if st.sidebar.button("データを手動更新"):
-    st.cache_data.clear()
-    st.rerun()
-
-# Last Updated
-st.sidebar.markdown("---")
-st.sidebar.caption(f"最終更新: {datetime.now().strftime('%Y/%m/%d %H:%M')}")
-
-# Filter Logic
-filtered_items = []
-for item in news_items:
-    # Source check
-    if item['source'] not in selected_sources:
-        continue
-    
-    # Search query check
-    if search_query:
-        query = search_query.lower()
-        if (query not in item['title'].lower()) and (query not in item['summary'].lower()):
-            continue
-            
-    filtered_items.append(item)
-
-# Display Stats
-st.caption(f"表示件数: {len(filtered_items)} / 全 {len(news_items)} 件")
-
-
-# Display Loop
-for item in filtered_items:
-    date_str = item['date'].strftime('%Y/%m/%d')
-    
-    # HTML Card Construction
-    summary_html = f'<div class="news-summary">{item["summary"]}</div>' if item["summary"] else ""
-    
-    
-    # HTML Card Construction
-    summary_html = f'<div class="news-summary">{item["summary"]}</div>' if item["summary"] else ""
-    
-
-    # HTML Card Construction
-    source_html = f'<span class="news-source">{item["source"]}</span>'
-    date_html = f'<span class="news-date">{date_str}</span>'
-    title_html = f'<div class="news-title"><a href="{item["url"]}" target="_blank">{item["title"]}</a></div>'
-    summary_html = f'<div class="news-summary">{item["summary"]}</div>' if item["summary"] else ""
-    link_html = f'<a href="{item["url"]}" target="_blank" class="read-more-btn">元記事を読む →</a>'
-
-    card_html = f"""<div class="news-card"><div>{source_html}{date_html}</div>{title_html}{summary_html}{link_html}</div>"""
-    st.markdown(card_html, unsafe_allow_html=True)
-
-# Footer
-st.markdown("---")
-st.markdown("© 2026 BestCar Web Subsite Project")
+import streamlit as st
+from datetime import datetime
+from collections import Counter
+
+from collectors import collect_news
+
+st.set_page_config(
+    page_title="BestCar Auto News",
+    page_icon="🚗",
+    layout="wide",
+    initial_sidebar_state="expanded",
+)
+
+EXPECTED_SOURCES = [
+    "Toyota",
+    "Honda",
+    "Mazda",
+    "Subaru",
+    "Daihatsu",
+    "Suzuki",
+    "Mitsubishi Motors",
+    "Nissan",
+]
+
+try:
+    VALID_ID = st.secrets["credentials"]["user_id"]
+    VALID_PW = st.secrets["credentials"]["password"]
+except Exception:
+    VALID_ID = "bestcar"
+    VALID_PW = "bestcar2026"
+
+if "authenticated" not in st.session_state:
+    st.session_state["authenticated"] = False
+
+if not st.session_state["authenticated"]:
+    col1, col2, col3 = st.columns([1, 2, 1])
+    with col2:
+        st.title("🔒 Login to BestCar Auto News")
+        with st.form("login_form"):
+            st.caption("関係者専用アクセス")
+            user_id = st.text_input("ID")
+            password = st.text_input("Password", type="password")
+            submitted = st.form_submit_button("Login")
+
+            if submitted:
+                if user_id == VALID_ID and password == VALID_PW:
+                    st.session_state["authenticated"] = True
+                    st.rerun()
+                else:
+                    st.error("IDまたはパスワードが間違っています")
+
+    if not st.session_state["authenticated"]:
+        st.stop()
+
+st.markdown(
+    """
+<style>
+    .news-card {
+        background-color: #ffffff;
+        border-radius: 12px;
+        padding: 20px;
+        margin-bottom: 20px;
+        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
+        transition: transform 0.2s;
+        border: 1px solid #f0f0f0;
+    }
+    .news-card:hover {
+        transform: translateY(-2px);
+        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
+    }
+    .news-source {
+        font-size: 0.8rem;
+        color: #666;
+        font-weight: 600;
+        text-transform: uppercase;
+        margin-bottom: 5px;
+        display: inline-block;
+        padding: 2px 8px;
+        background-color: #f5f5f5;
+        border-radius: 4px;
+    }
+    .news-date {
+        font-size: 0.8rem;
+        color: #999;
+        float: right;
+    }
+    .news-title {
+        font-size: 1.2rem;
+        font-weight: 700;
+        margin: 10px 0;
+        color: #333;
+        line-height: 1.4;
+    }
+    .news-title a {
+        text-decoration: none;
+        color: #333;
+    }
+    .news-title a:hover {
+        color: #e63946;
+    }
+    .news-summary {
+        font-size: 0.95rem;
+        color: #555;
+        margin-bottom: 15px;
+        line-height: 1.5;
+    }
+    .read-more-btn {
+        display: inline-block;
+        padding: 8px 16px;
+        background-color: #e63946;
+        color: white !important;
+        text-decoration: none;
+        border-radius: 6px;
+        font-size: 0.9rem;
+        transition: background-color 0.2s;
+    }
+    .read-more-btn:hover {
+        background-color: #d62828;
+    }
+</style>
+""",
+    unsafe_allow_html=True,
+)
+
+
+@st.cache_data(ttl=600, show_spinner=False)
+def load_data():
+    return collect_news()
+
+
+st.title("🚗 BestCar Auto News (仮)")
+st.markdown("自動車メーカー各社の最新ニュースをまとめてチェックできるダッシュボード")
+
+with st.spinner("ニュースを取得中..."):
+    news_items = load_data()
+
+if not news_items:
+    st.warning("ニュースを取得できませんでした。ネットワーク接続を確認するか、しばらく待ってから再読み込みしてください。")
+    st.stop()
+
+source_counts = Counter(item.get("source", "Unknown") for item in news_items)
+
+st.sidebar.header("フィルタ設定")
+
+all_sources = sorted(set(item["source"] for item in news_items))
+selected_sources = st.sidebar.multiselect("ソース選択", options=all_sources, default=all_sources)
+search_query = st.sidebar.text_input("キーワード検索", placeholder="例: EV, SUV...")
+
+if st.sidebar.button("データを手動更新"):
+    st.cache_data.clear()
+    st.rerun()
+
+st.sidebar.markdown("---")
+st.sidebar.subheader("ソース別取得件数")
+for source in EXPECTED_SOURCES:
+    total = source_counts.get(source, 0)
+    label = "🟢" if total > 0 else "🔴"
+    st.sidebar.write(f"{label} {source}: {total}件")
+
+zero_sources = [s for s in EXPECTED_SOURCES if source_counts.get(s, 0) == 0]
+if zero_sources:
+    st.sidebar.warning("0件のソース: " + ", ".join(zero_sources))
+
+st.sidebar.caption(f"最終更新: {datetime.now().strftime('%Y/%m/%d %H:%M')}")
+
+filtered_items = []
+for item in news_items:
+    if item["source"] not in selected_sources:
+        continue
+
+    if search_query:
+        query = search_query.lower()
+        if query not in item["title"].lower() and query not in item["summary"].lower():
+            continue
+
+    filtered_items.append(item)
+
+filtered_counts = Counter(item.get("source", "Unknown") for item in filtered_items)
+st.caption(f"表示件数: {len(filtered_items)} / 取得件数: {len(news_items)}")
+
+with st.expander("表示件数（フィルタ後）"):
+    for source in EXPECTED_SOURCES:
+        st.write(f"{source}: {filtered_counts.get(source, 0)}件")
+
+for item in filtered_items:
+    date_str = item["date"].strftime("%Y/%m/%d")
+    source_html = f'<span class="news-source">{item["source"]}</span>'
+    date_html = f'<span class="news-date">{date_str}</span>'
+    title_html = f'<div class="news-title"><a href="{item["url"]}" target="_blank">{item["title"]}</a></div>'
+    summary_html = f'<div class="news-summary">{item["summary"]}</div>' if item["summary"] else ""
+    link_html = f'<a href="{item["url"]}" target="_blank" class="read-more-btn">元記事を読む →</a>'
+
+    card_html = f"""
+    <div class="news-card">
+      <div>{source_html}{date_html}</div>
+      {title_html}
+      {summary_html}
+      {link_html}
+    </div>
+    """
+    st.markdown(card_html, unsafe_allow_html=True)
+
+st.markdown("---")
+st.markdown("© 2026 BestCar Web Subsite Project")
 
EOF
)
