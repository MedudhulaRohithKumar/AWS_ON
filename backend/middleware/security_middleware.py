"""
CSR Security Middleware
=======================
Applies enterprise security headers, enforces Content Security Policy (CSP),
strips server fingerprinting headers, prevents clickjacking and MIME-sniffing,
and enforces request payload size limits.
"""

import json
import logging
from typing import Set

logger = logging.getLogger(__name__)

# Headers that reveal server identity, framework, or runtime
SENSITIVE_HEADERS: Set[bytes] = {
    b"server",
    b"x-powered-by",
    b"x-runtime",
    b"x-aspnet-version",
    b"x-aspnetmvc-version",
    b"x-envoy-upstream-service-time",
}

# Maximum request payload size (5 MB)
MAX_CONTENT_LENGTH = 5 * 1024 * 1024

# Enterprise-grade Content Security Policy
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com data:; "
    "img-src 'self' data: https:; "
    "connect-src 'self' https:; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "upgrade-insecure-requests"
)

# Granular Permissions Policy to disable unneeded browser hardware and tracking features
PERMISSIONS_POLICY = (
    "accelerometer=(), "
    "autoplay=(), "
    "camera=(), "
    "cross-origin-isolated=(), "
    "display-capture=(), "
    "encrypted-media=(), "
    "fullscreen=(self), "
    "geolocation=(), "
    "gyroscope=(), "
    "keyboard-map=(), "
    "magnetometer=(), "
    "microphone=(), "
    "midi=(), "
    "payment=(), "
    "picture-in-picture=(), "
    "publickey-credentials-get=(), "
    "screen-wake-lock=(), "
    "sync-xhr=(), "
    "usb=(), "
    "xr-spatial-tracking=()"
)


class SecurityHeadersMiddleware:
    """
    Pure ASGI middleware that intercepts all HTTP responses to:
    1. Strip information-leakage headers (Server, X-Powered-By).
    2. Inject robust security headers (CSP, HSTS, X-Frame-Options, etc.).
    3. Disable client caching on sensitive /api/* endpoints.
    4. Protect against memory exhaustion / payload DoS.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Payload size check
        headers_dict = dict(scope.get("headers", []))
        content_length_raw = headers_dict.get(b"content-length")
        if content_length_raw and content_length_raw.isdigit():
            if int(content_length_raw) > MAX_CONTENT_LENGTH:
                body = json.dumps({"detail": "Request payload exceeds 5MB limit."}).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                        (b"connection", b"close"),
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": body,
                })
                return

        path = scope.get("path", "")
        is_api = path.startswith("/api/")

        async def send_with_hardened_headers(message):
            if message["type"] == "http.response.start":
                existing_headers = message.get("headers", [])

                # Strip fingerprinting headers
                filtered = [
                    (k, v) for k, v in existing_headers
                    if k.lower() not in SENSITIVE_HEADERS
                ]

                # Security headers to enforce
                headers_to_add = [
                    (b"content-security-policy", CSP_POLICY.encode("utf-8")),
                    (b"x-frame-options", b"DENY"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"permissions-policy", PERMISSIONS_POLICY.encode("utf-8")),
                    (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                    (b"cross-origin-resource-policy", b"same-origin"),
                    (b"x-xss-protection", b"0"),  # Modern best practice: disable legacy buggy XSS auditor
                ]

                # Sensitive API responses must never be cached by intermediaries
                if is_api:
                    headers_to_add.extend([
                        (b"cache-control", b"no-store, no-cache, must-revalidate, max-age=0"),
                        (b"pragma", b"no-cache"),
                        (b"expires", b"0"),
                    ])

                existing_names = {k.lower() for k, _ in filtered}
                final_headers = filtered[:]

                for k, v in headers_to_add:
                    if k not in existing_names:
                        final_headers.append((k, v))
                    else:
                        # Overwrite if already present
                        final_headers = [(hk, hv) if hk.lower() != k else (k, v) for hk, hv in final_headers]

                message["headers"] = final_headers

            await send(message)

        await self.app(scope, receive, send_with_hardened_headers)
