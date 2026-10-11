import base64

import pytest

from services import password_service
from services.password_service import (
    hash_password,
    validate_password,
    verify_password,
)


PASSWORD = "a sufficiently long password"


@pytest.fixture(scope="module")
def encoded_password():
    return hash_password(PASSWORD)


@pytest.mark.parametrize("password", ["a" * 15, "a" * 128, " " * 15, "密" * 15])
def test_policy_accepts_boundaries_unicode_and_spaces(password):
    assert validate_password(password) is None


@pytest.mark.parametrize("password", ["", "a" * 14, "a" * 129, None, b"a" * 15])
def test_policy_rejects_out_of_bounds_or_non_text_passwords(password):
    with pytest.raises(ValueError):
        validate_password(password)
    with pytest.raises(ValueError):
        hash_password(password)


def test_policy_rejects_invalid_unicode():
    with pytest.raises(ValueError, match="valid Unicode"):
        validate_password("a" * 15 + "\ud800")


def test_password_hash_uses_documented_cost_and_random_salt(encoded_password):
    second_hash = hash_password(PASSWORD)

    algorithm, version, parameters, salt, key = encoded_password.split("$")
    assert (algorithm, version, parameters) == ("scrypt", "v1", "n=131072,r=8,p=1")
    assert len(base64.urlsafe_b64decode(salt + "==")) == 16
    assert len(base64.urlsafe_b64decode(key + "=")) == 32
    assert encoded_password != second_hash
    assert PASSWORD not in encoded_password
    assert verify_password(PASSWORD, encoded_password)
    assert verify_password(PASSWORD, second_hash)
    assert not verify_password("an incorrect long password", encoded_password)


def test_unicode_and_leading_trailing_whitespace_are_not_normalized():
    password = "  中文密码🌱 with space  "
    encoded = hash_password(password)

    assert verify_password(password, encoded)
    assert not verify_password(password.strip(), encoded)
    assert not verify_password(password.replace("🌱", "🌿"), encoded)


def test_long_multibyte_password_uses_character_length():
    password = "🌱" * 128

    assert verify_password(password, hash_password(password))


@pytest.mark.parametrize(
    "alteration",
    [
        lambda value: "",
        lambda value: None,
        lambda value: value.encode("ascii"),
        lambda value: value + "$extra",
        lambda value: value.replace("scrypt", "argon2"),
        lambda value: value.replace("v1", "v2"),
        lambda value: value.replace("n=131072", "n=999999999999999999999999999"),
        lambda value: value.replace("n=131072", "n=2"),
        lambda value: value.replace("r=8", "r=0"),
        lambda value: value.replace("p=1", "p=99999999"),
        lambda value: value.replace("n=131072,r=8,p=1", "r=8,n=131072,p=1"),
        lambda value: "$".join(value.split("$")[:-1]),
        lambda value: "$".join(value.split("$")[:-2] + ["!invalid", "!invalid"]),
        lambda value: "$".join(value.split("$")[:-2] + ["AA", "AA"]),
        lambda value: "$".join(value.split("$")[:-2] + ["密" * 22, "密" * 43]),
        lambda value: value + "=",
        lambda value: value + "\n",
        lambda value: "scrypt$v1$n=131072,r=8,p=1$" + "A" * 1000 + "$" + "A" * 43,
    ],
)
def test_malformed_hashes_are_rejected_before_running_scrypt(
    alteration, encoded_password, monkeypatch
):
    def unexpected_scrypt(*args, **kwargs):
        pytest.fail("Malformed password hashes must not invoke scrypt")

    monkeypatch.setattr(password_service.hashlib, "scrypt", unexpected_scrypt)

    assert not verify_password(PASSWORD, alteration(encoded_password))


@pytest.mark.parametrize("password", [None, b"a" * 15, "short", "a" * 129])
def test_invalid_login_passwords_fail_closed(password, encoded_password):
    assert not verify_password(password, encoded_password)


def test_tampered_key_fails_verification(encoded_password):
    fields = encoded_password.split("$")
    key = base64.urlsafe_b64decode(fields[-1] + "=")
    tampered = bytes([key[0] ^ 1]) + key[1:]
    fields[-1] = base64.urlsafe_b64encode(tampered).rstrip(b"=").decode("ascii")

    assert not verify_password(PASSWORD, "$".join(fields))
