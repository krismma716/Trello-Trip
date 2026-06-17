import streamlit as st
import streamlit.components.v1 as components
import requests
import re
import base64
import concurrent.futures
import io
from PIL import Image

# ==========================================
# 0. 介面設定
# ==========================================
st.set_page_config(page_title="奧捷德匈 專屬旅程", page_icon="✈️", layout="wide")

LIGHTSPLIT_URL = "https://liff.line.me/1655320992-Y8GowEpw/g/f23GCF87vCLRRuMLKRa5zJ" 
TRIP_START_DATE = "2026-09-11T23:45:00+08:00"

st.markdown("""
    <style>
        header {visibility: hidden;} footer {visibility: hidden;} .stDeployButton {display:none;} #MainMenu {display:none;}
        .block-container { padding: 0 !important; max-width: 100% !important; margin: 0 !important; }
        iframe { border: none !important; width: 100vw !important; display: block !important; }
        
        div[data-testid="stButton"] { position: fixed !important; bottom: 5px !important; right: 8px !important; z-index: 999999 !important; }
        div[data-testid="stButton"] button { background-color: transparent !important; color: rgba(0,0,0,0.15) !important; border: none !important; box-shadow: none !important; padding: 5px !important; min-height: 0 !important; height: auto !important; transition: all 0.3s ease !important; }
        div[data-testid="stButton"] button p { font-size: 16px !important; margin: 0 !important; }
        div[data-testid="stButton"] button:hover { color: #FF5A5F !important; }
        div[data-testid="stButton"] button:active { transform: rotate(180deg) scale(0.9) !important; }
    </style>
""", unsafe_allow_html=True)

try:
    API_KEY = st.secrets["TRELLO_API_KEY"]
    TOKEN = st.secrets["TRELLO_TOKEN"]
    BOARD_ID = st.secrets["TRELLO_BOARD_ID"]
except KeyError:
    st.error("❌ 找不到 API 憑證！請確認 Secrets 設定。")
    st.stop()

