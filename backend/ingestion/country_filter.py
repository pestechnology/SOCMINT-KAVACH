"""
backend/ingestion/country_filter.py — Country-specific platform filtering.

When country_filter is set to "INDIA", we retain ONLY Indian domestic websites and
services (ShareChat, Koo, Paytm, Zomato, Flipkart, Indian banks, gov.in, Indian
edtech/OTT/matrimony, …) — plus the subject's own core identifier records
(phone / email / UPI / real name / breach hits / face), which are platform-agnostic
evidence rather than "a website the subject uses".

Global networks — Instagram, Facebook, Twitter/X, LinkedIn, GitHub, Reddit, YouTube,
Telegram, and every foreign-regional network (VK, Weibo, Naver, …) and global game
(Roblox, League of Legends, …) — are intentionally EXCLUDED. This is a strict
"Indian websites only" scope: it returns far fewer results, but nothing outside India.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.ingestion.base_module import RawProfile

# Substrings or exact matches for INDIAN domestic platforms/domains. A discovered
# account (social_account) or link (url) is retained ONLY if its platform or source_url
# matches one of these. Core identifier records (phone/email/upi/name/breach/face) are
# kept regardless — they are evidence about the person, not a website.
INDIA_ALLOWED_PLATFORMS = {
    # Indian social / short-video / news-aggregator networks
    "sharechat", "koo", "moj", "chingari", "josh", "roposo", "public",
    "inshorts", "dailyhunt",

    # Indian developer, coding-practice, jobs & professional platforms
    "geeksforgeeks", "codechef", "interviewbit", "hackerrank", "hashnode",
    "naukri", "instahyre", "apna", "foundit",

    # Indian email / web portals
    "rediff", "sify", "indiatimes", "zoho",

    # Indian fintech, UPI, banking & crypto
    "upi", "paytm", "phonepe", "bhim", "cred", "slice", "bharatpe", "mobikwik",
    "freecharge", "zerodha", "groww", "upstox", "angelone", "dhan", "indmoney",
    "wazirx", "coindcx", "coinswitch", "mudrex",
    "sbi", "hdfc", "icici", "axis", "kotak", "pnb", "bob", "canara", "idfc",

    # Indian e-commerce, delivery, travel & lifestyle
    "flipkart", "myntra", "ajio", "meesho", "snapdeal", "tatacliq", "nykaa",
    "zomato", "swiggy", "blinkit", "zepto", "instamart", "bigbasket", "dunzo",
    "ola", "rapido", "makemytrip", "cleartrip", "goibibo", "redbus", "ixigo",
    "irctc", "bookmyshow", "urbancompany", "nobroker", "magicbricks", "99acres",
    "housing", "quikr", "spinny", "cars24", "carwale", "cardekho", "lenskart",
    "tata", "reliance", "jio", "airtel",

    # Indian OTT, entertainment, gaming & matrimony
    "hotstar", "jiocinema", "sonyliv", "zee5", "altbalaji", "jiosaavn", "gaana",
    "wynk", "hungama", "bgmi", "dream11", "mpl", "my11circle",
    "shaadi", "bharatmatrimony", "jeevansathi", "betterhalf",

    # Indian governance, EdTech & health
    "digilocker", "parivahan", "uidai", "epfo", "incometax", "unacademy",
    "byjus", "physicswallah", "pw.live", "vedantu", "toppr", "doubtnut",
    "practo", "pharmeasy", "1mg", "tata1mg", "netmeds", "apollo247",
    "gov.in", "nic.in", "ac.in", "edu.in", "org.in", "co.in",
}

# Explicit blacklist — global networks and foreign-regional/gaming sites that must never
# appear under the Indian-only scope. Checked FIRST, so it also strips these even if a
# substring were to coincidentally overlap an allowed token.
INDIA_EXCLUDED_PLATFORMS = {
    # Global majors (excluded under strict Indian-only scope)
    "instagram", "facebook", "twitter", "x.com", "linkedin", "reddit", "quora",
    "youtube", "telegram", "snapchat", "pinterest", "threads", "tumblr",
    "github", "gitlab", "bitbucket", "stackoverflow", "leetcode", "medium",
    "substack", "discord", "spotify", "steam", "twitch", "amazon", "uber", "olx",
    # Global gaming (explicitly requested)
    "leagueoflegends", "league-of-legends", "riotgames", "op.gg", "opgg", "roblox",
    # Foreign-regional networks that cause false positives
    "xing", "ixbt", "vk", "vkontakte", "odnoklassniki", "ok.ru", "habr", "rambler",
    "gmx", "web.de", "mail.ru", "yandex", "weibo", "qq", "wechat", "baidu",
    "douyin", "bilibili", "zhihu", "naver", "daum", "kakao", "niconico", "pixiv",
    "line", "cyworld", "fc2", "freelance.ru", "kwork", "fl.ru", "livejournal",
    "pikabu", "drom", "auto.ru", "cian", "avito", "virustotal",
    "kermit", "lobsters", "lobste.rs", "vbulletin", "photobucket",
    "patreon", "onlyfans", "buymeacoffee", "ko-fi", "bandcamp", "last.fm",
    "myspace", "soundcloud", "vimeo", "dailymotion", "flickr", "deviantart",
    "artstation", "wattpad", "gravatar", "disqus", "keybase",
}


def filter_profiles_by_country(profiles: list[RawProfile], country: str) -> list[RawProfile]:
    if not country or str(country).strip().upper() != "INDIA":
        return profiles

    filtered = []
    for p in profiles:
        plat_lower = (p.platform or "").lower()
        url_lower = (p.source_url or "").lower()

        # Check explicit exclusions first
        if any(exc in plat_lower or exc in url_lower for exc in INDIA_EXCLUDED_PLATFORMS):
            continue

        # Core identifier / breach / biometric records are platform-agnostic evidence about
        # the person (not a website they use) — always kept. NOTE: `url` is intentionally
        # NOT here — a discovered link must point at an Indian site to survive the scope.
        if p.type in ("phone", "email", "upi", "name", "breach", "face"):
            filtered.append(p)
            continue

        # social_account / url enumerations: keep ONLY if the platform or link is Indian.
        if any(inc in plat_lower or inc in url_lower for inc in INDIA_ALLOWED_PLATFORMS):
            filtered.append(p)
            continue

        # If it's from mock mode or a custom source, keep it (offline demo / manual entry).
        if p.data_mode == "mock" or plat_lower in ("mock", "manual", "custom"):
            filtered.append(p)
            continue

    return filtered
