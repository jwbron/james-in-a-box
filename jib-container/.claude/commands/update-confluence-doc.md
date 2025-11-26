# Claude Command: Update Confluence Document

**Command**: `/update-confluence-doc <path-to-document>`

**Examples**:
- `/update-confluence-doc ~/context-sync/confluence/ENG/ADRs/ADR-123.md`
- `/update-confluence-doc ADR #895`

## Purpose

Helps iterate on Confluence documentation by:
1. Reading the original document (including synced comments)
2. Identifying feedback from inline/footer comments
3. Generating a "Changed Sections Only" document formatted for Confluence

## Workflow Steps

### 1. Locate the Document

If user provides:
- **Full path**: Use directly
- **Document name/number**: Search in `~/context-sync/confluence/`

```bash
# Search for document
find ~/context-sync/confluence -name "*<search-term>*" -type f
```

### 2. Read the Document

Read the full document including any comments section at the end.

**Look for**:
- Main content sections
- `## Comments` or `## Inline Comments` section (added by context-sync)
- Comment metadata (author, date, location)

### 3. Analyze Comments/Feedback

For each comment found:
1. Identify what section it references
2. Understand the feedback or question
3. Determine if it requires:
   - New section addition
   - Modification to existing section
   - Clarification of existing content

### 4. Generate Changed Sections Document

Create output at `~/sharing/<Document Name> - Changed Sections Only.md`

**File structure**:
```markdown
# <Document Name>: Changed Sections Only

Instructions: Copy each section below into the corresponding location in Confluence.

---

## NEW SECTION: Add after "<Section Name>"

<Content formatted for Confluence>

---

## MODIFIED: Replace "<Section Name>"

<Updated content formatted for Confluence>

---

## Integrated Feedback Summary

The following feedback has been integrated from comments:

1. **<Topic>** (Comment N): <What was added/changed>
2. ...
```

### 5. Apply Confluence Formatting Rules

When generating content, apply these rules:

**Links** - Use bare URLs:
```markdown
# Don't
See [Documentation](https://example.com/docs)

# Do
See: https://example.com/docs
```

**Tables** - Use `| --- |` separator:
```markdown
| Column 1 | Column 2 |
| --- | --- |
| Value 1 | Value 2 |
```

**Lists** - No blank lines between items:
```markdown
- Item 1
- Item 2
- Item 3
```

**Code blocks** - Triple backticks with language:
```markdown
```python
def example():
    pass
```
```

### 6. Report Results

After generating the document:

```
Created: ~/sharing/<Document Name> - Changed Sections Only.md

Integrated feedback from N comments:
- <Summary of changes>

To update Confluence:
1. Open the page in Confluence
2. Copy each section from the generated file
3. Paste into the corresponding location
4. Review formatting and save
```

## Example Output

```markdown
# ADR #895: Changed Sections Only

Instructions: Copy each section below into the corresponding location in Confluence.

---

## NEW SECTION: Add after "Background"

### Clarification: Boot Time vs. Runtime

**Boot time** means during application startup - specifically:
- **Go services**: In `main()` or during package initialization
- **TypeScript/JavaScript**: At module import time

**Runtime** means during request handling or after startup.

---

## MODIFIED: Replace "Key Requirements"

### Key Requirements

1. **Deployability**: Same container image can deploy to any GCP project without rebuilding
2. **Simplicity**: Configuration is immutable after boot
3. **Flexibility**: Support both shared and isolated resources

---

## Integrated Feedback Summary

1. **Boot vs Runtime** (Comment 2): Added clarification section
2. **Deployability** (Comment 14): Updated requirement wording
```

## Notes

- Always preserve the original document structure
- Group related changes together
- Include a summary of what feedback was addressed
- The human will copy-paste sections into Confluence manually
- If no comments exist, ask user what changes they want to make
