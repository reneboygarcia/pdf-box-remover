![banner](images/banner.webp)

# PDF Box Eraser

A Python-based tool that removes unwanted rectangular boxes from PDF files while preserving the underlying content. Built with Streamlit for an easy-to-use web interface.

## 🚀 Features

- **Box Removal**
  - Remove rectangular boxes, borders, and outlines from PDF files
  - Preserve text, images, and other content
  - Process single or multiple pages
  - Real-time progress tracking
  - Statistics on boxes removed and pages processed
  - Memory-efficient processing of large PDFs
  - User-friendly web interface

## 📋 Requirements

- Python 3.8+
- Dependencies from `requirements.txt`:
  - streamlit
  - pdf2image
  - opencv-python
  - numpy
  - Pillow
  - PyPDF2
  - watchdog
  - pikepdf

See `requirements.txt` for specific version requirements.

## 🛠️ Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/reneboygarcia/pdf-box-eraser
   cd pdf_box_eraser
   ```

2. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 💻 Usage

1. Start the application:
   ```bash
   streamlit run pdf_box_eraser/ui/streamlit_app.py
   ```

2. Upload your files:
   - Drop your PDF files in the upload area

3. Click "Process PDFs" to begin:
   - The app will remove unwanted rectangular boxes from the PDFs
   - Processed PDFs will preserve the underlying content

## Technical Details

- Uses `pikepdf` for low-level PDF manipulation
- Implements pattern matching to identify and remove box-drawing operations
- Handles various PDF structures including Form XObjects and ExtGState
- Manages memory efficiently for large PDFs
- Provides detailed logging for debugging

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This tool is intended for legitimate use only. Users are responsible for ensuring they have the right to access and modify any PDFs they process.
