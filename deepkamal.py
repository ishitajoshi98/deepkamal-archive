# import pickle
import json
import numpy as np
from PIL import Image
import base64
import os
import streamlit as st
import pandas as pd
import tempfile
import cloudconvert
import shutil
import io
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from google.oauth2.service_account import Credentials
from google.oauth2 import service_account
from streamlit_gsheets import GSheetsConnection
from shillelagh.backends.apsw.db import connect
import ast


if 'updates' not in st.session_state:
    st.session_state.updates = {}

#@st.cache, @st.cache_data, and @st.cache_resource
def clear_cache():
    keys = list(st.session_state.keys())
    for key in keys:
        st.session_state.pop(key)

st.sidebar.button('Clear Cache', on_click=clear_cache)

 # service account email = deepkamal@bdmproject-416408.iam.gserviceaccount.com
 # service account name = deepkamal

# Define the standardized columns and mandatory columns
all_std_columns = ['Item', 'Opening stock quantity', 'Opening stock amount', 'Purchase quantity', 'Purchase amount',
                   'Purchase return quantity', 'Purchase return amount', 'Sales quantity', 'Sales amount',
                   'Sales return quantity', 'Sales return amount', 'Closing stock quantity', 'Closing stock amount',
                   'Rate', 'Expiry Stock']
necessary_columns = ['Item', 'Opening stock quantity', 'Purchase quantity', 'Sales quantity', 'Closing stock quantity']
std_options = ['Ignore this column'] + all_std_columns

# Sidebar function selection
st.sidebar.title("DeepKamal Health Services")
choose_option = st.sidebar.selectbox("Choose a function",
                                     ('Select...', 'Convert to standard excel format', 'Generate report'))



 # service account email = deepkamal@bdmproject-416408.iam.gserviceaccount.com
 # service account name = deepkamal
########################### CODE BEGINS #########################################################
def modify_image_opacity(image_path, output_path, opacity=25):
    # Open the existing image
    img = Image.open(image_path).convert("RGBA")

    # Extract the alpha channel
    r, g, b, alpha = img.split()

    # Modify the alpha channel
    alpha = alpha.point(lambda p: p * opacity / 100)

    # Merge the channels back
    img.putalpha(alpha)

    # Save the modified image
    img.save(output_path)


modify_image_opacity("logo.jpeg", "logo_light.png", opacity=100)  # Adjust opacity as needed

def add_logo_to_corner():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{get_base64_of_file("logo_light.png")}");
            background-position: right 30px;
            background-repeat: no-repeat;
            background-size: 300px 100px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

def get_base64_of_file(path):
    with open(path, "rb") as f:
        data = f.read()
    import base64
    return base64.b64encode(data).decode()

add_logo_to_corner()

# SHEET_URL = 'https://docs.google.com/spreadsheets/d/1w62vve3epSiBc_60bjYPpviKLkCvk3MsVRWzPRG33Ac/edit?usp=sharing'

SHEET_URL = st.secrets["gsheets"]["url"]

def get_connection():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gsheets"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return connect(":memory:", adapter_kwargs={
        "gsheetsapi": {
            "service_account_info": {
                "type": st.secrets["gsheets"]["type"],
                "project_id": st.secrets["gsheets"]["project_id"],
                "private_key_id": st.secrets["gsheets"]["private_key_id"],
                "private_key": st.secrets["gsheets"]["private_key"],
                "client_email": st.secrets["gsheets"]["client_email"],
                "client_id": st.secrets["gsheets"]["client_id"],
                "auth_uri": st.secrets["gsheets"]["auth_uri"],
                "token_uri": st.secrets["gsheets"]["token_uri"],
                "auth_provider_x509_cert_url": st.secrets["gsheets"]["auth_provider_x509_cert_url"],
                "client_x509_cert_url": st.secrets["gsheets"]["client_x509_cert_url"],
            }
        },
    })


def get_table_download_link(df, file_name):
    output = io.BytesIO()
    df.to_excel(output, index=False, engine="xlsxwriter")
    excel_data = output.getvalue()
    b64 = base64.b64encode(excel_data).decode()
    new_file_name = os.path.splitext(file_name)[0].replace(" ", "_") + "_STD.xlsx"
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{new_file_name}">Download Excel file</a>'
    return href


# Function to load standard names from Google Sheets
def load_standard_names():
    conn = get_connection()
    query = f'SELECT * FROM "{SHEET_URL}"'
    df = pd.read_sql(query, conn)
    return df


