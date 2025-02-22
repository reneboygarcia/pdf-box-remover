"""Logging configuration for the PDF Box Eraser application."""
import logging
import os
from pathlib import Path

def setup_logging():
    """Set up logging configuration for the application."""
    project_root = Path(__file__).parent.parent
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(project_root, 'pdf_box_eraser.log'))
        ]
    )
    
    return logging.getLogger(__name__)
