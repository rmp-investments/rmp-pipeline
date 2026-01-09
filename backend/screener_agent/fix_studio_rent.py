"""Fix studio rent extraction."""
import re

with open('modules/pdf_extractor.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the rent extraction block
old_pattern = r"rent_matches = re\.findall\(r'\\\$\(\[\\d,\]\+\)\(\?!\\\.\\d\)', line\)\s+rents = \[int\(r\.replace\(',', ''\)\) for r in rent_matches if int\(r\.replace\(',', ''\)\) > 500\]\s+if len\(rents\) >= 1:\s+comp\['rent_1bed'\] = rents\[0\]\s+if len\(rents\) >= 2:\s+comp\['rent_2bed'\] = rents\[1\]\s+if len\(rents\) >= 3:\s+comp\['rent_3bed'\] = rents\[2\]"

new_code = """rent_matches = re.findall(r'\\$([\\d,]+)(?!\\.\\d)', line)
                            rents = [int(r.replace(',', '')) for r in rent_matches if int(r.replace(',', '')) >= 400]

                            # If 4+ rents, first is studio; if 3 rents, no studio data
                            if len(rents) >= 4:
                                comp['rent_studio'] = rents[0]
                                comp['rent_1bed'] = rents[1]
                                comp['rent_2bed'] = rents[2]
                                comp['rent_3bed'] = rents[3]
                            elif len(rents) >= 3:
                                comp['rent_1bed'] = rents[0]
                                comp['rent_2bed'] = rents[1]
                                comp['rent_3bed'] = rents[2]
                            elif len(rents) >= 2:
                                comp['rent_1bed'] = rents[0]
                                comp['rent_2bed'] = rents[1]
                            elif len(rents) >= 1:
                                comp['rent_1bed'] = rents[0]"""

match = re.search(old_pattern, content)
if match:
    content = content[:match.start()] + new_code + content[match.end():]
    with open('modules/pdf_extractor.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed studio rent extraction")
else:
    # Try simpler replacement
    old_simple = """rent_matches = re.findall(r'\\$([\\d,]+)(?!\\.\\d)', line)
                            rents = [int(r.replace(',', '')) for r in rent_matches if int(r.replace(',', '')) > 500]

                            if len(rents) >= 1:
                                comp['rent_1bed'] = rents[0]
                            if len(rents) >= 2:
                                comp['rent_2bed'] = rents[1]
                            if len(rents) >= 3:
                                comp['rent_3bed'] = rents[2]"""

    if old_simple in content:
        content = content.replace(old_simple, new_code)
        with open('modules/pdf_extractor.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print("Fixed studio rent extraction (simple method)")
    else:
        print("Could not find pattern to replace")
