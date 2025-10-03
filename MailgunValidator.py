import argparse
import requests
import time
import csv
import io
import zipfile
import random
import string
from datetime import datetime

# Replace with your actual Mailgun API key
API_KEY = "your-mailgun-api-key-here"

def submit_bulk_validation(emails_list, list_name):
    url = f"https://api.mailgun.net/v4/address/validate/bulk/{list_name}"
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(['email'])
    writer.writerows([[email] for email in emails_list])
    csv_buffer.seek(0)
    files = {'file': ('emails.csv', csv_buffer, 'text/csv')}
    response = requests.post(url, auth=("api", API_KEY), files=files, timeout=30)
    return response

def get_bulk_status(list_name):
    url = f"https://api.mailgun.net/v4/address/validate/bulk/{list_name}"
    response = requests.get(url, auth=("api", API_KEY), timeout=30)
    return response

def download_results(download_url):
    response = requests.get(download_url, timeout=30)
    if response.status_code == 200:
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            file_list = z.namelist()
            for file in file_list:
                if file.endswith('.json'):
                    with z.open(file) as f:
                        results = json.load(f)
                    return results, 'json'
                elif file.endswith('.csv'):
                    with z.open(file) as f:
                        csv_content = f.read().decode('utf-8')
                        csv_reader = csv.DictReader(io.StringIO(csv_content))
                        results = list(csv_reader)
                    return results, 'csv'
    return None, None

def process_emails(input_file, output_file):
    with open(input_file, 'r') as f:
        lines = f.readlines()

    emails_list = [line.strip() for line in lines if line.strip()]
    if not emails_list:
        print("No emails found in input file.")
        return

    print("Creating CSV from input file...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    list_name = f"validation_{timestamp}_{random_str}"

    print(f"Uploading file to Mailgun API...")
    submit_resp = submit_bulk_validation(emails_list, list_name)
    if submit_resp.status_code != 202:
        print(f"Error uploading file: {submit_resp.status_code}")
        return

    print(f"Job submitted successfully ({list_name}).")
    print("Waiting for validation to complete... (This may take a few minutes depending on list size)")

    start_time = time.time()
    timeout = 300
    results = None
    file_type = None
    while True:
        elapsed = int(time.time() - start_time)
        time.sleep(5)
        status_resp = get_bulk_status(list_name)
        if status_resp.status_code == 200:
            data = status_resp.json()
            status = data.get('status', 'unknown').lower()
            print(f"Processing... (Elapsed: {elapsed // 60}m {elapsed % 60}s)")
            download_url = data.get('download_url', {}).get('csv') or data.get('download_url', {}).get('json')
            if download_url:
                print("Download complete. Processing results...")
                results, file_type = download_results(download_url)
                if results:
                    break
                else:
                    print("Failed to process results.")
                    return
            elif status == 'failed':
                print(f"Job failed: {data.get('error', 'Unknown error')}")
                return
        else:
            print(f"Error checking status: {status_resp.status_code}")
            return
        if time.time() - start_time > timeout:
            print("Job timed out after 5 minutes. Check Mailgun dashboard.")
            return

    print("Extracting valid emails...")
    valid_emails = set()
    valid_count = 0
    invalid_count = 0
    low_risk = 0
    medium_risk = 0
    high_risk = 0
    error_count = 0

    for result in results:
        email = result.get('address') or result.get('email', '')
        if not email:
            continue
        val_result = result
        if file_type == 'csv':
            result_value = val_result.get('result', val_result.get('Result', '')).lower()
        else:
            result_value = val_result.get('result', '').lower()
        if 'error' in val_result:
            error_count += 1
        elif result_value == 'deliverable':
            valid_emails.add(email)
            valid_count += 1
            risk = val_result.get('risk', 'low').lower()
            if risk == 'low':
                low_risk += 1
            elif risk == 'medium':
                medium_risk += 1
            else:
                high_risk += 1
        else:
            invalid_count += 1

    with open(output_file, 'w') as f:
        for email in sorted(valid_emails):
            f.write(f"{email}\n")

    total = len(emails_list)
    print("\n" + "="*50)
    print("VALIDATION SUMMARY")
    print("="*50)
    print(f"Total emails processed: {total}")
    print(f"Deliverable emails: {valid_count} ({valid_count/total*100:.1f}%)")
    print(f"  - Low risk: {low_risk}")
    print(f"  - Medium risk: {medium_risk}")
    print(f"  - High risk: {high_risk}")
    print(f"Undeliverable emails: {invalid_count} ({invalid_count/total*100:.1f}%)")
    print(f"Errors: {error_count} ({error_count/total*100:.1f}%)")
    print(f"Low risk / validated emails saved to: {output_file}")
    print("="*50)

def main():
    parser = argparse.ArgumentParser(description="Validate emails using Mailgun Bulk API")
    parser.add_argument("-t", "--input-file", required=True, help="Input file containing emails (one per line)")
    parser.add_argument("-o", "--output-file", default="validated-emails.txt", help="Output file for valid emails")
    args = parser.parse_args()
    if API_KEY == "your-mailgun-api-key-here":
        print("Error: Update the API_KEY in the script with your Mailgun API key.")
        return
    print("Mailgun Bulk Email Validation Tool")
    print("-" * 40)
    process_emails(args.input_file, args.output_file)

if __name__ == "__main__":
    main()
