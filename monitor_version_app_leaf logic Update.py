import cv2
import numpy as np
import tkinter as tk
from tkinter import font
from PIL import Image, ImageTk
import gspread
from datetime import datetime
import os
import threading
import time

# --- 1. CONFIGURATION (Same as before) ---
# ... (Configuration for REFERENCE_OBJECT, PLANT, etc. remains unchanged) ...
# --- 1. CONFIGURATION (Same as before) ---

# --- REFERENCE OBJECT (BLUE) ---
REFERENCE_LOWER = np.array([90, 70, 50])
REFERENCE_UPPER = np.array([130, 255, 255])
REFERENCE_WIDTH_MM = 10.0

# --- PLANT (REDDISH-BROWN LEAVES) ---
# UPDATED: These values are tuned for the specific color in your provided leaf image.
# It targets the reddish-brown/olive hues.
PLANT_LOWER_1 = np.array([0, 30, 30])    # Adjusted Hue, Saturation, Value
PLANT_UPPER_1 = np.array([40, 255, 200]) # Adjusted Hue, Saturation, Value

# We can remove the second range if the first range is broad enough for the actual leaves.
# If some parts of your leaves are very dark red/purple, you might need a second range (160-180 hue).
# For now, let's simplify to one main range.
PLANT_LOWER_2 = np.array([0, 0, 0])      # Setting to 0,0,0 essentially disables this range
PLANT_UPPER_2 = np.array([0, 0, 0])      # Setting to 0,0,0 essentially disables this range


# --- OTHER SETTINGS ---
# UPDATED: Increased to filter out more noise
MIN_LEAF_AREA_PIXELS = 100 
IMAGE_DIR = "captures" # Folder to save images when logging

# --- 2. GOOGLE SHEETS LOGGER (Merged from google_sheets_logger.py) ---
CREDENTIALS_FILE = 'credentials.json' 
SHEET_NAME = 'Spinach Monitor' # Make sure this matches your sheet name!

def log_data(stem_mm, leaf_count, area_mm2, image_filename):
    """
    Logs the measured data to a Google Sheet in a separate thread.
    """
    print(f"Logging data: {stem_mm}mm, {leaf_count} leaves, {area_mm2}mm^2, {image_filename}")
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        sh = gc.open(SHEET_NAME).sheet1
        
        timestamp = datetime.now().isoformat()
        new_row = [timestamp, round(stem_mm, 2), leaf_count, round(area_mm2, 2), image_filename]
        
        if sh.get('A1').first() is None:
            print("Adding header row to new sheet.")
            sh.append_row(["Timestamp", "Stem Height (mm)", "Leaf Count", "Total Leaf Area (mm²)", "Image Filename"])

        sh.append_row(new_row)
        print("Successfully logged data to Google Sheet.")
        return True
        
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"Error: Spreadsheet '{SHEET_NAME}' not found.")
        print("Please create it and share it with the service account email.")
        return False
    except FileNotFoundError:
        print(f"Error: Credentials file '{CREDENTIALS_FILE}' not found.")
        return False
    except Exception as e:
        print(f"An error occurred during Google Sheets logging: {e}")
        return False

# --- 3. COMPUTER VISION FUNCTIONS (Merged from live_plant_analysis.py) ---

