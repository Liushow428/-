import streamlit as st
import time
import sqlite3
import urllib.parse
import base64
import re
import requests
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_groq import ChatGroq
import pytz

# 設定台灣時區
tz = pytz.timezone('Asia/Taipei')

st.set_page_config(page_title="智能社群營運工作站", page_icon="📱", layout="centered")

def load_css(file_name):
    with open(file_name, "r", encoding="utf-8") as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css("style.css")

def init_db():
    conn = sqlite3.connect('social_posts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS posts
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  topic TEXT, platform TEXT, post_content TEXT,
                  image_prompt TEXT, image_url TEXT, public_img_url TEXT, schedule_time DATETIME, status TEXT)''')
                  
    c.execute("PRAGMA table_info(posts)")
    columns = [col[1] for col in c.fetchall()]
    if 'public_img_url' not in columns:
        c.execute("ALTER TABLE posts ADD COLUMN public_img_url TEXT")
        
    conn.commit()
    conn.close()

def publish_to_api(platform, content, public_img_url):
    try:
        if platform == "Instagram":
            token = st.secrets.get("IG_ACCESS_TOKEN", "")
            ig_user_id = st.secrets.get("IG_USER_ID", "")
            if not token or not ig_user_id: 
                return False, "缺少 API 金鑰"
            
            container_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media"
            container_payload = {"image_url": public_img_url, "caption": content, "access_token": token}
            res = requests.post(container_url, data=container_payload).json()
            
            if "id" in res:
                creation_id = res["id"]
                # 等待 8 秒讓 Meta 伺服器下載圖片
                time.sleep(8)
                publish_url = f"https://graph.facebook.com/v19.0/{ig_user_id}/media_publish"
                pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": token}).json()
                
                if "id" in pub_res:
                    return True, "發布成功"
                else:
                    err_msg = pub_res.get("error", {}).get("message", "未知的發布錯誤")
                    return False, f"Meta拒絕發布: {err_msg}"
            else:
                err_msg = res.get("error", {}).get("message", "建立草稿失敗")
                return False, f"容器建立失敗: {err_msg}"
                
        elif platform == "Threads":
            token = st.secrets.get("THREADS_ACCESS_TOKEN", "")
            threads_user_id = st.secrets.get("THREADS_USER_ID", "")
            if not token or not threads_user_id: 
                return False, "缺少 API 金鑰"
            
            container_url = f"https://graph.threads.net/v1.0/{threads_user_id}/threads"
            container_payload = {"media_type": "IMAGE", "image_url": public_img_url, "text": content, "access_token": token}
            res = requests.post(container_url, data=container_payload).json()
            
            if "id" in res:
                creation_id = res["id"]
                time.sleep(8)
                publish_url = f"https://graph.threads.net/v1.0/{threads_user_id}/threads_publish"
                pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": token}).json()
                
                if "id" in pub_res:
                    return True, "發布成功"
                else:
                    err_msg = pub_res.get("error", {}).get("message", "未知的發布錯誤")
                    return False, f"Meta拒絕發布: {err_msg}"
            else:
                err_msg = res.get("error", {}).get("message", "建立草稿失敗")
                return False, f"容器建立失敗: {err_msg}"
                
        return False, "未支援的平台"
    except Exception as e:
        return False, f"系統錯誤: {str(e)}"

def check_and_publish():
    conn = sqlite3.connect('social_posts.db')
    c = conn.cursor()
    # 確保排程器讀取的是台灣時區的時間
    now = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')
    c.execute("SELECT id, platform, post_content, public_img_url FROM posts WHERE status='排程中' AND schedule_time <= ?", (now,))
    rows = c.fetchall()
    
    for row in rows:
        post_id, platform, content, public_img_url = row
        success, msg = publish_to_api(platform, content, public_img_url)
        
        if success:
            c.execute("UPDATE posts SET status='已發布' WHERE id=?", (post_id,))
        else:
            short_msg = msg[:35] + "..." if len(msg) > 35 else msg
            c.execute("UPDATE posts SET status=? WHERE id=?", (f"失敗: {short_msg}", post_id))
            
    conn.commit()
    conn.close()

@st.cache_resource
def init_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_publish, 'interval', seconds=15)
    scheduler.start()
    return scheduler

init_db()
init_scheduler()

if 'generated_data' not in st.session_state:
    st.session_state.generated_data = None

st.title("智能社群營運工作站")
st.markdown("基於 LLM 技術的自動化內容生產與排程系統")
st.divider()

st.subheader("參數設定")

col_topic, col_aud = st.columns(2)
with col_topic:
    topic = st.text_input("輸入內容主題 (必填)", placeholder="例如：大二必修生存指南")
with col_aud:
    target_audience = st.text_input("目標受眾 (必填)", placeholder="例如：在校大學生")

col_plat, col_tone = st.columns(2)
with col_plat:
    platform = st.selectbox("發布平台", ["Instagram", "Threads"])
with col_tone:
    tone = st.selectbox("文案風格", ["嚴肅專業 (Professional)", "知識干貨 (Educational)", "幽默風趣 (Humorous)", "懸念行銷 (Suspenseful)", "熱情活潑 (Enthusiastic)", "真誠分享 (Authentic)", "文青抒情 (Poetic)", "短小精悍 (Punchy)", "限時緊急 (Urgency)"])

with st.expander("進階視覺設定 (AI 繪圖)"):
    col_ratio, col_style = st.columns(2)
    with col_ratio:
        aspect_ratio = st.selectbox("圖片比例", ["1:1 (貼文)", "9:16 (限時動態)", "16:9 (橫式影片)"])
    with col_style:
        art_style = st.selectbox("藝術風格", ["寫實攝影 (Realistic)", "極簡風格 (Minimalist)", "數位插畫 (Digital Art)", "3D 渲染 (3D Render)", "賽博龐克 (Cyberpunk)", "蒸汽波 (Vaporwave)", "新海誠風 (Makoto Shinkai)", "像素藝術 (Pixel Art)", "印象派油畫 (Impressionist)"])

st.write("")
if st.button("一鍵生成圖文企劃"):
    st.session_state.generated_data = None
    
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except KeyError:
        st.error("操作失敗：請在 .streamlit/secrets.toml 中設定 GROQ_API_KEY！")
        st.stop()

    if not topic.strip() or not target_audience.strip():
        st.error("操作失敗：請填寫「內容主題」與「目標受眾」，兩者皆不可空白！")
    else:
        try:
            with st.status("AI 引擎運算中...", expanded=True) as status:
                st.write("啟動 Groq 高速演算...")
                
                llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0.7, groq_api_key=api_key)
                
                dim_map = {
                    "1:1 (貼文)": ("1024", "1024"),
                    "9:16 (限時動態)": ("768", "1344"),
                    "16:9 (橫式影片)": ("1344", "768")
                }
                img_w, img_h = dim_map[aspect_ratio]
                
                combined_prompt = PromptTemplate.from_template(
                    "You are a top-tier social media marketing expert and visual designer.\n"
                    "Based on the following parameters, complete two tasks:\n"
                    "1. Topic: {topic}\n"
                    "2. Target Audience: {target_audience}\n"
                    "3. Platform: {platform}\n"
                    "4. Tone: {tone}\n"
                    "5. Art Style: {art_style}\n\n"
                    "[Task 1]: Write a highly engaging, detailed social media post. "
                    "The article must be between 200 and 400 words. Expand on the topic with feasible suggestions or in-depth insights. "
                    "CRITICAL FORMATTING RULES: "
                    "1. DO NOT output a wall of text. Break the content into short, highly readable paragraphs (1-3 sentences max). "
                    "2. Add clear empty lines (line breaks) between every paragraph and section. "
                    "3. Use standard bullet points (•, -, or 1. 2. 3.) to structure key takeaways or lists cleanly. "
                    "4. DO NOT use Markdown formatting (like **bold** or # headings) because the target platform does not support them. Use ALL CAPS or brackets【】for headings and emphasis instead. "
                    "CRITICAL: Use emojis appropriately; remember not to use them excessively. "
                    "CRITICAL: The post MUST be written in the EXACT SAME LANGUAGE as the provided 'Topic'.\n\n"
                    "[Task 2]: Extract the visual key elements from the post and generate a HIGHLY DETAILED English prompt for an AI image generator (MUST be under 70 words). "
                    "You MUST briefly describe the main subject, background environment, lighting, and camera angle to ensure high image quality. "
                    "CRITICAL: You MUST use ONLY English letters, numbers, and basic punctuation. DO NOT use any Chinese characters.\n\n"
                    "You MUST output strictly in the following format without any extra words:\n"
                    "===POST===\n"
                    "[Task 1 content here]\n"
                    "===PROMPT===\n"
                    "[Task 2 content here]"
                )
                
                chain = combined_prompt | llm | StrOutputParser()
                
                st.write("單次生成長文案與視覺提示詞...")
                result_text = chain.invoke({
                    "platform": platform,
                    "topic": topic,
                    "target_audience": target_audience,
                    "tone": tone,
                    "art_style": art_style
                })
                
                st.write("解析資料並由後端抓取影像數據...")
                
                post_content = ""
                image_prompt = ""
                image_url = ""
                public_img_url = ""
                
                try:
                    if "===PROMPT===" in result_text:
                        parts = result_text.split("===PROMPT===")
                        post_content = parts[0].replace("===POST===", "").strip()
                        raw_image_prompt = parts[1].strip()
                    else:
                        post_content = result_text.replace("===POST===", "").strip()
                        raw_image_prompt = f"A highly detailed professional illustration of {topic}, {art_style}, cinematic lighting, masterpiece"
                        
                    safe_prompt = re.sub(r'[^a-zA-Z0-9\s,.-]', '', raw_image_prompt).strip()
                    safe_prompt = re.sub(r'\s+', ' ', safe_prompt)[:800]
                    
                    if not safe_prompt:
                        safe_prompt = "A high quality professional illustration, cinematic lighting, highly detailed"
                        
                    encoded_prompt = urllib.parse.quote(safe_prompt)
                    seed = int(time.time())
                    image_api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={img_w}&height={img_h}&nologo=true&seed={seed}"
                    
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    img_response = requests.get(image_api_url, headers=headers, timeout=60)
                    
                    if img_response.status_code == 200:
                        b64_img = base64.b64encode(img_response.content).decode('utf-8')
                        image_url = f"data:image/jpeg;base64,{b64_img}"
                        image_prompt = safe_prompt
                        public_img_url = image_api_url
                    else:
                        image_prompt = f"圖片伺服器忙碌 (HTTP: {img_response.status_code})"
                        
                except requests.exceptions.Timeout:
                    if not post_content: post_content = result_text.replace("===POST===", "").strip()
                    image_prompt = "伺服器算圖超時 (60秒)，請稍後至下方重新生成圖片"
                    
                except Exception as inner_e:
                    if not post_content: post_content = result_text.replace("===POST===", "").strip()
                    image_prompt = f"圖片下載失敗：{str(inner_e)}"

                status.update(label="圖文企劃生成完成", state="complete", expanded=False)

            st.session_state.generated_data = {
                "topic": topic,
                "platform": platform,
                "post": post_content,
                "prompt": image_prompt,
                "image_url": image_url,
                "public_img_url": public_img_url
            }
            st.rerun()

        except Exception as e:
            st.error(f"❌ 發生未知的 API 錯誤：{str(e)}")

if st.session_state.generated_data:
    st.divider()
    st.subheader("生成結果 (可自由修改)")
    
    tab1, tab2, tab3 = st.tabs(["社群文案", "視覺影像", "自動化排程"])
    
    with tab1:
        st.info("✍️ 你可以在下方直接修改 AI 生成的文案，排程發布將以修改後的內容為準。")
        edited_post = st.text_area(
            label="Content", 
            value=st.session_state.generated_data.get("post", ""), 
            height=400, 
            label_visibility="collapsed"
        )

    with tab2:
        if st.session_state.generated_data.get("image_url"):
            st.markdown(f'<img src="{st.session_state.generated_data.get("image_url")}" style="width: 100%; border-radius: 12px; margin-bottom: 1rem; border: 1px solid rgba(255,255,255,0.1);">', unsafe_allow_html=True)
        else:
            st.error(f"🚨 圖片生圖失敗！原因：{st.session_state.generated_data.get('prompt')}")
            
        st.info("🎨 你可以在下方修改 Prompt，然後點擊按鈕重新生成圖片！")
        edited_prompt = st.text_area(
            label="生成所使用的 Prompt", 
            value=st.session_state.generated_data.get("prompt", ""), 
            height=150
        )
        
        if st.button("重新生成圖片"):
            with st.spinner("重新繪製中 (伺服器算圖可能需要 40~60 秒，請耐心等候)..."):
                dim_map = {
                    "1:1 (貼文)": ("1024", "1024"),
                    "9:16 (限時動態)": ("768", "1344"),
                    "16:9 (橫式影片)": ("1344", "768")
                }
                img_w, img_h = dim_map[aspect_ratio]
                
                safe_prompt = re.sub(r'[^a-zA-Z0-9\s,.-]', '', edited_prompt).strip()
                safe_prompt = re.sub(r'\s+', ' ', safe_prompt)[:800]
                encoded_prompt = urllib.parse.quote(safe_prompt)
                seed = int(time.time())
                image_api_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={img_w}&height={img_h}&nologo=true&seed={seed}"
                
                headers = {'User-Agent': 'Mozilla/5.0'}
                
                try:
                    img_response = requests.get(image_api_url, headers=headers, timeout=60)
                    
                    if img_response.status_code == 200:
                        b64_img = base64.b64encode(img_response.content).decode('utf-8')
                        st.session_state.generated_data["image_url"] = f"data:image/jpeg;base64,{b64_img}"
                        st.session_state.generated_data["public_img_url"] = image_api_url
                        st.session_state.generated_data["prompt"] = edited_prompt
                        st.rerun()
                    else:
                        st.error(f"圖片伺服器忙碌，請稍後再試！ (狀態碼: {img_response.status_code})")
                
                except requests.exceptions.Timeout:
                    st.error("⏳ 圖片伺服器算圖時間過長（超過 60 秒），請稍微簡化 Prompt 或等一下再試！")
                except Exception as e:
                    st.error(f"🚨 發生未知連線錯誤：{str(e)}")
        
    with tab3:
        st.info("請設定預定的發布時間，系統將自動納入 SQLite 資料庫進行排程發布。")
        
        quick_mode = st.radio("快捷時間選擇", ["自訂時間", "5 分鐘後", "30 分鐘後", "1 小時後", "明天此時"], horizontal=True)
        
        now = datetime.now(tz)
        if quick_mode == "5 分鐘後":
            target_time = now + timedelta(minutes=5)
        elif quick_mode == "30 分鐘後":
            target_time = now + timedelta(minutes=30)
        elif quick_mode == "1 小時後":
            target_time = now + timedelta(hours=1)
        elif quick_mode == "明天此時":
            target_time = now + timedelta(days=1)
        else:
            target_time = now
            
        sc1, sc2 = st.columns(2)
        with sc1:
            schedule_date = st.date_input("選擇發布日期", value=target_time.date())
        with sc2:
            schedule_time = st.time_input("選擇發布時間", value=target_time.time(), step=60)
            
        if st.button("確認提交圖文排程"):
            schedule_datetime = datetime.combine(schedule_date, schedule_time).strftime('%Y-%m-%d %H:%M:%S')
            
            conn = sqlite3.connect('social_posts.db')
            c = conn.cursor()
            
            c.execute("INSERT INTO posts (topic, platform, post_content, image_prompt, image_url, public_img_url, schedule_time, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                      (st.session_state.generated_data.get("topic"), 
                       st.session_state.generated_data.get("platform"),
                       edited_post,
                       edited_prompt,
                       st.session_state.generated_data.get("image_url"),
                       st.session_state.generated_data.get("public_img_url"),
                       schedule_datetime,
                       "排程中"))
            conn.commit()
            conn.close()
            
            st.success(f"已成功加入排程隊列！預計發布時間：{schedule_datetime}")
            st.session_state.generated_data = None
            st.rerun()

st.divider()
st.subheader("排程隊列監控 (SQLite)")

conn = sqlite3.connect('social_posts.db')
c = conn.cursor()
c.execute("SELECT id, status, schedule_time, platform, topic, image_url FROM posts ORDER BY schedule_time DESC")
data = c.fetchall()
conn.close()

if data:
    for row in data:
        status_icon = "🟢" if row[1] == "已發布" else "⏳"
        with st.container(border=True):
            col_info, col_img = st.columns([3, 1])
            with col_info:
                st.markdown(f"**{status_icon} 狀態:** {row[1]} | **時間:** {row[2]}")
                st.markdown(f"**平台:** {row[3]} | **主題:** {row[4]}")
            with col_img:
                if row[5]:
                    st.markdown(f'<img src="{row[5]}" style="width: 100%; border-radius: 8px;">', unsafe_allow_html=True)
else:
    st.write("目前資料庫無任何排程資料。")