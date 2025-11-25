# Test Discovery and Execution Workflow

## Overview

Before making code changes in any repository, you MUST understand and follow the testing practices of that specific codebase. Rather than assuming hardcoded test commands, dynamically discover how tests are configured and run.

## Test Discovery (ALWAYS DO FIRST)

When starting work on a new codebase or repository, run the test discovery tool:

```bash
# Discover test configuration in current directory
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py

# Discover tests in a specific project
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py ~/khan/<repo>

# Get JSON output for programmatic use
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py --json
```

The tool scans for:
- **Python**: pytest.ini, pyproject.toml, setup.cfg, conftest.py, unittest patterns
- **JavaScript/TypeScript**: jest.config.js, package.json scripts, vitest, mocha, playwright
- **Go**: go.mod with built-in go test
- **Java**: Maven (pom.xml), Gradle (build.gradle)
- **Makefile targets**: test, lint, check, verify
- **Shell scripts**: test.sh, run-tests.sh, etc.

## Test Execution Workflow

### 1. Before Making Changes

**ALWAYS run existing tests first** to establish a baseline:

```bash
# Use discovered test command (e.g., from discover-tests.py output)
make test      # If Makefile target exists
pytest         # If pytest detected
npm test       # If package.json test script exists
go test ./...  # If Go project
```

If tests fail before your changes, note this and investigate whether it's a known issue or environmental problem.

### 2. During Development

Run tests frequently as you make changes:

```bash
# Run tests related to changed files (if supported)
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py --run --files "src/foo.py,src/bar.py"

# Or run specific test file
pytest path/to/test_file.py
jest path/to/file.test.js
```

### 3. Writing New Tests

When adding or modifying functionality, write tests that follow the codebase patterns:

**Discover existing patterns first:**
```bash
# Find existing test files to understand patterns
find . -name "test_*.py" -o -name "*.test.js" | head -20

# Look at existing test structure
cat tests/test_example.py  # or similar
```

**Follow discovered conventions:**
- Use the same test framework (pytest, jest, etc.)
- Match file naming patterns (test_*.py vs *_test.py)
- Follow test directory structure
- Use similar assertion styles
- Match fixture/mock patterns

### 4. Before Committing

**ALWAYS ensure tests pass before creating a PR:**

```bash
# Run full test suite
make test  # or discovered command

# Run linting if available
make lint  # or npm run lint, etc.
```

If tests fail:
1. Fix the failing tests (if your changes caused them)
2. Document why tests fail (if pre-existing issue)
3. Do NOT commit with failing tests unless explicitly discussed with the human

## Test File Patterns by Language

### Python (pytest)
```python
# test_<module>.py or <module>_test.py
import pytest
from mymodule import function_to_test

def test_function_does_expected_thing():
    result = function_to_test(input)
    assert result == expected

class TestClassName:
    def test_method_behavior(self):
        assert some_condition
```

### JavaScript/TypeScript (Jest)
```javascript
// *.test.js, *.spec.js, *.test.ts, *.spec.ts
import { functionToTest } from './module';

describe('functionToTest', () => {
  it('should return expected result', () => {
    expect(functionToTest(input)).toBe(expected);
  });
});
```

### Go
```go
// *_test.go
package mypackage

import "testing"

func TestFunctionName(t *testing.T) {
    result := FunctionName(input)
    if result != expected {
        t.Errorf("got %v, want %v", result, expected)
    }
}
```

## Common Test Commands Reference

| Framework | Run All | Run Specific | Watch Mode | Coverage |
|-----------|---------|--------------|------------|----------|
| pytest | `pytest` | `pytest test_file.py` | `pytest-watch` | `pytest --cov` |
| jest | `npm test` | `jest file.test.js` | `jest --watch` | `jest --coverage` |
| go test | `go test ./...` | `go test -run TestName` | - | `go test -cover` |
| gradle | `./gradlew test` | `./gradlew test --tests ClassName` | - | - |
| make | `make test` | (varies) | - | - |

## Handling Test Failures

### If Pre-existing Tests Fail
1. Run `git status` to confirm you haven't modified test-related files
2. Check if this is a known issue (search JIRA, recent commits)
3. Document the failure in your PR description
4. Consider notifying the human for guidance

### If Your Changes Cause Failures
1. Read the error message carefully
2. Determine if test needs updating (behavior change) or code is wrong
3. Fix the issue before committing
4. Run full test suite to catch regressions

### If Tests Are Flaky
1. Run the test multiple times to confirm flakiness
2. Note the flaky behavior in PR description
3. Consider adding a fix for the flakiness as a separate task

## Integration with Workflow

This test workflow integrates with the overall development process:

```
1. Receive task
2. ** Discover tests (NEW - run discover-tests.py) **
3. ** Run existing tests (NEW - baseline check) **
4. Gather context (ADRs, Confluence, existing code)
5. Plan and implement
6. ** Write new tests following discovered patterns (NEW) **
7. ** Verify all tests pass (NEW) **
8. Document and commit
9. Create PR
```

## Quick Reference

```bash
# Discovery
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py

# Run discovered tests
~/khan/james-in-a-box/jib-container/scripts/discover-tests.py --run

# Common direct commands (use discovered command when possible)
make test           # Makefile-based projects
npm test            # Node.js projects
pytest              # Python projects
go test ./...       # Go projects
./gradlew test      # Gradle projects
mvn test            # Maven projects
```

---

**Remember**: Every codebase is different. Don't assume test commands - discover them first!
