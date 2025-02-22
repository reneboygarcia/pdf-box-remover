"""Core PDF processing functionality."""

import pikepdf
import pdf2image
import tempfile
import logging
import re
import gc
from typing import Optional, Set, Dict, Union, List, Callable
from pdf_box_eraser.utils.decorators import log_exceptions
from pdf_box_eraser.core.box_remover import BoxRemover

logger = logging.getLogger(__name__)


class PDFProcessor:
    """Handles PDF processing and box removal operations."""

    def __init__(self):
        """Initialize the PDF processor."""
        self.box_remover = BoxRemover()

    def get_total_pages(self, pdf_path: str) -> int:
        """Get the total number of pages in a PDF."""
        with pikepdf.open(pdf_path) as pdf:
            return len(pdf.pages)

    def process_pdf_file(
        self,
        pdf_path: str,
        start_page: int,
        end_page: int,
        progress_callback: Optional[Callable] = None,
    ) -> str:
        """Process a PDF file and return path to processed file."""
        processed_pdf = self.process_pdf(
            pdf_path, start_page, end_page, progress_callback
        )

        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_output:
            processed_pdf.save(tmp_output.name)
            return tmp_output.name

    def convert_pdf_to_images(
        self, pdf_path: str, start_page: int, end_page: int
    ) -> List:
        """Convert PDF pages to images."""
        return pdf2image.convert_from_path(
            pdf_path, first_page=start_page, last_page=end_page
        )

    @log_exceptions
    def process_pdf(
        self,
        pdf_path: str,
        start_page: int = None,
        end_page: int = None,
        progress_callback: Optional[Callable] = None,
    ) -> pikepdf.Pdf:
        """Process a PDF file to remove unwanted boxes."""
        logger.info(f"Processing PDF: {pdf_path}")

        # Open PDF with specific options for better multi-page handling
        pdf = pikepdf.open(
            pdf_path, allow_overwriting_input=True, ignore_xref_streams=False
        )

        # Validate and adjust page range
        total_pages = len(pdf.pages)
        start_page = 1 if start_page is None else max(1, min(start_page, total_pages))
        end_page = (
            total_pages
            if end_page is None
            else max(start_page, min(end_page, total_pages))
        )

        logger.info(
            f"Processing pages {start_page} to {end_page} out of {total_pages} total pages"
        )

        try:
            self._process_pages(pdf, start_page, end_page, progress_callback)
        finally:
            # Log final statistics and cleanup
            logger.info(f"Processing complete. Statistics: {self.box_remover.stats}")
            gc.collect()

        return pdf

    def _process_pages(
        self,
        pdf: pikepdf.Pdf,
        start_page: int,
        end_page: int,
        progress_callback: Optional[Callable],
    ) -> None:
        """Process a range of pages in the PDF."""
        for page_num in range(start_page, end_page + 1):
            try:
                # Convert to 0-based index for pikepdf
                page = pdf.pages[page_num - 1]
                self.box_remover.process_page(page, page_num)

                # Report progress
                if progress_callback:
                    progress = (page_num - start_page + 1) / (end_page - start_page + 1)
                    progress_callback(progress, self.box_remover.stats)

                # Cleanup
                page = None
                if page_num % 10 == 0:  # Every 10 pages
                    gc.collect()

            except Exception as e:
                logger.error(f"Error processing page {page_num}: {e}")
                continue
