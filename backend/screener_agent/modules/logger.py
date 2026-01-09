"""
Screener Logger - Silent background logging for debugging
Automatically saves logs to property folder without cluttering the console
"""

import logging
import os
from datetime import datetime
from typing import Optional


class ScreenerLogger:
    """
    Silent background logger that saves detailed logs to file.
    Console output remains clean - only errors show.
    Log file captures everything for debugging.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ScreenerLogger._initialized:
            return

        self.logger = logging.getLogger('screener')
        self.logger.setLevel(logging.DEBUG)
        self.file_handler = None
        self.console_handler = None
        self.log_file_path = None

        # Add console handler (only warnings and errors)
        self.console_handler = logging.StreamHandler()
        self.console_handler.setLevel(logging.WARNING)
        console_format = logging.Formatter('[%(levelname)s] %(message)s')
        self.console_handler.setFormatter(console_format)
        self.logger.addHandler(self.console_handler)

        ScreenerLogger._initialized = True

    def setup_for_property(self, output_folder: str, property_name: str):
        """
        Set up logging for a specific property run.
        Creates a log file in the property's output folder.

        Args:
            output_folder: Path to property output folder
            property_name: Name of the property being processed
        """
        # Remove existing file handler if any
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)
            self.file_handler.close()

        # Create logs directory in property folder
        logs_dir = os.path.join(output_folder, 'Logs')
        os.makedirs(logs_dir, exist_ok=True)

        # Create timestamped log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_filename = f"screener_{property_name}_{timestamp}.log"
        self.log_file_path = os.path.join(logs_dir, log_filename)

        # Set up file handler (captures everything)
        self.file_handler = logging.FileHandler(self.log_file_path, encoding='utf-8')
        self.file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.file_handler.setFormatter(file_format)
        self.logger.addHandler(self.file_handler)

        self.info(f"=== Screener Log Started for {property_name} ===")
        self.info(f"Log file: {self.log_file_path}")

    def debug(self, msg: str, *args):
        """Debug level - only goes to file"""
        self.logger.debug(msg, *args)

    def info(self, msg: str, *args):
        """Info level - only goes to file"""
        self.logger.info(msg, *args)

    def warning(self, msg: str, *args):
        """Warning level - goes to file AND console"""
        self.logger.warning(msg, *args)

    def error(self, msg: str, *args):
        """Error level - goes to file AND console"""
        self.logger.error(msg, *args)

    def api_call(self, service: str, endpoint: str, params: dict = None):
        """Log an API call being made"""
        param_str = f" params={params}" if params else ""
        self.debug(f"API CALL [{service}] {endpoint}{param_str}")

    def api_response(self, service: str, status: int, size: int = None, error: str = None):
        """Log an API response"""
        if error:
            self.error(f"API ERROR [{service}] {error}")
        elif size:
            self.debug(f"API OK [{service}] status={status}, size={size} bytes")
        else:
            self.debug(f"API OK [{service}] status={status}")

    def extraction(self, field: str, value, source: str):
        """Log a data extraction"""
        if value is not None and value != '':
            self.debug(f"EXTRACTED [{source}] {field} = {value}")
        else:
            self.debug(f"MISSING [{source}] {field} = (empty)")

    def step_start(self, step_name: str):
        """Log the start of a major step"""
        self.info(f">>> STEP START: {step_name}")

    def step_end(self, step_name: str, success: bool = True, details: str = None):
        """Log the end of a major step"""
        status = "SUCCESS" if success else "FAILED"
        detail_str = f" - {details}" if details else ""
        self.info(f"<<< STEP END: {step_name} [{status}]{detail_str}")

    def get_log_path(self) -> Optional[str]:
        """Get the current log file path"""
        return self.log_file_path


# Global logger instance
_logger = None

def get_logger() -> ScreenerLogger:
    """Get the global screener logger instance"""
    global _logger
    if _logger is None:
        _logger = ScreenerLogger()
    return _logger


def setup_logging(output_folder: str, property_name: str):
    """Convenience function to set up logging for a property"""
    logger = get_logger()
    logger.setup_for_property(output_folder, property_name)
    return logger
