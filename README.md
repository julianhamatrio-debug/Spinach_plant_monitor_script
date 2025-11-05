# Spinach_plant_monitor_script
simple spinach plant monitor tool (leaf, stem) that can be logged into a google spreadsheet
*REQUIRES A GOOGLE SERVICE ACCOUNT WITH THEIR APIs ENABLED ON GOOGLE SPREADSHEET AND GOOGLE DRIVE*
-INSTRUCTIONS AT THE END



Real-Time Spinach Growth Monitor

1. Project Objective

The primary goal of this project was to develop a "bot" capable of monitoring the growth of a red spinach plant. The application was designed to move beyond manual measurements and provide a non-invasive, automated, and data-driven way to track plant health over time.

The core requirements were to measure:

Plant Height

Leaf Count

Total Leaf Area

This data was to be logged automatically to a Google Sheet for analysis.

2. Key Features of Final Application

The final application (monitor_version_app_leaf logic Update.py) is a complete, standalone desktop tool with the following features:

Live Video Feed: A real-time UI displays the webcam's view.

Real-Time Metrics: The UI shows a stabilized, live-updated "Plant Height (mm)", "Leaf Count", and "Total Leaf Area (mm²)."

Visual Analysis Overlay:

Draws a green box around the entire plant to show total height.

Draws yellow boxes (labeled L1, L2, etc.) around each individually detected leaf.

Draws a blue box around the reference object to confirm calibration.

Dynamic Calibration: A "RECALIBRATE" button allows the user to reset the pixels_per_mm ratio on the fly if the camera or plant is moved.

Manual & Automatic Logging:

A "LOG DATA" button allows for manual, on-demand logging.

A dropdown menu and "Start/Stop" button provide a full scheduler for automated logging (every second, minute, hour, or day).

Data Persistence: All logged data is sent to a Google Sheet via the gspread library, along with a timestamp and the filename of a snapshot.

Image Capture: A snapshot (e.g., plant_2025-11-05_19-30-00_best.jpg) is saved to a local captures/ folder for each log event.

3. Technology Stack

Language: Python 3

Computer Vision: OpenCV (cv2) for all image processing, color masking, and feature extraction.

GUI: Tkinter for the complete graphical user interface, including buttons, labels, and the video panel.

Data Logging: gspread library to interface with the Google Sheets API.

Concurrency: threading module to run the scheduler and data logging in the background, preventing the UI from freezing.

Utility Libraries: PIL (Pillow) to integrate OpenCV images with Tkinter, NumPy for numerical operations, os, and time.

4. Development & Iteration Process (What You Did)

The project evolved significantly through an iterative development process to solve key challenges:

Initial Concept: The project began as a simple, single-script idea to measure green spinach.

Pivoting to Red Spinach: You identified that the target was red spinach. This required a major logic change, moving from a simple green mask to a complex dual-range red mask (PLANT_LOWER_1, PLANT_LOWER_2) to handle the "wrap-around" hue of red.

Solving the "Stem Problem": The most critical challenge was that the red stems were being counted as leaves. Based on your photo (image_e7e71f.jpg), we iterated on detection logic.

Refining Leaf Detection: You provided a high-detail leaf image (image_656489.png). This allowed us to stop guessing and fine-tune the HSV color ranges (PLANT_LOWER_1, PLANT_UPPER_1) to specifically target the reddish-brown/olive color of your leaves, while ignoring the purer red of the stems.

Stem/Noise Filtering: To support this, we implemented an aggressive cv2.erode and cv2.dilate (3 iterations) to filter out the thin stems, as well as a MIN_LEAF_AREA_PIXELS to ignore camera noise.

Solving Instability: The live data was "flickering." You identified this as a key problem, which we solved with three main features:

UI Smoothing: A 30-frame running average (self.measurement_history) was added to stabilize the numbers displayed on the screen.

"Best Frame" Logging: The "LOG DATA" function was upgraded to analyze the feed for 2 seconds and log the data from the single best frame (based on max leaf area).

Calibration Lock: A self.calibrated flag and "RECALIBRATE" button were added to lock the pixels_per_mm ratio, preventing it from flickering and causing unstable mm measurements.

5. Final Application Functionality

The final code represents a robust, user-friendly, and stable phenotyping tool. It successfully overcomes the challenges of color-based segmentation and unstable live video by using a combination of precise HSV tuning, morphological operations (erosion/dilation), and intelligent data stabilization (smoothing and "best frame" analysis).

(SETTING UP THE APIs)
Google Sheets API Setup (credentials.json)

-This is for the google_sheets_logger.py script.

Enable the "Google Sheets API" and "Google Drive API" on your account.

Create a "Service Account".

Download the service account's key file. Rename this file to credentials.json and place it in the same directory as the Python scripts.

Create a new Google Sheet (e.g., "Spinach Growth Log").

Click the "Share" button on the sheet.

Find the client_email address inside your credentials.json file (it looks like ...gserviceaccount.com).

Paste this email into the "Share" dialog and give it "Editor" permissions.


