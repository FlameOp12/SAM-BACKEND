from flask import Flask, request, jsonify
from flask_cors import CORS
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import pytz
import hmac
import hashlib
import json
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import base64
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": ["http://*", "https://*"]}}, supports_credentials=True)

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

requests_sheet = client.open("StudentRecords_SAM").worksheet("Active_Records")
login_sheet = client.open("StudentRecords_SAM").worksheet('Student_Data')
done_sheet = client.open("StudentRecords_SAM").worksheet("Past_Records")
tz = pytz.timezone('Asia/Kolkata')

SECRET_KEY="1e8c0859a23047974ffdb4b0bdec79879fb96dd2943d1bf93ba05d42427c006b"


logging.basicConfig(level=logging.INFO)
app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,  # Number of proxy servers in front of Flask
    x_proto=1,  # Number of proxy servers for protocol
    x_host=1,   # Number of proxy servers for host
    x_port=1,   # Number of proxy servers for port
    x_prefix=1  # Number of proxy servers for URL prefix
)

@app.before_request
def log_client_ip():
    client_ip = request.remote_addr
    # logging.info(f"Client IP Address: {client_ip}")

# Define a middleware function to log IP addresses
def log_ip_address(app):
    @app.before_request
    def log_client_ip():
        client_ip = request.remote_addr
        # print(f"Client IP Address: {client_ip}")

log_ip_address(app)

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    # default_limits=["70 per day"],
    storage_uri="redis://127.0.0.1:6379/0"  # Localhost since Flask is on the same server
)

#student
# def decode_signature(encoded_signature, secret_key):
#     # Step 1: Base64 decoding
#     # print("Base64 decoding started.")
#     decoded_bytes = base64.b64decode(encoded_signature)
#     print(f"Decoded signature base 64: {decoded_bytes}")

#     decoded=decoded_bytes

#     # Step 2: Reverse the XOR transformation
#     derived_key = sum(ord(c) for c in secret_key) % 256  # Use secret_key to derive key for XOR
#     print(f"Derived key for XOR: {derived_key}")

#     try:
#         mixed_bytes = bytearray(decoded_bytes)
#         mixed_string = ''.join(chr(b ^ derived_key) for b in mixed_bytes)
#         print(f"Mixed string after XOR: {mixed_string}")
#     except Exception as e:
#         print(f"XOR transformation failed: {e}")
#         return False, "XOR transformation failed."

#     # Step 3: Extract roll number based on the known positions in the mixed string
#     positions = [2, 5, 8, 11, 14, 17, 20, 23, 26]  # Fixed positions
#     mixed = list(mixed_string)
#     print(f"Mixed list: {mixed}")

#     # Extract roll number
#     extracted_roll_number = ''.join(mixed[pos] for pos in positions)
#     print(f"Extracted roll number: {extracted_roll_number}")

#     # Remove roll number from the mixed string to reconstruct the secret key
#     for pos in reversed(positions):  # Remove in reverse order to avoid index shifts
#         del mixed[pos]
#     reconstructed_secret_key = ''.join(mixed)
#     print(f"Reconstructed secret key (after removal of roll number): {reconstructed_secret_key}")

#     try:
#         roll_number_column = login_sheet.col_values(1)  # Assuming "RollNumber" is in the first column
#         #print(f"Roll number column: {roll_number_column}")
        
#         if extracted_roll_number in roll_number_column:
#             row_index = roll_number_column.index(extracted_roll_number) + 1  # Add 1 for 1-based indexing
#             token_column_index = login_sheet.row_values(1).index("Token") + 1  # Find "Token" column index
#             print(f"Token column index: {token_column_index}")

#             token = login_sheet.cell(row_index, token_column_index).value
#             print(f"Token found: {token}")

#             if token == encoded_signature:
#                 print("Signature verification passed.")
#                 return True
#         else:
#             return False, "Roll number not found."
#     except Exception as e:
#         return False, f"Error: {e}"

