"""Google Gemini (AI Studio) credential provider for ``mi auth``.

Collects a ``GOOGLE_API_KEY`` for use with the ``google:`` model provider,
which calls the Generative Language API via Google AI Studio.
"""

from __future__ import annotations

from ..context import CredentialField
from .base import ManualProvider


class GoogleGeminiProvider(ManualProvider):
    name = "Google Gemini"
    slug = "google-gemini"
    description = "Google Gemini via AI Studio"
    console_url = "https://aistudio.google.com/apikey"
    fields = [
        CredentialField("GOOGLE_API_KEY", "Google AI Studio API key"),
    ]
