# Khan Academy Development Standards

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| Backend | Python, Django/Flask, Google App Engine |
| Frontend | React, TypeScript/JavaScript, Less/CSS |
| Testing | Jest, PyTest, Playwright |
| Build | Webpack, Babel |
| Data | PostgreSQL, Redis, Datastore |

## Code Standards

### Python
- PEP 8 style, type hints for signatures
- Docstrings for public functions/classes
- Import modules directly (not `from`)
- Prefer explicit over implicit

### JavaScript/TypeScript
- TypeScript for new code
- Follow ESLint rules
- Functional components with hooks
- Prefer `const` over `let`

### Testing
- Tests for new features
- Update tests when changing behavior
- Run tests before committing
- High coverage on critical paths

## Common Commands

```bash
# Development
make serve                    # Start dev server
make build                    # Build assets

# Testing
make test                     # Run all tests
pytest path/to/test.py       # Python tests
npm test                      # JS tests

# Linting
make lint                     # Check linting
make fix                      # Auto-fix

# Database
make reset-db                 # Reset database
make migrate                  # Run migrations
```

## File Organization

```
~/khan/
├── dev/            # Dev tools and scripts
├── services/       # Microservices/backend
├── webapp/         # Main application
│   ├── src/        # Source code
│   ├── tests/      # Tests
│   └── static/     # Static assets
├── shared/         # Shared libraries
├── config/         # Configuration
└── docs/           # Documentation
```

## Security Reminders

- Never commit secrets or credentials
- Validate all user input
- Sanitize data before display
- Check for SQL injection risks
- Escape HTML output
- Use HTTPS for external calls

## Debugging

**Python**: `import pdb; pdb.set_trace()` or `make logs`

**JS**: Browser console, Chrome DevTools, React DevTools

**DB**: `redis-cli ping`, `psql -U postgres`
