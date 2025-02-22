"""Box removal functionality for PDF files."""

import pikepdf
import logging
import re
import gc
from typing import Set, Dict, Union, Optional, List, Pattern
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pdf_box_eraser.utils.decorators import log_exceptions

logger = logging.getLogger(__name__)

@dataclass
class ProcessingStats:
    """Statistics for PDF processing."""
    pages_processed: int = 0
    pages_skipped: int = 0
    boxes_removed: int = 0
    objects_processed: int = 0
    quick_matches: int = 0

    def reset(self):
        """Reset all statistics to zero."""
        self.pages_processed = 0
        self.pages_skipped = 0
        self.boxes_removed = 0
        self.objects_processed = 0
        self.quick_matches = 0

class PDFObjectIdentifier:
    """Handles unique identification of PDF objects."""
    
    @staticmethod
    def get_object_id(obj: pikepdf.Object, prefix: str = "") -> str:
        """Get a unique identifier for a PDF object."""
        try:
            if hasattr(obj, "objgen"):
                return f"{prefix}{obj.objgen[0]}_{obj.objgen[1]}"

            content = obj.read_bytes() if isinstance(obj, pikepdf.Stream) else str(obj)
            return f"{prefix}{type(obj).__name__}_{hash(content)}"
        except Exception as e:
            logger.error(f"Failed to get object ID: {e}")
            return f"{prefix}{id(obj)}"

class PDFObjectHelper:
    """Helper class for safe PDF object operations."""
    
    @staticmethod
    def safe_get_object(obj: Optional[pikepdf.Object]) -> Optional[pikepdf.Object]:
        """Safely dereference a PDF object."""
        if obj is None:
            return None

        if isinstance(obj, pikepdf.Object):
            if obj.is_indirect:
                try:
                    return obj.get_object()
                except Exception:
                    try:
                        raw_obj = obj._obj
                        return raw_obj if raw_obj is not None else obj
                    except Exception:
                        return obj
        return obj

    @staticmethod
    @log_exceptions
    def safe_get_dict_item(pdf_dict: pikepdf.Dictionary, key: str) -> Optional[pikepdf.Object]:
        """Safely get an item from a PDF dictionary."""
        try:
            if not isinstance(pdf_dict, pikepdf.Dictionary):
                logger.debug(f"safe_get_dict_item: Not a dictionary, got {type(pdf_dict)}")
                return None

            if key not in pdf_dict:
                logger.debug(f"safe_get_dict_item: Key {key} not found in dictionary")
                return None

            item = pdf_dict.get(key)
            logger.debug(f"safe_get_dict_item: Retrieved item of type {type(item)} for key {key}")
            return PDFObjectHelper.safe_get_object(item)
        except Exception as e:
            logger.debug(f"Could not get dictionary item {key}: {str(e)}")
            return None

class BoxPattern(ABC):
    """Abstract base class for box pattern detection strategies."""
    
    @abstractmethod
    def matches(self, content: bytes) -> bool:
        """Check if content matches the pattern."""
        pass

    @abstractmethod
    def remove(self, content: str) -> str:
        """Remove matching patterns from content."""
        pass

class RegexBoxPattern(BoxPattern):
    """Box pattern detection using regular expressions."""
    
    def __init__(self, pattern: str, is_bytes: bool = False):
        """Initialize with regex pattern."""
        self.pattern = pattern
        self.is_bytes = is_bytes
        self._compiled = re.compile(pattern.encode() if is_bytes else pattern)

    def matches(self, content: bytes) -> bool:
        """Check if content matches the pattern."""
        if self.is_bytes:
            return bool(self._compiled.search(content, re.DOTALL))
        return bool(self._compiled.search(content.decode("latin1")))

    def remove(self, content: str) -> str:
        """Remove matching patterns from content."""
        if self.is_bytes:
            return content
        return self._compiled.sub("", content)

