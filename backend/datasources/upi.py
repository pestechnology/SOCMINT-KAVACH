"""Live UPI data source for parsing UPI IDs."""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

from backend.datasources.base import BaseDataSource
from backend.schemas import Identifier, IdentifierType, Platform, RawProfile, SourceTool

logger = logging.getLogger(__name__)


class UPIParser(BaseDataSource):
    """Concrete scraper parsing UPI handles into profile representations."""

    source_tool = SourceTool.UPI_PARSER

    @property
    def name(self) -> str:
        return "upi_parser"

    def supports(self, identifier_type: IdentifierType) -> bool:
        return identifier_type == IdentifierType.UPI

    async def resolve(self, identifier: Identifier) -> list[RawProfile]:
        if identifier.type != IdentifierType.UPI:
            return []

        full_upi_id = identifier.value.strip().lower()
        if not full_upi_id or "@" not in full_upi_id:
            return []

        if full_upi_id.startswith("@") or full_upi_id.endswith("@"):
            return []

        prefix, bank_handle = full_upi_id.split("@", 1)
        if not prefix or not bank_handle:
            return []

        platform_val = Platform.OTHER.value
        source_url = f"upi://{full_upi_id}"
        sha256_hash = hashlib.sha256(f"{full_upi_id}:{platform_val}:{source_url}".encode("utf-8")).hexdigest()
        now_iso = datetime.now(timezone.utc).isoformat()

        metadata: dict[str, Any] = {
            "fullname": "",
            "bio": "",
            "photo_url": "",
            "bank_handle": bank_handle,
            "username_prefix": prefix,
            "source_tool": self.source_tool.value,
            "source_query": full_upi_id,
        }

        profile = RawProfile(
            type="upi_id",
            value=full_upi_id,
            platform=platform_val,
            source_url=source_url,
            data_mode="live",
            metadata=metadata,
            collected_at=now_iso,
            sha256=sha256_hash,
        )

        return [profile]
