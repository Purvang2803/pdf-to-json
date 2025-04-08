


import os
import json
import re
import logging
import pdfplumber
from num2words import num2words

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def extract_text_from_pdf(pdf_path):
    """Extracts text from a PDF using pdfplumber only (no OCR)."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logging.error(f"Error reading PDF: {e}")
    return text.strip()

def convert_number_to_words(number):
    """Converts a number to Indian currency format in words."""
    try:
        number = float(number)
        return num2words(number, to="currency", lang="en_IN").replace("euro", "rupees").replace(",", "").replace(" and ", " ") + " only"
    except:
        return None

def extract_products_from_pdf(pdf_path):
    """Extracts product details from tables in the PDF."""
    products = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    headers = table[0]
                    for row in table[1:]:
                        if len(row) == len(headers):
                            row_dict = dict(zip(headers, row))
                            if any(re.search(r"(Qty|HSN|Amount|Rate|Description)", h, re.IGNORECASE) for h in headers):
                                products.append(row_dict)
    except Exception as e:
        logging.warning(f"Product extraction failed: {e}")
    return products

def extract_invoice_data(text):
    """Extracts structured invoice data from raw text."""
    data = {
        "invoice_number": None,
        "invoice_date": None,
        "buyer_details": None,
        "total": None,
        "grand_total": None,
        "tax_details": {"cgst": None, "sgst": None, "igst": None},
        "tax_amount_in_words": None,
        "products": []
    }

    combined_pattern = re.search(
        r"Invoice\s*No\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)\s+(?:Invoice\s*Date|Date|Dated)?[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})",
        text, re.IGNORECASE
    )
    if combined_pattern:
        num = combined_pattern.group(1).strip()
        dt = combined_pattern.group(2).strip()
        if re.match(r"^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$", dt):
            data["invoice_number"] = num
            data["invoice_date"] = dt

    if not data["invoice_number"]:
        match = re.search(r"Invoice\s*No\.?\s*[:\-]?\s*([A-Z0-9\/\-]+)", text, re.IGNORECASE)
        if match:
            val = match.group(1).strip()
            if val.upper() != "INVOICE":
                data["invoice_number"] = val

    if not data["invoice_date"]:
        match = re.search(r"(?:Date|Dated)?[:\-]?\s*([0-9]{1,2}[\/\-][0-9]{1,2}[\/\-][0-9]{2,4})", text)
        if match:
            val = match.group(1).strip()
            if re.match(r"^\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}$", val):
                data["invoice_date"] = val

    if not data["invoice_number"]:
        logging.warning("Invoice number not found.")
    if not data["invoice_date"]:
        logging.warning("Invoice date not found.")

    buyer_patterns = [
        r"Bill To\s+([\s\S]+?)\s+(Place of Supply|GSTIN)",
        r"Buyer\s*\(Bill to\)\s*([\s\S]+?)\s+GSTIN",
        r"Consignee\s*\(Ship to\)\s*([\s\S]+?)\s+GSTIN",
        r"PKRJ AND ASSOCIATES\s+([\s\S]+?)\s+India"
    ]
    for pat in buyer_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            buyer = match.group(1).strip()
            buyer = re.sub(r"\s+", " ", buyer)
            data["buyer_details"] = buyer
            break
    if not data["buyer_details"]:
        logging.warning("Buyer details not found.")

    total_patterns = [
        r"Total\s+₹?\s*([\d,]+\.\d+)",
        r"Amount of Payment\s*₹?([\d,]+\.\d+)",
        r"Total Amount\s*[:₹]*\s*([\d,]+\.\d+)"
    ]
    for pat in total_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            total = match.group(1).replace(",", "").strip()
            data["total"] = total
            break
    if not data["total"]:
        logging.warning("Total amount not found.")

    # Tax details
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

    try:
        grand_total = float(data["total"]) if data["total"] else 0
        for tax_val in data["tax_details"].values():
            if tax_val:
                grand_total += float(tax_val)
        data["grand_total"] = f"{grand_total:.2f}"
    except Exception as e:
        logging.warning(f"Failed to compute grand total: {e}")

    if data["grand_total"]:
        data["tax_amount_in_words"] = convert_number_to_words(data["grand_total"])

    return data

def process_single_pdf(pdf_path):
    """Main function to process PDF and save structured JSON output."""
    if not os.path.exists(pdf_path):
        logging.error("File not found!")
        return

    logging.info(f"Processing file: {pdf_path}")
    text = extract_text_from_pdf(pdf_path)
    invoice_data = extract_invoice_data(text)
    invoice_data["products"] = extract_products_from_pdf(pdf_path)

    output_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".json"
    output_path = os.path.join(os.path.dirname(pdf_path), output_filename)
    with open(output_path, "w") as f:
        json.dump(invoice_data, f, indent=4)

    logging.info(f"Extracted data saved to: {output_filename}")
    return invoice_data

if __name__ == "__main__":
    pdf_path = r"D:\DELL8\Documents\pdftodata\example.pdf"
    output = process_single_pdf(pdf_path)
    print(json.dumps(output, indent=4))





