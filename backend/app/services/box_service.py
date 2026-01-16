"""
Box Service - Integration with Box API for file operations.

Handles reading/writing files from Box cloud storage.
Supports OAuth2 authentication for personal/free Box accounts.
"""

import os
import json
import tempfile
from typing import Optional, List, Dict, Any
from pathlib import Path
import logging

# Lazy import for boxsdk to handle missing package gracefully
try:
    from boxsdk import OAuth2, Client
    from boxsdk.exception import BoxAPIException
    BOXSDK_AVAILABLE = True
except ImportError as e:
    import sys
    print(f"boxsdk import failed: {e}", file=sys.stderr)
    BOXSDK_AVAILABLE = False
    OAuth2 = None
    Client = None
    BoxAPIException = Exception
except Exception as e:
    import sys
    print(f"boxsdk import error (non-ImportError): {e}", file=sys.stderr)
    BOXSDK_AVAILABLE = False
    OAuth2 = None
    Client = None
    BoxAPIException = Exception

logger = logging.getLogger(__name__)

# Token storage file path (in a persistent location)
TOKEN_FILE = os.environ.get('BOX_TOKEN_FILE', '/tmp/box_tokens.json')


def _load_tokens() -> Dict[str, str]:
    """Load stored OAuth tokens from file or environment."""
    # First try environment variables
    access_token = os.environ.get('BOX_ACCESS_TOKEN')
    refresh_token = os.environ.get('BOX_REFRESH_TOKEN')

    if access_token and refresh_token:
        return {
            'access_token': access_token,
            'refresh_token': refresh_token
        }

    # Fall back to token file
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load tokens from file: {e}")

    return {}


def _save_tokens(access_token: str, refresh_token: str):
    """Save OAuth tokens to file."""
    try:
        tokens = {
            'access_token': access_token,
            'refresh_token': refresh_token
        }
        # Ensure directory exists
        os.makedirs(os.path.dirname(TOKEN_FILE) or '.', exist_ok=True)
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f)
        logger.info("Box tokens saved successfully")
    except Exception as e:
        logger.error(f"Failed to save tokens: {e}")


def _store_tokens_callback(access_token: str, refresh_token: str):
    """Callback for boxsdk to store refreshed tokens."""
    _save_tokens(access_token, refresh_token)