def verify_request_signature(valid_roll_number):
    """Verify the request's Authorization signature using the secret key."""
    received_signature = request.headers.get('Authorization', '').replace('Bearer ', '').strip()
    # print("Received signature: ", received_signature)

    if not received_signature:
        return jsonify({'success': False, 'message': 'Authorization header missing or invalid'}), 401
    
    try:
        token_column = login_sheet.col_values(6)  # Assuming "Token" is in column 6
        #print(f"Token column: {token_column}")
        
        if received_signature in token_column:
            row_index = token_column.index(received_signature) + 1  # 1-based indexing for rows
            old_rollno_column_index = 1  # Assuming "RollNumber" is in column 1
            new_rollno_column_index = 2  # Assuming "NewRollNumber" is in column 2

            old_roll_number = login_sheet.cell(row_index, old_rollno_column_index).value.lower()
            # print(f"Old Roll Number found: {old_roll_number}")

            new_roll_number = login_sheet.cell(row_index, new_rollno_column_index).value.lower()
            # print(f"New Roll Number found: {new_roll_number}")

            if old_roll_number == valid_roll_number.lower() or new_roll_number == valid_roll_number.lower():
                # print("Signature verification passed.")
                return None  # Verification successful; no error response
        return jsonify({'success': False, 'message': 'Signature verification failed'}), 403
    except Exception as e:
        # print(f"Error during signature verification: {e}")
        return jsonify({'success': False, 'message': f'Error during verification: {str(e)}'}), 500

    
    # decoded_received_signature = decode_signature(received_signature, SECRET_KEY)

    # # expected_signature = SECRET_KEY
    # # print("expected signature: ", expected_signature)

    # if decoded_received_signature == "False":
    #     print("Signature verification failed.")
    #     return jsonify({'success': False, 'message': 'Invalid Signature'}), 401

    # print("Signature verification passed.")
    # return None  # Means verification passed



def check_date_overlap(roll_number, new_out_date, new_in_date):
    existing_requests = [
        record for record in requests_sheet.get_all_records()
        if str(record.get("RollNumber")) == roll_number
        and record.get("Status", "").strip().upper() != "DONE"
    ]

    for existing_req in existing_requests:
        existing_out = datetime.strptime(existing_req['OutDate'], '%d/%m/%Y').date()
        existing_in = datetime.strptime(existing_req['InDate'], '%d/%m/%Y').date()
        
        if new_out_date <= existing_in and existing_out <= new_in_date:
            return True
    return False


@app.route('/requests/<roll_number>', methods=['GET'])
@limiter.limit("20 per minute")
def get_requests(roll_number):
    verification_response = verify_request_signature(roll_number)
    if verification_response:
        return verification_response 
    
    records = requests_sheet.get_all_records()
    filtered_requests = [
        {
            "request_id":  record.get("RequestID",""),
            "L/O": record.get("L/O",""),
            "OutDate": record.get("OutDate", ""),
            "InDate": record.get("InDate", ""),
            "Locality/Area": record.get("Locality/Area", ""),
            "City": record.get("City", ""),
            "State": record.get("State", ""),
            "Reason": record.get("Reason", ""),
            "Phone Number": record.get("Phone Number", ""),
            "Alt. Phone Number": record.get("Alt. Phone Number", ""),
            "Documents": record.get("Documents", ""),
            "Status": record.get("Status", ""),
            "OutTime": record.get("OutTime", ""),
            "InTime": record.get("InTime", "")
        }
        for idx, record in enumerate(records)
        if str(record.get("RollNumber")) == roll_number and record.get("Status", "").strip() not in ["DONE", ""]
    ]
    return jsonify(filtered_requests), 200

@app.route('/past_requests/<roll_number>', methods=['GET'])
@limiter.limit("10 per minute")
def get_past_requests(roll_number):
    #print(roll_number)
    verification_response = verify_request_signature(roll_number)
    if verification_response:
        return verification_response 
    
    records = done_sheet.get_all_records()
    #print(records)
    filtered_requests = [
        {
            "request_id": record.get("RequestID",""),
            "L/O": record.get("L/O",""),
            "OutDate": record.get("OutDate", ""),
            "InDate": record.get("InDate", ""),
            "Locality/Area": record.get("Locality/Area", ""),
            "City": record.get("City", ""),
            "State": record.get("State", ""),
            "Reason": record.get("Reason", ""),
            "Phone Number": record.get("Phone Number", ""),
            "Alt. Phone Number": record.get("Alt. Phone Number", ""),
            "Documents": record.get("Documents", ""),
            "Status": record.get("Status", ""),
            "OutTime": record.get("OutTime", ""),
            "InTime": record.get("InTime", "")
        }
        for idx, record in enumerate(records)
        if str(record.get("RollNumber")) == roll_number and record.get("Status", "").strip() == "DONE"
    ]
    return jsonify(filtered_requests), 200

