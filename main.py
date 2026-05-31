import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib.pyplot as plt
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
# 2. 爬蟲函數：搜尋產品 (✨ 新增功能 ✨)
# ==========================================
@st.cache_data(ttl=3600)
def search_cosme_products(keyword):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    # 組合 @cosme 的搜尋網址
    url = f"https://www.cosme.net.tw/search/product?keyword={keyword}"
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    products = []
    seen_ids = set()

    # 尋找搜尋結果中所有指向產品頁面的超連結
    for a in soup.find_all('a', href=True):
        href = a['href']
        # 尋找連結中符合 /products/數字 的格式
        match = re.search(r'products/(\d+)$', href)

        if match:
            product_id = match.group(1)
            # 清理文字：將多個換行或空白取代為單一空白，確保選單顯示整齊
            name = re.sub(r'\s+', ' ', a.text.strip())

            # 過濾掉沒有文字的圖片連結，並避免重複加入同一個商品
            if product_id not in seen_ids and len(name) > 2:
                # 擷取前 50 個字作為顯示名稱，避免抓到過長的無用敘述
                display_name = name if len(name) < 50 else name[:50] + "..."
                products.append({
                    "id": product_id,
                    "name": display_name
                })
                seen_ids.add(product_id)

    return products

# ==========================================
# 3. 核心分析區塊 (打包成函數，方便不同模式呼叫)
# ==========================================
# ==========================================
# 3. 核心分析區塊 (進階版：蜜糖與毒藥分流)
# ==========================================
# ==========================================
# 3. 核心分析區塊 (上下排列版)
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
        # 因為改成上下排列，高度可以稍微調低一點，避免佔用太多版面
        st.dataframe(df, use_container_width=True, height=400)

        st.divider()  # 加上分隔線，讓視覺更舒服

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

            # 蜜糖邏輯：只看 4 星以上的正面評價
            if rating >= 4:
                for kw in pros_keywords:
                    if kw in content:
                        pros_counts[kw] += 1

            # 毒藥邏輯：只看 3 星以下的負面評價
            if rating <= 3:
                for kw in cons_keywords:
                    if kw in content and f"不{kw}" not in content and f"沒長{kw}" not in content and f"不會{kw}" not in content:
                        cons_counts[kw] += 1

        # 3. 過濾掉次數為 0 的字，並由大到小排序
        pros_filtered = {k: v for k, v in sorted(pros_counts.items(), key=lambda item: item[1], reverse=True) if v > 0}
        cons_filtered = {k: v for k, v in sorted(cons_counts.items(), key=lambda item: item[1], reverse=True) if v > 0}

        # 設定圖表字體 (Windows 用戶請將 'Arial Unicode MS' 改為 'Microsoft JhengHei')
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS']
        plt.rcParams['axes.unicode_minus'] = False

        # --- 畫圖：蜜糖榜單 ---
        st.markdown("#### 💖 優點 (最常提及)")
        if pros_filtered:
            # 調整圖表大小，寬度拉長一點
            fig1, ax1 = plt.subplots(figsize=(8, 4))
            y_pos = list(pros_filtered.keys())[::-1]
            x_vals = list(pros_filtered.values())[::-1]

            bars1 = ax1.barh(y_pos, x_vals, color='#ffb3ba')
            ax1.set_xlabel('提及次數')

            for i, v in enumerate(x_vals):
                ax1.text(v + 0.1, i, str(v), va='center')

            st.pyplot(fig1)
        else:
            st.info("這款產品目前抓取的好評中，沒有對應到優點的關鍵字。")

        st.divider()

        # --- 畫圖：毒藥榜單 ---
        st.markdown("#### ☠️ 負評 (最常提及)")
        if cons_filtered:
            fig2, ax2 = plt.subplots(figsize=(8, 4))
            y_pos2 = list(cons_filtered.keys())[::-1]
            x_vals2 = list(cons_filtered.values())[::-1]

            bars2 = ax2.barh(y_pos2, x_vals2, color='#b3cde0')
            ax2.set_xlabel('提及次數')

            for i, v in enumerate(x_vals2):
                ax2.text(v + 0.1, i, str(v), va='center')

            st.pyplot(fig2)
        else:
            st.success("這款產品目前抓取的負評中，沒有對應到任何缺點的關鍵字。")

# ==========================================
# 4. Streamlit 網頁介面設計
# ==========================================
st.set_page_config(page_title="@cosme 美妝數據聲量統計分析", layout="wide")
st.title("💄 @cosme 美妝數據聲量統計分析")
st.markdown("搜尋產品或輸入網址，自動抓取評論並分析。")

# 使用分頁 (Tabs) 讓介面看起來更專業
tab1, tab2 = st.tabs(["🔍 關鍵字搜尋產品", "🔗 直接輸入產品網址"])

# --- 第一頁：搜尋模式 ---
with tab1:
    keyword = st.text_input("請輸入美妝產品名稱（例如：雅詩蘭黛 粉底液）：")

    if keyword:
        with st.spinner("正在搜尋相關產品..."):
            search_results = search_cosme_products(keyword)

        if search_results:
            # 將抓到的產品清單轉換為下拉式選單的選項格式
            options = {f"{p['name']} (ID: {p['id']})": p['id'] for p in search_results}

            # 讓使用者透過下拉選單選擇
            selected_option = st.selectbox("請選擇目標產品：", list(options.keys()))

            # 加入一個按鈕，點擊後才開始爬蟲，避免每次選單切換就直接跑分析
            if st.button("開始分析此產品", type="primary"):
                target_id = options[selected_option]
                run_analysis(target_id)
        else:
            st.warning("找不到相關產品，請嘗試縮短關鍵字或換個說法。")

# --- 第二頁：網址模式 ---
with tab2:
    target_url = st.text_input("請輸入 @cosme 產品頁面網址：", "https://www.cosme.net.tw/products/104761")
    if target_url:
        if st.button("開始爬蟲此網址", type="primary"):
            match = re.search(r'products/(\d+)', target_url)
            if not match:
                st.warning("⚠️ 請輸入有效的 @cosme 產品網址（需包含 products/商品編號）")
            else:
                run_analysis(match.group(1))