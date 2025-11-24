#!/usr/bin/env python3
"""
Confluence Watcher - Monitors Confluence documentation changes

Detects new or updated Confluence documents (especially ADRs), summarizes
changes, identifies impact on current work, and sends notifications.

Focus: ADRs, runbooks, and engineering documentation
"""

import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class ConfluenceWatcher:
    def __init__(self):
        self.confluence_dir = Path.home() / "context-sync" / "confluence"
        self.notifications_dir = Path.home() / "sharing" / "notifications"
        self.beads_dir = Path.home() / "beads"

        # Track which documents we've already notified about
        self.state_file = Path.home() / "sharing" / "tracking" / "confluence-watcher-state.json"
        self.processed_docs = self.load_state()

    def load_state(self) -> Dict:
        """Load previously processed documents with their last modified times"""
        import json
        if self.state_file.exists():
            try:
                with self.state_file.open() as f:
                    return json.load(f)
            except:
                pass
        return {'processed': {}}

    def save_state(self):
        """Save processed document state"""
        import json
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.state_file.open('w') as f:
            json.dump({'processed': self.processed_docs}, f, indent=2)

    def watch(self):
        """Main watch loop - check for new or updated documents"""
        if not self.confluence_dir.exists():
            print("Confluence directory not found - skipping watch")
            return

        # Focus on high-value documents
        # 1. ADRs (most important)
        # 2. Runbooks
        # 3. Engineering docs

        adr_files = list(self.confluence_dir.rglob("*ADR*.md")) + list(self.confluence_dir.rglob("*adr*.md"))
        runbook_files = list(self.confluence_dir.rglob("*unbook*.md")) + list(self.confluence_dir.rglob("*RUNBOOK*.md"))

        # Process ADRs first (highest priority)
        for doc_file in adr_files[:10]:  # Limit to avoid spam
            try:
                self.process_document(doc_file, doc_type='ADR')
            except Exception as e:
                print(f"Error processing {doc_file}: {e}")

        # Then runbooks
        for doc_file in runbook_files[:5]:
            try:
                self.process_document(doc_file, doc_type='Runbook')
            except Exception as e:
                print(f"Error processing {doc_file}: {e}")

    def process_document(self, doc_file: Path, doc_type: str = 'Document'):
        """Process a single Confluence document"""
        # Get file modification time
        try:
            mtime = doc_file.stat().st_mtime
            mtime_str = datetime.fromtimestamp(mtime).isoformat()
        except:
            return

        doc_path_str = str(doc_file)

        # Check if this is new or updated
        if doc_path_str in self.processed_docs:
            last_seen = self.processed_docs[doc_path_str]
            if last_seen == mtime_str:
                return  # No changes

        print(f"New or updated {doc_type}: {doc_file.name}")

        # Determine if new or updated
        is_new = doc_path_str not in self.processed_docs

        # Parse and analyze document
        doc = self.parse_document(doc_file, doc_type)
        if not doc:
            return

        analysis = self.analyze_document(doc, doc_type)

        # Only create Beads task for ADRs or if action is required
        beads_id = None
        if doc_type == 'ADR' and is_new:
            beads_id = self.create_beads_task(doc, analysis)

        # Send notification
        self.create_notification(doc, analysis, is_new, beads_id, doc_type)

        # Mark as processed
        self.processed_docs[doc_path_str] = mtime_str
        self.save_state()

    def parse_document(self, doc_file: Path, doc_type: str) -> Optional[Dict]:
        """Parse Confluence document"""
        try:
            with doc_file.open() as f:
                content = f.read()

            doc = {
                'file': doc_file,
                'name': doc_file.name,
                'type': doc_type,
                'title': '',
                'content': content,
                'summary': '',
                'sections': []
            }

            lines = content.split('\n')

            # Extract title (first h1)
            for line in lines:
                if line.startswith('# '):
                    doc['title'] = line.replace('#', '').strip()
                    break

            if not doc['title']:
                doc['title'] = doc_file.stem

            # Extract first few lines as summary
            content_lines = [l for l in lines if l.strip() and not l.startswith('#')]
            if content_lines:
                doc['summary'] = ' '.join(content_lines[:3])[:300]

            return doc

        except Exception as e:
            print(f"Error parsing document {doc_file}: {e}")
            return None

    def analyze_document(self, doc: Dict, doc_type: str) -> Dict:
        """Analyze document and extract insights"""
        analysis = {
            'key_points': [],
            'impact': '',
            'action_required': False,
            'related_work': [],
            'changes_detected': []
        }

        content = doc['content'].lower()
        title = doc['title'].lower()

        # Detect if this is an ADR
        if doc_type == 'ADR' or 'adr' in title:
            analysis['impact'] = 'Architecture Decision Record - may affect implementation approach'

            # Extract decision keywords
            decision_keywords = ['decided', 'approved', 'recommend', 'must', 'should', 'required']
            for keyword in decision_keywords:
                if keyword in content:
                    analysis['key_points'].append(f"Decision keyword found: {keyword}")

            # Check for deprecation/migration
            if any(word in content for word in ['deprecate', 'migration', 'replace', 'sunset']):
                analysis['action_required'] = True
                analysis['changes_detected'].append("Contains deprecation or migration plans")

            # Check for new patterns/standards
            if any(word in content for word in ['pattern', 'standard', 'guideline', 'best practice']):
                analysis['key_points'].append("Defines new patterns or standards")

        # Detect if this relates to current work (check for common terms)
        tech_keywords = ['terraform', 'kubernetes', 'docker', 'python', 'typescript', 'react',
                        'api', 'database', 'redis', 'postgres', 'gcp', 'aws']
        mentioned_tech = [tech for tech in tech_keywords if tech in content]
        if mentioned_tech:
            analysis['related_work'] = mentioned_tech[:5]

        # Check for action items
        if any(word in content for word in ['todo', 'action item', 'must do', 'need to']):
            analysis['action_required'] = True

        return analysis

    def create_beads_task(self, doc: Dict, analysis: Dict) -> Optional[str]:
        """Create Beads task for ADR review"""
        try:
            result = subprocess.run(['which', 'beads'], capture_output=True)
            if result.returncode != 0:
                return None

            title = f"Review ADR: {doc['title'][:60]}"

            result = subprocess.run(
                ['beads', 'add', title, '--tags', 'adr', 'confluence', 'documentation'],
                cwd=self.beads_dir,
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if 'Created' in output and 'bd-' in output:
                    bead_id = output.split('bd-')[1].split(':')[0]
                    bead_id = f"bd-{bead_id.split()[0]}"

                    notes = f"ADR: {doc['title']}\n"
                    notes += f"File: {doc['file'].name}\n"
                    if analysis['related_work']:
                        notes += f"Related tech: {', '.join(analysis['related_work'])}"

                    subprocess.run(
                        ['beads', 'update', bead_id, '--notes', notes],
                        cwd=self.beads_dir,
                        capture_output=True
                    )

                    print(f"  ✓ Created Beads task: {bead_id}")
                    return bead_id
        except Exception as e:
            print(f"  Could not create Beads task: {e}")

        return None

    def create_notification(self, doc: Dict, analysis: Dict, is_new: bool, beads_id: Optional[str], doc_type: str):
        """Create Slack notification for document change"""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        doc_name = doc['file'].stem.replace(' ', '-')[:50]
        notif_type = "new" if is_new else "updated"
        notif_file = self.notifications_dir / f"{timestamp}-confluence-{notif_type}-{doc_name}.md"

        with notif_file.open('w') as f:
            emoji = "📘" if doc_type == 'ADR' else "📄"
            action = "New" if is_new else "Updated"
            f.write(f"# {emoji} {action} {doc_type}: {doc['title']}\n\n")

            f.write(f"**Type**: {doc_type}\n")
            f.write(f"**File**: `{doc['file'].name}`\n")
            if beads_id:
                f.write(f"**Beads Task**: {beads_id}\n")
            f.write("\n")

            # Summary
            if doc.get('summary'):
                f.write("## 📝 Summary\n\n")
                f.write(f"{doc['summary']}\n\n")

            # Impact
            if analysis['impact']:
                f.write("## 💡 Impact\n\n")
                f.write(f"{analysis['impact']}\n\n")

            # Key Points
            if analysis['key_points']:
                f.write("## 🎯 Key Points\n\n")
                for point in analysis['key_points']:
                    f.write(f"- {point}\n")
                f.write("\n")

            # Related Technologies
            if analysis['related_work']:
                f.write("## 🔧 Related Technologies\n\n")
                tech_str = ', '.join(analysis['related_work'])
                f.write(f"This document mentions: {tech_str}\n\n")

            # Changes Detected
            if analysis['changes_detected']:
                f.write("## ⚠️ Important Changes\n\n")
                for change in analysis['changes_detected']:
                    f.write(f"- {change}\n")
                f.write("\n")

            # Action Required
            if analysis['action_required']:
                f.write("## ⚡ Action Required\n\n")
                f.write("This document contains action items or changes that may require your attention.\n")
                f.write("Review the full document to understand required actions.\n\n")

            # Next Steps
            f.write("## 📋 Suggested Next Steps\n\n")
            if doc_type == 'ADR':
                f.write("1. Read the ADR to understand the architectural decision\n")
                f.write("2. Consider how this affects current and future work\n")
                f.write("3. Update implementation approach if needed\n")
                f.write("4. Discuss with team if clarification needed\n")
            else:
                f.write("1. Review the document for relevant information\n")
                f.write("2. Note any changes to processes or patterns\n")
                f.write("3. Update current work if affected\n")

            f.write("\n")
            f.write(f"**Full document**: `{doc['file']}`\n\n")

            f.write("---\n")
            f.write(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📂 Confluence {doc_type}\n")

        print(f"  ✓ Created notification: {notif_file.name}")


def main():
    """Main entry point"""
    watcher = ConfluenceWatcher()
    watcher.watch()


if __name__ == '__main__':
    main()
