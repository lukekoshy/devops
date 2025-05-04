import os
import logging
import subprocess
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def convert_word_to_pdf(input_path, output_path=None):
    """
    Convert a Word document to PDF using LibreOffice or Microsoft Word
    Args:
        input_path (str): Path to the input Word document
        output_path (str, optional): Path for the output PDF file
    Returns:
        str: Path to the converted PDF file
    """
    try:
        # Generate output PDF path if not provided
        if output_path is None:
            output_path = os.path.splitext(input_path)[0] + '.pdf'

        if sys.platform.startswith('win'):
            # Use docx2pdf on Windows
            from docx2pdf import convert
            import pythoncom
            pythoncom.CoInitialize()
            try:
                convert(input_path, output_path)
            finally:
                pythoncom.CoUninitialize()
        else:
            # Use LibreOffice on Linux/Unix
            input_file = Path(input_path).absolute()
            output_dir = Path(output_path).parent.absolute()
            
            # Convert using LibreOffice
            cmd = [
                'libreoffice',
                '--headless',
                '--convert-to',
                'pdf',
                '--outdir',
                str(output_dir),
                str(input_file)
            ]
            
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            if process.returncode != 0:
                raise Exception(f"LibreOffice conversion failed: {process.stderr}")
        
        logger.info(f"Successfully converted {input_path} to {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"Error converting {input_path} to PDF: {str(e)}")
        raise 