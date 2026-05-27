import io
import os
import time
import bs4
from bs4 import BeautifulSoup
from ddgs import DDGS
import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# ==============================================================================
# 段落一：系統核心主函數與原生 UI 介面部署
# ==============================================================================
def crawl_and_show_reviews():
    # 使用最穩定的 Streamlit 原生語法部署標題與說明文字
    st.title("🧪 Cosme 美妝數據聲量統計分析")
    st.write("輸入化妝品或保養品名稱，系統將自動啟動 RAG 動態檢索，進行最新評價採集與特徵統計。")

    # 顯示標準輸入搜尋框與按鈕（垂直排列，防錯率最高）
    query_item = st.text_input("請輸入欲查詢的產品項目：", placeholder="例如：DR.WU 達爾膚 杏仁酸")
    search_button = st.button("開始搜尋")

    # 設定偽裝瀏覽器 Headers，防範美妝論壇拒絕連線 (HTTP 403 錯誤)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # 当使用者点击按钮且输入框不为空时，正式触发大数据采集与分析流程
    if search_button and query_item:

        # ==============================================================================
        # 段落二：初始化大數據特徵關鍵字庫與審計計數器 (特徵工程準備)
        # ==============================================================================
        # 建立 10 大正面與負面指標的聲量統計字典
        keyword_stats = {
            "優點: 保濕滋潤": 0, "優點: 清爽控油": 0, "優點: 溫和不刺激": 0, "優點: 提亮美白": 0, "優點: 吸收快速": 0,
            "缺點: 敏感紅腫": 0, "缺點: 黏膩厚重": 0, "缺點: 效果不明顯": 0, "缺點: 味道難聞": 0, "缺點: 長痘長粉刺": 0
        }

        # 定義各指標在全網文本中進行比對的關鍵字特徵庫群組
        mapping_keywords = {
            "優點: 保濕滋潤": ["保濕", "滋潤", "補水", "水潤", "不乾"],
            "優點: 清爽控油": ["清爽", "控油", "不油", "不黏", "霧面"],
            "優點: 溫和不刺激": ["溫和", "不刺激", "修護", "舒緩", "穩定"],
            "優點: 提亮美白": ["美白", "提亮", "變白", "淡斑", "光澤"],
            "優點: 吸收快速": ["好吸收", "吸收快", "一下就吸收", "不悶"],
            "缺點: 敏感紅腫": ["過敏", "泛紅", "刺痛", "紅腫", "發癢"],
            "缺點: 黏膩厚重": ["黏膩", "油膩", "厚重", "很悶", "悶痘"],
            "缺點: 效果不明顯": ["沒效果", "無感", "雞肋", "看不到效果", "普通"],
            "缺點: 味道難聞": ["不好聞", "香精味", "怪味", "臭", "味道刺鼻"],
            "缺點: 長痘長粉刺": ["長痘", "致痘", "長粉刺", "爆痘", "悶出粉刺"]
        }

        # 初始化資料審計追蹤變數 (Data Audit Metrics)
        total_scraped = 0  # 總共蒐集評論數
        actual_used = 0  # 實際採用評論數
        matched_review_ids = set()  # 存放至少命中一個優缺點關鍵字的評論 ID 集合

        # ==============================================================================
        # 段落三：動態全網檢索與雙機制網頁爬蟲網路連線模組 (RAG 資料獲取)
        # ==============================================================================
        with st.status("正在檢索...", expanded=True) as status:
            status.update(label=f"正在檢索關於 '{query_item}' 的相關網頁...")

            # 構建模糊搜尋語法，擴大搜尋池
            search_query = f"{query_item} 評價 心得 使用體驗"
            target_urls = []

            try:
                # 呼叫 2026 最新官方更名之 ddgs 套件進行動態搜尋，獲取前 3 個高相關網址
                with DDGS() as ddgs:
                    results = ddgs.text(query=search_query, max_results=3)
                    for r in results:
                        target_urls.append(r["href"])
            except Exception as e:
                st.error(f"搜尋引擎動態檢索連線異常: {e}")
                return

            # 防呆機制：若全網找不到相關網頁則優雅結束
            if not target_urls:
                st.warning("未能搜尋到相關評價網頁，請嘗試更換產品關鍵字。")
                return

            all_reviews_data = []
            review_id = 1

            # 遍歷搜尋到的目標網址，正式開始爬取內文
            for index, url in enumerate(target_urls, start=1):
                status.update(label=f"正在建立連線並分析數據來源網頁 ({index}/{len(target_urls)})...")

                try:
                    # 使用 requests 建立即時連線，並設定 8 秒超時防護以防程式卡死
                    response = requests.get(url, headers=headers, timeout=8)

                    # PyCharm 後台偵錯與效能監控日誌
                    print(f"========= 正在測試連線 =========")
                    print(f"目前嘗試網址: {url}")
                    print(f"網頁回應代碼 (Status Code): {response.status_code}")
                    print(f"下載的網頁字數: {len(response.text)}")

                    # 狀態碼非 200 則優雅跳過該網頁
                    if response.status_code != 200:
                        continue

                    # 自動識別網頁編碼，徹底防止繁體中文解析出亂碼
                    response.encoding = response.apparent_encoding
                    soup = BeautifulSoup(response.text, "html.parser")

                    # 撈取網頁標題，用於前端來源追蹤驗證
                    web_title = soup.title.text.strip() if soup.title else "未知網頁標題"

                    # 嘗試定位標準 @cosme 評論元件
                    review_containers = soup.find_all("div", class_="review-container")

                    # ------------------------------------------------------------------
                    # 核心演算法：雙機制自適應文本清洗與特徵匹配
                    # ------------------------------------------------------------------
                    if review_containers:
                        # 核心機制 A: 強匹配 (精準解析標準 @cosme 評論頁面)
                        total_scraped += len(review_containers)  # 計入總搜集評論基數

                        for container in review_containers[:5]:  # 每個網頁採樣前 5 筆高品質資料
                            content_tag = container.find("div", class_="review-content")
                            score_tag = container.find("div", class_="uc-rating-star")

                            content = content_tag.text.strip().replace("\n", " ") if content_tag else ""
                            score = score_tag.text.strip() if score_tag else "正常評分"

                            if content:
                                current_id = review_id
                                # 將結構化資料封裝入庫
                                all_reviews_data.append({
                                    "ID": current_id, "資料來源網站": "台灣 @cosme 美妝網",
                                    "網頁標題說明": web_title[:25] + "...", "評分星等": score,
                                    "摘要內文": content[:120] + "...", "原始網址連結": url
                                })
                                review_id += 1
                                actual_used += 1  # 計入實際採用合格數

                                # 對內文進行關鍵字矩陣特徵比對與累加
                                for feature_name, keywords_list in mapping_keywords.items():
                                    if any(kw in content for kw in keywords_list):
                                        keyword_stats[feature_name] += 1
                                        matched_review_ids.add(current_id)  # 記錄命中特徵之評論 ID
                    else:
                        # 核心機制 B: 弱匹配模糊採集 (相容 Dcard、美妝部落格或非標準規格網頁)
                        potential_tags = soup.find_all(["p", "div", "span"])
                        total_scraped += len(potential_tags)  # 計入總搜集文本段落數

                        saved_count = 0
                        for tag in potential_tags:
                            text = tag.text.strip().replace("\n", " ")

                            # 大數據自動去噪與過濾規則
                            if len(text) > 15 and saved_count < 8:
                                if any(keyword in text for keyword in
                                       ["登入", "隱私權", "購物車", "版權所有", "Copyright"]):
                                    continue

                                # 動態識別來源平台標籤
                                platform = "Dcard 美妝板" if "dcard.tw" in url else "網路綜合開箱"

                                current_id = review_id
                                all_reviews_data.append({
                                    "ID": current_id, "資料來源網站": platform,
                                    "網頁標題說明": web_title[:25] + "...", "評分星等": "用戶分享",
                                    "摘要內文": text[:120] + "...", "原始網址連結": url
                                })
                                review_id += 1
                                saved_count += 1
                                actual_used += 1  # 計入實際採用合格數

                                # 對模糊文本段落進行關鍵字矩陣特徵比對與累加
                                for feature_name, keywords_list in mapping_keywords.items():
                                    if any(kw in text for kw in keywords_list):
                                        keyword_stats[feature_name] += 1
                                        matched_review_ids.add(current_id)  # 記錄命中特徵之評論 ID

                    time.sleep(0.3)

                except Exception as e:
                    print(f"解析外部網頁時發生非預期例外，已自動跳過。原因: {e}")
                    continue

            status.update(label="數據採集與特徵工程計算完畢！", state="complete")

        # ==============================================================================
        # 段落四：前端 大數據審計指標面板渲染
        # ==============================================================================
        retention_rate = (actual_used / total_scraped * 100) if total_scraped > 0 else 0
        keyword_scanned_count = len(matched_review_ids)

        if all_reviews_data:
            st.markdown("### 📊 大數據採集與審計指標監控面板")
            # 建立三欄並排排版，將大數據漏斗模型可視化呈現
            m1, m2, m3 = st.columns(3)
            with m1:
                st.metric(label="📥 總共搜集評論段落數", value=f"{total_scraped} 筆")
            with m2:
                st.metric(label="🧼 實際採用結構評論數", value=f"{actual_used} 筆",
                          delta=f"數據過濾留存率 {retention_rate:.1f}%")
            with m3:
                st.metric(label="🎯 關鍵字清單採計之評論數", value=f"{keyword_scanned_count} 筆",
                          help="指經過文本特徵工程比對後，內文含有至少一項核心優缺點關鍵字之高參考價值評論總數")

            st.markdown("---")

        # ==============================================================================
        # 段落五：實時評價清單資料表與標準 Excel (.xlsx) 多工作表打包匯出模組
        # ==============================================================================
        st.subheader(f"📋 「{query_item}」 最新採集評價清單")

        if all_reviews_data:
            # 將明細資料轉換為 Pandas 資料表，並依照 2026 最新 Streamlit 語法進行展延排版
            df = pd.DataFrame(all_reviews_data)
            st.dataframe(df, width='stretch', hide_index=True)

            # 組裝第一個 Sheet 的數據：將大數據審計元數據 (Metadata) 打包
            summary_data = {
                "審計項目指標": [
                    "查詢目標產品名稱", "總共蒐集評論段落數 (Total Scraped)",
                    "實際採用結構評論數 (Actual Used)", "數據過濾保留率 (Retention Rate)",
                    "關鍵字清單採計之評論數 (Keyword Matched)"
                ],
                "統計數值結果": [
                    query_item, f"{total_scraped} 筆", f"{actual_used} 筆",
                    f"{retention_rate:.2f}%", f"{keyword_scanned_count} 筆"
                ],
                "備註說明": [
                    "使用者在系統輸入的查詢產品關鍵字", "網路底層採集到的所有原始 HTML 文字段落總數",
                    "通過系統去噪、長度過濾規則後，留存之高品質真實評論數",
                    "實際採用評論佔總搜集評論之百分比（指標越高代表數據原生髒噪越少）",
                    "經過美妝特徵庫比對，內文含有至少一項核心優缺點之有效評論基數"
                ]
            }
            summary_df = pd.DataFrame(summary_data)

            # 在記憶體中建立一個虛擬的二進位檔案流 (BytesIO Object)
            excel_buffer = io.BytesIO()

            # 使用 ExcelWriter 進行多 Sheets 壓縮寫入作業
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                summary_df.to_excel(writer, sheet_name="數據審計摘要", index=False)
                df.to_excel(writer, sheet_name="明細資料清單", index=False)

            excel_buffer.seek(0)

            # 部署標準 Excel 下載按鈕
            st.download_button(
                label="📥 下載本次搜尋評價 Excel 檔 (.xlsx)",
                data=excel_buffer,
                file_name=f"{query_item}_reviews.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # ==============================================================================
            # 段落六：Plotly 負向/正向聲量對比交互式統計圖表渲染
            # ==============================================================================
            st.markdown("---")
            st.subheader(f"📈 特徵分析：「{query_item}」 優缺點聲量分佈統計圖")

            # 將特徵計數字典轉換為圖表專用 DataFrame
            chart_data = pd.DataFrame({
                "特徵指標": list(keyword_stats.keys()),
                "提及次數 (頻率)": list(keyword_stats.values()),
                "性質": ["正面優點" if "優點" in k else "負面地雷" for k in keyword_stats.keys()]
            })

            chart_data = chart_data[chart_data["提及次數 (頻率)"] > 0]

            if not chart_data.empty:
                # 呼叫 Plotly Express 建立標準水平長條圖
                fig = px.bar(
                    chart_data,
                    x="提及次數 (頻率)",
                    y="特徵指標",
                    color="性質",
                    orientation="h",
                    title=f"文字探勘：消費者核心關注點分佈圖",
                    color_discrete_map={"正面優點": "#22c55e", "負面地雷": "#ef4444"},
                    template="plotly_white"
                )

                fig.update_layout(
                    yaxis={'categoryorder': 'total ascending'},
                    margin=dict(l=150, r=20, t=50, b=50),
                    showlegend=True
                )

                # ==========================================================
                # 將 use_container_width=True 替換為 2026 全新寫法 width='stretch'
                # ==========================================================
                st.plotly_chart(fig, width='stretch')
            else:
                st.info("💡 提示：本次採集的網路文字樣本較少，未達優缺點關鍵字顯著統計標準，故不單獨顯示統計圖表。")

        else:
            st.info("未能成功從目標網頁中提取出有效結構文字，請再試一次。")


# ==============================================================================
# 獨立腳本入口點 (Entry Point) 驗證
# ==============================================================================
if __name__ == "__main__":
    crawl_and_show_reviews()