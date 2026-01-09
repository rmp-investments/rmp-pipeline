"""Debug script to examine PDF text for missing fields."""
import re
import PyPDF2

pdf_path = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\CoStar Reports\Fieldstone SR.pdf"

with open(pdf_path, 'rb') as f:
    reader = PyPDF2.PdfReader(f)
    full_text = ""
    for page in reader.pages:
        full_text += page.extract_text() + "\n\n---PAGE---\n\n"

print("=" * 60)
print("1. RENT COMP PHOTO PAGES (vacancy, stories)")
print("=" * 60)
# Look for vacancy patterns
vacancy_patterns = re.findall(r'Vacancy\s+([\d.]+)%.{0,100}', full_text)
print(f"Found {len(vacancy_patterns)} Vacancy mentions:")
for v in vacancy_patterns[:5]:
    print(f"  {v[:80]}")

# Look for Units / Stories patterns
stories_patterns = re.findall(r'(\d+)\s*Units\s*/\s*(\d+)\s*Stor.{0,50}', full_text)
print(f"\nFound {len(stories_patterns)} Units/Stories mentions:")
for s in stories_patterns[:5]:
    print(f"  {s}")

print("\n" + "=" * 60)
print("2. RENT COMP DETAIL PAGES (city, distance)")
print("=" * 60)
# Look for Miles patterns
miles_patterns = re.findall(r'.{0,80}([\d.]+)\s*Miles', full_text)
print(f"Found {len(miles_patterns)} Miles mentions:")
for m in miles_patterns[:5]:
    print(f"  ...{m}")

# Look for city, state patterns near comp names
city_state = re.findall(r'([A-Z][a-z]+),\s*([A-Za-z]+)\s*-\s*([A-Za-z\s]+)Neighborhood', full_text)
print(f"\nFound {len(city_state)} City, State - Neighborhood patterns:")
for c in city_state[:5]:
    print(f"  {c}")

print("\n" + "=" * 60)
print("3. SALE COMP DATA (type, distance, submarket, cap rate)")
print("=" * 60)
# Look for sale comp patterns with more fields
# Check what's in the Sale Date section
sale_section = re.search(r'Sale Date\s+Price.*?(?:Page \d{2,}|$)', full_text, re.DOTALL)
if sale_section:
    lines = sale_section.group()[:2000].split('\n')
    print("Sale comp section (first 30 lines):")
    for i, line in enumerate(lines[:30]):
        print(f"  {i}: {line[:100]}")

# Look for Cap Rate mentions
cap_patterns = re.findall(r'Cap\s*Rate.{0,50}', full_text, re.IGNORECASE)
print(f"\nFound {len(cap_patterns)} Cap Rate mentions:")
for c in cap_patterns[:5]:
    print(f"  {c}")

# Look for distance in sale comps
sale_distance = re.findall(r'(\d+\.\d+)\s*(?:mi|miles?)', full_text, re.IGNORECASE)
print(f"\nFound {len(sale_distance)} distance values (mi/miles):")
for d in sale_distance[:10]:
    print(f"  {d}")

print("\n" + "=" * 60)
print("4. CHECKING SALE COMP DETAIL PAGES")
print("=" * 60)
# Look for sale comp detail pages - they have "Cap Rate:"
sale_detail_pages = re.findall(r'([\d\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Pky|Pkwy).+?Cap Rate.+?(?=\d+[\d\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Pky|Pkwy)|Page \d|$))', full_text, re.DOTALL)
print(f"Found {len(sale_detail_pages)} sale comp detail sections")
for i, page in enumerate(sale_detail_pages[:3]):
    print(f"\n--- Sale Comp Detail {i+1} ---")
    print(page[:500])

print("\n" + "=" * 60)
print("5. RENT COMP PHOTO PAGE FORMAT")
print("=" * 60)
# Look for rent comp photo pages with Vacancy
photo_pages = re.findall(r'(Vacancy\s+[\d.]+%.+?(?=Vacancy|---PAGE---|$))', full_text, re.DOTALL)
print(f"Found {len(photo_pages)} rent comp photo sections")
for i, page in enumerate(photo_pages[:2]):
    print(f"\n--- Photo Page {i+1} ---")
    print(page[:400])

print("\n" + "=" * 60)
print("6. CITY DOUBLING DEBUG")
print("=" * 60)
# Look for patterns where name+city are concatenated
name_city = re.findall(r'(\w+\s+of\s+\w+)([A-Z][a-z]+),\s*([A-Za-z]+)', full_text)
print(f"Found {len(name_city)} potential name+city patterns:")
for nc in name_city[:10]:
    print(f"  Name ends: '{nc[0]}' -> City: '{nc[1]}'")
