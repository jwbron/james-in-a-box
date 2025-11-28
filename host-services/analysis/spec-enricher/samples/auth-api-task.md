# Task: Add Authentication to API Endpoints

## Description

Secure the new user data API endpoints with JWT authentication.

## Requirements

- Add JWT token validation middleware
- Protect all /api/v2/user/* endpoints
- Return 401 for invalid/missing tokens
- Follow security best practices

## Acceptance Criteria

- [ ] All protected endpoints require valid JWT
- [ ] Invalid tokens return 401
- [ ] Tests cover auth scenarios
