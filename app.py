from flask import Flask, render_template, request, jsonify, send_file 
import configparser
import sqlite3
import json
import os
from io import StringIO
from tempfile import NamedTemporaryFile

# Flask App Configuration
app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# Parse configuration content from string
def parse_config_string(config_string, file_type='ini'):
    if file_type == 'json':
        return json.loads(config_string)
    elif file_type == 'ini':
        config = configparser.ConfigParser()
        config.read_file(StringIO(config_string))
        return {
            section: {key: config[section][key] for key in config[section]}
            for section in config.sections()
        }
    else:
        raise ValueError("Unsupported config file format.")

# Save new configuration to the database
def save_to_db(config_data):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS config_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        ''')
        cursor.execute('INSERT INTO config_data (data) VALUES (?)', (json.dumps(config_data),))
        conn.commit()

# Update the latest configuration entry
def update_last_config(config_data):
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM config_data ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        if row:
            cursor.execute('UPDATE config_data SET data = ? WHERE id = ?', (json.dumps(config_data), row[0]))
        else:
            cursor.execute('INSERT INTO config_data (data) VALUES (?)', (json.dumps(config_data),))
        conn.commit()


# Fetch the most recent config from DB
def get_latest_config():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT data FROM config_data ORDER BY id DESC LIMIT 1')
        row = cursor.fetchone()
        return json.loads(row[0]) if row else {}


# Main Page: Upload / Paste and Parse Config
@app.route('/', methods=['GET', 'POST'])
def index():
    message = None
    config_data = {}
    pasted_text = ""

    if request.method == 'POST':
        try:
            pasted_text = request.form.get("config_content", "").strip()
            file = request.files.get('config_file')
            config_string = ""
            file_type = 'ini'

            if file:
                filename = file.filename
                ext = os.path.splitext(filename)[1].lower()
                config_string = file.read().decode('utf-8')

                if ext == '.json':
                    file_type = 'json'
                elif ext == '.ini':
                    file_type = 'ini'
                else:
                    raise ValueError("Unsupported file format. Only .ini and .json are allowed.")
            elif pasted_text:
                config_string = pasted_text
                # Optional: Add detection here too if pasted JSON

            if not config_string:
                raise ValueError("No configuration input provided.")

            config_data = parse_config_string(config_string, file_type=file_type)
            save_to_db(config_data)
            message = "✅ Configuration parsed and saved successfully!"
        except Exception as e:
            message = f"❌ Error: {str(e)}"

    return render_template('index.html', message=message, config=config_data, pasted=pasted_text)

# API: Get latest config as JSON
@app.route('/get-config', methods=['GET'])
def get_config():
    try:
        config = get_latest_config()
        return jsonify(config) if config else jsonify({"message": "No configuration found."}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# API: Save edited config via AJAX
@app.route('/save-edited-config', methods=['POST'])
def save_edited_config():
    try:
        data = request.json
        if not data:
            raise ValueError("No data received for saving.")
        update_last_config(data)
        return jsonify({"message": "✅ Configuration updated successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Export Config as .ini or .json (downloadable)
@app.route('/export-config', methods=['GET'])
def export_config():
    try:
        export_format = request.args.get('format', 'ini').lower()
        config = get_latest_config()

        if not config:
            return "❌ No configuration available to export.", 404

        if export_format == 'json':
            with NamedTemporaryFile(mode='w+', delete=False, suffix='.json') as tmp:
                json.dump(config, tmp, indent=4)
                tmp_path = tmp.name
            return send_file(tmp_path, as_attachment=True, download_name='config.json')

        elif export_format == 'ini':
            parser = configparser.ConfigParser()
            for section, options in config.items():
                parser[section] = options
            with NamedTemporaryFile(mode='w+', delete=False, suffix='.ini') as tmp:
                parser.write(tmp)
                tmp_path = tmp.name
            return send_file(tmp_path, as_attachment=True, download_name='config.ini')

        return "❌ Invalid format. Use ?format=ini or ?format=json", 400

    except Exception as e:
        return f"❌ Error exporting config: {str(e)}", 500


# App Runner
if __name__ == '__main__':
    app.run(debug=True)
