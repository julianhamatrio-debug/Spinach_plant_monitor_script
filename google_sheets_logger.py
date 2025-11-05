import gspread
from datetime import datetime
import os
import logging
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("[OK] Libraries imported successfully")

# The path to your service account credentials file
CREDENTIALS_FILE = 'credentials.json' 

# The exact name of your Google Sheet
SHEET_NAME = 'Spinach Monitor'

# The worksheet name (tab) to use
WORKSHEET_NAME = 'Sheet1'

print("[OK] Configuration loaded:")
print(f"  - Credentials file: {CREDENTIALS_FILE}")
print(f"  - Sheet name: {SHEET_NAME}")
print(f"  - Worksheet: {WORKSHEET_NAME}")

class GoogleSheetsLogger:
    """
    A class to handle Google Sheets logging with connection pooling and error handling.
    """
    
    def __init__(self, credentials_file=CREDENTIALS_FILE, sheet_name=SHEET_NAME, worksheet_name=WORKSHEET_NAME):
        """
        Initialize the logger with credentials and sheet information.
        """
        self.credentials_file = credentials_file
        self.sheet_name = sheet_name
        self.worksheet_name = worksheet_name
        self.gc = None
        self.spreadsheet = None
        self.worksheet = None
        
        # Try to connect immediately
        self._connect()
    
    def _connect(self):
        """
        Establish connection to Google Sheets.
        """
        try:
            logger.info(f"Connecting to Google Sheet: {self.sheet_name}...")
            
            # Authenticate with Google Sheets
            self.gc = gspread.service_account(filename=self.credentials_file)
            
            # Open the spreadsheet
            self.spreadsheet = self.gc.open(self.sheet_name)
            
            # Get or create the worksheet
            try:
                self.worksheet = self.spreadsheet.worksheet(self.worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                logger.info(f"Worksheet '{self.worksheet_name}' not found. Creating it...")
                self.worksheet = self.spreadsheet.add_worksheet(
                    title=self.worksheet_name, 
                    rows=1000, 
                    cols=10
                )
            
            # Initialize headers if needed
            self._initialize_headers()
            
            logger.info("[OK] Successfully connected to Google Sheets")
            return True
            
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Spreadsheet '{self.sheet_name}' not found.")
            logger.error("Please create it and share it with the service account email.")
            logger.error("Service account email is in your credentials.json file.")
            return False
            
        except FileNotFoundError:
            logger.error(f"Credentials file '{self.credentials_file}' not found.")
            logger.error("Please download it from Google Cloud Console and place it in the same directory.")
            return False
            
        except Exception as e:
            logger.error(f"Error during Google Sheets authentication: {e}")
            return False
    
    def _initialize_headers(self):
        """
        Check if headers exist, if not, add them.
        """
        try:
            first_cell = self.worksheet.acell('A1').value
            
            if not first_cell:
                logger.info("Adding header row to sheet...")
                headers = [
                    "Timestamp",
                    "Date",
                    "Time", 
                    "Stem Length (mm)",
                    "Avg Leaf Width (mm)",
                    "Largest Leaf (mm)",
                    "Leaf Count",
                    "Total Leaf Area (mm^2)",
                    "Image Filename",
                    "Notes"
                ]
                self.worksheet.append_row(headers)
                
                # Format header row (bold)
                self.worksheet.format('A1:J1', {
                    "textFormat": {"bold": True},
                    "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}
                })
                
                logger.info("[OK] Headers added successfully")
                
        except Exception as e:
            logger.warning(f"Could not initialize headers: {e}")

print("[OK] GoogleSheetsLogger class initialized")

def extract_total_area(notes):
    """
    Extract total leaf area from notes string.
    Expected format: "Total area: 123.45mm^2 [Every X]"
    """
    if not notes:
        return ""
    
    # Extract number from "Total area: X.XXmm^2"
    match = re.search(r'Total area: ([\d.]+)mm', notes)
    if match:
        return round(float(match.group(1)), 2)
    return ""

def log_data_method(self, stem_mm, leaf_mm, image_filename, largest_leaf_mm=None, leaf_count=None, notes=""):
    """
    Logs the measured data to Google Sheet.
    
    Args:
        stem_mm: Stem length in millimeters
        leaf_mm: Average leaf width in millimeters
        image_filename: Path to the captured image
        largest_leaf_mm: Width of the largest leaf (optional)
        leaf_count: Number of leaves detected (optional)
        notes: Any additional notes (optional)
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info(f"Logging data to Google Sheet: {self.sheet_name}...")
    
    # Try to reconnect if connection was lost
    if not self.worksheet:
        if not self._connect():
            return False
    
    try:
        # Prepare timestamp data
        now = datetime.now()
        timestamp_iso = now.isoformat()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M:%S")
        
        # Prepare the new row with all data
        new_row = [
            timestamp_iso,
            date_str,
            time_str,
            round(stem_mm, 2) if stem_mm else "",
            round(leaf_mm, 2) if leaf_mm else "",
            round(largest_leaf_mm, 2) if largest_leaf_mm else "",
            leaf_count if leaf_count else "",
            extract_total_area(notes),  # Extract total area from notes
            os.path.basename(image_filename) if image_filename else "",
            notes
        ]
        
        # Append the data
        self.worksheet.append_row(new_row)
        
        logger.info("[OK] Successfully logged data to Google Sheet")
        logger.info(f"  Row data: Stem={stem_mm:.2f}mm, Leaf={leaf_mm:.2f}mm")
        if largest_leaf_mm:
            logger.info(f"  Largest Leaf={largest_leaf_mm:.2f}mm, Count={leaf_count}")
        
        return True
        
    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API error: {e}")
        logger.error("This might be a quota limit or permission issue.")
        return False
        
    except Exception as e:
        logger.error(f"Error appending data to sheet: {e}")
        # Try to reconnect for next time
        self.worksheet = None
        return False

# Add the method to the class
GoogleSheetsLogger.log_data = log_data_method

print("[OK] log_data() method added to GoogleSheetsLogger")


def get_all_data_method(self):
    """
    Retrieve all data from the sheet.
    
    Returns:
        list: All rows from the sheet, or None if error
    """
    try:
        if not self.worksheet:
            if not self._connect():
                return None
        
        data = self.worksheet.get_all_records()
        logger.info(f"Retrieved {len(data)} rows from Google Sheet")
        return data
        
    except Exception as e:
        logger.error(f"Error retrieving data: {e}")
        return None

def get_latest_measurement_method(self):
    """
    Get the most recent measurement from the sheet.
    
    Returns:
        dict: Latest measurement data, or None if error
    """
    try:
        data = self.get_all_data()
        if data and len(data) > 0:
            return data[-1]
        return None
    except Exception as e:
        logger.error(f"Error getting latest measurement: {e}")
        return None

# Add methods to the class
GoogleSheetsLogger.get_all_data = get_all_data_method
GoogleSheetsLogger.get_latest_measurement = get_latest_measurement_method

print("[OK] Data retrieval methods added to GoogleSheetsLogger")

def get_growth_summary_method(self):
    """
    Calculate growth statistics from all measurements.
    
    Returns:
        dict: Summary statistics
    """
    try:
        data = self.get_all_data()
        if not data or len(data) == 0:
            return None
        
        stem_lengths = [row.get('Stem Length (mm)', 0) for row in data if row.get('Stem Length (mm)')]
        leaf_widths = [row.get('Avg Leaf Width (mm)', 0) for row in data if row.get('Avg Leaf Width (mm)')]
        total_areas = [row.get('Total Leaf Area (mm^2)', 0) for row in data if row.get('Total Leaf Area (mm^2)')]
        
        summary = {
            'total_measurements': len(data),
            'first_measurement_date': data[0].get('Date', 'Unknown'),
            'latest_measurement_date': data[-1].get('Date', 'Unknown'),
            'initial_stem_length': stem_lengths[0] if stem_lengths else 0,
            'current_stem_length': stem_lengths[-1] if stem_lengths else 0,
            'stem_growth': stem_lengths[-1] - stem_lengths[0] if len(stem_lengths) > 1 else 0,
            'initial_leaf_width': leaf_widths[0] if leaf_widths else 0,
            'current_leaf_width': leaf_widths[-1] if leaf_widths else 0,
            'leaf_growth': leaf_widths[-1] - leaf_widths[0] if len(leaf_widths) > 1 else 0,
            'avg_stem_length': sum(stem_lengths) / len(stem_lengths) if stem_lengths else 0,
            'avg_leaf_width': sum(leaf_widths) / len(leaf_widths) if leaf_widths else 0,
            'initial_total_area': total_areas[0] if total_areas else 0,
            'current_total_area': total_areas[-1] if total_areas else 0,
            'total_area_growth': total_areas[-1] - total_areas[0] if len(total_areas) > 1 else 0,
            'avg_total_area': sum(total_areas) / len(total_areas) if total_areas else 0,
        }
        
        return summary
        
    except Exception as e:
        logger.error(f"Error calculating growth summary: {e}")
        return None

# Add method to the class
GoogleSheetsLogger.get_growth_summary = get_growth_summary_method

print("[OK] Growth analysis method added to GoogleSheetsLogger")

_logger_instance = None

def get_logger():
    """
    Get or create the global logger instance.
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = GoogleSheetsLogger()
    return _logger_instance

def log_data(stem_mm, leaf_mm, image_filename, largest_leaf_mm=None, leaf_count=None, notes=""):
    """
    Convenience function to log data using the global logger instance.
    This maintains compatibility with the old function signature.
    """
    logger_obj = get_logger()
    return logger_obj.log_data(stem_mm, leaf_mm, image_filename, largest_leaf_mm, leaf_count, notes)

print("[OK] Global logger instance and helper functions defined")
print("\nYou can now use:")
print("  - log_data() - Simple function for logging")
print("  - get_logger() - Get the logger instance for advanced features")

# Only run tests if this file is run directly (not imported)
if __name__ == "__main__":
    print("\n" + "="*60)
    print("TESTING GOOGLE SHEETS CONNECTION")
    print("="*60)
    
    # Try to initialize the logger
    try:
        test_logger = GoogleSheetsLogger()
        print("\n[OK] Logger initialized successfully!")
        print("\nReady to test logging...")
    except Exception as e:
        print(f"\n[ERROR] Error initializing logger: {e}")
        print("\nPlease check:")
        print("  1. credentials.json exists in this directory")
        print("  2. Google Sheet 'Spinach Monitor' is created")
        print("  3. Sheet is shared with service account email")
    
    print("\n" + "="*60)
    print("TESTING DATA LOGGING")
    print("="*60)
    
    # Log test data
    test_success = log_data(
        stem_mm=45.5,
        leaf_mm=12.3,
        image_filename="test_image.jpg",
        largest_leaf_mm=15.8,
        leaf_count=6,
        notes="Total area: 123.45mm^2 [Test]"
    )
    
    if test_success:
        print("\n[OK] Test data logged successfully!")
        print("Check your Google Sheet to see the new row.")
    else:
        print("\n[ERROR] Test logging failed. Check the errors above.")
    
    print("\n" + "="*60)
    print("RETRIEVING LATEST MEASUREMENT")
    print("="*60)
    
    sheets_logger = get_logger()
    latest = sheets_logger.get_latest_measurement()
    
    if latest:
        print("\nLatest measurement:")
        for key, value in latest.items():
            print(f"  {key}: {value}")
    else:
        print("\nNo measurements found or error occurred.")
    
    print("\n" + "="*60)
    print("SPINACH GROWTH SUMMARY")
    print("="*60)
    
    sheets_logger = get_logger()
    summary = sheets_logger.get_growth_summary()
    
    if summary:
        print(f"\nMeasurements:")
        print(f"  Total measurements: {summary['total_measurements']}")
        print(f"  First measurement: {summary['first_measurement_date']}")
        print(f"  Latest measurement: {summary['latest_measurement_date']}")
        
        print(f"\nStem Growth:")
        print(f"  Initial: {summary['initial_stem_length']:.2f}mm")
        print(f"  Current: {summary['current_stem_length']:.2f}mm")
        print(f"  Total growth: {summary['stem_growth']:.2f}mm")
        print(f"  Average: {summary['avg_stem_length']:.2f}mm")
        
        print(f"\nLeaf Growth:")
        print(f"  Initial: {summary['initial_leaf_width']:.2f}mm")
        print(f"  Current: {summary['current_leaf_width']:.2f}mm")
        print(f"  Total growth: {summary['leaf_growth']:.2f}mm")
        print(f"  Average: {summary['avg_leaf_width']:.2f}mm")
        
        print(f"\nTotal Leaf Area Growth:")
        print(f"  Initial: {summary['initial_total_area']:.2f}mm^2")
        print(f"  Current: {summary['current_total_area']:.2f}mm^2")
        print(f"  Total growth: {summary['total_area_growth']:.2f}mm^2")
        print(f"  Average: {summary['avg_total_area']:.2f}mm^2")
        
        print("\n" + "="*60)
    else:
        print("\nNo data available for summary or error occurred.")
    
    print("\n" + "="*60)
    print("ALL MEASUREMENT DATA")
    print("="*60)
    
    sheets_logger = get_logger()
    all_data = sheets_logger.get_all_data()
    
    if all_data:
        print(f"\nTotal rows: {len(all_data)}\n")
        
        # Display first 5 rows
        print("First 5 measurements:")
        for i, row in enumerate(all_data[:5], 1):
            print(f"\n  Measurement {i}:")
            print(f"    Date: {row.get('Date', 'N/A')}")
            print(f"    Stem: {row.get('Stem Length (mm)', 'N/A')}mm")
            print(f"    Leaf: {row.get('Avg Leaf Width (mm)', 'N/A')}mm")
            print(f"    Total Area: {row.get('Total Leaf Area (mm^2)', 'N/A')}mm^2")
        
        if len(all_data) > 5:
            print(f"\n  ... and {len(all_data) - 5} more measurements")
    else:
        print("\nNo data found or error occurred.")
    
    print("\n" + "="*60)