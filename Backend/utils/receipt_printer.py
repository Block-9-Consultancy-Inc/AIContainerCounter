#!/usr/bin/env python3

import os
import subprocess
import tempfile
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import qrcode

# Configuration
REFUND_RATE = 0.1  # Adjust as needed
COLUMN_WIDTH_14_FONT = 36  # Adjust based on font
COLUMN_WIDTH_12_FONT = 42  # Adjust based on font
PRINTER_NAME = 'EPSON_TM-T20II'  # Your printer name

def divider(width):
    """Create a divider string of dots"""
    return '.' * max(0, width)

def create_receipt_pdf(transaction_id, transaction_type, total_count, categories, refund_total):
    """Create a PDF receipt similar to the Node.js version"""
    
    # Create temporary file
    # temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
    # os.close(temp_fd)
    temp_path = 'test.pdf'
    
    try:        
        # Create canvas for direct drawing (more control like PDFDocument)
        c = canvas.Canvas(temp_path, pagesize=(350, 650))
        
        # Try to register monospace font (fallback to Courier if not available)
        try:
            # You would need to have these font files available
            pdfmetrics.registerFont(TTFont('RobotoMono-Bold', 'resources/Roboto_Mono/static/RobotoMono-Bold.ttf'))
            pdfmetrics.registerFont(TTFont('RobotoMono-Regular', 'resources/Roboto_Mono/RobotoMono-VariableFont_wght.ttf'))
            bold_font = 'RobotoMono-Bold'
            regular_font = 'RobotoMono-Regular'
        except:
            bold_font = 'Courier-Bold'
            regular_font = 'Courier'
        
        # Starting Y position
        y_position = 590
        
        # Add company logo (if exists)
        if os.path.exists('resources/recyclorobo-logo.png'):
            logo_width = 200
            logo_x = (350 - logo_width) / 2
            c.drawImage('resources/recyclorobo-logo.png', logo_x, y_position, width=logo_width, height=20, mask='auto')
            y_position -= 70
        
        # Transaction ID
        c.setFont(bold_font, 14)
        transaction_text = f"Transaction ID"
        id_divider_width = COLUMN_WIDTH_14_FONT - len(transaction_text) - 1
        transaction_line = f"{transaction_text} {divider(id_divider_width)}"
        c.drawString(25, y_position, transaction_line)
        y_position -= 15

        c.setFont(regular_font, 12)
        id_divider_width = COLUMN_WIDTH_12_FONT - len(transaction_id) - 1
        transaction_line = f"{transaction_id} {divider(id_divider_width)}"
        c.drawString(25, y_position, transaction_line)
        y_position -= 15

        transaction_type_width = COLUMN_WIDTH_12_FONT - len('Transaction Type') - len(transaction_type) - 2
        transaction_type_line = f"Transaction Type {divider(transaction_type_width)} {transaction_type}"
        c.drawString(25, y_position, transaction_type_line)
        y_position -= 25

        
        # Categories (commented out in original, but here's the implementation)
        c.setFont(regular_font, 12)
        for category, count in categories.items():
            count_str = str(count)
            category_divider_width = COLUMN_WIDTH_12_FONT - len(category) - len(count_str) - 2
            category_line = f"{category} {divider(category_divider_width)} {count_str}"
            c.drawString(25, y_position, category_line)
            y_position -= 15
        
        y_position -= 10
        
        # Total
        c.setFont(bold_font, 14)
        total_text = "Total"
        total_count_str = str(total_count)
        total_divider_width = COLUMN_WIDTH_14_FONT - len(total_text) - len(total_count_str) - 2
        total_line = f"{total_text} {divider(total_divider_width)} {total_count_str}"
        c.drawString(25, y_position, total_line)
        y_position -= 18
        
        # Total Refund
        refund_text = "Total Refund"
        refund_str = f"${refund_total}"
        refund_divider_width = COLUMN_WIDTH_14_FONT - len(refund_text) - len(refund_str) - 2
        refund_line = f"{refund_text} {divider(refund_divider_width)} {refund_str}"
        c.drawString(25, y_position, refund_line)
        y_position -= 25
        
        # Date and Time
        c.setFont(regular_font, 12)
        now = datetime.now()
        date_string = now.strftime("%m/%d/%Y")
        time_string = now.strftime("%I:%M:%S %p")
        
        date_text = "Date"
        date_divider_width = COLUMN_WIDTH_12_FONT - len(date_text) - len(date_string) - 2
        date_line = f"{date_text} {divider(date_divider_width)} {date_string}"
        c.drawString(25, y_position, date_line)
        y_position -= 15
        
        time_text = "Time"
        time_divider_width = COLUMN_WIDTH_12_FONT - len(time_text) - len(time_string) - 2
        time_line = f"{time_text} {divider(time_divider_width)} {time_string}"
        c.drawString(25, y_position, time_line)
        y_position -= 25
        
        # Thank you message (centered)
        c.drawString(25, y_position, '                  ')
        y_position -= 25
        thank_you_text = "Thank you for recycling!"
        text_width = c.stringWidth(thank_you_text, regular_font, 12)
        center_x = (350 - text_width) / 2
        c.drawString(center_x, y_position, thank_you_text)
        y_position -= 25
        c.drawString(25, y_position, '                  ')
        y_position -= 15
        c.drawString(25, y_position, '                  ')
        y_position -= 15
        
        # QR Code (if exists)
        qr_code = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            border=0,
        )
        qr_code.add_data(transaction_id)
        qr_code.make(fit=True)
        qr_code_image = qr_code.make_image()
        qr_size = 200
        qr_x = (350 - qr_size) / 2
        qr_code_image.get_image().save('qr_code.jpeg', format='JPEG')

        # Get the byte string from the BytesIO object
        c.drawImage('qr_code.jpeg', qr_x, y_position - qr_size, width=qr_size, height=qr_size, mask='auto')
        os.unlink('qr_code.jpeg')
        
        # Save the PDF
        c.save()
        
        return temp_path
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise e

