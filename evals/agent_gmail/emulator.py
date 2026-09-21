"""Owned Emulate process and independent Gmail state inspection."""
from __future__ import annotations

import base64
import json
import selectors
import subprocess
import tempfile
import time
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

import httpx

from .types import Mail

from .mailbox import USER, TOKEN, DATE


def decode_message(message: dict) -> dict:
    """Decode API raw MIME independently from the write adapter."""
    raw = message.get("raw", "")
    mime = BytesParser(policy=policy.default).parsebytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    body = mime.get_body(preferencelist=("plain", "html")) if mime.is_multipart() else mime
    return {
        "id": message["id"], "thread": message.get("threadId"),
        "labels": message.get("labelIds", []),
        "to": str(mime.get("To", "")), "sender": str(mime.get("From", "")),
        "cc": str(mime.get("Cc", "")), "bcc": str(mime.get("Bcc", "")),
        "subject": str(mime.get("Subject", "")),
        "body": body.get_content().rstrip("\r\n") if body else "",
        "message_id": str(mime.get("Message-ID", "")),
    }


def seed_raw(mail: Mail) -> str:
    message = EmailMessage()
    for key, value in {"From": mail.sender, "To": mail.to, "Subject": mail.subject,
                       "Date": DATE, "Message-ID": f"<{mail.id}@example.com>"}.items():
        message[key] = value
    message.set_content(mail.body)
    return base64.urlsafe_b64encode(message.as_bytes(policy=policy.SMTP)).decode()


class Emulator:
    def __init__(self, mail: tuple[Mail, ...] = ()):
        self.mail = mail
        self.process = None
        self.client = None
        self.directory = None

    def __enter__(self):
        self.directory = tempfile.TemporaryDirectory(prefix="gmail-emulate-")
        root = Path(self.directory.name)
        seed = {
            "tokens": {TOKEN: {"login": USER}},
            "google": {"users": [{"email": USER, "name": "Eval Owner"}], "messages": [
                {"id": m.id, "user_email": USER, "from": m.sender, "to": m.to,
                 "subject": m.subject, "body_text": m.body, "thread_id": m.thread or m.id,
                 "date": DATE, "internal_date": "1789473600000", "raw": seed_raw(m),
                 "label_ids": ["DRAFT"] if m.draft else ["INBOX"]}
                for m in self.mail
            ]},
        }
        (root / "seed.json").write_text(json.dumps(seed))
        launcher = Path(__file__).parent / "emulate" / "service.mjs"
        self.stderr = (root / "stderr.log").open("w+")
        try:
            self.process = subprocess.Popen(
                ["node", str(launcher), str(root / "seed.json")],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr, text=True,
            )
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                if not selector.select(20):
                    raise RuntimeError("Emulate did not become ready in 20 seconds")
                line = self.process.stdout.readline()
            if not line:
                self.stderr.seek(0)
                raise RuntimeError("Emulate startup failed: " + self.stderr.read())
            ready = json.loads(line)
            if not ready.get("ready"):
                raise RuntimeError(f"Unexpected Emulate startup: {ready}")
            self.url = ready["url"]
            if not self.url.startswith("http://127.0.0.1:"):
                raise RuntimeError("Emulate must expose a loopback URL")
            self.client = httpx.Client(base_url=self.url + "/gmail/v1/users/me/", headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10, trust_env=False)
            # Emulate prints its URL just before the socket becomes accept-ready.
            deadline = time.monotonic() + 10
            while True:
                try:
                    self.snapshot()
                    break
                except httpx.ConnectError:
                    if self.process.poll() is not None or time.monotonic() >= deadline:
                        self.stderr.flush()
                        self.stderr.seek(0)
                        raise RuntimeError("Emulate readiness failed: " + self.stderr.read())
                    time.sleep(0.05)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def request(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json() if response.content else {}

    def pages(self, path: str, key: str, **params):
        items = []
        while True:
            page = self.request("GET", path, params=params)
            items.extend(page.get(key, []))
            if not page.get("nextPageToken"):
                return items
            params["pageToken"] = page["nextPageToken"]

    def snapshot(self) -> dict:
        messages = [decode_message(self.request("GET", "messages/" + m["id"], params={"format": "raw"}))
                    for m in self.pages("messages", "messages", includeSpamTrash="true")]
        drafts = self.pages("drafts", "drafts")
        draft_ids = {d["message"]["id"]: d["id"] for d in drafts}
        for m in messages:
            if m["id"] in draft_ids:
                m["draft_id"] = draft_ids[m["id"]]
        return {"messages": messages}

    def __exit__(self, *_):
        if self.client:
            self.client.close()
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
        if getattr(self, "stderr", None):
            self.stderr.close()
        if self.directory:
            self.directory.cleanup()