def update_standard_names(updates):
    conn = get_connection()
    cursor = conn.cursor()
    for item, standard_name in updates.items():
        if item not in load_standard_names()['Alternate Name'].values:
            if standard_name != 'No match found':
                cursor.execute(f'INSERT INTO "{SHEET_URL}" ("Alternate Name", "Standard Name") VALUES (?, ?)',
                       (item, standard_name))
    conn.commit()



# Create a reverse dictionary from the dataframe
def create_reverse_dict(df):
    return dict(zip(df['Alternate Name'], df['Standard Name']))


# Standardize function with optional comparison to previous month
def standardize_column_names(df, std_columns, necessary_columns, reverse_standard_name_dict, comparison_df=None):
    renamed_cols = {}
    for col in df.columns:
        key = f"select_{col}"
        if key not in st.session_state:
            st.session_state[key] = 'Ignore this column'
        renamed_cols[col] = st.selectbox(col, std_columns, index=std_columns.index(st.session_state[key]), key=key)

    std_columns_selected = list(renamed_cols.values())
    duplicates = [col for col in set(std_columns_selected) if std_columns_selected.count(col) > 1 and col != 'Ignore this column']
    missing_cols = [col for col in necessary_columns if col not in renamed_cols.values()]
    errors = False

    if duplicates:
        st.error(f'Duplicate column assignments: {", ".join(duplicates)}')
        errors = True
        # return None

    if missing_cols:
        st.error(f'Missing mandatory columns: {", ".join(missing_cols)}')
        errors = True
        # return None

    if errors:
        return None


    drop_cols = [col for col, std in renamed_cols.items() if std == 'Ignore this column']
    df.drop(columns=drop_cols, inplace=True)
    df.rename(columns=renamed_cols, inplace=True)

    for col in std_columns:
        if col not in df.columns:
            df[col] = 0

    df['Closing balance check'] = np.where(
        (df['Opening stock quantity'] +
         df['Purchase quantity'] -
         df['Purchase return quantity'] -
         df['Sales quantity'] +
         df['Sales return quantity']) == df['Closing stock quantity'],
        'Ok',
        'Mismatch'
    )


    if comparison_df is not None:
        df = df[all_std_columns + ['Closing balance check']]

        merged = pd.merge(df, comparison_df[['Item', 'Closing stock quantity']],
                          on='Item', how='left', suffixes=('_curr', '_prev'))
        merged.rename(columns={'Closing stock quantity_curr': 'Closing stock quantity',
                               'Closing stock quantity_prev': 'Previous month closing stock'}, inplace=True)
        merged['Stock Difference (Previous CS - Current OS)'] = merged['Previous month closing stock'] - merged[
            'Opening stock quantity']
        merged['Previous month closing stock'].fillna('Previous month record not found', inplace=True)
        merged['Stock Difference (Previous CS - Current OS)'].fillna('Not applicable', inplace=True)
        return merged

    return df[all_std_columns + ['Closing balance check']]

def standardize_medicine_name(df, reverse_standard_name_dict):
    df['Std medicine names'] = df['Item'].map(reverse_standard_name_dict).fillna('No match found')

    no_match_items = df[df['Std medicine names'] == 'No match found']['Item'].unique()
    updates = st.session_state.get('updates', {})  #####new
    update_no_match_found = {} #$
    for item in no_match_items:
        selected_name = st.selectbox(f"Select standard name for '{item}'",
                                     ['No match found'] + sorted(list(set(reverse_standard_name_dict.values()))),
                                     key=f"select_{item}")
        updates[item] = selected_name

        if selected_name != 'No match found':
            # updates[item] = selected_name  ####new
            update_no_match_found[item] = selected_name
    df.loc[df['Std medicine names'] == 'No match found', 'Std medicine names'] = df['Item'].map(update_no_match_found)
    updated_updates ={}
    for k, v in updates.items():
        if v != 'No match found':
            updated_updates[k] = v
    st.session_state.updates = updated_updates  ######## new
    return df[['Std medicine names'] + all_std_columns + ['Closing balance check']]




