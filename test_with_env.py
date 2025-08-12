#!/usr/bin/env python3
"""
Test script for pyclient using .env configuration
Tests JWT authentication, file upload, download, and direct upload functionality
"""

import os
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# Add the pyclient directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from __init__ import decode2binary, get_jwt_token, upload_binary, upload_file, upload_file_direct


def load_env_config():
    """Load configuration from .env file"""
    # Try to load .env from current directory first, then parent
    local_env = Path(__file__).parent / '.env'
    parent_env = Path(__file__).parent.parent / '.env'

    if local_env.exists():
        load_dotenv(local_env)
        print(f"Using local .env: {local_env}")
    else:
        load_dotenv(parent_env)
        print(f"Using parent .env: {parent_env}")

    # Try pyclient-specific env vars first, then fall back to KOEKOE vars
    config = {
        'email': os.getenv('PYTSFILER_EMAIL') or os.getenv('KOEKOE_EMAIL', 'owner'),
        'password': os.getenv('PYTSFILER_PASSWORD') or os.getenv('KOEKOE_PASSWORD', 'StrongPassword123'),
        'base_url': os.getenv('PYTSFILER_BASE_URL') or os.getenv('KOEKOE_BASE_URL', 'https://localhost:3000'),
    }

    print(f"Loaded config: {config['email']} @ {config['base_url']}")
    return config

def create_test_file():
    """Create a temporary test file with unique content"""
    import random
    import time
    # Create unique content with timestamp and random data
    timestamp = str(time.time()).encode()
    random_data = str(random.randint(100000, 999999)).encode()
    test_data = b"Hello, this is a test file for pyclient!\n"
    test_data += b"Timestamp: " + timestamp + b"\n"
    test_data += b"Random: " + random_data + b"\n"
    test_data += b"Testing upload and download functionality.\n" + b"x" * 1000

    temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.txt')
    temp_file.write(test_data)
    temp_file.close()
    return temp_file.name, test_data

def test_jwt_authentication(config):
    """Test JWT token authentication"""
    print("\n=== Testing JWT Authentication ===")
    try:
        token = get_jwt_token(config['email'], config['password'], config['base_url'])
        print(f"✓ JWT token obtained: {token[:50]}...")
        return token
    except Exception as e:
        print(f"✗ JWT authentication failed: {e}")
        return None

def test_file_upload(token, config):
    """Test file upload with JWT token"""
    print("\n=== Testing File Upload ===")
    try:
        # Create test file
        test_file_path, original_data = create_test_file()
        print(f"Created test file: {test_file_path} ({len(original_data)} bytes)")

        # Upload file with timestamp and random suffix to avoid conflicts
        import random
        import time
        unique_filename = f"test_upload_{int(time.time())}_{random.randint(1000,9999)}.txt"
        result = upload_file(test_file_path, unique_filename, token, config['base_url'])
        print(f"✓ Upload successful: File ID {result['fileId']}")
        print(f"  Uploaded size: {result['uploadedSize']} bytes")

        # Clean up
        os.unlink(test_file_path)

        return result['fileId'], original_data
    except FileExistsError:
        print("✗ File already exists on server - this is expected behavior")
        return None, None
    except Exception as e:
        print(f"✗ File upload failed: {e}")
        import traceback
        traceback.print_exc()
        return None, None

def test_file_download(file_id, original_data, token, config):
    """Test file download and verification"""
    print("\n=== Testing File Download ===")
    try:
        # Download file
        downloaded_data = decode2binary(str(file_id), token, config['base_url'])
        print(f"✓ Download successful: {len(downloaded_data)} bytes")

        # Verify data integrity
        if downloaded_data == original_data:
            print("✓ Data integrity verified - upload and download match!")
            return True
        else:
            print(f"✗ Data integrity failed - sizes: original={len(original_data)}, downloaded={len(downloaded_data)}")
            return False
    except Exception as e:
        print(f"✗ File download failed: {e}")
        return False

def test_binary_upload(token, config):
    """Test binary upload directly from memory"""
    print("\n=== Testing Binary Upload ===")
    try:
        # Create test data with unique content
        import random
        import time
        test_data = b"Binary upload test data: "
        test_data += f"Time: {time.time()} Random: {random.randint(100000, 999999)}".encode()
        test_data += b" " + b"z" * 500

        # Upload binary data with unique filename
        import time
        unique_filename = f"binary_test_{int(time.time())}.bin"
        result = upload_binary(test_data, unique_filename, token, config['base_url'])
        print(f"✓ Binary upload successful: File ID {result['fileId']}")

        return result['fileId'], test_data
    except Exception as e:
        print(f"✗ Binary upload failed: {e}")
        return None, None

def test_direct_upload(config):
    """Test direct upload functionality (if token available)"""
    print("\n=== Testing Direct Upload ===")

    # For demo purposes, we'll skip direct upload since we need a valid upload token
    # In a real test, you would have an upload token from your server
    print("⚠ Direct upload test skipped - requires valid upload token")
    print("  To test direct upload, set UPLOAD_TOKEN environment variable")

    upload_token = os.getenv('PYTSFILER_UPLOAD_TOKEN') or os.getenv('UPLOAD_TOKEN')
    if not upload_token:
        return False

    try:
        # Create test file for direct upload
        test_file_path, test_data = create_test_file()

        # Test direct upload
        result = upload_file_direct(test_file_path, upload_token, config['base_url'])
        print(f"✓ Direct upload successful: File ID {result['fileId']}")

        # Clean up
        os.unlink(test_file_path)
        return True
    except Exception as e:
        print(f"✗ Direct upload failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🧪 Starting pyclient tests with .env configuration")

    # Load configuration
    try:
        config = load_env_config()
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        return

    # Test results tracking
    results = {}

    # Test 1: JWT Authentication
    token = test_jwt_authentication(config)
    results['auth'] = token is not None

    if not token:
        print("\n❌ Cannot continue without authentication token")
        return

    # Test 2: File Upload
    file_id, original_data = test_file_upload(token, config)
    results['upload'] = file_id is not None

    # Test 3: File Download (only if upload succeeded)
    if file_id and original_data:
        results['download'] = test_file_download(file_id, original_data, token, config)
    else:
        results['download'] = False

    # Test 4: Binary Upload
    binary_file_id, binary_data = test_binary_upload(token, config)
    results['binary_upload'] = binary_file_id is not None

    # Test 5: Direct Upload
    results['direct_upload'] = test_direct_upload(config)

    # Summary
    print("\n" + "="*50)
    print("📊 TEST SUMMARY")
    print("="*50)

    passed = sum(results.values())
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✓ PASS" if passed_test else "✗ FAIL"
        print(f"{test_name.upper():20} {status}")

    print(f"\nOverall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed - check output above")

if __name__ == "__main__":
    main()
