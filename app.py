from flask import Flask, render_template, flash
import pandas as pd
import json
import roboflow
import os
from datetime import datetime
import pytz
import schedule
import time
import threading

# Initialize Flask app
app = Flask(__name__)
app.secret_key = "supersecretkey"  # Needed for flash messages

# Paths and Configuration
images_folder = "Images"
bev_master_file_path = "Data/master_file.xlsx"
json_folder = "JSON"
report_folder = "Report"
schedule_time = "12:28"  # 24-hour format for schedule library

# Create folders if they don't exist
for folder in [images_folder, json_folder, "Data", report_folder]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Roboflow API configuration
api_key = "YxeULFmRqt8AtNbwzXrT"
model_id = "cooler-image"
model_version = "1"

# Helper function to generate compliance report
def generate_compliance_report():
    uploaded_files = [os.path.join(images_folder, file) for file in os.listdir(images_folder) if file.endswith(('jpg', 'jpeg', 'png'))]
    bev_master_file = bev_master_file_path

    if not uploaded_files or not bev_master_file:
        flash("Please upload all required files.", "error")
        return None
    else:
        img_names = [os.path.basename(file) for file in uploaded_files]
        
        rf = roboflow.Roboflow(api_key=api_key)
        model = rf.workspace().project(model_id).version(model_version).model

        # Function to process images and generate JSON
        def get_json_op(image_file_path):
            predictions_response = model.predict(image_file_path).json()
            predictions = predictions_response.get("predictions", [])
            
            output_json_path = os.path.join(json_folder, f"OP_{os.path.basename(image_file_path)}.json")
            with open(output_json_path, 'w') as json_file:
                json.dump(predictions, json_file, indent=4)
            return output_json_path

        json_paths = [get_json_op(file) for file in uploaded_files]

        # Define functions for report generation
        def size_classification(name):
            return "ic" if 'small' in name.lower() else "otg" if 'medium' in name.lower() else "fc" if 'big' in name.lower() or 'large' in name.lower() else ""

        def follows_order(ideal_order, current_order):
            ideal_index = 0
            for item in current_order:
                while ideal_index < len(ideal_order) and ideal_order[ideal_index] != item:
                    ideal_index += 1
                if ideal_index == len(ideal_order):
                    return 0
            return 1

        def expected_shelf_op(shelf):
            return "ic" if shelf in [1, 2] else "otg" if shelf in [3, 4] else "fc" if shelf >= 5 else ""

        ideal_order = ['Cola', 'Flavour', 'Energy Drink', 'Stills', 'Mixers', 'Water']

        bev_master = pd.read_excel(bev_master_file)

        def pack_order_comp(json_img_op):
            df = pd.read_json(json_img_op)
            df = df.sort_values(by=['y', 'x']).reset_index(drop=True)
            df['Image_id'] = os.path.basename(json_img_op).strip('.json').strip('OP_')
            
            df['y_diff'] = df['y'].diff().fillna(0)
            threshold = 50
            df['new_bin'] = (df['y_diff'] > threshold).cumsum()
            df['shelf'] = df['new_bin'].apply(lambda x: f'{x+1}')
            df['shelf'] = df['shelf'].astype('int')
            df.drop(columns=['y_diff', 'new_bin'], inplace=True)
            df = df.sort_values(by=['shelf', 'x'])
            
            df['actual size (json op)'] = df['class'].apply(size_classification)
            df = pd.merge(df, bev_master[['class_id', 'flavour_type']], on='class_id', how='left')
            df['expected size'] = df['shelf'].apply(expected_shelf_op)
            df['pack_order_check'] = df.apply(lambda row: 1 if row['actual size (json op)'] != row['expected size'] else 0, axis=1)
            
            return df

        def brand_order_comp(json_img_op):
            poc_op = pack_order_comp(json_img_op)
            shelf_flavour_mapping = poc_op.groupby('shelf')['flavour_type'].apply(list).to_dict()
            comparison_result = []
            for shelf, flavours in shelf_flavour_mapping.items():
                result = {
                    'Shelf': shelf,
                    'Flavour List': flavours,
                    'Ideal Order': ideal_order,
                    'brand_order_check': follows_order(ideal_order, flavours)
                }
                comparison_result.append(result)
            
            comparison_df = pd.DataFrame(comparison_result)
            comparison_df['Image_id'] = os.path.basename(json_img_op).strip('.json').strip('OP_')
            return comparison_df

        pack_compliance_output = pd.DataFrame()
        brand_compliance_df = pd.DataFrame()

        for json_path in json_paths:
            output_df = pack_order_comp(json_path)
            pack_compliance_output = pd.concat([pack_compliance_output, output_df], ignore_index=True)
            pack_compliance_output = pack_compliance_output[['Image_id', 'x', 'y', 'width', 'height', 'confidence', 'class', 'class_id',
                                                             'detection_id', 'prediction_type', 'shelf',
                                                             'actual size (json op)', 'flavour_type', 'expected size', 'pack_order_check']]

            brand_output_df = brand_order_comp(json_path)
            brand_compliance_df = pd.concat([brand_compliance_df, brand_output_df], ignore_index=True)
            brand_compliance_df = brand_compliance_df[['Image_id', 'Shelf', 'Flavour List', 'Ideal Order', 'brand_order_check']]

        pack_order_check = pd.DataFrame(pack_compliance_output.groupby('Image_id')['pack_order_check'].sum().reset_index())
        pack_order_check['pack_order_score'] = pack_order_check.apply(lambda row: 0 if row['pack_order_check'] > 0 else 2, axis=1)

        brand_order_check = pd.DataFrame(brand_compliance_df.groupby('Image_id')['brand_order_check'].sum().reset_index())
        brand_order_check['brand_order_score'] = brand_order_check.apply(lambda row: 3 if row['brand_order_check'] == 5 else 0, axis=1)

        final_op = pd.merge(pack_order_check, brand_order_check, on='Image_id')
        final_op = final_op.drop(columns=['pack_order_check', 'brand_order_check'])

        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        compliance_report_path = os.path.join(report_folder, f"COMPLIANCE_REPORT_{current_time}.xlsx")
        with pd.ExcelWriter(compliance_report_path, engine='openpyxl') as writer:
            final_op.to_excel(writer, sheet_name='Compliance Scores', index=False)
            pack_compliance_output.to_excel(writer, sheet_name='Pack Order Compliance', index=False)
            brand_compliance_df.to_excel(writer, sheet_name='Brand Order Compliance', index=False)

        flash("Compliance report generated successfully!", "success")
        return compliance_report_path

# Schedule the report generation
def schedule_compliance_report():
    schedule.every().day.at(schedule_time).do(generate_compliance_report)

    while True:
        schedule.run_pending()
        time.sleep(1)

# Run the scheduler in a separate thread
threading.Thread(target=schedule_compliance_report, daemon=True).start()

@app.route('/')
def index():
    return render_template('index.html', schedule_time=schedule_time)

if __name__ == '__main__':
    app.run(debug=True)