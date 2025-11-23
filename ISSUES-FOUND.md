# Issues Found During Documentation Review

## Critical Issues

### 1. Incorrect jib Script Path
**Location**: Main README.md, Container Control section
**Issue**: Documentation says `./jib` from root directory
**Reality**: Script is at `jib-container/jib` (with symlink at `bin/jib`)
**Fix**: Update README to use `bin/jib` or document adding to PATH

```bash
# Current (broken):
cd ~/khan/james-in-a-box
./jib

# Should be:
cd ~/khan/james-in-a-box
bin/jib

# Or:
cd ~/khan/james-in-a-box/jib-container
./jib
```

### 2. Broken Symlink
**Location**: `bin/setup-codebase-analyzer`
**Issue**: Points to `../components/codebase-analyzer/analyzer-ctl` which was deleted
**Fix**: Update symlink to point to `setup.sh` like other components

```bash
# Current (broken):
bin/setup-codebase-analyzer -> ../components/codebase-analyzer/analyzer-ctl

# Should be:
bin/setup-codebase-analyzer -> ../components/codebase-analyzer/setup.sh
```

### 3. Missing MIGRATION.md File
**Location**: Referenced in main README under "Migration" section
**Issue**: File doesn't exist
**Fix**: Either create the file or remove reference from README

## Consistency Issues

### 4. Missing Symlink for Conversation Analyzer
**Location**: `bin/` directory
**Issue**: `setup-codebase-analyzer` exists but `setup-conversation-analyzer` doesn't
**Recommendation**: Either add `setup-conversation-analyzer` symlink or remove `setup-codebase-analyzer` for consistency

Current bin/ setup scripts:
- ✅ setup-slack-notifier
- ✅ setup-slack-receiver
- ✅ setup-service-monitor
- ✅ setup-codebase-analyzer (broken)
- ❌ setup-conversation-analyzer (missing)

### 5. Incorrect Service Documentation References
**Location**: Component service files
**Issues**:

1. **slack-notifier.service**:
   ```ini
   Documentation=file:///home/jwies/khan/james-in-a-box/HOST-SLACK-NOTIFIER.md
   ```
   File doesn't exist. Should reference either:
   - `file:///home/jwies/khan/james-in-a-box/docs/architecture/host-slack-notifier.md`
   - `file:///home/jwies/khan/james-in-a-box/components/slack-notifier/README.md`

2. **Inconsistent GitHub URLs**:
   - codebase-analyzer.service: `https://github.com/jwiesebron/james-in-a-box`
   - conversation-analyzer.service: `https://github.com/jwiesebron/james-in-a-box`
   - slack-receiver.service: `https://github.com/anthropics/james-in-a-box`

   Choose one canonical repo URL and standardize.

## Recommended Fixes

### Quick Fix Script

```bash
#!/bin/bash
cd ~/khan/james-in-a-box

# 1. Fix broken symlink
rm bin/setup-codebase-analyzer
ln -s ../components/codebase-analyzer/setup.sh bin/setup-codebase-analyzer

# 2. Add missing symlink
ln -s ../components/conversation-analyzer/setup.sh bin/setup-conversation-analyzer

# 3. Fix slack-notifier service documentation
sed -i 's|HOST-SLACK-NOTIFIER.md|components/slack-notifier/README.md|' \
  components/slack-notifier/slack-notifier.service

# 4. Standardize GitHub URLs (pick one)
# Option A: Use anthropics
find components -name "*.service" -exec sed -i \
  's|github.com/jwiesebron|github.com/anthropics|g' {} \;

# Option B: Use jwiesebron (current maintainer)
find components -name "*.service" -exec sed -i \
  's|github.com/anthropics|github.com/jwiesebron|g' {} \;
```

### Documentation Updates Needed

1. **Main README.md**:
   - Change `./jib` to `bin/jib`
   - Remove MIGRATION.md reference or create the file

2. **bin/README.md**:
   - Document that users should add `bin/` to PATH for convenience
   - Or document using `bin/command-name` explicitly

## Summary

**High Priority**:
- ❗ Fix broken symlink (prevents codebase-analyzer setup)
- ❗ Update jib path in README (confusing for new users)
- ❗ Fix service documentation paths (systemd warnings)

**Medium Priority**:
- ⚠️  Add conversation-analyzer symlink (consistency)
- ⚠️  Standardize GitHub URLs (minor confusion)
- ⚠️  Create or remove MIGRATION.md reference

**Low Priority**:
- ℹ️  Document PATH setup for bin/ directory
