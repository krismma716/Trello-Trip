import streamlit as st
import streamlit.components.v1 as components
import requests
import re
import base64
import concurrent.futures

# ==========================================
# 0. 介面全螢幕沉浸化 + 隱形更新按鈕
# ==========================================
st.set_page_config(page_title="奧捷德匈 專屬旅程", page_icon="✈️", layout="wide")

st.markdown("""
    <style>
        header {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {
            padding: 0 !important;
            max-width: 100% !important;
        }
        iframe { border: none !important; width: 100% !important; }
        .stDeployButton {display:none;}

        div[data-testid="stButton"] {
            display: flex;
            justify-content: center;
            padding: 20px 0 40px 0;
            background-color: #F9FAFC;
        }
        div[data-testid="stButton"] button {
            background-color: transparent !important;
            color: #C7C7CC !important;
            border: none !important;
            box-shadow: none !important;
            font-weight: 500 !important;
            font-size: 13px !important;
            letter-spacing: 1px !important;
            transition: all 0.3s ease !important;
        }
        div[data-testid="stButton"] button:hover { color: #FF5A5F !important; background-color: transparent !important; }
        div[data-testid="stButton"] button:active { transform: scale(0.95) !important; }
    </style>
""", unsafe_allow_html=True)

try:
    API_KEY = st.secrets["TRELLO_API_KEY"]
    TOKEN = st.secrets["TRELLO_TOKEN"]
    BOARD_ID = st.secrets["TRELLO_BOARD_ID"]
