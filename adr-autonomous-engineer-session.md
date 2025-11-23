# Context: ADR for LLM-Powered Autonomous Software Engineer

**Session Date**: 2025-11-23
**Status**: ADR Complete and Production-Ready
**Location**: `~/khan/james-in-a-box/ADR-Autonomous-Software-Engineer.md`

---

## What Was Accomplished

### 1. Comprehensive ADR Created (1,467 lines)

**Complete Architecture Decision Record covering:**
- **7 Core Decisions**: Docker sandbox, Slack mobile-first interface, context strategy evolution, automated analyzers, mobile-first PR workflow, deployment strategy, cultural alignment with KA engineering standards
- **Security as Priority**: Data exfiltration as PRIMARY concern with 5-layer defense strategy
- **Mobile-First Philosophy**: Engineer productivity from phone is core requirement, not future enhancement
- **Cultural Alignment**: Agent behavior aligned with Khan Academy engineering values (L3-L4 expectations)
- **Clear Evolution Path**: Phase 1 (laptop, file-based) → Phase 3 (Cloud Run, MCP/API/GCP, DLP)

### 2. Security: Data Exfiltration Comprehensively Addressed

**5-Layer Defense Strategy:**
1. **Human Review** (Phase 1 - Current) - All outputs reviewed before external sharing
2. **Context Source Filtering** (Phase 2) - Confluence/JIRA allowlists, exclude customer data
3. **Content Classification** (Phase 2) - Tag docs as Public/Internal/Confidential
4. **DLP Scanning** (Phase 3) - Cloud DLP before Claude API calls, automated redaction
5. **Output Monitoring** (Phase 3) - Scan PR descriptions, commits, Slack for leaks

**Risk Progression:**
- **Current (Phase 1)**: MEDIUM risk - Human review only, acceptable for pilot
- **Target (Phase 3)**: LOW risk - DLP + filtering + monitoring operational
- **Escalation Criteria**: DLP required before customer-facing repos, multi-engineer rollout

**Detailed Remediation Plan**: Phase-by-phase implementation with success metrics (>95% DLP detection, <5% false positives, zero leaks)

### 3. Agent Cultural Alignment - Core Architecture

**Decision #7: Agent Demeanor Aligned with Khan Academy Standards**

**Implementation:**
- `.claude/rules/khan-academy-culture.md` sources SE level expectations from Confluence
- L3-L4 behaviors: Technical excellence, clear communication, user empathy, systematic problem-solving
- Conversation analyzer evaluates cultural fit daily
- Future: Self-assessment with success metrics (>90% L3-L4 standards, >85% alignment score)

**Rationale:** Agent effectiveness depends on cultural fit, not just technical capability. Using Confluence-documented standards ensures alignment with actual org expectations.

### 4. Consistency Fixes Applied

**11 Critical Fixes:**
1. **PR creation description** - Consistently "agent creates PR, engineer reviews and merges"
2. **GitHub token terminology** - Changed "read-only" → "PR-creation-scoped" (accurate permissions)
3. **Context sync paths** - Fixed to `~/confluence-docs/` and `~/jira/` (matches implementation)
4. **GCP authentication** - Clarified service account keys (Phase 2-3 laptop) vs. Workload Identity (Phase 3 Cloud Run)
5. **Cloud Run timeline** - Consistently "Phase 3" (not "Phase 3-4")
6. **Data exfiltration phases** - Aligned: Phase 2 filtering, Phase 3 DLP
7. **Implementation Checklist Phase 2** - Added 4 missing data exfiltration items
8. **Anthropic policy verification** - Added "verify before Phase 2" deadline
9. **Cultural alignment metrics** - Added 5 measurable success criteria
10. **Escalation approval process** - Security team + leadership approval documented
11. **Decision Matrix clarity** - Renamed to "Infrastructure Deployment"

**Duplication Removed:**
- Consolidated "Data Exfiltration Concerns" section and "Risk 1" summary - Risk 1 now references detailed section