@app.route('/student_details/<roll_number>', methods=['GET'])
@limiter.limit("20 per minute")
def student_details(roll_number):
    # print(roll_number)
    verification_response = verify_request_signature(roll_number)
    if verification_response:
        return verification_response 
    
    #print(roll_number)
    records = login_sheet.get_all_records()
    filtered_requests = [
        {
            'RollNumber': str(record.get("Roll Number (New Roll Number)", "")).strip().upper(),
            'Name': str(record.get("Full Name", "")),
            'Batch': str(record.get("Batch", "")),
            #'HostelName': str(record.get("Hostel Name", ""))
        }
        for record in records
        if str(record.get("Old Roll Number")).strip().upper() == str(roll_number).upper()
    ]

    if filtered_requests:
        return jsonify(filtered_requests[0]), 200

    return jsonify({'success': False, 'message': 'Student not found'}), 404

@app.route('/new_request_local', methods=['POST'])
@limiter.limit("10 per minute")
def new_request_local():
    data = request.get_json() 
    
    roll_number = data.get('RollNumber')

     # Step 1: Verify Signature
    verification_response = verify_request_signature(roll_number)
    if verification_response:
        return verification_response  

    name = data.get('Name')
    batch = data.get('Batch')
    #hostel_name = data.get('HostelName')
    local_outstation = data.get('L/O')
    out_date = data.get('OutDate')
    in_date = data.get('InDate')
    locality_area = data.get('Locality/Area')
    city = data.get('City')
    state = data.get('State')
    reason = data.get('Reason')
    ph_number = data.get('Phone Number')
    alt_ph_number = data.get('Alt. Phone Number')
    documents = data.get('Documents')
    status = data.get('Status', "")
    out_time = data.get('OutTime', "")
    in_time = data.get('InTime', "")

    # if not roll_number or not name or not batch or not hostel_name or not out_date or not in_date:
    #     return jsonify({'success': False, 'message': 'Please fill in all required fields'}), 400

    # records = requests_sheet.get_all_records()
    # for record in records:
    #     if str(record.get("RollNumber")) == roll_number and record.get("L/O") == "L" and record.get("Status", "").strip().upper() == "OUT":
    #         return jsonify({'success': False, 'message': 'You already have an active Single day outing request'}), 400

    required_fields = [roll_number, name, batch, out_date, in_date]
    if not all(required_fields):
        return jsonify({'success': False, 'message': 'Please fill in all required fields'}), 400

    try:
        new_out_date = datetime.strptime(out_date, '%d/%m/%Y').date()
        new_in_date = datetime.strptime(in_date, '%d/%m/%Y').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format. Use DD/MM/YYYY'}), 400

    if check_date_overlap(roll_number, new_out_date, new_in_date):
        return jsonify({'success': False, 'message': 'Overlapping request exists'}), 400
    
    records = requests_sheet.get_all_records()

    for record in records:
        if str(record.get("RollNumber")) == roll_number and record.get("L/O") == "L":
            return jsonify({'success': False, 'message': 'You already have an active Single day outing request'}), 400

    last_request_id = int(records[-1]['RequestID']) if records else 0
    new_request_id = last_request_id + 1

    requests_sheet.append_row([
        new_request_id,
        roll_number,
        name,
        batch,
        #hostel_name,
        local_outstation,
        out_date,
        in_date,
        locality_area,
        city,
        state,
        reason,
        ph_number,
        alt_ph_number,
        documents,
        status,
        out_time,
        in_time
    ])

    return jsonify({'success': True, 'message': 'Request submitted successfully', 'RequestID': new_request_id}), 200

