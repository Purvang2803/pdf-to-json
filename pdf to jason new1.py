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

def find_first_match(text, patterns):
    matches = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            match_val = match.group(1) if match.lastindex else match.group(0)
            matches.append(match_val)
    return max(matches, key=len) if matches else ""


def extract_invoice_number(text):
    patterns = [
        r'\b[A-Z]{2,10}/\d{1,6}/\d{2,4}-\d{2,4}\b',       
        r'\b[A-Z]{1,5}[-/]?\d{1,6}/\d{2}-\d{2}\b',
        r'\b\S+/[0-9]{2}-[0-9]{2}/[0-9]+\b',
        r'\b[A-Z0-9]+/[0-9]{4}-[0-9]{2}\b',
        r'\b[A-Z0-9]+/[0-9]{2}-[0-9]{2}\b',
        r'\b[A-Z]?\d{1,6}/\d{2,4}-\d{2,4}\b',
        r'Invoice No\.\s*([A-Z0-9/-]+)',
        r'Invoice\s*No\.?\s*[:\-]?\s*([A-Z0-9/-]+)',
        r'Invoice No\.\s*([A-Z0-9]+)',
        r'Invoice No\.\s*([0-9]+)'
    ]
    return find_first_match(text, patterns)



def extract_invoice_date(text):
    match = re.search(r'\b\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}\b', text)
    return match.group(0) if match else ""


def extract_products_block(text):
    # Updated start markers to match this invoice's format
    start_markers = ["Sl Description of", "Sl Particulars Amount", "Sl Particulars", 
                    "Sl Description of Goods", "No. Goods and Services"]
    end_markers = ["OUTPUT", "Out-Put", "TOTAL", "S-GST", "C-GST", "IGST", 
                  "Grand Total", "Payable Amount", "SGST", "CGST", "Amount Chargeable"]

    start = -1
    for marker in start_markers:
        start = text.find(marker)
        if start != -1:
            break

    if start == -1:
        return ""

    end = min((text.find(marker, start) for marker in end_markers if text.find(marker, start) != -1), 
          default=len(text))
    return text[start:end].strip()


