#!/usr/bin/env python3
"""
QQ 邮箱智能助手（IMAP 轮询版）

功能：
1) 自动读取新邮件主题 + 正文摘要
2) 通过桌面通知提醒（可选）
3) 自动过滤低价值邮件（支持规则 + 简单关键词打分）

使用前请先：
- 在 QQ 邮箱开启 IMAP 服务
- 生成授权码（不是登录密码）
- 将配置写入 config.json（可从 config.example.json 复制）
"""

from __future__ import annotations

import email
import email.utils
import imaplib
import json
import re
import time
from dataclasses import dataclass
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Iterable


CONFIG_PATH = Path("config.json")
SEEN_DB_PATH = Path(".seen_uids.json")
IMAP_HOST = "imap.qq.com"
IMAP_PORT = 993


@dataclass
class Config:
    email_address: str
    auth_code: str
    check_interval_seconds: int
    folder: str
    max_body_chars: int
    notify: bool
    notify_command: str | None
    ignore_senders: set[str]
    ignore_subject_keywords: set[str]
    high_value_keywords: set[str]


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        raise FileNotFoundError(
            f"未找到配置文件: {path}. 请先复制 config.example.json 为 config.json 并填写账号信息。"
        )

    data = json.loads(path.read_text(encoding="utf-8"))

    return Config(
        email_address=data["email_address"],
        auth_code=data["auth_code"],
        check_interval_seconds=int(data.get("check_interval_seconds", 60)),
        folder=data.get("folder", "INBOX"),
        max_body_chars=int(data.get("max_body_chars", 240)),
        notify=bool(data.get("notify", True)),
        notify_command=data.get("notify_command"),
        ignore_senders={s.lower() for s in data.get("ignore_senders", [])},
        ignore_subject_keywords={k.lower() for k in data.get("ignore_subject_keywords", [])},
        high_value_keywords={k.lower() for k in data.get("high_value_keywords", [])},
    )


def decode_mime_words(text: str | None) -> str:
    if not text:
        return ""
    chunks = decode_header(text)
    out = []
    for raw, enc in chunks:
        if isinstance(raw, bytes):
            out.append(raw.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(raw)
    return "".join(out)


def extract_plain_text(msg: Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            dispo = (part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in dispo:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def compact_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s


def load_seen_uids(path: Path = SEEN_DB_PATH) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seen_uids(uids: Iterable[str], path: Path = SEEN_DB_PATH) -> None:
    path.write_text(json.dumps(sorted(set(uids)), ensure_ascii=False, indent=2), encoding="utf-8")


def is_low_value(sender: str, subject: str, body: str, cfg: Config) -> bool:
    sender_l = sender.lower()
    subject_l = subject.lower()
    body_l = body.lower()

    if any(s in sender_l for s in cfg.ignore_senders):
        return True

    if any(k in subject_l for k in cfg.ignore_subject_keywords):
        return True

    if cfg.high_value_keywords:
        hit = any(k in subject_l or k in body_l for k in cfg.high_value_keywords)
        if not hit:
            return True

    noise_patterns = [
        r"退订",
        r"unsubscribe",
        r"广告",
        r"促销",
        r"限时优惠",
    ]
    noise_score = sum(bool(re.search(p, subject_l + " " + body_l)) for p in noise_patterns)
    return noise_score >= 2


def send_notification(title: str, message: str, cfg: Config) -> None:
    if not cfg.notify:
        return
    if cfg.notify_command:
        import subprocess

        cmd = cfg.notify_command.format(title=title, message=message)
        subprocess.run(cmd, shell=True, check=False)
    else:
        print(f"[通知] {title}\n{message}\n")


def summarize_mail(subject: str, body: str, max_chars: int) -> str:
    body = compact_text(body)
    if not body:
        return f"主题：{subject}（正文为空或仅HTML）"
    short = body[:max_chars] + ("..." if len(body) > max_chars else "")
    return f"主题：{subject}\n摘要：{short}"


def fetch_unseen_messages(conn: imaplib.IMAP4_SSL) -> list[tuple[str, Message]]:
    typ, data = conn.search(None, "UNSEEN")
    if typ != "OK":
        return []

    results: list[tuple[str, Message]] = []
    for uid_b in data[0].split():
        uid = uid_b.decode("utf-8", errors="ignore")
        typ, msg_data = conn.fetch(uid_b, "(RFC822)")
        if typ != "OK" or not msg_data or msg_data[0] is None:
            continue
        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)
        results.append((uid, msg))
    return results


def run() -> None:
    cfg = load_config()
    seen = load_seen_uids()

    print(f"QQ 邮箱助手启动，轮询间隔 {cfg.check_interval_seconds}s，文件夹 {cfg.folder}")

    while True:
        try:
            with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as conn:
                conn.login(cfg.email_address, cfg.auth_code)
                conn.select(cfg.folder)

                for uid, msg in fetch_unseen_messages(conn):
                    if uid in seen:
                        continue

                    subject = decode_mime_words(msg.get("Subject"))
                    sender_name, sender_addr = email.utils.parseaddr(msg.get("From", ""))
                    sender = f"{decode_mime_words(sender_name)} <{sender_addr}>".strip()
                    body = extract_plain_text(msg)

                    if is_low_value(sender, subject, body, cfg):
                        print(f"[过滤] {subject} / {sender}")
                        seen.add(uid)
                        continue

                    summary = summarize_mail(subject, body, cfg.max_body_chars)
                    notify_text = f"来自：{sender}\n{summary}"
                    send_notification("QQ 邮箱新邮件", notify_text, cfg)
                    print(f"[新邮件] {notify_text}\n")

                    seen.add(uid)

            save_seen_uids(seen)
        except KeyboardInterrupt:
            print("\n已停止。")
            save_seen_uids(seen)
            break
        except Exception as exc:
            print(f"[错误] {exc}")

        time.sleep(cfg.check_interval_seconds)


if __name__ == "__main__":
    run()
