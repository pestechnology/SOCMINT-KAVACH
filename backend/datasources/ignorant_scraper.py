"""Live Ignorant library data source for phone registration checks."""

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from backend.datasources._helpers import normalize_phone
from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, IdentifierType, Platform, RawProfile, SourceTool

logger = logging.getLogger(__name__)


class IgnorantScraper(BaseDataSource):
    """Concrete scraper running synchronous ignorant library checks in a separate thread."""

    source_tool = SourceTool.IGNORANT

    @property
    def name(self) -> str:
        return "ignorant"

    def supports(self, identifier_type: IdentifierType) -> bool:
        return identifier_type == IdentifierType.PHONE

    def _run_ignorant(self, phone: str) -> list[dict[str, Any]]:
        try:
            import ignorant
            results = []
            for mod_name in ["amazon", "instagram", "snapchat"]:
                try:
                    mod = getattr(getattr(ignorant, "modules", None), mod_name, None)
                    if mod and hasattr(mod, "check"):
                        exists = mod.check(phone)
                        results.append({"name": mod_name, "exists": bool(exists)})
                except Exception:
                    pass
            return results
        except Exception as e:
            logger.warning("[%s] synchronous execution failed: %s", self.name, e)
            return []

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        if identifier.type != IdentifierType.PHONE:
            return []

        norm_phone = normalize_phone(identifier.value)

        try:
            results = await asyncio.to_thread(self._run_ignorant, norm_phone)
        except Exception as e:
            logger.warning("[%s] asyncio.to_thread failed: %s", self.name, e)
            return []

        now_iso = datetime.now(timezone.utc).isoformat()
        profiles: list[RawProfile] = []

        if not isinstance(results, list):
            return []

        for res in results:
            if not isinstance(res, dict) or not res.get("exists"):
                continue

            name_str = str(res.get("name", "")).lower().strip()
            if not name_str:
                continue

            try:
                platform_val = Platform[name_str.upper()].value
            except (KeyError, AttributeError):
                platform_val = Platform.OTHER.value

            source_url = f"https://{name_str}.com"
            sha256_hash = hashlib.sha256(f"{norm_phone}:{platform_val}:{source_url}".encode("utf-8")).hexdigest()

            metadata: dict[str, Any] = {
                "fullname": "",
                "bio": "",
                "photo_url": "",
                "registered": True,
                "source_tool": self.source_tool.value,
                "source_query": norm_phone,
            }

            profile = RawProfile(
                type="phone_registration",
                value=norm_phone,
                platform=platform_val,
                source_url=source_url,
                data_mode="live",
                metadata=metadata,
                collected_at=now_iso,
                sha256=sha256_hash,
            )
            profiles.append(profile)

        return profiles
