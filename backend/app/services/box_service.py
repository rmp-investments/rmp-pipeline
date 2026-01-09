"""
Box Service - Integration with Box API for file operations.

Handles reading/writing files from Box cloud storage.
"""

import os
import json
import tempfile
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pathlib import Path
import logging

# Lazy import for boxsdk to handle missing package gracefully
try:
    from boxsdk import JWTAuth, Client
    from boxsdk.exception import BoxAPIException
    BOXSDK_AVAILABLE = True
except ImportError:
    BOXSDK_AVAILABLE = False
    JWTAuth = None
    Client = None
    BoxAPIException = Exception  # Fallback for type hints

logger = logging.getLogger(__name__)


class BoxService:
    """
    Service for interacting with Box cloud storage.

    Uses JWT authentication for server-to-server access.
    """

    def __init__(self):
        """Initialize Box client from environment variables or config."""
        self.client: Optional[Client] = None
        self._init_client()

    def _init_client(self):
        """Initialize the Box client using JWT auth."""
        if not BOXSDK_AVAILABLE:
            logger.warning("boxsdk package not available - Box integration disabled")
            return

        try:
            # Check for JSON config in environment variable
            box_config = os.environ.get('BOX_CONFIG_JSON')

            if box_config:
                # Parse JSON from environment variable
                config_dict = json.loads(box_config)
                auth = JWTAuth.from_settings_dictionary(config_dict)
            else:
                # Fall back to individual environment variables
                auth = JWTAuth(
                    client_id=os.environ.get('BOX_CLIENT_ID'),
                    client_secret=os.environ.get('BOX_CLIENT_SECRET'),
                    enterprise_id=os.environ.get('BOX_ENTERPRISE_ID'),
                    jwt_key_id=os.environ.get('BOX_JWT_KEY_ID'),
                    rsa_private_key_data=os.environ.get('BOX_PRIVATE_KEY', '').replace('\\n', '\n'),
                    rsa_private_key_passphrase=os.environ.get('BOX_PASSPHRASE'),
                )

            auth.authenticate_instance()
            self.client = Client(auth)

            # Get service account user
            service_account = self.client.user().get()
            logger.info(f"Box authenticated as: {service_account.name}")

        except Exception as e:
            logger.error(f"Failed to initialize Box client: {e}")
            self.client = None

    def is_connected(self) -> bool:
        """Check if Box client is connected."""
        return self.client is not None

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


# Singleton instance
_box_service: Optional[BoxService] = None


def get_box_service() -> BoxService:
    """Get or create Box service instance."""
    global _box_service
    if _box_service is None:
        _box_service = BoxService()
    return _box_service
