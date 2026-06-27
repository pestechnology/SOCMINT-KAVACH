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


import re

class MockScraper(BaseDataSource):
    name = "mock"

    async def _run_live(self, identifier: str) -> list[RawProfile]:
        # In mock mode resolve() routes to _run_mock; live path mirrors it for safety.
        return self._run_mock(identifier)

    def _run_mock(self, identifier: str) -> list[RawProfile]:
        identifier = (identifier or "").strip()
        
        # 1. Determine type and extract clean name/username
        if "@" in identifier:
            # Email or UPI ID
            localpart, _, _ = identifier.partition("@")
            username = localpart
            if "." in localpart:
                fullname = " ".join(part.capitalize() for part in localpart.split("."))
            else:
                fullname = localpart.capitalize()
        elif identifier.replace("+", "").isdigit():
            # Phone number
            username = f"user_{identifier[-4:]}"
            fullname = f"Phone User {identifier[-4:]}"
        elif " " in identifier:
            # Name seed
            fullname = identifier
            # Generate a username: e.g. vismay_hs
            parts = identifier.lower().split()
            if len(parts) >= 2:
                username = f"{parts[0]}_{''.join(p[0] for p in parts[1:])}"
            else:
                username = parts[0]
        else:
            # Username seed
            username = identifier
            # Generate a name: e.g. vismay_hs -> Vismay Hs
            fullname = " ".join(part.capitalize() for part in re.split(r"[-_.]", identifier))

        # Format red herring name
        name_parts = fullname.split()
        if len(name_parts) >= 2:
            red_herring_name = f"{name_parts[0]} {''.join(name_parts[1:-1])} Sharma" if len(name_parts) > 2 else f"{name_parts[0]} Sharma"
        else:
            red_herring_name = f"{fullname} Lawyer"

        # Generate a phone number based on username or fixed
        same_phone = "+919876543210"
        same_person_photo = f"https://example.com/photos/{username}.jpg"

        return [
            # --- same person: Instagram ---
            make_profile(
                "social_account", username, "instagram",
                f"https://instagram.com/{username}",
                metadata={
                    "fullname": fullname,
                    "bio": "Investment advisor | DM for guaranteed returns",
                    "photo_url": same_person_photo,
                    "phone": same_phone,
                    "posting_hours": [23, 0, 1],
                },
                data_mode="mock",
            ),
            # --- same person: Telegram (shared phone + photo + hours + style) ---
            make_profile(
                "social_account", f"{username}_helpdesk", "telegram",
                f"https://t.me/{username}_helpdesk",
                metadata={
                    "fullname": fullname,
                    "bio": "Guaranteed returns, double your money. DM now.",
                    "photo_url": same_person_photo,
                    "phone": same_phone,
                    "posting_hours": [23, 0, 1, 2],
                },
                data_mode="mock",
            ),
            # --- same person: Reddit (shared phone, same style) ---
            make_profile(
                "social_account", f"{username}_redditor", "reddit",
                f"https://reddit.com/u/{username}_redditor",
                metadata={
                    "fullname": fullname,
                    "bio": "double your money, guaranteed returns",
                    "phone": same_phone,
                    "posting_hours": [0, 1],
                },
                data_mode="mock",
            ),
            # --- RED HERRING: same username string, different person, no overlap ---
            make_profile(
                "social_account", username, "linkedin",
                f"https://linkedin.com/in/{username}",
                metadata={
                    "fullname": red_herring_name,            # different real name
                    "bio": "Corporate lawyer at a Bengaluru firm.",
                    "photo_url": "https://example.com/photos/different.jpg",
                    "posting_hours": [9, 10, 11],           # daytime, no overlap
                },
                data_mode="mock",
            ),
        ]
