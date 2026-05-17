import os
import json
from datetime import datetime, timedelta
import pytz
from podgen import Podcast, Episode, Media, Category, Person

EPISODES_FILE = "episodes.json"
FEED_FILE = "feed.xml"

# Podcast Metadata
PODCAST_NAME = "越南晨間快訊 Good Morning Vietnam"
PODCAST_DESC = "專為在越南生活的台商、華人與中文商務人士打造的每日重點新聞播報。AI 全自動產製，為您掌握越南產經、外資動態與在地生活情報。"
PODCAST_WEBSITE = "https://github.com/ericchi-valuation/Good_Morning_Vietnam_2026"
PODCAST_EXPLICIT = False
PODCAST_IMAGE_URL = "https://raw.githubusercontent.com/ericchi-valuation/Good_Morning_Vietnam_2026/main/cover.JPG"
AUTHOR_NAME = "Eric Chi"
AUTHOR_EMAIL = "eric.chi1988@gmail.com"  

def generate_rss(new_title, new_summary, str_date, mp3_url, duration, file_size):
    tz_str = os.environ.get("TZ", "Asia/Ho_Chi_Minh")
    tz = pytz.timezone(tz_str)
    
    episodes_data = []
    if os.path.exists(EPISODES_FILE):
        with open(EPISODES_FILE, 'r', encoding='utf-8') as f:
            try:
                episodes_data = json.load(f)
            except:
                pass

    new_ep = {
        "title": new_title,
        "summary": new_summary,
        "date": str_date,
        "mp3_url": mp3_url,
        "duration": duration,
        "file_size": file_size
    }
    
    episodes_data = [ep for ep in episodes_data if ep['title'] != new_title]
    episodes_data.append(new_ep)
    
    MAX_EPISODES = 366
    if len(episodes_data) > MAX_EPISODES:
        episodes_data = episodes_data[-MAX_EPISODES:]
    
    with open(EPISODES_FILE, 'w', encoding='utf-8') as f:
        json.dump(episodes_data, f, ensure_ascii=False, indent=2)

    p = Podcast()
    p.name = PODCAST_NAME
    p.description = PODCAST_DESC
    p.website = PODCAST_WEBSITE
    p.explicit = PODCAST_EXPLICIT
    p.image = PODCAST_IMAGE_URL
    p.language = "zh-TW"
    p.category = Category('News', 'Business News')
    
    p.authors = [Person(AUTHOR_NAME, AUTHOR_EMAIL)]
    p.owner = Person(AUTHOR_NAME, AUTHOR_EMAIL)

    for ep_data in episodes_data:
        pub_date = datetime.fromisoformat(ep_data['date'])
        
        episode = Episode()
        episode.title = ep_data['title']
        episode.summary = ep_data['summary'] 
        episode.publication_date = pub_date

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
    parser.add_argument("--summary-file", required=False, default="summary.txt")
    parser.add_argument("--date",         required=True)
    parser.add_argument("--url",          required=True)
    parser.add_argument("--duration",     required=True)
    parser.add_argument("--size",         required=True)
    args = parser.parse_args()

    summary_text = "今日最新的越南商業與科技動態。"
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
