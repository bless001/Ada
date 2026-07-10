import hashlib
import hmac


def verify_hmac_sha256(*, raw_body: bytes, secret: str, received_signature: str | None) -> bool:
    if not secret:
        return True

    if not received_signature:
        return False

    expected = hmac.new(
        key=secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    actual = received_signature.strip().lower()
    allowed_formats = {
        expected,
        f"sha256={expected}",
        f"hmac-sha256={expected}",
    }

    return any(hmac.compare_digest(actual, candidate) for candidate in allowed_formats)
