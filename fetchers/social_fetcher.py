"""
Vietnam Social Media Trending Fetcher
=======================================
爬取越南當地社群的熱門討論話題，供 AI 播報使用。

來源（全部為越南本地 / 越南主題）：
  1. Reddit r/vietnam      – 越南當地英語社群最熱門貼文
  2. Reddit r/VietnamBusiness – 越南商業、投資討論
  3. Google News RSS       – 越南本地中越文討論熱點（hl=vi, gl=VN）
  4. Facebook Vietnam Expats group（可選，需設定 FB_GROUP_ID + FB_ACCESS_TOKEN）

【重要】：所有來源均已設定為越南本地地區 (gl=VN, hl=vi 或 en-VN)，
         不抓台灣 PTT 或台灣版 Google News。
"""

import os
import feedparser
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TRASH_KEYWORDS = [
    '乳', '奶', '性愛', '做愛', '約炮', '外流', '色情', '🔞',
    '裸', '走光', '偷拍', 'nsfw', 'porn', 'sex tape', 'leaked'
]


def is_trash_social(title: str) -> bool:
    text = title.lower()
    return any(kw in text for kw in TRASH_KEYWORDS)


# ---------------------------------------------------------------------------
# Reddit Bypass (via Google News RSS) — Vietnam subreddits
# ---------------------------------------------------------------------------
def get_reddit_vietnam_bypassed(subreddit: str, limit: int = 3) -> list:
    """
    Bypasses Reddit's 403/block by searching for the subreddit content
    on Google News RSS, targeting Vietnam locale (gl=VN, hl=en-VN).
    This is highly reliable for GitHub Actions runners.
    """
    query = f"site:reddit.com/r/{subreddit}+when:1d"
    url = (
        f"https://news.google.com/rss/search?q={query}"
        f"&hl=en-VN&gl=VN&ceid=VN:en"
    )
    try:
        feed = feedparser.parse(url)
        posts = []
        for entry in feed.entries[:limit * 2]:
            title = entry.get('title', '').split(' - r/')[0].strip()
            if is_trash_social(title):
                continue
            posts.append({
                'title': title,
                'url': entry.get('link', ''),
                'topics': [f'Reddit r/{subreddit}']
            })
            if len(posts) >= limit:
                break
        return posts
    except Exception as e:
        print(f"Error fetching Reddit r/{subreddit} (Vietnam bypass): {e}")
        return []


# ---------------------------------------------------------------------------
# Google News RSS — Vietnam local Vietnamese-language hot topics
# ---------------------------------------------------------------------------
def get_vietnam_local_trending(limit: int = 3) -> list:
    """
    透過 Google News RSS 抓取越南本地熱門話題（越南語，gl=VN）。
    關鍵字涵蓋越南社會、民生、商業熱點。
    """
    url = (
        "https://news.google.com/rss/search"
        "?q=xu+huong+OR+hot+OR+mang+xa+hoi+khi+noi+when:1d"
        "&hl=vi&gl=VN&ceid=VN:vi"
    )
    try:
        feed = feedparser.parse(url)
        posts = []
        for entry in feed.entries[:limit * 2]:
            title = entry.get('title', '').strip()
            # Strip source suffix (e.g., " - VnExpress")
            if ' - ' in title:
                title = title.rsplit(' - ', 1)[0].strip()
            if is_trash_social(title):
                continue
            posts.append({
                'title': title,
                'url': entry.get('link', ''),
                'topics': ['越南本地熱門話題 (Google News VN)']
            })
            if len(posts) >= limit:
                break
        return posts
    except Exception as e:
        print(f"越南本地熱點抓取失敗：{e}")
        return []


# ---------------------------------------------------------------------------
# Facebook – Vietnam Expats / Business group (via Graph API, optional)
# ---------------------------------------------------------------------------
def get_fb_vietnam_expats(limit: int = 3) -> list:
    """
    Fetch recent posts from a Vietnam expats/business Facebook group
    using the Facebook Graph API.

    Requires two environment variables:
      FB_GROUP_ID          – The numeric ID of the Vietnam Expats/Business group
      FB_ACCESS_TOKEN      – A long-lived User or Page access token

    If either variable is missing the function silently returns an empty list,
    so the pipeline degrades gracefully without crashing.
    """
    group_id     = os.environ.get("FB_GROUP_ID", "")
    access_token = os.environ.get("FB_ACCESS_TOKEN", "")

    if not group_id or not access_token or access_token == "your_fb_access_token_here":
        print("⚠️  FB_GROUP_ID / FB_ACCESS_TOKEN not set – skipping Facebook source.")
        return []

    url = f"https://graph.facebook.com/v19.0/{group_id}/feed"
    params = {
        "fields": "message,story,permalink_url,created_time",
        "limit": limit * 2,
        "access_token": access_token
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        posts = []
        for item in data.get('data', []):
            text = (item.get('message') or item.get('story') or '').strip()
            if not text:
                continue
            title = text[:120].replace('\n', ' ')
            if is_trash_social(title):
                continue
            posts.append({
                'title': title,
                'url': item.get('permalink_url', ''),
                'topics': ['Facebook – Vietnam Expats/Business']
            })
            if len(posts) >= limit:
                break
        return posts
    except Exception as e:
        print(f"Error fetching Facebook Vietnam Expats: {e}")
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def get_social_trending(limit_per_source: int = 2) -> list:
    """
    彙整越南當地社群的熱門話題：
      - Reddit r/vietnam        (via Google News VN bypass)
      - Reddit r/VietnamBusiness (via Google News VN bypass)
      - Google News VN 越南本地熱點
      - Facebook Vietnam Expats group (optional, needs env vars)
    """
    posts = []
    posts.extend(get_reddit_vietnam_bypassed('vietnam', limit=limit_per_source))
    posts.extend(get_reddit_vietnam_bypassed('VietnamBusiness', limit=limit_per_source))
    posts.extend(get_vietnam_local_trending(limit=limit_per_source))
    posts.extend(get_fb_vietnam_expats(limit=limit_per_source))
    return posts


if __name__ == "__main__":
    hot_topics = get_social_trending(limit_per_source=3)
    print("--- 越南當地社群熱門話題 ---")
    for topic in hot_topics:
        print(f"標題：{topic['title']}")
        print(f"來源：{topic['topics']}\n")
