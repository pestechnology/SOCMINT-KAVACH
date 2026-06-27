"""
backend/ingestion/mock_scraper.py — fixed test data for development (never on stage).

Returns 4 profiles for any identifier:
  - TWO that are the SAME person (shared fullname "Arjun Mehta", shared photo_url,
    shared phone, overlapping late-night posting hours) -> must cluster HIGH
  - ONE more same-person corroborator (shared phone) to make the cluster robust
  - ONE RED HERRING: same username string, DIFFERENT fullname, no other overlap
    -> must score LOW/REJECT and must NOT join the HIGH cluster

Agent 5 (scoring) is built and tested against exactly this shape.
"""
from __future__ import annotations

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile


class MockScraper(BaseDataSource):
    name = "mock"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        # In mock mode resolve() routes to _run_mock; live path mirrors it for safety.
        return self._run_mock(identifier)

    def _run_mock(self, identifier: str) -> list[RawProfile]:
        u = identifier
        same_person_photo = "https://example.com/photos/arjun.jpg"
        same_phone = "+919876543210"

        return [
            # --- same person: Instagram ---
            make_profile(
                "social_account", u, "instagram",
                f"https://instagram.com/{u}",
                metadata={
                    "fullname": "Arjun Mehta",
                    "bio": "Investment advisor | DM for guaranteed returns",
                    "photo_url": same_person_photo,
                    "phone": same_phone,
                    "posting_hours": [23, 0, 1],
                },
                data_mode="mock",
            ),
            # --- same person: Telegram (shared phone + photo + hours + style) ---
            make_profile(
                "social_account", f"{u}_helpdesk", "telegram",
                f"https://t.me/{u}_helpdesk",
                metadata={
                    "fullname": "Arjun Mehta",
                    "bio": "Guaranteed returns, double your money. DM now.",
                    "photo_url": same_person_photo,
                    "phone": same_phone,
                    "posting_hours": [23, 0, 1, 2],
                },
                data_mode="mock",
            ),
            # --- same person: Reddit (shared phone, same style) ---
            make_profile(
                "social_account", f"{u}_redditor", "reddit",
                f"https://reddit.com/u/{u}_redditor",
                metadata={
                    "fullname": "Arjun Mehta",
                    "bio": "double your money, guaranteed returns",
                    "phone": same_phone,
                    "posting_hours": [0, 1],
                },
                data_mode="mock",
            ),
            # --- RED HERRING: same username string, different person, no overlap ---
            make_profile(
                "social_account", u, "linkedin",
                f"https://linkedin.com/in/{u}",
                metadata={
                    "fullname": "Arjun Sharma",            # different real name
                    "bio": "Corporate lawyer at a Bengaluru firm.",
                    "photo_url": "https://example.com/photos/different.jpg",
                    "posting_hours": [9, 10, 11],           # daytime, no overlap
                },
                data_mode="mock",
            ),
        ]
