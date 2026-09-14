from monitoring_api.security import hash_password, verify_password, new_token, token_hash


def test_argon2id_and_invalid_password():
    hashed = hash_password("long test password")
    assert hashed.startswith("$argon2id$")
    assert verify_password(hashed, "long test password")
    assert not verify_password(hashed, "wrong")
    assert not verify_password("broken", "anything")


def test_tokens_are_unique_and_hashes_are_binary_sha256():
    first, second = new_token(), new_token()
    assert first != second and len(first) >= 43
    assert len(token_hash(first)) == 32
    assert token_hash(first) != token_hash(second)
