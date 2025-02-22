"""Streamlit UI for PDF Box Eraser."""
import streamlit as st
import tempfile
import os
from typing import Callable, Dict
from pdf_box_eraser.core.pdf_processor import PDFProcessor

class PDFBoxEraserUI:
    """Handles the Streamlit UI for PDF Box Eraser."""
    
    def __init__(self):
        """Initialize the UI components."""
        st.title("PDF Box Eraser")
        st.write("Upload a PDF file to remove unwanted rectangular boxes while preserving content")
    
    def create_progress_components(self):
        """Create and return progress tracking components."""
        progress_container = st.container()
        stats_container = st.container()
        
        with progress_container:
            st.markdown("#### Processing Progress")
            progress_bar = st.progress(0)
            progress_text = st.empty()
        
        with stats_container:
            st.markdown("#### Processing Statistics")
            col1, col2, col3 = st.columns(3)
            pages_stat = col1.empty()
            boxes_stat = col2.empty()
            objects_stat = col3.empty()
            
        return progress_bar, progress_text, pages_stat, boxes_stat, objects_stat
    
    def create_progress_callback(self, progress_components) -> Callable:
        """Create a callback function for progress updates."""
        progress_bar, progress_text, pages_stat, boxes_stat, objects_stat = progress_components
        
        def update_progress(progress: float, stats: Dict):
            progress_bar.progress(progress)
            progress_text.markdown(f"**Progress:** {progress * 100:.1f}%")
            
            pages_stat.markdown(
                f"""
                📄 **Pages**
                {stats['pages_processed']} processed
                """
            )
            boxes_stat.markdown(
                f"""
                📦 **Boxes**
                {stats['boxes_removed']} removed
                """
            )
            objects_stat.markdown(
                f"""
                🔍 **Objects**
                {stats['objects_processed']} processed
                """
            )
        
        return update_progress
    
    def display_page_preview(self, original_images, processed_images, start_page):
        """Display side-by-side preview of original and processed pages."""
        for i, (orig_img, proc_img) in enumerate(zip(original_images, processed_images)):
            st.write(f"Page {start_page + i}")
            col1, col2 = st.columns(2)
            
            with col1:
                st.write("Original")
                st.image(orig_img, use_container_width=True)
            
            with col2:
                st.write("Processed")
                st.image(proc_img, use_container_width=True)
    
    def display_stats(self, stats):
        """Display processing statistics."""
        st.write("### Processing Statistics")
        
        # Create two rows of metrics
        row1_col1, row1_col2, row1_col3 = st.columns(3)
        row2_col1, row2_col2 = st.columns([2, 1])
        
        with row1_col1:
            st.metric("Pages Processed", stats['pages_processed'])
        
        with row1_col2:
            st.metric("Pages Skipped", stats['pages_skipped'])
        
        with row1_col3:
            st.metric("Boxes Removed", stats['boxes_removed'])
        
        with row2_col1:
            st.metric("Box Patterns Found", stats['quick_matches'])
        
        with row2_col2:
            st.metric("Objects Processed", stats['objects_processed'])
        
        # Show progress bar
        total_pages = stats['pages_processed'] + stats['pages_skipped']
        if total_pages > 0:
            progress = stats['pages_processed'] / total_pages
            st.progress(progress)
            st.text(f"Progress: {progress:.1%}")
    
    def handle_file_upload(self):
        """Handle PDF file upload and processing."""
        uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'])
        
        if uploaded_file is None:
            return
            
        try:
            # Save uploaded file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_input:
                tmp_input.write(uploaded_file.getvalue())
                input_path = tmp_input.name
            
            processor = PDFProcessor()
            total_pages = processor.get_total_pages(input_path)
            
            # Page range selection
            st.write(f"Total pages in PDF: {total_pages}")
            start_page, end_page = self.get_page_range(total_pages)
            
            if st.button("Process PDF"):
                progress_components = self.create_progress_components()
                progress_callback = self.create_progress_callback(progress_components)
                
                with st.spinner('Processing PDF...'):
                    # Process PDF
                    output_path = processor.process_pdf_file(
                        input_path, 
                        start_page, 
                        end_page,
                        progress_callback
                    )
                    
                    # Generate and display previews
                    original_images = processor.convert_pdf_to_images(
                        input_path,
                        start_page,
                        end_page
                    )
                    processed_images = processor.convert_pdf_to_images(
                        output_path,
                        start_page,
                        end_page
                    )
                    
                    st.success("Processing complete!")
                    self.display_page_preview(original_images, processed_images, start_page)
                    
                    # Create download button
                    with open(output_path, 'rb') as f:
                        st.download_button(
                            label="Download processed PDF",
                            data=f.read(),
                            file_name='processed.pdf',
                            mime='application/pdf'
                        )
                    
                    # Cleanup temporary files
                    os.unlink(input_path)
                    os.unlink(output_path)
        
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
    
    def get_page_range(self, total_pages):
        """Get page range selection from user."""
        col1, col2 = st.columns(2)
        
        with col1:
            start_page = st.number_input(
                "Start Page",
                min_value=1,
                max_value=total_pages,
                value=1,
                help="First page to process (1-based index)"
            )
        
        with col2:
            end_page = st.number_input(
                "End Page",
                min_value=start_page,
                max_value=total_pages,
                value=total_pages,
                help="Last page to process (1-based index)"
            )
        
        return start_page, end_page
    
    def run(self):
        """Run the Streamlit application."""
        self.handle_file_upload()

def main():
    app = PDFBoxEraserUI()
    app.run()

if __name__ == "__main__":
    main()
