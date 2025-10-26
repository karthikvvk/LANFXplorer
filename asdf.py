import streamlit as st

st.title("📁 File Picker Example")

# File uploader widget
uploaded_file = st.file_uploader("Choose a file", type=["csv", "txt", "pdf", "jpg", "png"])

if uploaded_file is not None:
    st.success(f"✅ You uploaded: {uploaded_file.name}")
    
    # Example: read text file
    if uploaded_file.type == "text/plain":
        text = uploaded_file.read().decode("utf-8")
        st.text_area("File Content", text, height=200)
    
    # Example: display image
    elif uploaded_file.type.startswith("image/"):
        st.image(uploaded_file, caption=uploaded_file.name)
    
    # Example: show dataframe for CSV
    elif uploaded_file.name.endswith(".csv"):
        import pandas as pd
        df = pd.read_csv(uploaded_file)
        st.dataframe(df)





import streamlit as st
import tkinter as tk
from tkinter import filedialog
import os

# Initialize tkinter
root = tk.Tk()
root.withdraw()  # Hide the main tkinter window

def select_folder():
    """Open a folder selection dialog and return the selected path."""
    folder_path = filedialog.askdirectory()
    return folder_path

# Streamlit app
st.title("Folder Selection in Streamlit")

# Button to trigger folder selection
if st.button("Select Folder"):
    folder_path = select_folder()
    if folder_path:
        st.session_state['folder_path'] = folder_path  # Store in session state
        st.success(f"Selected folder: {folder_path}")
    else:
        st.warning("No folder selected.")

# Display folder contents if a folder is selected
if 'folder_path' in st.session_state and os.path.isdir(st.session_state['folder_path']):
    folder_path = st.session_state['folder_path']
    files = os.listdir(folder_path)
    st.write("Files in the folder:", files)

# Clean up tkinter
root.destroy()