"""
backend/ingestion/country_filter.py — Country-specific platform filtering.

When country_filter is set to "INDIA", we retain only platforms and domains
commonly used in India (major global networks + Indian domestic platforms +
core OSINT/fintech/breach/data sources). Regional foreign networks (e.g. Xing,
VKontakte, Odnoklassniki, Rambler, Mail.ru, Weibo, QQ, Baidu, Daum, Naver, etc.)
are excluded to eliminate foreign false positives and noise.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.ingestion.base_module import RawProfile

# Substrings or exact matches for platforms/domains allowed when filtering for INDIA.
# Any profile whose platform or source_url matches one of these is retained.
# In addition, core identifier seeds / breach / osint / fintech records are always kept.
INDIA_ALLOWED_PLATFORMS = {
    # Major Global & Indian Social Networks & Messaging
    "instagram", "facebook", "twitter", "x.com", "linkedin", "reddit", "quora",
    "youtube", "telegram", "whatsapp", "snapchat", "pinterest", "threads",
    "medium", "substack", "discord", "sharechat", "koo", "moj", "chingari",
    "josh", "roposo", "public", "inshorts", "dailyhunt", "skype", "zoom", "meet",
    
    # Developer, Tech & Professional
    "github", "gitlab", "bitbucket", "stackoverflow", "leetcode", "hackerrank",
    "codechef", "codeforces", "geeksforgeeks", "spoj", "interviewbit", "kaggle",
    "behance", "dribbble", "figma", "notion", "naukri", "instahyre", "apna",
    "foundit", "monster", "indeed", "glassdoor", "hired", "angel", "wellfound",
    "hashnode", "dev.to", "replit", "npm", "pypi", "docker", "postman",
    
    # Email, Cloud & Core Services
    "gmail", "google", "yahoo", "outlook", "hotmail", "live", "icloud", "apple",
    "protonmail", "zoho", "rediff", "sify", "indiatimes", "gravatar", "microsoft",
    
    # Indian Fintech, UPI, Banking & Crypto
    "upi", "paytm", "phonepe", "gpay", "googlepay", "amazonpay", "bhim", "cred",
    "slice", "bharatpe", "mobikwik", "freecharge", "zerodha", "groww", "upstox",
    "angelone", "dhan", "indmoney", "wazirx", "coindcx", "coinswitch", "mudrex",
    "sbi", "hdfc", "icici", "axis", "kotak", "pnb", "bob", "canara", "idfc",
    
    # Indian E-Commerce, Delivery, Travel & Lifestyle
    "amazon", "flipkart", "myntra", "ajio", "meesho", "snapdeal", "tatacliq",
    "nykaa", "zomato", "swiggy", "blinkit", "zepto", "instamart", "bigbasket",
    "dunzo", "ola", "rapido", "uber", "makemytrip", "cleartrip", "goibibo",
    "redbus", "ixigo", "irctc", "bookmyshow", "urbancompany", "nobroker",
    "magicbricks", "99acres", "housing", "olx", "quikr", "spinny", "cars24",
    "carwale", "cardekho", "lenskart", "tata", "reliance", "jio", "airtel", "vi",
    
    # Indian Entertainment, OTT, Gaming & Matrimony
    "hotstar", "jiocinema", "sonyliv", "zee5", "altbalaji", "jiosaavn", "gaana",
    "wynk", "hungama", "spotify", "applemusic", "amazonmusic", "steam", "bgmi",
    "freefire", "dream11", "mpl", "my11circle", "shaadi", "bharatmatrimony",
    "jeevansathi", "jeeves", "betterhalf",

    # Global gaming / entertainment — kept (visible) but scored LOW & unlinked via
    # LOW_VALUE_PLATFORMS below (a game handle is weak identity evidence, but hiding it
    # entirely loses a lead an investigator may still want to see).
    "leagueoflegends", "league-of-legends", "riotgames", "op.gg", "opgg",
    "valorant", "fortnite", "epicgames", "minecraft", "battle.net", "xbox",
    "playstation", "psn", "ubisoft", "ea.com", "origin.com", "roblox",
    
    # Indian Governance, EdTech & Health
    "digilocker", "parivahan", "uidai", "epfo", "incometax", "unacademy",
    "byjus", "physicswallah", "pw.live", "vedantu", "toppr", "doubtnut",
    "practo", "pharmeasy", "1mg", "tata1mg", "netmeds", "apollo247", "gov.in",
    "nic.in", "ac.in", "edu.in", "org.in", "co.in",
    
    # Security, OSINT, Data sources & Phone lookup services
    "hibp", "haveibeenpwned", "xposedornot", "epieos", "serper", "truecaller",
    "ignorant", "phoneinfoga", "leakcheck", "dehashed", "wayback", "archive",
    "eyecon", "sync.me", "whoscall", "callerid",
}

# Explicit blacklist of noisy or foreign-only regional networks that commonly cause false positives
INDIA_EXCLUDED_PLATFORMS = {
    "xing", "ixbt", "vk", "vkontakte", "odnoklassniki", "ok.ru", "habr", "rambler",
    "gmx", "web.de", "mail.ru", "yandex", "weibo", "qq", "wechat", "baidu",
    "douyin", "bilibili", "zhihu", "naver", "daum", "kakao", "niconico", "pixiv",
    "line", "cyworld", "fc2", "freelance.ru", "kwork", "fl.ru", "livejournal",
    "pikabu", "drom", "auto.ru", "cian", "avito", "virustotal",
    "kermit", "lobsters", "lobste.rs", "vbulletin", "forum", "photobucket",
    "patreon", "onlyfans", "buymeacoffee", "ko-fi", "bandcamp", "last.fm",
    "myspace", "soundcloud", "vimeo", "dailymotion", "flickr", "deviantart",
    "artstation", "wattpad", "gravatar", "disqus", "keybase",
}

# Gaming / entertainment platforms that are kept (not filtered out) but treated as LOW-VALUE
# identity evidence: scoring/confidence.py caps a cluster made up entirely of these to LOW
# match confidence and never lets it read as a confirmed link (a game handle is not who a
# person is). Matched as a substring against a profile's platform or source_url.
LOW_VALUE_PLATFORMS = {
    "leagueoflegends", "league-of-legends", "riotgames", "op.gg", "opgg",
    "valorant", "fortnite", "epicgames", "minecraft", "battle.net", "xbox",
    "playstation", "psn", "ubisoft", "ea.com", "origin.com", "roblox",
    "steam", "twitch", "bgmi", "freefire",
}


def is_low_value_platform(platform: str = "", url: str = "") -> bool:
    """True if this account sits on a gaming/entertainment platform (weak identity evidence)."""
    p, u = (platform or "").lower(), (url or "").lower()
    return any(g in p or g in u for g in LOW_VALUE_PLATFORMS)

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

        # If it's a core identifier or breach/data record, keep it
        if p.type in ("phone", "email", "upi", "name", "breach", "face", "url"):
            filtered.append(p)
            continue

        # For social_account or username enumerations, check against allowed Indian/Global platforms
        if any(inc in plat_lower or inc in url_lower for inc in INDIA_ALLOWED_PLATFORMS):
            filtered.append(p)
            continue

        # If it's from mock mode or custom source, keep it
        if p.data_mode == "mock" or plat_lower in ("mock", "manual", "custom"):
            filtered.append(p)
            continue

    return filtered