class BoxService:
    """
    Service for interacting with Box cloud storage.

    Uses OAuth2 authentication for user-based access.
    """

    def __init__(self):
        """Initialize Box client from environment variables or stored tokens."""
        self.client: Optional[Client] = None
        self.oauth: Optional[OAuth2] = None
        self._init_client()

    def _init_client(self):
        """Initialize the Box client using OAuth2."""
        if not BOXSDK_AVAILABLE:
            logger.warning("boxsdk package not available - Box integration disabled")
            return

        client_id = os.environ.get('BOX_CLIENT_ID')
        client_secret = os.environ.get('BOX_CLIENT_SECRET')

        if not client_id or not client_secret:
            logger.warning("BOX_CLIENT_ID or BOX_CLIENT_SECRET not set - Box integration disabled")
            return

        try:
            # Load stored tokens
            tokens = _load_tokens()
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token')

            if access_token and refresh_token:
                # Initialize with existing tokens
                self.oauth = OAuth2(
                    client_id=client_id,
                    client_secret=client_secret,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    store_tokens=_store_tokens_callback
                )
                self.client = Client(self.oauth)

                # Verify connection works
                try:
                    user = self.client.user().get()
                    logger.info(f"Box authenticated as: {user.name} ({user.login})")
                except BoxAPIException as e:
                    if e.status == 401:
                        logger.warning("Box tokens expired, need re-authorization")
                        self.client = None
                    else:
                        raise
            else:
                logger.info("No Box tokens found - OAuth authorization required")
                logger.info("Visit /api/auth/box/login to authorize Box access")

        except Exception as e:
            logger.error(f"Failed to initialize Box client: {e}")
            self.client = None

    def is_connected(self) -> bool:
        """Check if Box client is connected."""
        return self.client is not None

    def get_authorization_url(self, redirect_uri: str) -> str:
        """
        Get Box OAuth2 authorization URL.

        Args:
            redirect_uri: The callback URL for OAuth

        Returns:
            Authorization URL to redirect user to
        """
        if not BOXSDK_AVAILABLE:
            return ""

        client_id = os.environ.get('BOX_CLIENT_ID')
        client_secret = os.environ.get('BOX_CLIENT_SECRET')

        oauth = OAuth2(
            client_id=client_id,
            client_secret=client_secret,
            store_tokens=_store_tokens_callback
        )

        auth_url, csrf_token = oauth.get_authorization_url(redirect_uri)
        # Store CSRF token for validation
        os.environ['BOX_CSRF_TOKEN'] = csrf_token
        return auth_url

    def authenticate_with_code(self, auth_code: str, redirect_uri: str) -> bool:
        """
        Complete OAuth2 flow with authorization code.

        Args:
            auth_code: Authorization code from Box callback
            redirect_uri: The callback URL used for OAuth

        Returns:
            True if authentication successful
        """
        if not BOXSDK_AVAILABLE:
            return False

        client_id = os.environ.get('BOX_CLIENT_ID')
        client_secret = os.environ.get('BOX_CLIENT_SECRET')

        try:
            oauth = OAuth2(
                client_id=client_id,
                client_secret=client_secret,
                store_tokens=_store_tokens_callback
            )

            # Exchange code for tokens
            access_token, refresh_token = oauth.authenticate(auth_code)

            # Save tokens
            _save_tokens(access_token, refresh_token)

            # Initialize client
            self.oauth = oauth
            self.client = Client(oauth)

            # Verify and log
            user = self.client.user().get()
            logger.info(f"Box OAuth successful! Authenticated as: {user.name}")

            return True

        except Exception as e:
            logger.error(f"Box OAuth authentication failed: {e}")
            return False

    def find_folder(self, folder_path: str, parent_folder_id: str = '0') -> Optional[str]:
        """
        Find a folder by path and return its ID.

        Args:
            folder_path: Path like "3. Underwriting Pipeline/Screener/Properties"
            parent_folder_id: Starting folder ID (default '0' for root)

        Returns:
            Folder ID if found, None otherwise
        """
        if not self.client:
            return None

        parts = folder_path.strip('/').split('/')
        current_folder_id = parent_folder_id

        for part in parts:
            if not part:
                continue

            found = False
            folder = self.client.folder(current_folder_id)
            items = folder.get_items(limit=1000)

            for item in items:
                if item.type == 'folder' and item.name == part:
                    current_folder_id = item.id
                    found = True
                    break

            if not found:
                logger.warning(f"Folder not found: {part} in path {folder_path}")
                return None

        return current_folder_id

    def list_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """List contents of a folder."""
        if not self.client:
            return []

        items = []
        folder = self.client.folder(folder_id)
        for item in folder.get_items(limit=1000):
            items.append({
                'id': item.id,
                'name': item.name,
                'type': item.type,
            })
        return items

    def download_file(self, file_id: str, local_path: str) -> bool:
        """
        Download a file from Box to local path.

        Args:
            file_id: Box file ID
            local_path: Local path to save file

        Returns:
            True if successful
        """
        if not self.client:
            return False

        try:
            with open(local_path, 'wb') as f:
                self.client.file(file_id).download_to(f)
            return True
        except BoxAPIException as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return False

    def download_folder_contents(self, folder_id: str, local_dir: str, pattern: str = None) -> List[str]:
        """
        Download all files from a Box folder to local directory.

        Args:
            folder_id: Box folder ID
            local_dir: Local directory to save files
            pattern: Optional file pattern to filter (e.g., '*.pdf')

        Returns:
            List of downloaded file paths
        """
        if not self.client:
            return []

        os.makedirs(local_dir, exist_ok=True)
        downloaded = []

        folder = self.client.folder(folder_id)
        for item in folder.get_items(limit=1000):
            if item.type == 'file':
                if pattern:
                    import fnmatch
                    if not fnmatch.fnmatch(item.name, pattern):
                        continue

                local_path = os.path.join(local_dir, item.name)
                if self.download_file(item.id, local_path):
                    downloaded.append(local_path)

        return downloaded

    def upload_file(self, local_path: str, folder_id: str, file_name: str = None) -> Optional[str]:
        """
        Upload a file to Box.

        Args:
            local_path: Local file path
            folder_id: Box folder ID to upload to
            file_name: Optional name for the file (defaults to local filename)

        Returns:
            File ID if successful, None otherwise
        """
        if not self.client:
            return None

        try:
            if file_name is None:
                file_name = os.path.basename(local_path)

            folder = self.client.folder(folder_id)

            # Check if file already exists
            for item in folder.get_items(limit=1000):
                if item.type == 'file' and item.name == file_name:
                    # Update existing file
                    with open(local_path, 'rb') as f:
                        updated_file = item.update_contents_with_stream(f)
                    return updated_file.id

            # Upload new file
            with open(local_path, 'rb') as f:
                uploaded_file = folder.upload_stream(f, file_name)
            return uploaded_file.id

        except BoxAPIException as e:
            logger.error(f"Failed to upload file to Box: {e}")
            return None

    def read_json_file(self, file_id: str) -> Optional[Dict]:
        """Read and parse a JSON file from Box."""
        if not self.client:
            return None

        try:
            content = self.client.file(file_id).content()
            return json.loads(content)
        except Exception as e:
            logger.error(f"Failed to read JSON file {file_id}: {e}")
            return None

    def find_file(self, folder_id: str, file_name: str) -> Optional[str]:
        """Find a file by name in a folder, return its ID."""
        if not self.client:
            return None

        folder = self.client.folder(folder_id)
        for item in folder.get_items(limit=1000):
            if item.type == 'file' and item.name == file_name:
                return item.id
        return None

    def get_file_content(self, file_id: str) -> Optional[bytes]:
        """Get raw file content."""
        if not self.client:
            return None
        try:
            return self.client.file(file_id).content()
        except Exception as e:
            logger.error(f"Failed to get file content {file_id}: {e}")
            return None


# Singleton instance
_box_service: Optional[BoxService] = None


def get_box_service() -> BoxService:
    """Get or create Box service instance."""
    global _box_service
    if _box_service is None:
        _box_service = BoxService()
    return _box_service


def reinitialize_box_service() -> BoxService:
    """Force re-initialization of Box service (after OAuth)."""
    global _box_service
    _box_service = BoxService()
    return _box_service
