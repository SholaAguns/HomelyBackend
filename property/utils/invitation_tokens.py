import hashlib
from django.core import signing

INVITE_SALT = 'project-invite-salt'
INVITE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days in seconds


def generate_invite_token(invitation_uuid: str) -> str:
    signer = signing.TimestampSigner(salt=INVITE_SALT)
    return signer.sign(str(invitation_uuid))


def verify_invite_token(token: str) -> str:
    """Returns invitation UUID string. Raises signing.BadSignature or signing.SignatureExpired."""
    signer = signing.TimestampSigner(salt=INVITE_SALT)
    return signer.unsign(token, max_age=INVITE_MAX_AGE)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
