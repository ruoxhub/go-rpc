import pytest

from llm.provider_url import ProviderUrlError, ProviderUrlValidator
from api.deps import provider_allowed_hosts


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["ftp://api.openai.com", "http://", "http://user:pass@api.openai.com"])
async def test_rejects_invalid_provider_urls(url):
    with pytest.raises(ProviderUrlError):
        await ProviderUrlValidator().validate(url)


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["api.openai.com", "generativelanguage.googleapis.com", "api.anthropic.com"])
async def test_default_allowlist_accepts_official_hosts(host):
    await ProviderUrlValidator().validate(f"https://{host}/v1")


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["unknown.example", "api.openai.com.evil.test"])
async def test_unknown_and_malicious_subdomains_are_rejected(host):
    with pytest.raises(ProviderUrlError):
        await ProviderUrlValidator().validate(f"https://{host}")


@pytest.mark.asyncio
async def test_allowlist_normalizes_case_and_trailing_dot():
    await ProviderUrlValidator({"CUSTOM.Example."}).validate("https://custom.example./v1")


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "100.100.100.200", "224.0.0.1", "0.0.0.0", "240.0.0.1"])
async def test_ip_literal_must_be_public(address):
    with pytest.raises(ProviderUrlError):
        await ProviderUrlValidator().validate(f"http://{address}")


@pytest.mark.asyncio
async def test_public_ip_literal_is_allowed():
    await ProviderUrlValidator().validate("https://93.184.216.34/v1")


@pytest.mark.asyncio
async def test_allowlist_explicitly_permits_loopback_ip():
    await ProviderUrlValidator({"127.0.0.1"}).validate("http://127.0.0.1:8045/v1")


@pytest.mark.asyncio
async def test_environment_explicitly_adds_custom_hosts(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_ALLOWED_HOSTS", " gateway.internal, CUSTOM.example. ")
    hosts = provider_allowed_hosts()
    assert "gateway.internal" in hosts
    assert "custom.example" in hosts
    await ProviderUrlValidator(hosts).validate("http://gateway.internal/v1")
