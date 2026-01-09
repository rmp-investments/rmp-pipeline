"""
Enhanced CoStar PDF Report Data Extractor
Extracts comprehensive data from CoStar PDF reports
"""

import PyPDF2
import pdfplumber
import os
import re
from typing import Dict, List, Any, Tuple


class CoStarPDFExtractor:
    """Enhanced extractor for comprehensive data from CoStar PDF reports."""

    def __init__(self, reports_dir: str):
        """
        Initialize extractor with reports directory.

        Args:
            reports_dir: Path to directory containing CoStar PDFs
        """
        self.reports_dir = reports_dir
        self.extracted_data = {}

    def extract_all(self) -> Dict[str, Any]:
        """
        Extract data from all PDF reports in directory.
        Handles both separate reports and combined reports.

        Returns:
            Dictionary containing all extracted data
        """
        pdf_files = [f for f in os.listdir(self.reports_dir) if f.endswith('.pdf') and not f.startswith('~$')]

        for pdf_file in pdf_files:
            pdf_path = os.path.join(self.reports_dir, pdf_file)
            filename_lower = pdf_file.lower()

            # Store source PDF info for hyperlinks
            self.extracted_data['_source_pdf'] = {
                'filename': pdf_file,
                'full_path': pdf_path,
                'reports_dir': self.reports_dir
            }

            # Check if it's a specific report type by filename
            if 'demographic' in filename_lower:
                self._extract_demographic_report(pdf_path)
            elif 'property' in filename_lower:
                self._extract_property_report(pdf_path)
            elif 'rent' in filename_lower:
                self._extract_rent_comp_report(pdf_path)
            elif 'asset' in filename_lower or 'market' in filename_lower:
                self._extract_market_report(pdf_path)
            else:
                # Combined/unknown PDF - try to extract ALL data types from it
                print(f"[INFO] Processing combined report: {pdf_file}")
                self._extract_combined_report(pdf_path)

        return self.extracted_data

    def _extract_combined_report(self, pdf_path: str):
        """Extract all data types from a combined PDF report."""
        # Run all extractors on the same PDF
        self._extract_subject_property(pdf_path)  # NEW - extract from Subject Property page first
        self._extract_demographic_report(pdf_path)
        self._extract_property_report(pdf_path)
        self._extract_rent_comp_report(pdf_path)
        self._extract_sale_comp_report(pdf_path)
        self._extract_market_report(pdf_path)
        self._extract_education_data(pdf_path)  # NEW - extract education data
        self._extract_cap_rates(pdf_path)  # NEW - extract cap rates
        self._extract_employment_data(pdf_path)  # Extract employment growth from Economy section


    def _extract_subject_property(self, pdf_path: str):
        """Extract data from Subject Property One Page section.

        This section contains clean, well-formatted data for:
        - Property basics (units, stories, year built, parking)
        - Current/historical rents and vacancy
        - Competitor and submarket comparisons
        - Absorption data
        """
        text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        subject_data = {}
        page_sources = {}  # Track which page each field came from

        # DYNAMIC SECTION DETECTION: Find Subject Property section boundaries
        # This works regardless of what page numbers the section is on
        # Look for "Subject Property" header and find where next major section starts
        section_headers = [
            r'RENT COMPARABLES',
            r'SALE COMPARABLES',
            r'SUBMARKET TREND',
            r'MARKET TREND',
            r'DEMOGRAPHICS',
            r'SUPPLY & DEMAND',
        ]

        # Find start of Subject Property section
        subject_start_match = re.search(r'Subject Property', text, re.IGNORECASE)
        subject_start = subject_start_match.start() if subject_start_match else 0

        # Find end of Subject Property section (start of next major section)
        subject_end = len(text)
        for header in section_headers:
            header_match = re.search(header, text[subject_start + 100:], re.IGNORECASE)  # Skip past "Subject Property" text
            if header_match:
                potential_end = subject_start + 100 + header_match.start()
                if potential_end < subject_end:
                    subject_end = potential_end

        # Extract just the Subject Property section
        subject_section_text = text[subject_start:subject_end]

        # Helper: Get page number for a position in the FULL text
        def get_page_at_position(pos):
            """Find which page a character position falls on."""
            page_markers = list(re.finditer(r'<<PAGE_(\d+)>>', text[:pos]))
            if page_markers:
                return int(page_markers[-1].group(1))
            return 1  # Default to page 1 if no markers found before position

        # Helper: Search within subject section and return (match, actual_page_number)
        def search_subject_section(pattern, flags=0):
            """Search within Subject Property section, return (match, page_num) or (None, None)."""
            match = re.search(pattern, subject_section_text, flags)
            if match:
                # Calculate position in full text to get correct page number
                full_text_pos = subject_start + match.start()
                page_num = get_page_at_position(full_text_pos)
                return match, page_num
            return None, None

        # Find Subject Property header info
        # Format: "Address - Property Name\nCity, State - Neighborhood"
        subject_match, subject_page = search_subject_section(
            r'Subject Property.*?'
            r'([\d\-]+[^\n]+)\s*-\s*([A-Za-z][^\n]+?)\n'  # Address - Name
            r'([A-Za-z][^,]+),\s*([A-Za-z]+)\s*-\s*([^\n]+?)\s*Neighborhood',  # City, State - Submarket
            flags=re.DOTALL
        )

        if subject_match:
            subject_data['address'] = subject_match.group(1).strip()
            subject_data['property_name'] = subject_match.group(2).strip()
            subject_data['city'] = subject_match.group(3).strip()
            subject_data['state'] = subject_match.group(4).strip()
            subject_data['submarket_neighborhood'] = subject_match.group(5).strip()
            page_sources['address'] = subject_page
            page_sources['property_name'] = subject_page
            page_sources['city'] = subject_page
            page_sources['state'] = subject_page
            page_sources['submarket_neighborhood'] = subject_page
            print(f'[INFO] Subject Property: {subject_data.get("property_name")} in {subject_data.get("submarket_neighborhood")} (pg {subject_page})')

        # Property basics from PROPERTY section (PAGES 1-3 ONLY)
        # No. of Units
        match, pg = search_subject_section(r'No\.\s*of\s*Units:\s*(\d+)')
        if match:
            subject_data['units'] = int(match.group(1))
            page_sources['units'] = pg

        # Stories
        match, pg = search_subject_section(r'Stories:\s*(\d+)')
        if match:
            subject_data['stories'] = int(match.group(1))
            page_sources['stories'] = pg

        # Avg. Unit Size
        match, pg = search_subject_section(r'Avg\.\s*Unit\s*Size:\s*([\d,]+)\s*SF')
        if match:
            subject_data['avg_unit_size'] = int(match.group(1).replace(',', ''))
            page_sources['avg_unit_size'] = pg

        # Year Built
        match, pg = search_subject_section(r'Year\s*Built:\s*(\d{4})')
        if match:
            subject_data['year_built'] = int(match.group(1))
            page_sources['year_built'] = pg

        # Parking
        match, pg = search_subject_section(r'Parking:\s*(\d+)\s*Spaces;\s*([\d.]+)\s*per\s*Unit')
        if match:
            subject_data['parking_spaces'] = int(match.group(1))
            subject_data['parking_ratio'] = float(match.group(2))
            page_sources['parking_spaces'] = pg
            page_sources['parking_ratio'] = pg

        # Rent Type (Affordable, Market, etc.)
        match, pg = search_subject_section(r'Rent\s*Type:\s*([A-Za-z]+)')
        if match:
            subject_data['rent_type'] = match.group(1).strip()
            page_sources['rent_type'] = pg

        # Property Type
        match, pg = search_subject_section(r'Type:\s*([A-Za-z\s\-]+?)(?:\n|Rent)')
        if match:
            subject_data['property_type'] = match.group(1).strip()
            page_sources['property_type'] = pg

        # Owner (pages 1-3)
        match, pg = search_subject_section(r'OWNER\s*([^\n]+?)\n')
        if match:
            subject_data['owner'] = match.group(1).strip()
            page_sources['owner'] = pg

        # === ASKING RENTS (PAGES 1-3 ONLY) ===
        # Current rent per unit and per SF
        match, pg = search_subject_section(r'Current:\s*\$([\d,]+)\s*\$([\d.]+)\s*/SF')
        if match:
            subject_data['current_rent_per_unit'] = int(match.group(1).replace(',', ''))
            subject_data['current_rent_psf'] = float(match.group(2))
            page_sources['current_rent_per_unit'] = pg
            page_sources['current_rent_psf'] = pg

        # Last Quarter rent
        match, pg = search_subject_section(r'Last\s*Quarter:\s*\$([\d,]+)\s*\$([\d.]+)\s*/SF')
        if match:
            subject_data['last_quarter_rent_per_unit'] = int(match.group(1).replace(',', ''))
            subject_data['last_quarter_rent_psf'] = float(match.group(2))
            page_sources['last_quarter_rent_per_unit'] = pg
            page_sources['last_quarter_rent_psf'] = pg

        # Year Ago rent
        match, pg = search_subject_section(r'Year\s*Ago:\s*\$([\d,]+)')
        if match:
            subject_data['year_ago_rent'] = int(match.group(1).replace(',', ''))
            page_sources['year_ago_rent'] = pg

        # Competitors rent
        match, pg = search_subject_section(r'Competitors:\s*\$([\d,]+)')
        if match:
            subject_data['competitor_rent'] = int(match.group(1).replace(',', ''))
            page_sources['competitor_rent'] = pg

        # Submarket rent
        match, pg = search_subject_section(r'Submarket:\s*\$([\d,]+)')
        if match:
            subject_data['submarket_rent'] = int(match.group(1).replace(',', ''))
            page_sources['submarket_rent'] = pg

        # === VACANCY (PAGES 1-3 ONLY) ===
        # Current vacancy - multiple formats
        vacancy_patterns = [
            r'VACANCY.*?Current:?\s*([\d.]+)\s*%\s*(\d+)\s*Units',  # With optional colon
            r'VACANCY.*?Current:?\s*([\d.]+)%\s+(\d+)',  # Compact format
            r'VACANCY\s+Current:?\s*([\d.]+)\s*%',  # Just percentage, no unit count
        ]
        for pattern in vacancy_patterns:
            match, pg = search_subject_section(pattern, flags=re.DOTALL | re.IGNORECASE)
            if match:
                subject_data['current_vacancy'] = float(match.group(1))
                page_sources['current_vacancy'] = pg
                if len(match.groups()) > 1 and match.group(2):
                    subject_data['current_vacant_units'] = int(match.group(2))
                    page_sources['current_vacant_units'] = pg
                print(f"[INFO] Found vacancy {match.group(1)}% from VACANCY section (pg {pg})")
                break

        # Year Ago vacancy
        match, pg = search_subject_section(r'VACANCY.*?Year\s*Ago:\s*([\d.]+)%', flags=re.DOTALL)
        if match:
            subject_data['year_ago_vacancy'] = float(match.group(1))
            page_sources['year_ago_vacancy'] = pg

        # Competitors vacancy
        match, pg = search_subject_section(r'VACANCY.*?Competitors:\s*([\d.]+)%', flags=re.DOTALL)
        if match:
            subject_data['competitor_vacancy'] = float(match.group(1))
            page_sources['competitor_vacancy'] = pg

        # Submarket vacancy
        match, pg = search_subject_section(r'VACANCY.*?Submarket:\s*([\d.]+)%', flags=re.DOTALL)
        if match:
            subject_data['submarket_vacancy'] = float(match.group(1))
            page_sources['submarket_vacancy'] = pg

        # === 12 MONTH ABSORPTION (PAGES 1-3 ONLY) ===
        # Helper to parse accounting-style negatives: "(1)" means -1
        def parse_absorption(val_str):
            val_str = val_str.strip().replace(',', '')
            if val_str.startswith('(') and val_str.endswith(')'):
                return -int(val_str[1:-1])
            elif val_str.startswith('-'):
                return int(val_str)
            return int(val_str)

        # Match both formats: "(1)" or "-1" or "1"
        match, pg = search_subject_section(r'12 MONTH ABSORPTION.*?Current:\s*(\(?[\d,]+\)?|-?[\d,]+)\s*Units', flags=re.DOTALL)
        if match:
            subject_data['absorption_12mo_current'] = parse_absorption(match.group(1))
            page_sources['absorption_12mo_current'] = pg

        match, pg = search_subject_section(r'Competitor\s*Total:\s*(\(?[\d,]+\)?|-?[\d,]+)\s*Units')
        if match:
            subject_data['absorption_12mo_competitor_total'] = parse_absorption(match.group(1))
            page_sources['absorption_12mo_competitor_total'] = pg

        match, pg = search_subject_section(r'Submarket\s*Total:\s*([\d,]+)\s*Units')
        if match:
            subject_data['absorption_12mo_submarket'] = int(match.group(1).replace(',', ''))
            page_sources['absorption_12mo_submarket'] = pg

        if subject_data:
            subject_data['_page_sources'] = page_sources  # Store page sources
            self.extracted_data['subject_property'] = subject_data
            print(f'[INFO] Extracted {len(subject_data) - 1} fields from Subject Property section')


    def _extract_education_data(self, pdf_path: str):
        """Extract education attainment data from Age & Education section."""
        text = self._extract_text_from_pdf(pdf_path)

        education_data = {}

        # Look for education percentages - format varies
        # Bachelor's Degree or Higher
        match = re.search(r"Bachelor'?s?\s*(?:Degree)?.*?(\d+\.?\d*)%", text, re.IGNORECASE)
        if match:
            education_data['bachelors_pct'] = float(match.group(1))

        # High School Graduate
        match = re.search(r'High\s*School\s*(?:Graduate|Diploma).*?(\d+\.?\d*)%', text, re.IGNORECASE)
        if match:
            education_data['high_school_pct'] = float(match.group(1))

        # Some College
        match = re.search(r'Some\s*College.*?(\d+\.?\d*)%', text, re.IGNORECASE)
        if match:
            education_data['some_college_pct'] = float(match.group(1))

        # Graduate Degree
        match = re.search(r'Graduate\s*(?:Degree|or\s*Professional).*?(\d+\.?\d*)%', text, re.IGNORECASE)
        if match:
            education_data['graduate_degree_pct'] = float(match.group(1))

        if education_data:
            if 'demographics' not in self.extracted_data:
                self.extracted_data['demographics'] = {}
            self.extracted_data['demographics'].update(education_data)
            print(f'[INFO] Extracted {len(education_data)} education fields')


    def _extract_cap_rates(self, pdf_path: str):
        """Extract cap rate data from Cap Rates Report section."""
        text = self._extract_text_from_pdf(pdf_path)

        cap_rate_data = {}

        # Market Cap Rate
        match = re.search(r'Market\s*Cap\s*Rate.*?([\d.]+)%', text, re.IGNORECASE)
        if match:
            cap_rate_data['market_cap_rate'] = float(match.group(1))

        # Average Cap Rate
        match = re.search(r'(?:Average|Avg\.?)\s*Cap\s*Rate.*?([\d.]+)%', text, re.IGNORECASE)
        if match:
            cap_rate_data['avg_cap_rate'] = float(match.group(1))

        # Look for cap rate in sale comps context
        match = re.search(r'CAP\s*RATE.*?([\d.]+)%', text, re.IGNORECASE)
        if match and 'market_cap_rate' not in cap_rate_data:
            cap_rate_data['market_cap_rate'] = float(match.group(1))

        # Trailing 12 Month Cap Rate
        match = re.search(r'(?:Trailing|TTM|12\s*Mo).*?Cap\s*Rate.*?([\d.]+)%', text, re.IGNORECASE)
        if match:
            cap_rate_data['trailing_cap_rate'] = float(match.group(1))

        if cap_rate_data:
            if 'market' not in self.extracted_data:
                self.extracted_data['market'] = {}
            self.extracted_data['market'].update(cap_rate_data)
            print(f'[INFO] Extracted {len(cap_rate_data)} cap rate fields')

    def _extract_text_from_pdf(self, pdf_path: str, page_num: int = None, include_page_markers: bool = False) -> str:
        """Extract text from PDF file.

        Args:
            pdf_path: Path to the PDF file
            page_num: If specified, extract only that page (0-indexed)
            include_page_markers: If True, insert page markers for tracking source pages
        """
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            if page_num is not None:
                try:
                    return pdf_reader.pages[page_num].extract_text() or ""
                except (IndexError, KeyError) as e:
                    # Fallback to pdfplumber for this page
                    print(f"[INFO] PyPDF2 failed on page {page_num}, trying pdfplumber...")
                    try:
                        with pdfplumber.open(pdf_path) as pdf:
                            return pdf.pages[page_num].extract_text() or ""
                    except Exception as e2:
                        print(f"[WARN] Both extractors failed on page {page_num}")
                        return ""
            else:
                text = ""
                failed_pages = []
                for i, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text() or ""
                    except (IndexError, KeyError) as e:
                        failed_pages.append(i)
                        page_text = ""  # Placeholder, will fill with pdfplumber

                    if include_page_markers:
                        # Try to extract CoStar's printed page number from page content
                        costar_page = self._extract_costar_page_number(page_text)
                        if costar_page:
                            text += f"\n<<PAGE_{costar_page}>>\n"
                        else:
                            text += f"\n<<PAGE_{i+1}>>\n"  # Fallback to PDF index
                    text += page_text

                # Use pdfplumber for any pages that failed
                if failed_pages:
                    print(f"[INFO] PyPDF2 failed on pages {[p+1 for p in failed_pages]}, trying pdfplumber...")
                    try:
                        with pdfplumber.open(pdf_path) as pdf:
                            # Re-extract those pages with pdfplumber
                            for page_idx in failed_pages:
                                try:
                                    page_text = pdf.pages[page_idx].extract_text() or ""
                                    # Find the page marker and insert the text after it
                                    marker = f"<<PAGE_{page_idx+1}>>"
                                    if marker in text:
                                        # Find position after marker
                                        pos = text.find(marker) + len(marker)
                                        # Find next marker or end
                                        next_marker = f"<<PAGE_{page_idx+2}>>"
                                        next_pos = text.find(next_marker) if next_marker in text else len(text)
                                        # Replace empty section with pdfplumber text
                                        text = text[:pos] + "\n" + page_text + text[next_pos:]
                                    print(f"  [OK] Page {page_idx+1} extracted with pdfplumber")
                                except Exception as e2:
                                    print(f"  [WARN] pdfplumber also failed on page {page_idx+1}: {e2}")
                    except Exception as e:
                        print(f"[WARN] pdfplumber fallback failed: {e}")

                return text

    def _get_page_number(self, text: str, match_pos: int) -> int:
        """Find which page a match position is on based on page markers."""
        page_markers = list(re.finditer(r'<<PAGE_(\d+)>>', text[:match_pos]))
        if page_markers:
            return int(page_markers[-1].group(1))
        return 1

    def _extract_costar_page_number(self, page_text: str) -> int:
        """
        Extract CoStar's printed page number from page content.
        CoStar reports typically have "Page X of Y" or "X of Y" in the footer.
        Returns the page number or None if not found.
        """
        if not page_text:
            return None

        # Look for common CoStar page number patterns
        # Pattern 1: "Page 75 of 80" or "page 75 of 80"
        match = re.search(r'[Pp]age\s+(\d+)\s+of\s+\d+', page_text)
        if match:
            return int(match.group(1))

        # Pattern 2: Just "75 of 80" at end of page (common in footers)
        # Look in the last portion of the page text
        last_portion = page_text[-500:] if len(page_text) > 500 else page_text
        match = re.search(r'\b(\d+)\s+of\s+(\d+)\s*$', last_portion.strip())
        if match:
            page_num = int(match.group(1))
            total = int(match.group(2))
            # Sanity check - page number should be <= total
            if page_num <= total:
                return page_num

        return None

    def _clean_property_name(self, name: str) -> str:
        """Clean property name - remove encoding artifacts and normalize."""
        if not name:
            return name

        # Replace common encoding issues
        replacements = {
            '\ufffd': '',  # Unicode replacement character
            '\x00': '',    # Null character
            '\u2019': "'", # Right single quote
            '\u2018': "'", # Left single quote
            '\u201c': '"', # Left double quote
            '\u201d': '"', # Right double quote
            '\u2013': '-', # En dash
            '\u2014': '-', # Em dash
        }

        for old, new in replacements.items():
            name = name.replace(old, new)

        # Remove any remaining non-ASCII characters that cause issues
        name = name.encode('ascii', 'ignore').decode('ascii')

        # Clean up whitespace
        name = ' '.join(name.split())

        # Truncate very long names for Excel compatibility
        if len(name) > 50:
            name = name[:47] + '...'

        return name

    def _extract_demographic_report(self, pdf_path: str):
        """Extract comprehensive demographics from Demographic Report PDF."""
        # Get all text from PDF with page markers for source tracking
        full_text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        # Also try specific pages for backwards compatibility
        text_p0 = self._extract_text_from_pdf(pdf_path, 0)
        text_p5 = self._extract_text_from_pdf(pdf_path, 5) if self._get_page_count(pdf_path) > 5 else ""

        # Use full text with page markers
        combined_text = full_text

        demographics = {}
        page_sources = {}  # Track which page each field came from

        # === PROPERTY OVERVIEW DATA ===
        # Search in full text for all patterns

        # Median HH Income (1-mile)
        match = re.search(r'Med\.\s*HH\s*Inc\.\s*\(1\s*mi\)\s*\$?([\d,]+)', combined_text, re.IGNORECASE)
        if match:
            demographics['median_hh_income_1mi'] = int(match.group(1).replace(',', ''))
            page_sources['median_hh_income_1mi'] = self._get_page_number(combined_text, match.start())

        # Absorption data - handle accounting notation where (X) means -X
        # Pattern matches: "Current: 5 Units" or "Current: (5) Units" or "Current: -5 Units"
        def parse_absorption_value(text_match):
            """Parse absorption value, treating parentheses as negative."""
            val_str = text_match.strip()
            if val_str.startswith('(') and val_str.endswith(')'):
                # Parentheses = negative in accounting notation
                return -int(val_str[1:-1])
            return int(val_str)

        match = re.search(r'Current:\s*(\(?\d+\)?|-?\d+)\s*Units', combined_text)
        if match:
            demographics['absorption_12mo_property'] = parse_absorption_value(match.group(1))
            page_sources['absorption_12mo_property'] = self._get_page_number(combined_text, match.start())
            print(f"[INFO] Property absorption: {demographics['absorption_12mo_property']} units")

        match = re.search(r'Competitor Total:\s*(\(?\d+\)?|-?\d+)\s*Units', combined_text)
        if match:
            demographics['absorption_12mo_competitor_total'] = parse_absorption_value(match.group(1))
            page_sources['absorption_12mo_competitor_total'] = self._get_page_number(combined_text, match.start())
            print(f"[INFO] Competitor absorption: {demographics['absorption_12mo_competitor_total']} units")

        match = re.search(r'Competitor Avg:\s*\(?([-\d.]+)\)?\s*Units', combined_text)
        if match:
            demographics['absorption_12mo_competitor_avg'] = float(match.group(1))
            page_sources['absorption_12mo_competitor_avg'] = self._get_page_number(combined_text, match.start())

        match = re.search(r'Submarket Total:\s*([\d,]+)\s*Units', combined_text)
        if match:
            demographics['absorption_12mo_submarket'] = int(match.group(1).replace(',', ''))
            page_sources['absorption_12mo_submarket'] = self._get_page_number(combined_text, match.start())

        # Competitor vacancy and rent
        match = re.search(r'Competitors:\s*([\d.]+)%', combined_text)
        if match:
            demographics['competitor_vacancy_rate'] = float(match.group(1))
            page_sources['competitor_vacancy_rate'] = self._get_page_number(combined_text, match.start())

        match = re.search(r'Competitors:\s*\$?([\d,]+)', combined_text)
        if match:
            demographics['competitor_avg_rent'] = int(match.group(1).replace(',', ''))
            page_sources['competitor_avg_rent'] = self._get_page_number(combined_text, match.start())

        # Submarket data
        match = re.search(r'Submarket:\s*([\d.]+)%', combined_text)
        if match:
            demographics['submarket_vacancy_rate'] = float(match.group(1))
            page_sources['submarket_vacancy_rate'] = self._get_page_number(combined_text, match.start())

        match = re.search(r'Submarket:\s*\$?([\d,]+)', combined_text)
        if match:
            demographics['submarket_avg_rent'] = int(match.group(1).replace(',', ''))
            page_sources['submarket_avg_rent'] = self._get_page_number(combined_text, match.start())

        # Year-over-year rent change
        match = re.search(r'Year Ago:\s*\$?([\d,]+)', combined_text)
        if match:
            demographics['rent_year_ago'] = int(match.group(1).replace(',', ''))
            page_sources['rent_year_ago'] = self._get_page_number(combined_text, match.start())

        # === DETAILED DEMOGRAPHICS (from demographic summary table) ===
        # Table format: "5 Mile 3 Mile 1 Mile" then "value5 value3 value1 Label"
        # Example: "216,499 99,942 11,875 2024 Population"

        # Population - extract all three radii
        match = re.search(r'([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*2024 Population', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['population_5mi_2024'] = int(match.group(1).replace(',', ''))
            demographics['population_3mi_2024'] = int(match.group(2).replace(',', ''))
            demographics['population_1mi_2024'] = int(match.group(3).replace(',', ''))
            page_sources['population_5mi_2024'] = page
            page_sources['population_3mi_2024'] = page
            page_sources['population_1mi_2024'] = page

        match = re.search(r'([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*2029 Population', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['population_5mi_2029'] = int(match.group(1).replace(',', ''))
            demographics['population_3mi_2029'] = int(match.group(2).replace(',', ''))
            demographics['population_1mi_2029'] = int(match.group(3).replace(',', ''))
            page_sources['population_5mi_2029'] = page
            page_sources['population_3mi_2029'] = page
            page_sources['population_1mi_2029'] = page

        # Pop Growth can have negative values in parentheses: (0.4%) or positive: 0.2%
        match = re.search(r'\(?(-?[\d.]+)%\)?\s+\(?(-?[\d.]+)%\)?\s+\(?(-?[\d.]+)%\)?\s*Pop Growth', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            # Convert parentheses format to negative: (0.4) -> -0.4
            val1 = float(match.group(1))
            val2 = float(match.group(2))
            val3 = float(match.group(3))
            # Check if original text had parentheses (indicating negative)
            orig = combined_text[match.start():match.end()]
            if '(' in orig.split('%')[0]:
                val1 = -abs(val1)
            if '(' in orig.split('%')[1]:
                val2 = -abs(val2)
            demographics['population_growth_pct_5mi'] = val1
            demographics['population_growth_pct_3mi'] = val2
            demographics['population_growth_pct'] = val3
            page_sources['population_growth_pct_5mi'] = page
            page_sources['population_growth_pct_3mi'] = page
            page_sources['population_growth_pct'] = page

        # Average Age - all radii
        match = re.search(r'(\d+)\s+(\d+)\s+(\d+)\s*2024 Average Age', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['avg_age_5mi'] = int(match.group(1))
            demographics['avg_age_3mi'] = int(match.group(2))
            demographics['avg_age_1mi'] = int(match.group(3))
            page_sources['avg_age_5mi'] = page
            page_sources['avg_age_3mi'] = page
            page_sources['avg_age_1mi'] = page

        # Households - all radii
        match = re.search(r'([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*2024 Households', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['households_5mi_2024'] = int(match.group(1).replace(',', ''))
            demographics['households_3mi_2024'] = int(match.group(2).replace(',', ''))
            demographics['households_1mi_2024'] = int(match.group(3).replace(',', ''))
            page_sources['households_5mi_2024'] = page
            page_sources['households_3mi_2024'] = page
            page_sources['households_1mi_2024'] = page

        match = re.search(r'([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*2029 Households', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['households_5mi_2029'] = int(match.group(1).replace(',', ''))
            demographics['households_3mi_2029'] = int(match.group(2).replace(',', ''))
            demographics['households_1mi_2029'] = int(match.group(3).replace(',', ''))
            page_sources['households_5mi_2029'] = page
            page_sources['households_3mi_2029'] = page
            page_sources['households_1mi_2029'] = page

        # Household Growth can have negative values in parentheses: (0.3%) or positive: 0.4%
        match = re.search(r'\(?(-?[\d.]+)%\)?\s+\(?(-?[\d.]+)%\)?\s+\(?(-?[\d.]+)%\)?\s*Household Growth', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            val1 = float(match.group(1))
            val2 = float(match.group(2))
            val3 = float(match.group(3))
            orig = combined_text[match.start():match.end()]
            if '(' in orig.split('%')[0]:
                val1 = -abs(val1)
            if '(' in orig.split('%')[1]:
                val2 = -abs(val2)
            demographics['household_growth_pct_5mi'] = val1
            demographics['household_growth_pct_3mi'] = val2
            demographics['household_growth_pct'] = val3
            page_sources['household_growth_pct_5mi'] = page
            page_sources['household_growth_pct_3mi'] = page
            page_sources['household_growth_pct'] = page

        # Median HH Income - all radii
        match = re.search(r'\$?([\d,]+)\s+\$?([\d,]+)\s+\$?([\d,]+)\s*Median Household Income', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['median_hh_income_5mi'] = int(match.group(1).replace(',', ''))
            demographics['median_hh_income_3mi'] = int(match.group(2).replace(',', ''))
            demographics['median_hh_income_1mi'] = int(match.group(3).replace(',', ''))
            page_sources['median_hh_income_5mi'] = page
            page_sources['median_hh_income_3mi'] = page
            page_sources['median_hh_income_1mi'] = page

        # Average household size - all radii
        match = re.search(r'([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*Average Household Size', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['avg_household_size_5mi'] = float(match.group(1))
            demographics['avg_household_size_3mi'] = float(match.group(2))
            demographics['avg_household_size'] = float(match.group(3))
            page_sources['avg_household_size_5mi'] = page
            page_sources['avg_household_size_3mi'] = page
            page_sources['avg_household_size'] = page

        # Average HH vehicles
        match = re.search(r'(\d+)\s+(\d+)\s+(\d+)\s*Average HH Vehicles', combined_text)
        if match:
            demographics['avg_hh_vehicles'] = int(match.group(3))  # 1-mile value
            page_sources['avg_hh_vehicles'] = self._get_page_number(combined_text, match.start())

        # Median home value - all radii
        match = re.search(r'\$?([\d,]+)\s+\$?([\d,]+)\s+\$?([\d,]+)\s*Median Home Value', combined_text)
        if match:
            page = self._get_page_number(combined_text, match.start())
            demographics['median_home_value_5mi'] = int(match.group(1).replace(',', ''))
            demographics['median_home_value_3mi'] = int(match.group(2).replace(',', ''))
            demographics['median_home_value'] = int(match.group(3).replace(',', ''))
            page_sources['median_home_value_5mi'] = page
            page_sources['median_home_value_3mi'] = page
            page_sources['median_home_value'] = page

        # Median year built
        match = re.search(r'(\d{4})\s+(\d{4})\s+(\d{4})\s*Median Year Built', combined_text)
        if match:
            demographics['median_year_built_housing'] = int(match.group(3))  # 1-mile value
            page_sources['median_year_built_housing'] = self._get_page_number(combined_text, match.start())

        # Store page sources
        demographics['_page_sources'] = page_sources
        self.extracted_data['demographics'] = demographics

    def _extract_property_report(self, pdf_path: str):
        """Extract comprehensive property details from Property Report PDF."""
        # Store current PDF path for use by extraction methods (e.g., pdfplumber fallback)
        self.current_pdf_path = pdf_path

        # Search full PDF for property data - include page markers for source tracking
        text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        property_data = {}
        page_sources = {}  # Track which page each field came from

        # Basic property info - try multiple patterns for units
        # First check if we already have this from subject_property section
        if 'subject_property' in self.extracted_data:
            sp = self.extracted_data['subject_property']
            sp_pages = sp.get('_page_sources', {})
            if 'units' in sp:
                property_data['units'] = sp['units']
                if 'units' in sp_pages:
                    page_sources['units'] = sp_pages['units']
            if 'stories' in sp:
                property_data['stories'] = sp['stories']
                if 'stories' in sp_pages:
                    page_sources['stories'] = sp_pages['stories']
            if 'avg_unit_size' in sp:
                property_data['avg_unit_size'] = sp['avg_unit_size']
                if 'avg_unit_size' in sp_pages:
                    page_sources['avg_unit_size'] = sp_pages['avg_unit_size']
            if 'year_built' in sp:
                property_data['vintage'] = sp['year_built']
                if 'year_built' in sp_pages:
                    page_sources['vintage'] = sp_pages['year_built']
            if 'parking_ratio' in sp:
                property_data['parking_ratio'] = sp['parking_ratio']
                if 'parking_ratio' in sp_pages:
                    page_sources['parking_ratio'] = sp_pages['parking_ratio']
            if 'parking_spaces' in sp:
                property_data['parking_spaces'] = sp['parking_spaces']
                if 'parking_spaces' in sp_pages:
                    page_sources['parking_spaces'] = sp_pages['parking_spaces']

        # Fallback: try multiple patterns for units if not from subject_property
        if 'units' not in property_data:
            unit_patterns = [
                r'(\d+)\s*Unit\s*Apartment',  # "216 Unit Apartment Building"
                r'Units\s+(\d+)',              # "Units 216"
                r'(\d+)\s*(?:Units|units)',    # "216 Units"
            ]
            for pattern in unit_patterns:
                match = re.search(pattern, text)
                if match:
                    units = int(match.group(1))
                    # Sanity check - property units should be 10-2000 range
                    if 10 <= units <= 2000:
                        property_data['units'] = units
                        page_sources['units'] = self._get_page_number(text, match.start())
                        break

        # Year Built - multiple patterns, with sanity check
        # Look for property-specific year patterns (not demographic median year built)

        # For combined reports, look for year in rent comp summary table
        # Pattern: "216 X,XXX ... AddressYYYY" where 216 is our unit count
        if 'units' in property_data and 'vintage' not in property_data:
            unit_count = property_data['units']
            # Find line with our unit count + year pattern at end of address
            # Format: "216 1,045 ... 133rd St2000" (no space before year)
            # Include common street suffixes including Tfwy (Trafficway), Pkwy, Cir, Pl, etc.
            pattern = rf'{unit_count}\s+[\d,]+.*?(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Tfwy|Pkwy|Cir|Pl|Hwy|Loop)(\d{{4}})'
            unit_year = re.search(pattern, text, re.IGNORECASE)
            if unit_year:
                year = int(unit_year.group(1))
                if 1950 <= year <= 2025:
                    property_data['vintage'] = year
                    page_sources['vintage'] = self._get_page_number(text, unit_year.start())

        # Fallback: look for "Year Built: YYYY" pattern in property details sections
        if 'vintage' not in property_data:
            # Look for explicit year built format (from individual comp pages)
            year_match = re.search(r'Year Built:\s*(\d{4})', text, re.IGNORECASE)
            if year_match:
                year = int(year_match.group(1))
                if 1950 <= year <= 2025:
                    property_data['vintage'] = year
                    page_sources['vintage'] = self._get_page_number(text, year_match.start())

        # Last resort: standard patterns
        if 'vintage' not in property_data:
            year_patterns = [
                r'Built\s+(\d{4})',              # "Built 2000"
                r'(\d{4})\s+(?:Year Built|Yr Built)',  # "2000 Year Built"
            ]
            for pattern in year_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    year = int(match.group(1))
                    # Sanity check: apartment buildings typically built 1950-2025
                    if 1960 <= year <= 2025:
                        property_data['vintage'] = year
                        page_sources['vintage'] = self._get_page_number(text, match.start())
                        break

        # Vacancy - PRIORITY: Use subject_property.current_vacancy (extracted from VACANCY section on page 1)
        # This is much more reliable than regex searching through the whole PDF
        if 'subject_property' in self.extracted_data:
            sp = self.extracted_data['subject_property']
            sp_pages = sp.get('_page_sources', {})
            if 'current_vacancy' in sp:
                property_data['vacancy_rate'] = sp['current_vacancy']
                if 'current_vacancy' in sp_pages:
                    page_sources['vacancy_rate'] = sp_pages['current_vacancy']
                print(f"[INFO] Using vacancy {sp['current_vacancy']}% from Subject Property section (page {sp_pages.get('current_vacancy', 1)})")

        # Only use regex fallback if subject_property vacancy not found
        if 'vacancy_rate' not in property_data:
            # Pattern: "Vacancy X.X%" near subject property header
            vacancy_match = re.search(r'Subject Property.*?Vacancy\s*([\d.]+)%', text, re.DOTALL)
            if vacancy_match:
                property_data['vacancy_rate'] = float(vacancy_match.group(1))
                page_sources['vacancy_rate'] = self._get_page_number(text, vacancy_match.start())

        # Stories - look for "XXX Units / Y Stories" pattern for subject property
        if 'units' in property_data and 'stories' not in property_data:
            unit_count = property_data['units']
            # Pattern: "216 Units / 2 Stories"
            stories_match = re.search(rf'{unit_count}\s*Units\s*/\s*(\d+)\s*Stor', text, re.IGNORECASE)
            if stories_match:
                property_data['stories'] = int(stories_match.group(1))
                page_sources['stories'] = self._get_page_number(text, stories_match.start())

        # Fallback stories pattern
        if 'stories' not in property_data:
            match = re.search(r'Stories\s+(\d+)', text)
            if match:
                property_data['stories'] = int(match.group(1))
                page_sources['stories'] = self._get_page_number(text, match.start())

        # Avg Unit Size - look for subject property in rent comp table
        if 'units' in property_data and 'avg_unit_size' not in property_data:
            unit_count = property_data['units']
            # Pattern: "216 1,045" in the rent comp summary (units then avg SF)
            sf_match = re.search(rf'{unit_count}\s+([\d,]+)\s+[-$]', text)
            if sf_match:
                sf = int(sf_match.group(1).replace(',', ''))
                if 400 <= sf <= 2000:  # Sanity check for apartment SF
                    property_data['avg_unit_size'] = sf
                    page_sources['avg_unit_size'] = self._get_page_number(text, sf_match.start())

        # Land and building details
        match = re.search(r'Land\s*(?:Area)?[:\s]*([\d.]+)\s*(?:AC|Acres?)', text, re.IGNORECASE)
        if match:
            property_data['land_area_acres'] = float(match.group(1))
            page_sources['land_area_acres'] = self._get_page_number(text, match.start())

        if 'avg_unit_size' not in property_data:
            match = re.search(r'Average Unit Size\s*([\d,]+)\s*SF', text)
            if match:
                property_data['avg_unit_size'] = int(match.group(1).replace(',', ''))
                page_sources['avg_unit_size'] = self._get_page_number(text, match.start())

        match = re.search(r'Construction\s*(?:Type)?[:\s]+([A-Za-z]+(?:\s+Frame)?)', text, re.IGNORECASE)
        if match:
            property_data['construction_type'] = match.group(1)
            page_sources['construction_type'] = self._get_page_number(text, match.start())

        # Require either "Number of Buildings" or "Buildings:" with colon to avoid matching photo captions like "Building 12"
        match = re.search(r'(?:Number\s+of\s+Buildings|Buildings)\s*:\s*(\d+)', text, re.IGNORECASE)
        if match:
            property_data['number_of_buildings'] = int(match.group(1))
            page_sources['number_of_buildings'] = self._get_page_number(text, match.start())

        # Parking
        match = re.search(r'([\d.]+)/Unit;\s*(\d+)\s*Surface Spaces;\s*(\d+)\s*Covered Spaces', text)
        if match:
            page = self._get_page_number(text, match.start())
            property_data['parking_ratio'] = float(match.group(1))
            property_data['parking_surface_spaces'] = int(match.group(2))
            property_data['parking_covered_spaces'] = int(match.group(3))
            page_sources['parking_ratio'] = page
            page_sources['parking_surface_spaces'] = page
            page_sources['parking_covered_spaces'] = page

        # Extract unit mix from the detailed table
        unit_mix, unit_mix_page = self._extract_unit_mix(text)
        if unit_mix:
            property_data['unit_mix'] = unit_mix
            # Extract rents by bedroom type for easy access
            unit_mix_rents = {}
            for unit in unit_mix:
                beds = unit.get('bedrooms')
                rent = unit.get('asking_rent_per_unit')
                if beds == 0:
                    unit_mix_rents['studio'] = rent
                    page_sources['unit_mix_rents.studio'] = unit_mix_page
                elif beds == 1:
                    unit_mix_rents['bed_1'] = rent
                    page_sources['unit_mix_rents.bed_1'] = unit_mix_page
                elif beds == 2:
                    unit_mix_rents['bed_2'] = rent
                    page_sources['unit_mix_rents.bed_2'] = unit_mix_page
                elif beds == 3:
                    unit_mix_rents['bed_3'] = rent
                    page_sources['unit_mix_rents.bed_3'] = unit_mix_page
            if unit_mix_rents:
                property_data['unit_mix_rents'] = unit_mix_rents

            # Also extract unit counts by bedroom type
            unit_counts = {}
            for unit in unit_mix:
                beds = unit.get('bedrooms')
                units = unit.get('units')
                if beds == 0:
                    unit_counts['studio'] = units
                    page_sources['unit_counts.studio'] = unit_mix_page
                elif beds == 1:
                    unit_counts['bed_1'] = units
                    page_sources['unit_counts.bed_1'] = unit_mix_page
                elif beds == 2:
                    unit_counts['bed_2'] = units
                    page_sources['unit_counts.bed_2'] = unit_mix_page
                elif beds == 3:
                    unit_counts['bed_3'] = units
                    page_sources['unit_counts.bed_3'] = unit_mix_page
            if unit_counts:
                property_data['unit_counts'] = unit_counts

        # Extract amenities
        amenities = self._extract_amenities(text)
        if amenities:
            property_data['amenities'] = amenities

        # Store page sources for source tracking
        property_data['_page_sources'] = page_sources
        self.extracted_data['property'] = property_data

    def _extract_unit_mix(self, text: str) -> Tuple[List[Dict[str, Any]], int]:
        """Extract detailed unit mix breakdown for SUBJECT PROPERTY ONLY.

        IMPORTANT: First determine which bedroom types exist by checking for
        "All X Beds" patterns in the Totals section. Only extract data for
        bedroom types that actually exist.

        Returns tuple of (unit_mix_list, page_number).
        """
        unit_mix = []
        first_match_page = 1  # Default page

        # CRITICAL FIX: Only search within pages 1-3 (Subject Property section)
        # Page markers are in format <<PAGE_X>> where X is the page number
        page_pattern = r'<<PAGE_(\d+)>>'

        # Split text by page markers and track page numbers
        page_splits = re.split(page_pattern, text)
        # page_splits alternates: [content_before_first_marker, page_num, content, page_num, content, ...]

        # Build a dict of page_num -> content
        pages_dict = {}
        if page_splits:
            # Content before first marker (if any) is considered part of page 1
            pages_dict[1] = page_splits[0]
            # Process remaining splits (page_num, content pairs)
            for i in range(1, len(page_splits), 2):
                if i + 1 < len(page_splits):
                    page_num = int(page_splits[i])
                    pages_dict[page_num] = page_splits[i + 1]

        # Get page 1 text only for bedroom type detection
        page1_text = pages_dict.get(1, text)

        # Get pages 1-3 for subject property section
        subject_text = pages_dict.get(1, '') + pages_dict.get(2, '') + pages_dict.get(3, '')

        # STEP 1: Determine which bedroom types ACTUALLY EXIST for this property
        # Look for "All X Beds" patterns in the Totals section of UNIT BREAKDOWN
        # ONLY on page 1 to avoid comparable properties
        existing_bed_types = set()

        # Check for each bedroom type (0=Studio, 1-4=beds) - PAGE 1 ONLY
        if re.search(r'All\s*Studios', page1_text, re.IGNORECASE):
            existing_bed_types.add(0)
        if re.search(r'All\s*1\s*Beds?', page1_text, re.IGNORECASE):
            existing_bed_types.add(1)
        if re.search(r'All\s*2\s*Beds?', page1_text, re.IGNORECASE):
            existing_bed_types.add(2)
        if re.search(r'All\s*3\s*Beds?', page1_text, re.IGNORECASE):
            existing_bed_types.add(3)
        if re.search(r'All\s*4\s*Beds?', page1_text, re.IGNORECASE):
            existing_bed_types.add(4)

        if existing_bed_types:
            print(f"[INFO] Property has bedroom types: {sorted(existing_bed_types)} (from page 1 'All X Beds')")
        else:
            # Fallback: if no "All X Beds" found, try to detect from Bed column in unit breakdown
            # Look for the pattern: Bed column with numbers, followed by unit data
            bed_matches = re.findall(r'(?:^|\s)(\d)\s+[\d.]+\s+[\d,]+\s+\d+\s+[\d.]+%', page1_text)
            if bed_matches:
                for bed in bed_matches[:5]:  # Only first few matches (subject property)
                    existing_bed_types.add(int(bed))
                print(f"[INFO] Bedroom types from unit rows: {sorted(existing_bed_types)}")

        # STEP 2: Extract unit mix data, but ONLY for bedroom types that exist
        # Search pages 1-2 for unit mix data (table may span two pages)
        # But bedroom type detection above is page 1 only to avoid comparable properties
        seen_bedrooms = set()

        # Get pages 1-2 text for extraction
        # IMPORTANT: Use pdfplumber for unit mix extraction because PyPDF2 sometimes
        # misses rows in CoStar tables (e.g., 3BR row missing from North Oak PDF)
        pages_1_2_text = ''
        if hasattr(self, 'current_pdf_path') and self.current_pdf_path:
            try:
                with pdfplumber.open(self.current_pdf_path) as pdf:
                    for i in range(min(2, len(pdf.pages))):
                        pages_1_2_text += f"<<PAGE_{i+1}>>" + (pdf.pages[i].extract_text() or '')
            except Exception as e:
                print(f"[WARN] pdfplumber failed for unit mix: {e}")
                pages_1_2_text = pages_dict.get(1, '') + pages_dict.get(2, '')
        else:
            # Fallback to pages_dict
            pages_1_2_text = pages_dict.get(1, '') + pages_dict.get(2, '')

        # Pattern to match unit mix rows
        # Format: Bed Bath AvgSF Units Mix% Units Mix% $Rent $PSF $Rent $PSF Concessions%
        # Note: Bath can be decimal (e.g., 1.5) so use [\d.]+ instead of \d
        # Note: Use [$] instead of \$ because \$ in raw strings still acts as end-of-line anchor
        pattern = r'(\d)\s+([\d.]+)\s+([\d,]+)\s+(\d+)\s+([\d.]+)%\s+(\d+)\s+([\d.]+)%\s+[$]\s*([\d,]+)\s+[$]\s*([\d.]+)\s+[$]\s*([\d,]+)\s+[$]\s*([\d.]+)\s+([\d.]+)%'

        # Use pages 1-2 for extraction (subject property unit breakdown may span pages)
        match_iter = re.finditer(pattern, pages_1_2_text)
        matches = list(match_iter)

        if matches:
            first_match_page = self._get_page_number(pages_1_2_text, matches[0].start())
            matches = [m.groups() for m in matches]

        if not matches:
            # Try alternate pattern for concatenated text (no spaces)
            # Note: Use [$]? instead of \$? for proper dollar sign matching
            pattern2 = r'(\d)([\d.]+)([\d,]+)(\d+)([\d.]+)%([\d]+)([\d.]+)%[$]?([\d,]+)[$]?([\d.]+)[$]?([\d,]+)[$]?([\d.]+)([\d.]+)%'
            match_iter2 = re.finditer(pattern2, pages_1_2_text)
            matches2 = list(match_iter2)
            if matches2:
                first_match_page = self._get_page_number(pages_1_2_text, matches2[0].start())
                matches = [m.groups() for m in matches2]

        for match in matches:
            try:
                bedrooms = int(match[0])

                # CRITICAL: Only extract if this bedroom type actually exists
                if existing_bed_types and bedrooms not in existing_bed_types:
                    continue  # Skip bedroom types that don't exist for this property

                # Only keep FIRST entry for each bedroom type
                if bedrooms in seen_bedrooms:
                    continue
                seen_bedrooms.add(bedrooms)

                unit_mix.append({
                    'bedrooms': bedrooms,
                    'bathrooms': float(match[1]),  # Can be decimal like 1.5
                    'avg_sf': int(match[2].replace(',', '')),
                    'units': int(match[3]),
                    'mix_pct': float(match[4]),
                    'units_available': int(match[5]),
                    'availability_pct': float(match[6]),
                    'asking_rent_per_unit': int(match[7].replace(',', '')),
                    'asking_rent_psf': float(match[8]),
                    'effective_rent_per_unit': int(match[9].replace(',', '')),
                    'effective_rent_psf': float(match[10]),
                    'concessions_pct': float(match[11])
                })

                # Stop after we have all existing bedroom types
                if len(seen_bedrooms) >= len(existing_bed_types):
                    break

            except (ValueError, IndexError) as e:
                continue

        # Log what we found
        if unit_mix:
            bed_types = [u['bedrooms'] for u in unit_mix]
            print(f"[INFO] Extracted unit mix for bedroom types: {bed_types}")

        return unit_mix, first_match_page

    def _extract_amenities(self, text: str) -> Dict[str, List[str]]:
        """Extract site and unit amenities."""
        amenities = {'site': [], 'unit': []}

        # Extract site amenities section
        site_match = re.search(r'SITE AMENITIES(.*?)UNIT AMENITIES', text, re.DOTALL)
        if site_match:
            site_text = site_match.group(1)
            # Common amenity keywords
            site_amenity_list = [
                'Basketball Court', 'Business Center', 'Clubhouse', 'Concierge',
                'Fitness Center', 'Laundry Facilities', 'Playground', 'Pool',
                'Property Manager on Site', 'Tennis Court', 'Dog Park', 'Garage',
                'Package Room'
            ]
            for amenity in site_amenity_list:
                if amenity in site_text:
                    amenities['site'].append(amenity)

        # Extract unit amenities section
        unit_match = re.search(r'UNIT AMENITIES(.*?)(?:Updated|11/)', text, re.DOTALL)
        if unit_match:
            unit_text = unit_match.group(1)
            unit_amenity_list = [
                'Air Conditioning', 'Balcony', 'Dishwasher', 'Disposal',
                'Fireplace', 'Washer/Dryer', 'Walk-In Closets', 'Vaulted Ceiling',
                'Patio', 'Hardwood Floors', 'Stainless Steel Appliances'
            ]
            for amenity in unit_amenity_list:
                if amenity in unit_text:
                    amenities['unit'].append(amenity)

        return amenities

    def _extract_rent_comp_report(self, pdf_path: str):
        """Extract comprehensive rent comp data from Rent Comp Report PDF."""
        # Get full PDF text with page markers for source tracking
        full_text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        rent_comps = {}
        page_sources = {}  # Track which page each field came from

        # Look for rent comp summary stats: "17$1,314 $1.49 6.7%No. Rent Comps..."
        # Note: no space between comp count and dollar sign in some reports
        match = re.search(r'(\d+)\$?([\d,]+)\s+\$?([\d.]+)\s+([\d.]+)%\s*No\.\s*Rent\s*Comps', full_text)
        if match:
            page = self._get_page_number(full_text, match.start())
            rent_comps['comp_count'] = int(match.group(1))
            rent_comps['avg_comp_rent_per_unit'] = int(match.group(2).replace(',', ''))
            rent_comps['avg_comp_rent_psf'] = float(match.group(3))
            rent_comps['avg_comp_vacancy'] = float(match.group(4))
            page_sources['comp_count'] = page
            page_sources['avg_comp_rent_per_unit'] = page
            page_sources['avg_comp_rent_psf'] = page
            page_sources['avg_comp_vacancy'] = page

        # Use subject_property data if available (more reliable source)
        if 'subject_property' in self.extracted_data:
            sp = self.extracted_data['subject_property']
            sp_pages = sp.get('_page_sources', {})
            if 'competitor_rent' in sp and 'avg_comp_rent_per_unit' not in rent_comps:
                rent_comps['avg_comp_rent_per_unit'] = sp['competitor_rent']
                if 'competitor_rent' in sp_pages:
                    page_sources['avg_comp_rent_per_unit'] = sp_pages['competitor_rent']
            if 'competitor_vacancy' in sp and 'avg_comp_vacancy' not in rent_comps:
                rent_comps['avg_comp_vacancy'] = sp['competitor_vacancy']
                if 'competitor_vacancy' in sp_pages:
                    page_sources['avg_comp_vacancy'] = sp_pages['competitor_vacancy']

        # Subject property current rent - try "Current:" format first
        match = re.search(r'Current:\s*\$?([\d,]+)\s*\$?([\d.]+)\s*/SF', full_text)
        if match:
            page = self._get_page_number(full_text, match.start())
            rent_comps['subject_current_rent'] = int(match.group(1).replace(',', ''))
            rent_comps['subject_current_rent_psf'] = float(match.group(2))
            page_sources['subject_current_rent'] = page
            page_sources['subject_current_rent_psf'] = page

        # If not found, try to extract from rent comp table using property unit count
        # Format: "184 1,052 - - $1,330 $1,471 $1.33" (units SF ... rents... $/SF)
        if 'subject_current_rent_psf' not in rent_comps and 'property' in self.extracted_data:
            unit_count = self.extracted_data['property'].get('units')
            if unit_count:
                # Find subject line: units avgSF ... $X.XX (rent/SF is last dollar amount with decimals)
                pattern = rf'{unit_count}\s+[\d,]+\s+.*?\$([\d.]+)\s*\d{{4}}'
                match = re.search(pattern, full_text)
                if match:
                    psf = float(match.group(1))
                    if 0.5 <= psf <= 5.0:  # Sanity check for rent/SF
                        rent_comps['subject_current_rent_psf'] = psf
                        page_sources['subject_current_rent_psf'] = self._get_page_number(full_text, match.start())

        # Calculate subject_current_rent (avg rent per unit) from rent/SF × avg unit size
        if 'subject_current_rent' not in rent_comps:
            psf = rent_comps.get('subject_current_rent_psf')
            avg_sf = self.extracted_data.get('property', {}).get('avg_unit_size')
            if psf and avg_sf:
                rent_comps['subject_current_rent'] = int(psf * avg_sf)
                # Source is calculated, but use same page as psf
                if 'subject_current_rent_psf' in page_sources:
                    page_sources['subject_current_rent'] = page_sources['subject_current_rent_psf']

        # Year ago rent
        match = re.search(r'Year Ago:\s*\$?([\d,]+)', full_text)
        if match:
            rent_comps['subject_rent_year_ago'] = int(match.group(1).replace(',', ''))
            page_sources['subject_rent_year_ago'] = self._get_page_number(full_text, match.start())

        # Competitor averages
        match = re.search(r'Competitors:\s*\$?([\d,]+)', full_text)
        if match:
            rent_comps['competitor_avg_rent'] = int(match.group(1).replace(',', ''))
            page_sources['competitor_avg_rent'] = self._get_page_number(full_text, match.start())

        # Submarket averages
        match = re.search(r'Submarket:\s*\$?([\d,]+)', full_text)
        if match:
            rent_comps['submarket_avg_rent'] = int(match.group(1).replace(',', ''))
            page_sources['submarket_avg_rent'] = self._get_page_number(full_text, match.start())

        # Extract individual rent comps from the summary table
        comp_properties = self._parse_rent_comps_from_combined(full_text)
        if comp_properties:
            # Enrich with vacancy, city/state, distance from other pages
            comp_properties = self._enrich_rent_comps_with_details(comp_properties, full_text)
            rent_comps['comparable_properties'] = comp_properties
            if 'comp_count' not in rent_comps:
                rent_comps['comp_count'] = len(comp_properties)

        # Store page sources
        rent_comps['_page_sources'] = page_sources
        self.extracted_data['rent_comps'] = rent_comps

    def _parse_rent_comps_from_combined(self, text: str) -> List[Dict[str, Any]]:
        """Parse rent comps from combined PDF format."""
        comps = []

        # Find the RENT comp section - identified by "Studio 1 Bed 2 Bed 3 Bed" columns
        comp_section_match = re.search(r'Studio\s+1\s*Bed\s+2\s*Bed\s+3\s*Bed(.*?)(?:Rent Comparables Photo|Page \d{2,}|$)', text, re.DOTALL)
        if not comp_section_match:
            return comps

        comp_text = comp_section_match.group(1)
        lines = comp_text.split('\n')

        current_name = None
        for i, line in enumerate(lines):
            line = line.strip()

            # Skip empty lines, dashes, and headers
            if not line or line == '-' or 'Rent Comparables' in line or 'Property Size' in line:
                continue

            # NEW FORMAT: Property name directly followed by units on same line
            # Example: "The Jefferson on the Lake352 663 - $1,260 $1,376 - $2.0012251-12289 S Strang Lin...1 1986"
            # Pattern: PropertyName + Units(2-4 digit) + Space + AvgSF(3-5 digit, may have comma)
            combined_match = re.search(r'^([A-Za-z][A-Za-z\s\-\'\.]+?)(\d{2,4})\s+([\d,]{3,5})\s+', line)

            if combined_match:
                try:
                    name = combined_match.group(1).strip()
                    units = int(combined_match.group(2))
                    avg_sf = int(combined_match.group(3).replace(',', ''))

                    # Only process if units and SF are reasonable
                    if 20 <= units <= 1000 and 400 <= avg_sf <= 2000:
                        comp = {
                            'name': self._clean_property_name(name),
                            'units': units,
                            'avg_sf': avg_sf
                        }

                        # Extract rent values - $X,XXX format (not PSF which is $X.XX)
                        rent_matches = re.findall(r'\$([\d,]+)(?!\.\d)', line)
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
                            comp['rent_1bed'] = rents[0]

                        # Extract rent PSF - $X.XX format
                        psf_match = re.search(r'\$(\d+\.\d{2})', line)
                        if psf_match:
                            comp['rent_psf'] = float(psf_match.group(1))

                        # Extract year built - last 4-digit number that's a valid year
                        year_matches = re.findall(r'(\d{4})', line)
                        for ym in reversed(year_matches):
                            year = int(ym)
                            if 1960 <= year <= 2025:
                                comp['year_built'] = year
                                break

                        # Extract address - pattern after rent/SF, before rank+year
                        # Format: "$2.00{Address}{Rank} {Year}" e.g. "$2.0012251-12289 S Strang Lin1 1986"
                        addr_match = re.search(r'\$\d+\.\d{2}([\d\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Tfwy|Pkwy|Cir|Pl|Hwy|Loop|Pky|Lin))', line, re.IGNORECASE)
                        if addr_match:
                            address = addr_match.group(1).strip()
                            # Street number is part of address - keep it
                            if len(address) > 5:
                                comp['address'] = address

                        comps.append(comp)
                except (ValueError, IndexError):
                    pass
                continue

            # OLD FORMAT: Check if this is a data line that starts with "units avgSF" pattern
            # Format: "352 663 - $1,151 $1,288 - $1.85 Address1 1986"
            data_match = re.match(r'^(\d{2,4})\s+([\d,]+)\s+', line)

            if data_match:
                # This is a data line - use the previous non-empty line as name
                if current_name and len(current_name) > 3:
                    try:
                        units = int(data_match.group(1))
                        avg_sf = int(data_match.group(2).replace(',', ''))

                        # Only process if units and SF are reasonable
                        if 20 <= units <= 1000 and 400 <= avg_sf <= 2000:
                            comp = {
                                'name': self._clean_property_name(current_name),
                                'units': units,
                                'avg_sf': avg_sf
                            }

                            # Extract rent values - $X,XXX format (not PSF which is $X.XX)
                            rent_matches = re.findall(r'\$([\d,]+)(?!\.\d)', line)
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
                                comp['rent_1bed'] = rents[0]

                            # Extract rent PSF - $X.XX format
                            psf_match = re.search(r'\$(\d+\.\d{2})', line)
                            if psf_match:
                                comp['rent_psf'] = float(psf_match.group(1))

                            # Extract year built - last 4-digit number that's a valid year
                            year_matches = re.findall(r'(\d{4})', line)
                            for ym in reversed(year_matches):
                                year = int(ym)
                                if 1960 <= year <= 2025:
                                    comp['year_built'] = year
                                    break

                            # Extract address - pattern after rent/SF, before rank+year
                            # Format: "$1.58 97 NE 97th St 1 2021" or "$1.58 8501 N Platte Purchase Dr 3 2007"
                            addr_match = re.search(r'\$\d+\.\d{2}([\d\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Tfwy|Pkwy|Cir|Pl|Hwy|Loop|Pky))\d*\s*\d{4}', line, re.IGNORECASE)
                            if addr_match:
                                address = addr_match.group(1).strip()
                                # Street number is part of address - keep it
                                if len(address) > 5:
                                    comp['address'] = address

                            comps.append(comp)
                    except (ValueError, IndexError):
                        pass

                current_name = None
            else:
                # This might be a property name
                # Property names don't start with numbers and aren't addresses
                if len(line) > 3 and not line[0].isdigit() and not re.match(r'^\d+\s', line):
                    current_name = line

        # Filter out subject property from comps list
        subject_address = self.extracted_data.get('property', {}).get('address', '')
        subject_name = self.extracted_data.get('property', {}).get('name', '')

        if subject_address:
            comps = [c for c in comps if subject_address.lower() not in c.get('address', '').lower()]

        # Filter by subject property name (case insensitive partial match)
        if subject_name:
            subject_name_lower = subject_name.lower()
            # Remove common words for matching
            subject_key = subject_name_lower.replace('apartments', '').replace('apartment', '').strip()
            comps = [c for c in comps if subject_key not in c.get('name', '').lower()]

        return comps[:17]  # Limit to 17 comps

    def _extract_rent_comp_vacancy_from_photos(self, text: str) -> Dict[str, Dict[str, Any]]:
        """
        Extract vacancy, stories from photo comparison pages.
        Format: "Vacancy 12.7%\n8201 Renner Rd\n260 Units / 3 Stories\nOwner: ...Rent/SF{PropertyName}\n{rank}"
        Returns dict keyed by property name for matching.
        """
        details = {}

        # NEW format: Vacancy X.X%\n{address}\n{units} Units / {stories} Stories\nOwner:...Rent/SF{name}\n{rank}
        # The property name comes after Rent/SF, followed by the rank number on next line
        photo_sections = re.findall(
            r'Vacancy\s+([\d.]+)%\s*\n([^\n]+)\n(\d+)\s*Units\s*/\s*(\d+)\s*Stor.*?Rent/SF([A-Za-z][A-Za-z\s\-\'\.]+?)\n\s*(\d+)',
            text, re.DOTALL
        )

        for match in photo_sections:
            vacancy = float(match[0])
            address = match[1].strip()
            units = int(match[2])
            stories = int(match[3])
            name = match[4].strip()
            rank = match[5]

            # Clean name - remove trailing special chars
            name = re.sub(r'[\-\ufffd]+$', '', name).strip()

            details[name.lower()] = {
                'vacancy': vacancy,
                'stories': stories,
                'address_from_photo': address
            }

        # Also try alternate format with dollar amount (older PDF format)
        alt_sections = re.findall(
            r'Vacancy\s+([\d.]+)%\s*\n([^\n]+?)(\d+)\s*Units\s*/\s*(\d+)\s*Stor.*?Rent/SF\s*\$([\d.]+),([^\n]+)',
            text, re.DOTALL
        )

        for match in alt_sections:
            vacancy = float(match[0])
            address = match[1].strip()
            units = int(match[2])
            stories = int(match[3])
            name = match[5].strip()

            name = re.sub(r'\s*\d+$', '', name).strip()

            if name.lower() not in details:
                details[name.lower()] = {
                    'vacancy': vacancy,
                    'stories': stories,
                    'address_from_photo': address
                }

        return details

    def _extract_rent_comp_detail_pages(self, text: str) -> Dict[str, Dict[str, Any]]:
        """
        Extract city, state, neighborhood, distance from individual comp detail pages.
        Format: "{Address} - {PropertyName}\n{City}, {State} - {Neighborhood} Neighborhood\n...\n{distance} Miles"
        """
        details = {}

        # New format: Address - Name on one line, City, State - Neighborhood on next line
        # Example: "1890 N Lennox St - Arlo of Olathe\nOlathe, Kansas - Ridgeview Neighborhood"
        detail_pattern = re.compile(
            r'([\d\-]+[\d\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Pkwy|Pky|Cir|Pl|Tfwy))\s*-\s*([A-Za-z][A-Za-z\s\-\'\.]+?)\n([A-Z][a-z]+(?:\s[A-Z][a-z]+)?),\s*([A-Za-z]+)\s*-\s*([A-Za-z\s]+?)Neighborhood',
            re.MULTILINE
        )

        # Also find distances separately - they appear later on the page
        distance_pattern = re.compile(r'([\d.]+)\s*Miles')

        for match in detail_pattern.finditer(text):
            address = match.group(1).strip()
            name = match.group(2).strip()
            city = match.group(3).strip()
            state = match.group(4).strip()
            neighborhood = match.group(5).strip()

            # Clean name - remove trailing city name if concatenated (no space before city)
            # e.g., "Arlo of OlatheOlathe" -> remove second "Olathe"
            city_pattern = re.compile(rf'(?<=[a-z]){re.escape(city)}$', re.IGNORECASE)
            name = city_pattern.sub('', name).strip()

            # Also remove any trailing "Apartments" duplication
            name = re.sub(r'Apartments$', '', name).strip()

            # Clean city - remove any newlines or duplicates
            city = city.replace('\n', ' ').strip()
            city = re.sub(r'(\w+)\s*\1', r'\1', city)  # Remove immediate duplicates

            # Find distance for this property (look ahead in text after the match)
            post_match_text = text[match.end():match.end()+500]
            distance_match = distance_pattern.search(post_match_text)
            distance = float(distance_match.group(1)) if distance_match else None

            detail_data = {
                'city': city,
                'state': state,
                'neighborhood': neighborhood,
                'distance': distance,
                'address': address
            }

            # Store by name (lowercase) for name matching
            details[name.lower()] = detail_data
            # Also store by address for address matching
            details[f'addr:{address.lower()}'] = detail_data

        return details

    def _extract_rent_comp_unit_counts(self, text: str) -> Dict[str, Dict[str, int]]:
        """
        Extract unit counts by bedroom type from rent comp detail pages.
        Format: Property header line followed by "All Studios XXX N" or "All 1 Beds XXX N"
        Returns dict keyed by property name (lowercase) for matching.
        """
        unit_counts = {}

        # Split text into pages/sections by "Rent Comparables" header
        # Each rent comp detail page starts with "Rent Comparables{subject address}"
        pages = re.split(r'Rent Comparables\d+[\d\-]+\s+[A-Z]', text)

        for page in pages:
            if 'All 1 Beds' not in page and 'All Studios' not in page and 'All 2 Beds' not in page:
                continue

            # Extract property name from the page header
            # Format: "{rank}{address} - {name}{city}, {state}"
            # Look for pattern like: "1890 N Lennox St - Arlo of OlatheOlathe, Kansas"
            name_match = re.search(
                r'\d+[\w\s\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Pkwy|Cir|Pl|Tfwy)\s*-\s*([A-Za-z][^\d]+?)(?:[A-Z][a-z]+,\s*[A-Za-z]+)',
                page
            )

            if not name_match:
                continue

            name = name_match.group(1).strip()
            # Clean up - only remove trailing city name if directly concatenated (no space before it)
            # E.g., "Hawthorne ApartmentsOverland" -> "Hawthorne Apartments"
            # But NOT "Arlo of Olathe" -> keep as is (space before city)
            name = re.sub(r'(?<=[a-z])(?:Olathe|Overland|Lenexa|Kansas City|Kansas|Park)$', '', name).strip()

            counts = {}

            # Extract unit counts - format: "All X Beds/Studios {avg_sf} {unit_count} {mix%}..."
            # The unit count is the SECOND number after the bed type

            # Studios: "All Studios 650 4 1.0%..." -> 4 is unit count
            studio_match = re.search(r'All Studios\s+(\d+)\s+(\d+)\s+[\d.]+%', page)
            if studio_match:
                counts['studio'] = int(studio_match.group(2))

            # 1 Beds: "All 1 Beds 564 160 45.5%..." -> 160 is unit count
            bed1_match = re.search(r'All 1 Beds\s+([\d,]+)\s+(\d+)\s+[\d.]+%', page)
            if bed1_match:
                counts['1bed'] = int(bed1_match.group(2))

            # 2 Beds: "All 2 Beds 746 192 54.5%..." -> 192 is unit count
            bed2_match = re.search(r'All 2 Beds\s+([\d,]+)\s+(\d+)\s+[\d.]+%', page)
            if bed2_match:
                counts['2bed'] = int(bed2_match.group(2))

            # 3 Beds: "All 3 Beds 1,450 22 3.0%..." -> 22 is unit count
            bed3_match = re.search(r'All 3 Beds\s+([\d,]+)\s+(\d+)\s+[\d.]+%', page)
            if bed3_match:
                counts['3bed'] = int(bed3_match.group(2))

            # Extract concession % from Totals line
            # Format: "Totals 663 352 100% 42 11.9% $1,226 $1.85 $1,217 $1.84 0.7%"
            # The concession is the LAST percentage on the line
            totals_match = re.search(r'Totals\s+[\d,]+\s+\d+\s+100%.*?(\d+\.\d+)%\s*$', page, re.MULTILINE)
            if totals_match:
                counts['concession'] = float(totals_match.group(1))

            if counts and name:
                unit_counts[name.lower()] = counts

        return unit_counts


    def _clean_city(self, city: str) -> str:
        """Clean up city name - remove duplicates, newlines, extra text."""
        if not city:
            return city
        # Remove newlines
        city = city.replace('\n', ' ').strip()
        # Remove "Apartments" or similar if accidentally captured
        city = re.sub(r'^Apartments?\s*', '', city, re.IGNORECASE).strip()
        # Remove duplicate words (e.g., "Olathe Olathe" -> "Olathe")
        words = city.split()
        seen = []
        for w in words:
            if not seen or w.lower() != seen[-1].lower():
                seen.append(w)
        return ' '.join(seen)

    def _enrich_rent_comps_with_details(self, comps: List[Dict], text: str) -> List[Dict]:
        """Enrich rent comps with vacancy, city/state, distance, unit counts from other pages."""
        photo_details = self._extract_rent_comp_vacancy_from_photos(text)
        page_details = self._extract_rent_comp_detail_pages(text)
        unit_count_details = self._extract_rent_comp_unit_counts(text)

        for comp in comps:
            name_lower = comp.get('name', '').lower()
            address_lower = comp.get('address', '').lower()

            # Try to match vacancy by name (fuzzy matching)
            for key, details in photo_details.items():
                if key in name_lower or name_lower in key or (len(name_lower) > 8 and name_lower[:8] in key):
                    if 'vacancy' not in comp:
                        comp['vacancy'] = details.get('vacancy')
                    if 'stories' not in comp:
                        comp['stories'] = details.get('stories')
                    break

            # Try to match city/state/distance/neighborhood
            matched = False

            # First try exact address matching (most reliable)
            if address_lower:
                addr_key = f'addr:{address_lower}'
                if addr_key in page_details:
                    details = page_details[addr_key]
                    comp['city'] = self._clean_city(details.get('city'))
                    comp['state'] = details.get('state')
                    comp['neighborhood'] = details.get('neighborhood')
                    comp['distance'] = details.get('distance')
                    matched = True
                else:
                    # Try partial address match (street number match)
                    for key, details in page_details.items():
                        if key.startswith('addr:'):
                            detail_addr = details.get('address', '').lower()
                            if detail_addr and address_lower:
                                # Extract street numbers for comparison
                                addr_num = re.match(r'^(\d+)', address_lower)
                                detail_num = re.match(r'^(\d+)', detail_addr)
                                if addr_num and detail_num and addr_num.group(1) == detail_num.group(1):
                                    comp['city'] = self._clean_city(details.get('city'))
                                    comp['state'] = details.get('state')
                                    comp['neighborhood'] = details.get('neighborhood')
                                    comp['distance'] = details.get('distance')
                                    matched = True
                                    break

            # Fall back to name matching if address didn't match
            if not matched:
                for key, details in page_details.items():
                    if not key.startswith('addr:'):
                        # Check name overlap
                        if key in name_lower or name_lower in key:
                            comp['city'] = self._clean_city(details.get('city'))
                            comp['state'] = details.get('state')
                            comp['neighborhood'] = details.get('neighborhood')
                            comp['distance'] = details.get('distance')
                            matched = True
                            break
                        # Try first 8 chars for truncated names
                        elif len(name_lower) > 8 and len(key) > 8:
                            if name_lower[:8] in key or key[:8] in name_lower:
                                comp['city'] = self._clean_city(details.get('city'))
                                comp['state'] = details.get('state')
                                comp['neighborhood'] = details.get('neighborhood')
                                comp['distance'] = details.get('distance')
                                matched = True
                                break

            # Match unit counts and concession by name
            for key, counts in unit_count_details.items():
                if key in name_lower or name_lower in key or (len(name_lower) > 8 and name_lower[:8] in key):
                    if counts.get('studio'):
                        comp['unit_count_studio'] = counts['studio']
                    if counts.get('1bed'):
                        comp['unit_count_1bed'] = counts['1bed']
                    if counts.get('2bed'):
                        comp['unit_count_2bed'] = counts['2bed']
                    if counts.get('3bed'):
                        comp['unit_count_3bed'] = counts['3bed']
                    if counts.get('concession') is not None:
                        comp['concession'] = counts['concession']
                    break

        return comps

    def _extract_rent_comp_details(self, text: str) -> List[Dict[str, Any]]:
        """Extract individual comparable property details."""
        comps = []

        # Look for comp summary statistics first
        match = re.search(r'(\d+)\s*No\.\s*Rent\s*Comps\s*\$?([\d,]+)\s*Avg\.\s*Rent\s*Per\s*Unit\s*\$?([\d.]+)\s*Avg\.\s*Rent\s*Per\s*SF\s*([\d.]+)%\s*Avg\.\s*Vacancy\s*Rate', text)
        if match:
            comps.append({
                'comp_count': int(match.group(1)),
                'avg_rent_per_unit': int(match.group(2).replace(',', '')),
                'avg_rent_psf': float(match.group(3)),
                'avg_vacancy_rate': float(match.group(4))
            })

        return comps

    def _parse_rent_comps_page(self, text: str) -> List[Dict[str, Any]]:
        """Parse individual rent comparable properties from page 7."""
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        comps = []
        current_name = None

        for line in lines:
            # Skip header and dividers
            if line == '-' or 'Rent Comparables Summary' in line or 'Property Name' in line:
                continue

            # Check if this line has data pattern (starts with digits for units)
            data_match = re.match(r'^(\d+)\s+([\d,]+)', line)

            if data_match and current_name:
                # This is a data line for the previous name
                try:
                    comp = self._parse_comp_data_line(current_name, line)
                    if comp:
                        comps.append(comp)
                except:
                    pass  # Skip failed parses
                current_name = None
            else:
                # This is likely a property name
                if line and not line.isdigit() and len(line) > 5:
                    current_name = line

        return comps

    def _parse_comp_data_line(self, name: str, line: str) -> Dict[str, Any]:
        """Parse a single comp data line."""
        # Clean property name - remove encoding artifacts and truncate if needed
        clean_name = self._clean_property_name(name)
        comp = {'name': clean_name}

        parts = line.split()

        # First two numbers are units and avg SF
        try:
            comp['units'] = int(parts[0])
            comp['avg_sf'] = int(parts[1].replace(',', ''))
        except:
            return None

        # Find year built - check for renovation format (YYYY/YYYY) first
        year_reno_match = re.search(r'(\d{4})/(\d{4})', line)
        if year_reno_match:
            # Preserve both original build and renovation year
            comp['year_built'] = int(year_reno_match.group(1))
            comp['year_renovated'] = int(year_reno_match.group(2))
            comp['year_built_display'] = f"{year_reno_match.group(1)}/{year_reno_match.group(2)}"
        else:
            # Just the build year
            year_match = re.search(r'(\d{4})$', line)
            if year_match:
                comp['year_built'] = int(year_match.group(1))

        # Find rent PSF - look for $X.XX pattern (2 decimal places)
        rent_psf_match = re.search(r'\$(\d+\.\d{2})', line)
        if rent_psf_match:
            comp['rent_psf'] = float(rent_psf_match.group(1))

        # Find rent values - $X,XXX format
        rent_matches = re.findall(r'\$(\d{1,2}),(\d{3})', line)
        rents = [int(m[0] + m[1]) for m in rent_matches]

        # Assign rents to bedroom types (assuming order: studio, 1bed, 2bed, 3bed)
        if len(rents) >= 1:
            comp['rent_1bed'] = rents[0] if len(rents) == 1 else (rents[1] if len(rents) >= 2 else None)
        if len(rents) >= 2:
            comp['rent_2bed'] = rents[1] if len(rents) == 2 else (rents[2] if len(rents) >= 3 else None)
        if len(rents) >= 3:
            comp['rent_3bed'] = rents[2] if len(rents) == 3 else (rents[3] if len(rents) >= 4 else None)

        return comp

    def _extract_sale_comp_report(self, pdf_path: str):
        """Extract sale comparable data from PDF."""
        full_text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        sale_comps = {}
        page_sources = {}  # Track which page each field came from

        # Look for sale comp summary stats
        # Format: "North Oak Crossing Apartments12 $122 $24.7 13.7%Sale Comparables"
        # The count comes right after the property name
        match = re.search(r'Apartments\s*(\d+)\s+\$?([\d,]+)\s+\$?([\d.]+)\s+([\d.]+)%\s*Sale Comparables', full_text)
        if match:
            page = self._get_page_number(full_text, match.start())
            sale_comps['comp_count'] = int(match.group(1))
            sale_comps['avg_price_per_unit'] = int(match.group(2).replace(',', '')) * 1000  # In thousands
            sale_comps['avg_price'] = float(match.group(3)) * 1000000  # In millions
            sale_comps['avg_vacancy_at_sale'] = float(match.group(4))
            page_sources['comp_count'] = page
            page_sources['avg_price_per_unit'] = page
            page_sources['avg_price'] = page
            page_sources['avg_vacancy_at_sale'] = page

        # Extract individual sale comps from the summary table
        # Format: "7005 N Bales AveThe Bluffs- 1 1968 138 8.0% 9/19/2025 $11,700,000 $84,782 $90"
        comp_properties = self._parse_sale_comps(full_text)
        if comp_properties:
            # Enrich with detail page data (submarket, distance, cap rate, type)
            comp_properties = self._enrich_sale_comps_with_details(comp_properties, full_text)
            sale_comps['comparable_properties'] = comp_properties
            if 'comp_count' not in sale_comps:
                sale_comps['comp_count'] = len(comp_properties)

        # Store page sources
        sale_comps['_page_sources'] = page_sources
        self.extracted_data['sale_comps'] = sale_comps

    def _parse_sale_comps(self, text: str) -> List[Dict[str, Any]]:
        """Parse sale comps from combined PDF format."""
        comps = []

        # Find the SALE comp section - look for "Sale Date Price Price/Unit Price/SF"
        comp_section_match = re.search(r'Sale Date\s+Price\s+Price/Unit\s+Price/SF\s*Sale Information(.*?)(?:Page \d{2,}|Sale Comparables Photo|$)', text, re.DOTALL)
        if not comp_section_match:
            return comps

        comp_text = comp_section_match.group(1)
        lines = comp_text.split('\n')

        current_addr_name = None

        for line in lines:
            line = line.strip()
            if not line or line == '-' or 'Sale Comparables' in line:
                continue

            # Check if line has sale data: rank year units vacancy% date price price/unit price/sf
            # Format: " 1 1968 138 8.0% 9/19/2025 $11,700,000 $84,782 $90"
            sale_match = re.search(r'^\s*(\d+)\s+(\d{4})\s+(\d+)\s+([\d.]+)%\s+(\d{1,2}/\d{1,2}/\d{4})\s+\$([\d,]+)\s+\$([\d,]+)\s+\$(\d+)', line)

            if sale_match:
                # This is a data line - parse the previous address/name line
                if current_addr_name:
                    try:
                        # Parse address + name from combined line
                        # Format: "7005 N Bales AveThe Bluffs-" or "6201 NW 70th StHunters Glen Apartments-"
                        # Use non-greedy match and look for capital letter after street suffix
                        # Match: number + words + St/Ave/etc, then capital letter starts name
                        # Include numbered streets like "61st", "70th", "133rd"
                        street_types = r'(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Pkwy|Pky|Cir|Pl|Tfwy|\d+(?:st|nd|rd|th))'
                        # Optional direction suffix (N/S/E/W) followed by capital+lowercase (name start)
                        direction_suffix = r'(?:\s?[NSEW](?=[A-Z][a-z]))?'
                        addr_name_match = re.match(rf'^(\d+.*?{street_types}{direction_suffix})([A-Z][a-z].*?)[-\ufffd]?$', current_addr_name)

                        address = ''
                        name = ''
                        if addr_name_match:
                            address = addr_name_match.group(1).strip()
                            name = addr_name_match.group(2).strip() if addr_name_match.group(2) else ''
                        else:
                            # Fallback - just use whole line as name
                            name = current_addr_name.rstrip('-').rstrip('\ufffd')

                        comp = {
                            'name': self._clean_property_name(name) if name else f'Comp {sale_match.group(1)}',
                            'rank': int(sale_match.group(1)),
                            'year_built': int(sale_match.group(2)),
                            'units': int(sale_match.group(3)),
                            'vacancy_at_sale': float(sale_match.group(4)),
                            'sale_date': sale_match.group(5),
                            'sale_price': int(sale_match.group(6).replace(',', '')),
                            'price_per_unit': int(sale_match.group(7).replace(',', '')),
                            'price_per_sf': int(sale_match.group(8))
                        }
                        if address:
                            comp['address'] = address

                        comps.append(comp)
                    except (ValueError, IndexError):
                        pass

                current_addr_name = None
            else:
                # This is likely an address/name line (before the data line)
                # Format: "7005 N Bales AveThe Bluffs-"
                if len(line) > 5 and re.search(r'(St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Pkwy|Pky|Cir|Pl)', line, re.IGNORECASE):
                    current_addr_name = line

        return comps[:15]  # Limit to 15 sale comps

    def _enrich_sale_comps_with_details(self, comps: List[Dict], text: str) -> List[Dict]:
        """
        Enrich sale comps with submarket, distance, cap rate, type from detail pages.
        Sale comp detail format:
        "{Name} - {Address}\n{City}, {State} {ZIP} - {Submarket} Neighborhood\n...\n{distance} Miles"
        """
        # Use a combined pattern that matches "Name - Address\nCity, State ZIP - Submarket Neighborhood"
        # This ensures we get the Name directly above the City line
        # Note: City can have apostrophes (e.g., "Lee's Summit")
        # Street suffixes include numbered streets like 61st, 70th
        combined_pattern = re.compile(
            r"([A-Z][A-Za-z0-9][A-Za-z0-9 \t\-'\.]+?)\s*-\s*"  # Name - (allow digits like "Altitude 970")
            r"(\d+[A-Za-z\d \t\-]+(?:St|Ave|Blvd|Rd|Dr|Ter|Ct|Ln|Way|Pkwy|Pky|Cir|Pl|Tfwy|\d+(?:st|nd|rd|th)))\n"  # Address\n
            r"([A-Z][a-z']+(?:\s[A-Z][a-z']+)?),\s*([A-Z]{2})\s+(\d{5})\s*-\s*([A-Za-z\s\-]+?)Neighborhood",  # City, ST ZIP - Sub Neighborhood (allow hyphen in submarket)
            re.MULTILINE
        )

        # Build lookup by property name
        detail_info = {}
        for match in combined_pattern.finditer(text):
            name = match.group(1).strip()
            address = match.group(2).strip()
            city = match.group(3).strip()
            state = match.group(4).strip()
            zipcode = match.group(5)
            submarket = match.group(6).strip()

            # Skip if name looks like a footer/header
            if 'Page' in name or 'CoStar' in name or 'Leeds' in name:
                continue

            # Look for distance, cap rate, type after this match
            post_text = text[match.end():match.end()+800]

            distance_match = re.search(r'([\d.]+)\s*Miles', post_text)
            distance = float(distance_match.group(1)) if distance_match else None

            cap_rate_match = re.search(r'Cap Rate:\s*([\d.]+)%', post_text)
            cap_rate = float(cap_rate_match.group(1)) if cap_rate_match else None

            type_match = re.search(r'Type:\s*([A-Za-z\s\-]+?)(?:\n|Rent)', post_text)
            prop_type = type_match.group(1).strip() if type_match else None

            detail_info[name.lower()] = {
                'submarket': submarket,
                'distance': distance,
                'cap_rate': cap_rate,
                'type': prop_type,
                'city': city,
                'state': state
            }
            detail_info[f'addr:{address.lower()}'] = detail_info[name.lower()]

        # Enrich each comp
        for comp in comps:
            name_lower = comp.get('name', '').lower()
            address_lower = comp.get('address', '').lower()

            # Try address match first
            matched_info = None
            if address_lower and f'addr:{address_lower}' in detail_info:
                matched_info = detail_info[f'addr:{address_lower}']
            else:
                # Try name match
                for key, info in detail_info.items():
                    if not key.startswith('addr:'):
                        if key in name_lower or name_lower in key:
                            matched_info = info
                            break
                        # Try partial match
                        elif len(name_lower) > 6 and len(key) > 6:
                            if name_lower[:6] in key or key[:6] in name_lower:
                                matched_info = info
                                break

            if matched_info:
                if matched_info.get('submarket'):
                    comp['submarket'] = matched_info['submarket']
                if matched_info.get('distance'):
                    comp['distance'] = matched_info['distance']
                if matched_info.get('cap_rate'):
                    comp['cap_rate'] = matched_info['cap_rate']
                if matched_info.get('type'):
                    comp['type'] = matched_info['type']
                if matched_info.get('city') and 'city' not in comp:
                    comp['city'] = matched_info['city']
                if matched_info.get('state') and 'state' not in comp:
                    comp['state'] = matched_info['state']

        return comps

    def _extract_market_report(self, pdf_path: str):
        """Extract comprehensive market data from Asset/Market Report PDF."""
        # Search full PDF for market data - include page markers for source tracking
        text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        market_data = {}
        page_sources = {}  # Track which page each field came from

        # 12 month metrics from OVERALL section
        # NOTE: In submarket-only reports, this IS the submarket vacancy (not market)
        # Format: "289 131 9.7% -6.4%" before "12 Mo Delivered Units..." header
        # Note: rent growth can be negative (e.g., -6.4%)
        match = re.search(r'([\d,]+)\s+([\d,]+)\s+([\d.]+)%\s+(-?[\d.]+)%\s*12 Mo Delivered Units\s*12 Mo Absorption Units\s*Vacancy Rate\s*12 Mo Asking Rent Growth', text)
        if match:
            page = self._get_page_number(text, match.start())
            market_data['delivered_12mo'] = int(match.group(1).replace(',', ''))
            market_data['absorption_12mo'] = int(match.group(2).replace(',', ''))
            market_data['submarket_vacancy_rate'] = float(match.group(3))
            market_data['asking_rent_growth'] = float(match.group(4))
            # Track page sources
            page_sources['delivered_12mo'] = page
            page_sources['absorption_12mo'] = page
            page_sources['submarket_vacancy_rate'] = page
            page_sources['asking_rent_growth'] = page

        # Under construction
        match = re.search(r'([\d,]+)\s*units\s*under\s*construction', text, re.IGNORECASE)
        if match:
            page = self._get_page_number(text, match.start())
            market_data['under_construction'] = int(match.group(1).replace(',', ''))
            page_sources['under_construction'] = page
        else:
            # Check for "no projects under construction" = 0
            if re.search(r'no.*(?:projects?|units?).*under\s*construction', text, re.IGNORECASE):
                market_data['under_construction'] = 0

        # === VACANCY TRENDS (from Annual Trends table on pg 58) ===
        # Full text format: "6.6% 7.8% -1.1% (YOY) Vacancy" (columns read L-to-R)
        # Groups: 1=Forecast Avg, 2=Historical Avg, 3=YoY change
        vacancy_trend_match = re.search(
            r'([\d.]+)%\s+([\d.]+)%\s+(-?[\d.]+)%\s*\(YOY\)\s*Vacancy',
            text, re.IGNORECASE
        )
        if vacancy_trend_match:
            page = self._get_page_number(text, vacancy_trend_match.start())
            market_data['vacancy_yoy_change'] = float(vacancy_trend_match.group(3))
            market_data['vacancy_historical_avg'] = float(vacancy_trend_match.group(2))
            market_data['vacancy_forecast_avg'] = float(vacancy_trend_match.group(1))
            page_sources['vacancy_yoy_change'] = page
            page_sources['vacancy_historical_avg'] = page
            page_sources['vacancy_forecast_avg'] = page
            print(f"[INFO] Vacancy trends: YoY={market_data['vacancy_yoy_change']}%, Hist Avg={market_data['vacancy_historical_avg']}%, Forecast Avg={market_data['vacancy_forecast_avg']}%")

        # Population growth mention
        if 'population growth' in text.lower():
            market_data['has_population_growth'] = True

        # Rent growth trend
        match = re.search(r'rents\s*increased\s*by\s*([\d.]+)%', text, re.IGNORECASE)
        if match:
            page = self._get_page_number(text, match.start())
            market_data['rent_growth_actual'] = float(match.group(1))
            page_sources['rent_growth_actual'] = page

        # === SUBMARKET DETECTION (do this first, needed for rent growth) ===
        # Find the property's submarket from "{SUBMARKET} SUBMARKET SALES VOLUME IN UNITS" pattern
        property_submarket = ''
        submarket_match = re.search(r'([A-Z][A-Z ]+)\s+SUBMARKET SALES VOLUME IN UNITS', text)
        if submarket_match:
            property_submarket = submarket_match.group(1).strip()
            market_data['property_submarket'] = property_submarket

            # Find vacancy rate from SUBMARKET VACANCY & ABSORPTION table
            vacancy_section_match = re.search(r'SUBMARKET VACANCY & ABSORPTION(.*?)(?:SUBMARKET RENT|Page \d|$)', text, re.DOTALL)
            if vacancy_section_match:
                vacancy_section = vacancy_section_match.group(1)
                vacancy_pattern = rf'\d+\s+{re.escape(property_submarket)}\s+([\d,]+)\s+([\d.]+)%'
                vacancy_match = re.search(vacancy_pattern, vacancy_section, re.IGNORECASE)
                if vacancy_match:
                    market_data['submarket_vacancy_rate'] = float(vacancy_match.group(2))

        # === RENT GROWTH EXTRACTION ===
        # NOTE: CoStar provides:
        #   - SUBMARKET RENT table: CURRENT YoY rent growth per submarket (single value, not projections)
        #   - OVERALL VACANCY & RENT: 5-year projections (2025-2029) at MARKET level only
        # Submarket-level 5-year projections are NOT available in CoStar reports.

        rent_growth_projections = {}

        # Step 1: Extract property's submarket CURRENT YoY rent growth
        if property_submarket:
            submarket_rent_match = re.search(r'SUBMARKET RENT(.*?)(?:OVERALL|Page \d{2}|$)', text, re.DOTALL)
            if submarket_rent_match:
                section = submarket_rent_match.group(1)
                # Format: "9 Johnson County KS 1.3% 3 1.5% ..."
                pattern = rf'\d+\s+{re.escape(property_submarket)}\s+(-?[\d.]+)%'
                growth_match = re.search(pattern, section, re.IGNORECASE)
                if growth_match:
                    current_growth = float(growth_match.group(1))
                    rent_growth_projections['submarket_current_yoy_growth'] = current_growth
                    print(f'[INFO] Submarket ({property_submarket}) current YoY rent growth: {current_growth}%')

        # Step 2: Extract 5-year projections from OVERALL VACANCY & RENT section
        # NOTE: In submarket-only reports, OVERALL section IS the submarket data
        overall_match = re.search(r'OVERALL VACANCY & RENT(.*?)(?:4 & 5 STAR|SUBMARKET|Page \d{2}|$)', text, re.DOTALL)
        if overall_match:
            section = overall_match.group(1)
            overall_page = self._get_page_number(text, overall_match.start())
            print('[INFO] Extracting 5-year rent growth projections from OVERALL (submarket level)')

            for year in ['2025', '2026', '2027', '2028', '2029']:
                # Format: "(ppts) 2029 8.6% (0.1) 16,690 $1,458 $1.57 1.8% ..."
                # Pattern: ppts_chg year vacancy% ppts_chg absorption $rent $psf growth%
                # Note: growth% can be negative (e.g., -6.9%)
                pattern = rf'[\d.\-()]+\s+{year}\s+[\d.]+%\s+[\d.\-()]+\s+[\d,]+\s+\$[\d,]+\s+\$[\d.]+\s+(-?[\d.]+)%'
                match = re.search(pattern, section)
                if match:
                    rent_growth_projections[f'rent_growth_{year}'] = float(match.group(1))
                    page_sources[f'rent_growth_{year}'] = overall_page
                    print(f'  [OK] Submarket rent growth {year}: {match.group(1)}%')

        if not rent_growth_projections:
            print('[WARNING] No rent growth data found')

        if rent_growth_projections:
            market_data['rent_growth_projections'] = rent_growth_projections

        # Store page sources for later use
        market_data['_page_sources'] = page_sources
        self.extracted_data['market'] = market_data

    def _extract_employment_data(self, pdf_path: str):
        """Extract employment growth data from Economy section.

        Looks for the KANSAS CITY EMPLOYMENT BY INDUSTRY table and extracts
        Total Employment row with Market vs US growth comparisons.

        Table columns: Jobs, LQ, Current Growth (Market/US), 10 Yr Historical (Market/US), 5 Yr Forecast (Market/US)
        """
        text = self._extract_text_from_pdf(pdf_path, include_page_markers=True)

        employment_data = {}
        page_sources = {}

        # Look for Economy section with employment table
        # The table has "Total Employment" row with aggregate data
        # Format varies but Total Employment row contains: jobs count, LQ, then 6 percentage values
        # Example: "Total Employment 1,151 1.0-0.35% 0.59% 0.94% 1.12% 0.39% 0.44%"

        # First find the Economy section
        economy_match = re.search(r'Economy\s*\n.*?EMPLOYMENT BY INDUSTRY', text, re.DOTALL | re.IGNORECASE)
        if not economy_match:
            # Try alternate pattern
            economy_match = re.search(r'EMPLOYMENT BY INDUSTRY', text, re.IGNORECASE)

        if economy_match:
            page = self._get_page_number(text, economy_match.start())

            # Find Total Employment row - pattern handles negative percentages and various formats
            # Jobs LQ then 6 percentage values (can be negative like -0.35%)
            total_emp_pattern = r'Total Employment\s+([\d,]+)\s+([\d.]+)\s*(-?[\d.]+)%\s*(-?[\d.]+)%\s*(-?[\d.]+)%\s*(-?[\d.]+)%\s*(-?[\d.]+)%\s*(-?[\d.]+)%'

            total_match = re.search(total_emp_pattern, text)
            if total_match:
                employment_data['total_jobs_thousands'] = int(total_match.group(1).replace(',', ''))
                employment_data['location_quotient'] = float(total_match.group(2))
                employment_data['current_growth_market'] = float(total_match.group(3))
                employment_data['current_growth_us'] = float(total_match.group(4))
                employment_data['historical_10yr_market'] = float(total_match.group(5))
                employment_data['historical_10yr_us'] = float(total_match.group(6))
                employment_data['forecast_5yr_market'] = float(total_match.group(7))
                employment_data['forecast_5yr_us'] = float(total_match.group(8))

                page_sources['employment'] = page
                print(f'[OK] Employment data from Economy section (pg {page}):')
                print(f'     Current Growth: Market {employment_data["current_growth_market"]}% vs US {employment_data["current_growth_us"]}%')
                print(f'     5-Yr Forecast: Market {employment_data["forecast_5yr_market"]}% vs US {employment_data["forecast_5yr_us"]}%')
            else:
                print('[INFO] Could not parse Total Employment row')
        else:
            print('[INFO] No Economy/Employment section found')

        if employment_data:
            employment_data['_page_sources'] = page_sources
            self.extracted_data['employment'] = employment_data

    def _get_page_count(self, pdf_path: str) -> int:
        """Get total page count of PDF."""
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            return len(pdf_reader.pages)

    def get_summary(self) -> str:
        """Get a summary of extracted data."""
        summary = ["=== EXTRACTED DATA SUMMARY ===\n"]

        for category, data in self.extracted_data.items():
            summary.append(f"\n{category.upper()}:")
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, list) and len(value) > 0:
                        summary.append(f"  {key}: {len(value)} items")
                    elif isinstance(value, dict):
                        summary.append(f"  {key}: {len(value)} fields")
                    else:
                        summary.append(f"  {key}: {value}")

        return "\n".join(summary)


if __name__ == "__main__":
    # Test enhanced extraction
    reports_dir = r"C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\Properties\Fieldstone\CoStar Reports"
    extractor = CoStarPDFExtractor(reports_dir)
    data = extractor.extract_all()

    print(extractor.get_summary())
    print("\n" + "="*80)
    print("UNIT MIX DETAILS:")
    if 'property' in data and 'unit_mix' in data['property']:
        for unit in data['property']['unit_mix']:
            print(f"{unit['bedrooms']}BR/{unit['bathrooms']}BA - {unit['units']} units @ ${unit['asking_rent_per_unit']}/mo")
