"""General checksum utilities for iPod databases."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from .hash58 import compute_hash58
from .hash72 import compute_hash72

if TYPE_CHECKING:
    from ..device.models import ChecksumType

logger = logging.getLogger(__name__)

HASH72_OFFSET = 0x72
HASH72_LEN = 46
HASH58_OFFSET = 0x58
HASH58_LEN = 20


def _has_hash72(db_data: bytes) -> bool:
    return db_data[HASH72_OFFSET] == 0x01


def update_checksums(
    db_data: bytes,
    firewire_guid: Optional[str] = None,
    scheme: Optional["ChecksumType"] = None,
) -> bytes:
    """Update all checksums in iTunesDB data.

    iTunes (and Winamp) write *both* signatures for an iPod Classic: hash72 at 0x72 and hash58
    at 0x58. Which one the iPod checks depends on the device, so:

    - scheme HASH58 (iPod Classic 6G, Nano 3G/4G): hash72 is refreshed first if present, then
      hash58 last (the hash58 HMAC covers the hash72 bytes; the hash72 SHA1 zeroes hash58, so
      this order leaves both valid).
    - scheme HASH72: only hash72.
    - scheme unknown (None): hash72 if present, then hash58 when a FirewireGuid is known.

    Before this fix a database that already carried a hash72 signature only got hash72
    recomputed, leaving a stale hash58: a Classic 6G then showed no tracks or playlists.

    Args:
        db_data: Raw iTunesDB bytes.
        firewire_guid: Device FirewireGuid (needed for hash58).
        scheme: Device checksum type (``Device.checksum_type``), if known.

    Returns:
        iTunesDB bytes with updated checksums.
    """
    logger.info("Updating checksums")
    if len(db_data) < HASH72_OFFSET + HASH72_LEN:
        return db_data

    name = getattr(scheme, "name", None)
    data = db_data
    if name == "HASH72":
        logger.debug("Applied hash type: hash72")
        return compute_hash72(data, firewire_guid)

    if _has_hash72(data):
        logger.debug("Applied hash type: hash72 (existing signature)")
        data = compute_hash72(data, firewire_guid)

    if firewire_guid:
        # Sau cùng: HMAC hash58 tính cả vùng hash72 vừa ghi
        logger.debug("Applied hash type: hash58")
        data = compute_hash58(data, firewire_guid)
    elif name == "HASH58":
        logger.warning("hash58 needed but FirewireGuid is unknown; database left unsigned")
    return data
