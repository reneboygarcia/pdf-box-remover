"""Main entry point for the PDF Box Eraser application."""
import logging
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(project_root, 'pdf_box_eraser.log'))
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point for the application."""
    try:
        # Import here to ensure logging is set up first
        from pdf_box_eraser.ui.streamlit_app import PDFBoxEraserUI
        
        # Create and run the UI
        app = PDFBoxEraserUI()
        app.run()
        
    except Exception as e:
        logger.error(f"Application failed to start: {e}")
        raise

if __name__ == "__main__":
    main()
