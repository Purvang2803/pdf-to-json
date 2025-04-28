import pdfplumber
import json
import re

def extract_invoice_details(pdf_path):
    invoice_data = {
        "invoice_no": "",
        "invoice_date": "",
        "products": [],
        "cgst": "",
        "sgst": "",
        "igst": "",
        "total": "",
        "discount": "",
        "grand_total": ""
    }

    full_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += "\n" + text

    invoice_data["invoice_no"] = extract_invoice_number(full_text)
    invoice_data["invoice_date"] = extract_invoice_date(full_text)

    products_block = extract_products_block(full_text)
    if products_block:
        invoice_data["products"] = extract_products(products_block)

    invoice_data["discount"] = extract_discount_amount(full_text)  
    extract_tax_and_totals(full_text, invoice_data)

    return invoice_data


def extract_invoice_number(text):
    patterns = [
        r'\b[A-Z]{3}/\d{4}-\d{2}/\d{4}\b',
        r'\b[A-Z0-9]+/[0-9]{4}-[0-9]{2}\b',
        r'\b[A-Z0-9]+/[0-9]{2}-[0-9]{2}\b',
        r'\b\S+/[0-9]{2}-[0-9]{2}/[0-9]+\b',
        r'\b[A-Z]{1,5}[-/]?\d{1,6}/\d{2}-\d{2}\b',
        r'Invoice No\.\s*([0-9]+)',
        r'Invoice No\.\s*([A-Z0-9/-]+)',
        r'Invoice No\.\s*([A-Z0-9]+)',  
    ]
    invoice_no = find_first_match(text, patterns) 
    return invoice_no


def extract_invoice_date(text):
    match = re.search(r'\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}\b', text)
    return match.group(0) if match else ""


def extract_products_block(text):
    start_markers = ["Sl Description of Goods", "Sl Particulars Amount", "Sl Particulars"]
    end_markers = ["OUTPUT", "Out-Put", "TOTAL", "S-GST", "C-GST", "Grand Total", "Payable Amount"]  # removed "Less"

    start = -1
    for marker in start_markers:
        start = text.find(marker)
        if start != -1:
            break

    if start == -1:
        return ""

    end = min((text.find(marker, start) for marker in end_markers if text.find(marker, start) != -1), default=len(text))
    return text[start:end].strip()


def extract_products(products_block):
    lines = products_block.split("\n")
    products = []
    seen = set()

    for line in lines:
        parts = line.split()
        if len(parts) < 3 or not parts[0].isdigit():
            continue

        try:
            product_info = parse_product_line(parts)
            if product_info:
                
                key = (product_info["product_number"], product_info["product_name"], product_info["amount"])
                if key not in seen:
                    seen.add(key)
                    products.append(product_info)
        except Exception as e:
            print(f"Error parsing line: {line}\n{e}")

    return products



def parse_product_line(parts):
    line = " ".join(parts)
    patterns = [
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d+)\s+(?P<qty>\d+)\s+[A-Z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+[A-Z]+\s+(?P<discount>\d+)\s+%\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d+)\s+(?P<alt_qty>[0-9.]+)\s+[A-Z]+\s+(?P<qty>[0-9.]+)\s+[A-Z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+[A-Z]+\s+(?P<discount>\d+)\s+%\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d{4,})\s+(?P<gst>\d+)\s+%\s+(?P<qty>[0-9.]+)\s+[A-Za-z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+[A-Za-z]+\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d{4,})\s+(?P<qty>\d+)\s+[A-Za-z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+[A-Za-z]+\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d{4,})\s+(?P<alt_qty>\d+)\s+[A-Za-z]+\s+(?P<qty>\d+)\s+[A-Za-z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+[A-Za-z]+\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<wsp>[0-9,]+\.\d{2})\s+(?P<size>\S+)\s+(?P<qty>\d+)\s+[PсС][a-zA-Z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+(?P<discount>\d+)\s+%\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<wsp>[0-9,]+\.\d{2})\s+(?P<size>[0-9xX*/\-]+)\s+(?P<qty>\d+)\s+[PсС][a-zA-Z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+(?P<discount>\d+)\s+%\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d+)\s+(?P<qty>\d+)\s+[A-Z]+\s+(?P<rate>[0-9,]+\.\d{2})\s+[A-Z]+\s+(?P<discount>\d+)%\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<hsn>\d{4,})\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<amount>[0-9,]+\.\d{2})\s+(?P<hsn>\d+)$")
    ]

    for pattern in patterns:
        match = pattern.match(line)
        if match:
            g = match.groupdict()
            desc = g.get("desc", "").strip()
            size = g.get("size", "").strip()
            
            parts = desc.split("-")
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                code = parts[0]
                maybe_size = parts[1] if len(parts) > 2 else ""
                product_name = " - ".join(parts[2:]) if len(parts) > 2 else parts[1]
                description = f"{code} - {maybe_size}".strip(" -")
            else:
                product_name = desc
                description = ""
            return {
                "product_number": g.get("number"),
                "product_name": product_name,
                "description": description,
                "hsn_sac": g.get("hsn", ""),
                "size": size,
                "quantity": g.get("qty", ""),
                "rate": g.get("rate", ""),
                "discount": (g.get("discount", "") + "%") if g.get("discount") else "",
                "wsp": g.get("wsp", ""),
                "amount": g.get("amount", "").replace(",", "")
            }

    print(f"Regex did not match: {line}")
    return None


