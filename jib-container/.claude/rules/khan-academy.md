# Khan Academy Development Standards

## Project Context

You are working in the Khan Academy codebase at `~/khan/`

### Key Technologies
- **Backend**: Python, Django/Flask, Google App Engine
- **Frontend**: React, TypeScript/JavaScript, Less/CSS
- **Testing**: Jest, PyTest, Playwright
- **Build**: Webpack, Babel
- **Data**: PostgreSQL, Redis, Datastore

## Code Standards

### Python
- Follow PEP 8 style guide
- Use type hints for function signatures
- Write docstrings for public functions/classes
- Import modules directly (not using `from`)
- Prefer explicit over implicit

Example:
```python
import os
import sys

def process_data(input_file: str) -> dict:
    """Process input file and return results.
    
    Args:
        input_file: Path to input file
        
    Returns:
        Dictionary with processed results
    """
    # Implementation
    pass
```

### JavaScript/TypeScript
- Use TypeScript for new code
- Follow ESLint rules
- Use functional components with hooks
- Prefer const over let
- Use meaningful variable names

Example:
```typescript
import React from 'react';

export const MyComponent: React.FC<Props> = ({name}) => {
    const [count, setCount] = React.useState(0);
    
    return <div>{name}: {count}</div>;
};
```

### Testing (REQUIRED Before PR)

**Core Requirements:**
- Write tests for new features (no exceptions)
- Update tests when changing behavior
- Run test suites before committing AND before opening PR
- Aim for high coverage on critical paths
- **Never open a PR with failing tests**

**Test Coverage Expectations:**
- New features: Must have corresponding tests
- Bug fixes: Add a test that would have caught the bug
- Refactoring: Existing tests should still pass (no test changes needed unless API changed)

**Test Naming Conventions:**
- Python: `test_<function_name>_<scenario>` (e.g., `test_login_with_invalid_password`)
- JavaScript: `describe('<Component/Module>')` → `it('should <expected behavior>')`

## Common Commands

### Development
```bash
# Start development server
make serve

# Build assets
make build
```

### Testing (Run These BEFORE Opening Any PR)

**REQUIRED: Run full test suite before PR:**
```bash
# Run all tests (MANDATORY before PR)
make test
```

**For faster iteration during development:**
```bash
# Python tests - specific file
pytest path/to/test.py -v

# Python tests - specific test
pytest -k test_name -v

# Python tests - see full output on failures
pytest --tb=long

# JavaScript tests - all
npm test

# JavaScript tests - watch mode (during development)
npm test -- --watch

# JavaScript tests - specific file
npm test -- --testPathPattern="filename"
```

**Verify test results before PR:**
```bash
# Good (proceed to PR):
# ==================== 47 passed in 3.21s ====================

# Bad (FIX BEFORE PR):
# ==================== 45 passed, 2 failed in 3.45s ====================
```

### Linting and Formatting (Run These BEFORE Opening Any PR)

**REQUIRED: Run linters before PR:**
```bash
# Check linting (MANDATORY before PR)
make lint

# Auto-fix linting issues
make fix
```

**Language-specific tools:**
```bash
# Python - format and lint
black path/to/file.py      # Auto-format
pylint path/to/file.py     # Lint check
mypy path/to/file.py       # Type check (if used)

# JavaScript/TypeScript - format and lint
prettier --write path/to/file.js   # Auto-format
eslint path/to/file.js             # Lint check
eslint --fix path/to/file.js       # Auto-fix lint issues
```

**Before PR, ensure:**
- `make lint` passes with no errors
- `make test` passes with all tests green

### Database
```bash
# Reset database
make reset-db

# Run migrations
make migrate
```

### Dependencies
```bash
# Python dependencies
pip install -r requirements.txt

# JavaScript dependencies
npm install
```

## File Organization

```
~/khan/
├── dev/            # Development tools and scripts
├── services/       # Microservices and backend code
├── webapp/         # Main application code
│   ├── src/        # Source code
│   ├── tests/      # Test files
│   └── static/     # Static assets
├── shared/         # Shared libraries and utilities
├── config/         # Configuration files
└── docs/           # Documentation
```

## Development Workflow

1. **Create a feature branch**
   ```bash
   git checkout -b feature/description
   ```

2. **Make changes with tests**
   - Write code
   - Write/update tests
   - Run tests frequently during development

3. **Run linters and fix issues**
   ```bash
   make lint       # Check for issues
   make fix        # Auto-fix what can be fixed
   make lint       # Verify all issues resolved
   ```

4. **Run full test suite (MANDATORY)**
   ```bash
   make test
   # Must see "X passed, 0 failed" before proceeding
   # If tests fail: FIX THEM before continuing
   ```

5. **Commit with clear messages**
   ```bash
   git add .
   git commit -m "feat: Add feature description

   - Detail 1
   - Detail 2
   - All tests passing: X passed"
   ```

6. **Final verification before PR**
   ```bash
   # One last check
   make lint && make test
   # Both must pass with no errors
   ```

7. **Create PR** (for writable repos)
   ```bash
   create-pr-helper.py --auto --reviewer jwiesebron
   ```

8. **Human reviews and merges** (from GitHub)

## Debugging Tips

### Backend (Python)
```bash
# View application logs
make logs

# Use pdb for debugging
import pdb; pdb.set_trace()

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### Frontend (JavaScript)
- Use browser console for errors
- Use Chrome DevTools for debugging
- Check Network tab for API calls
- Use React DevTools extension

### Database
```bash
# Check Redis
redis-cli ping

# PostgreSQL console
psql -U postgres

# Check if services running
service postgresql status
service redis-server status
```

## Security Reminders

- Never commit secrets or credentials
- Use environment variables for config
- Validate all user input
- Sanitize data before display
- Follow principle of least privilege
- Check for SQL injection risks
- Escape HTML output
- Use HTTPS for external calls

## Getting Help

### Documentation
```bash
# Check project docs
cat ~/khan/docs/README.md

# Check Confluence
cat ~/confluence-docs/ENG/...
cat ~/confluence-docs/INFRA/...
```

### Code Examples
- Look at similar existing code in the codebase
- Follow established patterns
- Check ADRs for architectural decisions

### When Stuck
- Read relevant ADRs in `~/confluence-docs/`
- Search codebase for similar implementations
- Ask user for clarification on ambiguous requirements
- Document what you've tried

## Common Patterns

### API Endpoints
```python
# Backend route
@app.route('/api/v1/resource', methods=['GET', 'POST'])
def resource_handler():
    if request.method == 'POST':
        # Handle POST
        pass
    return jsonify(data)
```

### React Components
```typescript
// Functional component with hooks
export const ComponentName: React.FC<Props> = ({prop1, prop2}) => {
    const [state, setState] = React.useState(initialValue);
    
    React.useEffect(() => {
        // Side effects
    }, [dependencies]);
    
    return <div>...</div>;
};
```

### Testing
```python
# Python test
def test_feature():
    result = function_under_test(input)
    assert result == expected
```

```javascript
// JavaScript test
describe('ComponentName', () => {
    it('should render correctly', () => {
        const {getByText} = render(<ComponentName />);
        expect(getByText('expected')).toBeInTheDocument();
    });
});
```

---

**See also**: `mission.md` for your role and workflow, `environment.md` for sandbox constraints.

