# PDF Box Eraser

A Streamlit application that removes unwanted black boxes from PDF files.

## Features

- Drag and drop PDF file upload
- Automatic detection and removal of black boxes
- Side-by-side comparison of original and processed pages
- Download processed pages individually
- Support for multi-page PDFs

## Installation

1. Clone this repository
2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the Streamlit app:
```bash
streamlit run app.py
```

2. Open your web browser and navigate to the provided URL
3. Upload a PDF file using the file uploader
4. View the processed results and download the modified pages

## How it works

The application uses:
- `pdf2image` for PDF to image conversion
- `OpenCV` for box detection and removal
- `Streamlit` for the web interface
- `Pillow` for image processing

The box detection algorithm looks for rectangular shapes based on:
- Contour detection
- Area thresholds
- Aspect ratio filtering

## Requirements

See `requirements.txt` for a full list of dependencies.
