"""Debug script to check Data Inputs row mapping vs template formulas."""
import sys
sys.path.insert(0, 'modules')
from data_inputs_mapper import DataInputsMapper

mapper = DataInputsMapper()
refs = mapper.get_cell_references()

print("=" * 60)
print("DATA INPUTS ROW MAPPING")
print("=" * 60)

# Key fields that formulas reference
key_fields = [
    "Property Name",
    "Street Address",
    "City",
    "State",
    "Number of Units",
    "Year Built",
    "Avg Unit Size (SF)",
    "Net Rentable SF",
    "Stories",
    "Subject Current Rent (Avg)",
    "Subject Rent PSF",
    "Avg Comp Rent/Unit",
    "Avg Comp Rent PSF",
    "Number of Rent Comps",
    "Avg Rent Comp Vacancy %",
    "Home Ownership %",
    "School Rating (1-10)",
    "High School Avg",
]

print("\nKey field -> Cell reference:")
for field in key_fields:
    if field in refs:
        print(f"  {field}: {refs[field]}")

print("\n" + "=" * 60)
print("TEMPLATE FORMULA REFERENCES (from debug_formulas.py)")
print("=" * 60)
print("""
Screener Cover references Data Inputs:
  C5: C6 (Property Name?)
  C6: C7 (Address?)
  C7: C8 (City?)
  C8: C9 (State?)
  C9: C12 (Units?)
  C10: C13 (Year Built?)
  F5: C110 (Subject Current Rent?)
  F6: C111 (Subject Rent PSF?)
  F7: C15 (Avg Unit Size?)

Rent Comps references:
  C3: C127 (Number of Rent Comps?)
  E3: C120 (Avg Comp Rent/Unit?)
  E4: C121 (Avg Comp Rent PSF?)
  E5: C128/100 (Avg Rent Comp Vacancy %?)
""")

# Check for mismatches
print("\n" + "=" * 60)
print("CHECKING FOR MISMATCHES")
print("=" * 60)
expected = {
    "Property Name": "C6",
    "Street Address": "C7",
    "City": "C8",
    "State": "C9",
    "Number of Units": "C12",
    "Year Built": "C13",
    "Avg Unit Size (SF)": "C15",
    "Subject Current Rent (Avg)": "C110",
    "Subject Rent PSF": "C111",
    "Avg Comp Rent/Unit": "C120",
    "Avg Comp Rent PSF": "C121",
    "Number of Rent Comps": "C127",
    "Avg Rent Comp Vacancy %": "C128",
}

for field, expected_cell in expected.items():
    actual_cell = refs.get(field, "NOT FOUND")
    match = "OK" if actual_cell == expected_cell else "MISMATCH!"
    print(f"  {field}: Expected {expected_cell}, Actual {actual_cell} - {match}")
