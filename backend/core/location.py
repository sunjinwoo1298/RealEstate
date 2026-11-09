"""Helpers for presenting a project's location to buyers."""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote_plus


def map_url_for(project_name: Optional[str], location: Optional[str]) -> Optional[str]:
    """
    A Google Maps search link built from the project's stored name and
    location text, so a buyer can open the site on their phone with one tap.
    Returns None when no location has been recorded (never a made-up pin).
    """
    location = " ".join((location or "").split())
    if not location:
        return None
    query = " ".join(part for part in (" ".join((project_name or "").split()), location) if part)
    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"
