"""FastAPI-specific security patterns.

Provides taint sources, sinks, and sanitizers for FastAPI framework.
"""

# Taint sources (user input)
FASTAPI_TAINT_SOURCES = [
    "Query(...)",
    "Path(...)",
    "Body(...)",
    "Header(...)",
    "Cookie(...)",
    "Form(...)",
    "File(...)",
    "Request.query_params",
    "Request.path_params",
    "Request.headers",
    "Request.cookies",
]

# Taint sinks (dangerous operations)
FASTAPI_TAINT_SINKS = [
    # Command Injection
    "eval",
    "exec",
    "os.system",
    "subprocess.call",
    "subprocess.Popen",
    # Path Traversal
    "FileResponse",
    "open",
    # SSRF
    "requests.get",
    "requests.post",
    "httpx.get",
    "httpx.post",
]

# Auth dependencies
FASTAPI_AUTH_DEPENDENCIES = [
    "Depends(get_current_user)",
    "Depends(get_current_active_user)",
    "Security(...)",
    "HTTPBearer()",
    "OAuth2PasswordBearer(...)",
]

# Security utilities
FASTAPI_SECURITY_UTILS = [
    "fastapi.security.HTTPBasic",
    "fastapi.security.HTTPBearer",
    "fastapi.security.HTTPDigest",
    "fastapi.security.OAuth2",
    "fastapi.security.OAuth2PasswordBearer",
    "fastapi.security.APIKeyHeader",
    "fastapi.security.APIKeyCookie",
    "fastapi.security.APIKeyQuery",
]

# Pydantic validators (sanitizers)
FASTAPI_SANITIZERS = [
    "EmailStr",
    "HttpUrl",
    "validator",
    "Field(..., regex=...)",
]

# Security middleware
FASTAPI_SECURITY_MIDDLEWARE = [
    "CORSMiddleware",
    "TrustedHostMiddleware",
    "HTTPSRedirectMiddleware",
]

# Security best practices
FASTAPI_SECURITY_BEST_PRACTICES = {
    "authentication": [
        "Use OAuth2PasswordBearer or JWT for API authentication",
        "Store passwords hashed (use passlib)",
        "Implement token expiration",
    ],
    "validation": [
        "Use Pydantic models for all input validation",
        "Define explicit Field(...) validators",
        "Use HttpUrl, EmailStr for URL/email validation",
    ],
    "cors": [
        "Configure CORS explicitly",
        "Never use allow_origins=['*'] in production",
        "Use allow_credentials=True only when necessary",
    ],
}
