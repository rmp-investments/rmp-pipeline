"""
Screener Service - Integration with Screener Agent via Box API.

This service runs the screener by:
1. Downloading property files from Box
2. Running the screener agent locally
3. Uploading results back to Box
"""

import asyncio
import sys
import os
import json
import tempfile
import shutil
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import logging

from app.services.box_service import get_box_service

logger = logging.getLogger(__name__)

# Box folder paths (relative to root)
BOX_ROOT_FOLDER = "3. Underwriting Pipeline"
BOX_SCREENER_FOLDER = f"{BOX_ROOT_FOLDER}/Screener"
BOX_PROPERTIES_FOLDER = f"{BOX_SCREENER_FOLDER}/Properties"

# Add screener_agent to path
SCREENER_AGENT_PATH = Path(__file__).parent.parent.parent / "screener_agent"
if str(SCREENER_AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(SCREENER_AGENT_PATH))


@dataclass
class ScreenerProgress:
    """Progress update from screener."""
    step: str
    status: str  # "running", "complete", "error"
    percent: int
    message: Optional[str] = None


@dataclass
class ScreenerResult:
    """Result from screener run."""
    success: bool
    output_excel_path: Optional[str] = None
    maps_generated: Optional[list] = None
    error_message: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None


class ScreenerService:
    """
    Service class for running property screener analysis via Box.
    """

    def __init__(self):
        """Initialize the screener service."""
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._box = get_box_service()
        self._properties_folder_id: Optional[str] = None

    def _get_properties_folder_id(self) -> Optional[str]:
        """Get the Box folder ID for Properties folder."""
        if self._properties_folder_id:
            return self._properties_folder_id

        self._properties_folder_id = self._box.find_folder(BOX_PROPERTIES_FOLDER)
        return self._properties_folder_id

    def _find_property_folder(self, property_name: str) -> Optional[Dict]:
        """
        Find a property folder in Box by name.

        Returns dict with folder_id and zone info if found.
        """
        if not self._box.is_connected():
            logger.error("Box not connected")
            return None

        props_folder_id = self._get_properties_folder_id()
        if not props_folder_id:
            logger.error("Properties folder not found in Box")
            return None

        # Search through zone folders
        zone_folders = self._box.list_folder(props_folder_id)
        for zone in zone_folders:
            if zone['type'] != 'folder' or zone['name'].startswith('_'):
                continue

            # Search property folders in this zone
            property_folders = self._box.list_folder(zone['id'])
            for prop in property_folders:
                if prop['type'] != 'folder':
                    continue

                # Check if this folder has a config.json
                config_file_id = self._box.find_file(prop['id'], 'config.json')
                if config_file_id:
                    config = self._box.read_json_file(config_file_id)
                    if config and config.get('property_name', '').lower() == property_name.lower():
                        return {
                            'folder_id': prop['id'],
                            'folder_name': prop['name'],
                            'zone': zone['name'],
                            'config_file_id': config_file_id,
                            'config': config,
                        }

        return None

    def _run_screener_sync(self, property_info: Dict, temp_dir: str) -> Dict[str, Any]:
        """
        Run the screener synchronously.

        Downloads files from Box, runs screener, uploads results.
        """
        try:
            property_name = property_info['config']['property_name']
            folder_id = property_info['folder_id']

            # Create local folder structure
            local_prop_dir = os.path.join(temp_dir, property_info['folder_name'])
            os.makedirs(local_prop_dir, exist_ok=True)

            costar_dir = os.path.join(local_prop_dir, 'CoStar Reports')
            os.makedirs(costar_dir, exist_ok=True)

            maps_dir = os.path.join(local_prop_dir, 'Maps')
            os.makedirs(maps_dir, exist_ok=True)

            # Download config.json
            config_path = os.path.join(local_prop_dir, 'config.json')
            self._box.download_file(property_info['config_file_id'], config_path)

            # Update config with local paths
            with open(config_path, 'r') as f:
                config = json.load(f)

            config['paths'] = {
                'costar_reports_dir': costar_dir,
                'output_path': local_prop_dir,
                'screener_file': os.path.join(local_prop_dir, f"RMP Screener_{property_name}.xlsx"),
                'output_file': os.path.join(local_prop_dir, f"RMP Screener_{property_name}.xlsx"),
            }

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            # Find and download CoStar PDFs from Box
            costar_folder_id = self._box.find_folder("CoStar Reports", folder_id)
            if costar_folder_id:
                self._box.download_folder_contents(costar_folder_id, costar_dir, '*.pdf')
                self._box.download_folder_contents(costar_folder_id, costar_dir)

            logger.info(f"Downloaded files to {local_prop_dir}")

            # Run the screener agent
            from agent_v2 import ScreenerAgent
            agent = ScreenerAgent(config_path)
            agent.run()

            # Upload results back to Box
            output_file = config['paths']['output_file']
            if os.path.exists(output_file):
                self._box.upload_file(output_file, folder_id)

            # Upload maps
            if os.path.exists(maps_dir):
                maps_folder_id = self._box.find_folder('Maps', folder_id)
                if maps_folder_id:
                    for map_file in os.listdir(maps_dir):
                        map_path = os.path.join(maps_dir, map_file)
                        if os.path.isfile(map_path):
                            self._box.upload_file(map_path, maps_folder_id)

            return {
                "success": True,
                "output_file": output_file,
                "maps": list(agent.map_screenshots.keys()) if hasattr(agent, 'map_screenshots') else [],
                "extracted_data": agent.extracted_data if hasattr(agent, 'extracted_data') else {},
            }

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.exception(f"Screener failed: {e}")
            return {
                "success": False,
                "error": f"{str(e)}\n\nTraceback:\n{tb}",
            }

    async def run_analysis(
        self,
        property_id: int,
        property_name: str,
        property_address: Optional[str] = None,
        config_path: Optional[str] = None,
        progress_callback: Optional[Callable[[ScreenerProgress], None]] = None,
    ) -> ScreenerResult:
        """
        Run full screener analysis for a property.
        """
        temp_dir = None
        try:
            # Report initial progress
            if progress_callback:
                progress_callback(ScreenerProgress(
                    step="Initializing",
                    status="running",
                    percent=5,
                    message="Connecting to Box...",
                ))

            if not self._box.is_connected():
                return ScreenerResult(
                    success=False,
                    error_message="Box API not connected. Check BOX_CONFIG_JSON environment variable.",
                )

            # Find property in Box
            if progress_callback:
                progress_callback(ScreenerProgress(
                    step="Finding Property",
                    status="running",
                    percent=10,
                    message=f"Searching for {property_name} in Box...",
                ))

            property_info = self._find_property_folder(property_name)
            if not property_info:
                return ScreenerResult(
                    success=False,
                    error_message=f"Property folder not found in Box: {property_name}",
                )

            logger.info(f"Found property in Box: {property_info['folder_name']}")

            if progress_callback:
                progress_callback(ScreenerProgress(
                    step="Running Screener",
                    status="running",
                    percent=20,
                    message="Downloading files and running analysis...",
                ))

            # Create temp directory for processing
            temp_dir = tempfile.mkdtemp(prefix='screener_')

            # Run the screener in a thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                self._run_screener_sync,
                property_info,
                temp_dir,
            )

            if result.get("success"):
                if progress_callback:
                    progress_callback(ScreenerProgress(
                        step="Complete",
                        status="complete",
                        percent=100,
                        message="Analysis complete. Results uploaded to Box.",
                    ))

                return ScreenerResult(
                    success=True,
                    output_excel_path=result.get("output_file"),
                    maps_generated=result.get("maps", []),
                    extracted_data=result.get("extracted_data", {}),
                )
            else:
                if progress_callback:
                    progress_callback(ScreenerProgress(
                        step="Error",
                        status="error",
                        percent=0,
                        message=result.get("error", "Unknown error"),
                    ))

                return ScreenerResult(
                    success=False,
                    error_message=result.get("error", "Unknown error"),
                )

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.exception(f"Screener failed for {property_name}: {e}")

            if progress_callback:
                progress_callback(ScreenerProgress(
                    step="Error",
                    status="error",
                    percent=0,
                    message=str(e),
                ))

            return ScreenerResult(
                success=False,
                error_message=f"{str(e)}\n\nTraceback:\n{tb}",
            )

        finally:
            # Clean up temp directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to clean up temp dir: {e}")

    def list_available_properties(self) -> list:
        """List properties available in Box."""
        if not self._box.is_connected():
            return []

        properties = []
        props_folder_id = self._get_properties_folder_id()
        if not props_folder_id:
            return []

        zone_folders = self._box.list_folder(props_folder_id)
        for zone in zone_folders:
            if zone['type'] != 'folder' or zone['name'].startswith('_'):
                continue

            property_folders = self._box.list_folder(zone['id'])
            for prop in property_folders:
                if prop['type'] != 'folder':
                    continue

                config_file_id = self._box.find_file(prop['id'], 'config.json')
                if config_file_id:
                    config = self._box.read_json_file(config_file_id)
                    if config:
                        properties.append({
                            "id": prop['id'],
                            "name": config.get('property_name', prop['name']),
                            "zone": zone['name'],
                            "status": "active",
                        })

        return properties


# Singleton instance
_screener_service: Optional[ScreenerService] = None


def get_screener_service() -> ScreenerService:
    """Get or create screener service instance."""
    global _screener_service
    if _screener_service is None:
        _screener_service = ScreenerService()
    return _screener_service
