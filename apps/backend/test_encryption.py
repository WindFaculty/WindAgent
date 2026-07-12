import os
import sys
sys.path.insert(0, '.')

from utils.encryption import encrypt, decrypt, is_encrypted, mask_api_key

# Generate a valid Fernet key and set it as environment variable
from cryptography.fernet import Fernet
key = Fernet.generate_key()
os.environ['WINDAGENT_SECRET_ENCRYPTION_KEY'] = key.decode()  # This is a base64 string

def test_encryption():
    plaintext = "sk-1234567890abcdef"
    encrypted = encrypt(plaintext)
    assert encrypted.startswith('enc:v1:'), f"Expected encrypted to start with 'enc:v1:', got {encrypted}"
    decrypted = decrypt(encrypted)
    assert decrypted == plaintext, f"Decrypted '{decrypted}' does not match plaintext '{plaintext}'"
    print("Encryption/decryption test passed")

def test_is_encrypted():
    assert is_encrypted('enc:v1:somedata') == True
    assert is_encrypted('plaintext') == False
    assert is_encrypted('') == False
    print("is_encrypted test passed")

def test_mask_api_key():
    # Test plaintext
    assert mask_api_key('sk-1234567890') == '********7890'
    # Test empty string
    assert mask_api_key('') == ''
    # Test short string
    assert mask_api_key('abc') == '***'
    # Test exactly 4 chars
    assert mask_api_key('abcd') == 'abcd'
    # Test encrypted (should mask the encrypted string)
    encrypted = encrypt('sk-1234567890')
    masked = mask_api_key(encrypted)
    # The masked string should have the same length as encrypted, but with * except last 4
    assert len(masked) == len(encrypted)
    assert masked.endswith(encrypted[-4:])
    assert masked[:-4] == '*' * (len(encrypted) - 4)
    print("mask_api_key test passed")

def test_missing_key():
    # Remove the environment variable
    if 'WINDAGENT_SECRET_ENCRYPTION_KEY' in os.environ:
        del os.environ['WINDAGENT_SECRET_ENCRYPTION_KEY']
    try:
        encrypt('test')
        assert False, "Expected ValueError for missing key"
    except ValueError as e:
        assert "Encryption key not set" in str(e)
    print("Missing key test passed")

if __name__ == '__main__':
    test_encryption()
    test_is_encrypted()
    test_mask_api_key()
    test_missing_key()
    print("All tests passed!")