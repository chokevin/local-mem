"""
Microsoft Teams Indexer - Imports Teams chat messages as workstreams.

Azure AD App Registration Setup:
================================
1. Go to Azure Portal > Azure Active Directory > App registrations
2. Click "New registration"
3. Name your app (e.g., "Local Mem Teams Indexer")
4. Set supported account types (typically "Single tenant")
5. Click "Register"

6. Note the following values for environment variables:
   - Application (client) ID -> MICROSOFT_CLIENT_ID
   - Directory (tenant) ID -> MICROSOFT_TENANT_ID

7. Go to "Certificates & secrets" > "New client secret"
   - Create a new secret and copy the value -> MICROSOFT_CLIENT_SECRET

8. Go to "API permissions" > "Add a permission" > "Microsoft Graph"
   - Add these Delegated permissions:
     * ChannelMessage.Read.All (for channel messages)
     * Chat.Read (for 1:1 and group chats)
     * Team.ReadBasic.All (to list teams)
     * Channel.ReadBasic.All (to list channels)
   - Or for Application permissions (daemon/service):
     * ChannelMessage.Read.All
     * Chat.Read.All
     * Team.ReadBasic.All
     * Channel.ReadBasic.All

9. Grant admin consent for the permissions

Environment Variables:
=====================
- MICROSOFT_CLIENT_ID: Azure AD application (client) ID
- MICROSOFT_CLIENT_SECRET: Azure AD client secret
- MICROSOFT_TENANT_ID: Azure AD directory (tenant) ID
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

try:
    import msal
    import requests

    MSAL_AVAILABLE = True
except ImportError:
    MSAL_AVAILABLE = False

from ..types import CreateWorkstreamRequest


@dataclass
class TeamsMessage:
    """Represents a Teams chat message."""

    id: str
    content: str
    sender: str
    created_at: datetime
    reply_to_id: Optional[str] = None
    attachments: list[dict[str, Any]] | None = None


@dataclass
class TeamsChannel:
    """Represents a Teams channel."""

    id: str
    display_name: str
    description: Optional[str] = None


@dataclass
class TeamsTeam:
    """Represents a Teams team."""

    id: str
    display_name: str
    description: Optional[str] = None


class TeamsIndexerError(Exception):
    """Custom exception for Teams indexer errors."""

    pass


class TeamsIndexer:
    """
    Indexes Microsoft Teams chat messages into workstreams.

    Uses Microsoft Graph API to fetch Teams data and converts
    chat threads into workstream format.
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    GRAPH_SCOPES = ["https://graph.microsoft.com/.default"]

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Initialize the Teams indexer.

        Args:
            client_id: Azure AD application client ID (or use MICROSOFT_CLIENT_ID env var)
            client_secret: Azure AD client secret (or use MICROSOFT_CLIENT_SECRET env var)
            tenant_id: Azure AD tenant ID (or use MICROSOFT_TENANT_ID env var)

        Raises:
            TeamsIndexerError: If required credentials are missing or msal not installed
        """
        if not MSAL_AVAILABLE:
            raise TeamsIndexerError(
                "msal package not installed. Run: pip install msal requests"
            )

        self.client_id = client_id or os.environ.get("MICROSOFT_CLIENT_ID")
        self.client_secret = client_secret or os.environ.get("MICROSOFT_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.environ.get("MICROSOFT_TENANT_ID")

        if not all([self.client_id, self.client_secret, self.tenant_id]):
            missing = []
            if not self.client_id:
                missing.append("MICROSOFT_CLIENT_ID")
            if not self.client_secret:
                missing.append("MICROSOFT_CLIENT_SECRET")
            if not self.tenant_id:
                missing.append("MICROSOFT_TENANT_ID")
            raise TeamsIndexerError(
                f"Missing required credentials: {', '.join(missing)}. "
                "See module docstring for Azure AD setup instructions."
            )

        self._access_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None

    def _get_access_token(self) -> str:
        """Get or refresh the access token using client credentials flow."""
        if self._access_token and self._token_expires:
            if datetime.now() < self._token_expires:
                return self._access_token

        authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        app = msal.ConfidentialClientApplication(
            self.client_id,
            authority=authority,
            client_credential=self.client_secret,
        )

        result = app.acquire_token_for_client(scopes=self.GRAPH_SCOPES)

        if "access_token" not in result:
            error = result.get("error_description", result.get("error", "Unknown error"))
            raise TeamsIndexerError(f"Failed to acquire access token: {error}")

        self._access_token = result["access_token"]
        # Token typically expires in 1 hour, refresh 5 minutes early
        expires_in = result.get("expires_in", 3600)
        self._token_expires = datetime.now().replace(
            second=datetime.now().second + expires_in - 300
        )

        return self._access_token

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """Make an authenticated request to the Graph API."""
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.GRAPH_BASE_URL}{endpoint}"
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 401:
            # Token might be expired, clear and retry
            self._access_token = None
            token = self._get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code != 200:
            raise TeamsIndexerError(
                f"Graph API request failed ({response.status_code}): {response.text}"
            )

        return response.json()

    def list_teams(self) -> list[TeamsTeam]:
        """List all teams the app has access to."""
        data = self._make_request("/teams")
        return [
            TeamsTeam(
                id=team["id"],
                display_name=team.get("displayName", ""),
                description=team.get("description"),
            )
            for team in data.get("value", [])
        ]

    def list_channels(self, team_id: str) -> list[TeamsChannel]:
        """List all channels in a team."""
        data = self._make_request(f"/teams/{team_id}/channels")
        return [
            TeamsChannel(
                id=channel["id"],
                display_name=channel.get("displayName", ""),
                description=channel.get("description"),
            )
            for channel in data.get("value", [])
        ]

    def get_channel_messages(
        self,
        team_id: str,
        channel_id: str,
        limit: int = 50,
    ) -> list[TeamsMessage]:
        """
        Get messages from a Teams channel.

        Args:
            team_id: The team ID
            channel_id: The channel ID
            limit: Maximum number of messages to fetch

        Returns:
            List of TeamsMessage objects
        """
        endpoint = f"/teams/{team_id}/channels/{channel_id}/messages"
        params = {"$top": min(limit, 50)}  # Graph API max is 50 per page

        messages = []
        while len(messages) < limit:
            data = self._make_request(endpoint, params)

            for msg in data.get("value", []):
                if msg.get("messageType") != "message":
                    continue  # Skip system messages

                body = msg.get("body", {})
                content = body.get("content", "")

                # Strip HTML if content type is html
                if body.get("contentType") == "html":
                    import re
                    content = re.sub(r"<[^>]+>", "", content)

                sender_info = msg.get("from", {})
                user_info = sender_info.get("user", {}) if sender_info else {}
                sender = user_info.get("displayName", "Unknown")

                created_str = msg.get("createdDateTime", "")
                try:
                    created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    created_at = datetime.now()

                messages.append(
                    TeamsMessage(
                        id=msg["id"],
                        content=content,
                        sender=sender,
                        created_at=created_at,
                        reply_to_id=msg.get("replyToId"),
                        attachments=msg.get("attachments"),
                    )
                )

            # Check for next page
            next_link = data.get("@odata.nextLink")
            if not next_link or len(messages) >= limit:
                break

            # Parse the next link for continuation
            endpoint = next_link.replace(self.GRAPH_BASE_URL, "")
            params = None

        return messages[:limit]

    def get_chat_messages(self, chat_id: str, limit: int = 50) -> list[TeamsMessage]:
        """
        Get messages from a 1:1 or group chat.

        Args:
            chat_id: The chat ID
            limit: Maximum number of messages to fetch

        Returns:
            List of TeamsMessage objects
        """
        endpoint = f"/chats/{chat_id}/messages"
        params = {"$top": min(limit, 50)}

        messages = []
        data = self._make_request(endpoint, params)

        for msg in data.get("value", []):
            if msg.get("messageType") != "message":
                continue

            body = msg.get("body", {})
            content = body.get("content", "")

            if body.get("contentType") == "html":
                import re
                content = re.sub(r"<[^>]+>", "", content)

            sender_info = msg.get("from", {})
            user_info = sender_info.get("user", {}) if sender_info else {}
            sender = user_info.get("displayName", "Unknown")

            created_str = msg.get("createdDateTime", "")
            try:
                created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                created_at = datetime.now()

            messages.append(
                TeamsMessage(
                    id=msg["id"],
                    content=content,
                    sender=sender,
                    created_at=created_at,
                    reply_to_id=msg.get("replyToId"),
                    attachments=msg.get("attachments"),
                )
            )

        return messages[:limit]

    def _group_messages_by_thread(
        self, messages: list[TeamsMessage]
    ) -> dict[str, list[TeamsMessage]]:
        """Group messages into threads based on reply_to_id."""
        threads: dict[str, list[TeamsMessage]] = {}

        for msg in messages:
            # Use reply_to_id if it's a reply, otherwise use message id as thread root
            thread_id = msg.reply_to_id or msg.id
            if thread_id not in threads:
                threads[thread_id] = []
            threads[thread_id].append(msg)

        # Sort messages within each thread by creation time
        for thread_id in threads:
            threads[thread_id].sort(key=lambda m: m.created_at)

        return threads

    def create_workstream_from_channel(
        self,
        team_id: str,
        channel_id: str,
        channel_name: Optional[str] = None,
        team_name: Optional[str] = None,
        message_limit: int = 50,
    ) -> list[CreateWorkstreamRequest]:
        """
        Create workstream requests from a Teams channel's message threads.

        Args:
            team_id: The team ID
            channel_id: The channel ID
            channel_name: Optional channel name for context
            team_name: Optional team name for context
            message_limit: Maximum messages to fetch

        Returns:
            List of CreateWorkstreamRequest objects, one per thread
        """
        messages = self.get_channel_messages(team_id, channel_id, limit=message_limit)
        threads = self._group_messages_by_thread(messages)

        workstreams = []
        for thread_id, thread_messages in threads.items():
            if not thread_messages:
                continue

            # Use first message as the thread starter
            root_msg = thread_messages[0]

            # Create a summary from the thread
            summary_parts = []
            for msg in thread_messages[:5]:  # First 5 messages for summary
                summary_parts.append(f"[{msg.sender}]: {msg.content[:200]}")

            summary = "\n".join(summary_parts)
            if len(thread_messages) > 5:
                summary += f"\n... and {len(thread_messages) - 5} more messages"

            # Generate a name from the first message
            first_content = root_msg.content[:50]
            if len(root_msg.content) > 50:
                first_content += "..."

            name_parts = []
            if team_name:
                name_parts.append(team_name)
            if channel_name:
                name_parts.append(channel_name)
            name_parts.append(first_content or f"Thread {thread_id[:8]}")
            name = " / ".join(name_parts)

            # Build tags
            tags = ["teams", "chat"]
            if team_name:
                tags.append(f"team:{team_name.lower().replace(' ', '-')}")
            if channel_name:
                tags.append(f"channel:{channel_name.lower().replace(' ', '-')}")

            # Build metadata
            participants = list(set(msg.sender for msg in thread_messages))
            metadata = {
                "source": "teams",
                "teamId": team_id,
                "channelId": channel_id,
                "threadId": thread_id,
                "messageCount": len(thread_messages),
                "participants": participants,
                "firstMessageDate": thread_messages[0].created_at.isoformat(),
                "lastMessageDate": thread_messages[-1].created_at.isoformat(),
            }

            workstreams.append(
                CreateWorkstreamRequest(
                    name=name,
                    summary=summary,
                    tags=tags,
                    metadata=metadata,
                )
            )

        return workstreams

    async def index_channel(
        self,
        team_id: str,
        channel_id: str,
        message_limit: int = 50,
    ) -> list[CreateWorkstreamRequest]:
        """
        Async wrapper for create_workstream_from_channel.

        Fetches team and channel names for better context.
        """
        # Get team and channel info for naming
        team_name = None
        channel_name = None

        try:
            teams = self.list_teams()
            team = next((t for t in teams if t.id == team_id), None)
            if team:
                team_name = team.display_name

            channels = self.list_channels(team_id)
            channel = next((c for c in channels if c.id == channel_id), None)
            if channel:
                channel_name = channel.display_name
        except TeamsIndexerError:
            pass  # Continue without names

        return self.create_workstream_from_channel(
            team_id=team_id,
            channel_id=channel_id,
            channel_name=channel_name,
            team_name=team_name,
            message_limit=message_limit,
        )
