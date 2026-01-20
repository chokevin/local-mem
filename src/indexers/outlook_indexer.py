"""
Outlook Email Indexer - imports emails from Outlook via Microsoft Graph API.

Converts email threads into workstreams with extracted subjects, content, and metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from html import unescape
import re

from ..types import CreateWorkstreamRequest
from .microsoft_auth import MicrosoftGraphAuth


@dataclass
class EmailMessage:
    """Represents an Outlook email message."""

    id: str
    subject: str
    body_preview: str
    body_content: str
    sender: str
    recipients: list[str]
    received_datetime: str
    conversation_id: str
    is_read: bool
    importance: str
    has_attachments: bool
    web_link: Optional[str] = None

    @classmethod
    def from_graph_response(cls, data: dict[str, Any]) -> "EmailMessage":
        """Create EmailMessage from Graph API response."""
        sender_email = ""
        if data.get("sender", {}).get("emailAddress"):
            sender_email = data["sender"]["emailAddress"].get("address", "")

        recipients = []
        for recipient in data.get("toRecipients", []):
            if recipient.get("emailAddress", {}).get("address"):
                recipients.append(recipient["emailAddress"]["address"])

        return cls(
            id=data.get("id", ""),
            subject=data.get("subject", "(No Subject)"),
            body_preview=data.get("bodyPreview", ""),
            body_content=data.get("body", {}).get("content", ""),
            sender=sender_email,
            recipients=recipients,
            received_datetime=data.get("receivedDateTime", ""),
            conversation_id=data.get("conversationId", ""),
            is_read=data.get("isRead", False),
            importance=data.get("importance", "normal"),
            has_attachments=data.get("hasAttachments", False),
            web_link=data.get("webLink"),
        )


@dataclass
class EmailThread:
    """Represents a conversation/thread of emails."""

    conversation_id: str
    subject: str
    messages: list[EmailMessage] = field(default_factory=list)
    participants: set[str] = field(default_factory=set)
    first_received: Optional[str] = None
    last_received: Optional[str] = None

    def add_message(self, message: EmailMessage) -> None:
        """Add a message to the thread."""
        self.messages.append(message)
        self.participants.add(message.sender)
        self.participants.update(message.recipients)

        if self.first_received is None or message.received_datetime < self.first_received:
            self.first_received = message.received_datetime
        if self.last_received is None or message.received_datetime > self.last_received:
            self.last_received = message.received_datetime


class OutlookIndexer:
    """Indexes Outlook emails and converts them to workstreams."""

    # Well-known folder names in Microsoft Graph
    FOLDER_INBOX = "inbox"
    FOLDER_SENT = "sentitems"
    FOLDER_DRAFTS = "drafts"
    FOLDER_DELETED = "deleteditems"
    FOLDER_ARCHIVE = "archive"

    def __init__(self, auth: Optional[MicrosoftGraphAuth] = None):
        """
        Initialize the Outlook indexer.

        Args:
            auth: MicrosoftGraphAuth instance (creates one if not provided)
        """
        self.auth = auth or MicrosoftGraphAuth()

    async def get_mail_folders(self) -> list[dict[str, Any]]:
        """Get list of mail folders."""
        response = await self.auth.graph_request(
            "/me/mailFolders",
            params={"$select": "id,displayName,totalItemCount,unreadItemCount"},
        )
        return response.get("value", [])

    async def get_folder_id(self, folder_name: str) -> Optional[str]:
        """
        Get folder ID by name.

        Args:
            folder_name: Display name or well-known name (inbox, sent, etc.)

        Returns:
            Folder ID or None if not found
        """
        # Well-known folders can be accessed directly
        well_known = {
            "inbox": self.FOLDER_INBOX,
            "sent": self.FOLDER_SENT,
            "sentitems": self.FOLDER_SENT,
            "drafts": self.FOLDER_DRAFTS,
            "deleted": self.FOLDER_DELETED,
            "deleteditems": self.FOLDER_DELETED,
            "archive": self.FOLDER_ARCHIVE,
        }

        normalized = folder_name.lower().replace(" ", "")
        if normalized in well_known:
            return well_known[normalized]

        # Search for folder by display name
        folders = await self.get_mail_folders()
        for folder in folders:
            if folder.get("displayName", "").lower() == folder_name.lower():
                return folder.get("id")

        return None

    async def fetch_emails(
        self,
        folder: str = "inbox",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 100,
        unread_only: bool = False,
    ) -> list[EmailMessage]:
        """
        Fetch emails from a folder.

        Args:
            folder: Folder name or ID (default: inbox)
            start_date: Filter emails received after this date (ISO format)
            end_date: Filter emails received before this date (ISO format)
            max_results: Maximum number of emails to fetch
            unread_only: Only fetch unread emails

        Returns:
            List of EmailMessage objects
        """
        folder_id = await self.get_folder_id(folder) or folder

        # Build query parameters
        params: dict[str, Any] = {
            "$select": "id,subject,bodyPreview,body,sender,toRecipients,receivedDateTime,conversationId,isRead,importance,hasAttachments,webLink",
            "$orderby": "receivedDateTime desc",
            "$top": max_results,
        }

        # Build filter conditions
        filters = []
        if start_date:
            filters.append(f"receivedDateTime ge {start_date}")
        if end_date:
            filters.append(f"receivedDateTime le {end_date}")
        if unread_only:
            filters.append("isRead eq false")

        if filters:
            params["$filter"] = " and ".join(filters)

        endpoint = f"/me/mailFolders/{folder_id}/messages"
        response = await self.auth.graph_request(endpoint, params=params)

        messages = []
        for item in response.get("value", []):
            messages.append(EmailMessage.from_graph_response(item))

        return messages

    def group_into_threads(self, messages: list[EmailMessage]) -> list[EmailThread]:
        """
        Group emails by conversation ID into threads.

        Args:
            messages: List of email messages

        Returns:
            List of EmailThread objects
        """
        threads_map: dict[str, EmailThread] = {}

        for message in messages:
            conv_id = message.conversation_id
            if conv_id not in threads_map:
                threads_map[conv_id] = EmailThread(
                    conversation_id=conv_id,
                    subject=message.subject,
                )
            threads_map[conv_id].add_message(message)

        # Sort threads by last received date
        threads = list(threads_map.values())
        threads.sort(
            key=lambda t: t.last_received or "",
            reverse=True,
        )

        return threads

    def _clean_html(self, html: str) -> str:
        """Strip HTML tags and clean up content."""
        # Remove style and script tags with content
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Decode HTML entities
        text = unescape(text)
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_key_content(self, thread: EmailThread, max_length: int = 500) -> str:
        """Extract key content from thread for summary."""
        # Get the most recent message's body
        if not thread.messages:
            return ""

        # Sort by date descending
        sorted_msgs = sorted(
            thread.messages,
            key=lambda m: m.received_datetime,
            reverse=True,
        )

        # Use body preview if available, otherwise clean the HTML body
        content = sorted_msgs[0].body_preview
        if not content and sorted_msgs[0].body_content:
            content = self._clean_html(sorted_msgs[0].body_content)

        if len(content) > max_length:
            content = content[:max_length] + "..."

        return content

    def thread_to_workstream_request(
        self,
        thread: EmailThread,
        additional_tags: Optional[list[str]] = None,
    ) -> CreateWorkstreamRequest:
        """
        Convert an email thread to a CreateWorkstreamRequest.

        Args:
            thread: EmailThread to convert
            additional_tags: Extra tags to add

        Returns:
            CreateWorkstreamRequest ready for storage
        """
        # Build name from subject
        name = thread.subject or "(No Subject)"
        if name.lower().startswith("re: "):
            name = name[4:]
        if name.lower().startswith("fw: ") or name.lower().startswith("fwd: "):
            name = name[4:]

        # Build summary
        key_content = self._extract_key_content(thread)
        participants_str = ", ".join(sorted(thread.participants)[:5])
        if len(thread.participants) > 5:
            participants_str += f" +{len(thread.participants) - 5} more"

        summary = f"Email thread with {len(thread.messages)} message(s). "
        summary += f"Participants: {participants_str}. "
        if key_content:
            summary += f"\n\nLatest: {key_content}"

        # Build tags
        tags = ["email", "outlook"]
        if thread.messages and thread.messages[0].importance == "high":
            tags.append("high-priority")
        if any(m.has_attachments for m in thread.messages):
            tags.append("has-attachments")
        if additional_tags:
            tags.extend(additional_tags)

        # Build metadata
        metadata = {
            "source": "outlook",
            "conversationId": thread.conversation_id,
            "messageCount": len(thread.messages),
            "participants": list(thread.participants),
            "firstReceived": thread.first_received,
            "lastReceived": thread.last_received,
        }

        # Add web link if available
        if thread.messages and thread.messages[0].web_link:
            metadata["webLink"] = thread.messages[0].web_link

        return CreateWorkstreamRequest(
            name=name,
            summary=summary,
            tags=tags,
            metadata=metadata,
        )

    async def index_emails(
        self,
        folder: str = "inbox",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_results: int = 100,
        unread_only: bool = False,
        additional_tags: Optional[list[str]] = None,
    ) -> list[CreateWorkstreamRequest]:
        """
        Index emails from Outlook and convert to workstream requests.

        Args:
            folder: Folder to index (default: inbox)
            start_date: Filter emails received after this date (ISO format, e.g., '2024-01-01')
            end_date: Filter emails received before this date (ISO format)
            max_results: Maximum number of emails to fetch
            unread_only: Only index unread emails
            additional_tags: Extra tags to add to all workstreams

        Returns:
            List of CreateWorkstreamRequest objects ready for storage
        """
        # Fetch emails
        messages = await self.fetch_emails(
            folder=folder,
            start_date=start_date,
            end_date=end_date,
            max_results=max_results,
            unread_only=unread_only,
        )

        if not messages:
            return []

        # Group into threads
        threads = self.group_into_threads(messages)

        # Convert to workstream requests
        requests = []
        for thread in threads:
            request = self.thread_to_workstream_request(thread, additional_tags)
            requests.append(request)

        return requests

    async def close(self) -> None:
        """Close the indexer and cleanup resources."""
        await self.auth.close()
