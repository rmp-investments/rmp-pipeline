"""Quick test of rent and sale comp extraction."""
import sys
import re
sys.path.insert(0, 'modules')
from pdf_extractor import CoStarPDFExtractor
import PyPDF2

reports_dir = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\CoStar Reports"

# Debug: Check sale comp detail pattern
pdf_path = reports_dir + r"\Fieldstone SR.pdf"
with open(pdf_path, 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"

print("=" * 60)
print("DEBUG: Checking sale comp detail pattern")
print("=" * 60)

# Pattern from the enrichment function - UPDATED
detail_pattern = re.compile(
    r'([A-Z][A-Za-z][A-Za-z\s\-\'\.]+?)\s*-\s*(\d+[\d\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Pkwy|Pky|Cir|Pl|Tfwy))\n([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Z]{2})\s+\d{5}\s*-\s*([A-Za-z\s]+?)Neighborhood',
    re.MULTILINE
)

matches = list(detail_pattern.finditer(text))
print(f"Found {len(matches)} matches")
for m in matches[:3]:
    print(f"\n  Name: {m.group(1)}")
    print(f"  Address: {m.group(2)}")
    print(f"  City: {m.group(3)}")
    print(f"  State: {m.group(4)}")
    print(f"  Submarket: {m.group(5)}")

# Try a simpler pattern
print("\n--- Trying simpler pattern for 'Neighborhood' ---")
simple_matches = re.findall(r'([A-Za-z\s]+),\s*([A-Z]{2})\s+\d+\s*-\s*([A-Za-z\s]+?)Neighborhood', text)
print(f"Found {len(simple_matches)} simple matches")
for m in simple_matches[:3]:
    print(f"  {m}")

extractor = CoStarPDFExtractor(reports_dir)
data = extractor.extract_all()

print("=" * 60)
print("RENT COMPS (first 3)")
print("=" * 60)
rent_comps = data.get('rent_comps', {}).get('comparable_properties', [])
for i, comp in enumerate(rent_comps[:3]):
    print(f"\n{i+1}. {comp.get('name', 'Unknown')}")
    print(f"   City: {comp.get('city', 'N/A')}")
    print(f"   Stories: {comp.get('stories', 'N/A')}")
    print(f"   Vacancy: {comp.get('vacancy', 'N/A')}%")
    print(f"   Distance: {comp.get('distance', 'N/A')} mi")

print("\n" + "=" * 60)
print("SALE COMPS (first 3)")
print("=" * 60)
sale_comps = data.get('sale_comps', {}).get('comparable_properties', [])
for i, comp in enumerate(sale_comps[:3]):
    print(f"\n{i+1}. {comp.get('name', 'Unknown')}")
    print(f"   Type: {comp.get('type', 'N/A')}")
    print(f"   Distance: {comp.get('distance', 'N/A')} mi")
    print(f"   Submarket: {comp.get('submarket', 'N/A')}")
    print(f"   Cap Rate: {comp.get('cap_rate', 'N/A')}%")

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Rent comps: {len(rent_comps)}")
print(f"Sale comps: {len(sale_comps)}")

# Check for issues
rent_cities = [c.get('city', 'N/A') for c in rent_comps]
bad_cities = [c for c in rent_cities if '\n' in str(c) or 'Apartments' in str(c)]
if bad_cities:
    print(f"\n[!] Still have {len(bad_cities)} cities with issues: {bad_cities[:3]}")
else:
    print("\n[OK] All rent comp cities look clean")
