import os
import json
import time
import datetime
import re
import pytz
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def diagnostic_list_models(client):
    """
    [自動診斷工具] 查詢這把 API Key 到底可以使用哪些模型
    """
    print("\n🔍 [系統診斷] 正在向 Google 查詢此 API Key 可用的模型清單...")
    try:
        models = client.models.list()
        available_models = []
        for m in models:
            if 'generateContent' in m.supported_actions:
                clean_name = m.name.replace('models/', '')
                available_models.append(clean_name)
        
        if available_models:
            print(f"✅ 您的 API Key 支援以下 {len(available_models)} 個模型：")
            print(", ".join(available_models))
        else:
            print("❌ 警告：您的 API Key 無法存取任何文字生成模型！這通常是因為帳號權限或地區限制。")
            
    except Exception as e:
        print(f"❌ 查詢模型清單失敗，您的金鑰或連線被阻擋: {e}")
    print("-" * 50 + "\n")


def score_and_sort_articles(client, news_data):
    """
    使用 Gemini 模型為新聞評分 (1-10)，依對在越華人/台商的重要性排序。
    """
    all_articles = []
    for source, articles in news_data.items():
        for a in articles:
            a['source_name'] = source
            all_articles.append(a)
    
    if not all_articles:
        return []

    articles_list_text = ""
    for i, a in enumerate(all_articles):
        articles_list_text += f"ID: {i} | Title: {a['title']}\nSummary: {a['summary']}\n\n"

    scoring_prompt = f"""
    You are an expert news editor for a daily Chinese-language podcast targeting Taiwanese businesspeople (台商) and Chinese-speaking professionals living in Vietnam.
    Score the following news articles from 1 to 10 based on their importance for this target audience.
    
    SCORING CRITERIA:
    - 9-10: VND exchange rate moves, State Bank of Vietnam (SBV) policies, major FDI announcements, significant supply chain shifts, labor law or visa changes for foreigners.
    - 7-8: Macroeconomic updates (GDP, inflation), major infrastructure projects, significant industry news (manufacturing, tech).
    - 5-6: Local business news, real estate trends in major cities (Hanoi, HCMC), cross-border trade updates.
    - 1-4: Minor local events, lifestyle, general interest.
    
    IMPORTANT: If multiple articles discuss the same topic or event, give them a "Frequency Bonus" (+1 or +2).
    VND exchange rate and FDI manufacturing news ALWAYS score highly.
    
    OUTPUT FORMAT:
    You MUST output ONLY a raw JSON array. DO NOT wrap it in ```json blocks. DO NOT add any conversational text.
    Example:
    [
      {{"id": 0, "score": 8}},
      {{"id": 1, "score": 5}}
    ]
    
    ARTICLES:
    {articles_list_text}
    """

    scoring_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "id": {"type": "INTEGER"},
                "score": {"type": "INTEGER"}
            },
            "required": ["id", "score"]
        }
    }

    models_to_try = ['gemini-2.5-flash', 'gemini-3.5-flash', 'gemini-2.5-pro', 'gemini-2.5-flash-lite']
    response = None
    
    for model_name in models_to_try:
        try:
            print(f"正在使用 {model_name} 為 {len(all_articles)} 則新聞進行重要性評分...")
            response = client.models.generate_content(
                model=model_name,
                contents=scoring_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    response_schema=scoring_schema
                )
            )
            if response:
                print(f"  ✔️ 評分完成 (使用 {model_name})")
                break
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ {model_name} 評分失敗: {error_msg}")
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                time.sleep(15)
            continue

    if not response:
        print("❌ 所有模型皆無法進行評分，將使用預設排序。")
        for a in all_articles:
            a['score'] = 1
        return all_articles[:10]

    try:
        if response.parsed:
            scores = response.parsed
        else:
            clean_text = response.text.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if json_match:
                clean_text = json_match.group(0)
            scores = json.loads(clean_text)
        
        score_map = {item['id']: item['score'] for item in scores}
        for i, a in enumerate(all_articles):
            a['score'] = score_map.get(i, 1) 
            
    except Exception as e:
        print(f"⚠️ 評分結果解析失敗: {e}")
        for a in all_articles:
            if 'score' not in a:
                a['score'] = 1

    sorted_articles = sorted(all_articles, key=lambda x: x.get('score', 0), reverse=True)
    return sorted_articles[:10]


