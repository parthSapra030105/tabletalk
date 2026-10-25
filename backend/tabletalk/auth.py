"""
One shared sign-in for a hosted copy, using the browser's own prompt (HTTP Basic).

Off unless APP_USER and APP_PASSWORD are set, so local development is unchanged. The
browser then sends the credentials with every request, including the UI's fetch and XHR
calls, so nothing in the frontend needs to know about it. /healthz stays open for uptime
monitors: it answers "ok" and touches nothing else.
"""

import base64
import binascii
import hmac
import os

from django.http import HttpResponse

OPEN_PATHS = {"/healthz"}


class BasicAuth:
    def __init__(self, get_response):
        self.get_response = get_response
        user, password = os.environ.get("APP_USER", ""), os.environ.get("APP_PASSWORD", "")
        self.expected = f"{user}:{password}".encode() if user and password else None

    def __call__(self, request):
        if (self.expected and request.path not in OPEN_PATHS
                and not self._signed_in(request.headers.get("Authorization", ""))):
            response = HttpResponse("Sign-in required", status=401)
            response["WWW-Authenticate"] = 'Basic realm="Tabletalk", charset="UTF-8"'
            return response
        return self.get_response(request)

    def _signed_in(self, header):
        scheme, _, value = header.partition(" ")
        if scheme.lower() != "basic":
            return False
        try:
            given = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError):
            return False
        return hmac.compare_digest(given, self.expected)
