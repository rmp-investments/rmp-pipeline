"""
RMP Screener Agent v2 - Main Orchestrator with Parallel Execution
Automated property screener population using CoStar reports and web data
"""

import json
import os
import sys
import argparse
import traceback
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add modules directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'modules'))

from pdf_extractor import CoStarPDFExtractor
from web_scraper import DemographicScraper
from excel_writer import ScreenerExcelWriter
from map_generator import MapGenerator
from gis_utils import try_get_parcel_data
from logger import setup_logging, get_logger

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
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self.extracted_data = {}
        self.updates = []
        self.map_screenshots = {}
        self.flood_zone_info = None

    def _load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file and resolve relative paths."""
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Resolve relative paths in the 'paths' section
        # Base directory is the folder containing the config file (screener_agent/configs)
        config_dir = os.path.dirname(os.path.abspath(config_path))

        if 'paths' in config:
            for key, value in config['paths'].items():
                if value and isinstance(value, str) and not os.path.isabs(value):
                    # Resolve relative path from config directory
                    config['paths'][key] = os.path.normpath(os.path.join(config_dir, value))

        console.print(f"  [green]>[/green] Loaded config: [bold]{config['property_name']}[/bold]")
        return config

    def _save_config(self):
        """Save current configuration back to the JSON file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            console.print(f"  [yellow]![/yellow] Could not save config: {e}")

    def run(self):
        """Execute the full agent workflow."""
        console.print()

        # Set up logging for this property
        output_folder = self.config['paths'].get('output_path',
            os.path.dirname(self.config['paths'].get('output_file', '')))
        if not output_folder:
            output_folder = os.path.dirname(self.config['paths']['costar_reports_dir'])
        self.logger = setup_logging(output_folder, self.config['property_name'])
        self.logger.info(f"Property: {self.config['property_name']}")
        self.logger.info(f"Address: {self.config.get('property_details', {}).get('address', 'N/A')}")
        self.logger.info(f"Config path: {self.config_path}")

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

        # ALL STEPS IN PARALLEL: PDF + Web + Maps
        use_pdfs = self.config['data_sources']['use_costar_pdfs']
        use_web = self.config['data_sources']['use_web_scraping']
        use_maps = self.config.get('data_sources', {}).get('generate_maps', True)

        self.logger.step_start("Data Extraction + Maps (all parallel)")
        console.print(Panel("[bold]STEP 1-3[/bold]  Extracting data + generating maps (all parallel)", style="dark_orange", box=box.HEAVY_HEAD))

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            if use_pdfs:
                console.print(f"  [dark_orange]>[/dark_orange] Starting PDF extraction...")
                self.logger.debug("Starting PDF extraction...")
                futures['pdf'] = executor.submit(self._extract_costar_data)

            if use_web:
                console.print(f"  [dark_orange]>[/dark_orange] Starting web scraping...")
                self.logger.debug("Starting web scraping...")
                futures['web'] = executor.submit(self._scrape_web_data)

            if use_maps:
                console.print(f"  [dark_orange]>[/dark_orange] Starting map generation...")
                self.logger.debug("Starting map generation...")
                futures['maps'] = executor.submit(self._generate_maps_parallel)

            # Wait for all to complete
            for name, future in futures.items():
                try:
                    future.result()
                    console.print(f"  [green]>[/green] {name.upper()} complete")
                    self.logger.info(f"{name.upper()} complete")
                except Exception as e:
                    console.print(f"  [red]X[/red] {name.upper()} failed: {e}")
                    console.print(f"  [dim]{traceback.format_exc()}[/dim]")
                    self.logger.error(f"{name.upper()} failed: {e}\n{traceback.format_exc()}")

        self.logger.step_end("Data Extraction + Maps", success=True, details=f"PDF={use_pdfs}, Web={use_web}, Maps={use_maps}")
        console.print()

        # Step 4: Write to Excel (includes map screenshots)
        self.logger.step_start("Excel Population")
        console.print(Panel("[bold]STEP 4[/bold]  Populating Excel screener", style="dark_orange", box=box.HEAVY_HEAD))
        with console.status("[bold dark_orange]Writing to Excel...", spinner="dots"):
            self._write_to_excel()
        self.logger.step_end("Excel Population", success=True)
        console.print()

        # Summary
        self._print_summary()

        # Log completion
        log_path = self.logger.get_log_path()
        if log_path:
            self.logger.info(f"=== Screener Complete ===")
            console.print(f"  [dim]Log saved: {log_path}[/dim]")

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

        # Use parcel coords if available (manual fix takes priority), otherwise use config coords
        lat = prop_details.get('parcel_lat') or prop_details.get('latitude')
        lon = prop_details.get('parcel_lon') or prop_details.get('longitude')

        # Determine output folder for caching
        output_folder = self.config['paths'].get('output_path',
            os.path.dirname(self.config['paths'].get('output_file', '')))
        if not output_folder:
            output_folder = os.path.dirname(self.config['paths']['costar_reports_dir'])

        # Demographic scraper
        demo_scraper = DemographicScraper(
            address=prop_details['address'],
            city=prop_details['city'],
            state=prop_details['state'],
            zip_code=prop_details['zip_code'],
            lat=lat,
            lon=lon,
            cache_dir=output_folder
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
        # Load template path from settings.json
        settings_file = os.path.join(os.path.dirname(__file__), 'settings.json')
        if os.path.exists(settings_file):
            with open(settings_file, 'r') as f:
                settings = json.load(f)
            source_file = settings.get('template_excel', r'C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\RMP Screener_PreLinked_v3.xlsx')
        else:
            source_file = r'C:\Users\carso\OneDrive - UCB-O365\Work\RMP\Screener\RMP Screener_PreLinked_v3.xlsx'

        # Output to property folder with property name
        property_name = self.config['property_name']
        output_folder = self.config['paths'].get('output_path',
            os.path.dirname(self.config['paths'].get('output_file', '')))
        if not output_folder:
            output_folder = os.path.dirname(self.config['paths']['costar_reports_dir'])
        output_file = os.path.join(output_folder, f'RMP Screener_{property_name}.xlsx')

        if not os.path.exists(source_file):
            console.print(f"  [red]X[/red] Blank template not found: {source_file}")
            return

        console.print(f"  [dim]Template:[/dim] {source_file}")

        writer = ScreenerExcelWriter(source_file, output_file)
        writer.load_workbook()

        console.print(f"  [dark_orange]>[/dark_orange] Creating Data Inputs sheet...")
        writer.create_data_inputs_sheet(self.extracted_data, self.config)

        console.print(f"  [dark_orange]>[/dark_orange] Adding reference formulas...")
        # writer.add_reference_formulas()  # DISABLED - Pre-linked template already has formulas

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

            # Insert income map into Stage 1
            if 'income' in self.map_screenshots:
                console.print(f"  [dark_orange]>[/dark_orange] Inserting income map into Stage 1...")
                writer.insert_stage1_income_map(
                    income_png=self.map_screenshots['income'],
                    income_html=self.map_screenshots.get('income_html', '')
                )

            # Insert flood map into Stage 1
            if 'flood' in self.map_screenshots:
                console.print(f"  [dark_orange]>[/dark_orange] Inserting flood map into Stage 1...")
                writer.insert_stage1_flood_map(self.map_screenshots['flood'])

        writer.save()
        writer.close()

        console.print(f"  [green]>[/green] Excel file saved")
        self.output_file = output_file

    def _geocode_address(self) -> tuple:
        """Geocode property address to get lat/lon coordinates."""
        import requests

        prop = self.config['property_details']
        address = f"{prop['address']}, {prop['city']}, {prop['state']} {prop['zip_code']}"

        # PRIORITY 1: Use manually corrected parcel coordinates (from manual fix mode)
        if prop.get('parcel_lat') and prop.get('parcel_lon'):
            return prop['parcel_lat'], prop['parcel_lon']

        # PRIORITY 2: Check if coordinates are in config
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
        output_folder = self.config['paths'].get('output_path',
            os.path.dirname(self.config['paths'].get('output_file', '')))
        if not output_folder:
            output_folder = os.path.dirname(self.config['paths']['costar_reports_dir'])
        maps_dir = os.path.join(output_folder, 'Maps')

        # Use parcel coords for all maps if available (manual fix takes priority)
        prop_details = self.config.get('property_details', {})
        map_lat = prop_details.get('parcel_lat') or lat
        map_lon = prop_details.get('parcel_lon') or lon
        if map_lat != lat or map_lon != lon:
            console.print(f"  [dim]Using manually fixed coords: {map_lat:.4f}, {map_lon:.4f}[/dim]")

        # Create map generator with best available coords
        generator = MapGenerator(map_lat, map_lon, self.config['property_name'], maps_dir)

        # Generate maps
        self.generated_maps = []

        # 1. Income map (subject county + adjacent counties)
        console.print(f"  [dark_orange]>[/dark_orange] Creating income map (subject + adjacent counties)...")
        income_map = generator.create_income_map(zoom=11)
        if income_map:
            self.generated_maps.append(income_map)
            console.print(f"  [green]>[/green] Income map saved")

        # 2. Metro location map
        console.print(f"  [dark_orange]>[/dark_orange] Creating metro location map...")
        location_map = generator.create_metro_location(zoom=10)
        if location_map:
            self.generated_maps.append(location_map)
            console.print(f"  [green]>[/green] Location map saved")

        # 3. Parcel satellite view (use saved coordinates/polygon if available, or auto-detect)
        console.print(f"  [dark_orange]>[/dark_orange] Creating satellite view...")
        prop_details = self.config.get('property_details', {})
        parcel_lat = prop_details.get('parcel_lat')
        parcel_lon = prop_details.get('parcel_lon')
        parcel_zoom = prop_details.get('parcel_zoom', 18)
        parcel_polygon = prop_details.get('parcel_polygon')

        # Only auto-detect if we don't have saved coordinates (respect manual fixes!)
        if not parcel_lat or not parcel_lon:
            console.print(f"  [dim]Detecting parcel from county GIS...[/dim]")
            # Pass street address to help match the correct parcel
            street_address = prop_details.get('address', '')
            parcel_data = try_get_parcel_data(lat, lon, property_address=street_address)
            if parcel_data:
                parcel_lat, parcel_lon = parcel_data['centroid']
                parcel_polygon = parcel_data['polygon']
                console.print(f"  [green]>[/green] Parcel found: {parcel_lat:.6f}, {parcel_lon:.6f} ({len(parcel_polygon)} vertices)")
                # Save to config for future runs
                self.config['property_details']['parcel_lat'] = parcel_lat
                self.config['property_details']['parcel_lon'] = parcel_lon
                self.config['property_details']['parcel_zoom'] = 18
                self.config['property_details']['parcel_polygon'] = parcel_polygon
                self._save_config()
            else:
                console.print(f"  [dim]Could not detect parcel - using geocoded point[/dim]")

        if parcel_lat and parcel_lon:
            console.print(f"  [dim]Using parcel coordinates[/dim]")
            parcel_generator = MapGenerator(parcel_lat, parcel_lon, self.config['property_name'], maps_dir)
            # Let zoom auto-calculate from polygon if available, otherwise use saved zoom
            zoom_to_use = None if parcel_polygon else parcel_zoom
            parcel_map = parcel_generator.create_parcel_satellite(zoom=zoom_to_use, parcel_polygon=parcel_polygon)
        else:
            parcel_map = generator.create_parcel_satellite(zoom=18)

        if parcel_map:
            self.generated_maps.append(parcel_map)
            console.print(f"  [green]>[/green] Satellite view saved")

        # 4. Flood zone map (zoom 16 for property-level detail)
        console.print(f"  [dark_orange]>[/dark_orange] Creating flood zone map...")
        flood_map = generator.create_flood_zone_map(zoom=16)
        if flood_map:
            self.generated_maps.append(flood_map)
            console.print(f"  [green]>[/green] Flood zone map saved")

        console.print(f"  [green]>[/green] Generated {len(self.generated_maps)} maps in {maps_dir}")

        # 5. Capture screenshots for Excel embedding
        console.print(f"  [dark_orange]>[/dark_orange] Capturing map screenshots...")
        self.map_screenshots = generator.capture_all_screenshots()
        if self.map_screenshots:
            console.print(f"  [green]>[/green] Captured {len(self.map_screenshots)} screenshots")

        # Store flood zone info for Excel
        self.flood_zone_info = generator.get_flood_zone_info()
        if self.flood_zone_info:
            console.print(f"  [green]>[/green] Flood zone: {self.flood_zone_info.get('zone', 'Unknown')} - {self.flood_zone_info.get('flood_risk', '')}")

    def _generate_maps_parallel(self):
        """Generate property maps in parallel for faster execution."""
        prop_details = self.config['property_details']

        # Get coordinates
        lat, lon = self._geocode_address()
        if not lat or not lon:
            console.print(f"  [red]X[/red] Could not geocode address - skipping maps")
            return

        console.print(f"  [green]>[/green] Geocoded: {lat:.4f}, {lon:.4f}")

        # Set up output directory
        output_folder = self.config['paths'].get('output_path',
            os.path.dirname(self.config['paths'].get('output_file', '')))
        if not output_folder:
            output_folder = os.path.dirname(self.config['paths']['costar_reports_dir'])
        maps_dir = os.path.join(output_folder, 'Maps')

        # Use parcel coords for all maps if available (manual fix takes priority)
        prop_details = self.config.get('property_details', {})
        map_lat = prop_details.get('parcel_lat') or lat
        map_lon = prop_details.get('parcel_lon') or lon
        if map_lat != lat or map_lon != lon:
            console.print(f"  [dim]Using manually fixed coords: {map_lat:.4f}, {map_lon:.4f}[/dim]")

        # Create map generator with best available coords
        generator = MapGenerator(map_lat, map_lon, self.config['property_name'], maps_dir)

        # Generate all 4 maps in PARALLEL
        self.generated_maps = []
        console.print(f"  [dark_orange]>[/dark_orange] Generating 4 maps in parallel...")

        # Check for saved parcel coordinates/polygon, or try to auto-detect from county GIS
        prop_details = self.config.get('property_details', {})
        parcel_lat = prop_details.get('parcel_lat')
        parcel_lon = prop_details.get('parcel_lon')
        parcel_zoom = prop_details.get('parcel_zoom', 18)
        parcel_polygon = prop_details.get('parcel_polygon')

        # Only auto-detect if we don't have saved coordinates (respect manual fixes!)
        if not parcel_lat or not parcel_lon:
            console.print(f"  [dim]Detecting parcel from county GIS...[/dim]")
            # Pass street address to help match the correct parcel
            street_address = prop_details.get('address', '')
            parcel_data = try_get_parcel_data(lat, lon, property_address=street_address)
            if parcel_data:
                parcel_lat, parcel_lon = parcel_data['centroid']
                parcel_polygon = parcel_data['polygon']
                console.print(f"  [green]>[/green] Parcel found: {parcel_lat:.6f}, {parcel_lon:.6f} ({len(parcel_polygon)} vertices)")
                # Save to config for future runs
                self.config['property_details']['parcel_lat'] = parcel_lat
                self.config['property_details']['parcel_lon'] = parcel_lon
                self.config['property_details']['parcel_zoom'] = 18
                self.config['property_details']['parcel_polygon'] = parcel_polygon
                self._save_config()
            else:
                console.print(f"  [dim]Could not detect parcel - using geocoded point[/dim]")

        def create_income():
            return ('income', generator.create_income_map(zoom=11))

        def create_location():
            return ('location', generator.create_metro_location(zoom=10))

        def create_parcel():
            if parcel_lat and parcel_lon:
                parcel_gen = MapGenerator(parcel_lat, parcel_lon, self.config['property_name'], maps_dir)
                # Let zoom auto-calculate from polygon if available
                zoom_to_use = None if parcel_polygon else parcel_zoom
                return ('parcel', parcel_gen.create_parcel_satellite(zoom=zoom_to_use, parcel_polygon=parcel_polygon))
            return ('parcel', generator.create_parcel_satellite(zoom=18))

        def create_flood():
            return ('flood', generator.create_flood_zone_map(zoom=16))

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(create_income),
                executor.submit(create_location),
                executor.submit(create_parcel),
                executor.submit(create_flood)
            ]

            for future in as_completed(futures):
                try:
                    map_type, map_path = future.result()
                    if map_path:
                        self.generated_maps.append(map_path)
                        console.print(f"  [green]>[/green] {map_type.capitalize()} map saved")
                except Exception as e:
                    console.print(f"  [red]X[/red] Map generation failed: {e}")

        console.print(f"  [green]>[/green] Generated {len(self.generated_maps)} maps in {maps_dir}")

        # Capture screenshots (can also be parallel but selenium has issues with multiple instances)
        console.print(f"  [dark_orange]>[/dark_orange] Capturing map screenshots...")
        self.map_screenshots = generator.capture_all_screenshots()
        if self.map_screenshots:
            console.print(f"  [green]>[/green] Captured {len(self.map_screenshots)} screenshots")

        # Store flood zone info for Excel
        self.flood_zone_info = generator.get_flood_zone_info()
        if self.flood_zone_info:
            console.print(f"  [green]>[/green] Flood zone: {self.flood_zone_info.get('zone', 'Unknown')} - {self.flood_zone_info.get('flood_risk', '')}")

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
