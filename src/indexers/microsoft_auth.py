"""
Shared Microsoft Graph API authentication for Outlook, Teams, etc.

Environment variables required:
- MICROSOFT_CLIENT_ID: Azure AD application client ID
- MICROSOFT_CLIENT_SECRET: Azure AD application client secret  
- MICROSOFT_TENANT_ID: Azure AD tenant ID (optional, defaults to 'common')

For personal/consumer accounts, use tenant_id='consumers'.
For work/school accounts, use your organization's tenant ID or 'organizations'.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Optional

import httpx


@dataclass
class TokenResponse:
    """OAuth2 token response."""

    access_token: str
    token_type: str
    expires_in: int
    scope: str
    refresh_token: Optional[str] = None


class MicrosoftGraphAuth:
    """Handles Microsoft Graph API authentication using OAuth2 client credentials."""

    AUTHORITY_URL = "https://login.microsoftonline.com"
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize Microsoft Graph auth.

        Args:
            client_id: Azure AD app client ID (or MICROSOFT_CLIENT_ID env var)
            client_secret: Azure AD app client secret (or MICROSOFT_CLIENT_SECRET env var)
            tenant_id: Azure AD tenant ID (or MICROSOFT_TENANT_ID env var, defaults to 'common')
        """
        self.client_id = client_id or os.environ.get("MICROSOFT_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.environ.get("MICROSOFT_TENANT_ID", "common")

        if not self.client_id:
            raise ValueError(
                "Microsoft client ID required. Set MICROSOFT_CLIENT_ID env var."
            )
        if not self.client_secret:
            raise ValueError(
                "Microsoft client secret required. Set MICROSOFT_CLIENT_SECRET env var."
            )

        self._access_token: Optional[str] = None
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def token_url(self) -> str:
        """Get the OAuth2 token endpoint URL."""
        return f"{self.AUTHORITY_URL}/{self.tenant_id}/oauth2/v2.0/token"

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def get_access_token(
        self, scopes: Optional[list[str]] = None
    ) -> str:
        """
        Get an access token for Microsoft Graph API.

        Args:
            scopes: OAuth2 scopes (defaults to Graph API default scope)

        Returns:
            Access token string
        """
        if scopes is None:
            scopes = ["https://graph.microsoft.com/.default"]

        client = await self._get_http_client()

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": " ".join(scopes),
            "grant_type": "client_credentials",
        }

        response = await client.post(self.token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        self._access_token = token_data["access_token"]
        return self._access_token

    async def get_headers(self) -> dict[str, str]:
        """Get authorization headers for Graph API requests."""
        if not self._access_token:
            await self.get_access_token()

        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    async def graph_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[dict[str, Any]] = None,
        json_data: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Make an authenticated request to Microsoft Graph API.

        Args:
            endpoint: API endpoint (relative to /v1.0, e.g., '/me/messages')
            method: HTTP method
            params: Query parameters
            json_data: JSON body data

        Returns:
            JSON response as dict
        """
        client = await self._get_http_client()
        headers = await self.get_headers()

        url = f"{self.GRAPH_API_BASE}{endpoint}"

        response = await client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
        )
        response.raise_for_status()

        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
