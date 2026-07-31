"""SSRF test suite for browser policy validation."""

from __future__ import annotations
import pytest
from pathlib import Path

from windagent_tools.browser import (
    AgentBrowserConfig,
    AgentBrowserPolicyError,
    validate_navigation_url,
)


class TestSSRFProtection:
    """Test SSRF (Server-Side Request Forgery) protection."""

    def test_reject_private_ipv4(self):
        """Reject private IPv4 addresses."""
        private_ips = [
            "10.0.0.1",
            "10.255.255.255",
            "172.16.0.1",
            "172.31.255.255",
            "192.168.0.1",
            "192.168.255.255",
            "127.0.0.1",
            "127.255.255.255",
            "169.254.0.1",
            "169.254.255.255",
            "0.0.0.0",
            "224.0.0.1",
            "239.255.255.255",
            "240.0.0.1",
            "255.255.255.255",
        ]
        for ip in private_ips:
            url = f"http://{ip}:8000/path"
            with pytest.raises(AgentBrowserPolicyError, match="Private|non-routable|reserved|unspecified"):
                validate_navigation_url(url, allowed_domains=(), allow_private_network=False)

    def test_reject_private_ipv6(self):
        """Reject private IPv6 addresses."""
        private_ips = [
            "::1",
            "fe80::1",
            "fc00::1",
            "fd00::1",
        ]
        for ip in private_ips:
            url = f"http://[{ip}]:8000/path"
            with pytest.raises(AgentBrowserPolicyError, match="Private|non-routable|reserved|unspecified"):
                validate_navigation_url(url, allowed_domains=(), allow_private_network=False)

    def test_reject_localhost(self):
            """Reject localhost and .local domains."""
            urls = [
                "http://localhost:8000/path",
                "http://sub.localhost/path",  # subdomain of localhost
                "http://myhost.local/path",
            ]
            for url in urls:
                with pytest.raises(AgentBrowserPolicyError, match="Private or local"):
                    validate_navigation_url(url, allowed_domains=(), allow_private_network=False)
        
            # localhost.localdomain is NOT a .local TLD domain, so it's allowed
            result = validate_navigation_url(
                "http://localhost.localdomain/path",
                allowed_domains=(),
                allow_private_network=False,
            )
            assert result == "http://localhost.localdomain/path"

    def test_allow_private_network_opt_in(self):
        """Allow private network when explicitly opted in."""
        url = "http://127.0.0.1:8000/fixture"
        # Should not raise when allow_private_network=True
        result = validate_navigation_url(url, allowed_domains=("127.0.0.1",), allow_private_network=True)
        assert result == url

    def test_reject_credentials_in_url(self):
        """Reject embedded credentials in URL."""
        urls = [
            "http://user:pass@example.com/path",
            "https://user@example.com/path",
            "http://:password@example.com/path",
        ]
        for url in urls:
            with pytest.raises(AgentBrowserPolicyError, match="Credentials must not be embedded"):
                validate_navigation_url(url, allowed_domains=("example.com",), allow_private_network=False)

    def test_reject_non_http_scheme(self):
        """Reject non-http/https schemes."""
        urls = [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "ws://example.com/ws",
            "wss://example.com/ws",
        ]
        for url in urls:
            with pytest.raises(AgentBrowserPolicyError, match="Only http and https"):
                validate_navigation_url(url, allowed_domains=("example.com",), allow_private_network=False)

    def test_enforce_domain_allowlist(self):
        """Enforce domain allowlist after redirects."""
        # Allowed domain
        result = validate_navigation_url(
            "https://youtube.com/watch?v=test",
            allowed_domains=("youtube.com", "*.youtube.com", "youtu.be"),
            allow_private_network=False,
        )
        assert result == "https://youtube.com/watch?v=test"

        # Disallowed domain
        with pytest.raises(AgentBrowserPolicyError, match="outside the configured domain policy"):
            validate_navigation_url(
                "https://evil.com/path",
                allowed_domains=("youtube.com", "*.youtube.com"),
                allow_private_network=False,
            )

    def test_subdomain_matching(self):
        """Test wildcard subdomain matching."""
        allowed = ("*.example.com", "example.com")
        test_cases = [
            ("https://example.com", True),
            ("https://sub.example.com", True),
            ("https://deep.sub.example.com", True),
            ("https://evil.com", False),
            ("https://example.com.evil.com", False),
        ]
        for url, should_pass in test_cases:
            if should_pass:
                result = validate_navigation_url(url, allowed_domains=allowed, allow_private_network=False)
                assert result == url
            else:
                with pytest.raises(AgentBrowserPolicyError):
                    validate_navigation_url(url, allowed_domains=allowed, allow_private_network=False)

    def test_config_validates_authenticated_profile(self):
        """Config rejects authenticated profile without explicit opt-in."""
        with pytest.raises(AgentBrowserPolicyError, match="authenticated=true"):
            AgentBrowserConfig(
                binary="agent-browser",
                session="test",
                profile="Default",
            )

    def test_config_validates_containment_with_profile(self):
        """Config rejects native containment with profile."""
        with pytest.raises(AgentBrowserPolicyError, match="native domain containment cannot be combined with"):
            AgentBrowserConfig(
                binary="agent-browser",
                session="test",
                authenticated=True,
                profile="Default",
                allowed_domains=("example.com",),
                containment_mode="native",
            )