@app.route('/new_request_outstation', methods=['POST'])
@limiter.limit("10 per minute")
def new_request_outstation():
    data = request.get_json()

    roll_number = data.get('RollNumber')

    verification_response = verify_request_signature(roll_number)
    if verification_response:
        return verification_response 
    
    name = data.get('Name')
    batch = data.get('Batch')
    #hostel_name = data.get('HostelName')
    local_outstation = data.get('L/O')
    out_date = data.get('OutDate')
    in_date = data.get('InDate')
    locality_area = data.get('Locality/Area')
    city = data.get('City')
    state = data.get('State')
    reason = data.get('Reason')
    ph_number = data.get('Phone Number')
    alt_ph_number = data.get('Alt. Phone Number')
    documents = data.get('Documents')
    status = data.get('Status', "")
    out_time = data.get('OutTime', "")
    in_time = data.get('InTime', "")

    # if not roll_number or not name or not batch or not hostel_name or not out_date or not in_date or not locality_area or not city or not state or not reason or not ph_number:
    #     return jsonify({'success': False, 'message': 'Please fill in all required fields'}), 400

    required_fields = [roll_number, name, batch, out_date, in_date, locality_area, city, state, reason, ph_number, alt_ph_number]
    if not all(required_fields):
        return jsonify({'success': False, 'message': 'Please fill in all required fields'}), 400

    try:
        new_out_date = datetime.strptime(out_date, '%d/%m/%Y').date()
        new_in_date = datetime.strptime(in_date, '%d/%m/%Y').date()
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid date format. Use DD/MM/YYYY'}), 400

    if check_date_overlap(roll_number, new_out_date, new_in_date):
        return jsonify({'success': False, 'message': 'Overlapping request exists'}), 400
    
    records = requests_sheet.get_all_records()
    for record in records:
        if str(record.get("RollNumber")) == roll_number and record.get("L/O") == "O":
            return jsonify({'success': False, 'message': 'You already have an active Multiple days outing request'}), 400

    last_request_id = int(records[-1]['RequestID']) if records else 0
    new_request_id = last_request_id + 1

    requests_sheet.append_row([
        new_request_id,
        roll_number,
        name,
        batch,
        #hostel_name,
        local_outstation,
        out_date,
        in_date,
        locality_area,
        city,
        state,
        reason,
        ph_number,
        alt_ph_number,
        documents,
        status,
        out_time,
        in_time
    ])

    return jsonify({'success': True, 'message': 'Request submitted successfully', 'RequestID': new_request_id}), 200

@app.route('/delete_request/<int:request_id>', methods=['DELETE'])
@limiter.limit("5 per minute")
def delete_request(request_id):
    try:      
        records = requests_sheet.get_all_records()

        row_index = None
        for idx, record in enumerate(records):
            if record.get("RequestID") == request_id: 
                row_index = idx + 2
                roll_number = record.get("RollNumber")
                break

        if row_index is None:
            return jsonify({'success': False, 'message': 'Request ID not found'}), 404
        
        verification_response = verify_request_signature(roll_number)
        if verification_response:
            return verification_response 

        requests_sheet.delete_rows(row_index)

        return jsonify({'success': True, 'message': 'Request deleted successfully'}), 200
    except Exception as e:
        #print(f"Error deleting request: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while deleting the request'}), 500

@app.route('/update_in_date_multiple', methods=['POST'])
@limiter.limit("10 per minute")
def update_in_date():
    try:
        data = request.json
    
        request_id = data.get('request_id')
        new_in_date = data.get('in_date') 

        if not request_id  or not new_in_date:
            return jsonify({'error': 'Missing required fields'}), 400

        records = requests_sheet.get_all_records()
        row_idx = next(
            (i for i, rec in enumerate(records) 
             if (rec.get('RequestID', '')) == request_id), 
            None
        )

        if row_idx is None:
            return jsonify({'error': 'Request not found'}), 404
        
        roll_number = records[row_idx].get('RollNumber')

        verification_response = verify_request_signature(roll_number)
        if verification_response:
            return verification_response 

        in_date_col = 7
        requests_sheet.update_cell(row_idx + 2, in_date_col, new_in_date)  # Ensure correct row index

        return jsonify({'success': True, 'message': 'In Date updated successfully'})
    except Exception as e:
        #print(f"Error occurred: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/check_in_date_single', methods=['POST'])
