from devops_ci.redaction import Redactor


def test_redacts_common_credentials_and_known_secrets():
    text = """token=ghp_abcdefghijklmnopqrstuvwxyz123456
aws=AKIAABCDEFGHIJKLMNOP
DATABASE_URL=postgres://admin:super-secret@db.internal:5432/app
Authorization: Bearer very-secret-token
custom=organization-secret"""

    result = Redactor(["organization-secret"]).redact(text)

    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in result.text
    assert "AKIAABCDEFGHIJKLMNOP" not in result.text
    assert "super-secret" not in result.text
    assert "very-secret-token" not in result.text
    assert "organization-secret" not in result.text
    assert result.count >= 5


def test_redacts_private_key_blocks():
    text = "-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
    result = Redactor().redact(text)
    assert result.text == "[REDACTED_PRIVATE_KEY]"
