import streamlit as st
from datetime import datetime, timedelta, timezone
from collections import Counter
from collectors import collect_news
from data_manager import load_news, save_news, load_history, save_history, merge_news

# 日本標準時 (JST) の定義
JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="BestCar Auto News",
    page_icon="🚗",
    layout="wide",
)

EXPECTED_SOURCES = ["Toyota", "Honda", "Mazda", "Subaru", "Daihatsu", "Suzuki", "Mitsubishi Motors", "Nissan"]

try:
    VALID_ID = st.secrets["credentials"]["user_id"]
    VALID_PW = st.secrets["credentials"]["password"]
except Exception:
    VALID_ID = "bestcar"
    VALID_PW = "bestcar2026"

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Login")
        with st.form("login_form"):
            user_id = st.text_input("ID")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                if user_id == VALID_ID and password == VALID_PW:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Invalid ID or Password")
    st.stop()

# セッション状態の初期化
if "display_count" not in st.session_state:
    st.session_state["display_count"] = 20

st.markdown("""
<style>
    .news-card { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #eee; }
    .news-source { font-size: 0.75rem; color: #666; font-weight: 700; background: #f0f0f0; padding: 2px 8px; border-radius: 4px; }
    .news-date { font-size: 0.8rem; color: #999; float: right; }
    .news-title { font-size: 1.15rem; font-weight: 700; margin: 10px 0; }
    .news-title a { text-decoration: none; color: #333; }
    .news-summary { font-size: 0.9rem; color: #555; line-height: 1.6; }
    .read-more { font-size: 0.85rem; color: #e63946; font-weight: 600; text-decoration: none; }
    .more-button-container { display: flex; justify-content: center; margin: 30px 0; }
</style>
""", unsafe_allow_html=True)

# データの読み込み
news_items = load_news()
fetch_history = load_history()

st.title("🚗 BestCar Auto News")

# ニュース取得関数
def refresh_news():
    with st.spinner("最新ニュースを取得中..."):
        try:
            new_items = collect_news()
            current_news = load_news()
            merged = merge_news(current_news, new_items)
            save_news(merged)
            
            # 更新履歴の保存（チェックした時刻として記録）
            now_str = datetime.now(JST).strftime("%Y/%m/%d %H:%M:%S")
            save_history(now_str)
            return True
        except Exception as e:
            st.error(f"取得中にエラーが発生しました: {e}")
            return False

# 初回起動時などでデータがない場合はメッセージ表示（自動取得はしない）
if not news_items:
    st.info("⏳ まだニュースがありません。左のサイドバーにある「🔄 最新ニュースに更新」ボタンを押してニュースを取得してください。")

source_counts = Counter(item.get("source", "Unknown") for item in news_items)

st.sidebar.header("📊 ニュース管理")

# 更新ボタン
if st.sidebar.button("🔄 最新ニュースに更新", use_container_width=True):
    if refresh_news():
        st.session_state["display_count"] = 20  # 更新時は表示件数をリセット
        st.rerun()

# 更新履歴の表示
st.sidebar.markdown("---")
st.sidebar.subheader("🕒 更新履歴 (最新10件)")
if fetch_history:
    for idx, ts in enumerate(fetch_history):
        if idx == 0:
            st.sidebar.caption(f"**前回: {ts}**")
        else:
            st.sidebar.caption(f"{ts}")
else:
    st.sidebar.caption("履歴なし")

st.sidebar.markdown("---")
st.sidebar.header("🔍 フィルタ設定")

all_sources = sorted(set(item["source"] for item in news_items)) if news_items else EXPECTED_SOURCES
selected_sources = st.sidebar.multiselect("メーカー選択", options=all_sources, default=all_sources)
search_query = st.sidebar.text_input("キーワード検索", placeholder="例: EV, SUV...")

st.sidebar.markdown("---")
st.sidebar.subheader("ソース別取得件数")
for source in EXPECTED_SOURCES:
    count = source_counts.get(source, 0)
    label = "🟢" if count > 0 else "🔴"
    st.sidebar.write(f"{label} {source}: {count}件")

# フィルタリング
filtered_items = []
for item in news_items:
    if item["source"] not in selected_sources:
        continue
    if search_query:
        query = search_query.lower()
        if query not in item["title"].lower() and query not in item.get("summary", "").lower():
            continue
    filtered_items.append(item)

st.caption(f"表示中: {min(len(filtered_items), st.session_state['display_count'])} / フィルタ後件数: {len(filtered_items)} / 総保存件数: {len(news_items)}")

# ニュースの表示（表示件数制限）
displayed_items = filtered_items[:st.session_state["display_count"]]

for item in displayed_items:
    try:
        date_str = item["date"].strftime("%Y/%m/%d")
    except Exception:
        date_str = str(item["date"])
        
    st.markdown(f"""
    <div class="news-card">
        <div><span class="news-source">{item['source']}</span><span class="news-date">{date_str}</span></div>
        <div class="news-title"><a href="{item['url']}" target="_blank">{item['title']}</a></div>
        <div class="news-summary">{item['summary']}</div>
        <a href="{item['url']}" target="_blank" class="read-more">元記事を読む →</a>
    </div>
    """, unsafe_allow_html=True)

# 「もっと読む」ボタン
if len(filtered_items) > st.session_state["display_count"]:
    st.markdown('<div class="more-button-container">', unsafe_allow_html=True)
    if st.button("もっと読む", type="primary"):
        st.session_state["display_count"] += 20
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
st.markdown("© 2026 BestCar Auto News Project")