# Convert to standard format option
if choose_option == 'Convert to standard excel format':
    st.title("Convert to Standard Excel Format")
    uploaded_file = st.sidebar.file_uploader("Upload current month's file", type=["xlsx"])

    if uploaded_file:
        current_data = pd.read_excel(uploaded_file)
        st.text('Note: Clear cache before uploading a new file')
        st.text(
            "These columns are mandatory:\n1. Item\n2. Opening stock quantity\n3. Purchase quantity\n4. Sales quantity\n5. Closing stock quantity")

        # Load standard names from Google Sheets
        standard_names_df = load_standard_names()
        reverse_standard_name_dict = create_reverse_dict(standard_names_df)

        # Initialize session state for step management
        if 'step' not in st.session_state:
            st.session_state.step = 'select_columns'

        # Step 1: Select and rename columns
        with st.expander("Step 1: Select Standard Column Names", expanded=st.session_state.step == 'select_columns'):
            standardized_data = standardize_column_names(current_data, std_options, necessary_columns,
                                                               reverse_standard_name_dict)
            if standardized_data is not None and st.button("Next"):
                st.session_state.step = 'standardize_medicine_name'
                st.session_state.standardized_data = standardized_data
                st.experimental_rerun()

        # Step 2: Standardize medicine names
        if st.session_state.step == 'standardize_medicine_name':
            standardized_data = st.session_state.standardized_data
            with st.expander("Step 2: Standardize Medicine Names", expanded=True):
                standardized_data = standardize_medicine_name(standardized_data, reverse_standard_name_dict)
                for item, selected_name in st.session_state.updates.items():  ####new
                    st.write(f"{item} will be renamed as: {selected_name}")
                    # st.session_state.standardized_data = standardized_data
                if st.button("Submit"):
                    update_standard_names(st.session_state.updates)####new
                    st.success("Standard names updated successfully!")####new
                    st.write(standardized_data)
                    st.markdown(get_table_download_link(standardized_data, uploaded_file.name), unsafe_allow_html=True)


# Generate report option
elif choose_option == 'Generate report':
    st.title("Generate Report")
    current_file = st.sidebar.file_uploader("Upload current month's file", type=["xlsx"])
    previous_month_file = st.sidebar.file_uploader("Upload previous month's file", type=["xlsx"])

    if current_file and previous_month_file:
        current_data = pd.read_excel(current_file)
        previous_data = pd.read_excel(previous_month_file)
        st.text('Note: Clear cache before uploading a new file')
        st.text(
            "These columns are mandatory:\n1. Item\n2. Opening stock quantity\n3. Purchase quantity\n4. Sales quantity\n5. Closing stock quantity")

        # Load standard names from Google Sheets
        standard_names_df = load_standard_names()
        reverse_standard_name_dict = create_reverse_dict(standard_names_df)

        # Initialize session state for step management
        if 'step' not in st.session_state:
            st.session_state.step = 'select_columns'

        # Step 1: Select and rename columns
        with st.expander("Step 1: Select Standard Column Names", expanded=st.session_state.step == 'select_columns'):
            standardized_data = standardize_column_names(current_data, std_options, necessary_columns,
                                                               reverse_standard_name_dict)
            if standardized_data is not None and st.button("Next"):
                st.session_state.step = 'standardize_medicine_name'
                st.session_state.standardized_data = standardized_data
                st.experimental_rerun()

        # Step 2: Standardize medicine names
        if st.session_state.step == 'standardize_medicine_name':
            standardized_data = st.session_state.standardized_data
            with st.expander("Step 2: Standardize Medicine Names", expanded=True):
                standardized_data = standardize_medicine_name(standardized_data, reverse_standard_name_dict)
                for item, selected_name in st.session_state.updates.items():  ####new
                    st.write(f"{item} will be renamed as: {selected_name}")
                    # st.session_state.standardized_data = standardized_data
                if st.button("Submit"):
                    update_standard_names(st.session_state.updates)####new
                    st.success("Standard names updated successfully!")####new
                    merged = pd.merge(standardized_data, previous_data[['Item', 'Closing stock quantity']],
                                      on='Item', how='left', suffixes=('_curr', '_prev'))
                    merged.rename(columns={'Closing stock quantity_curr': 'Closing stock quantity',
                                           'Closing stock quantity_prev': 'Previous month closing stock'}, inplace=True)
                    merged['Stock Difference (Previous CS - Current OS)'] = merged['Previous month closing stock'] - \
                                                                            merged[
                                                                                'Opening stock quantity']
                    merged['Previous month closing stock'].fillna('Previous month record not found', inplace=True)
                    merged['Stock Difference (Previous CS - Current OS)'].fillna('Not applicable', inplace=True)

                    st.write(merged)
                    st.markdown(get_table_download_link(merged, current_file.name), unsafe_allow_html=True)


# Default selection screen
else:
    # st.title("Welcome to DeepKamal Health Services")
    st.write("Please select a function from the sidebar to get started.")


