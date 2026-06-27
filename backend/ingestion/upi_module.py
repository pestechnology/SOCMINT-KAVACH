"""
backend/ingestion/upi_module.py — UPI seed handler (India-specific differentiator).

Pure-Python, no network:
  - parse the bank/PSP from the handle suffix (@oksbi -> SBI, @okhdfcbank -> HDFC, ...)
  - extract an embedded phone if the localpart is a 10-digit number
  - emit the localpart as a USERNAME RawProfile so the orchestrator can cascade it
    into the username tools (Maigret etc.)

Returns a list of RawProfiles: one bank-identification record + one username seed
(+ phone if embedded). Never raises.
"""
from __future__ import annotations

from backend.ingestion.base_module import BaseDataSource, RawProfile, make_profile

# Common NPCI/PSP handle suffixes -> bank / provider.
UPI_BANK_MAP = {
    "oksbi": "State Bank of India", "okhdfcbank": "HDFC Bank",
    "okicici": "ICICI Bank", "okaxis": "Axis Bank",
    "ybl": "PhonePe (Yes Bank)", "ibl": "PhonePe (ICICI)", "axl": "PhonePe (Axis)",
    "paytm": "Paytm Payments Bank", "apl": "Amazon Pay (Axis)",
    "okbizaxis": "Axis Bank (business)", "upi": "BHIM (NPCI)",
    "sbi": "State Bank of India", "hdfcbank": "HDFC Bank", "icici": "ICICI Bank",
    "axisbank": "Axis Bank", "kotak": "Kotak Mahindra Bank", "pnb": "Punjab National Bank",
    "yapl": "Google Pay (Axis)", "okwallet": "Wallet",
}


def parse_upi(upi_id: str) -> dict:
    upi_id = (upi_id or "").strip().lower()
    if "@" not in upi_id:
        return {"valid": False, "upi_id": upi_id}
    localpart, _, handle = upi_id.partition("@")
    bank = UPI_BANK_MAP.get(handle, f"Unknown PSP ({handle})")
    embedded_phone = localpart if localpart.isdigit() and len(localpart) == 10 else None
    return {"valid": True, "upi_id": upi_id, "localpart": localpart,
            "handle": handle, "bank": bank, "embedded_phone": embedded_phone}


class UPIScraper(BaseDataSource):
    name = "upi"

    async def _run_live(self, upi_id: str) -> list[RawProfile]:
        return self._build(upi_id)

    def _run_mock(self, upi_id: str) -> list[RawProfile]:
        return self._build(upi_id)

    def _build(self, upi_id: str) -> list[RawProfile]:
        info = parse_upi(upi_id)
        if not info["valid"]:
            return []
        out = [make_profile(
            "upi", info["upi_id"], "upi", "",
            metadata={"bank": info["bank"], "handle": info["handle"],
                      "localpart": info["localpart"],
                      "note": f"UPI ID belongs to {info['bank']} (from @{info['handle']} suffix)"},
        )]
        # cascade seed: the localpart as a username (orchestrator runs username tools on it)
        if info["localpart"] and not info["localpart"].isdigit():
            out.append(make_profile(
                "username", info["localpart"], "derived",
                "", metadata={"derived_from": info["upi_id"], "cascade": True},
            ))
        if info["embedded_phone"]:
            out.append(make_profile(
                "phone", info["embedded_phone"], "derived",
                "", metadata={"derived_from": info["upi_id"], "cascade": True},
            ))
        return out
