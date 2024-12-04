from flask import Flask, render_template, request, send_file, session, jsonify, send_from_directory, make_response
import os
import json
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management

def merge_jsons(json1, json2):
    final_json = {}
    all_keys = set(json1.keys()).union(set(json2.keys()))

    for key in all_keys:
        value1 = json1.get(key)
        value2 = json2.get(key)

        if value1 == value2:
            final_json[key] = {"value": value1}
        else:
            final_json[key] = [
                {"value": value1, "source": "model1"} if value1 is not None else None,
                {"value": value2, "source": "model2"} if value2 is not None else None
            ]
            final_json[key] = [entry for entry in final_json[key] if entry is not None]

    return final_json

def process_folders(folder1, folder2):
    merged_data = {}

    files = [f for f in os.listdir(folder1) if f.endswith('.json')]

    for file in files:
        file_path1 = os.path.join(folder1, file)
        file_path2 = os.path.join(folder2, file)

        if not os.path.exists(file_path2):
            print(f"File {file} does not exist in {folder2}. Skipping.")
            continue

        with open(file_path1, 'r') as f1, open(file_path2, 'r') as f2:
            json1 = json.load(f1)
            json2 = json.load(f2)

        merged_json = merge_jsons(json1, json2)
        merged_data[file] = merged_json

    return merged_data

def update_json_file(file, changes):
    """Update the JSON file with the new changes."""
    merged_data = session.get('merged_data', {})
    if file not in merged_data:
        return False, "File not found in session"

    file_data = merged_data[file]
    
    # Apply changes
    for change in changes:
        key = change['key']
        new_value = change['value']
        
        if key in file_data:
            if isinstance(file_data[key], dict):
                file_data[key]['value'] = new_value
            else:
                # Find and update the correct entry in the list
                source = change.get('source')
                for entry in file_data[key]:
                    if entry['source'] == source:
                        entry['value'] = new_value
                        break
    
    # Update session data
    merged_data[file] = file_data
    session['merged_data'] = merged_data
    
    return True, None

def prepare_download_json(file_data, selected_values=None):
    """Prepare JSON for download, including only selected values for radio options."""
    download_data = {}
    
    for key, value in file_data.items():
        if isinstance(value, dict):
            # For single values, just include the value
            download_data[key] = value['value']
        else:
            # For radio button groups, check for selected value
            if selected_values:
                # Try to find the selected value for this key
                for param_key, param_value in selected_values.items():
                    if param_key.endswith(key):
                        download_data[key] = param_value
                        break
                else:
                    # If no selection is found, use the first value as default
                    download_data[key] = value[0]['value']
            else:
                # If no selections provided, use the first value as default
                download_data[key] = value[0]['value']
    
    return download_data

# Define a custom filter to check if a value is a dictionary
@app.template_filter('is_dict')
def is_dict(value):
    return isinstance(value, dict)

def validate_selections(merged_data, form_data=None):
    """Validate that all required selections have been made."""
    if form_data is None:
        form_data = request.form
        
    for file, data in merged_data.items():
        for key, value in data.items():
            if not isinstance(value, dict):  # If it's not a single value
                field_name = f'file_{file}_{key}'
                if form_data and field_name not in form_data:
                    return False
    return True

@app.route('/')
def index():
    folder1 = '/home/jasmin/dq/mergejsons/folder1'
    folder2 = '/home/jasmin/dq/mergejsons/folder2'
    merged_data = process_folders(folder1, folder2)
    session['merged_data'] = merged_data
    return render_template('merged_json.html', merged_data=merged_data)

@app.route('/get_image/<filename>')
def get_image(filename):
    images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')
    return send_from_directory(images_dir, filename)

@app.route('/save_changes', methods=['POST'])
def save_changes():
    try:
        data = request.get_json()
        if not data or 'file' not in data or 'changes' not in data:
            return jsonify({'success': False, 'error': 'Invalid request data'})
        
        merged_data = session.get('merged_data', {})
        file = data['file']
        changes = data['changes']

        if file not in merged_data:
            return jsonify({'success': False, 'error': 'File not found'})

        file_data = merged_data[file]
        
        # Apply changes
        for change in changes:
            key = change['key']
            new_value = change['value']
            source = change.get('source')
            
            if key in file_data:
                if isinstance(file_data[key], dict):
                    # Update single value
                    file_data[key]['value'] = new_value
                else:
                    # Update value in radio group
                    for entry in file_data[key]:
                        if entry['source'] == source:
                            entry['value'] = new_value
                            break

        # Update session data
        session['merged_data'] = merged_data
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/download/<filename>')
def download_json(filename):
    merged_data = session.get('merged_data', {})
    if filename not in merged_data:
        return "File not found", 404
    
    file_data = merged_data[filename]
    download_data = {}
    
    # Process all fields
    for key, value in file_data.items():
        if isinstance(value, dict):
            # Single value field
            download_data[key] = value['value']
        else:
            # Radio button group
            field_name = f'file_{filename}_{key}'
            selected_value = request.args.get(field_name)
            
            if selected_value:
                download_data[key] = selected_value
            else:
                # If no selection, use the first value
                download_data[key] = value[0]['value']
    
    # Create response
    response = make_response(json.dumps(download_data, indent=2))
    response.headers['Content-Type'] = 'application/json'
    response.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return response

if __name__ == '__main__':
    app.run(debug=True)