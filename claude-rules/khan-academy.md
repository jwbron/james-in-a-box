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

### Testing
- Write tests for new features
- Update tests when changing behavior
- Run test suites before committing
- Aim for high coverage on critical paths

## Common Commands

### Development
```bash
# Start development server
make serve

# Build assets
make build
```

### Testing
```bash
# Run all tests
make test

# Python tests
pytest path/to/test.py
pytest -v  # verbose
pytest -k test_name  # specific test

# JavaScript tests
npm test
npm test -- --watch
```

### Linting and Formatting
```bash
# Check linting
make lint

# Auto-fix linting issues
make fix

# Python specific
black path/to/file.py
pylint path/to/file.py

# JavaScript specific
eslint path/to/file.js
prettier --write path/to/file.js
```

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
   - Run tests locally

3. **Run linters and tests locally**
   ```bash
   make lint
   make test
   ```

4. **Commit with clear messages**
   ```bash
   git add .
   git commit -m "feat: Add feature description"
   ```

5. **Prepare PR artifacts**
   ```bash
   @create-pr audit
   # Generates PR description file
   ```
   
6. **Human pushes, opens PR, and merges** (from host)

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