@limiter.limit("10 per minute")
def check_in_date_single():
    try:
        data = request.get_json()

        roll_number = data.get('roll_number')
        # print(f"Received RollNumber: {roll_number}")

        verification_response = verify_request_signature(roll_number)
        if verification_response:
            return verification_response 

        if not roll_number:
            return jsonify({'success': False, 'message': 'RollNumber is missing'}), 400

        records = requests_sheet.get_all_records()
        #print(records)
        for record in records:
            if str(record.get("RollNumber")) == str(roll_number) and record.get("L/O") == "O":
                return jsonify({'success': False, 'message': 'You already have an active Multiple days outing request. Delete the Multiple days outing request and try again.'}), 400

        # If no active multiple days outing request is found, return success
        return jsonify({'success': True, 'message': 'No active multiple days outing request found'}), 200

    except Exception as e:
        #print(f"Error occurred: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/update_in_date_single', methods=['POST'])
@limiter.limit("10 per minute")
def update_request():
    try:
        data = request.json

        request_id = data.get('request_id')
        new_in_date_str = data.get('in_date')  # Ensure correct key
        locality_area = data.get('locality')
        city = data.get('city')
        state = data.get('state')
        reason = data.get('reason')
        phone_number = data.get('phone_number')
        alt_phone_number = data.get('alternate_phone')
        documents = data.get('documents')

        # print(request_id)
        # print(new_in_date_str)

        required_fields = [request_id, new_in_date_str, locality_area, city, state, reason, phone_number, alt_phone_number]
        if not all(required_fields):
            return jsonify({'success': False, 'message': 'Please fill in all required fields'}), 400

        # Parse the date string to a datetime object
        try:
            new_in_date = datetime.strptime(new_in_date_str, '%d/%m/%Y')
        except ValueError:
            return jsonify({'error': 'Invalid date format. Expected dd/MM/yyyy'}), 400

        records = requests_sheet.get_all_records()
        row_idx = next(
            (i for i, rec in enumerate(records) 
             if (rec.get('RequestID', '')) == request_id), 
            None
        )

        if row_idx is None:
            return jsonify({'error': 'Request not found'}), 404
        
        # print(row_idx)
        
        roll_number = records[row_idx].get('RollNumber')
        # print(roll_number)

        verification_response = verify_request_signature(roll_number)
        if verification_response:
            return verification_response 

        # Define column indices based on your sheet structure
        status_col = 5
        in_date_col = 7
        locality_area_col = 8
        city_col = 9
        state_col = 10
        reason_col = 11
        phone_number_col = 12
        alt_phone_number_col = 13
        documents_col = 14

        # Update the cells
        requests_sheet.update_cell(row_idx + 2, status_col, "O")
        requests_sheet.update_cell(row_idx + 2, in_date_col, new_in_date_str)  # Use the string directly
        requests_sheet.update_cell(row_idx + 2, locality_area_col, locality_area)
        requests_sheet.update_cell(row_idx + 2, city_col, city)
        requests_sheet.update_cell(row_idx + 2, state_col, state)
        requests_sheet.update_cell(row_idx + 2, reason_col, reason)
        requests_sheet.update_cell(row_idx + 2, phone_number_col, phone_number)
        requests_sheet.update_cell(row_idx + 2, alt_phone_number_col, alt_phone_number)
        requests_sheet.update_cell(row_idx + 2, documents_col, documents)

        return jsonify({'success': True, 'message': 'Request updated successfully'})
    except Exception as e:
        # print(f"Error occurred: {e}")
        return jsonify({'error': 'Internal server error'}), 500

#GUARD
@app.route('/get_student', methods=['POST'])
def get_student():
    data = request.json
    roll_number = data.get('roll_number', '').strip().upper()
    #print(roll_number)
    
    # Convert 'O' to '0' in roll_number
    if 'O' in roll_number:
        roll_number = roll_number.replace('O', '0')
        #print(roll_number)
    
    records = requests_sheet.get_all_records()

    students = [
        rec for rec in records 
        if str(rec.get('RollNumber', '')).strip() == roll_number
        and str(rec.get('Status', '')).strip().upper() != 'DONE'
    ]
    #print(students)

    if not students:
        return jsonify({'error': 'Student not found or all requests are completed'}), 404

    if len(students) > 1:        
        def parse_date(date_str):
            try:
                return datetime.strptime(date_str, '%d/%m/%Y')
            except ValueError:
                return None

        students = sorted(
            students,
            key=lambda rec: parse_date(rec.get('OutDate', '')) or datetime.max
        )

    student = students[0]
    #print(student)

    is_local = student.get('L/O', '').strip().upper() == 'L'
    is_outstation = student.get('L/O', '').strip().upper() == 'O'

    response = {
        'request_id': student.get('RequestID',''),
        'name': student.get('Name', ''),
        'roll_number': roll_number,
        'L/O': student.get('L/O', ''),
        'status': student.get('Status', ''),
        'out_enabled': student.get('Status', '').strip().upper() == 'OUT',
        'in_enabled': student.get('Status', '').strip().upper() == 'IN',
    }

    if is_local:
        response.update({'location': 'Local'})
    elif is_outstation:
        response.update({
            'city': student.get('City', ''),
            'state': student.get('State', ''),
            'location': 'OutStation',
        })

    return jsonify(response)

