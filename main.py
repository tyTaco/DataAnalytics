## 成功抓取評論第一頁所有評論
import time
import random
import pandas as pd
import plotly.express as px
import streamlit as st
from bs4 import BeautifulSoup
from curl_cffi import requests

# ==============================================================================
# Streamlit 網頁基本設定 (網頁標籤 title)
# ==============================================================================
st.set_page_config(page_title="@cosme 美妝分析統計", page_icon="💄", layout="centered")

st.title("💄 @cosme 美妝數據聲量統計分析")
st.caption("本系統採用真人級 TLS 指紋隱匿技術，動態層級解析美妝輿情數據。")
st.write("---")

# ==============================================================================
# 初始化 Session State 狀態機
# ==============================================================================
if "product_list" not in st.session_state:
    st.session_state.product_list = []
if "last_search_kw" not in st.session_state:
    st.session_state.last_search_kw = ""
if "step" not in st.session_state:
    st.session_state.step = 1
# 【本次新增】建立分析結果的「硬碟級快取記憶體」，專門防止下載按鈕引發重新爬取
if "df_reviews_cache" not in st.session_state:
    st.session_state.df_reviews_cache = None
if "df_stats_cache" not in st.session_state:
    st.session_state.df_stats_cache = None


# ==============================================================================
# 核心後端功能
# ==============================================================================
def fetch_products(keyword):
    """Step 1~3: 進入網站並取得搜尋結果"""
    search_url = f"https://www.cosme.net.tw/search/product?keyword={keyword}"
    try:
        response = requests.get(search_url, impersonate="chrome", timeout=10)
        if response.status_code == 200:
            search_soup = BeautifulSoup(response.text, "html.parser")
            product_list = []
            all_links = search_soup.find_all("a", href=True)

            for item in all_links:
                href = item['href']
                text = item.get_text().strip()
                if "/products/" in href and text:
                    full_url = f"https://www.cosme.net.tw{href}" if href.startswith("/") else href
                    if "篇" in text or href.endswith("/reviews"):
                        continue
                    if len(text) > 2 and full_url not in [p['url'] for p in product_list]:
                        product_list.append({"name": text, "url": full_url})
            return product_list
    except Exception as e:
        st.error(f"連線發生錯誤：{e}")
    return []


def scan_first_page_review_urls(reviews_base_url):
    """快速精準定位並帶回第一頁主列表的所有評論網址"""
    try:
        reviews_response = requests.get(reviews_base_url, impersonate="chrome", timeout=10)
        if reviews_response.status_code != 200:
            return [], None

        reviews_soup = BeautifulSoup(reviews_response.text, "html.parser")
        review_urls = []

        main_review_area = reviews_soup.select_one(".reviews-list, .review-container, #review-list, .main-content")
        search_target = main_review_area if main_review_area else reviews_soup

        for a_tag in search_target.find_all("a", href=True):
            r_href = a_tag['href']
            if "/reviews/" in r_href and not r_href.endswith("/reviews") and not "products" in r_href:
                full_review_url = f"https://www.cosme.net.tw{r_href}" if r_href.startswith("/") else r_href
                if full_review_url not in review_urls:
                    review_urls.append(full_review_url)

        if not review_urls:
            for a_tag in reviews_soup.find_all("a", href=True):
                r_href = a_tag['href']
                if "/reviews/" in r_href and not r_href.endswith("/reviews") and not "products" in r_href:
                    full_review_url = f"https://www.cosme.net.tw{r_href}" if r_href.startswith("/") else r_href
                    if full_review_url not in review_urls:
                        review_urls.append(full_review_url)

        return review_urls, reviews_soup
    except Exception:
        return [], None


# ==============================================================================
# 一級畫面：搜尋框
# ==============================================================================
current_input = st.text_input("🔍 請輸入欲搜尋之產品名稱或品牌（輸入完請按 Enter）：", key="search_keyword")

if current_input and current_input != st.session_state.last_search_kw:
    st.session_state.product_list = []
    st.session_state.step = 1
    st.session_state.df_reviews_cache = None  # 【本次新增】換產品時，清空分析舊快取
    st.session_state.df_stats_cache = None
    if "active_product" in st.session_state:
        del st.session_state.active_product

    with st.spinner("『關鍵字變更』已重置舊數據，正在檢索新產品數據中..."):
        results = fetch_products(current_input)
        if results:
            st.session_state.product_list = results
            st.session_state.last_search_kw = current_input
            st.session_state.step = 2
            st.rerun()
        else:
            st.session_state.last_search_kw = current_input
            st.error("未能找到相關產品，請嘗試更換關鍵字。")

