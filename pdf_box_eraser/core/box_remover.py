"""Box removal functionality for PDF files."""

import pikepdf
import logging
import re
import gc
from typing import Set, Dict, Union, Optional
from pdf_box_eraser.utils.decorators import log_exceptions

logger = logging.getLogger(__name__)


class BoxRemover:
    """Handles the removal of rectangular boxes from PDF content."""

    # Box patterns to match and remove
    BOX_PATTERNS = [
        # Basic rectangle operations
        r"re\s+[SsWnfFbB]",
        # Rectangle with stroke color
        r"[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+RG\s+re\s+[SsWnfFbB]",
        # Rectangle with fill color
        r"[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+rg\s+re\s+[SsWnfFbB]",
        # Rectangle in a graphics state
        r"q\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWnfFbB]",
        # Rectangle with transformation matrix
        r"[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+cm\s+re\s+[SsWnfFbB]",
        # Graphics state with rectangle
        r"q\s+GS\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWnfFbB]",
    ]

    # Quick detection patterns for common box operations
    QUICK_PATTERNS = {
        "basic": b"re\\s+[SsWnfFbB]",  # Simple rectangle operations
        "styled": b"q.*?re\\s+[SsWnfFbB].*?Q",  # Styled rectangles
        "text": b"BT.*?re\\s+[SsWnfFbB]",  # Text bounding boxes
    }

    def __init__(self):
        """Initialize the BoxRemover with tracking stats."""
        self.processed_objects: Set[str] = set()
        self.stats = self._create_empty_stats()

    def _create_empty_stats(self) -> Dict[str, int]:
        """Create a fresh statistics dictionary."""
        return {
            "pages_processed": 0,
            "pages_skipped": 0,
            "boxes_removed": 0,
            "objects_processed": 0,
            "quick_matches": 0,
        }

    def reset_state(self):
        """Reset the internal state for a new processing session."""
        self.processed_objects.clear()
        self.stats = self._create_empty_stats()

    @log_exceptions
    def process_content_stream(self, stream, stream_id=None) -> bool:
        """Process a single content stream."""
        stream = self._safe_get_object(stream)
        if not isinstance(stream, pikepdf.Stream):
            return False

        # Get unique object identifier
        if stream_id is None:
            stream_id = self.get_object_id(stream, "stream_")
        logger.debug(f"Processing content stream {stream_id}")
        if stream_id in self.processed_objects:
            logger.debug(f"Content stream {stream_id} was previously processed")
            return False
        self.processed_objects.add(stream_id)
        self.stats["objects_processed"] += 1

        # Get the raw content
        content = stream.read_bytes()
        logger.debug(f"Content stream {stream_id} size: {len(content)} bytes")

        # Process the content
        modified_content = self.remove_boxes_from_content(content)
        if modified_content != content:
            logger.debug(f"Content stream {stream_id} was modified")
            stream.write(modified_content)
            return True
        else:
            logger.debug(f"No modifications needed for content stream {stream_id}")
            return False

    @log_exceptions
    def process_page(self, page, page_num: int) -> None:
        """Process a single PDF page, skipping if no boxes detected.

        Args:
            page: PDF page object to process
            page_num: Page number for logging
        """
        page_id = self.get_object_id(page, f"page_{page_num}_")
        logger.info(f"Analyzing page {page_num} (ID: {page_id})")

        # Skip if already processed
        if page_id in self.processed_objects:
            logger.debug(f"Page {page_num} already processed")
            self.stats["pages_skipped"] += 1
            return

        # Skip if no boxes detected
        if not self._should_process_page(page):
            logger.info(f"No boxes detected on page {page_num}")
            self.stats["pages_skipped"] += 1
            return

        # Process the page
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

        self.stats["pages_processed"] += 1
        gc.collect()  # Help manage memory

    def _safe_get_object(self, obj):
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

    @log_exceptions
    def _safe_get_dict_item(self, pdf_dict, key):
        """Safely get an item from a PDF dictionary."""
        try:
            if not isinstance(pdf_dict, pikepdf.Dictionary):
                logger.debug(
                    f"safe_get_dict_item: Not a dictionary, got {type(pdf_dict)}"
                )
                return None

            if key not in pdf_dict:
                logger.debug(f"safe_get_dict_item: Key {key} not found in dictionary")
                return None

            item = pdf_dict.get(key)
            logger.debug(
                f"safe_get_dict_item: Retrieved item of type {type(item)} for key {key}"
            )
            return self._safe_get_object(item)
        except Exception as e:
            logger.debug(f"Could not get dictionary item {key}: {str(e)}")
            return None

    @log_exceptions
    def _process_resources(self, resources) -> None:
        """Process PDF resource dictionary."""
        resources = self._safe_get_object(resources)
        if not isinstance(resources, pikepdf.Dictionary):
            return

        # Check if resources were already processed
        res_id = self.get_object_id(resources, "res_")
        if res_id in self.processed_objects:
            return

        self.processed_objects.add(res_id)

        # Process Form XObjects
        xobjects = resources.get("/XObject")
        if isinstance(xobjects, pikepdf.Dictionary):
            try:
                # Get all keys first to avoid modification during iteration
                xobject_keys = list(xobjects.keys())
                logger.debug(f"Processing XObjects: {xobject_keys}")

                # Process form XObjects first (usually prefixed with Fm or FXX)
                form_keys = [
                    k
                    for k in xobject_keys
                    if k.startswith("/Fm") or k.startswith("/FXX")
                ]
                for key in form_keys:
                    try:
                        xobject = xobjects.get(key)
                        if xobject is not None:
                            # Check subtype before processing
                            subtype = xobject.get("/Subtype")
                            if subtype == "/Form":
                                logger.debug(f"Processing Form XObject: {key}")
                                self._process_form_xobject(xobject)
                            else:
                                logger.debug(
                                    f"Skipping non-Form XObject: {key} (subtype: {subtype})"
                                )
                    except Exception as e:
                        logger.debug(f"Skipping problematic XObject {key}: {str(e)}")

                # Skip image XObjects (usually prefixed with Im)
                image_keys = [k for k in xobject_keys if k.startswith("/Im")]
                if image_keys:
                    logger.debug(f"Skipping Image XObjects: {image_keys}")

            except Exception as e:
                logger.debug(f"Error processing XObjects: {str(e)}")

        # Process ExtGState for soft masks
        extgstate = resources.get("/ExtGState")
        if isinstance(extgstate, pikepdf.Dictionary):
            try:
                gstate_keys = list(extgstate.keys())
                for key in gstate_keys:
                    try:
                        gstate = extgstate.get(key)
                        if (
                            isinstance(gstate, pikepdf.Dictionary)
                            and "/SMask" in gstate
                        ):
                            logger.debug(f"Processing SMask in ExtGState: {key}")
                            self._process_form_xobject(gstate["/SMask"])
                    except Exception as e:
                        logger.debug(f"Skipping problematic ExtGState {key}: {str(e)}")
            except Exception as e:
                logger.debug(f"Error processing ExtGState: {str(e)}")

    @log_exceptions
    def _process_form_xobject(self, xobject) -> None:
        """Process a Form XObject and its resources."""
        xobject = self._safe_get_object(xobject)
        if not isinstance(xobject, pikepdf.Stream):
            return

        # Get unique object identifier for the Form XObject
        obj_id = self.get_object_id(xobject, "form_")
        logger.debug(f"Processing Form XObject {obj_id}")
        if obj_id in self.processed_objects:
            logger.debug(f"XObject {obj_id} was previously processed")
            return
        self.processed_objects.add(obj_id)
        self.stats["objects_processed"] += 1

        # Process resources first
        if xobject.get("/Resources"):
            logger.debug(f"Processing resources for XObject {obj_id}")
            self._process_resources(xobject["/Resources"])

        # Process the content stream with a different ID
        logger.debug(f"Processing content stream for XObject {obj_id}")
        self._process_content_stream(xobject, f"stream_{obj_id}")

    @log_exceptions
    def _process_content_stream(self, stream, stream_id=None) -> bool:
        """Process a single content stream."""
        stream = self._safe_get_object(stream)
        if not isinstance(stream, pikepdf.Stream):
            return False

        # Get unique object identifier
        if stream_id is None:
            stream_id = self.get_object_id(stream, "stream_")
        logger.debug(f"Processing content stream {stream_id}")
        if stream_id in self.processed_objects:
            logger.debug(f"Content stream {stream_id} was previously processed")
            return False
        self.processed_objects.add(stream_id)
        self.stats["objects_processed"] += 1

        # Get the raw content
        content = stream.read_bytes()
        logger.debug(f"Content stream {stream_id} size: {len(content)} bytes")

        # Process the content
        modified_content = self.remove_boxes_from_content(content)
        if modified_content != content:
            logger.debug(f"Content stream {stream_id} was modified")
            stream.write(modified_content)
            return True
        else:
            logger.debug(f"No modifications needed for content stream {stream_id}")
            return False

    @log_exceptions
    def get_object_id(self, obj, prefix="") -> str:
        """Get a unique identifier for a PDF object."""
        try:
            # Try to get the PDF object number and generation
            if hasattr(obj, "objgen"):
                return f"{prefix}{obj.objgen[0]}_{obj.objgen[1]}"

            # Fallback to object type and content hash
            content = obj.read_bytes() if isinstance(obj, pikepdf.Stream) else str(obj)
            return f"{prefix}{type(obj).__name__}_{hash(content)}"

        except Exception as e:
            logger.error(f"Failed to get object ID: {e}")
            return f"{prefix}{id(obj)}"

    def _has_box_patterns(self, content: bytes) -> bool:
        """Check if content contains any box patterns.

        Args:
            content: Raw PDF content stream bytes

        Returns:
            bool: True if any box patterns are found
        """
        if not content:
            return False

        try:
            for pattern_name, pattern in self.QUICK_PATTERNS.items():
                if re.search(pattern, content, re.DOTALL):
                    logger.debug(f"Found {pattern_name} box pattern")
                    self.stats["quick_matches"] += 1
                    return True

            logger.debug("No box patterns detected")
            return False

        except Exception as e:
            logger.warning(f"Error in pattern matching: {e}")
            return True  # Conservative approach: process on error

    def _should_process_stream(self, stream) -> bool:
        """Determine if a PDF stream needs box removal.

        Args:
            stream: PDF stream object

        Returns:
            bool: True if stream contains box patterns
        """
        if not isinstance(stream, pikepdf.Stream):
            return False

        try:
            content = stream.read_bytes()
            return self._has_box_patterns(content)
        except Exception as e:
            logger.warning(f"Error reading stream: {e}")
            return True  # Conservative approach: process on error

    def _should_process_page(self, page) -> bool:
        """Determine if a page needs box removal.

        Args:
            page: PDF page object

        Returns:
            bool: True if page contains box patterns
        """
        contents = page.get("/Contents")
        if not contents:
            return False

        try:
            # Handle both single stream and array of streams
            if isinstance(contents, pikepdf.Array):
                return any(self._should_process_stream(stream) for stream in contents)
            return self._should_process_stream(contents)

        except Exception as e:
            logger.warning(f"Error analyzing page contents: {e}")
            return True  # Conservative approach: process on error

    @log_exceptions
    def remove_boxes_from_content(self, content: bytes) -> bytes:
        """Remove box-drawing operations from PDF content stream."""
        try:
            # Decode content
            content_str = content.decode("latin1")
            original_length = len(content_str)

            # Remove each box pattern
            patterns = [re.compile(pattern) for pattern in self.BOX_PATTERNS]
            for pattern in patterns:
                try:
                    matches = pattern.findall(content_str)
                    if matches:
                        logger.debug(f"Found {len(matches)} matches for pattern")
                        content_str = pattern.sub("", content_str)
                        self.stats["boxes_removed"] += len(matches)
                except Exception as e:
                    logger.error(f"Error processing pattern: {e}")
                    continue

            # Only encode if content was modified
            if len(content_str) != original_length:
                logger.debug(
                    f"Content modified: original size {original_length}, new size {len(content_str)}"
                )
                return content_str.encode("latin1")
            return content

        except Exception as e:
            logger.error(f"Failed to process content: {e}")
            return content
