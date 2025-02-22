"""Decorators for the PDF Box Eraser application."""
import functools
import logging

logger = logging.getLogger(__name__)

def log_exceptions(func):
    """Decorator to handle and log exceptions.
    
    This decorator provides consistent error handling across the application by:
    1. Logging exceptions with appropriate context
    2. Handling specific function cases differently
    3. Providing appropriate fallback values
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Get the class name if method is part of a class
            class_name = args[0].__class__.__name__ if args else ''
            func_name = f"{class_name}.{func.__name__}" if class_name else func.__name__
            logger.error(f"Failed in {func_name}: {e}")
            
            # Only reraise for specific functions that need it
            if func.__name__ in ['process_pdf', 'main']:
                raise
                
            # Return appropriate default values based on function
            if func.__name__ == 'remove_boxes_from_content':
                return args[1] if len(args) > 1 else None  # Return original content
                
            return None
    return wrapper
