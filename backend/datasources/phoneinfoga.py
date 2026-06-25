"""Live PhoneInfoga CLI data source for phone lookups."""

import asyncio
import hashlib
import logging
import re
import shutil
from datetime import datetime, timezone
from typing import Any

from backend.datasources._helpers import normalize_phone
from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, IdentifierType, Platform, RawProfile, SourceTool

logger = logging.getLogger(__name__)


class PhoneInfogaScraper(BaseDataSource):
    """Concrete scraper running real phoneinfoga CLI via async subprocess."""

    source_tool = SourceTool.PHONEINFOGA

    def __init__(self) -> None:
        self.cli_path = shutil.which("phoneinfoga")
        if not self.cli_path:
            logger.warning("[phoneinfoga] CLI tool 'phoneinfoga' not found on PATH.")

    @property
    def name(self) -> str:
        return "phoneinfoga"

    def supports(self, identifier_type: IdentifierType) -> bool:
        return identifier_type == IdentifierType.PHONE

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        if identifier.type != IdentifierType.PHONE:
            return []

        cli_path = self.cli_path or shutil.which("phoneinfoga")
        if not cli_path:
            logger.warning("[%s] CLI tool 'phoneinfoga' not found.", self.name)
            return []

        norm_phone = normalize_phone(identifier.value)
        cmd = [cli_path, "scan", "-n", norm_phone]
        logger.debug("[%s] launching subprocess: %s", self.name, " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=30.0
            )

            if proc.returncode != 0:
                logger.warning("[%s] exited with code %d", self.name, proc.returncode)
                return []

            stdout_str = stdout_bytes.decode("utf-8", errors="replace")

        except asyncio.TimeoutError:
            logger.warning("[%s] timed out after 30.0s for '%s'", self.name, norm_phone)
            try:
                proc.kill()
            except Exception:
                pass
            return []
        except Exception as e:
            logger.warning("[%s] subprocess execution failed: %s", self.name, e)
            return []

        urls = re.findall(r"https?://\S+", stdout_str)
        now_iso = datetime.now(timezone.utc).isoformat()
        profiles: list[RawProfile] = []

        for url in sorted(set(urls)):
            clean_url = url.strip()
            platform_val = Platform.OTHER.value
            sha256_hash = hashlib.sha256(f"{norm_phone}:{platform_val}:{clean_url}".encode("utf-8")).hexdigest()

            metadata: dict[str, Any] = {
                "fullname": "",
                "bio": "",
                "photo_url": "",
                "source_tool": self.source_tool.value,
                "source_query": norm_phone,
            }

            profile = RawProfile(
                type="phone_lookup",
                value=norm_phone,
                platform=platform_val,
                source_url=clean_url,
                data_mode="live",
                metadata=metadata,
                collected_at=now_iso,
                sha256=sha256_hash,
            )
            profiles.append(profile)

        return profiles