def extract_products(products_block):
    lines = products_block.split("\n")
    products = []
    seen = set()
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        parts = line.split()

        if len(parts) >= 3 and parts[0].isdigit():
            try:
                product_info = parse_product_line(parts)
                if product_info:
                    key = (product_info["product_number"], product_info["product_name"], product_info["amount"])
                    if key not in seen:
                        seen.add(key)

                        description_lines = []
                        j = i + 1
                        while j < len(lines):
                            next_line = lines[j].strip()

                            if (
                                re.match(r"^\d+\s", next_line) or
                                re.search(r"(Total\s₹?|Grand Total|SGST|CGST|IGST|Amount Chargeable|"
                                        r"HSN/SAC|E\. & O\.E|continued to page|SUBJECT TO|INVOICE|"
                                        r"Authorised Signatory|Discount Allowed|Round Off|Less\s*:?|"
                                        r"Out-?Put|^\(?-?[0-9,]+\.\d{2}\)?$)",next_line, re.IGNORECASE)): break

                            if not next_line or re.match(r"^\s*\d+(\.\d+)?\s*$", next_line):
                                j += 1
                                continue

                            description_lines.append(next_line)
                            j += 1

                        if description_lines:
                            clean_desc = " | ".join(description_lines).strip(" |")
                            product_info["description"] = clean_desc

                        products.append(product_info)
                        i = j
                        continue
            except Exception as e:
                print(f"Error parsing line: {line}\n{e}")
        i += 1

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
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<amount>[0-9,]+\.\d{2})\s+(?P<hsn>\d+)$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>[A-Za-z0-9\- ]+?)\s+(?P<amount>[0-9,]+\.\d{2})pcs(?P<rate>[0-9,]+\.\d{2})(?P<quantity>[0-9.]+)\s+pcs(?P<gst>\d+)\s*%(?P<hsn>\d+)$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>[A-Za-z0-9\- ]+)\s+(?P<hsn>\d+)\s+(?P<gst>\d+)\s+%\s+(?P<quantity>[0-9.]+)\s+pcs\s+(?P<rate>[0-9,]+\.\d{2})\s+pcs\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<name1>\S+)\s+(?P<size>\S+)\s+\((?P<sp>SP\s*-\s*\d+)\)\s+(?P<hsn>\d+)\s+(?P<qty>\d+)\s+Pcs\s+(?P<rate>[0-9,]+\.\d{2})\s+Pcs\s+(?P<amount>[0-9,]+\.\d{2})$"),
        re.compile(r"^(?P<number>\d+)\s+(?P<desc>.+?)\s+(?P<amount>[0-9,]+\.\d{2})\s+(?P<gst>\d+)\s+%\s+(?P<hsn>\d+)$")
    
    ]

    for pattern in patterns:
        match = pattern.match(line)
        if match:
            g = match.groupdict()
            desc = g.get("desc", "").strip()
            size = g.get("size", "").strip()
            product_name = f"{g.get('name1', '')} {g.get('size', '')} ({g.get('sp', '')})".strip()

            
            desc_clean = re.sub(r'\s+', ' ', desc).strip()
            if " (" in desc_clean:
                main_name, bracket = desc_clean.split(" (", 1)
                product_name = main_name.strip()
                description = "(" + bracket.strip()
            else:
                product_name = desc_clean
                description = ""
            
            return {
                "product_number": g.get("number"),
                "product_name": product_name,
                "description": "",
                "hsn_sac": g.get("hsn"),
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
    # Calculate the total of all product amounts
    product_total = sum(float(p.get("amount", "0").replace(",", "")) for p in invoice_data.get("products", []))
    
    # Extract discount information (percentage or fixed amount)
    discount_percent_match = re.search(r'Trade Discount.*?([\d.]+)\s*%', text, re.IGNORECASE)
    discount_amount_match = re.search(r'Trade Discount.*?([\d,]+\.\d{2})', text, re.IGNORECASE)
    
    if discount_percent_match:
        discount_percent = float(discount_percent_match.group(1))
        discount_amount = round(product_total * discount_percent / 100, 2)
    elif discount_amount_match:
        discount_amount = float(discount_amount_match.group(1).replace(",", ""))
    else:
        discount_amount = 0.0
    
    invoice_data['discount'] = f"{discount_amount:.2f}"
    
    # Calculate taxable amount (after discount)
    taxable_amount = product_total - discount_amount
    invoice_data['total'] = f"{taxable_amount:.2f}"

    # Extract tax values - handle both percentage and fixed amounts
    tax_labels = {
        'cgst': ['CGST', 'C-GST', 'OUTPUT CGST'],
        'sgst': ['SGST', 'S-GST', 'OUTPUT SGST'], 
        'igst': ['IGST']
    }

    for tax_type, labels in tax_labels.items():
        tax_amount = 0.0
        tax_found = False
        
        # First try to find percentage
        for label in labels:
            percent_match = re.search(rf'{label}.*?([\d.]+)\s*%', text, re.IGNORECASE)
            if percent_match:
                percentage = float(percent_match.group(1))
                tax_amount = round(taxable_amount * percentage / 100, 2)
                tax_found = True
                break
        
        # If percentage not found, try to find fixed amount
        if not tax_found:
            for label in labels:
                amount_match = re.search(rf'{label}\s*(?:@\s*[\d.]+\s*%?\s*)?(?:₹)?\s*([\d,]+\.\d{{2}})', text, re.IGNORECASE)
                if amount_match:
                    tax_amount = float(amount_match.group(1).replace(",", ""))
                    tax_found = True
                    break
        
        invoice_data[tax_type] = f"{tax_amount:.2f}"

    # Handle round off if present
    round_off_match = re.search(r'Round\s*Off\s*([\d.,+-]+)', text, re.IGNORECASE)
    round_off = float(round_off_match.group(1).replace(",", "")) if round_off_match else 0.0

    # Calculate grand total
    cgst = float(invoice_data.get("cgst", "0"))
    sgst = float(invoice_data.get("sgst", "0"))
    igst = float(invoice_data.get("igst", "0"))
    
    grand_total = taxable_amount + cgst + sgst + igst + round_off
    invoice_data['grand_total'] = f"{grand_total:.2f}"

def extract_discount_amount(text):
    match = re.search(r'Discount\s+A/c\s+\(?-?\)?₹?\(?([0-9,]+\.\d{2})\)?', text, re.IGNORECASE)
    if match:
        return match.group(1).replace(",", "").strip()
    return "0"


def get_tax_value_in_rupees(text, labels, subtotal):
    for label in labels:
        # Match both percentage and rupee value like: CGST @ 2.5% 2,024.44
        match = re.search(
            rf'{label}.*?@?\s*[0-9]+\.\d+\s*%.*?([0-9,]+\.\d{{2}})', text, re.IGNORECASE)
        if match:
            value = match.group(1).replace(",", "")
            return float(value)

    for label in labels:
        # Fallback to percentage only if rupee value not found
        percent_match = re.search(
            rf'{label}.*?([0-9]+\.\d+)\s*%', text, re.IGNORECASE)
        if percent_match:
            percentage = float(percent_match.group(1))
            return round(subtotal * (percentage / 100),2)

    return 0.00




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

pdf_path = r"C:\Users\DELL8\Downloads\Sales_SAC_24-25_519.pdf"
output_path = "parsed_invoice.json"

invoice_data = extract_invoice_details(pdf_path)
save_to_json(invoice_data, output_path)
print(json.dumps(invoice_data, indent=4))
