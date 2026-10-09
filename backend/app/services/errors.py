class NotFoundError(Exception):
    """A referenced code (sku, region, ...) does not exist. Mapped to HTTP 404."""