@app.route('/update_status', methods=['POST'])
def update_status():
    data = request.json
    request_id = data.get('request_id')
    roll_number = data.get('roll_number')
    action = data.get('action', '').upper()
    
    # Convert 'O' to '0' in roll_number
    if roll_number:
        roll_number = roll_number.strip().upper().replace('O', '0')

    if not request_id or not roll_number or not action:
        return jsonify({'error': 'Missing required fields'}), 400

    records = requests_sheet.get_all_records()
    row_idx = next((i for i, rec in enumerate(records) 
                   if str(rec.get('RollNumber', '')).strip().upper() == roll_number 
                   and str(rec.get('RequestID', '')).strip() == request_id 
                   and str(rec.get('Status', '')).strip().upper() != 'DONE'), None)
    
    if row_idx is None:
        return jsonify({'error': 'Student not found'}), 404

    status_col = 15  
    out_time_col = 16 
    in_time_col = 17
    in_date_col = 7  

    current_time = datetime.now(tz)
    formatted_time = current_time.strftime("%Y-%m-%d %H:%M:%S")
    formatted_date = current_time.strftime("%d/%m/%Y")

    try: 
        if action == 'OUT':
            requests_sheet.update_cell(row_idx + 2, out_time_col, formatted_time)
            requests_sheet.update_cell(row_idx + 2, status_col, 'IN')
        elif action == 'IN':
            requests_sheet.update_cell(row_idx + 2, in_time_col, formatted_time)
            requests_sheet.update_cell(row_idx + 2, in_date_col, formatted_date)
            requests_sheet.update_cell(row_idx + 2, status_col, 'DONE')

            row_data = requests_sheet.row_values(row_idx + 2)
            done_sheet.append_row(row_data)

            requests_sheet.delete_rows(row_idx + 2)
        
        return jsonify({'success': True})
    except Exception as e:
        #print(f"Error occurred: {e}")
        return jsonify({'error': 'Internal server error'}), 500

