import requests
import base64
import hashlib
import os
import pathlib
import logging
from typing import Optional, Dict, Any, List
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# Import enhanced client classes
try:
    from .client import (
        TSFClient, TSFConfig, UploadResult, FileInfo,
        TSFError, AuthenticationError, UploadError, DownloadError,
        create_client, progress_printer
    )
except ImportError:
    # Fallback for when aiohttp is not available
    TSFClient = None
    TSFConfig = None
    UploadResult = None
    FileInfo = None
    TSFError = Exception
    AuthenticationError = Exception
    UploadError = Exception  
    DownloadError = Exception
    create_client = None
    progress_printer = None

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    "base_url": "https://localhost:3000",  # Changed to HTTPS
    "verify_ssl": False,  # Can be changed to True in production
    "timeout": 30,
    "chunk_size": 8192
}

def decode2binary(file_id: str, jwt_token: str, base_url: str = "https://localhost:3000") -> bytes:
    """
    1. /download/:fileId にアクセスしてメタデータを取得
    2. 返ってきた JSON から urls, keys, ivs, algorithm を取り出す
    3. 各 url で暗号化されたファイルチャンクを GET
    4. 対応する keys[i], ivs[i] で復号
    5. 復号したチャンクを連結し、最終的なバイナリを返す
    """

    # 1. ファイル情報メタデータを取得
    endpoint = f"{base_url}/download/{file_id}"
    headers = {
        "Authorization": f"Bearer {jwt_token}"
    }
    resp = requests.get(endpoint, headers=headers,verify=False)
    resp.raise_for_status()  # ステータスコードが200以外なら例外を投げる

    data = resp.json()

    urls = data.get("urls", [])       # ["https://.../chunk1", "https://.../chunk2", ...]
    keys = data.get("keys", [])       # ["<Base64Key1>", "<Base64Key2>", ...]
    ivs  = data.get("ivs", [])        # ["<Base64Iv1>", "<Base64Iv2>", ...]
    algorithm = data.get("algorithm", "aes-256-cbc")

    # 念のためチェック
    if not urls:
        raise ValueError("No 'urls' in response.")
    if len(urls) != len(keys) or len(urls) != len(ivs):
        raise ValueError("Mismatch in lengths of urls, keys, and ivs.")

    # 2. 復号の結果をまとめるためのバッファ
    decrypted_data = b""
    print(ivs)
    # 3. 各チャンクを取得して復号 → decrypted_data に連結
    for i, url in enumerate(urls):
        # (a) 暗号化ファイルチャンクをHTTP GETで取得
        chunk_resp = requests.get(url)
        chunk_resp.raise_for_status()
        encrypted_chunk = chunk_resp.content  # bytes

        # (b) Base64デコードしたキーとIVを使ってAES復号器を初期化
        key = base64.b64decode(keys[i])
        iv  = base64.b64decode(ivs[i])
        
        # 本例では "aes-256-cbc" を想定
        if algorithm.lower() == "aes-256-cbc":
            cipher = AES.new(key, AES.MODE_CBC, iv)
        else:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # (c) 復号
        decrypted_chunk = cipher.decrypt(encrypted_chunk)
        # PKCS7 Paddingが入っている想定なら、unpadで取り除く
        # ただし複数チャンク分を連結する場合、最後のチャンクだけunpadすることもあるので
        # アップロード時の実装に合わせて調整が必要。
        #
        # ここでは各チャンクが独立してパディングされている想定とし、毎回unpadをかける。
        try:
            decrypted_chunk = unpad(decrypted_chunk, AES.block_size)
        except ValueError:
            # パディング除去失敗の場合は適宜エラー処理
            raise ValueError("Padding error. Possibly incorrect key/IV or corrupted data.")

        # (d) 復号済みチャンクを連結
        decrypted_data += decrypted_chunk

    # 4. 連結した結果をリターン
    return decrypted_data

def get_md5(data: bytes) -> str:
    """
    バイナリデータのMD5を計算し、16進文字列として返す
    """
    md5_hash = hashlib.md5(data).hexdigest()
    return md5_hash