**Time Estimates Removed:**
- All month estimates removed per user request (use phases only)
- Changed "Month X-Y" → "Phase N" throughout
- Changed "Near-term (3-6 months)" → "Near-term"

---

## Key Architectural Decisions

### Security Model
- **Docker sandbox** with no credentials (SSH keys, cloud tokens, secrets excluded)
- **Network isolation**: Outbound HTTP only (Claude API, packages)
- **Human-in-the-loop**: All PRs require human merge approval
- **Data exfiltration**: 5-layer defense, MEDIUM→LOW risk progression

### Mobile-First Design
- **Core requirement** (not future enhancement)
- Engineer fully productive from phone
- Slack mobile-optimized notifications with quick actions
- Agent creates PRs, engineer reviews/merges from phone

### Context Strategy Evolution
- **Phase 1**: File-based sync (Confluence/JIRA → markdown, 15-30 min intervals)
- **Phase 2-3**: Hybrid approach - MCP servers (real-time) + APIs (bi-directional) + GCP (operational data) + files (bulk docs)
- **Rationale**: Fast MVP with clear evolution path

### Cultural Alignment
- **Confluence-sourced KA engineering standards** in `.claude/rules/khan-academy-culture.md`
- **L3-L4 behavior expectations**: Technical excellence, user empathy, systematic debugging
- **Continuous evaluation**: Conversation analyzer assesses cultural fit
- **Measurable**: >90% L3-L4 standards, >85% alignment score

### Deployment Strategy
- **Phase 1**: Laptop (pilot, fast iteration)
- **Phase 3**: Cloud Run via Terraform (Workload Identity, stateless containers, multi-engineer)

---

## Implementation Phases

### Phase 1 (Complete)
- ✅ Docker sandbox
- ✅ Slack integration
- ✅ File-based context sync
- ✅ Automated analyzers
- ✅ Mobile-accessible interface
- 🔄 Safe PR creation (in progress)

### Phase 2 (Next)
**Focus**: Enhanced security, cultural alignment, context evolution assessment

**Critical Items**:
- [ ] **Context source filtering** - Confluence/JIRA allowlists (Engineering YES, Customer support NO)
- [ ] **Document classification policy** - What's safe to send to Claude API
- [ ] **Data exfiltration monitoring** - Log all Claude API calls, weekly review
- [ ] **Engineer training** - Identify confidential content in PR/commit reviews
- [ ] **Cultural alignment** - Create `.claude/rules/khan-academy-culture.md` from Confluence
- [ ] **Conversation analyzer demeanor evaluation** - Cultural fit assessment
- [ ] **MCP server evaluation** - Real-time context assessment
- [ ] **API integration assessment** - Bi-directional updates
- [ ] **GCP service account design** - IAM policies, scoping, rotation

### Phase 3 (Planned)
**Focus**: Production hardening, Cloud Run deployment, DLP integration

**Critical Items**:
- [ ] **Cloud Run deployment** via Terraform (Workload Identity, no key files)
- [ ] **DLP integration** - Cloud DLP scanning before Claude API calls
- [ ] **Automated redaction** - PII, API keys, sensitive patterns
- [ ] **Output monitoring** - Scan PR descriptions, commits, Slack before posting
- [ ] **Hybrid context strategy** - MCP + files + GCP operational

### Phase 4 (Future)
- Cross-repo awareness
- Advanced autonomous capabilities
- CI/CD integration
- Self-service onboarding

---

## Immediate Actions Required (Phase 1)

**Before Phase 2 Rollout:**

1. **Document acceptable context sources** ← DO THIS FIRST
   - Confluence: Engineering ADRs YES, Customer contracts NO
   - JIRA: Internal engineering YES, Customer support NO
   - Code: Internal tools YES, Payment processing NO

2. **Verify Anthropic security policies**
   - Data handling (no training on API data?)
   - Data retention (30 days?)
   - Document findings before Phase 2

3. **Engineer training program**
   - Checklist: How to identify confidential content
   - What to look for in PR descriptions
   - When to reject agent output

4. **Monitoring baseline**
   - Log all Claude API calls (timestamp, prompt size, context sources)
   - Track which Confluence/JIRA docs included
   - Weekly manual log review

