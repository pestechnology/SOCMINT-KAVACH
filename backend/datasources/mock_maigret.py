"""Mock Maigret scraper — returns realistic username-to-platform hits."""

import logging
from datetime import datetime, timezone

from backend.config import settings
from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, RawProfile, compute_hash

logger = logging.getLogger(__name__)


class MockMaigretScraper(BaseDataSource):
    """Mock implementation of Maigret username OSINT scraper."""

    @property
    def name(self) -> str:
        return "maigret"

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        """Return richer mock profiles for any requested username."""
        try:
            username = identifier.value.strip()
            username_lower = username.lower()
            now = datetime.now(timezone.utc).isoformat()

            # 3 profiles in main cluster (github, youtube, twitter)
            # 1 weak match red herring (instagram)
            # 1 unrelated singleton (reddit)

            mock_entries = [
                # Main Cluster (HIGH confidence)
                {
                    "platform": "github",
                    "value": username,
                    "source_url": f"https://github.com/{username}",
                    "metadata": {
                        "fullname": f"{username}",
                        "bio": "Passionate about investment, trading strategies, and maximizing returns.",
                        "photo_url": f"https://avatars.githubusercontent.com/{username}",
                        "photo_phash": "a3f5b8c2d1e4f6a7",
                        "phone": "+919876543210",
                        "email": f"{username_lower}@gmail.com",
                        "follower_count": 14200,
                        "created_at": "2021-01-25",
                        "location": "Mumbai, India",
                        "tags": ["trading", "finance"],
                    },
                },
                {
                    "platform": "youtube",
                    "value": username,
                    "source_url": f"https://www.youtube.com/@{username}/about",
                    "metadata": {
                        "fullname": f"{username} Trades",
                        "bio": "Daily investment tips, live trading sessions, and returns analysis.",
                        "photo_url": f"https://yt3.googleusercontent.com/{username}",
                        "photo_phash": "a3f5b8c2d1e4f6a7",
                        "phone": "+919876543210",
                        "email": f"{username_lower}@gmail.com",
                        "follower_count": 850,
                        "created_at": "2022-03-10",
                        "tags": ["video", "investing"],
                    },
                },
                {
                    "platform": "twitter",
                    "value": username,
                    "source_url": f"https://twitter.com/{username}",
                    "metadata": {
                        "fullname": f"{username}",
                        "bio": "Sharing market research, trading alpha, investment ideas, and portfolio returns.",
                        "photo_url": f"https://pbs.twimg.com/profile_images/{username}.jpg",
                        "photo_phash": "a3f5b8c2d1e4f6a7",
                        "phone": "+919876543210",
                        "email": f"{username_lower}@gmail.com",
                        "follower_count": 32000,
                        "created_at": "2021-06-15",
                        "location": "Mumbai",
                        "tags": ["social", "markets"],
                    },
                },
                # Weak Match (LOW confidence / Red Herring)
                {
                    "platform": "instagram",
                    "value": username,
                    "source_url": f"https://www.instagram.com/{username}",
                    "metadata": {
                        "fullname": f"{username} (Photography)",
                        "bio": "Just posting travel sunsets, cafe aesthetics, and weekend selfies.",
                        "photo_url": f"https://instagram.com/p/{username}.jpg",
                        "photo_phash": "1111222233334444",
                        "phone": "+919999999999",
                        "email": "totally_different_user@yahoo.com",
                        "follower_count": 5400,
                        "created_at": "2018-09-01",
                        "location": "Delhi, India",
                        "tags": ["social", "photos"],
                    },
                },
                # Unrelated (Singleton)
                {
                    "platform": "reddit",
                    "value": "unrelated_handle_x7",
                    "source_url": "https://www.reddit.com/user/unrelated_handle_x7",
                    "metadata": {
                        "fullname": "GamerX7",
                        "bio": "Hardware reviews, PC building guides, and gaming clips.",
                        "photo_url": None,
                        "photo_phash": "9999888877776666",
                        "phone": "+918888888888",
                        "email": "gamer_x7_unrelated@outlook.com",
                        "follower_count": 120,
                        "created_at": "2019-11-20",
                        "tags": ["forum", "gaming"],
                        "karma": 4580,
                    },
                },
            ]

            profiles: list[RawProfile] = []
            for entry in mock_entries:
                profiles.append(
                    RawProfile(
                        type="social_account",
                        value=entry["value"],
                        platform=entry["platform"],
                        source_url=entry["source_url"],
                        metadata=entry["metadata"],
                        data_mode=settings.DATA_MODE,
                        collected_at=now,
                        sha256=compute_hash(
                            entry["source_url"],
                            entry["platform"],
                            entry["value"],
                        ),
                    )
                )

            logger.info(
                "[%s] resolved '%s' → %d profiles (mode=%s)",
                self.name,
                username,
                len(profiles),
                settings.DATA_MODE,
            )
            return profiles

        except Exception as e:
            logger.warning("[%s] failed for '%s': %s", self.name, identifier.value, e)
            return []
