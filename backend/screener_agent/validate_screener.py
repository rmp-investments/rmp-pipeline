"""
Screener Data Validator Runner
Validates extracted data against original sources using Claude API.

Usage:
    python validate_screener.py

Then follow the prompts to select a file and run validation.
"""

import os
import sys
from pathlib import Path

# Add modules to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'modules'))

from data_validator import DataValidator, load_api_key_from_config, save_api_key_to_config


def find_screener_outputs(base_path: str = None) -> list:
    """Find all screener output Excel files."""
    if base_path is None:
        # Default to Properties folder
        base_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'Properties'
        )

    outputs = []

    if not os.path.exists(base_path):
        print(f"Properties folder not found: {base_path}")
        return outputs

    # Search for Excel files matching screener output pattern
    for root, dirs, files in os.walk(base_path):
        for f in files:
            if f.startswith('RMP Screener_') and f.endswith('.xlsx'):
                full_path = os.path.join(root, f)
                outputs.append({
                    'path': full_path,
                    'name': f,
                    'property': Path(root).name
                })

    return outputs


def select_file(outputs: list) -> str:
    """Let user select which file to validate."""
    if not outputs:
        print("No screener output files found!")
        return None

    print("\n" + "=" * 60)
    print("SCREENER DATA VALIDATOR")
    print("=" * 60)
    print("\nAvailable screener outputs:\n")

    for i, output in enumerate(outputs, 1):
        print(f"  [{i}] {output['property']}")
        print(f"      {output['name']}")
        print()

    print(f"  [0] Enter custom path")
    print()

    while True:
        try:
            choice = input("Select file number (or 0 for custom path): ").strip()

            if choice == '0':
                custom_path = input("Enter full path to Excel file: ").strip()
                custom_path = custom_path.strip('"')  # Remove quotes if present
                if os.path.exists(custom_path):
                    return custom_path
                else:
                    print(f"File not found: {custom_path}")
                    continue

            idx = int(choice) - 1
            if 0 <= idx < len(outputs):
                return outputs[idx]['path']
            else:
                print("Invalid selection. Try again.")
        except ValueError:
            print("Please enter a number.")


def get_api_key() -> str:
    """Get Claude API key from config, environment, or user input."""
    # Check config file first
    config_key = load_api_key_from_config()
    if config_key:
        masked = config_key[:8] + '...' + config_key[-4:]
        use_config = input(f"\nFound API key in config: {masked}\nUse this key? [Y/n]: ").strip().lower()
        if use_config != 'n':
            return config_key

    # Check environment
    env_key = os.environ.get('ANTHROPIC_API_KEY')
    if env_key:
        masked = env_key[:8] + '...' + env_key[-4:]
        use_env = input(f"\nFound API key in environment: {masked}\nUse this key? [Y/n]: ").strip().lower()
        if use_env != 'n':
            return env_key

    # Ask user for key
    print("\nEnter your Claude API key (starts with 'sk-ant-'):")
    key = input("> ").strip()

    if key:
        # Offer to save to config
        save_choice = input("Save this key to config file for future use? [Y/n]: ").strip().lower()
        if save_choice != 'n':
            save_api_key_to_config(key)

    return key


def main():
    """Main entry point."""
    print("\n" + "=" * 60)
    print("  RMP SCREENER DATA VALIDATOR")
    print("  Validates extracted data against original sources")
    print("=" * 60)

    # Find available outputs
    properties_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'Properties'
    )
    outputs = find_screener_outputs(properties_path)

    # Select file
    excel_path = select_file(outputs)
    if not excel_path:
        print("No file selected. Exiting.")
        return

    print(f"\nSelected: {excel_path}")

    # Get API key
    api_key = get_api_key()
    if not api_key:
        print("No API key provided. Exiting.")
        return

    # Confirm
    print("\n" + "-" * 60)
    print("Ready to validate:")
    print(f"  File: {os.path.basename(excel_path)}")
    print(f"  Validates: CoStar PDF sources only")
    print(f"  (Web/scraped sources skipped - can't reliably re-verify)")
    print("-" * 60)

    confirm = input("\nProceed with validation? [Y/n]: ").strip().lower()
    if confirm == 'n':
        print("Cancelled.")
        return

    # Run validation
    print("\n")
    try:
        validator = DataValidator(excel_path)
        validator.init_claude_client(api_key)
        validator.load_excel()
        validator.run_validation()

        # Ask about saving
        print("\n" + "-" * 60)
        summary = validator.get_summary()
        print(f"Results: OK={summary.get('OK', 0)}, FAIL={summary.get('FAIL', 0)}, ?={summary.get('?', 0)}, SKIP={summary.get('SKIP', 0)}")

        save_choice = input("\nSave results to Excel? [Y/n]: ").strip().lower()
        if save_choice != 'n':
            # Option to save to new file
            save_new = input("Save to new file? [y/N]: ").strip().lower()
            if save_new == 'y':
                new_path = excel_path.replace('.xlsx', '_validated.xlsx')
                validator.save(new_path)
            else:
                validator.save()

        print("\n✓ Validation complete!")

        # Show any failures
        failures = [r for r in validator.validation_results if r['result'] == 'FAIL']
        if failures:
            print("\n⚠ FAILURES DETECTED:")
            for f in failures:
                print(f"  - {f['field']}: {f['explanation']}")

    except Exception as e:
        print(f"\n✗ Error during validation: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
