# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in cobol-wrap, please report it privately.

- Email: **kossiso@electricsheep.africa**
- Subject: **[cobol-wrap Security] <short description>**

Please include:

1. A clear description of the issue
2. Steps to reproduce
3. Affected version(s)
4. Potential impact
5. Any suggested mitigation

## Response Process

- We will acknowledge receipt within **72 hours**.
- We will investigate and triage severity.
- We will work on a fix and coordinate responsible disclosure.
- We will publish a security advisory once a patch is available.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x   | Yes       |
| < 1.0.0 | No        |

## Scope

Security reports are especially valuable for:

- SQL injection in generated VSAM bridge code
- Code injection via COBOL source parsing
- Unsafe ctypes memory access in generated shims
- Path traversal in model registry or file operations
- Authentication/authorization issues in generated APIs
