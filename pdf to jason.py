


import os
import json
import pdfplumber
import re
import spacy
import pytesseract
from pdf2image import convert_from_path
from num2words import num2words

# Load NLP model
nlp = spacy.load("en_core_web_sm")

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF. Uses OCR if no extractable text found."""
    extracted_text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    extracted_text += text + "\n"
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
    
    if not extracted_text.strip():
        print(f"OCR fallback for scanned PDF: {pdf_path}")
        images = convert_from_path(pdf_path)
        for img in images:
            extracted_text += pytesseract.image_to_string(img) + "\n"

    return extracted_text.strip()

def convert_number_to_words(number):
    """Converts a numeric amount to words."""
    try:
        number = float(number)
        return num2words(number, to="currency", lang="en_IN").replace("euro", "rupees").replace(",", "").replace(" and ", " ") + " only"
    except:
        return None

def extract_products_from_pdf(pdf_path):
    """Attempts to extract product rows from invoice tables."""
    products = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    headers = table[0]
                    for row in table[1:]:
                        if len(row) < 3: continue
                        if any(re.search(r"(Qty|Rate|Amount|HSN)", str(cell), re.IGNORECASE) for cell in headers):
                            products.append(dict(zip(headers, row)))
    except Exception as e:
        print(f"Error extracting products from {pdf_path}: {e}")
    return products

def extract_invoice_data(text):
    """Extracts invoice details using regex and NLP."""
    data = {
        "invoice_number": None,
        "invoice_date": None,
        "buyer_details": None,
        "total": None,
        "tax_details": {"cgst": None, "sgst": None, "igst": None},
        "tax_amount_in_words": None,
        "products": []
    }

    # Invoice Number
    patterns = [
        r"(?:Invoice\s*No\.?|Inv\. No\.?|Invoice #:?)\s*([A-Z0-9\/\-]+)",
        r"([\d]{5}\/[\d]{4}-[\d]{2})"
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            data["invoice_number"] = match.group(1).strip()
            break

    # Invoice Date
    date_patterns = [
        r"(?:Invoice Date|Dated)[:\s]*([\d]{1,2}[\/\-][A-Za-z]{3}[\/\-][\d]{2,4})",
        r"(?:Invoice Date|Dated)[:\s]*([\d]{2}[\/\-][\d]{2}[\/\-][\d]{2,4})"
    ]
    for pat in date_patterns:
        match = re.search(pat, text)
        if match:
            data["invoice_date"] = match.group(1).strip()
            break

    # Buyer Details
    buyer_patterns = [
        r"Bill To\s+([\s\S]+?)\s+(Place of Supply|GSTIN)",
        r"Buyer\s*\(Bill to\)\s*([\s\S]+?)\s+GSTIN",
        r"Consignee\s*\(Ship to\)\s*([\s\S]+?)\s+GSTIN",
        r"PKRJ AND ASSOCIATES\s+([\s\S]+?)\s+India"
    ]
    for pat in buyer_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            data["buyer_details"] = re.sub(r"\s+", " ", match.group(1).strip()).replace("Terms of Delivery ", "").strip()
            break

    # Total Amount
    total_patterns = [
        r"Total\s+₹?\s*([\d,]+\.\d+)",
        r"Amount of Payment\s*₹?([\d,]+\.\d+)",
        r"Grand Total\s*[:\s]*₹?([\d,]+\.\d+)",
        r"Total Amount\s*[:₹]*\s*([\d,]+\.\d+)"
    ]
    for pat in total_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            data["total"] = match.group(1).replace(",", "").strip()
            break

    # Tax Details
    tax_patterns = {
        "cgst": [r"CGST\s*\d+\.\d+%\s*₹?\s*([\d,]+\.\d+)"],
        "sgst": [r"SGST\s*\d+\.\d+%\s*₹?\s*([\d,]+\.\d+)"],
        "igst": [r"IGST\s*\d+\.\d+%\s*₹?\s*([\d,]+\.\d+)"]
    }
    for tax, pats in tax_patterns.items():
        for pat in pats:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                data["tax_details"][tax] = match.group(1).replace(",", "").strip()
                break

    # Convert total to words
    if data["total"]:
        data["tax_amount_in_words"] = convert_number_to_words(data["total"])

    return data

def process_single_pdf(pdf_path):
    """Processes one PDF and saves extracted data to a JSON file."""
    if not os.path.exists(pdf_path):
        print(" File not found!")
        return

    print(f" Processing: {pdf_path}")
    text = extract_text_from_pdf(pdf_path)
    invoice_data = extract_invoice_data(text)
    invoice_data["products"] = extract_products_from_pdf(pdf_path)

    output_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".json"
    output_path = os.path.join(os.path.dirname(pdf_path), output_filename)
    with open(output_path, "w") as f:
        json.dump(invoice_data, f, indent=4)

    print(f" Extracted data saved to {output_filename}")
    return invoice_data

if __name__ == "__main__":
    pdf_path = r"D:\DELL8\Documents\pdftodata\example.pdf" 
    output = process_single_pdf(pdf_path)
    print(json.dumps(output, indent=4))






