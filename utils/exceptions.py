"""
Shared exception types for the pipeline.
"""


class RateLimitError(Exception):
    """Raised when any external API returns a 429 or quota-exceeded error."""

    SERVICE_LABELS = {
        "llm":      "FocusChain LLM (AI model)",
        "serper":   "Serper (Google Search)",
        "apollo":   "Apollo (Contacts)",
        "apify":    "Apify (Web scraper)",
        "tracxn":   "Tracxn (Funding data)",
        "hunter":   "Hunter.io (Email finder)",
    }

    def __init__(self, service: str, message: str = "", retry_after: int = 0):
        self.service     = service
        self.retry_after = retry_after  # seconds hint, 0 = unknown
        label = self.SERVICE_LABELS.get(service, service)
        super().__init__(message or f"{label} rate limit reached")

    @property
    def label(self) -> str:
        return self.SERVICE_LABELS.get(self.service, self.service)