def print_pdf_with_lpr(file_path, printer_name=None):
    """Print PDF using lpr command"""
    try:
        cmd = ['lpr']
        
        # Add printer name if specified
        if printer_name:
            cmd.extend(['-P', printer_name])
        
        # Add the file to print
        cmd.append(file_path)
        
        # Execute the command
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        return True, "Print job submitted successfully"
        
    except subprocess.CalledProcessError as e:
        return False, f"Print command failed: {e.stderr}"
    except Exception as e:
        return False, f"Error printing: {str(e)}"

# Alternative function for direct use (without Flask)
def print_receipt(transaction_id, transaction_type, categories, printer_name=None):
    """
    Direct function to print receipt without Flask
    
    Args:
        transaction_number (int): Transaction ID
        total_count (int): Total count of items
        categories (dict): Dictionary of categories and their counts
        printer_name (str): Optional printer name
    
    Returns:
        tuple: (success: bool, message: str, refund_total: str)
    """
    try:
        total_count = sum(categories.values())
        # Calculate refund total
        refund_total = f"{(total_count * REFUND_RATE):.2f}"
        
        # # Create PDF
        pdf_path = create_receipt_pdf(transaction_id, transaction_type, total_count, categories, refund_total)
        
        # Print PDF
        success, message = print_pdf_with_lpr(pdf_path, printer_name or PRINTER_NAME)
        # success, message = True, 'Print job successfully'
        # Clean up temporary file
        os.unlink(pdf_path)
        
        return success, message, refund_total
        
    except Exception as e:
        return False, f"Error: {str(e)}", "0.00"

# Example usage
if __name__ == '__main__':
    # Example of direct usage
    sample_categories = {
        'can': 120,
        'plastic': 100,
        'drinkbox': 50,
        'gabletop': 50,
        'pouch': 100
    }
    
    success, message, refund_total = print_receipt(
        transaction_id='e7258a64-ba09-4982-b7a1-c68b77b82f67',
        transaction_type='Express',
        categories=sample_categories,
        printer_name='EPSON_TM-T20II'
    )
    
    print(f"Success: {success}")
    print(f"Message: {message}")
    print(f"Refund Total: ${refund_total}")