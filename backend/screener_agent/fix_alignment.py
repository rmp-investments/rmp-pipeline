"""Add center alignment to excel_writer.py for rent and sale comps."""
import re

with open('modules/excel_writer.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Add alignment to write_rent_comps (after AB column, before print)
old_rent = '''            # AB: #3 Beds (unit count)
            if comp.get('unit_count_3bed'):
                sheet[f'AB{row}'] = comp['unit_count_3bed']

        print(f"[OK] Wrote subject + {len(comps[:17])} rent comparables to Rent Comps sheet")'''

new_rent = '''            # AB: #3 Beds (unit count)
            if comp.get('unit_count_3bed'):
                sheet[f'AB{row}'] = comp['unit_count_3bed']

        # Apply center alignment to all data cells (rows 9-26, columns B-AB)
        center_align = Alignment(horizontal='center', vertical='center')
        rent_comp_cols = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N',
                         'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z', 'AA', 'AB']
        for row in range(9, 27):  # Rows 9-26
            for col in rent_comp_cols:
                sheet[f'{col}{row}'].alignment = center_align

        print(f"[OK] Wrote subject + {len(comps[:17])} rent comparables to Rent Comps sheet")'''

if old_rent in content:
    content = content.replace(old_rent, new_rent)
    print("Fixed rent comps alignment")
else:
    print("Could not find rent comps pattern - may already be fixed")

# Fix 2: Add alignment to write_sale_comps (after N column, before print)
old_sale = '''            # N: Submarket
            if comp.get('submarket'):
                sheet[f'N{row}'] = comp['submarket']

        print(f"[OK] Wrote subject + {len(comps[:15])} sale comparables to Sale Comps sheet")'''

new_sale = '''            # N: Submarket
            if comp.get('submarket'):
                sheet[f'N{row}'] = comp['submarket']

        # Apply center alignment to all data cells (rows 8-22, columns B-N)
        center_align = Alignment(horizontal='center', vertical='center')
        sale_comp_cols = ['B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']
        for row in range(8, 23):  # Rows 8-22
            for col in sale_comp_cols:
                sheet[f'{col}{row}'].alignment = center_align

        print(f"[OK] Wrote subject + {len(comps[:15])} sale comparables to Sale Comps sheet")'''

if old_sale in content:
    content = content.replace(old_sale, new_sale)
    print("Fixed sale comps alignment")
else:
    print("Could not find sale comps pattern - may already be fixed")

with open('modules/excel_writer.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