#WARDEN
@app.route('/get_local', methods=['POST'])
def get_local():
    try:
        # Fetch all rows from the sheet
        records = requests_sheet.get_all_records()

        # Get the current date
        current_date = datetime.now().strftime('%d/%m/%Y')

        # Filter records where L/O = "L", InDate < current date, and InTime is blank
        filtered_requests = []
        for idx, record in enumerate(records):
            in_date = record.get('InDate', '').strip()
            in_time = record.get('InTime', '').strip()

            # Convert date format properly (skip invalid dates)
            try:
                in_date_obj = datetime.strptime(in_date, '%d/%m/%Y') if in_date else None
                current_date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            except ValueError:
                continue  # Skip rows with invalid date format

            if record.get('L/O') == 'L' and in_date_obj and in_date_obj < current_date_obj and not in_time:
                filtered_requests.append({
                    "RequestID": record['RequestID'],  # Row number (idx starts at 0, header is row 1)
                    "RollNumber": record['RollNumber'],
                    "Name": record['Name'],
                    "Batch": record['Batch'],
                    #"HostelName": record['HostelName'],
                    "L/O": record['L/O'],
                    "OutDate": record['OutDate'],
                    "InDate": record['InDate'],
                    "Phone Number":record['Phone Number'],
                    "OutTime":record['OutTime']

                })

        return jsonify({'requests': filtered_requests}), 200
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/get_outstation', methods=['POST'])
def get_outstation():
    try:
        # Fetch all rows from the sheet
        records = requests_sheet.get_all_records()

        # Get the current date
        current_date = datetime.now().strftime('%d/%m/%Y')

        # Filter records where L/O = "L", InDate < current date, and InTime is blank
        filtered_requests = []
        for idx, record in enumerate(records):
            in_date = record.get('InDate', '').strip()
            in_time = record.get('InTime', '').strip()

            # Convert date format properly (skip invalid dates)
            try:
                in_date_obj = datetime.strptime(in_date, '%d/%m/%Y') if in_date else None
                current_date_obj = datetime.strptime(current_date, '%d/%m/%Y')
            except ValueError:
                continue  # Skip rows with invalid date format

            if record.get('L/O') == 'O' and in_date_obj and in_date_obj < current_date_obj and not in_time:
                filtered_requests.append({
                    "RequestID": record['RequestID'],  # Row number (idx starts at 0, header is row 1)
                    "RollNumber": record['RollNumber'],
                    "Name": record['Name'],
                    "Batch": record['Batch'],
                    #"HostelName": record['HostelName'],
                    "L/O": record['L/O'],
                    "OutDate": record['OutDate'],
                    "InDate": record['InDate'],
                    "Locality/Area": record['Locality/Area'],
                    "City":record['City'],
                    "State":record['State'],
                    "Reason": record['Reason'],
                    "Phone Number":record['Phone Number'],
                    "Alt. Phone Number":record['Alt. Phone Number'],
                    "Documents":record['Documents'],
                    "OutTime":record['OutTime']
                })

        return jsonify({'requests': filtered_requests}), 200
    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500
    
@app.route('/get_rollnumberwise', methods=['POST'])
def get_rollnumberwise():
    try:
        # Parse JSON request data
        data = request.get_json()
        roll_number = data.get('rollNumber', '').strip().upper()
       # print(roll_number)

        if not roll_number:
            return jsonify({'error': 'Roll Number is required.'}), 400

        # Fetch all rows from the records_sheet
        records = login_sheet.get_all_records()
       #print(records)
        matched_record = next(
            (record for record in records if str(record.get('Roll Number (New Roll Number)')).strip().upper() == roll_number), None
        )

        #print(matched_record)

        if not matched_record:
            return jsonify({'error': 'No record found for the entered Roll Number in records_sheet.'}), 404

        # Extract personal details
        personal_details = {
            "RollNumber": matched_record.get('Roll Number (New Roll Number)', ''),
            "Name": matched_record.get('Full Name', ''),
            "Batch": matched_record.get('Batch', ''),
            #"HostelName": matched_record.get('Hostel Name', '')
        }


        # Fetch all rows from the request_sheet
        requests = done_sheet.get_all_records()
        filtered_requests = []

        # Filter and process L/O details
        for record in requests:
            if record.get('RollNumber') == roll_number:
                lo_type = record.get('L/O').strip()
                if lo_type == 'L':
                    filtered_requests.append({
                        "RequestID": record['RequestID'],
                        "L/O": lo_type,
                        "OutDate": record['OutDate'],
                        "InDate": record['InDate'],
                        "Phone Number": record.get('Phone Number', ''),
                        "OutTime": record.get('OutTime', ''),
                        "InTime": record.get('InTime', ''),
                        "Status": record.get('Status', '')
                    })
                elif lo_type == 'O':
                    filtered_requests.append({
                        "RequestID": record['RequestID'],
                        "L/O": lo_type,
                        "OutDate": record['OutDate'],
                        "InDate": record['InDate'],
                        "Locality/Area": record.get('Locality/Area', ''),
                        "City": record.get('City', ''),
                        "State": record.get('State', ''),
                        "Reason": record.get('Reason', ''),
                        "Phone Number": record.get('Phone Number', ''),
                        "Alt. Phone Number": record.get('Alt. Phone Number', ''),
                        "Documents": record.get('Documents', ''),
                        "OutTime": record.get('OutTime', ''),
                        "InTime": record.get('InTime', ''),
                        "Status": record.get('Status', '')
                    })

        # Combine personal details and requests
        response = {
            "personalDetails": personal_details,
            "requests": filtered_requests
        }

        return jsonify(response), 200

    except Exception as e:
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