def upload_binary(
    data: bytes,
    original_path: str,
    jwt_token: str,
    base_url: str = "https://localhost:3000"
) -> dict:
    """
    1. /upload/signed エンドポイントに POST して、signedUrlなどの暗号化情報を取得
    2. 得られた鍵・IVで data を暗号化
    3. signedUrl に PUT リクエストを送信
    4. 成功したら fileId 等を返す

    戻り値:
      {
        "fileId": number,
        "uploadedSize": number,  # アップロードしたバイト数
      }
    """
    # (1) メタデータ取得: originalPath, md5を含むペイロードを送信
    md5_hex = get_md5(data)
    payload = {
        "originalPath": original_path,
        "md5": md5_hex
    }
    headers = {"Authorization": f"Bearer {jwt_token}"}

    resp = requests.post(f"{base_url}/upload/signed", json=payload, headers=headers,verify=False)
    
    # Handle 409 Conflict (file already exists)
    if resp.status_code == 409:
        error_data = resp.json()
        raise FileExistsError(f"File already exists: {error_data.get('error', 'Unknown error')}")
    
    resp.raise_for_status()
    meta = resp.json()

    if "error" in meta:
        raise FileExistsError(f"Upload error: {meta['error']}")


    # signedUrl等を取得
    signed_url = meta["signedUrl"]
    file_id = meta["fileId"]
    aes_key_base64 = meta["aesKeyBase64"]
    iv_base64 = meta["ivBase64"]
    algorithm = meta["algorithm"]
    print(iv_base64)
    # (2) 暗号化用のキーとIVをBase64デコード
    aes_key = base64.b64decode(aes_key_base64)  # 32バイト想定
    iv = base64.b64decode(iv_base64)            # 16バイトまたは12バイトなど(アルゴリズムにより)
    print(len(iv))
    # ※ サーバー側で "aes-256-cbc" と言っているなら 16バイトIV のCBCモードを想定
    if algorithm.lower() == "aes-256-cbc":
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    # CBCモードの場合、ブロックサイズに合わせてパディング
    encrypted_data = cipher.encrypt(pad(data, AES.block_size))

    # (3) PUT でアップロード (Content-Type は任意。binaryとして送信)
    put_resp = requests.put(signed_url, data=encrypted_data, headers={"Content-Type": "application/octet-stream"})
    put_resp.raise_for_status()

    # (4) アップロード完了を確認
    confirmation = confirm_upload(file_id, jwt_token, base_url)

    return {
        "fileId": file_id,
        "uploadedSize": len(encrypted_data),
        "finalFilesize": confirmation.get("filesize", len(encrypted_data)),
        "success": confirmation.get("success", True)
    }


def upload_file(
    file_path: str,
    original_path: str,
    jwt_token: str,
    base_url: str = "https://localhost:3000"
) -> dict:
    """
    ローカルファイルを読み込んでバイナリ化し、upload_binary を呼び出すラッパ関数
    """
    with open(file_path, "rb") as f:
        data = f.read()

    result = upload_binary(data, original_path, jwt_token, base_url)
    return result

def register_user(email: str, password: str, base_url: str = "https://localhost:3000") -> str:
    """Register a new user account and return JWT token."""
    payload = {
        "email": email,
        "password": password
    }
    response = requests.post(base_url + "/auth/register", json=payload, verify=False)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(f"Registration failed: {result['error']}")
    return result["token"]


def get_jwt_token(email: str, password: str, base_url: str = "https://localhost:3000") -> str:
    """Authenticate user and get JWT token."""
    payload = {
        "email": email,
        "password": password
    }
    response = requests.post(base_url + "/auth/login", json=payload, verify=False)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(f"Authentication failed: {result['error']}")
    return result["token"]


def confirm_upload(file_id: str, jwt_token: str, base_url: str = "https://localhost:3000") -> Dict[str, Any]:
    """Confirm upload completion and get final file size."""
    payload = {"fileId": file_id}
    headers = {"Authorization": f"Bearer {jwt_token}"}
    
    response = requests.post(f"{base_url}/upload/signed/confirm", json=payload, headers=headers, verify=False)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise ValueError(f"Upload confirmation failed: {result['error']}")
    return result

def upload_file_direct(
    file_path: str,
    upload_token: str,
    base_url: str = "https://localhost:3000"
) -> dict:
    """
    Upload a file using the direct upload endpoint with token authentication.
    
    Args:
        file_path: Path to file to upload
        upload_token: Upload token for authentication
        base_url: Server base URL
        
    Returns:
        Dict with upload result
    """
    import os
    
    # Read file data
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    # Prepare the request
    filename = os.path.basename(file_path)
    files = {'file': (filename, file_data)}
    data = {'filename': filename}
    headers = {'Authorization': f'Bearer {upload_token}'}
    
    # Upload file
    response = requests.post(f"{base_url}/upload/direct", 
                           files=files, 
                           data=data, 
                           headers=headers, 
                           verify=False)
    response.raise_for_status()
    return response.json()


def upload_binary_direct(
    data: bytes,
    filename: str,
    upload_token: str,
    base_url: str = "https://localhost:3000"
) -> dict:
    """
    Upload binary data using the direct upload endpoint with token authentication.
    
    Args:
        data: Binary data to upload
        filename: Name for the uploaded file
        upload_token: Upload token for authentication
        base_url: Server base URL
        
    Returns:
        Dict with upload result
    """
    # Prepare the request
    files = {'file': (filename, data)}
    data_payload = {'filename': filename}
    headers = {'Authorization': f'Bearer {upload_token}'}
    
    # Upload file
    response = requests.post(f"{base_url}/upload/direct", 
                           files=files, 
                           data=data_payload, 
                           headers=headers, 
                           verify=False)
    response.raise_for_status()
    return response.json()

# Export all classes and functions for easy importing
__all__ = [
    # Enhanced client classes (if available)
    'TSFClient', 'TSFConfig', 'UploadResult', 'FileInfo',
    'TSFError', 'AuthenticationError', 'UploadError', 'DownloadError',
    'create_client', 'progress_printer',
    
    # Original functions (backward compatibility)
    'decode2binary', 'upload_binary', 'upload_file', 'get_jwt_token', 'register_user',
    'confirm_upload', 'get_md5', 'DEFAULT_CONFIG',
    
    # New direct upload functions
    'upload_file_direct', 'upload_binary_direct'
]