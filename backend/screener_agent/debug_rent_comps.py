"""Debug script to test rent comps extraction."""
import sys
import re
sys.path.insert(0, 'modules')
from pdf_extractor import CoStarPDFExtractor

reports_dir = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\CoStar Reports"
pdf_path = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\CoStar Reports\Fieldstone SR.pdf"

extractor = CoStarPDFExtractor(reports_dir)
data = extractor.extract_all()

print("=" * 60)
print("RENT COMPS DATA")
print("=" * 60)

rent_comps = data.get('rent_comps', {})
print(f"Keys in rent_comps: {list(rent_comps.keys())}")

if 'comparable_properties' in rent_comps:
    comps = rent_comps['comparable_properties']
    print(f"\nNumber of comps found: {len(comps)}")
    for i, comp in enumerate(comps[:5]):
        print(f"\nComp {i+1}: {comp}")
else:
    print("\nNo 'comparable_properties' key found!")

# Let's also check the raw text for rent comp patterns
import PyPDF2
with open(pdf_path, 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    full_text = ""
    for page_num in range(len(reader.pages)):
        full_text += reader.pages[page_num].extract_text() + "\n"

    # Try the exact pattern used in the extractor
    comp_section_match = re.search(r'Studio\s+1\s*Bed\s+2\s*Bed\s+3\s*Bed(.*?)(?:Rent Comparables Photo|Page \d{2,}|$)', full_text, re.DOTALL)

    if comp_section_match:
        print("\n\nSECTION FOUND! Here's what's in the matched text:")
        comp_text = comp_section_match.group(1)
        lines = comp_text.split('\n')[:30]  # First 30 lines
        for i, line in enumerate(lines):
            print(f"{i:3}: {line[:100]}")

        # Check for property-like patterns
        print("\n\nLooking for data patterns (units/SF)...")
        data_matches = re.findall(r'^(\d{2,4})\s+([\d,]+)\s+', comp_text, re.MULTILINE)
        print(f"Found {len(data_matches)} potential data lines")
        for m in data_matches[:5]:
            print(f"  Units: {m[0]}, SF: {m[1]}")
    else:
        print("\n\nSECTION NOT FOUND in full text!")
        # Check what terminator patterns exist
        if 'Rent Comparables Photo' in full_text:
            print("  - 'Rent Comparables Photo' exists in text")
        pages = re.findall(r'Page \d{2,}', full_text)
        print(f"  - Found {len(pages)} 'Page XX' patterns")
