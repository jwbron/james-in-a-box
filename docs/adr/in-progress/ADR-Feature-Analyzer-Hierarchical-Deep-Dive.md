# ADR: Feature Analyzer - Hierarchical Deep-Dive with PR-Based Workflow

**Driver:** James Wiesebron
**Approver:** James Wiesebron
**Status:** In Progress
**Proposed:** December 2025

## Table of Contents

- [Context](#context)
- [Decision](#decision)
- [Implementation Plan](#implementation-plan)
- [Open Questions](#open-questions)
- [Consequences](#consequences)

## Context

### Background

The current feature analyzer provides a robust foundation for codebase analysis with multiple agent passes:

1. **Cartographer Agent**: Discovers which directories contain features
2. **Scout Agent**: Recommends which files to read for feature detection
3. **Analyzer Agent**: Extracts features from file contents

However, the current implementation has limitations for complex codebases:

**Problem 1: Artificial Processing Limits**
- `MAX_DEEP_ANALYSIS_FILES = 15` limits analysis depth
- Large codebases with many features may be truncated
- No mechanism to ensure comprehensive coverage

**Problem 2: Single-Pass, Non-Interactive Analysis**
- Analysis runs to completion without human checkpoints
- No opportunity for feedback like "you missed this" or "combine these"
- All results delivered at once, making review overwhelming

**Problem 3: Flat Feature Structure**
- Features are listed flatly without hierarchical organization
- Monoliths may have services → modules → sub-features
- James-in-a-box has integrations → sub-components → specific features

### Goals

1. **Comprehensive Analysis**: Remove artificial limits; ensure all features are captured
2. **Two-Phase Workflow**: Higher-level analysis first, then deep-dives on request
3. **Human-in-the-Loop**: PR-based workflow with feedback opportunity between phases
4. **Hierarchical Structure**: Support multi-level feature hierarchies
5. **Flexible Depth**: User can specify which features to deep-dive into

### Non-Goals

- Real-time streaming of analysis results
- Multi-repository analysis (single-repo scope)
- Automatic deep-dive without user trigger

## Decision

We will implement a **hierarchical, PR-based feature analysis workflow** with the following components:

### Workflow Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 1: HIGH-LEVEL ANALYSIS                  │
│                                                                  │
│  User triggers: feature-analyzer analyze-structure               │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │ Cartographer │───►│    Scout     │───►│   Analyzer   │       │
│  │   (dirs)     │    │  (files)     │    │ (features)   │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                │                                 │
│                                ▼                                 │
│                     ┌────────────────────┐                       │
│                     │  HIGH_LEVEL.md     │                       │
│                     │  (categories only) │                       │
│                     └────────────────────┘                       │
│                                │                                 │
│                                ▼                                 │
│                     ┌────────────────────┐                       │
│                     │  Open PR for       │                       │
│                     │  human review      │                       │
│                     └────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
              ┌───────────────────────────────────────┐
              │         HUMAN FEEDBACK                │
              │                                       │
              │  Options:                             │
              │  • "You missed X"                     │
              │  • "Combine A and B"                  │
              │  • "Deep-dive into: Communication,    │
              │     GitHub Integration"              │
              │  • "Analyze all features deeply"      │
              └───────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PHASE 2: DEEP-DIVE ANALYSIS                   │
│                                                                  │
│  User triggers (via Slack/PR comment):                           │
│    "Deep-dive into: Communication, GitHub Integration"           │
│                                                                  │
│  For each requested category:                                    │
│  ┌──────────────────────────────────────────────────────────┐    │
│  │  Deep-Dive Agent (parallel execution)                    │    │
│  │                                                          │    │
│  │  • Read ALL files in the category (no limits)           │    │
│  │  • Extract sub-features with full detail                │    │
│  │  • Identify sub-sub-features if applicable              │    │
│  │  • Generate comprehensive documentation                  │    │
│  └──────────────────────────────────────────────────────────┘    │
│                                │                                 │
│                                ▼                                 │
│                     ┌────────────────────┐                       │
│                     │  Update FEATURES.md│                       │
│                     │  with deep details │                       │
│                     └────────────────────┘                       │
│                                │                                 │
│                                ▼                                 │
│                     ┌────────────────────┐                       │
│                     │  Open/Update PR    │                       │
│                     └────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

#### 1. Remove Artificial Limits

```python
# Current (to be removed):
MAX_DEEP_ANALYSIS_FILES = 15

# New approach:
# - No hardcoded limits on file count
# - Let agents decide what's important
# - Use streaming/chunking for large analyses
```

**Rationale**: The current limit was added for cost control, but it prevents comprehensive analysis. Better to let the LLM agents (Scout, Analyzer) decide what's worth processing, with token management handled at the prompt level.

#### 2. Two-Phase Workflow

**Phase 1: Structure Analysis**
- Identify high-level categories (e.g., "Communication", "GitHub Integration")
- List top-level features under each category
- NO deep sub-feature extraction
- Opens PR for review

**Phase 2: Deep-Dive Analysis**
- Triggered by user feedback
- Analyzes specific categories in depth
- Extracts full feature hierarchy
- Updates PR with detailed findings

#### 3. PR-Based Feedback Loop

The PR serves as the communication channel:
- Phase 1 creates a PR with high-level structure
- User reviews and comments with feedback
- JIB monitors for specific commands:
  - `/deep-dive Communication, GitHub Integration` - analyze specific categories
  - `/deep-dive all` - analyze all categories deeply
  - `/add-feature XYZ to Communication` - add missed feature
  - `/merge ABC, DEF` - combine two feature entries
- Phase 2 updates the same PR with deep-dive results

#### 4. Hierarchical Feature Structure

Support for multi-level hierarchy in FEATURES.md:

```markdown
## Communication

### 1. Slack Notifier Service
**Location:** `host-services/slack/slack-notifier/`

Host-side systemd service that monitors ~/.jib-sharing/notifications/...

**Components:**
- **Message Batching** - 15-second batching window for notifications
- **Auto-Chunking** - Splits long messages for Slack limits
- **Thread Reply Support** - YAML frontmatter for threading

### 2. Slack Receiver Service
**Location:** `host-services/slack/slack-receiver/`

Receives incoming Slack DMs via Socket Mode...

**Components:**
- **Remote Control via Slack** - /jib commands for management
- **Thread Context Preservation** - Full conversation history
- **User Authentication** - Allowlist-based access control
```

This structure already exists in the current FEATURES.md - we'll enhance it with more detail during deep-dives.

#### 5. Parallel Deep-Dive Execution

When analyzing multiple categories:
- Launch parallel agents for each category
- Each agent handles one category completely
- Results consolidated into single PR update

## Implementation Plan

### Phase 1: Remove Limits & Improve Thoroughness

**Changes:**
1. Remove `MAX_DEEP_ANALYSIS_FILES` constant
2. Update Scout agent to process ALL files without truncation
3. Add token-aware chunking for large file sets
4. Ensure Analyzer processes complete category inventories

**Files to modify:**
- `jib-container/jib-tasks/analysis/feature_analyzer.py`

### Phase 2: Implement Structure-Only Analysis Mode

**New CLI command:**
```bash
feature-analyzer analyze-structure --repo-root /path/to/repo
```

**Behavior:**
1. Run Cartographer to discover directories
2. Run Scout (root-level) on each directory
3. Run Analyzer with "structure-only" mode:
   - Extract category names
   - List top-level features (name, one-line description, location)
   - NO sub-feature extraction
   - NO documentation generation
4. Generate `HIGH_LEVEL_STRUCTURE.md`
5. Create PR with structure for review

**Files to modify:**
- `host-services/analysis/feature-analyzer/feature-analyzer.py` (add command)
- `jib-container/jib-tasks/analysis/feature_analyzer.py` (add StructureAnalyzer class)
- `jib-container/jib-tasks/analysis/analysis-processor.py` (add handler)

### Phase 3: Implement Deep-Dive Command

**New CLI command:**
```bash
feature-analyzer deep-dive --categories "Communication,GitHub Integration" --pr 123
```

**Or via PR comment:**
```
/deep-dive Communication, GitHub Integration
```

**Behavior:**
1. Load high-level structure from existing PR
2. For each requested category (parallel):
   - Read ALL files in the category
   - Extract full feature hierarchy with components
   - Generate detailed descriptions
   - Identify sub-sub-features if applicable
3. Update FEATURES.md with deep-dive results
4. Update PR with new commits

**Files to modify:**
- `host-services/analysis/feature-analyzer/feature-analyzer.py` (add command)
- `jib-container/jib-tasks/analysis/feature_analyzer.py` (add DeepDiveAnalyzer class)
- `jib-container/jib-tasks/analysis/analysis-processor.py` (add handler)

### Phase 4: PR Comment Handler

**New handler for PR comments:**
- Monitor for `/deep-dive`, `/add-feature`, `/merge` commands
- Parse command arguments
- Trigger appropriate analyzer
- Post results as PR updates

**Files to modify:**
- `jib-container/jib-tasks/github/comment-responder.py` (add command parsing)
- `host-services/analysis/github-watcher/github-watcher.py` (detect command comments)

### Phase 5: Hierarchical FEATURES.md Format

**Update format to support:**
- Multi-level nesting (Category → Feature → Component → Sub-component)
- Collapsible sections for deep details
- Cross-references between related features

**Files to modify:**
- `jib-container/jib-tasks/analysis/feature_analyzer.py` (format_feature_entry)
- `docs/FEATURES.md` (update structure)

## Open Questions

### Question 1: Token Management Strategy

**Context:** Removing file limits will increase token usage significantly.

**Options:**
A. **Chunked Analysis**: Process files in chunks, consolidate results
B. **Summary-First**: Extract signatures/docstrings first, full content only when needed
C. **Tiered Analysis**: Quick pass for all files, deep pass for important ones
D. **Budget-Based**: Set token budget, let Scout optimize within it

**Recommendation:** Option B (Summary-First) - already partially implemented with `_extract_file_summary()`. We should make this the default and only read full content when explicitly requested.

**Question for James:** Are you okay with potentially higher API costs for more thorough analysis? Should we add a `--max-tokens` flag for cost control?

### Question 2: Feedback Command Syntax

**Context:** Need a clean way for users to provide feedback via PR comments.

**Options:**
A. **Slash commands**: `/deep-dive Communication`, `/add-feature X`
B. **Natural language**: "Please deep-dive into Communication"
C. **Structured YAML**:
   ```yaml
   command: deep-dive
   categories: [Communication, GitHub Integration]
   ```
D. **GitHub Actions labels**: Add label `deep-dive:Communication`

**Recommendation:** Option A (slash commands) - familiar pattern, easy to parse, clear intent.

**Question for James:** Any preference on command syntax? Should we support natural language as well?

### Question 3: PR vs New PR for Deep-Dives

**Context:** When deep-dive results come in, should we update the existing PR or create a new one?

**Options:**
A. **Update existing PR**: Keeps all analysis together, simpler review
B. **New PR per deep-dive**: Cleaner commits, easier to review incrementally
C. **Configurable**: User chooses via flag

**Recommendation:** Option A (update existing PR) - keeps context together, avoids PR sprawl.

**Question for James:** Preference?

### Question 4: Handling Very Large Codebases

**Context:** Monoliths like webapp may have 100+ features.

**Options:**
A. **Pagination**: Split FEATURES.md into multiple files by category
B. **Single file**: One FEATURES.md with all features (current approach)
C. **Hybrid**: Main FEATURES.md with links to category-specific files

**Recommendation:** Option C (Hybrid) - FEATURES.md has overview + links, detailed files in `docs/features/`.

**Question for James:** Already have `docs/features/` with category files. Should deep-dives update those instead of main FEATURES.md?

### Question 5: james-in-a-box vs External Repos

**Context:** This design is tailored for james-in-a-box. Other repos (webapp, etc.) have different structures.

**Options:**
A. **JIB-only**: Optimize for james-in-a-box structure
B. **Configurable**: Allow repo-specific config for feature structure
C. **Auto-detect**: LLM determines appropriate structure per repo

**Recommendation:** Option C (Auto-detect) - Cartographer already does this. Extend to structure detection.

**Question for James:** Should we prioritize JIB-specific optimizations or generalize from the start?

## Consequences

### Benefits

1. **Complete Coverage**: No features missed due to artificial limits
2. **Human Oversight**: Feedback loop ensures accuracy
3. **Manageable Review**: Phased approach prevents information overload
4. **Flexible Depth**: Users control how deep to analyze
5. **Hierarchical Organization**: Matches real codebase structure

### Drawbacks

1. **Higher API Costs**: More thorough analysis = more tokens
2. **Longer Analysis Time**: Two-phase workflow takes longer overall
3. **Implementation Complexity**: More moving parts than single-pass
4. **PR Management**: Need to track state across multiple phases

### Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Token costs explode | Token-aware chunking, summary-first approach |
| Analysis takes too long | Parallel execution, progress indicators |
| User forgets to trigger deep-dive | Reminder comments on PRs after 24h |
| Deep-dive results conflict with manual edits | Merge strategy, human review |

---

**Next Steps:**
1. Review this ADR and answer open questions
2. Approve approach
3. Begin implementation Phase 1 (remove limits)

---

**Last Updated:** 2025-12-17
