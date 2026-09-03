# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.19.x   | ✅ Yes              |
| 0.14.x   | ⚠️ Research Only   |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability:

1. **Do NOT open a public Issue** — vulnerabilities should be handled privately
2. Contact: `jaby@example.com` (or via GitHub Private Messages)
3. Include steps to reproduce and expected behavior

## Security Measures

### 🔒 Code Safety
- No hardcoded secrets, API keys, or credentials in source code
- SSH keys and tokens managed via environment variables only
- `.gitignore` excludes `.env`, `*.key`, and sensitive config files

### 🧪 Automated Scanning
- Pre-commit hook checks for accidental secret leaks
- CI pipeline scans for known vulnerable dependencies

### 📦 Package Distribution
- All releases verified via SHA-256 checksums
- Signed tags for official releases on GitHub

---

*This project is provided as-is without warranty. Use at your own risk.*
