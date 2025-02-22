"""Box removal functionality for PDF files."""
import pikepdf
import logging
import re
import gc
from typing import Optional, Set, Dict, Union
from pdf_box_eraser.utils.decorators import log_exceptions

logger = logging.getLogger(__name__)

class BoxRemover:
    """Handles the removal of rectangular boxes from PDF content."""
    
    # PDF operators that create boxes
    BOX_PATTERNS = [
        # Basic box operations
        r're\s+S',      # rectangle + stroke
        r're\s+s',      # rectangle + close and stroke
        r're\s+n',      # rectangle + non-stroking
        r're\s+W',      # rectangle + clip
        r're\s+W\s+n',  # rectangle + clip + non-stroke
        
        # Box with style settings
        r'q\s+[\d.]+\s+w\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+RG\s+re\s+[SsWn]\s+Q',
        r'q\s+[\d.]+\s+w\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+rg\s+re\s+[SsWn]\s+Q',
        r'q\s+[\d.]+\s+w\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+K\s+re\s+[SsWn]\s+Q',
        r'q\s+[\d.]+\s+w\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+k\s+re\s+[SsWn]\s+Q',
        
        # Clipping paths
        r'q\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+W\s+n',
        r'q\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+W\s*',
        
        # Text bounding boxes
        r'BT\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWn]',
        r'ET\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWn]',
        
        # Additional box patterns
        r're\s+f',      # rectangle + fill
        r're\s+F',      # rectangle + fill (even-odd)
        r're\s+b',      # rectangle + fill + stroke
        r're\s+B',      # rectangle + fill + stroke (even-odd)
        r're\s+h',      # rectangle + close path
        r're\s+H',      # rectangle + close path (even-odd)
        
        # Complex patterns with transformations
        r'q\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+cm\s+re\s+[SsWnfFbB]',
        r'q\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+Tm\s+re\s+[SsWnfFbB]',
        
        # Patterns with graphics state
        r'q\s+gs\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWnfFbB]',
        r'q\s+GS\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+re\s+[SsWnfFbB]',
    ]
    
    def __init__(self):
        """Initialize the BoxRemover."""
        self.processed_objects: Set[str] = set()
        self.stats = {
            'pages_processed': 0,
            'boxes_removed': 0,
            'objects_processed': 0
        }
    
    def reset_state(self):
        """Reset the internal state of the BoxRemover."""
        self.processed_objects.clear()
        self.stats = {
            'pages_processed': 0,
            'boxes_removed': 0,
            'objects_processed': 0
        }
    
    @log_exceptions
    def get_object_id(self, obj, prefix='') -> str:
        """Get a unique identifier for a PDF object."""
        # Try to get the PDF object number and generation
        if hasattr(obj, 'objgen'):
            obj_id = f"{prefix}{obj.objgen[0]}_{obj.objgen[1]}"
            logger.debug(f"Using PDF object ID: {obj_id}")
            return obj_id
        
        # Fallback to object type and content hash
        content = obj.read_bytes() if isinstance(obj, pikepdf.Stream) else str(obj)
        content_hash = hash(content)
        obj_type = type(obj).__name__
        fallback_id = f"{prefix}{obj_type}_{content_hash}"
        logger.debug(f"Using fallback ID: {fallback_id}")
        return fallback_id
    
    @log_exceptions
    def remove_boxes_from_content(self, content: bytes) -> bytes:
        """Remove box-drawing operations from PDF content stream."""
        try:
            # Decode content
            content_str = content.decode('latin1')
            original_length = len(content_str)
            
            # Remove each box pattern
            for pattern in self.BOX_PATTERNS:
                try:
                    matches = re.findall(pattern, content_str, flags=re.MULTILINE)
                    if matches:
                        logger.debug(f"Found {len(matches)} matches for pattern: {pattern}")
                        content_str = re.sub(pattern, '', content_str, flags=re.MULTILINE)
                        self.stats['boxes_removed'] += len(matches)
                except Exception as e:
                    logger.error(f"Error processing pattern {pattern}: {e}")
                    continue
            
            # Only encode if content was modified
            if len(content_str) != original_length:
                logger.debug(f"Content modified: original size {original_length}, new size {len(content_str)}")
                return content_str.encode('latin1')
            return content
            
        except Exception as e:
            logger.error(f"Failed to process content: {e}")
            return content
    
    @log_exceptions
    def process_content_stream(self, stream, stream_id=None) -> bool:
        """Process a single content stream, returns True if modified."""
        try:
            stream = self._safe_get_object(stream)
            if not isinstance(stream, pikepdf.Stream):
                return False
                
            # Get unique object identifier
            if stream_id is None:
                stream_id = self.get_object_id(stream, 'stream_')
            logger.debug(f"Processing content stream {stream_id}")
            if stream_id in self.processed_objects:
                logger.debug(f"Content stream {stream_id} was previously processed")
                return False
            self.processed_objects.add(stream_id)
            
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
                
        except Exception as e:
            logger.error(f"Failed to process content stream: {e}")
            return False
            
    @log_exceptions
    def process_page(self, page, page_num: int) -> None:
        """Process a single PDF page."""
        try:
            # Get unique object identifier
            page_id = self.get_object_id(page, f'page_{page_num}_')
            logger.info(f"Processing page {page_num} (ID: {page_id})")
            
            if page_id in self.processed_objects:
                logger.debug(f"Page {page_num} was previously processed")
                return
                
            self.processed_objects.add(page_id)
            
            # Process page resources first
            if page.get('/Resources'):
                self._process_resources(page['/Resources'])
            
            # Process page content
            contents = page.get('/Contents')
            if contents is None:
                return
                
            # Handle both single stream and array of streams
            if isinstance(contents, pikepdf.Array):
                for stream in contents:
                    self.process_content_stream(stream)
            else:
                self.process_content_stream(contents)
                
            self.stats['pages_processed'] += 1
            
            # Free memory after processing each page
            gc.collect()
            
        except Exception as e:
            logger.error(f"Failed to process page {page_num}: {e}")
            
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
                logger.debug(f"safe_get_dict_item: Not a dictionary, got {type(pdf_dict)}")
                return None
                
            if key not in pdf_dict:
                logger.debug(f"safe_get_dict_item: Key {key} not found in dictionary")
                return None
                
            item = pdf_dict.get(key)
            logger.debug(f"safe_get_dict_item: Retrieved item of type {type(item)} for key {key}")
            return self._safe_get_object(item)
        except Exception as e:
            logger.debug(f"Could not get dictionary item {key}: {str(e)}")
            return None
    
    @log_exceptions
    def _process_resources(self, resources) -> None:
        """Process PDF resource dictionary."""
        try:
            resources = self._safe_get_object(resources)
            if not isinstance(resources, pikepdf.Dictionary):
                return
                
            # Get unique object identifier
            res_id = self.get_object_id(resources, 'res_')
            logger.debug(f"Processing resources {res_id}")
            if res_id in self.processed_objects:
                logger.debug(f"Resources {res_id} were previously processed")
                return
            self.processed_objects.add(res_id)
            
            # Process Form XObjects
            xobjects = resources.get('/XObject')
            if isinstance(xobjects, pikepdf.Dictionary):
                try:
                    # Get all keys first to avoid modification during iteration
                    xobject_keys = list(xobjects.keys())
                    logger.debug(f"Processing XObjects: {xobject_keys}")
                    
                    # Process form XObjects first (usually prefixed with Fm or FXX)
                    form_keys = [k for k in xobject_keys if k.startswith('/Fm') or k.startswith('/FXX')]
                    for key in form_keys:
                        try:
                            xobject = xobjects.get(key)
                            if xobject is not None:
                                # Check subtype before processing
                                subtype = xobject.get('/Subtype')
                                if subtype == '/Form':
                                    logger.debug(f"Processing Form XObject: {key}")
                                    self._process_form_xobject(xobject)
                                else:
                                    logger.debug(f"Skipping non-Form XObject: {key} (subtype: {subtype})")
                        except Exception as e:
                            logger.debug(f"Skipping problematic XObject {key}: {str(e)}")
                            
                    # Skip image XObjects (usually prefixed with Im)
                    image_keys = [k for k in xobject_keys if k.startswith('/Im')]
                    if image_keys:
                        logger.debug(f"Skipping Image XObjects: {image_keys}")
                        
                except Exception as e:
                    logger.debug(f"Error processing XObjects: {str(e)}")
            
            # Process ExtGState for soft masks
            extgstate = resources.get('/ExtGState')
            if isinstance(extgstate, pikepdf.Dictionary):
                try:
                    gstate_keys = list(extgstate.keys())
                    for key in gstate_keys:
                        try:
                            gstate = extgstate.get(key)
                            if isinstance(gstate, pikepdf.Dictionary) and '/SMask' in gstate:
                                logger.debug(f"Processing SMask in ExtGState: {key}")
                                self._process_form_xobject(gstate['/SMask'])
                        except Exception as e:
                            logger.debug(f"Skipping problematic ExtGState {key}: {str(e)}")
                except Exception as e:
                    logger.debug(f"Error processing ExtGState: {str(e)}")
                        
        except Exception as e:
            logger.error(f"Failed to process resources: {str(e)}")
    
    @log_exceptions
    def _process_form_xobject(self, xobject) -> None:
        """Process a Form XObject and its resources."""
        xobject = self._safe_get_object(xobject)
        if not isinstance(xobject, pikepdf.Stream):
            return
            
        # Get unique object identifier for the Form XObject
        obj_id = self.get_object_id(xobject, 'form_')
        logger.debug(f"Processing Form XObject {obj_id}")
        if obj_id in self.processed_objects:
            logger.debug(f"XObject {obj_id} was previously processed")
            return
        self.processed_objects.add(obj_id)
        self.stats['objects_processed'] += 1
        
        # Process resources first
        if xobject.get('/Resources'):
            logger.debug(f"Processing resources for XObject {obj_id}")
            self._process_resources(xobject['/Resources'])
        
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
            stream_id = self.get_object_id(stream, 'stream_')
        logger.debug(f"Processing content stream {stream_id}")
        if stream_id in self.processed_objects:
            logger.debug(f"Content stream {stream_id} was previously processed")
            return False
        self.processed_objects.add(stream_id)
        self.stats['objects_processed'] += 1
        
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