# ==============================================================================
# 二級畫面：產品選單
# ==============================================================================
if st.session_state.step >= 2 and st.session_state.product_list:
    st.write("### 🗂️ 請選擇目標完整產品名稱")

    prod_options = st.session_state.product_list
    dynamic_dropdown_key = f"select_{st.session_state.last_search_kw}"


    def get_display_label(prod_obj):
        prod_id = prod_obj["url"].split("/")[-1]
        return f"{prod_obj['name']}  (商品ID: {prod_id})"


    selected_prod_object = st.selectbox(
        "選擇產品：",
        options=prod_options,
        format_func=get_display_label,
        key=dynamic_dropdown_key
    )

    if st.button("🚀 確定選擇此產品並開始文本探勘"):
        st.session_state.active_product = selected_prod_object
        st.session_state.step = 3
        st.session_state.df_reviews_cache = None  # 【本次新增】換選商品時，重置舊快取
        st.session_state.df_stats_cache = None
        st.rerun()

# ==============================================================================
# 三級畫面：Excel 下載與 Plotly 數據視覺化 (【本次修正】導入快取防禦阻斷機制)
# ==============================================================================
if st.session_state.step == 3 and "active_product" in st.session_state:
    if st.button("⬅️ 返回重新選擇商品"):
        st.session_state.step = 2
        st.session_state.df_reviews_cache = None
        st.session_state.df_stats_cache = None
        st.rerun()

    st.write("---")
    st.write(f"### 📊 正在深度解構：`{st.session_state.active_product['name']}`")

    reviews_base_url = f"{st.session_state.active_product['url']}/reviews"

    # --------------------------------------------------------------------------
    # 【本次修正核心】快取防禦鎖：如果快取是空的，才進去跑網路爬蟲；若已有資料則直接讀取
    # --------------------------------------------------------------------------
    if st.session_state.df_reviews_cache is None:

        review_urls, reviews_soup = scan_first_page_review_urls(reviews_base_url)
        total_to_crawl = len(review_urls)

        if total_to_crawl > 0:
            meta_info_box = st.empty()
            progress_bar = st.progress(0)
            live_log_box = st.empty()

            pos_kws = [
                # 質地與觸感
                "好吸收", "好推勻", "延展度佳", "保濕", "不黏膩", "清爽", "滋潤", "水潤", "溫和", "輕透", "零負擔",
                "柔嫩", "滑嫩",
                # 妝效與外觀
                "明亮", "透亮", "光澤", "提亮", "服貼", "自然", "修飾", "遮瑕", "均勻膚色", "奶油肌",
                # 功效與持久度
                "持久", "控油", "不脫妝", "不暗沉", "穩定", "緊緻", "舒緩", "鎮定", "鎖水",
            ]

            neg_kws = [
                # 質地與觸感
                "黏膩", "悶感", "悶", "厚重", "油膩", "乾澀", "緊繃", "難推", "搓泥",
                # 膚況反應 (刺激性)
                "致痘", "爆痘", "粉刺", "過敏", "刺痛", "熏眼", "辣眼睛", "紅腫", "發癢", "泛紅", "刺激", "刺眼",
                "刺鼻", "太香",
                # 妝效災難
                "起屑", "卡粉", "浮粉", "脫妝", "暗沉", "斑駁", "起皮", "泛白", "假白", "面具感", "假面", "顯毛孔",
                "顯紋理", "不持久", "太乾", "很乾"
            ]

            all_data = []
            kw_stats = {"特徵詞": [], "次數": [], "評價屬性": []}
            pos_counter = {k: 0 for k in pos_kws}
            neg_counter = {k: 0 for k in neg_kws}

            start_time = time.time()

            for idx, r_url in enumerate(review_urls):
                current_count = idx + 1
                progress_percent = current_count / total_to_crawl

                elapsed_time = time.time() - start_time
                avg_time = elapsed_time / current_count if current_count > 0 else 1.8
                eta_seconds = (total_to_crawl - current_count) * avg_time
                eta_string = f"{int(eta_seconds // 60)} 分 {int(eta_seconds % 60)} 秒" if eta_seconds > 60 else f"{int(eta_seconds)} 秒"

                meta_info_box.markdown(f"""
                <div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 10px; border-left: 5px solid #1f77b4;">
                    <h4 style="margin-top:0; color: #1f77b4; font-family: sans-serif;">⏳ 輿情分析引擎全速解構中</h4>
                    <ul style="list-style-type: none; padding-left: 5px; font-family: sans-serif; line-height: 1.6;">
                        <li><b>目前進度：</b> <code style="font-size:1.1em; background-color:#fff; padding:2px 6px; border-radius:4px;">[{current_count} / {total_to_crawl}]</code> 🚀 <b>{progress_percent * 100:.1f}%</b></li>
                        <li><b>已耗時間：</b> {int(elapsed_time // 60)} 分 {int(elapsed_time % 60)} 秒</li>
                        <li><b>預估剩餘時間 (ETA)：</b> <span style="color:#e74c3c; font-weight:bold;">{eta_string}</span></li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)

                progress_bar.progress(progress_percent)
                live_log_box.caption(f"🔗 [實時文本分析中] 正在閱覽評論網址： {r_url}")

                time.sleep(random.uniform(1.0, 2.2))

                try:
                    r_resp = requests.get(r_url, impersonate="chrome", timeout=10)
                    if r_resp.status_code == 200:
                        r_soup = BeautifulSoup(r_resp.text, "html.parser")
                        text_block = r_soup.select_one(".review-content, .comment-content, .card-body")
                        if text_block:
                            content = text_block.get_text().strip()

                            # === 【修改這裡】加入簡單語意排除邏輯 ===
                            # 1. 處理正面特徵
                            for k in pos_kws:
                                if k in content:
                                    # 排除「不保濕」、「不好吸收」等狀況
                                    if f"不{k}" not in content and f"沒{k}" not in content:
                                        pos_counter[k] += 1

                            # 2. 處理負面特徵 (解決不黏膩被歸類為黏膩的問題)
                            for k in neg_kws:
                                if k in content:
                                    # 排除「不黏膩」、「沒致痘」、「不會過敏」、「沒長粉刺」等狀況
                                    if f"不{k}" not in content and f"沒{k}" not in content and f"不會{k}" not in content and f"沒長{k}" not in content:
                                        neg_counter[k] += 1
                            # ==================================

                            all_data.append({"評論網址": r_url, "心得摘要截斷": content[:100] + "..."})
                    elif r_resp.status_code == 403:
                        live_log_box.error("⚠️ 觸發網頁高頻保護機制！系統自動進入 10 秒冷卻冬眠後繼續推進...")
                        time.sleep(10)
                except Exception:
                    continue

            meta_info_box.empty()
            progress_bar.empty()
            live_log_box.empty()

            # 爬取完成，將結果打包存入快取記憶體中鎖定
            st.session_state.df_reviews_cache = pd.DataFrame(all_data)

            for k, v in pos_counter.items():
                if v > 0:
                    kw_stats["特徵詞"].append(k);
                    kw_stats["次數"].append(v);
                    kw_stats["評價屬性"].append("正面評價")
            for k, v in neg_counter.items():
                if v > 0:
                    kw_stats["特徵詞"].append(k);
                    kw_stats["次數"].append(v);
                    kw_stats["評價屬性"].append("負面評價")
            st.session_state.df_stats_cache = pd.DataFrame(kw_stats)
            st.rerun()  # 儲存完快取，手動刷新一次直接進入渲染場景

        else:
            st.error("該產品主評論區未發現可爬取的評論連結。")

    # --------------------------------------------------------------------------
    # 最終渲染場景：【本次新增】直接讀取快取數據，點擊下載再也不會驚動爬蟲！
    # --------------------------------------------------------------------------
    if st.session_state.df_reviews_cache is not None and not st.session_state.df_reviews_cache.empty:
        st.success(f"🎉 全流水線大功告成！已成功分析第一頁共 {len(st.session_state.df_reviews_cache)} 篇真實消費者數據。")

        st.write("#### 📥 1. 輿情數據下載 (Excel / CSV)")
        csv_data = st.session_state.df_reviews_cache.to_csv(index=False).encode('utf-8-sig')

        # 這裡點擊下載，雖然網頁會重整，但因為上面查到 cache 有資料，會秒速通過，絕對不會重爬！
        st.download_button(
            label="📥 點擊下載產品評論與網址匯總表 (Excel可開)",
            data=csv_data,
            file_name=f"{st.session_state.active_product['name']}_評論匯總.csv",
            mime="text/csv"
        )
        st.dataframe(st.session_state.df_reviews_cache, use_container_width=True)

        st.write("#### 📈 2. 產品優缺點特徵聲量統計圖 (Plotly)")
        if st.session_state.df_stats_cache is not None and not st.session_state.df_stats_cache.empty:
            fig = px.bar(
                st.session_state.df_stats_cache, x="特徵詞", y="次數", color="評價屬性",
                title=f"{st.session_state.active_product['name']} - 輿情關鍵字詞頻分佈",
                barmode="group",
                color_discrete_map={"正面評價": "#2ecc71", "負面評價": "#e74c3c"}
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("該產品的樣本評論中，暫時未匹配到核心優缺點字典特徵詞。")