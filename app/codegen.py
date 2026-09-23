import secrets
import string

_ALPHABET = string.ascii_letters + string.digits


def generate_candidate_code(length: int) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
