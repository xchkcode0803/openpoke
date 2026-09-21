"""Mechanical Composio action translation. No agent decisions or repairs."""
from __future__ import annotations

import base64
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from .mailbox import DATE, USER
from .types import Fault


class UnsupportedOperation(RuntimeError):
    pass


def mime_message(
    arguments: dict,
    *,
    subject: str | None = None,
    body: str | None = None,
    reply_id: str | None = None,
) -> str:
    if arguments.get("attachment"):
        raise UnsupportedOperation("Composio-uploaded attachments are not emulated")
    message = EmailMessage()
    message["From"] = USER
    recipients = [arguments["recipient_email"], *arguments.get("extra_recipients", [])]
    message["To"] = ", ".join(recipients)
    message["Subject"] = arguments.get("subject", "") if subject is None else subject
    message["Date"] = DATE
    for name in ("cc", "bcc"):
        if arguments.get(name):
            message[name.title()] = ", ".join(arguments[name])
    if reply_id:
        message["In-Reply-To"] = reply_id
        message["References"] = reply_id
    message.set_content(
        arguments.get("body", "") if body is None else body,
        subtype="html" if arguments.get("is_html") else "plain",
    )
    return base64.urlsafe_b64encode(message.as_bytes(policy=policy.SMTP)).decode()


class GmailAdapter:
    def __init__(self, emulator, faults: tuple[Fault, ...] = (), emit=None):
        self.emulator = emulator
        self.faults = [[f, f.count] for f in faults]
        self.emit = emit or (lambda *args, **kwargs: None)
        self.unsupported = []

    def request(self, method, path, **kwargs):
        try:
            result = self.emulator.request(method, path, **kwargs)
            self.emit("http", method=method, path=path, request=kwargs, response=result)
            return result
        except Exception as exc:
            self.emit("http", method=method, path=path, request=kwargs, error=str(exc))
            raise

    def __call__(self, action, user_id, arguments=None):
        args = arguments or {}
        before = self.emulator.snapshot()
        try:
            for fault in self.faults:
                spec, remaining = fault
                if (
                    remaining
                    and action == spec.action
                    and (not spec.recipient or args.get("recipient_email") == spec.recipient)
                ):
                    fault[1] -= 1
                    self.emit("injected_fault", action=action, arguments=args)
                    raise RuntimeError("Gmail API temporarily unavailable (HTTP 503)")
            data = self.execute(action, args)
            result = {"successful": True, "data": data}
            self.emit(
                "gmail_action",
                action=action,
                arguments=args,
                result=result,
                before=before,
                after=self.emulator.snapshot(),
            )
            return result
        except Exception as exc:
            if isinstance(exc, UnsupportedOperation):
                self.unsupported.append(str(exc))
            self.emit(
                "gmail_action",
                action=action,
                arguments=args,
                error=str(exc),
                before=before,
                after=self.emulator.snapshot(),
            )
            raise

    def execute(self, action, args):
        if args.get("attachment"):
            raise UnsupportedOperation("Composio-uploaded attachments are not emulated")
        if action == "GMAIL_CREATE_EMAIL_DRAFT":
            message = {"raw": mime_message(args)}
            if args.get("thread_id"):
                message["threadId"] = args["thread_id"]
            return self.request("POST", "drafts", json={"message": message})
        if action == "GMAIL_SEND_DRAFT":
            return self.request("POST", "drafts/send", json={"id": args["draft_id"]})
        if action == "GMAIL_DELETE_DRAFT":
            return self.request("DELETE", "drafts/" + quote(args["draft_id"], safe=""))
        if action == "GMAIL_LIST_DRAFTS":
            params = {"maxResults": args.get("max_results", 100)}
            if args.get("page_token"):
                params["pageToken"] = args["page_token"]
            result = self.request("GET", "drafts", params=params)
            if args.get("verbose"):
                result["drafts"] = [
                    self.request(
                        "GET", "drafts/" + draft["id"], params={"format": "full"}
                    )
                    for draft in result.get("drafts", [])
                ]
            return result
        if action == "GMAIL_FETCH_EMAILS":
            params = {"q": args.get("query", ""), "maxResults": args.get("max_results", 10),
                      "includeSpamTrash": str(args.get("include_spam_trash", False)).lower()}
            if args.get("page_token"):
                params["pageToken"] = args["page_token"]
            result = self.request("GET", "messages", params=params)
            result["messages"] = [self.fetch_message(m["id"]) for m in result.get("messages", [])]
            return result
        if action == "GMAIL_REPLY_TO_THREAD":
            thread = self.request(
                "GET",
                "threads/" + quote(args["thread_id"], safe=""),
                params={"format": "full"},
            )
            messages = thread.get("messages", [])
            if not messages:
                raise ValueError("Thread contains no messages")
            source = self.fetch_message(messages[-1]["id"])
            subject = source["subject"]
            if not subject.lower().startswith("re:"):
                subject = "Re: " + subject
            headers = {h["name"].lower(): h["value"] for h in source["payload"].get("headers", [])}
            raw = mime_message(
                args,
                subject=subject,
                body=args["message_body"],
                reply_id=headers.get("message-id"),
            )
            return self.request(
                "POST", "messages/send", json={"raw": raw, "threadId": args["thread_id"]}
            )
        if action == "GMAIL_FORWARD_MESSAGE":
            source = self.fetch_message(args["message_id"])
            from server.services.gmail.processing import EmailTextCleaner
            original = EmailTextCleaner().clean_email_content(source)
            body = (
                args.get("additional_text", "")
                + "\n\n---------- Forwarded message ----------\n"
                + f"From: {source['sender']}\nSubject: {source['subject']}\n"
                + f"To: {source['to']}\n\n{original}"
            )
            raw = mime_message(args, subject="Fwd: " + source["subject"], body=body)
            return self.request("POST", "messages/send", json={"raw": raw})
        raise UnsupportedOperation(f"Unsupported Emulate action: {action}")

    def fetch_message(self, message_id):
        message = self.request(
            "GET", "messages/" + quote(message_id, safe=""), params={"format": "full"}
        )
        headers = {
            header["name"].lower(): header["value"]
            for header in message.get("payload", {}).get("headers", [])
        }
        def pad_payload(part):
            body = part.get("body", {})
            if isinstance(body.get("data"), str):
                body["data"] += "=" * (-len(body["data"]) % 4)
            for child in part.get("parts", []):
                pad_payload(child)
        payload = message.get("payload", {})
        pad_payload(payload)
        if payload.get("mimeType") == "text/html":
            message["htmlBody"] = base64.urlsafe_b64decode(
                payload.get("body", {}).get("data", "")
            ).decode("utf-8", errors="replace")
        return {
            **message,
            "subject": headers.get("subject", ""),
            "sender": headers.get("from", ""),
            "to": headers.get("to", ""),
            "messageTimestamp": parsedate_to_datetime(
                headers.get("date", DATE)
            ).isoformat(),
        }
