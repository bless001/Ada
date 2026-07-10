#!/usr/bin/env python3
from pathlib import Path
import secrets
import re

root = Path(__file__).resolve().parents[1]
env_example = root / ".env.example"
env_file = root / ".env"

if env_file.exists():
    text = env_file.read_text(encoding="utf-8")
else:
    text = env_example.read_text(encoding="utf-8")

def set_var(text: str, key: str, value: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
    line = f"{key}={value}"
    if pattern.search(text):
        return pattern.sub(line, text)
    return text.rstrip() + "\n" + line + "\n"

def needs_replace(value: str) -> bool:
    v = value.strip()
    return (
        not v
        or "change_me" in v
        or "GENERATE" in v
        or "please_run" in v
        or len(v) < 64
    )

def get_var(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""

secret_key = get_var(text, "OPENPROJECT_SECRET_KEY_BASE")
if needs_replace(secret_key):
    text = set_var(text, "OPENPROJECT_SECRET_KEY_BASE", secrets.token_hex(64))

pg_password = get_var(text, "POSTGRES_PASSWORD")
if "change_me" in pg_password or not pg_password:
    text = set_var(text, "POSTGRES_PASSWORD", secrets.token_urlsafe(32))

neo4j_password = get_var(text, "NEO4J_PASSWORD")
if "change_me" in neo4j_password or not neo4j_password:
    text = set_var(text, "NEO4J_PASSWORD", secrets.token_urlsafe(32))

webhook_secret = get_var(text, "WEBHOOK_SIGNATURE_SECRET")
if "change_me" in webhook_secret or not webhook_secret:
    text = set_var(text, "WEBHOOK_SIGNATURE_SECRET", secrets.token_hex(32))

env_file.write_text(text, encoding="utf-8")
print(f"Generated/updated {env_file}")
print("OPENPROJECT_SECRET_KEY_BASE is now a valid generated secret.")
