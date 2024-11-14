from flask import Flask, request, render_template, redirect, url_for, flash
import pandas as pd
import json
import os
import time
import schedule
from datetime import datetime, timedelta
import pytz
import roboflow

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Paths
images_folder = "Images"
bev_master_file_path = "Data/master_file.xlsx"
json_folder = "JSON"
report_folder = "Report"

# Ensure necessary folders exist
for folder in [images_folder, json_folder, "Data", report_folder]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Roboflow API key and model ID
api_key = "YxeULFmRqt8AtNbwzXrT"
model_id = "cooler-image"
model_version = "1"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_files():
    uploaded_files = request.files.getlist("images")
    if not uploaded_files:
        flash("No files uploaded. Please try again.")
        return redirect(url_for('index'))

    for file in uploaded_files:
        file.save(os.path.join(images_folder, file.filename))
    
    flash("Images uploaded successfully!")
    return redirect(url_for('index'))

def generate_compliance_report():
    # (Place your report generation code here from the Streamlit function, slightly modified for Flask)
    # This includes roboflow setup, data processing, and saving the report as before.

    # Placeholder message for simplicity:
    print("Compliance report generated successfully.")

@app.route('/generate-report')
def generate_report():
    generate_compliance_report()
    flash("Compliance report generated successfully!")
    return render_template("report.html", report_folder=report_folder)

def run_scheduled_task():
    # Define schedule logic here, similar to the Streamlit code's schedule setup
    print("Scheduled task triggered for compliance report generation.")
    check_images_folder()  # Your modified folder check function

def check_images_folder():
    if not os.listdir(images_folder):
        print("No images in the Images folder. Please upload images.")
    else:
        generate_compliance_report()

# Scheduler setup
schedule_time = "03:00"
ist = pytz.timezone('Asia/Kolkata')

def scheduler():
    while True:
        now_utc = datetime.now(pytz.utc)
        now_ist = now_utc.astimezone(ist)
        target_time = datetime.strptime(schedule_time, "%H:%M").time()
        if now_ist.time() == target_time:
            check_images_folder()
        time.sleep(60)

if __name__ == '__main__':
    app.run(debug=True)
    # Optional: Run scheduler in background if needed
    # scheduler()