class BoxDetector:
    """Handles detection of boxes in PDF content."""
    
    # Quick detection patterns
    QUICK_PATTERNS = {
        "basic": RegexBoxPattern(r"re\s+[SsWnfFbB]", True),
        "styled": RegexBoxPattern(r"q.*?re\s+[SsWnfFbB].*?Q", True),
        "text": RegexBoxPattern(r"BT.*?re\s+[SsWnfFbB]", True),
    }

    def has_boxes(self, content: bytes) -> bool:
        """Check if content contains any box patterns."""
        if not content:
            return False

        try:
            for pattern_name, pattern in self.QUICK_PATTERNS.items():
                if pattern.matches(content):
                    logger.debug(f"Found {pattern_name} box pattern")
                    return True

            logger.debug("No box patterns detected")
            return False
        except Exception as e:
            logger.warning(f"Error in pattern matching: {e}")
            return True

class BoxRemover:
    """Handles the removal of rectangular boxes from PDF content."""

    # Box removal patterns
    BOX_PATTERNS = [
        RegexBoxPattern(r"re\s+[SsWnfFbB]"),
        RegexBoxPattern(r"[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+RG\s+re\s+[SsWnfFbB]"),
        RegexBoxPattern(r"[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+rg\s+re\s+[SsWnfFbB]"),
        RegexBoxPattern(r"q\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWnfFbB]"),
        RegexBoxPattern(r"[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+cm\s+re\s+[SsWnfFbB]"),
        RegexBoxPattern(r"q\s+GS\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWnfFbB]"),
    ]

    def __init__(self):
        """Initialize the BoxRemover."""
        self.processed_objects: Set[str] = set()
        self.stats = ProcessingStats()
        self.detector = BoxDetector()
        self.object_helper = PDFObjectHelper()
        self.object_id = PDFObjectIdentifier()

    def reset_state(self):
        """Reset the internal state for a new processing session."""
        self.processed_objects.clear()
        self.stats.reset()

    @log_exceptions
    def process_content_stream(self, stream: pikepdf.Stream, stream_id: Optional[str] = None) -> bool:
        """Process a single content stream."""
        stream = self.object_helper.safe_get_object(stream)
        if not isinstance(stream, pikepdf.Stream):
            return False

        # Get unique object identifier
        if stream_id is None:
            stream_id = self.object_id.get_object_id(stream, "stream_")
        
        logger.debug(f"Processing content stream {stream_id}")
        if stream_id in self.processed_objects:
            logger.debug(f"Content stream {stream_id} was previously processed")
            return False
            
        self.processed_objects.add(stream_id)
        self.stats.objects_processed += 1

        # Process the content
        content = stream.read_bytes()
        logger.debug(f"Content stream {stream_id} size: {len(content)} bytes")

        modified_content = self.remove_boxes_from_content(content)
        if modified_content != content:
            logger.debug(f"Content stream {stream_id} was modified")
            stream.write(modified_content)
            return True
            
        logger.debug(f"No modifications needed for content stream {stream_id}")
        return False

    @log_exceptions
    def process_page(self, page: pikepdf.Page, page_num: int) -> None:
        """Process a single PDF page."""
        page_id = self.object_id.get_object_id(page, f"page_{page_num}_")
        logger.info(f"Analyzing page {page_num} (ID: {page_id})")

        if page_id in self.processed_objects:
            logger.debug(f"Page {page_num} already processed")
            self.stats.pages_skipped += 1
            return

        if not self._should_process_page(page):
            logger.info(f"No boxes detected on page {page_num}")
            self.stats.pages_skipped += 1
            return

        self.processed_objects.add(page_id)
        logger.info(f"Processing page {page_num}")

        # Process page resources
        if page.get("/Resources"):
            self._process_resources(page["/Resources"])

        # Process page contents
        contents = page.get("/Contents")
        if contents:
            if isinstance(contents, pikepdf.Array):
                for stream in contents:
                    self.process_content_stream(stream)
            else:
                self.process_content_stream(contents)

        self.stats.pages_processed += 1
        gc.collect()

    def _process_resources(self, resources: pikepdf.Dictionary) -> None:
        """Process PDF resource dictionary."""
        resources = self.object_helper.safe_get_object(resources)
        if not isinstance(resources, pikepdf.Dictionary):
            return

        res_id = self.object_id.get_object_id(resources, "res_")
        if res_id in self.processed_objects:
            return

        self.processed_objects.add(res_id)
        self._process_xobjects(resources)
        self._process_extgstate(resources)

    def _process_xobjects(self, resources: pikepdf.Dictionary) -> None:
        """Process XObjects in resources."""
        xobjects = resources.get("/XObject")
        if not isinstance(xobjects, pikepdf.Dictionary):
            return

        try:
            xobject_keys = list(xobjects.keys())
            logger.debug(f"Processing XObjects: {xobject_keys}")

            # Process form XObjects
            form_keys = [k for k in xobject_keys if k.startswith("/Fm") or k.startswith("/FXX")]
            for key in form_keys:
                try:
                    xobject = xobjects.get(key)
                    if xobject is not None and xobject.get("/Subtype") == "/Form":
                        logger.debug(f"Processing Form XObject: {key}")
                        self._process_form_xobject(xobject)
                except Exception as e:
                    logger.debug(f"Skipping problematic XObject {key}: {str(e)}")

            # Log skipped image XObjects
            image_keys = [k for k in xobject_keys if k.startswith("/Im")]
            if image_keys:
                logger.debug(f"Skipping Image XObjects: {image_keys}")

        except Exception as e:
            logger.debug(f"Error processing XObjects: {str(e)}")

    def _process_extgstate(self, resources: pikepdf.Dictionary) -> None:
        """Process ExtGState in resources."""
        extgstate = resources.get("/ExtGState")
        if not isinstance(extgstate, pikepdf.Dictionary):
            return

        try:
            for key in extgstate.keys():
                try:
                    gstate = extgstate.get(key)
                    if isinstance(gstate, pikepdf.Dictionary) and "/SMask" in gstate:
                        logger.debug(f"Processing SMask in ExtGState: {key}")
                        self._process_form_xobject(gstate["/SMask"])
                except Exception as e:
                    logger.debug(f"Skipping problematic ExtGState {key}: {str(e)}")
        except Exception as e:
            logger.debug(f"Error processing ExtGState: {str(e)}")

    def _process_form_xobject(self, xobject: pikepdf.Stream) -> None:
        """Process a Form XObject and its resources."""
        xobject = self.object_helper.safe_get_object(xobject)
        if not isinstance(xobject, pikepdf.Stream):
            return

        obj_id = self.object_id.get_object_id(xobject, "form_")
        if obj_id in self.processed_objects:
            logger.debug(f"XObject {obj_id} was previously processed")
            return

        self.processed_objects.add(obj_id)
        self.stats.objects_processed += 1

        if xobject.get("/Resources"):
            logger.debug(f"Processing resources for XObject {obj_id}")
            self._process_resources(xobject["/Resources"])

        logger.debug(f"Processing content stream for XObject {obj_id}")
        self.process_content_stream(xobject, f"stream_{obj_id}")

    def _should_process_stream(self, stream: pikepdf.Stream) -> bool:
        """Determine if a PDF stream needs box removal."""
        if not isinstance(stream, pikepdf.Stream):
            return False

        try:
            return self.detector.has_boxes(stream.read_bytes())
        except Exception as e:
            logger.warning(f"Error reading stream: {e}")
            return True

    def _should_process_page(self, page: pikepdf.Page) -> bool:
        """Determine if a page needs box removal."""
        contents = page.get("/Contents")
        if not contents:
            return False

        try:
            if isinstance(contents, pikepdf.Array):
                return any(self._should_process_stream(stream) for stream in contents)
            return self._should_process_stream(contents)
        except Exception as e:
            logger.warning(f"Error analyzing page contents: {e}")
            return True

    @log_exceptions
    def remove_boxes_from_content(self, content: bytes) -> bytes:
        """Remove box-drawing operations from PDF content stream."""
        try:
            content_str = content.decode("latin1")
            original_length = len(content_str)

            for pattern in self.BOX_PATTERNS:
                try:
                    if pattern.matches(content):
                        content_str = pattern.remove(content_str)
                        self.stats.boxes_removed += 1
                except Exception as e:
                    logger.warning(f"Error applying pattern: {e}")

            if len(content_str) != original_length:
                logger.debug(f"Removed {original_length - len(content_str)} characters")

            return content_str.encode("latin1")
        except Exception as e:
            logger.error(f"Error removing boxes: {e}")
            return content