# ==========================================
# 2. 核心程式：加入 Pillow 影像極致瘦身引擎
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_trello_data():
    def clean_text(text):
        if not text: return ""
        text = re.sub(r'[\U0001F1E6-\U0001F1FF]{2}', '', text)
        text = re.sub(r'(?i)\b(cz|at|hu)\b', '', text)
        return text.strip()

    def parse_markdown(text):
        if not text: return ""
        text = clean_text(text)
        text = re.sub(r'\*\*(.*?)\*\*', r'<span class="highlight-text">\1</span>', text)
        text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
        text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank" class="action-btn">📍 \1</a>', text)
        text = re.sub(r'(?<!=")(https?://[^\s<]+)(?!">)', r'<a href="\1" target="_blank" class="action-btn">🔗 點擊連結</a>', text)
        lines = text.split('\n')
        html_lines, in_list = [], False
        for line in lines:
            if line.strip().startswith(('- ', '* ')):
                if not in_list: html_lines.append('<ul class="custom-ul">'); in_list = True
                html_lines.append(f'<li>{line.strip()[2:]}</li>')
            else:
                if in_list: html_lines.append('</ul>'); in_list = False
                html_lines.append(line)
        if in_list: html_lines.append('</ul>')
        return '<br>'.join(html_lines).replace('</ul><br>', '</ul>').replace('<br><ul', '<ul')

    # 🛡️ 拯救 iPhone 的終極魔法：下載後強制壓縮！
    def download_and_compress_image(url, card_name):
        if not url: return None
        try:
            if "trello.com" in url:
                headers = {"Authorization": f'OAuth oauth_consumer_key="{API_KEY}", oauth_token="{TOKEN}"'}
                res = requests.get(url, headers=headers, allow_redirects=False, timeout=10)
                if res.status_code in [301, 302, 303, 307, 308]:
                    aws_url = res.headers.get('Location')
                    final_res = requests.get(aws_url, timeout=15)
                else: final_res = res
            else: final_res = requests.get(url, timeout=15)

            if final_res.status_code == 200:
                ctype = final_res.headers.get('Content-Type', '').lower()
                content = final_res.content
                
                # 🍏 只要是圖片，管它原本多肥，一律送進 Pillow 壓縮廠！
                try:
                    if 'image' in ctype or url.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                        img = Image.open(io.BytesIO(content))
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        # 強制將圖片最大邊長縮小到 600px，維持原比例
                        img.thumbnail((600, 600), Image.Resampling.LANCZOS)
                        out = io.BytesIO()
                        # 以 80% 的高品質 JPEG 存出，體積瞬間暴瘦 90%
                        img.save(out, format='JPEG', quality=80)
                        content = out.getvalue()
                        ctype = 'image/jpeg'
                except Exception as e:
                    print(f"⚠️ {card_name} 圖片壓縮失敗，使用原檔: {e}")

                b64 = base64.b64encode(content).decode('utf-8')
                return f"data:{ctype};base64,{b64}"
        except Exception: pass
        return None

    lists_res = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/lists", params={'key': API_KEY, 'token': TOKEN})
    cards_res = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/cards", params={'key': API_KEY, 'token': TOKEN, 'attachments': 'true'})

    if lists_res.status_code != 200 or cards_res.status_code != 200:
        return "<div style='text-align:center; padding:50px;'>❌ API 連線失敗。</div>"

    lists = lists_res.json()
    all_cards = cards_res.json()
    cards_by_list = {}
    for c in all_cards:
        lid = c['idList']
        if lid not in cards_by_list: cards_by_list[lid] = []
        cards_by_list[lid].append(c)

    url_set = set()
    card_to_url = {}
    for lst in lists:
        for c in cards_by_list.get(lst['id'], []):
            img_url = None
            cover_id = c.get('cover', {}).get('idAttachment')
            attachments = c.get('attachments', [])
            
            if cover_id:
                for att in attachments:
                    if att['id'] == cover_id:
                        previews = att.get('previews', [])
                        if previews:
                            previews.sort(key=lambda x: x['width'])
                            valid = [p for p in previews if p['width'] >= 600]
                            img_url = valid[0]['url'] if valid else previews[-1]['url']
                        else: img_url = att['url']
                        break
            if not img_url and attachments:
                for att in attachments:
                    if 'image' in att.get('mimeType', '') or att.get('url', '').lower().endswith(('.png', '.jpg', '.jpeg')):
                        previews = att.get('previews', [])
                        if previews:
                            previews.sort(key=lambda x: x['width'])
                            valid = [p for p in previews if p['width'] >= 600]
                            img_url = valid[0]['url'] if valid else previews[-1]['url']
                        else: img_url = att['url']
                        break
            if not img_url and c.get('cover', {}).get('sharedSourceUrl'): 
                img_url = c['cover']['sharedSourceUrl']
                
            if img_url:
                url_set.add(img_url)
                card_to_url[c['id']] = img_url

    url_to_base64 = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # 使用全新的瘦身下載器
        future_to_url = {executor.submit(download_and_compress_image, u, "圖片"): u for u in url_set}
        for future in concurrent.futures.as_completed(future_to_url):
            try: url_to_base64[future_to_url[future]] = future.result()
            except Exception: url_to_base64[future_to_url[future]] = None

    days_data, info_data = [], []
    for lst in lists:
        list_name = clean_text(lst['name'])
        cards = cards_by_list.get(lst['id'], [])
        cards_html = ""
        is_checklist = "清單" in list_name or "待辦" in list_name

        for card in cards:
            card_name = clean_text(card.get("name", ""))
            card_desc = parse_markdown(card.get("desc", "").strip())
            
            if is_checklist:
                desc_html = f'<div class="check-desc">{card_desc}</div>' if card_desc else ''
                cards_html += f"""
                <div class="checklist-item" onclick="toggleCheck(this)">
                    <div class="check-circle"></div>
                    <div class="check-content"><div class="check-text">{card_name}</div>{desc_html}</div>
                </div>
                """
            else:
                target_url = card_to_url.get(card['id'])
                img_src = url_to_base64.get(target_url) if target_url else None
                img_html = f'<img src="{img_src}" class="card-cover-img" loading="lazy">' if img_src else ''
                has_desc = bool(card_desc)
                chevron_html = '<div class="chevron"></div>' if has_desc else ''
                onclick_html = 'onclick="toggleCard(this)"' if has_desc else ''
                cursor_style = 'cursor: pointer;' if has_desc else 'cursor: default;'
                cards_html += f"""
                <div class="ios-card">
                    <div class="card-trigger" {onclick_html} style="{cursor_style}">
                        {img_html}
                        <div class="card-header"><h3 class="card-title">{card_name}</h3>{chevron_html}</div>
                    </div>
                    <div class="card-body"><div class="card-content"><div class="card-desc">{card_desc}</div></div></div>
                </div>
                """
        if not cards_html: cards_html = '<div class="empty-state">🌴 準備中...</div>'
        if is_checklist and cards: cards_html = f'<div class="checklist-group">{cards_html}</div>'

        list_id = f"section_{lst['id']}"
        if list_name.startswith("D0") or list_name.startswith("D1"):
            match = re.search(r'(D\d+)\s*(\([^\)]+\)\s*\d+/\d+)?\s*(.*)', list_name)
            if match:
                short_name = match.group(1).strip()
                date_info = match.group(2).strip() if match.group(2) else ""
                location = match.group(3).strip() if match.group(3) else "行程"
                clean_location = re.sub(r'\(.*?\)', '', location).strip()
                capsule_subtitle = clean_location[:4] if clean_location else date_info.split(' ')[-1]
            else:
                short_name, date_info, location = list_name.split(' ')[0], "", list_name
                capsule_subtitle = "行程"
            days_data.append({'id': list_id, 'short_name': short_name, 'subtitle': capsule_subtitle, 'date_info': date_info, 'location': location, 'html': cards_html})
        else:
            info_data.append({'id': list_id, 'short_name': list_name, 'html': cards_html})

    day_pills_html, day_contents_html = "", ""
    for i, day in enumerate(days_data):
        active, display = ("active", "block") if i == 0 else ("", "none")
        day_pills_html += f"""
        <div class="sub-pill {active}" onclick="switchSubTab(\'{day["id"]}\', this, \'day-content\')">
            <span class="pill-title">{day["short_name"]}</span>
            <span class="pill-subtitle">{day["subtitle"]}</span>
        </div>
        """
        day_contents_html += f"""
        <div id="{day['id']}" class="day-content sub-content" style="display: {display};" data-location="{day['location']}">
            <div class="city-header">
                <div class="date-row"><span class="city-date">📅 {day['date_info']}</span> <span class="weather-badge"></span></div>
                <h2 class="city-title">{day['location']}</h2>
            </div>
            <div class="card-list">{day['html']}</div>
        </div>
        """

    info_pills_html, info_contents_html = "", ""
    for i, info in enumerate(info_data):
        active, display = ("active", "block") if i == 0 else ("", "none")
        info_pills_html += f'<div class="sub-pill info-pill {active}" onclick="switchSubTab(\'{info["id"]}\', this, \'info-content\')"><span class="pill-title">{info["short_name"]}</span></div>'
        info_contents_html += f"""
        <div id="{info['id']}" class="info-content sub-content" style="display: {display};">
            <div class="city-header"><h2 class="city-title highlight-title">{info['short_name']}</h2></div>
            <div class="card-list">{info['html']}</div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@600;700;800;900&family=Noto+Sans+TC:wght@500;700;900&display=swap');
            ::-webkit-scrollbar {{ display: none; }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Nunito', 'Noto Sans TC', sans-serif; -webkit-tap-highlight-color: transparent; }}
            
            /* 🍏 iOS 終極滑動解藥：讓 HTML 自己內部滾動，不再依賴外部 iframe 縮放 */
            html, body {{ 
                width: 100%; height: 100vh; overflow-x: hidden; overflow-y: auto; 
                -webkit-overflow-scrolling: touch; background-color: #F8F9FA; color: #1E2022; user-select: none; 
            }}
            .app {{ width: 100%; max-width: 500px; margin: 0 auto; min-height: 100vh; padding-bottom: 80px; position: relative; }}
            
            :root {{ --primary: #FF6B6B; --primary-light: #FFF0F0; --text-main: #1E2022; --text-sub: #6B7280; --bg-color: #F8F9FA; --border-color: #F3F4F6; }}

            .nav-bar {{ background: rgba(248, 249, 250, 0.9); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); position: sticky; top: 0; z-index: 100; padding: 20px 20px 14px; display: flex; justify-content: space-between; align-items: center; height: 74px; border-bottom: 1px solid rgba(0,0,0,0.02); }}
            .nav-title {{ font-size: 22px; font-weight: 900; color: var(--primary); letter-spacing: 0.5px; }}
            .tab-switcher {{ display: flex; background: #E5E7EB; border-radius: 12px; padding: 4px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.02); }}
            .tab-btn {{ padding: 8px 14px; font-size: 13px; font-weight: 700; color: #6B7280; border-radius: 10px; cursor: pointer; transition: 0.3s; }}
            .tab-btn.active {{ background: #FFFFFF; color: var(--primary); box-shadow: 0 4px 10px rgba(0,0,0,0.04); transform: scale(1.02); }}
            
            .countdown-wrapper {{ margin: 15px 20px 5px; border-radius: 20px; padding: 20px; background: #FFFFFF; border: 1px solid var(--border-color); box-shadow: 0 10px 25px rgba(0,0,0,0.02); display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 110px; transition: all 0.5s ease; }}
            .cd-mode {{ display: flex; flex-direction: column; align-items: center; width: 100%; }}
            .cd-title {{ font-size: 13px; font-weight: 700; color: var(--text-sub); margin-bottom: 12px; letter-spacing: 1px; display: flex; align-items: center; gap: 6px; }}
            .cd-timer {{ display: flex; gap: 12px; }}
            .cd-box {{ display: flex; flex-direction: column; align-items: center; justify-content: center; }}
            .cd-num {{ font-size: 32px; font-weight: 900; color: var(--text-main); line-height: 1; }}
            .cd-label {{ font-size: 11px; font-weight: 700; color: var(--text-sub); text-transform: uppercase; margin-top: 4px; }}
            .journey-mode {{ display: none; flex-direction: column; align-items: center; width: 100%; text-align: center; animation: fadeIn 0.8s ease; }}
            .journey-greeting {{ font-size: 18px; font-weight: 800; color: var(--primary); margin-bottom: 6px; }}
            .journey-sub {{ font-size: 13px; font-weight: 600; color: var(--text-sub); display: flex; align-items: center; gap: 6px; }}
            .journey-weather-badge {{ background: var(--primary-light); color: var(--primary); padding: 2px 8px; border-radius: 8px; font-size: 11px; font-weight: 800; display: none; }}

            .sub-nav-wrapper {{ background: rgba(248, 249, 250, 0.95); backdrop-filter: blur(20px); position: sticky; top: 74px; z-index: 90; padding: 12px 20px 16px; border-bottom: 1px solid rgba(0,0,0,0.02); }}
            .pill-scroll {{ display: flex; overflow-x: auto; gap: 10px; scrollbar-width: none; padding-bottom: 4px; align-items: center; }}
            .sub-pill {{ display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 10px 20px; background: #FFFFFF; border-radius: 16px; min-width: 70px; cursor: pointer; transition: 0.2s ease; border: 1px solid var(--border-color); box-shadow: 0 4px 10px rgba(0,0,0,0.01); }}
            .pill-title {{ font-size: 16px; font-weight: 800; color: var(--text-main); transition: 0.2s; }}
            .pill-subtitle {{ font-size: 10px; font-weight: 700; color: var(--text-sub); margin-top: 2px; white-space: nowrap; transition: 0.2s; }}
            .sub-pill.active {{ background: var(--primary); border-color: var(--primary); box-shadow: 0 8px 20px rgba(255, 107, 107, 0.25); transform: translateY(-2px); }}
            .sub-pill.active .pill-title, .sub-pill.active .pill-subtitle {{ color: #FFFFFF; }}
            .info-pill {{ flex-direction: row; padding: 10px 20px; white-space: nowrap; width: auto; min-width: 0; }}
            .info-pill .pill-subtitle {{ display: none; }}
            .info-pill .pill-title {{ font-size: 14px; font-weight: 700; display: block; }}
            
            .content-area {{ padding: 24px 20px; }}
            .main-tab {{ display: none; }}
            .main-tab.active {{ display: block; animation: fadeUp 0.4s cubic-bezier(0.4, 0, 0.2, 1); }}
            @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(15px); }} to {{ opacity: 1; transform: translateY(0); }} }}
            @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
            
            .city-header {{ margin-bottom: 24px; padding-left: 4px; margin-top: 5px; }}
            .date-row {{ display: flex; align-items: center; margin-bottom: 6px; }}
            .city-date {{ font-size: 13px; font-weight: 800; color: var(--primary); letter-spacing: 1px; }}
            .weather-badge {{ background: var(--primary-light); color: var(--primary); padding: 4px 10px; border-radius: 10px; font-size: 12px; font-weight: 800; margin-left: 12px; display: none; }}
            .city-title {{ font-size: 28px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.2; color: var(--text-main); }}
            .highlight-title {{ color: var(--primary); }}

            .split-card {{ background: linear-gradient(135deg, #1E2022 0%, #374151 100%); border-radius: 20px; padding: 20px; display: flex; align-items: center; color: white; margin-bottom: 24px; box-shadow: 0 10px 25px rgba(0,0,0,0.1); cursor: pointer; transition: 0.2s; }}
            .split-card:active {{ transform: scale(0.96); }}
            .split-icon {{ font-size: 24px; margin-right: 16px; background: rgba(255,255,255,0.15); width: 50px; height: 50px; border-radius: 14px; display: flex; justify-content: center; align-items: center; }}
            .split-info {{ flex: 1; }}
            .split-title {{ font-size: 17px; font-weight: 800; margin-bottom: 4px; letter-spacing: 0.5px; }}
            .split-desc {{ font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.7); }}
            .split-arrow {{ font-size: 16px; font-weight: 900; background: #FFFFFF; color: #1E2022; width: 32px; height: 32px; border-radius: 50%; display: flex; justify-content: center; align-items: center; }}

            .card-list {{ display: flex; flex-direction: column; gap: 20px; }}
            .ios-card {{ background: #FFFFFF; border-radius: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.03); overflow: hidden; border: 1px solid var(--border-color); }}
            .card-cover-img {{ width: 100%; height: auto; max-height: 350px; object-fit: contain; display: block; border-bottom: 1px solid var(--border-color); background-color: #FFFFFF; }}
            .card-header {{ padding: 20px; display: flex; justify-content: space-between; align-items: center; }}
            .card-title {{ font-size: 17px; font-weight: 800; line-height: 1.4; margin-right: 12px; color: var(--text-main); }}
            
            .chevron {{ width: 28px; height: 28px; background: var(--primary-light); border-radius: 50%; display: flex; justify-content: center; align-items: center; transition: 0.4s ease; flex-shrink: 0; }}
            .chevron::after {{ content: ''; width: 7px; height: 7px; border-right: 2px solid var(--primary); border-bottom: 2px solid var(--primary); transform: translateY(-2px) rotate(45deg); transition: 0.3s; }}
            .open .chevron {{ transform: rotate(180deg); background: var(--primary); box-shadow: 0 4px 10px rgba(255, 107, 107, 0.3); }}
            .open .chevron::after {{ border-color: #FFFFFF; transform: translateY(2px) rotate(45deg); }}
            
            .card-body {{ display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.4s ease; }}
            .card-body.open {{ grid-template-rows: 1fr; border-top: 1px solid var(--border-color); }}
            .card-content {{ overflow: hidden; }}
            .card-desc {{ padding: 0 20px 24px; font-size: 15px; color: var(--text-sub); line-height: 1.7; word-wrap: break-word; margin-top: 16px; user-select: text; }}
            
            .checklist-group {{ background: #FFFFFF; border-radius: 20px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.03); border: 1px solid var(--border-color); }}
            .checklist-item {{ display: flex; align-items: flex-start; padding: 16px 20px; border-bottom: 1px solid var(--border-color); cursor: pointer; transition: 0.2s; background: #FFFFFF; }}
            .checklist-item:active {{ background: var(--bg-color); }}
            .checklist-item:last-child {{ border-bottom: none; }}
            .check-circle {{ width: 22px; height: 22px; border-radius: 50%; border: 2px solid #D1D5DB; margin-right: 14px; flex-shrink: 0; transition: 0.2s; position: relative; margin-top: 2px; }}
            .check-content {{ flex: 1; }}
            .check-text {{ font-size: 15px; font-weight: 700; color: var(--text-main); line-height: 1.4; transition: 0.2s; }}
            .check-desc {{ font-size: 13px; color: var(--text-sub); margin-top: 4px; font-weight: 600; line-height: 1.5; }}
            .checklist-item.checked .check-circle {{ background: #10B981; border-color: #10B981; transform: scale(1.05); }}
            .checklist-item.checked .check-circle::after {{ content: '✓'; color: white; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 12px; font-weight: 900; }}
            .checklist-item.checked .check-text {{ color: #9CA3AF; text-decoration: line-through; }}
            .checklist-item.checked .check-desc {{ color: #D1D5DB; text-decoration: line-through; }}

            .custom-ul {{ margin: 10px 0 10px 22px; padding: 0; }}
            .custom-ul li {{ margin-bottom: 10px; list-style-type: disc; color: var(--text-sub); line-height: 1.5; }}
            .highlight-text {{ font-weight: 700; color: var(--text-main); box-shadow: inset 0 -8px 0 rgba(255, 204, 0, 0.3); }}
            .action-btn {{ display: inline-flex; align-items: center; margin-top: 15px; margin-right: 10px; padding: 12px 20px; background: var(--primary-light); color: var(--primary); text-decoration: none; font-size: 14px; font-weight: 800; border-radius: 12px; transition: 0.2s; }}
            .action-btn:active {{ transform: scale(0.95); }}
            .empty-state {{ text-align: center; color: #B0B3C6; padding: 40px 0; font-size: 15px; font-weight: 500; }}

            /* 計算機 */
            .calc-wrapper {{ background: #FFFFFF; border-radius: 24px; padding: 20px; box-shadow: 0 8px 30px rgba(0,0,0,0.04); border: 1px solid var(--border-color); }}
            .calc-screen {{ background: var(--bg-color); border-radius: 16px; padding: 20px; text-align: right; display: flex; flex-direction: column; justify-content: flex-end; position: relative; border: 1px solid var(--border-color); margin-bottom: 20px; }}
            .currency-badge {{ position: absolute; top: 16px; left: 16px; background: #FFFFFF; border: 1px solid var(--border-color); padding: 6px 12px; border-radius: 10px; font-size: 14px; font-weight: 800; color: var(--text-main); box-shadow: 0 2px 8px rgba(0,0,0,0.02); outline: none; -webkit-appearance: none; cursor: pointer; }}
            .calc-formula {{ font-size: 15px; color: var(--text-sub); min-height: 22px; font-weight: 700; margin-top: 16px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
            .calc-foreign {{ font-size: 40px; font-weight: 900; color: var(--text-main); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; letter-spacing: -1px; margin-bottom: 4px; }}
            .calc-twd {{ font-size: 16px; font-weight: 800; color: #10B981; background: rgba(16, 185, 129, 0.1); display: inline-block; padding: 4px 10px; border-radius: 8px; align-self: flex-end; }}
            
            .calc-keypad {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }}
            .key {{ background: #FFFFFF; color: var(--text-main); font-size: 20px; font-weight: 700; border-radius: 14px; aspect-ratio: 1.2/1; border: 1px solid var(--border-color); text-align: center; transition: 0.1s; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 2px 6px rgba(0,0,0,0.02); touch-action: manipulation; }}
            .key:active {{ transform: scale(0.92); background: var(--bg-color); }}
            .key.op {{ color: var(--primary); font-size: 22px; background: var(--primary-light); border-color: transparent; }}
            .key.op:active {{ background: #FFE0E0; }}
            .key.equal {{ background: var(--primary); color: #FFFFFF; font-size: 24px; border-color: transparent; box-shadow: 0 6px 15px rgba(255, 107, 107, 0.3); }}
            .key.clear {{ color: var(--text-sub); font-weight: 800; background: var(--bg-color); border-color: transparent; }}
            .rate-status {{ text-align: center; font-size: 12px; color: var(--text-sub); font-weight: 700; margin-top: 12px; }}
            .dot {{ display: inline-block; width: 6px; height: 6px; border-radius: 50%; background: #10B981; margin-right: 6px; vertical-align: middle; box-shadow: 0 0 6px rgba(16, 185, 129, 0.5); }}
            .dot.offline {{ background: #F59E0B; box-shadow: 0 0 6px rgba(245, 158, 11, 0.5); }}
        </style>
    </head>
    <body>
        <div class="app">
            <div class="nav-bar">
                <h1 class="nav-title">奧捷德匈</h1>
                <div class="tab-switcher">
                    <div class="tab-btn active" onclick="switchMainTab('tab-itinerary')">行程</div>
                    <div class="tab-btn" onclick="switchMainTab('tab-info')">資訊</div>
                    <div class="tab-btn" onclick="switchMainTab('tab-tools')">工具</div>
                </div>
            </div>
            
            <div id="countdown-widget" class="countdown-wrapper" style="display: none;">
                <div id="cd-mode" class="cd-mode">
                    <div class="cd-title">✈️ 距離出發還剩</div>
                    <div class="cd-timer">
                        <div class="cd-box"><span id="cd-day" class="cd-num">--</span><span class="cd-label">天</span></div>
                        <div class="cd-box"><span id="cd-hr" class="cd-num">--</span><span class="cd-label">時</span></div>
                        <div class="cd-box"><span id="cd-min" class="cd-num">--</span><span class="cd-label">分</span></div>
                        <div class="cd-box"><span id="cd-sec" class="cd-num">--</span><span class="cd-label">秒</span></div>
                    </div>
                </div>
                <div id="journey-mode" class="journey-mode">
                    <div id="journey-greeting" class="journey-greeting">✨ 旅程正式展開！</div>
                    <div class="journey-sub">
                        <span id="journey-location">目前位置分析中...</span>
                        <span id="journey-weather" class="journey-weather-badge"></span>
                    </div>
                </div>
            </div>
            
            <div id="nav-itinerary" class="sub-nav-wrapper"><div class="pill-scroll">{day_pills_html}</div></div>
            <div id="nav-info" class="sub-nav-wrapper" style="display: none;"><div class="pill-scroll">{info_pills_html}</div></div>
            
            <div class="content-area">
                <div id="tab-itinerary" class="main-tab active">{day_contents_html}</div>
                <div id="tab-info" class="main-tab">{info_contents_html}</div>
                
                <div id="tab-tools" class="main-tab">
                    <div class="split-card" onclick="window.open('{LIGHTSPLIT_URL}', '_blank')">
                        <div class="split-icon">💸</div>
                        <div class="split-info">
                            <div class="split-title">光速分帳 LightSplit</div>
                            <div class="split-desc">開啟專屬公費帳本</div>
                        </div>
                        <div class="split-arrow">↗</div>
                    </div>

                    <div class="city-header"><span class="city-date">Calculator</span><h2 class="city-title">外幣匯率換算</h2></div>
                    <div class="calc-wrapper">
                        <div class="calc-screen">
                            <select id="cur-select" class="currency-badge" onchange="updateCalc()">
                                <option value="EUR">🇪🇺 EUR</option><option value="CZK">🇨🇿 CZK</option><option value="HUF">🇭🇺 HUF</option>
                            </select>
                            <div id="calc-formula" class="calc-formula"></div>
                            <div id="calc-foreign" class="calc-foreign">0</div>
                            <div id="calc-twd" class="calc-twd">≈ NT$ 0</div>
                        </div>
                        <div class="calc-keypad" id="keypad">
                            <button class="key clear" onclick="pressKey('C')">C</button>
                            <button class="key op" onclick="pressKey('(')">(</button>
                            <button class="key op" onclick="pressKey(')')">)</button>
                            <button class="key op" onclick="pressKey('/')">÷</button>
                            <button class="key" onclick="pressKey('7')">7</button>
                            <button class="key" onclick="pressKey('8')">8</button>
                            <button class="key" onclick="pressKey('9')">9</button>
                            <button class="key op" onclick="pressKey('*')">×</button>
                            <button class="key" onclick="pressKey('4')">4</button>
                            <button class="key" onclick="pressKey('5')">5</button>
                            <button class="key" onclick="pressKey('6')">6</button>
                            <button class="key op" onclick="pressKey('-')">−</button>
                            <button class="key" onclick="pressKey('1')">1</button>
                            <button class="key" onclick="pressKey('2')">2</button>
                            <button class="key" onclick="pressKey('3')">3</button>
                            <button class="key op" onclick="pressKey('+')">+</button>
                            <button class="key" onclick="pressKey('0')">0</button>
                            <button class="key" onclick="pressKey('.')">.</button>
                            <button class="key" onclick="pressKey('DEL')">⌫</button>
                            <button class="key equal" onclick="pressKey('=')">=</button>
                        </div>
                    </div>
                    <div id="rate-hint" class="rate-status"><span class="dot offline"></span>載入匯率中...</div>
                </div>
            </div>
        </div>

        <script>
            function switchMainTab(tabId) {{
                document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
                event.target.classList.add('active');
                document.querySelectorAll('.main-tab').forEach(c => c.classList.remove('active'));
                document.getElementById(tabId).classList.add('active');
                document.getElementById('nav-itinerary').style.display = tabId === 'tab-itinerary' ? 'block' : 'none';
                document.getElementById('nav-info').style.display = tabId === 'tab-info' ? 'block' : 'none';
                window.scrollTo(0,0);
            }}

            function switchSubTab(targetId, element, contentClass) {{
                const parentNav = element.closest('.pill-scroll');
                parentNav.querySelectorAll('.sub-pill').forEach(p => p.classList.remove('active'));
                element.classList.add('active');
                const mainTab = document.getElementById(contentClass.includes('day') ? 'tab-itinerary' : 'tab-info');
                mainTab.querySelectorAll('.' + contentClass).forEach(c => c.style.display = 'none');
                
                const targetContent = document.getElementById(targetId);
                targetContent.style.display = 'block';
                
                let loc = targetContent.getAttribute('data-location');
                if (loc) {{
                    for (let zh of Object.keys(coords)) {{
                        if (loc.includes(zh)) {{ currentActiveCity = zh; break; }}
                    }}
                }}
                updateJourneyWeather(currentActiveCity);
                
                const offset = contentClass.includes('day') ? 250 : 145; 
                const elementPosition = targetContent.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.pageYOffset - offset;
                window.scrollTo({{ top: offsetPosition, behavior: 'smooth' }});
            }}

            function toggleCard(triggerElement) {{
                const card = triggerElement.closest('.ios-card');
                const body = card.querySelector('.card-body');
                const chevron = card.querySelector('.chevron');
                if (!card.querySelector('.card-desc').innerHTML.trim()) return;
                if (body.classList.contains('open')) {{
                    body.classList.remove('open');
                    triggerElement.classList.remove('open');
                }} else {{
                    body.classList.add('open');
                    triggerElement.classList.add('open');
                }}
            }}

            function toggleCheck(itemElement) {{ itemElement.classList.toggle('checked'); }}

            const coords = {{
                "布拉格": {{lat: 50.088, lon: 14.42}}, "維也納": {{lat: 48.208, lon: 16.37}},
                "薩爾斯堡": {{lat: 47.809, lon: 13.04}}, "哈修塔特": {{lat: 47.562, lon: 13.64}},
                "布達佩斯": {{lat: 47.497, lon: 19.04}}, "庫倫洛夫": {{lat: 48.812, lon: 14.31}},
                "CK": {{lat: 48.812, lon: 14.31}}, "國王湖": {{lat: 47.588, lon: 12.98}}, "慕尼黑": {{lat: 48.135, lon: 11.58}}
            }};
            function getWeatherEmoji(code) {{
                if(code === 0) return "☀️"; if(code <= 3) return "⛅"; if(code <= 48) return "🌫️";
                if(code <= 67) return "🌧️"; if(code <= 77) return "❄️"; if(code <= 82) return "🌨️";
                if(code >= 95) return "⛈️"; return "🌡️";
            }}
            function updateWeatherBadge(badgeElement, targetCoord) {{
                if (!targetCoord || !badgeElement) return;
                fetch(`https://api.open-meteo.com/v1/forecast?latitude=${{targetCoord.lat}}&longitude=${{targetCoord.lon}}&current_weather=true`)
                    .then(res => res.json())
                    .then(data => {{
                        if(data && data.current_weather) {{
                            let temp = Math.round(data.current_weather.temperature);
                            let emoji = getWeatherEmoji(data.current_weather.weathercode);
                            badgeElement.innerHTML = `${{emoji}} ${{temp}}°C`;
                            badgeElement.style.display = 'inline-block';
                        }}
                    }}).catch(() => {{ badgeElement.style.display = 'none'; }});
            }}

            document.querySelectorAll('.day-content').forEach(day => {{
                let loc = day.getAttribute('data-location');
                if(!loc) return;
                let targetCoord = null;
                for (let [zh, c] of Object.entries(coords)) {{
                    if (loc.includes(zh)) {{ targetCoord = c; break; }}
                }}
                let badge = day.querySelector('.weather-badge');
                if (targetCoord && badge) updateWeatherBadge(badge, targetCoord);
            }});
            
            function updateJourneyWeather(cityName) {{
                let targetCoord = coords[cityName];
                let journeyBadge = document.getElementById('journey-weather');
                if (targetCoord && journeyBadge) {{
                    updateWeatherBadge(journeyBadge, targetCoord);
                }} else if (journeyBadge) {{
                    journeyBadge.style.display = 'none';
                }}
            }}

            const targetDate = new Date("{TRIP_START_DATE}").getTime();
            const widgetWrapper = document.getElementById('countdown-widget');
            const cdMode = document.getElementById('cd-mode');
            const journeyMode = document.getElementById('journey-mode');
            let currentActiveCity = "維也納";

            function toggleWidgetVisibility(tabId) {{
                widgetWrapper.style.display = tabId === 'tab-itinerary' ? 'flex' : 'none';
            }}
            toggleWidgetVisibility('tab-itinerary');

            const timerInterval = setInterval(function() {{
                const now = new Date();
                const distance = targetDate - now.getTime();

                if (distance < 0) {{
                    clearInterval(timerInterval);
                    cdMode.style.display = 'none';
                    journeyMode.style.display = 'flex';
                    
                    let hour = now.getHours();
                    let greeting = "✨ 盡情享受專屬旅程！";
                    if (hour >= 5 && hour < 12) greeting = "☕ 早安！今天也是充滿期待的一天";
                    else if (hour >= 12 && hour < 18) greeting = "☀️ 午安！盡情享受美好的午後時光";
                    else if (hour >= 18 || hour < 5) greeting = "🌙 晚安！辛苦了，回飯店好好休息吧";
                    
                    document.getElementById('journey-greeting').innerText = greeting;
                    document.getElementById('journey-location').innerText = currentActiveCity;
                    updateJourneyWeather(currentActiveCity);
                    return;
                }}

                document.getElementById('cd-day').innerText = Math.floor(distance / (1000 * 60 * 60 * 24));
                document.getElementById('cd-hr').innerText = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)).toString().padStart(2, '0');
                document.getElementById('cd-min').innerText = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60)).toString().padStart(2, '0');
                document.getElementById('cd-sec').innerText = Math.floor((distance % (1000 * 60)) / 1000).toString().padStart(2, '0');
            }}, 1000);

            let currentFormula = "";
            let rates = {{ 'EUR': 34.50, 'CZK': 1.35, 'HUF': 0.088 }};
            let isResult = false;
            fetch('https://open.er-api.com/v6/latest/TWD')
                .then(res => res.json())
                .then(data => {{
                    if(data && data.rates) {{
                        rates['EUR'] = 1 / data.rates.EUR; rates['CZK'] = 1 / data.rates.CZK; rates['HUF'] = 1 / data.rates.HUF;
                        document.getElementById('rate-hint').innerHTML = `<span class="dot"></span>即時匯率: 1 EUR ≈ ${{rates['EUR'].toFixed(2)}} TWD`;
                        updateCalc();
                    }}
                }}).catch(() => {{
                    document.getElementById('rate-hint').innerHTML = `<span class="dot offline"></span>無網路，使用預設匯率`;
                }});

            function pressKey(key) {{
                let formulaDiv = document.getElementById('calc-formula');
                let displayDiv = document.getElementById('calc-foreign');
                if (key === 'C') {{ currentFormula = ""; displayDiv.innerText = "0"; formulaDiv.innerText = ""; isResult = false; }} 
                else if (key === 'DEL') {{
                    if (isResult) {{ currentFormula = ""; isResult = false; }}
                    else {{ currentFormula = currentFormula.slice(0, -1); }}
                    displayDiv.innerText = currentFormula || "0";
                }}
                else if (key === '=') {{
                    if (!currentFormula) return;
                    try {{
                        let evalResult = Function('"use strict";return (' + currentFormula + ')')();
                        if(!isFinite(evalResult)) throw "error";
                        formulaDiv.innerText = currentFormula + " =";
                        currentFormula = evalResult.toString();
                        displayDiv.innerText = Number(evalResult).toLocaleString('en-US', {{maximumFractionDigits: 2}});
                        isResult = true;
                    }} catch (e) {{ displayDiv.innerText = "Error"; currentFormula = ""; }}
                }}
                else {{
                    if (isResult && !['+', '-', '*', '/'].includes(key)) {{ currentFormula = key; }} 
                    else {{ currentFormula += key; }}
                    isResult = false;
                    displayDiv.innerText = currentFormula;
                }}
                if(currentFormula.length > 12) {{ displayDiv.style.fontSize = "30px"; }} else {{ displayDiv.style.fontSize = "42px"; }}
                updateCalc();
            }}

            function updateCalc() {{
                let cur = document.getElementById('cur-select').value;
                let valToCalc = 0;
                if (currentFormula) {{
                    try {{ valToCalc = Function('"use strict";return (' + currentFormula + ')')(); if(!isFinite(valToCalc)) valToCalc = 0; }} 
                    catch (e) {{ valToCalc = 0; }}
                }}
                let twd = valToCalc * rates[cur];
                document.getElementById('calc-twd').innerText = '≈ NT$ ' + twd.toLocaleString('en-US', {{maximumFractionDigits: 0}});
                let curStatus = document.getElementById('rate-hint').innerHTML.includes('即時') ? '即時' : '預設';
                let dotClass = curStatus === '即時' ? 'dot' : 'dot offline';
                document.getElementById('rate-hint').innerHTML = `<span class="${{dotClass}}"></span>${{curStatus}}匯率: 1 ${{cur}} ≈ ${{rates[cur].toFixed(2)}} TWD`;
            }}
        </script>
    </body>
    </html>
    """
    return html_content

# ==========================================
# 3. Streamlit 渲染 (🚀 高度交給 CSS 控制，不依賴 JS 縮放)
# ==========================================
with st.spinner('🌍 正在同步最新行程與圖片，請稍候...'):
    final_html = fetch_trello_data()

# 🍏 關鍵解藥：scrolling=True 讓 iframe 自己處理滾動，避開 Safari 記憶體超載
components.html(final_html, height=850, scrolling=True)

if st.button("↻"):
    fetch_trello_data.clear() 
    st.rerun()