except KeyError:
    st.error("❌ 找不到 API 憑證！請確認 Secrets 設定。")
    st.stop()


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
        text = re.sub(r'\[([^\]]+)\]\((https?://[^\)]+)\)', r'<a href="\2" target="_blank" class="action-btn">📍 \1</a>',
                      text)
        text = re.sub(r'(?<!=")(https?://[^\s<]+)(?!">)',
                      r'<a href="\1" target="_blank" class="action-btn">🔗 點擊連結</a>', text)
        lines = text.split('\n')
        html_lines, in_list = [], False
        for line in lines:
            if line.strip().startswith(('- ', '* ')):
                if not in_list:
                    html_lines.append('<ul class="custom-ul">')
                    in_list = True
                html_lines.append(f'<li>{line.strip()[2:]}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(line)
        if in_list: html_lines.append('</ul>')
        return '<br>'.join(html_lines).replace('</ul><br>', '</ul>').replace('<br><ul', '<ul')

    def download_real_attachment(url):
        if not url: return None
        try:
            if "trello.com" in url:
                headers = {"Authorization": f'OAuth oauth_consumer_key="{API_KEY}", oauth_token="{TOKEN}"'}
                res = requests.get(url, headers=headers, allow_redirects=False, timeout=5)
                if res.status_code in [301, 302, 303, 307, 308]:
                    aws_url = res.headers.get('Location')
                    final_res = requests.get(aws_url, timeout=10)
                else:
                    final_res = res
            else:
                final_res = requests.get(url, timeout=10)

            if final_res.status_code == 200:
                ctype = final_res.headers.get('Content-Type', 'image/jpeg')
                b64 = base64.b64encode(final_res.content).decode('utf-8')
                return f"data:{ctype};base64,{b64}"
        except Exception:
            pass
        return None

    lists_res = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/lists",
                             params={'key': API_KEY, 'token': TOKEN})
    cards_res = requests.get(f"https://api.trello.com/1/boards/{BOARD_ID}/cards",
                             params={'key': API_KEY, 'token': TOKEN, 'attachments': 'true'})

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
                        img_url = att['url']
                        break
            if not img_url and attachments:
                for att in attachments:
                    if 'image' in att.get('mimeType', '') or att.get('url', '').lower().endswith(
                            ('.png', '.jpg', '.jpeg')):
                        img_url = att['url']
                        break
            if not img_url and c.get('cover', {}).get('sharedSourceUrl'):
                img_url = c['cover']['sharedSourceUrl']
            if img_url:
                url_set.add(img_url)
                card_to_url[c['id']] = img_url

    url_to_base64 = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(download_real_attachment, u): u for u in url_set}
        for future in concurrent.futures.as_completed(future_to_url):
            try:
                url_to_base64[future_to_url[future]] = future.result()
            except Exception:
                url_to_base64[future_to_url[future]] = None

    days_data, info_data = [], []
    for lst in lists:
        list_name = clean_text(lst['name'])
        cards = cards_by_list.get(lst['id'], [])
        cards_html = ""
        for card in cards:
            card_name = clean_text(card.get("name", ""))
            card_desc = parse_markdown(card.get("desc", "").strip())

            target_url = card_to_url.get(card['id'])
            img_src = url_to_base64.get(target_url) if target_url else None

            img_html = f'<img src="{img_src}" class="card-cover-img">' if img_src else ''
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

            days_data.append(
                {'id': list_id, 'short_name': short_name, 'subtitle': capsule_subtitle, 'date_info': date_info,
                 'location': location, 'html': cards_html})
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
        info_pills_html += f'<div class="sub-pill info-pill {active}" onclick="switchSubTab(\'{info["id"]}\', this, \'info-content\')">{info["short_name"]}</div>'
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
            @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@600;800&family=Noto+Sans+TC:wght@500;700;900&display=swap');

            ::-webkit-scrollbar {{ display: none; }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Nunito', 'Noto Sans TC', sans-serif; -webkit-tap-highlight-color: transparent; }}
            body {{ background-color: #F9FAFC; color: #2D3142; user-select: none; }}
            .app {{ width: 100%; max-width: 500px; margin: 0 auto; background-color: #F9FAFC; min-height: 100vh; overflow-x: hidden; }}

            /* 🏝️ 頂部主導航：固定在最上面 */
            .nav-bar {{ background: rgba(249, 250, 252, 0.85); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); position: sticky; top: 0; z-index: 100; padding: 20px 20px 12px; display: flex; justify-content: space-between; align-items: center; }}
            .nav-title {{ font-size: 22px; font-weight: 900; background: linear-gradient(135deg, #FF5A5F 0%, #FF7E67 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; letter-spacing: 0.5px; }}
            .tab-switcher {{ display: flex; background: #EFEFF4; border-radius: 12px; padding: 4px; box-shadow: inset 0 2px 4px rgba(0,0,0,0.02); }}
            .tab-btn {{ padding: 8px 14px; font-size: 13px; font-weight: 700; color: #9094A6; border-radius: 10px; cursor: pointer; transition: 0.3s cubic-bezier(0.4, 0, 0.2, 1); }}
            .tab-btn.active {{ background: #FFFFFF; color: #FF5A5F; box-shadow: 0 4px 10px rgba(0,0,0,0.06); transform: scale(1.02); }}

            /* 💊 子導航膠囊列：這就是你要的凍結窗格！ */
            /* 讓它貼在 top: 68px (剛好在導航列下方)，並加上毛玻璃效果與底線，區隔內容 */
            .sub-nav-wrapper {{ background: rgba(249, 250, 252, 0.95); backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px); position: sticky; top: 68px; z-index: 90; padding: 12px 20px 16px; border-bottom: 1px solid rgba(0,0,0,0.05); }}
            .pill-scroll {{ display: flex; overflow-x: auto; gap: 12px; scrollbar-width: none; padding-bottom: 4px; align-items: center; }}

            /* 解決換行問題：加寬 min-width，並且強制文字不換行 */
            .sub-pill {{ display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 8px 18px; background: #FFFFFF; border-radius: 18px; min-width: 68px; cursor: pointer; transition: 0.3s; box-shadow: 0 2px 8px rgba(0,0,0,0.02); border: 1px solid #F0F0F5; }}
            .pill-title {{ font-size: 16px; font-weight: 800; color: #5B5F71; }}

            /* 讓 subtitle 超過 4 個字會變成點點點，絕對不會換行破壞版面 */
            .pill-subtitle {{ font-size: 10px; font-weight: 600; color: #9094A6; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 50px; text-align: center; }}

            .sub-pill.active {{ background: linear-gradient(135deg, #FF7E67 0%, #FF5A5F 100%); box-shadow: 0 6px 16px rgba(255, 90, 95, 0.3); border: none; transform: translateY(-2px); }}
            .sub-pill.active .pill-title {{ color: #FFFFFF; }}
            .sub-pill.active .pill-subtitle {{ color: rgba(255,255,255,0.8); }}

            .info-pill {{ flex-direction: row; padding: 10px 20px; }}
            .info-pill .pill-subtitle {{ display: none; }}
            .info-pill .pill-title {{ font-size: 14px; font-weight: 700; }}

            .content-area {{ padding: 24px 20px; }}
            .main-tab {{ display: none; }}
            .main-tab.active {{ display: block; animation: fadeUp 0.4s cubic-bezier(0.4, 0, 0.2, 1); }}
            @keyframes fadeUp {{ from {{ opacity: 0; transform: translateY(15px); }} to {{ opacity: 1; transform: translateY(0); }} }}

            .city-header {{ margin-bottom: 30px; padding-left: 4px; margin-top: 5px; }}
            .date-row {{ display: flex; align-items: center; margin-bottom: 8px; }}
            .city-date {{ font-size: 13px; font-weight: 800; color: #FF7E67; letter-spacing: 1px; }}
            .weather-badge {{ background: #E8F0FE; color: #007AFF; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 800; margin-left: 12px; display: none; }}
            .city-title {{ font-size: 30px; font-weight: 900; letter-spacing: -0.5px; line-height: 1.2; color: #2D3142; }}
            .highlight-title {{ color: #FF5A5F; }}

            .card-list {{ display: flex; flex-direction: column; gap: 24px; }}
            .ios-card {{ background: #FFFFFF; border-radius: 24px; box-shadow: 0 12px 30px rgba(45, 49, 66, 0.06); overflow: hidden; transition: 0.3s; border: 1px solid rgba(0,0,0,0.01); }}
            .card-cover-img {{ width: 100%; height: auto; max-height: 280px; object-fit: contain; background-color: #F9FAFC; display: block; border-bottom: 1px solid rgba(0,0,0,0.02); }}
            .card-header {{ padding: 22px; display: flex; justify-content: space-between; align-items: center; }}
            .card-title {{ font-size: 18px; font-weight: 800; line-height: 1.4; margin-right: 12px; color: #2D3142; }}
            .chevron {{ width: 32px; height: 32px; background: #FFF0F0; border-radius: 50%; display: flex; justify-content: center; align-items: center; transition: 0.4s cubic-bezier(0.4, 0, 0.2, 1); flex-shrink: 0; }}
            .chevron::after {{ content: ''; width: 8px; height: 8px; border-right: 3px solid #FF5A5F; border-bottom: 3px solid #FF5A5F; transform: translateY(-2px) rotate(45deg); transition: 0.3s; }}
            .open .chevron {{ transform: rotate(180deg); background: #FF5A5F; box-shadow: 0 4px 10px rgba(255, 90, 95, 0.3); }}
            .open .chevron::after {{ border-color: #FFFFFF; transform: translateY(2px) rotate(45deg); }}

            .card-body {{ display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.4s cubic-bezier(0.4, 0, 0.2, 1); }}
            .card-body.open {{ grid-template-rows: 1fr; border-top: 1px dashed #F0F0F5; }}
            .card-content {{ overflow: hidden; }}
            .card-desc {{ padding: 0 22px 26px; font-size: 15px; color: #5B5F71; line-height: 1.7; word-wrap: break-word; margin-top: 18px; user-select: text; }}

            .custom-ul {{ margin: 12px 0 12px 24px; padding: 0; }}
            .custom-ul li {{ margin-bottom: 10px; list-style-type: none; position: relative; color: #5B5F71; }}
            .custom-ul li::before {{ content: '✨'; position: absolute; left: -22px; font-size: 12px; top: 2px; }}
            .highlight-text {{ font-weight: 800; color: #2D3142; background: linear-gradient(120deg, #FFD166 0%, #FFD166 100%); background-repeat: no-repeat; background-size: 100% 35%; background-position: 0 90%; padding: 0 2px; }}
            .action-btn {{ display: inline-flex; align-items: center; margin-top: 15px; margin-right: 10px; padding: 12px 20px; background: #FFF0F0; color: #FF5A5F; text-decoration: none; font-size: 14px; font-weight: 800; border-radius: 14px; transition: 0.2s; }}
            .action-btn:active {{ transform: scale(0.95); }}
            .empty-state {{ text-align: center; color: #B0B3C6; padding: 40px 0; font-size: 16px; font-weight: 700; }}

            .calc-wrapper {{ background: #FFFFFF; border-radius: 32px; padding: 24px; box-shadow: 0 16px 40px rgba(45, 49, 66, 0.08); display: flex; flex-direction: column; gap: 20px; border: 1px solid rgba(0,0,0,0.02); }}
            .calc-screen {{ background: #F9FAFC; border-radius: 20px; padding: 24px; text-align: right; display: flex; flex-direction: column; justify-content: flex-end; position: relative; border: 1px solid #F0F0F5; }}
            .currency-badge {{ position: absolute; top: 20px; left: 20px; background: #FFFFFF; border: none; padding: 8px 14px; border-radius: 12px; font-size: 15px; font-weight: 800; color: #FF5A5F; box-shadow: 0 4px 12px rgba(0,0,0,0.05); outline: none; -webkit-appearance: none; cursor: pointer; }}
            .calc-formula {{ font-size: 16px; color: #9094A6; min-height: 24px; font-weight: 700; margin-top: 20px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
            .calc-foreign {{ font-size: 42px; font-weight: 900; color: #2D3142; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; letter-spacing: -1px; margin-bottom: 5px; }}
            .calc-twd {{ font-size: 18px; font-weight: 800; color: #06D6A0; background: rgba(6, 214, 160, 0.1); display: inline-block; padding: 4px 12px; border-radius: 10px; align-self: flex-end; }}
            .calc-keypad {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }}
            .key {{ background: #FFFFFF; color: #2D3142; font-size: 22px; font-weight: 700; border-radius: 50%; aspect-ratio: 1/1; border: none; text-align: center; transition: 0.15s; cursor: pointer; display: flex; justify-content: center; align-items: center; box-shadow: 0 4px 12px rgba(0,0,0,0.04); touch-action: manipulation; }}
            .key:active {{ transform: scale(0.9); box-shadow: 0 1px 4px rgba(0,0,0,0.02); background: #F0F0F5; }}
            .key.op {{ color: #FF7E67; font-size: 26px; background: #FFF0F0; box-shadow: none; }}
            .key.op:active {{ background: #FFE0E0; }}
            .key.equal {{ background: linear-gradient(135deg, #FF7E67 0%, #FF5A5F 100%); color: #FFFFFF; font-size: 30px; box-shadow: 0 8px 20px rgba(255, 90, 95, 0.4); }}
            .key.equal:active {{ box-shadow: 0 4px 10px rgba(255, 90, 95, 0.3); }}
            .key.clear {{ color: #FF5A5F; font-weight: 800; background: #FFF0F0; box-shadow: none; }}
            .rate-status {{ text-align: center; font-size: 13px; color: #9094A6; font-weight: 700; margin-top: 10px; }}
            .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #06D6A0; margin-right: 6px; vertical-align: middle; box-shadow: 0 0 8px rgba(6, 214, 160, 0.6); }}
            .dot.offline {{ background: #FFD166; box-shadow: 0 0 8px rgba(255, 209, 102, 0.6); }}
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

            <div id="nav-itinerary" class="sub-nav-wrapper"><div class="pill-scroll">{day_pills_html}</div></div>
            <div id="nav-info" class="sub-nav-wrapper" style="display: none;"><div class="pill-scroll">{info_pills_html}</div></div>

            <div class="content-area">
                <div id="tab-itinerary" class="main-tab active">{day_contents_html}</div>
                <div id="tab-info" class="main-tab">{info_contents_html}</div>

                <div id="tab-tools" class="main-tab">
                    <div class="city-header">
                        <span class="city-date">Calculator</span>
                        <h2 class="city-title">外幣匯率換算</h2>
                    </div>
                    <div class="calc-wrapper">
                        <div class="calc-screen">
                            <select id="cur-select" class="currency-badge" onchange="updateCalc()">
                                <option value="EUR">🇪🇺 EUR</option>
                                <option value="CZK">🇨🇿 CZK</option>
                                <option value="HUF">🇭🇺 HUF</option>
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
                document.getElementById(targetId).style.display = 'block';
                element.scrollIntoView({{ behavior: 'smooth', block: 'nearest', inline: 'center' }});

                // 💡 計算導航列高度，讓畫面捲動到剛好標題的位置
                const offset = 140; 
                const elementPosition = document.getElementById(targetId).getBoundingClientRect().top;
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

            const coords = {{
                "布拉格": {{lat: 50.088, lon: 14.42}}, "維也納": {{lat: 48.208, lon: 16.37}},
                "薩爾斯堡": {{lat: 47.809, lon: 13.04}}, "哈修塔特": {{lat: 47.562, lon: 13.64}},
                "布達佩斯": {{lat: 47.497, lon: 19.04}}, "庫倫洛夫": {{lat: 48.812, lon: 14.31}},
                "CK": {{lat: 48.812, lon: 14.31}}, "國王湖": {{lat: 47.588, lon: 12.98}},
                "慕尼黑": {{lat: 48.135, lon: 11.58}}
            }};

            function getWeatherEmoji(code) {{
                if(code === 0) return "☀️";
                if(code >= 1 && code <= 3) return "⛅";
                if(code >= 45 && code <= 48) return "🌫️";
                if(code >= 51 && code <= 67) return "🌧️";
                if(code >= 71 && code <= 77) return "❄️";
                if(code >= 80 && code <= 82) return "🌨️";
                if(code >= 95) return "⛈️";
                return "🌡️";
            }}

            document.querySelectorAll('.day-content').forEach(day => {{
                let loc = day.getAttribute('data-location');
                if(!loc) return;
                let targetCoord = null;
                for (let [zh, c] of Object.entries(coords)) {{
                    if (loc.includes(zh)) {{ targetCoord = c; break; }}
                }}
                if (targetCoord) {{
                    fetch(`https://api.open-meteo.com/v1/forecast?latitude=${{targetCoord.lat}}&longitude=${{targetCoord.lon}}&current_weather=true`)
                        .then(res => res.json())
                        .then(data => {{
                            if(data && data.current_weather) {{
                                let temp = Math.round(data.current_weather.temperature);
                                let emoji = getWeatherEmoji(data.current_weather.weathercode);
                                let badge = day.querySelector('.weather-badge');
                                badge.innerHTML = `${{emoji}} ${{temp}}°C`;
                                badge.style.display = 'inline-block';
                            }}
                        }}).catch(() => {{}});
                }}
            }});

            let currentFormula = "";
            let rates = {{ 'EUR': 34.50, 'CZK': 1.35, 'HUF': 0.088 }};
            let isResult = false;

            fetch('https://open.er-api.com/v6/latest/TWD')
                .then(res => res.json())
                .then(data => {{
                    if(data && data.rates) {{
                        rates['EUR'] = 1 / data.rates.EUR;
                        rates['CZK'] = 1 / data.rates.CZK;
                        rates['HUF'] = 1 / data.rates.HUF;
                        document.getElementById('rate-hint').innerHTML = `<span class="dot"></span>即時匯率: 1 EUR ≈ ${{rates['EUR'].toFixed(2)}} TWD`;
                        updateCalc();
                    }}
                }}).catch(() => {{
                    document.getElementById('rate-hint').innerHTML = `<span class="dot offline"></span>無網路，使用安全預設匯率`;
                }});

            function pressKey(key) {{
                let formulaDiv = document.getElementById('calc-formula');
                let displayDiv = document.getElementById('calc-foreign');
                if (key === 'C') {{
                    currentFormula = "";
                    displayDiv.innerText = "0";
                    formulaDiv.innerText = "";
                    isResult = false;
                }} 
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
                    }} catch (e) {{
                        displayDiv.innerText = "Error";
                        currentFormula = "";
                    }}
                }}
                else {{
                    if (isResult && !['+', '-', '*', '/'].includes(key)) {{ currentFormula = key; }} 
                    else {{ currentFormula += key; }}
                    isResult = false;
                    displayDiv.innerText = currentFormula;
                }}
                if(currentFormula.length > 12) {{ displayDiv.style.fontSize = "30px"; }} 
                else {{ displayDiv.style.fontSize = "42px"; }}
                updateCalc();
            }}

            function updateCalc() {{
                let cur = document.getElementById('cur-select').value;
                let valToCalc = 0;
                if (currentFormula) {{
                    try {{
                        valToCalc = Function('"use strict";return (' + currentFormula + ')')();
                        if(!isFinite(valToCalc)) valToCalc = 0;
                    }} catch (e) {{ valToCalc = 0; }}
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
# 3. Streamlit 渲染
# ==========================================
with st.spinner('🌍 正在同步最新行程與圖片，請稍候...'):
    final_html = fetch_trello_data()

components.html(final_html, height=1400, scrolling=True)

# 🤫 把更新按鈕變成隱形的浮水印文字 (滑到最底才看得到)
if st.button("↻ 同步資料"):
    fetch_trello_data.clear()
    st.rerun()