def extract_tax_and_totals(text, invoice_data):
    product_total = sum(float(p.get("amount", "0").replace(",", "")) for p in invoice_data.get("products", []))
    
    extracted_total = extract_tax(text, r'\bTotal\s*₹?\s*([0-9,]+\.\d{1,2})')
    extracted_total_float = float(extracted_total or "0")
    
    if extracted_total_float < (product_total * 0.8):
        subtotal = product_total
    else:
        subtotal = extracted_total_float

    invoice_data['total'] = f"{subtotal:.2f}"


    cgst_amount = get_tax_value_in_rupees(text, ['CGST', 'C-GST', 'OUTPUT CGST'], subtotal)
    sgst_amount = get_tax_value_in_rupees(text, ['SGST', 'S-GST', 'OUTPUT SGST'], subtotal)
    igst_amount = get_tax_value_in_rupees(text, ['IGST'], subtotal)

    
    cgst = float(cgst_amount or "0")
    sgst = float(sgst_amount or "0")
    igst = float(igst_amount or "0")

    invoice_data['cgst'] = f"{cgst:.2f}"
    invoice_data['sgst'] = f"{sgst:.2f}"
    invoice_data['igst'] = f"{igst:.2f}"

    discount_amount = float(invoice_data.get("discount", "0") or "0")
    
    grand_total = subtotal + cgst + sgst + igst - discount_amount

    invoice_data['grand_total'] = f"{grand_total:.2f}"






def extract_discount_amount(text):
    match = re.search(r'Discount\s+A/c\s+\(?-?\)?₹?\(?([0-9,]+\.\d{2})\)?', text, re.IGNORECASE)
    if match:
        return match.group(1).replace(",", "").strip()
    return "0"


def get_tax_value_in_rupees(text, labels, subtotal):
    """
    Extract tax either directly in rupees or calculate from percentage.
    """
    for label in labels:
        
        rupee_match = re.search(rf'{label}[^\d₹%]*₹\s*([0-9,]+\.\d{{1,2}})', text, re.IGNORECASE)
        if rupee_match:
            return rupee_match.group(1).replace(",", "").strip()

        
        percent_match = re.search(rf'{label}[^\d₹%]*([0-9]+\.\d+|\d+)\s*%', text, re.IGNORECASE)
        if percent_match and subtotal > 0:
            percentage = float(percent_match.group(1))
            tax_in_rupees = subtotal * (percentage / 100)
            return f"{tax_in_rupees:.2f}"

        loose_percent_match = re.search(rf'{label}[^\d₹%]*([0-9]+\.\d+|\d+)\b', text, re.IGNORECASE)
        if loose_percent_match and subtotal > 0:
            percentage = float(loose_percent_match.group(1))
            tax_in_rupees = subtotal * (percentage / 100)
            return f"{tax_in_rupees:.2f}"

    return "0.00"









def extract_tax(text, regex):
    match = re.search(regex, text, re.IGNORECASE | re.MULTILINE)
    if match:
        print(f"Matched Total: {match.group(1)}") 
        return match.group(1).replace(",", "").strip()
    return "0"


def find_first_match(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return ""


def save_to_json(data, output_path):
    with open(output_path, "w") as f:
        json.dump(data, f, indent=4)
    print(f"\n Data saved to: {output_path}")

pdf_path = r"C:\Users\DELL8\Downloads\dugar fashion.pdf"
output_path = "parsed_invoice.json"

invoice_data = extract_invoice_details(pdf_path)
save_to_json(invoice_data, output_path)
print(json.dumps(invoice_data, indent=4))
