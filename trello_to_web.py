import streamlit as st
import streamlit.components.v1 as components
import requests
import re
import base64
import concurrent.futures

# ==========================================
# 0. Streamlit 頁面設定
# ==========================================
st.set_page_config(page_title="奧捷德匈 專屬旅程", page_icon="🌍", layout="centered")

# ==========================================
# 1. 🔒 安全讀取機密憑證 (Secrets)
# ==========================================
try:
    API_KEY = st.secrets["TRELLO_API_KEY"]
    TOKEN = st.secrets["TRELLO_TOKEN"]
    BOARD_ID = st.secrets["TRELLO_BOARD_ID"]
except KeyError:
    st.error("❌ 找不到 API 憑證！請確認本地端有設定 `.streamlit/secrets.toml`，或雲端有設定 Secrets。")
    st.stop()  # 找不到密碼就停止執行，保護程式不崩潰


# ==========================================
# 2. 核心工具與極速下載器
# ==========================================
@st.cache_data(ttl=600, show_spinner=False)
def fetch_trello_data():
    def parse_markdown(text):
        if not text: return ""
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
        return "<div style='text-align:center; padding:50px;'>❌ 無法連線到 Trello，請檢查 API 設定。</div>"

    lists = lists_res.json()
    all_cards = cards_res.json()

    url_set = set()
    card_to_url = {}
    cards_by_list = {}

    for c in all_cards:
        lid = c['idList']
        if lid not in cards_by_list: cards_by_list[lid] = []
        cards_by_list[lid].append(c)

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
                if 'image' in att.get('mimeType', '') or att.get('url', '').lower().endswith(('.png', '.jpg', '.jpeg')):
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
            u = future_to_url[future]
            try:
                url_to_base64[u] = future.result()
            except Exception:
                url_to_base64[u] = None

    days_data, info_data = [], []
    for lst in lists:
        list_name = lst['name']
        cards = cards_by_list.get(lst['id'], [])
        cards_html = ""

        for card in cards:
            card_name = card.get("name", "")
            card_desc = parse_markdown(card.get("desc", "").strip())

            target_url = card_to_url.get(card['id'])
            img_src = url_to_base64.get(target_url) if target_url else None

            img_html = f'<img src="{img_src}" class="card-cover-img">' if img_src else ''
            has_desc = bool(card_desc)
            chevron_html = '<span class="chevron"></span>' if has_desc else ''
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

        if not cards_html: cards_html = '<div class="empty-state">尚無內容</div>'

        list_id = f"section_{lst['id']}"
        if list_name.startswith("D0") or list_name.startswith("D1"):
            match = re.search(r'(D\d+)\s*(\([^\)]+\)\s*\d+/\d+)?\s*(.*)', list_name)
            if match:
                short_name, date_info, location = match.group(1).strip(), (match.group(2) or "").strip(), (
                            match.group(3) or "行程").strip()
            else:
                short_name, date_info, location = list_name.split(' ')[0], "", list_name
            days_data.append({'id': list_id, 'short_name': short_name, 'date_info': date_info, 'location': location,
                              'html': cards_html})
        else:
            info_data.append({'id': list_id, 'short_name': list_name, 'html': cards_html})

    day_pills_html, day_contents_html = "", ""
    for i, day in enumerate(days_data):
        active, display = ("active", "block") if i == 0 else ("", "none")
        day_pills_html += f'<div class="sub-pill {active}" onclick="switchSubTab(\'{day["id"]}\', this, \'day-content\')">{day["short_name"]}</div>'
        day_contents_html += f"""
        <div id="{day['id']}" class="day-content sub-content" style="display: {display};">
            <div class="city-header"><span class="city-date">{day['date_info']}</span><h2 class="city-title">{day['location']}</h2></div>
            <div class="card-list">{day['html']}</div>
        </div>
        """

    info_pills_html, info_contents_html = "", ""
    for i, info in enumerate(info_data):
        active, display = ("active", "block") if i == 0 else ("", "none")
        info_pills_html += f'<div class="sub-pill {active}" onclick="switchSubTab(\'{info["id"]}\', this, \'info-content\')">{info["short_name"]}</div>'
        info_contents_html += f"""
        <div id="{info['id']}" class="info-content sub-content" style="display: {display};">
            <div class="city-header"><h2 class="city-title" style="color:#007AFF;">{info['short_name']}</h2></div>
            <div class="card-list">{info['html']}</div>
        </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-TW">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <style>
            ::-webkit-scrollbar {{ display: none; }}
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif; -webkit-tap-highlight-color: transparent; }}
            body {{ background-color: #F5F5F7; color: #1D1D1F; }}
            .app {{ width: 100%; max-width: 500px; margin: 0 auto; background-color: #F5F5F7; min-height: 100vh; padding-bottom: 40px; }}
            .nav-bar {{ background: rgba(245, 245, 247, 0.85); backdrop-filter: blur(20px); position: sticky; top: 0; z-index: 100; padding: 16px 20px 10px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(0,0,0,0.05); }}
            .nav-title {{ font-size: 22px; font-weight: 700; }}
            .tab-switcher {{ display: flex; background: #E3E3E8; border-radius: 9px; padding: 3px; }}
            .tab-btn {{ padding: 6px 14px; font-size: 13px; font-weight: 600; color: #86868B; border-radius: 7px; cursor: pointer; transition: 0.2s; }}
            .tab-btn.active {{ background: #FFFFFF; color: #1D1D1F; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            .sub-nav-wrapper {{ background: rgba(245, 245, 247, 0.95); position: sticky; top: 62px; z-index: 90; padding: 12px 20px; border-bottom: 1px solid rgba(0,0,0,0.05); }}
            .pill-scroll {{ display: flex; overflow-x: auto; gap: 8px; scrollbar-width: none; }}
            .sub-pill {{ padding: 8px 16px; background: #E3E3E8; color: #86868B; font-size: 14px; font-weight: 600; border-radius: 20px; white-space: nowrap; cursor: pointer; transition: 0.3s; }}
            .sub-pill.active {{ background: #007AFF; color: #FFFFFF; font-weight: 700; box-shadow: 0 4px 10px rgba(0, 122, 255, 0.3); }}
            .content-area {{ padding: 24px 20px; }}
            .main-tab {{ display: none; }}
            .main-tab.active {{ display: block; }}
            .city-header {{ margin-bottom: 24px; padding-left: 4px; }}
            .city-date {{ font-size: 13px; font-weight: 600; color: #007AFF; text-transform: uppercase; margin-bottom: 4px; display: block; }}
            .city-title {{ font-size: 32px; font-weight: 800; letter-spacing: -0.5px; line-height: 1.1; }}
            .card-list {{ display: flex; flex-direction: column; gap: 20px; }}
            .ios-card {{ background: #FFFFFF; border-radius: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.04); overflow: hidden; }}
            .card-cover-img {{ width: 100%; height: auto; max-height: 320px; object-fit: contain; background-color: #FFFFFF; display: block; border-bottom: 1px solid rgba(0,0,0,0.05); }}
            .card-header {{ padding: 20px; display: flex; justify-content: space-between; align-items: flex-start; }}
            .card-title {{ font-size: 18px; font-weight: 700; line-height: 1.3; margin-right: 12px; }}
            .chevron {{ width: 24px; height: 24px; background: #F5F5F7; border-radius: 50%; display: flex; justify-content: center; align-items: center; transition: 0.3s; flex-shrink: 0; }}
            .chevron::after {{ content: ''; width: 8px; height: 8px; border-right: 2px solid #86868B; border-bottom: 2px solid #86868B; transform: translateY(-2px) rotate(45deg); }}
            .open .chevron {{ transform: rotate(180deg); background: #007AFF; }}
            .open .chevron::after {{ border-color: #FFFFFF; transform: translateY(2px) rotate(45deg); }}
            .card-body {{ display: grid; grid-template-rows: 0fr; transition: grid-template-rows 0.3s ease; }}
            .card-body.open {{ grid-template-rows: 1fr; }}
            .card-content {{ overflow: hidden; }}
            .card-desc {{ padding: 0 20px 24px; font-size: 15px; color: #48484A; line-height: 1.6; word-wrap: break-word; }}
            .custom-ul {{ margin: 10px 0 10px 20px; padding: 0; }}
            .custom-ul li {{ margin-bottom: 8px; list-style-type: disc; color: #48484A; }}
            .highlight-text {{ font-weight: 700; color: #1D1D1F; box-shadow: inset 0 -8px 0 rgba(255, 204, 0, 0.4); }}
            .action-btn {{ display: inline-block; margin-top: 16px; margin-right: 8px; padding: 10px 18px; background: #F5F5F7; color: #007AFF; text-decoration: none; font-size: 14px; font-weight: 600; border-radius: 100px; transition: 0.2s; }}
            .empty-state {{ text-align: center; color: #86868B; padding: 40px 0; font-size: 15px; }}
        </style>
    </head>
    <body>
        <div class="app">
            <div class="nav-bar">
                <h1 class="nav-title">奧捷德匈</h1>
                <div class="tab-switcher">
                    <div class="tab-btn active" onclick="switchMainTab('tab-itinerary')">行程</div>
                    <div class="tab-btn" onclick="switchMainTab('tab-info')">資訊</div>
                </div>
            </div>
            <div id="nav-itinerary" class="sub-nav-wrapper"><div class="pill-scroll">{day_pills_html}</div></div>
            <div id="nav-info" class="sub-nav-wrapper" style="display: none;"><div class="pill-scroll">{info_pills_html}</div></div>
            <div class="content-area">
                <div id="tab-itinerary" class="main-tab active">{day_contents_html}</div>
                <div id="tab-info" class="main-tab">{info_contents_html}</div>
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
                window.scrollTo(0,0);
            }}
            function toggleCard(triggerElement) {{
                const card = triggerElement.closest('.ios-card');
                const body = card.querySelector('.card-body');
                const chevron = card.querySelector('.chevron');
                if (!chevron.innerHTML && !chevron.classList.length) return;
                if (body.classList.contains('open')) {{
                    body.classList.remove('open');
                    triggerElement.classList.remove('open');
                }} else {{
                    body.classList.add('open');
                    triggerElement.classList.add('open');
                }}
            }}
        </script>
    </body>
    </html>
    """
    return html_content


# ==========================================
# 3. Streamlit 渲染區
# ==========================================
with st.spinner('🌍 正在同步最新行程與圖片，請稍候...'):
    final_html = fetch_trello_data()

components.html(final_html, height=850, scrolling=True)

st.markdown("---")
if st.button("🔄 強制刷新 Trello 最新資料"):
    fetch_trello_data.clear()
    st.rerun()