"""
Test AES-ECB encryption/decryption on a file

Usage:
    cd /Users/wadahana/workspace/AI/claw/weixin/weixin-clawbot-python
    source /Users/wadahana/workspace/py312/bin/activate
    python tests/test_aes_file.py
"""

import sys
from pathlib import Path

# Add parent directory to path to import app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils import aes_ecb_encrypt, aes_ecb_decrypt


def test_aes_file_encrypt_decrypt():
    """Test AES-ECB encryption and decryption on example.jpg"""

    # 16-byte AES key (128-bit)
    key = b"0123456789abcdef"  # 16 bytes for AES-128

    input_path = Path("examples/example.jpg")
    encrypted_path = Path("examples/encrypted.bin")
    decrypted_path = Path("examples/decrypted.jpg")

    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        print("Creating a dummy test file...")
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_bytes(b"This is a test file for AES encryption/decryption. " * 10)
        print(f"Created dummy file: {input_path}")

    # Read original file
    print(f"Reading: {input_path}")
    original_data = input_path.read_bytes()
    print(f"Original size: {len(original_data)} bytes")

    # Encrypt
    print("\nEncrypting...")
    encrypted_data = aes_ecb_encrypt(original_data, key)
    encrypted_path.write_bytes(encrypted_data)
    print(f"Encrypted size: {len(encrypted_data)} bytes")
    print(f"Saved encrypted to: {encrypted_path}")

    # Decrypt
    print("\nDecrypting...")
    decrypted_data = aes_ecb_decrypt(encrypted_data, key)
    decrypted_path.write_bytes(decrypted_data)
    print(f"Decrypted size: {len(decrypted_data)} bytes")
    print(f"Saved decrypted to: {decrypted_path}")

    # Verify
    print("\nVerifying...")
    if original_data == decrypted_data:
        print("✓ SUCCESS: Original and decrypted data match!")
        print(f"  MD5 match: {hash(original_data) == hash(decrypted_data)}")
    else:
        print("✗ FAILED: Data mismatch!")
        print(f"  Original length: {len(original_data)}")
        print(f"  Decrypted length: {len(decrypted_data)}")
        return False

    # Show file info
    print("\n" + "="*50)
    print("File Info:")
    print(f"  Input:    {input_path} ({input_path.stat().st_size} bytes)")
    print(f"  Encrypted:{encrypted_path} ({encrypted_path.stat().st_size} bytes)")
    print(f"  Decrypted:{decrypted_path} ({decrypted_path.stat().st_size} bytes)")
    print("="*50)

    return True


if __name__ == "__main__":
    success = test_aes_file_encrypt_decrypt()
    sys.exit(0 if success else 1)
