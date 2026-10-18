"""LLM provider endpoint allowlist validation."""
from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


DEFAULT_ALLOWED_HOSTS = frozenset({
    "api.openai.com",
    "generativelanguage.googleapis.com",
    "api.anthropic.com",
})


class ProviderUrlError(ValueError):
    pass


def normalize_host(host: str) -> str:
    try:
        return host.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ProviderUrlError("Provider host is invalid") from error


class ProviderUrlValidator:
    def __init__(self, allowlisted_hosts: set[str] | frozenset[str] | None = None) -> None:
        configured = DEFAULT_ALLOWED_HOSTS if allowlisted_hosts is None else allowlisted_hosts
        self._allowlisted_hosts = frozenset(normalize_host(host.strip()) for host in configured if host.strip())

    async def validate(self, url: str) -> None:
        try:
            parsed = urlsplit(url)
            parsed.port
        except ValueError as error:
            raise ProviderUrlError("Provider URL is invalid") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ProviderUrlError("Provider URL is invalid")

        host = normalize_host(parsed.hostname)
        if host in self._allowlisted_hosts:
            return
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            raise ProviderUrlError("Provider host is not allowlisted")
        if (
            not address.is_global
            or address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            raise ProviderUrlError("Provider IP is unsafe")
