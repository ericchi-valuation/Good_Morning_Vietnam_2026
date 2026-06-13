import os
import json
from datetime import datetime, timedelta
import pytz
from podgen import Podcast, Episode, Media, Category, Person

EPISODES_FILE = "episodes.json"
FEED_FILE = "feed.xml"

# Podcast Metadata
PODCAST_NAME = "The Hungarian Daily"
PODCAST_DESC = (
    "Your essential morning briefing on life, business, and politics in Hungary — "
    "produced fresh every day by AI, hosted by Ray. "
    "Each episode scans 10+ trusted Hungarian and international sources including "
    "Hungary Today, Portfolio.hu, Budapest Business Journal, The Budapest Times, "
    "Telex, Daily News Hungary, and more. "
    "We cover ranked top stories, Budapest weather, Forint exchange rates "
    "(EUR/HUF and USD/HUF vs the previous business day's close), "
    "local events around the city, and what the expat community is talking about on Reddit r/budapest. "
    "Episodes run 8–12 minutes. New episode every morning. "
    "Perfect for expats, international professionals, and anyone curious about Central Europe."
)
PODCAST_WEBSITE = "https://open.spotify.com/show/7zU2b8xDgRL8D7b9T9kjiE"
PODCAST_EXPLICIT = False
PODCAST_IMAGE_URL = "https://ericchi-valuation.github.io/The-Hungary-Daily/cover.jpg"
AUTHOR_NAME = "Eric Chi"
AUTHOR_EMAIL = "eric.chi1988@gmail.com"

def generate_rss(new_title, new_summary, str_date, mp3_url, duration, file_size):
    tz_str = os.environ.get("TZ", "Europe/Budapest")
    tz = pytz.timezone(tz_str)
    
    # 1. 讀取歷史集數清單
    episodes_data = []
    if os.path.exists(EPISODES_FILE):
        with open(EPISODES_FILE, 'r', encoding='utf-8') as f:
            try:
                episodes_data = json.load(f)
            except:
                pass

    # 2. 新增今日集數
    new_ep = {
        "title": new_title,
        "summary": new_summary,
        "date": str_date,
        "mp3_url": mp3_url,
        "duration": duration,
        "file_size": file_size
    }
    
    # 檢查是否重複上架同一天
    episodes_data = [ep for ep in episodes_data if ep['title'] != new_title]
    episodes_data.append(new_ep)
    
    # 限制集數 (保留最新 366 集，約一年份)，避免 RSS 無限膨脹
    MAX_EPISODES = 366
    if len(episodes_data) > MAX_EPISODES:
        episodes_data = episodes_data[-MAX_EPISODES:]
    
    # 寫回 json 備份
    with open(EPISODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(episodes_data, f, ensure_ascii=False, indent=2)

    # 3. 使用 podgen 產生乾淨完美的 RSS XML
    p = Podcast()
    p.name = PODCAST_NAME
    p.description = PODCAST_DESC
    p.website = PODCAST_WEBSITE
    p.explicit = PODCAST_EXPLICIT
    p.image = PODCAST_IMAGE_URL
    p.language = "en-US"
    p.category = Category('News', 'Daily News')
    
    # 👇 更新點：加上 作者 與 Email，以符合 Spotify / Apple Podcast 驗證權限需求
    p.authors = [Person(AUTHOR_NAME, AUTHOR_EMAIL)]
    p.owner = Person(AUTHOR_NAME, AUTHOR_EMAIL)

    for ep_data in episodes_data:
        # 將 ISO 日期字串轉回 True localized datetime
        pub_date = datetime.fromisoformat(ep_data['date'])
        
        episode = Episode()
        episode.title = ep_data['title']
        episode.summary = ep_data['summary'] # Apple Podcast 需要的純文字或微量HTML簡介
        episode.publication_date = pub_date

        # 將 HH:MM:SS 轉為 datetime.timedelta
        h, m, s = map(int, ep_data['duration'].split(':'))
        td = timedelta(hours=h, minutes=m, seconds=s)
        
        episode.media = Media(ep_data['mp3_url'], int(ep_data['file_size']), type="audio/mpeg", duration=td)
        
        p.episodes.append(episode)

    p.rss_file(FEED_FILE, minimize=False)
    print(f"✅ 成功更新 RSS Feed: {FEED_FILE} (目前共 {len(episodes_data)} 集)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--title",        required=True)
    parser.add_argument("--summary-file", required=False, default="summary.txt",
                        help="Path to a text file containing the episode description (default: summary.txt)")
    parser.add_argument("--date",         required=True)
    parser.add_argument("--url",          required=True)
    parser.add_argument("--duration",     required=True)
    parser.add_argument("--size",         required=True)
    args = parser.parse_args()

    # Read summary from file to avoid shell quoting / length issues
    summary_text = "Today's top news and updates from Hungary for expats and international professionals."
    summary_path = args.summary_file
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as _f:
            _content = _f.read().strip()
            if _content:
                summary_text = _content
        print(f"  ✔️  Loaded episode summary from '{summary_path}' ({len(summary_text)} chars).")
    else:
        print(f"  ⚠️  '{summary_path}' not found. Using default summary.")

    generate_rss(args.title, summary_text, args.date, args.url, args.duration, args.size)