5. **Create `.claude/rules/khan-academy-culture.md`**
   - Extract SE level expectations from Confluence (L3, L4, L5)
   - Document KA engineering values
   - Technical excellence, communication, problem-solving, collaboration standards

---

## Decision Matrix Summary

| Area | Chosen Approach | Key Rationale |
|------|----------------|---------------|
| **Execution Environment** | Docker sandbox, no credentials | Security, isolation, safe experimentation |
| **LLM Provider** | Anthropic Claude | Code quality, context window, safety |
| **User Interface** | Slack mobile-first | Where engineers are, excellent mobile support |
| **Context Integration** | File-based (Phase 1) → API/MCP/GCP (Phase 2-3) | Fast MVP, scalable to real-time |
| **PR Creation** | Agent creates, human merges | Balance automation and safety, mobile productivity |
| **Infrastructure Deployment** | Laptop (Phase 1), Cloud Run (Phase 3) | Fast MVP, scales cloud-native |
| **Cultural Alignment** | Confluence-sourced KA standards | Behavior aligns with org values |

---

## Security Risks & Mitigations

**Risk 1: Data Exfiltration (PRIMARY CONCERN)**
- **Threat**: Confidential Confluence/JIRA/code/GCP data leaked via PRs, commits, Slack, Claude API
- **Impact**: HIGH - Business strategies, customer data, security practices exposed
- **Current**: MEDIUM risk (human review only)
- **Target**: LOW risk (DLP + filtering + monitoring)
- **5-Layer Defense**: Human review → Source filtering → Classification → DLP → Output monitoring

**Risks 2-9**: Agent code vulnerabilities, prompt injection, GitHub token compromise, Claude API compromise, malicious context sync, supply chain attacks, GCP service account compromise, insufficient PR review

All risks have specific, concrete mitigations (not generic).

---

## Files Delivered

1. **ADR** (1,467 lines): `~/khan/james-in-a-box/ADR-Autonomous-Software-Engineer.md`
2. **Review Summary**: `~/sharing/notifications/20251123-adr-review-complete.md`
3. **Cultural Alignment Summary**: `~/sharing/notifications/20251123-adr-cultural-alignment.md`
4. **Final Summary**: `~/sharing/notifications/20251123-adr-final.md`

---

## Production Readiness

**Status**: ✅ **PRODUCTION-READY**

The ADR is:
- ✅ Consistent (11 critical fixes applied, no contradictions)
- ✅ Well-justified (all decisions have rationale and alternatives)
- ✅ Comprehensive (security, mobile, culture all covered)
- ✅ Actionable (implementation checklist ready)
- ✅ Measurable (success metrics defined: >95% DLP, >85% cultural fit)

**Ready for:**
- Engineering leadership review
- Security team review
- Stakeholder approval
- Phase 2 implementation kickoff

---

## Key Learnings

### What Worked Well
1. **Security-first approach** - Data exfiltration addressed comprehensively from the start
2. **Mobile-first as core** - Not future enhancement, integrated throughout
3. **Cultural alignment** - Agent demeanor as architectural decision
4. **Phase-based evolution** - Clear progression from MVP to production
5. **Measurable success** - Concrete metrics, not vague goals

### Critical Success Factors
1. **Context source filtering** - Must define acceptable sources before Phase 2
2. **DLP before scale** - Required before customer-facing repos or multi-engineer
3. **Cultural fit** - KA standards integration ensures adoption
4. **Human-in-the-loop** - Safety without blocking productivity
5. **Mobile productivity** - Engineer satisfaction and adoption

---

## Next Steps

**For Phase 2 Kickoff:**
1. Review ADR with engineering leadership
2. Review with security team (especially data exfiltration section)
3. Document acceptable context sources (allowlists)
4. Create `.claude/rules/khan-academy-culture.md` from Confluence
5. Set up data exfiltration monitoring baseline
6. Verify Anthropic data handling policies
7. Begin engineer training program

**This context document provides everything needed to continue the project with full context.**
