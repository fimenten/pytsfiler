import requests
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import requests
import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import os
import pathlib
def decode2binary(file_id: str, jwt_token: str, base_url: str = "http://localhost:3000") -> bytes:
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
    base_url: str = "http://localhost:3000"
) -> dict:
    """
    1. /upload エンドポイントに POST して、signedUrlなどの暗号化情報を取得
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

    resp = requests.post(f"{base_url}/upload", json=payload, headers=headers,verify=False)
    resp.raise_for_status()
    meta = resp.json()

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
    # ※ サーバー側で “aes-256-cbc” と言っているなら 16バイトIV のCBCモードを想定
    if algorithm.lower() == "aes-256-cbc":
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    else:
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    # CBCモードの場合、ブロックサイズに合わせてパディング
    encrypted_data = cipher.encrypt(pad(data, AES.block_size))

    # (3) PUT でアップロード (Content-Type は任意。binaryとして送信)
    put_resp = requests.put(signed_url, data=encrypted_data, headers={"Content-Type": "application/octet-stream"})
    put_resp.raise_for_status()

    return {
        "fileId": file_id,
        "uploadedSize": len(encrypted_data)
    }


def upload_file(
    file_path: str,
    original_path: str,
    jwt_token: str,
    base_url: str = "http://localhost:3000"
) -> dict:
    """
    ローカルファイルを読み込んでバイナリ化し、upload_binary を呼び出すラッパ関数
    """
    with open(file_path, "rb") as f:
        data = f.read()

    result = upload_binary(data, original_path, jwt_token, base_url)
    return result

def get_jwt_token(email,password,base_url):
    payload = {
        "email": email,
        "password": password
    }
    response = requests.post(base_url + "/auth/login", json=payload,verify=False)
    token = response.json()["token"]
    return token
def putMetaData(token:str,BASE_URL,data:dict):  
    header = {"authorization":f"a {token}"}
    ret = requests.put(f"{BASE_URL}/metadata",json={"metadata":data},verify=False,headers=header)
    ret.raise_for_status()
    return ret

def queryMetaData(token:str,query:dict,BASE_URL:str,select:dict):
    header = {"authorization":f"a {token}"}
    ret = requests.post(f"{BASE_URL}/metadata/query",headers=header,json={"query":query,"select":select},verify=False)
    ret.raise_for_status()
    return ret

def recursive_dealing(p:str,email,password,host_url):
    pathes = list(pathlib.Path(p).glob("*"))
    files = [p for p in pathes if not p.is_dir()]
    dirs = [p for p in pathes if p.is_dir()]
    print(files)
    print(dirs)
    for p in files:
        print(p)
        with open(p,mode="rb") as f:
            binary = f.read()
        token = get_jwt_token(email,password,host_url)
        try:
            upload_binary(binary,str(p),token,host_url)
            os.remove(p)
        except Exception as e:
            print(e)
            pass
    
    for p in dirs:
        recursive_dealing(p,email,password,host_url)


if __name__ == "__main__":
    # テスト用
    pass
