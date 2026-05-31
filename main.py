import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import plotly.express as px  # 改用 plotly.express
import time
import re


# ==========================================
# 1. 爬蟲函數：抓取商品評論
# ==========================================
@st.cache_data(ttl=3600)
def scrape_cosme_reviews(product_id, max_pages=10):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    all_reviews_data = []

    for page in range(1, max_pages + 1):
        url = f"https://www.cosme.net.tw/products/{product_id}/reviews?page={page}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            break

        soup = BeautifulSoup(response.text, 'html.parser')
        review_blocks = soup.select('.uc-review.seo-review-with-title')

        if len(review_blocks) == 0:
            break

        for block in review_blocks:
            try:
                rating_tag = block.select_one('.review-score')
                rating = int(rating_tag.text.strip()) if rating_tag else 0

                content_tag = block.select_one('.three-line-dot.uc-content-link')
                content = content_tag.text.strip() if content_tag else ""

                all_reviews_data.append({
                    "rating": rating,
                    "content": content
                })
            except Exception:
                continue

        time.sleep(1)

    return all_reviews_data


# ==========================================
# 2. 爬蟲函數：搜尋產品
# ==========================================
@st.cache_data(ttl=3600)
def search_cosme_products(keyword):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    url = f"https://www.cosme.net.tw/search/product?keyword={keyword}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = []
    seen_ids = set()

    for a in soup.find_all('a', href=True):
        href = a['href']
        match = re.search(r'products/(\d+)$', href)

        if match:
            product_id = match.group(1)
            name = re.sub(r'\s+', ' ', a.text.strip())

            if product_id not in seen_ids and len(name) > 2:
                display_name = name if len(name) < 50 else name[:50] + "..."
                products.append({
                    "id": product_id,
                    "name": display_name
                })
                seen_ids.add(product_id)

    return products

# ==========================================
# 3. 核心分析區塊 (改用 Plotly 互動式圖表)
# ==========================================
# ==========================================
# 3. 核心分析區塊 (改用 Plotly 互動式圖表 - 移除小數點版)
# ==========================================
def run_analysis(product_id):
    with st.spinner(f'正在抓取商品 {product_id} 的資料，請稍候...'):
        results = scrape_cosme_reviews(product_id, max_pages=3)

        if not results:
            st.error("無法抓取資料，可能是該商品沒有心得或網站結構改變。")
            return

        st.success(f"✅ 成功抓取 {len(results)} 筆評論！")
        df = pd.DataFrame(results)

        # --- 第一區塊：原始資料表格 (在上) ---
        st.subheader("📋 原始評論資料")
        st.dataframe(df, use_container_width=True, height=400)

        st.divider()

        # --- 第二區塊：圖表分析 (在下) ---
        st.subheader("📊 優點 vs 缺點")

        # 1. 擴充並分類關鍵字庫
        pros_keywords = ['保濕', '服貼', '提亮', '遮瑕', '清爽', '持久', '控油', '自然', '好推', '透亮', '好吸收',
                         '溫和', '光澤', '不脫妝']
        cons_keywords = ['黏膩', '痘痘', '粉刺', '脫妝', '暗沉', '乾', '浮粉', '厚重', '斑駁', '過敏', '卡粉', '起屑',
                         '致痘']

        pros_counts = {kw: 0 for kw in pros_keywords}
        cons_counts = {kw: 0 for kw in cons_keywords}

        # 2. 結合星等與「簡單語意排除」來精準計數
        for index, row in df.iterrows():
            content = row['content']
            rating = row['rating']

            if rating >= 4:
                for kw in pros_keywords:
                    if kw in content:
                        pros_counts[kw] += 1

            if rating <= 3:
                for kw in cons_keywords:
                    if kw in content and f"不{kw}" not in content and f"沒長{kw}" not in content and f"不會{kw}" not in content:
                        cons_counts[kw] += 1

        # 3. 過濾掉次數為 0 的字，並由大到小排序
        pros_filtered = {k: v for k, v in sorted(pros_counts.items(), key=lambda item: item[1], reverse=True) if v > 0}
        cons_filtered = {k: v for k, v in sorted(cons_counts.items(), key=lambda item: item[1], reverse=True) if v > 0}

        # --- 畫圖：優點榜單 (Plotly) ---
        st.markdown("#### 💖 優點 (最常提及)")
        if pros_filtered:
            y_pos = list(pros_filtered.keys())[::-1]
            x_vals = list(pros_filtered.values())[::-1]

            fig1 = px.bar(
                x=x_vals,
                y=y_pos,
                orientation='h',
                text=x_vals,
                labels={'x': '提及次數', 'y': '討論特徵'}
            )

            fig1.update_traces(marker_color='#ffb3ba', textposition='outside')
            fig1.update_layout(
                height=350,
                margin=dict(l=0, r=20, t=20, b=0),
                xaxis_title=None,
                yaxis_title=None
            )
            # ✨ 新增：強制 X 軸為整數，且刻度間距為 1
            fig1.update_xaxes(tickformat="d", dtick=1)

            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.info("這款產品目前抓取的好評中，沒有對應到優點的關鍵字。")

        st.divider()

        # --- 畫圖：缺點榜單 (Plotly) ---
        st.markdown("#### ☠️ 負評 (最常提及)")
        if cons_filtered:
            y_pos2 = list(cons_filtered.keys())[::-1]
            x_vals2 = list(cons_filtered.values())[::-1]

            fig2 = px.bar(
                x=x_vals2,
                y=y_pos2,
                orientation='h',
                text=x_vals2,
                labels={'x': '提及次數', 'y': '討論特徵'}
            )

            fig2.update_traces(marker_color='#b3cde0', textposition='outside')
            fig2.update_layout(
                height=350,
                margin=dict(l=0, r=20, t=20, b=0),
                xaxis_title=None,
                yaxis_title=None
            )
            # ✨ 新增：強制 X 軸為整數，且刻度間距為 1
            fig2.update_xaxes(tickformat="d", dtick=1)

            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.success("這款產品目前抓取的負評中，沒有對應到任何缺點的關鍵字。")


# ==========================================
# 4. Streamlit 網頁介面設計
# ==========================================
st.set_page_config(page_title="@cosme 美妝數據聲量統計分析", layout="wide")
st.title("💄 @cosme 美妝數據聲量統計分析")
st.markdown("搜尋產品或輸入網址，自動抓取評論並分析。")

tab1, tab2 = st.tabs(["🔍 關鍵字搜尋產品", "🔗 直接輸入產品網址"])

with tab1:
    keyword = st.text_input("請輸入美妝產品名稱（例如：雅詩蘭黛 粉底液）：")

    if keyword:
        with st.spinner("正在搜尋相關產品..."):
            search_results = search_cosme_products(keyword)

        if search_results:
            options = {f"{p['name']} (ID: {p['id']})": p['id'] for p in search_results}
            selected_option = st.selectbox("請選擇目標產品：", list(options.keys()))

            if st.button("開始分析此產品", type="primary"):
                target_id = options[selected_option]
                run_analysis(target_id)
        else:
            st.warning("找不到相關產品，請嘗試縮短關鍵字或換個說法。")

with tab2:
    target_url = st.text_input("請輸入 @cosme 產品頁面網址：", "https://www.cosme.net.tw/products/104761")
    if target_url:
        if st.button("開始爬蟲此網址", type="primary"):
            match = re.search(r'products/(\d+)', target_url)
            if not match:
                st.warning("⚠️ 請輸入有效的 @cosme 產品網址（需包含 products/商品編號）")
            else:
                run_analysis(match.group(1))