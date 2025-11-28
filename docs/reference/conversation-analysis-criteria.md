# Conversation Analysis Criteria

> Reference document defining assessment criteria for the conversation analyzer.
> Used to evaluate agent performance against Khan Academy L3-L4 standards.

## Assessment Dimensions

### 1. Technical Communication Quality

| Level | Characteristics |
|-------|-----------------|
| **Excellent (L4)** | Clear explanations adjusted for audience, identifies core issues, explains "why" |
| **Good (L3)** | Clear documentation, asks clarifying questions, concise writing |
| **Needs Improvement** | Vague explanations, assumes context, missing rationale |
| **Red Flags** | Incorrect info stated confidently, ignoring questions, defensive |

### 2. Problem-Solving Approach

| Level | Characteristics |
|-------|-----------------|
| **Excellent (L4)** | Systematic breakdown, data-driven solutions, early risk identification |
| **Good (L3)** | Uses data and docs, strong root cause analysis, learns from mistakes |
| **Needs Improvement** | Treats symptoms, doesn't use available data, repeats mistakes |
| **Red Flags** | Guessing instead of investigating, ignoring ADRs, knowingly adding debt |

### 3. User Empathy & Impact Focus

| Level | Characteristics |
|-------|-----------------|
| **Excellent (L4)** | Considers learner/educator impact, uses user research, sees big picture |
| **Good (L3)** | Understands work scope and impact, considers diverse use cases |
| **Needs Improvement** | Technical focus over user value, ignores accessibility/performance |
| **Red Flags** | Dismissing user feedback, prioritizing cleverness over usability |

### 4. Inclusive Collaboration

| Level | Characteristics |
|-------|-----------------|
| **Excellent (L4)** | Seeks diverse opinions, gives credit, encourages cross-team engagement |
| **Good (L3)** | Encourages open communication, listens respectfully |
| **Needs Improvement** | Assumes one approach is best, doesn't acknowledge contributions |
| **Red Flags** | Dismissive of stakeholders, taking credit for others' ideas |

### 5. Code Quality & Long-Term Thinking

| Level | Characteristics |
|-------|-----------------|
| **Excellent (L4)** | Detailed planning, robust solutions, proactively reduces friction |
| **Good (L3)** | Builds for long term, uses quality tools, modernizes code |
| **Needs Improvement** | Quick fixes, skipping tests, not following patterns |
| **Red Flags** | Security vulnerabilities, copy-paste without understanding, no tests |

### 6. Autonomy & Judgment

| Level | Characteristics |
|-------|-----------------|
| **Excellent (L4)** | Leads complex solutions, excellent escalation judgment |
| **Good (L3)** | Works independently, knows when to ask for help |
| **Needs Improvement** | Needs hand-holding, or never asks for help when stuck |
| **Red Flags** | Architectural decisions without consultation, ignoring guidance |

## Scoring

- **5 - Excellent (L4+)**: Exceeds L3-L4 expectations
- **4 - Strong (L4)**: Meets L4 expectations
- **3 - Good (L3-L4)**: Target range
- **2 - Developing**: Below L3 level
- **1 - Needs Improvement**: Significant gaps

**Target Range:** 3.0-4.0 overall average

## Positive Indicators

- Problem decomposition with todo lists
- Status updates during long tasks
- References ADRs and documentation
- Mentions testing approach
- Connects work to user impact
- Acknowledges uncertainty

## Negative Indicators

- Vague error reports
- No status updates
- Jumping to solutions without analysis
- No mention of testing
- Missing user focus
- Making major decisions without asking

---
*This is reference material used by the conversation analyzer.*
*See [docs/index.md](../index.md) for navigation.*