def generate_podcast_script(news_data, social_data, weather_data=None, exchange_data=None, events_data=None, sponsor_text=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "your_gemini_api_key_here":
        print("\n❌ 錯誤: 找不到有效的 GEMINI_API_KEY。")
        return None

    client = genai.Client(api_key=api_key)

    diagnostic_list_models(client)

    if not news_data and not social_data:
        print("⚠️ 警告：沒有收集到任何新聞或社群資料，跳過 AI 生成。")
        return None

    top_articles = score_and_sort_articles(client, news_data)
    
    sources_text = "【今日重點越南新聞】\n"
    if not top_articles:
        sources_text += "今日無重大新聞。\n"
    else:
        for a in top_articles:
            sources_text += f"\n[Score: {a.get('score', 0)}/10] 來源: {a.get('source_name')} | 標題: {a.get('title')}\n摘要: {a.get('summary')}\n"
            
    sources_text += "\n\n[🌤️ 今日越南雙城天氣 (河內與胡志明市)]\n"
    if weather_data and 'hanoi' in weather_data:
        for city_key in ['hanoi', 'hcmc']:
            city_weather = weather_data.get(city_key, {})
            if city_weather.get('condition') != '資料無法取得':
                sources_text += (
                    f"【{city_weather.get('city', city_key)}】 "
                    f"狀況: {city_weather.get('condition')}, "
                    f"最高溫: {city_weather.get('temp_max_c')}°C, "
                    f"最低溫: {city_weather.get('temp_min_c')}°C, "
                    f"降雨: {city_weather.get('precip_mm')} mm\n"
                )
    else:
        sources_text += "今日天氣資料無法取得。\n"

    if exchange_data and exchange_data.get('usd_vnd'):
        sources_text += "\n\n[💱 最新收盤匯率動態 (非即時)]\n"
        sources_text += f"高波動: {'是' if exchange_data.get('high_volatility') else '否'}\n"
        sources_text += exchange_data.get('summary', '') + "\n"

    sources_text += "\n\n[💬 越南當地社群熱議 (Reddit / 越南新聞)]\n"
    for post in social_data:
        title = post.get('title', '未知主題')
        topics = post.get('topics', [])
        topics_str = ', '.join(topics) if topics else '綜合討論'
        sources_text += f"話題: {title} (來源: {topics_str})\n"

    if events_data:
        sources_text += "\n\n[🎭 今日雙城活動 (河內 & 胡志明市)]\n"
        for ev in events_data:
            sources_text += f"活動: {ev.get('title')} (來源: {ev.get('source')})\n摘要: {ev.get('summary')}\n"

    tz_str = os.environ.get("TZ", "Asia/Ho_Chi_Minh")
    tz = pytz.timezone(tz_str)
    today_str = datetime.datetime.now(tz).strftime("%Y年%m月%d日")

    sponsor_instruction = ""
    if sponsor_text and sponsor_text.strip():
        sponsor_instruction = f"本集節目由以下贊助商提供支持：{sponsor_text.strip()}。"
    else:
        sponsor_instruction = "本集目前無贊助商。請勿提及贊助資訊。"

    system_prompt = f"""
    You are 語昕, an energetic, professional yet engaging podcast host for a daily Chinese-language news show called "越南晨間快訊 Good Morning Vietnam".
    Your strict target audience is Taiwanese businesspeople (台商), expats, and Chinese-speaking professionals living/working in Vietnam.
    
    Please write the script entirely in TRADITIONAL CHINESE (繁體中文).

    IMPORTANT: You MUST start the broadcast by welcoming the listener, introducing yourself as 語昕,
    explicitly reading today's date ({today_str}), and integrating the sponsor message if provided.

    ### SPONSOR MESSAGE ##    ### MANDATORY SECTION — SMART CURRENCY CORNER ###
    You MUST include a dedicated "財經匯率報導" (Currency Report) segment in EVERY single broadcast.
    - CRITICAL TIMING CONTEXT: The exchange rates provided reflect the MOST RECENTLY SETTLED trading day's closing rates, NOT live real-time rates.
    - When announcing rates, frame it accurately: "截至上一個交易日收盤..." or "根據最新收盤匯率...". NEVER say "今天的匯率是" or "目前的即時匯率".
    - Report the exact USD/VND, CNY/VND, and TWD/VND exchange rates from the source materials. DO NOT invent numbers.
    - SMART LOGIC (STRICTLY ENFORCED):
      * If "高波動: 是": State the three rates and their change percentages, then add ONE sentence of practical business impact. MAXIMUM 4 sentences total. Keep it under 100 words.
        → GOOD EXAMPLE: "截至上一個交易日收盤1美元對換26,227越南皾，下滕0.46%；1人民帖3,849.9越南皾，下滕0.65%；1新台帖3,849.9越南皾。美元與人民帖同步軟強，相同的走勢。依賴進口原料的製造業，本週採購成本會進一步紊縮，建議各位對照訂單量自行評估適當性。"
        → BANNED phrases: "要定期密切關注匯率動態", "遠期外匯合約避險", "調整採購與銷售策略", "此为參考，不構成投資建議", "聯準會貨季政策", "美元避險需求"
        → The goal is a quick factual update, NOT a financial advisory column.
      * If "高波動: 否": Report the three rates in ONE sentence, then say "今日越南皾匯率相對平穩。"
        MAXIMUM 2 sentences total. NO further analysis whatsoever.至上一個交易日收盤..." or "根據最新收盤匯率...". NEVER say "今天的匯率是" or "目前的即時匯率" because they are not live.
    - Report the exact USD/VND, CNY/VND, and TWD/VND exchange rates provided in the source materials.
    - If the rates are not provided, simply mention that the data is unavailable today. DO NOT invent numbers.
    - SMART LOGIC (STRICTLY ENFORCED):
      * If "高波動: 是": Provide a focused 3-4 sentence analysis ONLY about the direct practical impact
        (e.g. how it affects payroll, procurement costs, or cross-border remittances). Do NOT write generic
        macroeconomic textbook explanations about FDI, Fed policy, trade surplus, or hedging instruments.
        Keep total currency segment under 150 words.
      * If "高波動: 否": Report the three rates in ONE sentence, then say "今日越南盾匯率相對平穩。"
        MAXIMUM 2 sentences total. ABSOLUTELY NO further analysis, explanation, or commentary.

    ### EDITORIAL GUIDELINES ###
    1. PRIORITIZATION: The news items are pre-sorted by an importance score. Maintain this order.
    2. DEPTH BY IMPORTANCE: Devote significantly more time to higher-scoring stories. **IMPORTANT: To hit the 12-minute target length, provide deep, factual context and historical background for the top news stories. Do NOT add subjective analysis or commentary.**
    3. EXPAT FOCUS: Focus heavily on business, FDI, manufacturing supply chains, real estate, and policies affecting foreigners in Vietnam.
    4. FACT-CHECKING: Do NOT say "tomorrow's announcement" if the event has already passed based on article dates.
    5. EVENTS: After the news, feature 1-2 interesting events from Hanoi OR HCMC from the provided sources to add "lifestyle flavor".
    6. FILTER TRASH: Ignore tabloid gossip.
    7. SOCIAL MEDIA: End the news section with 1-2 fun trending topics from the provided social data. Filter out NSFW content strictly. Provide commentary on why the local community is discussing this.
    8. CALL TO ACTION (CTA): MANDATORY. After the social media segment, you MUST say: "以上就是今天的越南晨間快訊 Good Morning Vietnam。如果你覺得這集節目對你有幫助，請記得訂閱我們的頻道，並分享給你在越南打拼的同事和朋友。也歡迎你在收聽平台給我們留下五星好評，這對我們是莫大的鼓勵。我是語昕，我們明天見，Tạm biệt！" This closing MUST be the very last thing in the script. The script is NOT complete without it.
    9. TONE: Professional but conversational, like a friendly business briefing. Pace should be engaging.
    10. LENGTH (CRITICAL): The full script MUST be between 2800 and 3400 Chinese characters (which translates to roughly 11-13 minutes of spoken audio). Pad the script with rich, factual context on Vietnam\'s economic situation, historical background on companies mentioned, and objective explanations of policies. Do NOT give business advice. ALWAYS finish the full closing before hitting the length limit — never truncate the CTA or sign-off.
    11. NEWS SOURCE FILTER (CRITICAL): ONLY report stories that originate from Vietnam-local media or events
        happening INSIDE Vietnam. SKIP any story that is primarily about Taiwan-based events, conferences,
        or government activities that merely mention Vietnam. The audience is ALREADY IN Vietnam — they need
        local on-the-ground news, NOT news from Taiwan about Vietnam.

    ### STRICT PROHIBITIONS ###
    - NO SUBJECTIVE INTERPRETATION OR ADVICE: Do NOT add any phrases like "建議您..." (I suggest you...), "這是一個重要警示" (This is an important warning), or "這凸顯了...".
    - Strictly report only the objective facts of the news. Do NOT give business, investment, or personal advice.
    - DO NOT hallucinate or invent any news stories, quotes, or events.
    - DO NOT mention any editorial score or rating in the spoken script.
    - DO NOT use any Markdown formatting.
    - DO NOT state the wrong date. Today is {today_str}.
    - DO NOT list or enumerate the target audience by name.
    - NATURAL PHRASING: When writing English phrases like "Good Morning Vietnam", ALWAYS surround them with a comma or dash (e.g. "越南晨間快訊，Good Morning Vietnam") to ensure the TTS engine pauses and switches languages naturally. Do NOT run them together with Chinese characters.

    ### SCRIPT FORMAT ###
    Output ONLY a JSON object.
    Format:
    {{
      "script": "The full spoken broadcast script in Traditional Chinese ending with the mandatory CTA and Tạm biệt sign-off...",
      "summary": "A 3-5 sentence episode description for podcast platforms in Traditional Chinese. Start with today's top 2-3 news stories, then list today's events with their names and a one-line description each. End with one sentence inviting listeners to tune in."
    }}
    """
    
    podcast_schema = {
        "type": "OBJECT",
        "properties": {
            "script": {"type": "STRING"},
            "summary": {"type": "STRING"}
        },
        "required": ["script", "summary"]
    }

    print("\n[AI 運作中] 正在編寫長篇講稿與摘要 (約需 30~60 秒)...")
    
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7, # Slightly higher temperature for more expansive writing
        response_mime_type='application/json',
        response_schema=podcast_schema
    )
    
    prompt_content = f"這是今天的素材。請撰寫長篇、詳細、深度分析的 12 分鐘廣播稿與摘要：\n\n{sources_text}"
    
    models_to_try = [
        'gemini-2.5-flash', 
        'gemini-3.5-flash',
        'gemini-2.5-pro',
        'gemini-2.5-flash-lite'
    ]
    response = None
    
    for model_name in models_to_try:
        max_retries = 3
        base_wait = 20
        
        for attempt in range(max_retries):
            try:
                print(f"嘗試載入 {model_name} 模型 (attempt {attempt + 1}/{max_retries})...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt_content,
                    config=config
                )
                print(f"✔️ 成功使用 {model_name} 模型生成內容！")
                break 
                
            except Exception as e:
                error_msg = str(e)
                print(f"⚠️ {model_name} 失敗: {error_msg}")
                
                if "503" in error_msg or "UNAVAILABLE" in error_msg:
                    wait_sec = base_wait * (2 ** attempt)
                    print(f"  ⏳ API 暫時過載 (503)。等待 {wait_sec} 秒後重試...")
                    time.sleep(wait_sec)
                elif "429" in error_msg or "Quota exceeded" in error_msg:
                    print(f"⏳ 偵測到 API 額度耗盡 (429)，暫停 60 秒後重試...")
                    time.sleep(60)
                else:
                    break
                    
        if response:
            break
            
    if getattr(response, 'text', None) is None:
        print("❌ 所有模型皆無回應或 API 額度受限，無法生成內容。")
        return None
        
    try:
        if getattr(response, 'parsed', None):
            result_json = response.parsed
        else:
            raw_text = response.text.strip()
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            json_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if json_match:
                clean_text = json_match.group(0)
            result_json = json.loads(clean_text)
        
        script = result_json.get('script', '')
        summary = result_json.get('summary', "今日最新的越南商業與科技動態。")
        
        with open("script.txt", "w", encoding="utf-8") as f:
            f.write(script)
            
        with open("summary.txt", "w", encoding="utf-8") as f:
            f.write(summary)
            
        print("✅ 講稿與摘要生成完畢！已儲存至 script.txt 與 summary.txt")
        return script
        
    except Exception as e:
        print(f"❌ JSON 解析失敗: {e}")
        return None

