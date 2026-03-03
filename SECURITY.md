# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public issue
2. Email the maintainer directly or use GitHub's private vulnerability reporting
3. Include steps to reproduce the vulnerability
4. Allow reasonable time for a fix before public disclosure

## Scope

This project is a knowledge graph library and visualization tool. Security concerns include:

- **Seed injection**: Malicious YAML seed files that could execute code
- **MCP server**: Unauthorized access to brain_query/brain_learn tools
- **Path traversal**: File access outside intended directories
- **Dependency vulnerabilities**: Known CVEs in dependencies

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
| < 1.0   | No        |