class TestDNSRebinding:
    """Test DNS rebinding protection."""

    def test_dns_rebinding_protection_blocks_private_ip_resolution(self, monkeypatch):
        """Test that hostname resolving to private IP via DNS is blocked."""
        import socket

        def mock_getaddrinfo(host, port, *args, **kwargs):
            if host == "rebound-domain.com":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

        monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

        with pytest.raises(AgentBrowserPolicyError, match="DNS resolution for host 'rebound-domain.com' resolved to private"):
            validate_navigation_url(
                "http://rebound-domain.com/path",
                allowed_domains=(),
                allow_private_network=False,
            )

    def test_dns_rebinding_protection_allows_public_ip_resolution(self, monkeypatch):
        """Test that hostname resolving to public IP is allowed."""
        import socket

        def mock_getaddrinfo(host, port, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]

        monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

        result = validate_navigation_url(
            "http://example.com/path",
            allowed_domains=(),
            allow_private_network=False,
        )
        assert result == "http://example.com/path"


class TestAgentBrowserConfig:
    """Test AgentBrowserConfig validation."""

    def test_valid_config(self):
        """Test valid config creation."""
        config = AgentBrowserConfig(
            binary="agent-browser",
            session="test-session",
            authenticated=False,
            allowed_domains=("example.com",),
            timeout_seconds=60.0,
        )
        assert config.session == "test-session"

    def test_invalid_session_name(self):
        """Test invalid session name rejected."""
        with pytest.raises(AgentBrowserPolicyError):
            AgentBrowserConfig(
                binary="agent-browser",
                session="invalid session!",
            )

    def test_empty_binary_rejected(self):
        """Test empty binary path rejected."""
        with pytest.raises(AgentBrowserPolicyError, match="binary path cannot be empty"):
            AgentBrowserConfig(binary="   ")

    def test_timeout_positive(self):
        """Test timeout must be positive."""
        with pytest.raises(AgentBrowserPolicyError, match="timeout must be positive"):
            AgentBrowserConfig(binary="agent-browser", timeout_seconds=0)

    def test_retry_attempts_bounds(self):
        """Test retry attempts bounds."""
        with pytest.raises(AgentBrowserPolicyError):
            AgentBrowserConfig(binary="agent-browser", retry_attempts=0)
        with pytest.raises(AgentBrowserPolicyError):
            AgentBrowserConfig(binary="agent-browser", retry_attempts=5)

    def test_max_output_bounds(self):
        """Test max output chars bounds."""
        with pytest.raises(AgentBrowserPolicyError):
            AgentBrowserConfig(binary="agent-browser", max_output_chars=500)
        with pytest.raises(AgentBrowserPolicyError):
            AgentBrowserConfig(binary="agent-browser", max_output_chars=3_000_000)