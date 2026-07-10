#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from pathlib import Path

path = Path("openproject/provision/ensure_agent_bot_token_webhook.rb")
text = path.read_text(encoding="utf-8")

helper = '''
def generate_policy_compliant_password(length = 48)
  lowercase = ("a".."z").to_a
  uppercase = ("A".."Z").to_a
  numbers = ("0".."9").to_a
  special = %w[! @ # $ % ^ & * - _ + = ?]
  all = lowercase + uppercase + numbers + special

  password_chars = [
    lowercase.sample,
    uppercase.sample,
    numbers.sample,
    special.sample
  ]

  (length - password_chars.length).times do
    password_chars << all.sample
  end

  password_chars.shuffle.join
end

'''

if "def generate_policy_compliant_password" not in text:
    text = text.replace(
        "def set_if_possible(record, attr, value)\n",
        helper + "def set_if_possible(record, attr, value)\n",
    )

text = text.replace(
    "password = SecureRandom.hex(48)",
    "password = generate_policy_compliant_password(64)",
)

path.write_text(text, encoding="utf-8")
print("Patched bot password generator.")
PY
