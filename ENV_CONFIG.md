# PyTSFiler Environment Configuration

This document explains how to configure the pyclient using environment variables.

## Quick Start

1. Copy the template file:
   ```bash
   cp .env.template .env
   ```

2. Edit `.env` with your server credentials and settings

3. Run the test script to verify configuration:
   ```bash
   python test_with_env.py
   ```

## Environment Variables

### Authentication
- `PYTSFILER_EMAIL`: Your TSF server login email
- `PYTSFILER_PASSWORD`: Your TSF server password

### Server Configuration  
- `PYTSFILER_BASE_URL`: Full HTTPS URL of your TSF server (e.g., `https://localhost:3000`)
- `PYTSFILER_VERIFY_SSL`: Set to `false` for self-signed certificates

### Upload Settings
- `PYTSFILER_UPLOAD_TOKEN`: Optional token for direct uploads (bypasses JWT auth)
- `PYTSFILER_CHUNK_SIZE`: Size of chunks for file operations (default: 8192 bytes)
- `PYTSFILER_MAX_FILE_SIZE`: Maximum file size allowed (default: 100MB)

### Network Settings
- `PYTSFILER_TIMEOUT`: Request timeout in seconds (default: 30)
- `PYTSFILER_RETRY_LIMIT`: Number of retry attempts (default: 3)
- `PYTSFILER_RETRY_DELAY`: Delay between retries in seconds (default: 1)

### Logging
- `PYTSFILER_LOG_LEVEL`: Log verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `PYTSFILER_LOG_FILE`: Optional path to log file (defaults to console)

### Development
- `PYTSFILER_DEBUG`: Enable debug mode for verbose output
- `PYTSFILER_SHOW_PROGRESS`: Show upload/download progress bars

## Fallback Configuration

The pyclient will check for environment variables in this order:
1. PyTSFiler-specific variables (e.g., `PYTSFILER_EMAIL`)
2. Legacy KOEKOE variables (e.g., `KOEKOE_EMAIL`) 
3. Default values

## SSL/TLS Configuration

For production environments with proper SSL certificates:
```bash
PYTSFILER_VERIFY_SSL=true
```

For self-signed certificates or development:
```bash
PYTSFILER_VERIFY_SSL=false
```

To use a custom CA certificate:
```bash
PYTSFILER_CA_CERT_PATH=/path/to/ca-cert.pem
```

## Testing Your Configuration

Run the included test script to verify all settings:
```bash
python test_with_env.py
```

This will test:
- JWT authentication
- File upload with encryption
- File download and decryption
- Data integrity verification
- Direct upload (if token provided)