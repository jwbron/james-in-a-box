# Building Reusable Tools in ~/tools/

## Purpose

The `~/tools/` directory is for building reusable scripts and utilities that persist across container rebuilds. When you find yourself doing something repeatedly, or need a custom tool that should survive sessions, put it here.

## Location

- **Host**: `~/.jib-tools/`
- **Container**: `~/tools/`
- **Persistence**: Read-write, survives container rebuilds
- **Sharing**: Accessible from both host and container

## What to Put Here

### Good Uses
✅ **Custom scripts** - Automation for repetitive tasks
✅ **Helper tools** - Utilities that wrap complex commands
✅ **Code generators** - Templates and boilerplate generators
✅ **Test runners** - Smart test execution scripts
✅ **Validation tools** - PR checks, lint runners
✅ **Setup scripts** - Environment configuration helpers
✅ **Data processors** - Scripts for transforming/analyzing data

### Not Here
❌ **Project-specific code** - Goes in `~/khan/`
❌ **Temporary files** - Use `~/tmp/` instead
❌ **Large binaries** - Install system-wide or use package managers
❌ **Context documents** - Use `@save-context` instead

## Examples

### Test Runner
```bash
# ~/tools/run-tests.sh
#!/bin/bash
set -euo pipefail

cd ~/khan/webapp
echo "🧪 Running tests..."
npm test -- --coverage
```

### PR Validator
```bash
# ~/tools/check-pr.sh
#!/bin/bash
# Validates PR before creation

echo "🔍 Checking for common issues..."
grep -r "console.log" . --exclude-dir=node_modules && {
    echo "❌ Found console.log statements"
    exit 1
}

grep -r "TODO" . --exclude-dir=node_modules && {
    echo "⚠️  Found TODO comments (review before PR)"
}

echo "✅ PR validation passed"
```

### Code Generator
```python
# ~/tools/generate-component.py
#!/usr/bin/env python3
import sys
import os

if len(sys.argv) < 2:
    print("Usage: generate-component.py ComponentName")
    sys.exit(1)

name = sys.argv[1]
template = f"""
import React from 'react';

export const {name} = () => {{
    return <div>{name}</div>;
}};
"""

path = f"~/khan/webapp/src/components/{name}.tsx"
with open(os.path.expanduser(path), 'w') as f:
    f.write(template)

print(f"✅ Created {name} component")
```

### Development Environment Setup
```bash
# ~/tools/setup-dev-env.sh
#!/bin/bash
# Install commonly needed tools

echo "🔧 Setting up development environment..."

# Install system packages
apt-get update && apt-get install -y \
    ripgrep \
    fd-find \
    jq \
    httpie

# Install Python tools
pip install \
    pytest-watch \
    black \
    mypy

# Install Node tools
npm install -g \
    typescript-language-server \
    prettier

echo "✅ Development environment ready"
```

## Best Practices

### 1. Make Scripts Executable
```bash
chmod +x ~/tools/my-script.sh
```

### 2. Use Shebangs
```bash
#!/bin/bash
# or
#!/usr/bin/env python3
```

### 3. Add Help Text
```bash
#!/bin/bash
# Generate React component
# Usage: generate-component.sh ComponentName

if [ $# -eq 0 ]; then
    echo "Usage: $0 ComponentName"
    exit 1
fi
```

### 4. Error Handling
```bash
#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures
```

### 5. Document Purpose
Add comments explaining:
- What the script does
- When to use it
- Any prerequisites
- Example usage

## Workflow

### Building a Tool

1. **Identify need**: "I keep doing X manually"

2. **Prototype in ~/tmp/**: Test the logic
   ```bash
   cd ~/tmp/
   vim prototype.sh
   bash prototype.sh  # Test it
   ```

3. **Move to ~/tools/**: Once it works
   ```bash
   mv ~/tmp/prototype.sh ~/tools/my-tool.sh
   ```

4. **Make executable**
   ```bash
   chmod +x ~/tools/my-tool.sh
   ```

5. **Document**: Add usage comments at top

6. **Test**: Run it a few times to verify

7. **Refine**: Improve based on usage

### Using Tools

```bash
# Direct execution
~/tools/run-tests.sh

# Add to PATH in your session
export PATH="$HOME/tools:$PATH"
run-tests.sh

# Call from other scripts
bash ~/tools/setup-dev-env.sh
```

## Integration with Workflow

### In PR Creation
```bash
# Before creating PR
~/tools/check-pr.sh
@create-pr audit
```

### In Testing
```bash
# Continuous testing during development
~/tools/watch-tests.sh
```

### In Setup
```bash
# When starting a new session
~/tools/setup-dev-env.sh
~/tools/check-dependencies.sh
```

## Tool Ideas

### Automation
- `deploy-check.sh` - Pre-deployment validation
- `sync-deps.sh` - Update all dependencies
- `clean-build.sh` - Clean and rebuild everything
- `backup-db.sh` - Snapshot database state

### Code Quality
- `check-coverage.sh` - Ensure test coverage thresholds
- `find-todos.sh` - List all TODO comments
- `check-types.sh` - Run type checkers across codebase
- `security-scan.sh` - Run security linters

### Development Utilities
- `create-migration.sh` - Generate database migration
- `extract-strings.sh` - Extract i18n strings
- `optimize-images.sh` - Compress images in directory
- `generate-api-client.py` - Generate API client from OpenAPI spec

### Testing
- `test-changed.sh` - Run tests for changed files only
- `test-integration.sh` - Run integration test suite
- `benchmark.sh` - Run performance benchmarks
- `load-test.sh` - Load testing utilities

## Sharing Tools

When you build a particularly useful tool:

1. **Document it well** - Clear comments and usage
2. **Make it robust** - Add error handling
3. **Consider team value** - Could others benefit?
4. **Mention in context** - Add to `@save-context` so you remember it

## Maintenance

### Review Occasionally
```bash
# List all tools
ls -lh ~/tools/

# Remove obsolete tools
rm ~/tools/old-unused-script.sh
```

### Update Documentation
- Keep comments current when changing scripts
- Update usage examples if interface changes
- Add version comments for significant changes

### Test After Changes
```bash
# After modifying a tool, test it
~/tools/modified-tool.sh --test
```

## Advanced Patterns

### Tool with Configuration
```bash
#!/bin/bash
# ~/tools/deploy-check.sh

CONFIG_FILE="$HOME/tools/.deploy-config"

if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
else
    echo "⚠️  No config found, using defaults"
    TARGET_ENV="staging"
fi

echo "Checking deployment to $TARGET_ENV..."
```

### Tool that Calls Other Tools
```bash
#!/bin/bash
# ~/tools/pre-commit.sh
# Runs all checks before committing

set -euo pipefail

echo "Running pre-commit checks..."

~/tools/check-pr.sh || exit 1
~/tools/check-coverage.sh || exit 1
~/tools/run-tests.sh || exit 1

echo "✅ All checks passed"
```

### Tool with Options
```bash
#!/bin/bash
# ~/tools/run-tests.sh

WATCH=false
COVERAGE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --watch) WATCH=true; shift ;;
        --coverage) COVERAGE=true; shift ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [ "$WATCH" = true ]; then
    npm test -- --watch
elif [ "$COVERAGE" = true ]; then
    npm test -- --coverage
else
    npm test
fi
```

## Remember

Tools in this directory are **yours to build and evolve**. Think of it as your personal toolbox that grows more useful over time.

**Golden rule**: When you solve a problem with a script, ask yourself "Will I need this again?" If yes, save it to `~/tools/`.

---

**See also**: `environment.md` for file system layout, `mission.md` for your overall workflow.

