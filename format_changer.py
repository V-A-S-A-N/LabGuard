import json
import re

def load_filtered_usb_products(filename, keywords=None):
    """
    Parse the usb.ids file and return a list of dictionaries containing
    product IDs and product names for products whose names match one of the keywords.
    The usb.ids file is hierarchical (vendor lines followed by product lines),
    so this function ignores vendor lines and only collects product entries.
    
    Each product entry in the output list is in the form:
      {"id": "product_id", "name": "product_name"}
    
    Parameters:
      - filename: path to the usb.ids file.
      - keywords: list of keywords to filter product names (case-insensitive).
                  Default: ["keyboard", "mouse", "headset", "headphone"]
    """
    if keywords is None:
        keywords = ["keyboard", "mouse", "headset", "headphone"]
    # Convert keywords to lowercase for case-insensitive matching.
    keywords = [kw.lower() for kw in keywords]
    
    products = []
    current_vendor = None  # We'll ignore vendor info in output.
    try:
        with open(filename, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Remove trailing whitespace.
                line = line.rstrip("\n")
                # Skip empty lines or comments.
                if not line or line.startswith("#"):
                    continue
                # Vendor lines: no leading whitespace.
                if not line.startswith("\t"):
                    # Reset current vendor.
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        current_vendor = parts[0].lower()  # Vendor ID (unused here)
                    continue
                # Product lines: should start with a tab.
                stripped_line = line.lstrip("\t")
                parts = stripped_line.split(None, 1)
                if len(parts) != 2 or current_vendor is None:
                    continue
                product_id, product_name = parts
                product_id = product_id.lower()
                product_name_str = product_name.strip()
                # Filter by keywords: if any keyword is in the product name (lowercase), keep it.
                if any(kw in product_name_str.lower() for kw in keywords):
                    products.append({"id": product_id, "name": product_name_str})
    except Exception as e:
        print(f"Error reading file: {e}")
    return products

if __name__ == "__main__":
    input_filename = "usb.ids.txt"  # Your downloaded file
    output_filename = "filtered_usb_products.json"
    filtered_products = load_filtered_usb_products(input_filename)
    try:
        with open(output_filename, "w", encoding="utf-8") as outfile:
            json.dump(filtered_products, outfile, indent=2)
        print(f"Filtered USB products written to {output_filename}")
    except Exception as e:
        print(f"Error writing output file: {e}")