def review_and_improve_script(script: str, client=None) -> str:
    """
    AI 編輯審稿：在 TTS 之前檢查稿件品質。
    - 確保長度符合約 12 分鐘的時長（約 2800 - 3400 字）
    - 清除格式
    - 支援第二輪裁剪修飾
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not client:
        if not api_key:
            print("⚠️ [AI Editor] 無 GEMINI_API_KEY，跳過 AI 審稿，僅做格式清理。")
            return _clean_script_formatting(script)
        client = genai.Client(api_key=api_key)

    word_count = len(re.findall(r'\S', script))
    print(f"\n📝 [AI Editor] 審稿中... 目前中文字數預估: {word_count} 字 (以非空白字元估算)")

    script = _clean_script_formatting(script)

    needs_expansion = word_count < 2600
    needs_trim = word_count > 3600

    if not needs_expansion and not needs_trim:
        print(f"  ✔️ [AI Editor] 字數 ({word_count}) 在 12 分鐘的合理範圍內，稿件通過審閱。")
        return script

    if needs_expansion:
        action = "EXPAND"
        instruction = (
            f"目前稿件偏短 (約 {word_count} 字)。這不足以支撐 12 分鐘的廣播。請將其大幅擴充至約 3000 字。"
            "請為主要新聞加入更深入的產業分析、在越台商/外資的背景脈絡、以及政策對外企的潛在影響。"
            "提供豐富的情境與價值，但絕對請勿加入無意義的廢話，也不要無中生有捏造新聞或數據。"
        )
    else:
        action = "TRIM"
        instruction = (
            f"目前稿件偏長 (約 {word_count} 字)。請將其精簡至 3300 字以內。刪除冗長累贅的分析，但必須保留所有主要新聞、天氣、匯率與活動。"
        )

    print(f"  🤖 [AI Editor] 正在 {action} 稿件...")

    editor_prompt = f"""
    You are a senior podcast editor for a Chinese-language daily news podcast in Vietnam.

    {instruction}

    STRICT RULES:
    1. Output ONLY the revised script text in Traditional Chinese (繁體中文). No JSON, no markdown, no explanation.
    2. Do NOT add any Markdown formatting (no #, ##, **, *, ---).
    3. Do NOT add vocabulary lessons or "word of the day" segments.
    4. Do NOT invent new facts, numbers, or events.
    5. Maintain the same host voice and professional tone.
    6. CRITICAL: The script MUST end with the full closing CTA and "Tạm biệt!" sign-off. If the original script is missing this or it is cut off, you MUST restore it: add "以上就是今天的越南晨間快訊 Good Morning Vietnam。如果你覺得這集節目對你有幫助，請記得訂閱我們的頻道，並分享給你在越南打拼的同事和朋友。也歡迎你在收聽平台給我們留下五星好評，這對我們是莫大的鼓勵。我是語昕，我們明天見，Tạm biệt！"
    7. When trimming, NEVER cut the closing CTA or sign-off — trim from the middle of news stories instead.
    8. DO NOT list or enumerate the target audience by name anywhere in the script. Remove any phrases like "各位在越南打拼的台商、華人與商務人士" — replace them with direct address to the listener ("你" or "各位聽眾").
    9. For weather tips: keep only ONE brief practical tip. Remove any suggestions of specific venues or leisure activities.

    10. STRICTLY REMOVE all subjective interpretations, opinions, warnings, and business advice (e.g. remove phrases like "建議您...", "這是一個警示").

    HERE IS THE CURRENT SCRIPT:
    ---
    {script}
    ---
    """

    editor_models = ['gemini-2.5-flash', 'gemini-3.5-flash', 'gemini-2.5-pro']
    revised = None
    for model_name in editor_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=editor_prompt,
                config=types.GenerateContentConfig(temperature=0.5)
            )
            revised = _clean_script_formatting(response.text.strip())
            new_word_count = len(re.findall(r'\S', revised))
            print(f"  ✔️ [AI Editor] 第一輪審稿完成 (使用 {model_name})，修訂後字數: {new_word_count} 字")
            break
        except Exception as e:
            print(f"  ⚠️ [AI Editor] {model_name} 失敗: {e}")
            time.sleep(15)

    if revised is None:
        print("  ⚠️ [AI Editor] 所有模型均失敗，回傳格式清理後的原稿。")
        return script

    # Second-pass trim if expansion overshot
    post_edit_count = len(re.findall(r'\S', revised))
    if needs_expansion and post_edit_count > 3700:
        print(f"  ⚠️ [AI Editor] 擴充後字數 ({post_edit_count}) 超過上限，啟動第二輪自動裁剪...")
        trim_instruction = (
            f"目前稿件字數 ({post_edit_count}) 稍微過長，請將其修剪至約 3300 字以內。去除過度解釋的段落，"
            "保留所有主要新聞、天氣、匯率，以及最重要的結尾。"
        )
        trim_prompt = f"""
    You are a senior podcast editor for a Chinese-language daily news podcast in Vietnam.
    {trim_instruction}

    STRICT RULES:
    1. Output ONLY the revised script text in Traditional Chinese.
    2. No Markdown formatting.
    3. NEVER cut the closing CTA or "Tạm biệt!" sign-off.
    4. Maintain tone.

    HERE IS THE CURRENT SCRIPT:
    ---
    {revised}
    ---
    """
        for model_name in editor_models:
            try:
                resp2 = client.models.generate_content(
                    model=model_name,
                    contents=trim_prompt,
                    config=types.GenerateContentConfig(temperature=0.4)
                )
                trimmed = _clean_script_formatting(resp2.text.strip())
                final_count = len(re.findall(r'\S', trimmed))
                print(f"  ✔️ [AI Editor] 第二輪裁剪完成 (使用 {model_name})，最終字數: {final_count} 字")
                return trimmed
            except Exception as e:
                print(f"  ⚠️ [AI Editor] 第二輪裁剪失敗 ({model_name}): {e}")
                time.sleep(10)

    return revised


def _clean_script_formatting(script: str) -> str:
    script = re.sub(r'^#{1,6}\s+', '', script, flags=re.MULTILINE)
    script = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', script)
    script = re.sub(r'^[\-\*_]{3,}\s*$', '', script, flags=re.MULTILINE)
    script = re.sub(
        r'(?i)(,?\s*)'
        r'((?:both|also|each)?\s*(?:scoring|rated?|with\s+a\s+score\s+of|a\s+perfect)'
        r'\s+[a-z\s]*?\d{1,2}(?:\s*out\s*of\s*10|/10))',
        '',
        script
    )
    script = re.sub(r'\n{3,}', '\n\n', script)
    return script.strip()
