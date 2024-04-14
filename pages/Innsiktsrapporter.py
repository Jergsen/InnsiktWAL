import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json
import io
from google.cloud import storage
import time
import datetime
from google.oauth2 import service_account
import streamlit.components.v1 as components

# Load the service account key as a string
service_account_key_string = st.secrets["textkey"]

# Parse the string to a Python dictionary
service_account_info = json.loads(service_account_key_string)

# Initialize Firebase Admin using the service account info
if not firebase_admin._apps:
    firebase_cred = credentials.Certificate(service_account_info)
    firebase_admin.initialize_app(firebase_cred)

# Initialize Firestore
db = firestore.client()

gcs_credentials = service_account.Credentials.from_service_account_info(service_account_info)

# Initialize Firebase Storage
storage_client = storage.Client(credentials=gcs_credentials)
bucket = storage_client.bucket('innsikt-887f3.appspot.com')

st.title('Innsiktsrapporter')

def upload_file_to_storage(file, file_name):
    blob = bucket.blob(file_name)
    blob.upload_from_file(file, content_type='application/pdf')
    blob.make_public()  # Make the file publicly accessible
    return blob.public_url

def add_report_to_firestore(title, author, file_url, date):
    doc_ref = db.collection('reports').document()
    doc_ref.set({
        'title': title,
        'author': author,
        'file_url': file_url,
        'date': date.isoformat()
    })

# File uploader
uploaded_file = st.file_uploader("Last opp innsiktsrapport", type=["pdf"])

if uploaded_file:
    file_name = f"reports/{uploaded_file.name}_{int(time.time())}.pdf"
    file_url = upload_file_to_storage(uploaded_file, file_name)
    add_report_to_firestore(uploaded_file.name, "Author Name", file_url, datetime.datetime.now())
    st.success('Rapporten er nå lastet opp :)')

def display_reports():
    reports = db.collection('reports').stream()
    for report in reports:
        report_data = report.to_dict()
        st.subheader(report_data.get('title', 'No Title'))

        # Embed the PDF if the URL is available
        pdf_url = report_data.get('file_url')
        if pdf_url:
            pdf_embed_code = f'<iframe src="{pdf_url}" width="700" height="500" style="border:none;"></iframe>'
            components.html(pdf_embed_code, height=500)

                # Fallback link
            st.markdown(f"Vises ikke rapporten? [Åpne i ny fane]({pdf_url})", unsafe_allow_html=True)



display_reports()
