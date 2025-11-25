"""
Confluence documentation sync script.

Downloads Confluence pages with view-formatted content and hierarchical structure for optimal readability and LLM indexing.
"""

import os
import json
import requests
import base64
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urljoin, quote
import re
from datetime import datetime
import hashlib
import pickle

from connectors.confluence.config import ConfluenceConfig


class ConfluenceSync:
    """Sync Confluence pages to local files with view-formatted content and hierarchical structure for optimal readability and LLM indexing."""
    
    def __init__(self):
        self.config = ConfluenceConfig()
        self.session = requests.Session()
        self._setup_auth()
        self.sync_state_file = Path(self.config.OUTPUT_DIR) / ".sync_state"
        
    def _setup_auth(self):
        """Setup authentication for Confluence API."""
        if not self.config.validate():
            raise ValueError(
                "Missing required configuration. Please set CONFLUENCE_BASE_URL, "
                "CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN, and CONFLUENCE_SPACE_KEYS"
            )
        
        # Use Basic auth with email:token for Confluence Cloud
        import base64
        auth_string = f"{self.config.USERNAME}:{self.config.API_TOKEN}"
        auth_bytes = auth_string.encode('ascii')
        auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
        
        self.session.headers.update({
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def _load_sync_state(self) -> Dict:
        """Load sync state from file."""
        if self.sync_state_file.exists():
            try:
                with open(self.sync_state_file, 'rb') as f:
                    return pickle.load(f)
            except:
                pass
        return {}
    
    def _save_sync_state(self, state: Dict):
        """Save sync state to file."""
        self.sync_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sync_state_file, 'wb') as f:
            pickle.dump(state, f)
    
    def _get_page_hash(self, page: Dict) -> str:
        """Generate hash for page content."""
        # Handle different version field structures in API v2
        page_id = page.get('id', '')
        version_info = page.get('version', {})

        if isinstance(version_info, dict):
            version_number = version_info.get('number', '')
            version_when = version_info.get('when', '')
        else:
            # Fallback if version is not a dict
            version_number = str(version_info) if version_info else ''
            version_when = ''

        content = f"{page_id}_{version_number}_{version_when}"
        return hashlib.md5(content.encode()).hexdigest()

    def _get_comments_hash(self, comments: List[Dict]) -> str:
        """Generate hash for comments to detect changes."""
        if not comments:
            return ""
        # Hash based on comment IDs and their version numbers
        comment_data = []
        for comment in comments:
            comment_id = comment.get('id', '')
            version_info = comment.get('version', {})
            version_num = version_info.get('number', '') if isinstance(version_info, dict) else ''
            comment_data.append(f"{comment_id}:{version_num}")
        content = "|".join(sorted(comment_data))
        return hashlib.md5(content.encode()).hexdigest()
    
    def get_space_info(self, space_key: str) -> Optional[Dict]:
        """Get space information including ID from space key."""
        try:
            # First try to get space by key
            url = f"{self.config.BASE_URL}/api/v2/spaces"
            params = {
                'keys': space_key,
                'limit': 1
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            spaces = data.get('results', [])
            
            if spaces:
                return spaces[0]
            else:
                print(f"Space with key '{space_key}' not found")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Error fetching space info for {space_key}: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem while preserving readability."""
        # Only remove characters that are truly problematic for filesystems
        # Keep spaces for better readability and LLM indexing
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove control characters
        filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
        # Trim whitespace and limit length
        filename = filename.strip()
        return filename[:200]  # Limit length
    
    def get_page_ancestors_from_parentid(self, page: Dict, page_lookup: Dict[str, Dict]) -> List[Dict]:
        """Get ancestors of a page using parentId chain from the page lookup."""
        ancestors = []
        current_page = page
        
        # Walk up the parent chain
        while current_page.get('parentId'):
            parent_id = current_page['parentId']
            parent_page = page_lookup.get(parent_id)
            
            if parent_page:
                ancestors.insert(0, parent_page)  # Insert at beginning to maintain order
                current_page = parent_page
                print(f"      Found parent: {parent_page.get('title', 'Unknown')} (ID: {parent_id})")
            else:
                print(f"      Parent page {parent_id} not found in current page set, stopping hierarchy walk")
                break
        
        return ancestors
    
    def _build_page_path(self, page_title: str, ancestors: List[Dict]) -> Path:
        """Build the full path for a page including its hierarchy."""
        # Build path from ancestors (excluding space home page)
        path_parts = []
        
        # Add ancestor titles to path, but skip the space home page
        for ancestor in ancestors:
            ancestor_title = ancestor.get('title', '')
            if ancestor_title and not ancestor_title.endswith('Home'):  # Skip typical space home pages
                sanitized_title = self._sanitize_filename(ancestor_title)
                if sanitized_title:
                    path_parts.append(sanitized_title)
                    print(f"        → {sanitized_title}/")
            else:
                print(f"        ✗ Skipped: {ancestor_title} (home page or empty)")
        
        # Add the current page title
        sanitized_title = self._sanitize_filename(page_title)
        if sanitized_title:
            path_parts.append(sanitized_title + '.html')
        
        return Path(*path_parts) if path_parts else Path(sanitized_title + '.html')

    def get_pages_in_space(self, space_key: str) -> List[Dict]:
        """Get all pages in a Confluence space using v2 API."""
        # First get the space ID from the space key
        space_info = self.get_space_info(space_key)
        if not space_info:
            print(f"Could not find space with key: {space_key}")
            return []
        
        space_id = space_info.get('id')
        space_name = space_info.get('name', space_key)
        
        print(f"Found space: {space_name} (ID: {space_id})")
        
        pages = []
        cursor = None
        limit = 50
        page_count = 0
        
        while True:
            # Use space ID instead of space key for the pages endpoint
            url = f"{self.config.BASE_URL}/api/v2/spaces/{space_id}/pages"
            params = {
                'limit': limit
            }
            if cursor:
                params['cursor'] = cursor
            
            try:
                response = self.session.get(url, params=params)
                response.raise_for_status()
                
                data = response.json()
                new_pages = data.get('results', [])
                pages.extend(new_pages)
                page_count += 1
                
                print(f"  Fetched page {page_count}: {len(new_pages)} pages (total: {len(pages)})")
                
                # Check for next page using cursor-based pagination
                if '_links' in data and 'next' in data['_links']:
                    next_url = data['_links']['next']
                    if 'cursor=' in next_url:
                        cursor = next_url.split('cursor=')[1].split('&')[0]
                    else:
                        break
                else:
                    break
                    
                # Check if we've hit the limit
                if self.config.MAX_PAGES != float('inf') and len(pages) >= self.config.MAX_PAGES:
                    print(f"  Reached limit of {self.config.MAX_PAGES} pages")
                    break
                    
            except requests.exceptions.RequestException as e:
                print(f"Error fetching pages from space {space_key} (ID: {space_id}): {e}")
                break
        
        print(f"Total pages found: {len(pages)}")
        if self.config.MAX_PAGES != float('inf'):
            return pages[:self.config.MAX_PAGES]
        return pages
    
    def get_page_by_id(self, page_id: str) -> Optional[Dict]:
        """Get page metadata by ID using v2 API."""
        url = f"{self.config.BASE_URL}/api/v2/pages/{page_id}"
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching page {page_id}: {e}")
            return None

    def get_page_content(self, page_id: str) -> Optional[str]:
        """Get page content in view format using v2 API."""
        # Use the correct API endpoint as per Atlassian documentation
        url = f"{self.config.BASE_URL}/api/v2/pages/{page_id}"
        params = {
            'body-format': 'view'
        }
        
        try:
            # Add timeout to prevent hanging
            response = self.session.get(url, params=params, timeout=30)
            
            # Check for rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', '60')
                print(f"      Rate limited! Waiting {retry_after} seconds...")
                import time
                time.sleep(int(retry_after))
                # Retry once after rate limit
                response = self.session.get(url, params=params, timeout=30)
            
            response.raise_for_status()
            
            data = response.json()
            content = data.get('body', {}).get('view', {}).get('value', '')
            
            # Return view-formatted content for optimal readability and LLM indexing
            return content
            
        except requests.exceptions.Timeout:
            print(f"      Timeout fetching page {page_id}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"      Failed to get page {page_id}: {e}")
            if hasattr(e.response, 'status_code'):
                print(f"      Status code: {e.response.status_code}")
            return None

    def get_page_comments(self, page_id: str) -> List[Dict]:
        """Get all comments (footer + inline) for a page using v2 API."""
        all_comments = []

        # Fetch both footer comments and inline comments
        comment_endpoints = [
            ('footer', f"{self.config.BASE_URL}/api/v2/pages/{page_id}/footer-comments?body-format=storage"),
            ('inline', f"{self.config.BASE_URL}/api/v2/pages/{page_id}/inline-comments?body-format=storage"),
        ]

        for comment_type, url in comment_endpoints:
            try:
                # Fetch all comments with pagination
                while url:
                    response = self.session.get(url, timeout=30)

                    # Check for rate limiting
                    if response.status_code == 429:
                        retry_after = response.headers.get('Retry-After', '60')
                        print(f"      Rate limited! Waiting {retry_after} seconds...")
                        import time
                        time.sleep(int(retry_after))
                        response = self.session.get(url, timeout=30)

                    response.raise_for_status()
                    data = response.json()

                    # Add comments from this page, tagging with type
                    for comment in data.get('results', []):
                        comment['_comment_type'] = comment_type
                        all_comments.append(comment)

                    # Check for next page
                    next_link = data.get('_links', {}).get('next')
                    url = f"{self.config.BASE_URL}{next_link}" if next_link else None

            except requests.exceptions.RequestException as e:
                print(f"      Failed to get {comment_type} comments for page {page_id}: {e}")

        return all_comments

    def format_comments(self, comments: List[Dict]) -> str:
        """Format comments for inclusion in page output."""
        if not comments:
            return ""

        formatted = "\n\n---\n\n## Comments\n\n"

        for i, comment in enumerate(comments, 1):
            # Get comment author
            author_name = comment.get('authorId', 'Unknown')
            version_info = comment.get('version', {})
            comment_type = comment.get('_comment_type', 'footer')

            # Get created date
            created_at = version_info.get('createdAt', 'Unknown date')

            # Get comment body (try storage format first, then view for compatibility)
            body_data = comment.get('body', {})
            body = body_data.get('storage', {}).get('value', '') or body_data.get('view', {}).get('value', '')

            # Convert to markdown if configured
            if self.config.OUTPUT_FORMAT == 'markdown' and body:
                body = self.convert_html_to_markdown(body)

            type_label = f"[{comment_type}] " if comment_type == 'inline' else ""
            formatted += f"### Comment {i} {type_label}- {author_name} ({created_at})\n\n"
            formatted += f"{body}\n\n"

        return formatted

    def convert_html_to_markdown(self, html_content: str) -> str:
        """Convert HTML content to Markdown format."""
        try:
            import html2text
        except ImportError:
            print("Warning: html2text not installed. Install with: pip install html2text")
            return html_content

        # Configure html2text for Confluence content
        h = html2text.HTML2Text()
        h.body_width = 0  # Don't wrap lines
        h.protect_links = True  # Preserve link formatting
        h.unicode_snob = True  # Use unicode
        h.images_to_alt = False  # Keep image links
        h.single_line_break = False  # Standard markdown line breaks

        # Convert and clean up
        markdown = h.handle(html_content)

        # Basic cleanup for Confluence artifacts
        import re
        markdown = re.sub(r'\n\n\n+', '\n\n', markdown)  # Remove extra blank lines

        return markdown.strip()

    def extract_page_id_from_url(self, url: str) -> Optional[str]:
        """Extract page ID from Confluence URL."""
        import re
        # Classic format: /pages/viewpage.action?pageId=12345
        match = re.search(r'[?&]pageId=(\d+)', url)
        if match:
            return match.group(1)
        # New format: /wiki/spaces/SPACE/pages/12345/Title
        match = re.search(r'/pages/(\d+)(?:/|$)', url)
        if match:
            return match.group(1)
        return None
    
    def _build_relative_index_path(self, current_dir: Path, target_file: Path) -> str:
        """Build a relative path from current directory to target file for index links."""
        try:
            relative_path = target_file.relative_to(current_dir)
            return str(relative_path)
        except ValueError:
            # If we can't make it relative, use the filename
            return target_file.name

    def _create_directory_index(self, directory: Path, space_key: str) -> None:
        """Create an index file for a directory showing its contents."""
        if not directory.exists():
            return
            
        index_content = f"# {directory.name} Documentation\n\n"
        
        # List subdirectories
        subdirs = [d for d in directory.iterdir() if d.is_dir()]
        if subdirs:
            index_content += "## Subdirectories\n\n"
            for subdir in sorted(subdirs):
                index_content += f"- [{subdir.name}/]({subdir.name}/README.md)\n"
            index_content += "\n"
        
        # List content files (excluding README.md)
        content_files = [f for f in directory.iterdir() if f.suffix in ['.html', '.md'] and f.name != 'README.md']
        if content_files:
            index_content += "## Pages\n\n"
            for content_file in sorted(content_files):
                page_name = content_file.stem
                index_content += f"- [{page_name}]({content_file.name})\n"
        
        # Write index
        index_file = directory / 'README.md'
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(index_content)

    def sync_space(self, space_key: str, incremental: bool = True):
        """Sync all pages from a Confluence space with hierarchical directory structure.
        
        Creates .html files for page content and .md files for directory navigation indexes.
        """
        print(f"Syncing space: {space_key}")
        
        # Create output directory
        output_dir = Path(self.config.OUTPUT_DIR) / space_key
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load sync state for incremental sync
        sync_state = self._load_sync_state() if incremental else {}
        space_state = sync_state.get(space_key, {})
        
        # Get all pages
        pages = self.get_pages_in_space(space_key)
        print(f"Found {len(pages)} pages in space {space_key}")
        
        updated_pages = 0
        new_pages = 0
        created_directories = set()
        all_files = []  # Track all created files for main index
        
        # Build a lookup map of all pages by ID for hierarchy resolution
        page_lookup = {page['id']: page for page in pages}
        print(f"Built page lookup with {len(page_lookup)} pages")
        
        for page in pages:
            page_id = page['id']
            page_title = page['title']
            page_url = f"{self.config.BASE_URL}/pages/viewpage.action?pageId={page_id}"
            page_hash = self._get_page_hash(page)
            
            # Show page processing info
            print(f"  Processing: {page_title}")
            if 'parentId' in page and page['parentId']:
                print(f"    Parent ID: {page['parentId']}")
            else:
                print(f"    No parent (root page)")
            
            # Build hierarchical path using parentId chain
            print(f"    Building hierarchy...")
            ancestors = self.get_page_ancestors_from_parentid(page, page_lookup)
            print(f"      Found {len(ancestors)} ancestors for '{page_title}'")
            
            relative_path = self._build_page_path(page_title, ancestors)
            # Adjust file extension based on configured output format
            if self.config.OUTPUT_FORMAT == 'markdown':
                relative_path = relative_path.with_suffix('.md')
            filepath = output_dir / relative_path
            
            # Show final path being created
            if len(relative_path.parts) > 1:
                print(f"    → Final path: {relative_path}")
            else:
                print(f"    → Root file: {relative_path}")
            
            # Track directory for index creation
            file_dir = filepath.parent
            created_directories.add(file_dir)
            all_files.append(filepath)

            # Always fetch comments to check for changes (lightweight API call)
            print(f"    Fetching comments for page {page_id}...")
            comments = self.get_page_comments(page_id)
            comments_hash = self._get_comments_hash(comments)
            if comments:
                print(f"    Found {len(comments)} comment(s)")

            # Get stored state for this page
            stored_state = space_state.get(page_id, {})
            if isinstance(stored_state, str):
                # Migrate old format (just page hash) to new format
                stored_state = {'page_hash': stored_state, 'comments_hash': ''}

            stored_page_hash = stored_state.get('page_hash', '')
            stored_comments_hash = stored_state.get('comments_hash', '')

            # Check if page content or comments have changed
            page_changed = (page_hash != stored_page_hash)
            comments_changed = (comments_hash != stored_comments_hash)

            if incremental and not page_changed and not comments_changed:
                print(f"  - {page_title} (no changes)")
                continue

            # Determine what changed for logging
            change_reasons = []
            if page_changed:
                change_reasons.append("content")
            if comments_changed:
                change_reasons.append("comments")

            # Get page content (only if page changed, otherwise read from existing file)
            if page_changed or not filepath.exists():
                print(f"    Fetching content for page {page_id}...")
                content = self.get_page_content(page_id)
                if content is None:
                    print(f"    Failed to get content for {page_title}, skipping")
                    continue
                print(f"    Content fetched successfully ({len(content)} characters)")

                # Convert to markdown if configured
                if self.config.OUTPUT_FORMAT == 'markdown':
                    print(f"    Converting to Markdown format...")
                    content = self.convert_html_to_markdown(content)
            else:
                # Page content unchanged, extract from existing file (before comments section)
                print(f"    Using cached content (only comments changed)")
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        existing_content = f.read()
                    # Split at comments section if it exists
                    if '\n\n---\n\n## Comments\n\n' in existing_content:
                        content = existing_content.split('\n\n---\n\n## Comments\n\n')[0]
                        # Remove the header we added
                        lines = content.split('\n')
                        # Find where the actual content starts (after ---)
                        content_start = 0
                        for i, line in enumerate(lines):
                            if line == '---':
                                content_start = i + 2  # Skip --- and blank line
                                break
                        content = '\n'.join(lines[content_start:])
                    else:
                        # No comments section, extract content after header
                        lines = existing_content.split('\n')
                        content_start = 0
                        for i, line in enumerate(lines):
                            if line == '---':
                                content_start = i + 2
                                break
                        content = '\n'.join(lines[content_start:])
                except Exception as e:
                    print(f"    Failed to read existing file, fetching fresh: {e}")
                    content = self.get_page_content(page_id)
                    if content is None:
                        print(f"    Failed to get content for {page_title}, skipping")
                        continue
                    if self.config.OUTPUT_FORMAT == 'markdown':
                        content = self.convert_html_to_markdown(content)

            # Small delay to avoid rate limiting
            import time
            time.sleep(0.1)  # 100ms delay between API calls

            # Create directory structure
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # Write page content with minimal processing
            page_content = f"# {page_title}\n\n"
            page_content += f"**Source:** [{page_title}]({page_url})\n\n"

            # Handle version info safely
            version_info = page.get('version', {})
            if isinstance(version_info, dict) and 'when' in version_info:
                last_updated = version_info['when']
            else:
                last_updated = "Unknown"

            page_content += f"**Last updated:** {last_updated}\n\n"
            page_content += "---\n\n"
            page_content += content

            # Append comments if any
            if comments:
                page_content += self.format_comments(comments)

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(page_content)

            # Update sync state with both hashes
            space_state[page_id] = {
                'page_hash': page_hash,
                'comments_hash': comments_hash
            }

            is_new = stored_page_hash == '' and stored_comments_hash == ''
            if is_new:
                new_pages += 1
                print(f"  - {page_title} (new)")
            else:
                updated_pages += 1
                print(f"  - {page_title} (updated: {', '.join(change_reasons)})")
        
        # Create directory indices for better navigation
        print("Creating directory indices...")
        for directory in created_directories:
            self._create_directory_index(directory, space_key)
        
        # Create main space index
        main_index_content = f"# {space_key} Documentation\n\n"
        main_index_content += f"**Last synced:** {datetime.now().isoformat()}\n\n"
        main_index_content += f"**Total pages:** {len(pages)}\n\n"
        
        # Group files by top-level directory
        top_level_items = {}
        for filepath in all_files:
            relative_to_space = filepath.relative_to(output_dir)
            if len(relative_to_space.parts) == 1:
                # File in root
                top_level_items.setdefault('_root', []).append(filepath)
            else:
                # File in subdirectory
                top_dir = relative_to_space.parts[0]
                top_level_items.setdefault(top_dir, []).append(filepath)
        
        if '_root' in top_level_items:
            main_index_content += "## Root Pages\n\n"
            for filepath in sorted(top_level_items['_root']):
                page_name = filepath.stem
                main_index_content += f"- [{page_name}]({filepath.name})\n"
            main_index_content += "\n"
        
        # List top-level directories
        directories = [d for d in output_dir.iterdir() if d.is_dir()]
        if directories:
            main_index_content += "## Sections\n\n"
            for directory in sorted(directories):
                main_index_content += f"- [{directory.name}/]({directory.name}/README.md)\n"
        
        # Write main index
        main_index_file = output_dir / 'README.md'
        with open(main_index_file, 'w', encoding='utf-8') as f:
            f.write(main_index_content)
        
        # Save sync state
        sync_state[space_key] = space_state
        self._save_sync_state(sync_state)
        
        print(f"Sync complete: {new_pages} new pages, {updated_pages} updated pages")
        print(f"Created directory structure with {len(created_directories)} directories")
    
    def sync_single_page(self, page_id_or_url: str, incremental: bool = True, 
                         output_format: str = 'html'):
        """Sync a single Confluence page.
        
        Args:
            page_id_or_url: The Confluence page ID or URL
            incremental: Whether to skip if unchanged
            output_format: 'html' or 'markdown'
        """
        # Handle URL input (convenience feature)
        if page_id_or_url.startswith('http'):
            page_id = self.extract_page_id_from_url(page_id_or_url)
            if not page_id:
                print(f"Could not extract page ID from URL: {page_id_or_url}")
                print("Please provide the page ID directly (the number in the URL)")
                return
        else:
            page_id = page_id_or_url
        
        print(f"Syncing single page: {page_id} (format: {output_format})")
        
        # Get page metadata
        page = self.get_page_by_id(page_id)
        if not page:
            print(f"Could not fetch page with ID: {page_id}")
            return
        
        # Get space info
        space_id = page.get('spaceId')
        if not space_id:
            print(f"Page {page_id} has no space ID")
            return
        
        # Get space key
        space_url = f"{self.config.BASE_URL}/api/v2/spaces/{space_id}"
        try:
            response = self.session.get(space_url)
            response.raise_for_status()
            space_data = response.json()
            space_key = space_data.get('key', 'UNKNOWN')
        except:
            space_key = 'UNKNOWN'
        
        # Create output directory
        output_dir = Path(self.config.OUTPUT_DIR) / space_key
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Fetch ancestors for hierarchy
        ancestors = []
        current_parent_id = page.get('parentId')
        while current_parent_id:
            parent = self.get_page_by_id(current_parent_id)
            if parent:
                ancestors.insert(0, parent)
                current_parent_id = parent.get('parentId')
            else:
                break
        
        # Build path with appropriate extension
        page_title = page['title']
        relative_path = self._build_page_path(page_title, ancestors)
        if output_format == 'markdown':
            relative_path = relative_path.with_suffix('.md')
        filepath = output_dir / relative_path

        # Always fetch comments first to check for changes
        print(f"Fetching comments for '{page_title}'...")
        comments = self.get_page_comments(page_id)
        comments_hash = self._get_comments_hash(comments)
        if comments:
            print(f"Found {len(comments)} comment(s)")

        # Check incremental sync with both page and comment hashes
        page_hash = self._get_page_hash(page)
        state_key = f"{page_id}_{output_format}"

        if incremental:
            sync_state = self._load_sync_state()
            space_state = sync_state.get(space_key, {})
            stored_state = space_state.get(state_key, {})

            # Handle old format (just page hash string)
            if isinstance(stored_state, str):
                stored_state = {'page_hash': stored_state, 'comments_hash': ''}

            stored_page_hash = stored_state.get('page_hash', '')
            stored_comments_hash = stored_state.get('comments_hash', '')

            page_changed = (page_hash != stored_page_hash)
            comments_changed = (comments_hash != stored_comments_hash)

            if not page_changed and not comments_changed:
                print(f"Page '{page_title}' is up to date")
                return

            # Log what changed
            changes = []
            if page_changed:
                changes.append("content")
            if comments_changed:
                changes.append("comments")
            print(f"Changes detected: {', '.join(changes)}")

        # Get content (only fetch if page changed or file doesn't exist)
        page_changed_or_new = not incremental or page_hash != stored_page_hash if incremental else True

        if page_changed_or_new or not filepath.exists():
            print(f"Fetching content for '{page_title}'...")
            content = self.get_page_content(page_id)
            if content is None:
                print(f"Failed to get content for {page_title}")
                return

            # Convert to Markdown if requested
            if output_format == 'markdown':
                print(f"Converting to Markdown format...")
                content = self.convert_html_to_markdown(content)
        else:
            # Only comments changed, reuse existing content
            print(f"Using cached content (only comments changed)")
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    existing_content = f.read()
                # Extract content (everything after --- and before comments section)
                if '\n\n---\n\n## Comments\n\n' in existing_content:
                    content = existing_content.split('\n\n---\n\n## Comments\n\n')[0]
                else:
                    content = existing_content
                # Remove header to get just content
                lines = content.split('\n')
                content_start = 0
                for i, line in enumerate(lines):
                    if line == '---':
                        content_start = i + 2
                        break
                content = '\n'.join(lines[content_start:])
            except Exception as e:
                print(f"Failed to read existing file, fetching fresh: {e}")
                content = self.get_page_content(page_id)
                if content is None:
                    print(f"Failed to get content for {page_title}")
                    return
                if output_format == 'markdown':
                    content = self.convert_html_to_markdown(content)

        # Small delay to avoid rate limiting
        import time
        time.sleep(0.1)

        # Write file
        filepath.parent.mkdir(parents=True, exist_ok=True)

        page_url = f"{self.config.BASE_URL}/pages/viewpage.action?pageId={page_id}"
        page_content = f"# {page_title}\n\n"
        page_content += f"**Source:** [{page_title}]({page_url})\n\n"

        version_info = page.get('version', {})
        last_updated = version_info.get('when', 'Unknown') if isinstance(version_info, dict) else 'Unknown'

        page_content += f"**Last updated:** {last_updated}\n\n"
        page_content += "---\n\n"
        page_content += content

        # Append comments if any
        if comments:
            page_content += self.format_comments(comments)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(page_content)
        
        print(f"✓ Synced: {filepath.relative_to(Path(self.config.OUTPUT_DIR))}")

        # Update sync state with both page and comment hashes
        sync_state = self._load_sync_state()
        space_state = sync_state.get(space_key, {})
        state_key = f"{page_id}_{output_format}"
        space_state[state_key] = {
            'page_hash': page_hash,
            'comments_hash': comments_hash
        }
        sync_state[space_key] = space_state
        self._save_sync_state(sync_state)
        
        # Create directory index
        self._create_directory_index(filepath.parent, space_key)

    def sync_all_spaces(self, incremental: bool = True):
        """Sync all configured spaces."""
        space_keys = self.config.get_space_keys_list()
        
        if not space_keys:
            print("No space keys configured. Please set CONFLUENCE_SPACE_KEYS.")
            return
        
        print(f"Starting sync for {len(space_keys)} spaces...")
        
        for space_key in space_keys:
            try:
                self.sync_space(space_key, incremental)
            except Exception as e:
                print(f"Error syncing space {space_key}: {e}")
        
        print("All spaces synced!")


def main():
    """Main function with single page and format support."""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='Sync Confluence documentation')
    parser.add_argument('--full', action='store_true', 
                       help='Full sync (not incremental)')
    parser.add_argument('--page-id', type=str, 
                       help='Sync single page by ID')
    parser.add_argument('--page-url', type=str,
                       help='Sync single page by URL')
    parser.add_argument('--format', choices=['html', 'markdown'], 
                       default='html',
                       help='Output format (default: html)')
    
    args = parser.parse_args()
    
    try:
        syncer = ConfluenceSync()
        
        if args.page_id:
            # Single page sync by ID
            syncer.sync_single_page(args.page_id, 
                                  incremental=not args.full,
                                  output_format=args.format)
        elif args.page_url:
            # Single page sync by URL
            syncer.sync_single_page(args.page_url,
                                  incremental=not args.full,
                                  output_format=args.format)
        else:
            # Default: sync all spaces (could extend format support here later)
            syncer.sync_all_spaces(incremental=not args.full)
        
        return 0
    except Exception as e:
        print(f"Sync failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main()) 
