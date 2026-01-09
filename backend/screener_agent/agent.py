"""
RMP Screener Agent - Main Orchestrator
Automated property screener population using CoStar reports and web data
"""

import json
import os
import sys
import argparse
from datetime import datetime

# Add modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from pdf_extractor import CoStarPDFExtractor
from web_scraper import DemographicScraper
from excel_writer import ScreenerExcelWriter
from map_generator import MapGenerator

# Rich console for beautiful output
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()


class ScreenerAgent:
    """Main agent for automating screener population."""

    def __init__(self, config_path: str):
        """
        Initialize agent with configuration file.

        Args:
            config_path: Path to property configuration JSON file
        """
        self.config = self._load_config(config_path)
        self.extracted_data = {}
        self.updates = []
        self.map_screenshots = {}

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file and resolve relative paths."""
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Resolve relative paths in the 'paths' section
        config_dir = os.path.dirname(os.path.abspath(config_path))

        if 'paths' in config:
            for key, value in config['paths'].items():
                if value and isinstance(value, str) and not os.path.isabs(value):
                    config['paths'][key] = os.path.normpath(os.path.join(config_dir, value))

        console.print(f"  [green]>[/green] Loaded config: [bold]{config['property_name']}[/bold]")
        return config

    def _get_output_folder(self) -> str:
        """Get the output folder for this property."""
        output_folder = self.config['paths'].get('output_path',
            os.path.dirname(self.config['paths'].get('output_file', '')))
        if not output_folder:
            output_folder = os.path.dirname(self.config['paths']['costar_reports_dir'])
        return output_folder

    def _get_output_file_path(self) -> str:
        """Get the actual output Excel file path."""
        property_name = self.config['property_name']
        return os.path.join(self._get_output_folder(), f'RMP Screener_{property_name}.xlsx')

    def run(self):
        """Execute the full agent workflow."""

        # Pre-flight check: Ensure Excel file is not open
        output_file = self._get_output_file_path()
        if not self._check_file_not_open(output_file):
            return  # Exit early if file is open

        console.print()

        # Property info panel
        property_info = Table.grid(padding=1)
        property_info.add_column(style="dark_orange", justify="right")
        property_info.add_column(style="white")
        property_info.add_row("Property:", f"[bold dark_orange]{self.config['property_name']}[/bold dark_orange]")
        property_info.add_row("Address:", self.config.get('property_details', {}).get('address', 'N/A'))
        property_info.add_row("City:", f"{self.config.get('property_details', {}).get('city', 'N/A')}, {self.config.get('property_details', {}).get('state', '')}")
        property_info.add_row("Started:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        console.print(Panel(property_info, title="[bold white]Processing[/bold white]", border_style="dark_orange", box=box.ROUNDED))
        console.print()

        # Execute workflow steps
        # Step 1: Extract data from CoStar PDFs
        if self.config['data_sources']['use_costar_pdfs']:
            console.print(f"  [dark_orange]>[/dark_orange] Extracting CoStar PDFs...")
            self._extract_costar_data()

        # Step 2: Scrape web data if needed
        if self.config['data_sources']['use_web_scraping']:
            console.print(f"  [dark_orange]>[/dark_orange] Scraping web data...")
            self._scrape_web_data()

        # Step 3: Generate Maps
        if self.config.get('data_sources', {}).get('generate_maps', True):
            console.print(f"  [dark_orange]>[/dark_orange] Generating maps...")
            self._generate_maps()

        # Step 4: Write to Excel
        console.print(f"  [dark_orange]>[/dark_orange] Writing to Excel...")
        self._write_to_excel()

        console.print()

        # Summary
        self._print_summary()

    def _check_file_not_open(self, file_path: str) -> bool:
        """
        Check if a file is currently open (e.g., in Excel).
        Returns True if file is available, False if it's locked.
        """
        if not os.path.exists(file_path):
            return True  # File doesn't exist yet, so it's not open

        try:
            # Try to open file in exclusive write mode
            with open(file_path, 'a') as f:
                pass
            return True
        except PermissionError:
            console.print()
            console.print(Panel(
                f"[bold red]Excel file is currently open![/bold red]\n\n"
                f"[white]Please close the file and re-run the agent:[/white]\n"
                f"[dim]{os.path.basename(file_path)}[/dim]",
                title="[bold red]Cannot Write to File[/bold red]",
                border_style="red",
                box=box.HEAVY
            ))
            console.print()
            return False
        except Exception as e:
            console.print(f"  [yellow]![/yellow] Warning: Could not verify file access: {e}")
            return True  # Proceed anyway, will fail later if there's a real issue

    def _extract_costar_data(self):
        """Extract data from CoStar PDF reports."""
        reports_dir = self.config['paths']['costar_reports_dir']

        if not os.path.exists(reports_dir):
            console.print(f"  [red]X[/red] CoStar reports directory not found: {reports_dir}")
            return

        extractor = CoStarPDFExtractor(reports_dir)
        costar_data = extractor.extract_all()

        # Merge with extracted data
        self.extracted_data.update(costar_data)

        summary = extractor.get_summary()
        if summary:
            console.print(f"  [green]>[/green] {summary}")

    def _scrape_web_data(self):
        """Scrape additional data from web sources."""
        prop_details = self.config['property_details']

        # Demographic scraper
        demo_scraper = DemographicScraper(
            address=prop_details['address'],
            city=prop_details['city'],
            state=prop_details['state'],
            zip_code=prop_details['zip_code'],
            cache_dir=self._get_output_folder()
        )

        web_demo_data = demo_scraper.scrape_all()

        # Add to extracted data
        if 'web_demographics' not in self.extracted_data:
            self.extracted_data['web_demographics'] = {}
        self.extracted_data['web_demographics'].update(web_demo_data)

        demo_summary = demo_scraper.get_summary()
        if demo_summary:
            console.print(f"  [green]>[/green] {demo_summary}")

    def _write_to_excel(self):
        """Write extracted data to Excel screener via Data Inputs sheet."""
        # ALWAYS start from blank template - never use existing property file
        # v3 uses XLOOKUP formulas instead of direct cell references
        source_file = r'C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\RMP Screener_PreLinked_v3.xlsx'

        # Output to property folder with property name
        output_file = self._get_output_file_path()

        if not os.path.exists(source_file):
            console.print(f"  [red]X[/red] Blank template not found: {source_file}")
            return

        console.print(f"  [dim]Template:[/dim] {source_file}")

        writer = ScreenerExcelWriter(source_file, output_file)
        writer.load_workbook()

        console.print(f"  [dark_orange]>[/dark_orange] Creating Data Inputs sheet...")
        writer.create_data_inputs_sheet(self.extracted_data, self.config)

        console.print(f"  [dark_orange]>[/dark_orange] Writing rent comparables...")
        writer.write_rent_comps(self.extracted_data, self.config)

        console.print(f"  [dark_orange]>[/dark_orange] Writing sale comparables...")
        writer.write_sale_comps(self.extracted_data, self.config)

        # Insert map screenshots into Screener Cover (location + parcel with hyperlinks)
        if hasattr(self, 'map_screenshots') and self.map_screenshots:
            if 'location' in self.map_screenshots and 'parcel' in self.map_screenshots:
                console.print(f"  [dark_orange]>[/dark_orange] Inserting maps into Screener Cover...")
                writer.insert_cover_maps(
                    location_png=self.map_screenshots['location'],
                    parcel_png=self.map_screenshots['parcel'],
                    location_html=self.map_screenshots.get('location_html', ''),
                    parcel_html=self.map_screenshots.get('parcel_html', '')
                )

        writer.save()
        writer.close()

        console.print(f"  [green]>[/green] Excel file saved")
        self.output_file = output_file

    def _geocode_address(self) -> tuple:
        """Geocode property address to get lat/lon coordinates."""
        import requests

        prop = self.config['property_details']
        address = f"{prop['address']}, {prop['city']}, {prop['state']} {prop['zip_code']}"

        # Check if coordinates are in config
        if 'latitude' in prop and 'longitude' in prop:
            return prop['latitude'], prop['longitude']

        # Use Census geocoder (free, no API key)
        try:
            url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
            params = {
                'address': address,
                'benchmark': 'Public_AR_Current',
                'format': 'json'
            }
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()

            matches = data.get('result', {}).get('addressMatches', [])
            if matches:
                coords = matches[0]['coordinates']
                return coords['y'], coords['x']  # lat, lon
        except Exception as e:
            console.print(f"  [yellow]![/yellow] Geocoding failed: {e}")

        return None, None

    def _generate_maps(self):
        """Generate property maps including income heatmap."""
        prop_details = self.config['property_details']

        # Get coordinates
        lat, lon = self._geocode_address()
        if not lat or not lon:
            console.print(f"  [red]X[/red] Could not geocode address - skipping maps")
            return

        console.print(f"  [green]>[/green] Geocoded: {lat:.4f}, {lon:.4f}")

        # Set up output directory
        maps_dir = os.path.join(self._get_output_folder(), 'Maps')

        # Create map generator
        generator = MapGenerator(lat, lon, self.config['property_name'], maps_dir)

        # Generate maps
        self.generated_maps = []

        # 1. Income map (subject county + adjacent counties)
        console.print(f"  [dark_orange]>[/dark_orange] Creating income map (subject + adjacent counties)...")
        income_map = generator.create_income_map(zoom=9)
        if income_map:
            self.generated_maps.append(income_map)
            console.print(f"  [green]>[/green] Income map saved")

        # 2. Metro location map
        console.print(f"  [dark_orange]>[/dark_orange] Creating metro location map...")
        location_map = generator.create_metro_location(zoom=10)
        if location_map:
            self.generated_maps.append(location_map)
            console.print(f"  [green]>[/green] Location map saved")

        # 3. Parcel satellite view
        console.print(f"  [dark_orange]>[/dark_orange] Creating satellite view...")
        parcel_map = generator.create_parcel_satellite(zoom=18)
        if parcel_map:
            self.generated_maps.append(parcel_map)
            console.print(f"  [green]>[/green] Satellite view saved")

        console.print(f"  [green]>[/green] Generated {len(self.generated_maps)} maps in {maps_dir}")

        # 4. Capture screenshots for Excel embedding
        console.print(f"  [dark_orange]>[/dark_orange] Capturing map screenshots...")
        self.map_screenshots = generator.capture_all_screenshots()
        if self.map_screenshots:
            console.print(f"  [green]>[/green] Captured {len(self.map_screenshots)} screenshots")

    def _print_summary(self):
        """Print execution summary."""
        console.print()

        # Summary table
        summary_table = Table(box=box.ROUNDED, show_header=False, border_style="rgb(205,102,0)", padding=(0, 2))
        summary_table.add_column("Label", style="dark_orange")
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Property", f"[bold]{self.config['property_name']}[/bold]")
        summary_table.add_row("CoStar PDFs", "[green]Enabled[/green]" if self.config['data_sources']['use_costar_pdfs'] else "[dim]Disabled[/dim]")
        summary_table.add_row("Web Scraping", "[green]Enabled[/green]" if self.config['data_sources']['use_web_scraping'] else "[dim]Disabled[/dim]")

        total_fields = 0
        for category in self.extracted_data.keys():
            if isinstance(self.extracted_data[category], dict):
                count = len(self.extracted_data[category])
                total_fields += count
                summary_table.add_row(f"  {category}", f"{count} fields")

        summary_table.add_row("Total Fields", f"[bold green]{total_fields}[/bold green]")

        output_file = getattr(self, 'output_file', self.config['paths'].get('output_file', 'N/A'))
        summary_table.add_row("Output", f"[dim]{output_file}[/dim]")

        # Success banner
        success_text = Text()
        success_text.append("\n  AGENT COMPLETE  \n", style="bold white on green")

        console.print(Panel(success_text, box=box.DOUBLE, border_style="green"))
        console.print()
        console.print(summary_table)
        console.print()
        console.print("[dim]Check the 'Data Inputs' sheet for extracted values.[/dim]")
        console.print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='RMP Screener Agent - Automate property screener population'
    )
    parser.add_argument(
        '--property',
        type=str,
        required=True,
        help='Property name (e.g., "fieldstone")'
    )
    parser.add_argument(
        '--config-dir',
        type=str,
        default='configs',
        help='Directory containing config files (default: configs)'
    )

    args = parser.parse_args()

    # Build config path
    config_path = os.path.join(
        os.path.dirname(__file__),
        args.config_dir,
        f"{args.property}.json"
    )

    if not os.path.exists(config_path):
        print(f"Error: Configuration file not found: {config_path}")
        print(f"\nAvailable configs:")
        config_dir_full = os.path.join(os.path.dirname(__file__), args.config_dir)
        if os.path.exists(config_dir_full):
            for f in os.listdir(config_dir_full):
                if f.endswith('.json') and f != 'template.json':
                    print(f"  - {f.replace('.json', '')}")
        sys.exit(1)

    # Run agent
    agent = ScreenerAgent(config_path)
    agent.run()


if __name__ == "__main__":
    main()