def find_pixels_per_mm(frame):
    """
    Finds the blue reference object and calculates the px/mm ratio.
    Returns: The frame with the ref box drawn, and the px/mm ratio (or 0 if not found)
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, REFERENCE_LOWER, REFERENCE_UPPER)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not contours:
        return frame, 0 # Return 0 if no ref object found
    
    ref_contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(ref_contour)
    width_in_pixels = w
    
    cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2) # Blue box
    cv2.putText(frame, "Ref Object", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
    
    if width_in_pixels == 0:
        return frame, 0

    pixels_per_mm = width_in_pixels / REFERENCE_WIDTH_MM
    return frame, pixels_per_mm

def find_plant_contours(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    
    # Use the new, more specific plant color range
    mask1 = cv2.inRange(hsv, PLANT_LOWER_1, PLANT_UPPER_1)
    
    # Only use mask2 if its bounds are not 0 (i.e., if it's explicitly defined)
    if not np.all(PLANT_LOWER_2 == 0) and not np.all(PLANT_UPPER_2 == 0):
        mask2 = cv2.inRange(hsv, PLANT_LOWER_2, PLANT_UPPER_2)
        mask = cv2.bitwise_or(mask1, mask2)
    else:
        mask = mask1 # Only use the first mask

    # More aggressive erosion to remove thin stems/noise
    mask = cv2.erode(mask, None, iterations=3)
    mask = cv2.dilate(mask, None, iterations=3)
    
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Filter out tiny noise contours
    valid_contours = [c for c in contours if cv2.contourArea(c) > MIN_LEAF_AREA_PIXELS]
    return valid_contours

# --- 4. TKINTER APPLICATION CLASS ---

class PlantMonitorApp:
    def __init__(self, window_title="Red Spinach Monitor"):
        self.window = tk.Tk()
        self.window.title(window_title)
        self.window.config(bg="gray10")

        os.makedirs(IMAGE_DIR, exist_ok=True)

        # --- Webcam and CV Variables ---
        self.cap = cv2.VideoCapture(0)
        self.current_frame_raw = None 
        self.current_metrics = {"height": 0, "count": 0, "area": 0}

        # --- NEW: Calibration Variables ---
        self.pixels_per_mm = 0
        self.calibrated = False

        # --- NEW: UI Smoothing Variables ---
        self.measurement_history = [] 
        self.smoothing_window = 30  # Average over 30 frames (approx 1 sec)

        # --- Scheduler Variables ---
        self.scheduler_stop_event = threading.Event()
        self.scheduler_thread = None

        # --- UI Elements ---
        helv = font.Font(family="Helvetica", size=12, weight="bold")
        
        self.title_label = tk.Label(self.window, text="RED SPINACH MONITOR", font=("Helvetica", 16, "bold"), fg="white", bg="gray10")
        self.title_label.pack(pady=10)

        self.video_label = tk.Label(self.window)
        self.video_label.pack(padx=10, pady=5)

        self.data_frame = tk.Frame(self.window, bg="gray10")
        self.data_frame.pack(fill="x", padx=10, pady=5)
        
        self.lbl_height = tk.Label(self.data_frame, text="Height: -- mm", font=helv, fg="cyan", bg="gray10")
        self.lbl_height.pack(side="left", expand=True)
        
        self.lbl_count = tk.Label(self.data_frame, text="Leaf Count: --", font=helv, fg="cyan", bg="gray10")
        self.lbl_count.pack(side="left", expand=True)
        
        self.lbl_area = tk.Label(self.data_frame, text="Total Area: -- mm²", font=helv, fg="cyan", bg="gray10")
        self.lbl_area.pack(side="left", expand=True)

        self.button_frame = tk.Frame(self.window, bg="gray10")
        self.button_frame.pack(fill="x", padx=10, pady=10)

        self.btn_log = tk.Button(self.button_frame, text="LOG DATA", font=helv, bg="green", fg="white", command=self.log_data_thread)
        self.btn_log.pack(side="left", expand=True, padx=5, ipady=5)
        
        # --- NEW: Recalibrate Button ---
        self.btn_recal = tk.Button(self.button_frame, text="RECALIBRATE", font=helv, bg="blue", fg="white", command=self.recalibrate)
        self.btn_recal.pack(side="left", expand=True, padx=5, ipady=5)

        self.btn_quit = tk.Button(self.button_frame, text="QUIT", font=helv, bg="red", fg="white", command=self.on_closing)
        self.btn_quit.pack(side="right", expand=True, padx=5, ipady=5)

        self.schedule_frame = tk.Frame(self.window, bg="gray20", pady=5)
        self.schedule_frame.pack(fill="x", padx=10, pady=5)

        self.schedule_label = tk.Label(self.schedule_frame, text="Auto-Log:", font=helv, fg="white", bg="gray20")
        self.schedule_label.pack(side="left", padx=5)

        self.schedule_var = tk.StringVar(self.window)
        self.schedule_options = ["Off", "Every Second", "Every Minute", "Every Hour", "Every Day"]
        self.schedule_var.set(self.schedule_options[0]) 
        
        self.schedule_menu = tk.OptionMenu(self.schedule_frame, self.schedule_var, *self.schedule_options)
        self.schedule_menu.config(font=("Helvetica", 10), bg="gray20", fg="white", width=12)
        self.schedule_menu.pack(side="left", padx=5)

        self.btn_schedule_toggle = tk.Button(self.schedule_frame, text="Start Schedule", font=helv, bg="gray50", fg="white", command=self.toggle_scheduler)
        self.btn_schedule_toggle.pack(side="left", expand=True, padx=5, ipady=2)

        self.status_label = tk.Label(self.window, text="Status: Calibrating...", font=("Helvetica", 10), fg="yellow", bg="gray10")
        self.status_label.pack(pady=5)

        self.video_loop()
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.window.mainloop()

    # --- NEW: Recalibrate Function ---
    def recalibrate(self):
        """Flags the app to re-run calibration on the next video frame."""
        self.calibrated = False
        self.pixels_per_mm = 0
        self.status_label.config(text="Status: Recalibrating...", fg="yellow")
        # Clear history as old mm values are now invalid
        self.measurement_history = [] 

    def video_loop(self):
        ret, frame = self.cap.read()
        if not ret:
            self.status_label.config(text="Error: Webcam feed lost.", fg="red")
            self.window.after(100, self.video_loop) # Try again
            return

        self.current_frame_raw = frame.copy() 
        frame_processed = frame.copy()

        # --- A. UPDATED: Calibration Logic ---
        # Only run calibration if not already calibrated
        if not self.calibrated:
            frame_processed, pixels_per_mm_found = find_pixels_per_mm(frame_processed)
            if pixels_per_mm_found > 0:
                self.pixels_per_mm = pixels_per_mm_found
                self.calibrated = True
                self.status_label.config(text="Status: Calibrated! Monitoring.", fg="green")
                print(f"Calibration successful: {self.pixels_per_mm:.2f} px/mm")
            else:
                # Show error but keep trying
                cv2.putText(frame_processed, "Cannot find BLUE reference object!", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                if not (self.scheduler_thread and self.scheduler_thread.is_alive()):
                    self.status_label.config(text="Status: Cannot find BLUE reference object.", fg="red")
        else:
            # Already calibrated, just draw the ref box for confirmation
            hsv = cv2.cvtColor(frame_processed, cv2.COLOR_BGR2HSV)
            mask = cv2.inRange(hsv, REFERENCE_LOWER, REFERENCE_UPPER)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                ref_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(ref_contour)
                cv2.rectangle(frame_processed, (x, y), (x + w, y + h), (255, 0, 0), 2)


        # --- B. Measurement ---
        plant_height_mm, total_leaf_area_mm2, leaf_count = 0.0, 0.0, 0
        
        # Only measure if calibration is successful
        if self.calibrated and self.pixels_per_mm > 0:
            if not (self.scheduler_thread and self.scheduler_thread.is_alive()) and self.calibrated:
                self.status_label.config(text="Status: Calibrated! Monitoring.", fg="green")

            plant_contours = find_plant_contours(frame_processed)
            
            if plant_contours:
                leaf_count = len(plant_contours)
                all_points = np.concatenate(plant_contours)
                x_all, y_all, w_all, h_all = cv2.boundingRect(all_points)
                cv2.rectangle(frame_processed, (x_all, y_all), (x_all + w_all, y_all + h_all), (0, 255, 0), 2) # Green box
                
                plant_height_mm = h_all / self.pixels_per_mm
                
                total_leaf_area_pixels = sum(cv2.contourArea(c) for c in plant_contours)
                total_leaf_area_mm2 = total_leaf_area_pixels / (self.pixels_per_mm ** 2)
                
                # --- NEW: Individual Leaf Tracking (Yellow Boxes) ---
                for i, c in enumerate(plant_contours):
                    x, y, w, h = cv2.boundingRect(c)
                    # Draw individual YELLOW box
                    cv2.rectangle(frame_processed, (x, y), (x + w, y + h), (0, 255, 255), 2) # BGR for Yellow
                    label = f"L{i + 1}"
                    cv2.putText(frame_processed, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
                # --- END NEW ---

        # Store metrics for the log button (RAW values)
        self.current_metrics = {
            "height": plant_height_mm, 
            "count": leaf_count, 
            "area": total_leaf_area_mm2
        }
        
        # --- NEW: Smoothing Logic ---
        self.measurement_history.append(self.current_metrics)
        if len(self.measurement_history) > self.smoothing_window:
            self.measurement_history.pop(0) 
            
        if self.measurement_history:
            avg_height = np.mean([m['height'] for m in self.measurement_history])
            avg_count = np.mean([m['count'] for m in self.measurement_history])
            avg_area = np.mean([m['area'] for m in self.measurement_history])
        else:
            avg_height, avg_count, avg_area = 0, 0, 0
        
        # Update UI labels (with SMOOTHED values)
        self.lbl_height.config(text=f"Height: {avg_height:.2f} mm")
        self.lbl_count.config(text=f"Leaf Count: {int(avg_count)}")
        self.lbl_area.config(text=f"Total Area: {avg_area:.2f} mm²")

        # --- C. Display ---
        frame_rgb = cv2.cvtColor(frame_processed, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)
        tk_image = ImageTk.PhotoImage(image=pil_image)
        
        self.video_label.imgtk = tk_image
        self.video_label.config(image=tk_image)
        
        self.window.after(10, self.video_loop)

    # --- UPDATED: 2-Second "Best Frame" Logger ---
    def log_data_thread(self):
        if not self.calibrated:
            self.status_label.config(text="Status: Please calibrate first!", fg="red")
            return
            
        self.status_label.config(text="Status: Analyzing for 2 seconds...", fg="yellow")
        
        start_time = time.time()
        all_measurements = []

        print("Starting 2-second analysis window...")
        while time.time() - start_time < 2.0:
            if self.current_frame_raw is not None:
                # We copy to prevent issues from the other thread writing to them
                current_metrics_copy = self.current_metrics.copy()
                current_frame_copy = self.current_frame_raw.copy()
                all_measurements.append((current_metrics_copy, current_frame_copy))
            time.sleep(0.1) 
        
        if not all_measurements:
            self.status_label.config(text="Status: Analysis failed (no frames).", fg="red")
            return

        # Find the best measurement based on highest total leaf area
        best_measurement = max(all_measurements, key=lambda item: item[0]['area'])
        
        best_metrics = best_measurement[0]
        best_frame = best_measurement[1]

        print(f"Analysis complete. Best Area: {best_metrics['area']:.2f} mm^2")
        self.status_label.config(text="Status: Analysis complete. Logging data...", fg="yellow")

        timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(IMAGE_DIR, f'plant_{timestamp_str}_best.jpg')
        
        cv2.imwrite(filename, best_frame)
        
        height = best_metrics["height"]
        count = best_metrics["count"]
        area = best_metrics["area"]

        log_thread = threading.Thread(
            target=self.log_to_sheets_and_update_status,
            args=(height, count, area, filename)
        )
        log_thread.start()
    # --- END OF UPDATE ---

    def log_to_sheets_and_update_status(self, height, count, area, filename):
        success = log_data(height, count, area, filename)
        
        if success:
            self.window.after(0, self.status_label.config, {"text": "Status: Logged successfully!", "fg": "green"})
        else:
            self.window.after(0, self.status_label.config, {"text": "Status: Logging FAILED. Check terminal.", "fg": "red"})

        time.sleep(3)
        if not (self.scheduler_thread and self.scheduler_thread.is_alive()) and self.calibrated:
             self.window.after(0, self.status_label.config, {"text": "Status: Calibrated! Monitoring.", "fg": "green"})

    # --- SCHEDULER FUNCTIONS ---
    def toggle_scheduler(self):
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_stop_event.set()
            self.btn_schedule_toggle.config(text="Start Schedule", bg="gray50")
            self.status_label.config(text="Status: Scheduler stopping...", fg="yellow")
        else:
            if not self.calibrated:
                self.status_label.config(text="Status: Please calibrate first!", fg="red")
                return
            
            self.scheduler_stop_event.clear()
            self.btn_schedule_toggle.config(text="Stop Schedule", bg="orange")
            
            self.scheduler_thread = threading.Thread(target=self.scheduler_loop, daemon=True)
            self.scheduler_thread.start()

    def scheduler_loop(self):
        selected_option = self.schedule_var.get()
        
        interval_map = {
            "Every Second": 1,
            "Every Minute": 60,
            "Every Hour": 3600,
            "Every Day": 86400
        }
        interval_seconds = interval_map.get(selected_option)

        if not interval_seconds:
            self.window.after(0, self.status_label.config, {"text": "Status: Scheduler Off.", "fg": "gray80"})
            self.window.after(0, self.btn_schedule_toggle.config, {"text": "Start Schedule", "bg": "gray50"})
            return

        self.window.after(0, self.status_label.config, {"text": f"Status: Auto-logging {selected_option}", "fg": "cyan"})

        while not self.scheduler_stop_event.is_set():
            print(f"Scheduler: Triggering log for {selected_option}")
            self.log_data_thread()
            stopped = self.scheduler_stop_event.wait(timeout=interval_seconds)
            if stopped:
                break 

        print("Scheduler loop finished.")
        self.window.after(0, self.status_label.config, {"text": "Status: Scheduler Off.", "fg": "gray80"})
        self.window.after(0, self.btn_schedule_toggle.config, {"text": "Start Schedule", "bg": "gray50"})


    def on_closing(self):
        print("Closing application...")
        self.scheduler_stop_event.set()
        self.cap.release()
        self.window.destroy()


# --- 5. START THE APPLICATION ---
if __name__ == "__main__":
    PlantMonitorApp()

