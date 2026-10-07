"""
Email & phone validation / normalisation helpers.
"""
from typing import Optional
import re

try:
    from email_validator import validate_email, EmailNotValidError
except ImportError:
    validate_email = None

try:
    import phonenumbers
    from phonenumbers import NumberParseException, PhoneNumberFormat
except ImportError:
    phonenumbers = None


def is_valid_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    if validate_email:
        try:
            validate_email(email, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False
    # Fallback simple check
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


def normalize_phone(phone: str, default_region: str = "US") -> Optional[str]:
    if not phone or not phonenumbers:
        return phone
    try:
        num = phonenumbers.parse(phone, default_region)
        if phonenumbers.is_valid_number(num):
            return phonenumbers.format_number(num, PhoneNumberFormat.E164)
    except NumberParseException:
        pass
    return phone


def clean_email(email: str) -> Optional[str]:
    if not email:
        return None
    email = email.strip().lower()
    if is_valid_email(email):
        return email
    return None
