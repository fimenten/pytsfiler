# PyTSFiler - Python Client for TSF Server

Enhanced Python client library for the TSF (TypeScript File) server API with latest server compatibility.

## Features

- **JWT & Token Authentication**: Support for both authentication methods
- **File Upload/Download**: Binary file operations with encryption
- **Direct Upload**: Token-based direct upload functionality  
- **Enhanced Client**: Async client with progress tracking
- **Server API Compatibility**: Updated for latest server endpoints

## Installation

```bash
pip install -e .
```

## Quick Start

### Basic Usage

```python
from pytsfiler import get_jwt_token, upload_file, decode2binary

# Authenticate
token = get_jwt_token("user@example.com", "password")

# Upload file
result = upload_file("local_file.txt", "remote_path.txt", token)
print(f"File uploaded with ID: {result['fileId']}")

# Download file
data = decode2binary(result['fileId'], token)
with open("downloaded_file.txt", "wb") as f:
    f.write(data)
```

### Direct Upload (Token-based)

```python
from pytsfiler import upload_file_direct

# Upload with token (no JWT required)
result = upload_file_direct("file.txt", "your_upload_token")
```

### Enhanced Async Client

```python
import asyncio
from pytsfiler import TSFClient, TSFConfig

async def main():
    config = TSFConfig(base_url="https://your-server.com")
    
    async with TSFClient(config) as client:
        await client.authenticate("user@example.com", "password")
        
        # Upload with progress tracking
        result = await client.upload_file("large_file.zip")
        print(f"Upload result: {result}")

asyncio.run(main())
```

## API Endpoints

The client supports the latest TSF server API:

- `POST /upload/signed` - JWT-authenticated uploads
- `POST /upload/signed/confirm` - Upload confirmation
- `POST /upload/direct` - Token-based direct uploads
- `GET /download/:fileId` - File downloads
- `GET /files` - File listing
- `POST /auth/login` - User authentication

## Server Compatibility

This client is compatible with the latest TSF server API changes:
- Updated upload endpoints (`/upload/signed`)
- New direct upload functionality
- Enhanced file metadata handling