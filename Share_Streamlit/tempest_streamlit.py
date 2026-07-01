import streamlit as st
import pandas as pd
import os
import tempfile

# Assuming you have refactored Tempest_workflow.ipynb into a callable function
# in a file named 'tempest_workflow_core.py' in the same directory.
# You might need to adjust the import path if your file structure is different.
# from tempest_workflow_core import run_tempest_workflow

# Placeholder for the workflow function until you create tempest_workflow_core.py
def run_tempest_workflow(input_example_path, data_file_path):
    st.warning("Placeholder: You need to implement 'run_tempest_workflow' in 'tempest_workflow_core.py'")
    st.write(f"Would run workflow with: {input_example_path} and {data_file_path}")
    
    # Simulate loading and returning some data
    try:
        input_df = pd.read_csv(input_example_path)
        data_df = pd.read_csv(data_file_path)
        st.write("Simulating workflow results based on uploaded data.")
        return {"status": "Simulated workflow completion.", "processed_dataframe": data_df.head(), "example_input_df": input_df}
    except Exception as e:
        return {"status": f"Simulated workflow error: {e}", "processed_dataframe": None, "example_input_df": None}


st.set_page_config(page_title="Tempest Workflow GUI", layout="centered")
st.title("🌊 Tempest Workflow Application")

st.markdown("--- ")

st.subheader("1. Upload Input Configuration File")
input_example_file = st.file_uploader("Upload `Input_Example_Tempest.csv` (contains workflow parameters)", type=["csv"], key="input_example_uploader")

st.subheader("2. Upload Main Data File")
data_file = st.file_uploader("Upload your main data file (e.g., `IB1_FV01.csv`)", type=["csv"], key="data_uploader")

st.markdown("--- ")

# Create a temporary directory to store uploaded files and the modified input CSV
# This ensures the files are accessible to the workflow function
TEMP_DIR = tempfile.mkdtemp()

if input_example_file and data_file:
    st.success("Both files uploaded successfully! Proceed to run the workflow.")

    if st.button("Run Tempest Workflow", help="Click to execute the workflow with the uploaded files."):
        with st.spinner("Running workflow... This might take a moment."):
            # Save the uploaded Input_Example_Tempest.csv temporarily
            input_example_path = os.path.join(TEMP_DIR, "Input_Example_Tempest.csv")
            with open(input_example_path, "wb") as f:
                f.write(input_example_file.getvalue())
            
            # Save the uploaded data file temporarily
            data_file_name = data_file.name # Get original name
            data_file_path = os.path.join(TEMP_DIR, data_file_name)
            with open(data_file_path, "wb") as f:
                f.write(data_file.getvalue())

            # --- Modify Input_Example_Tempest.csv content --- 
            # Load the uploaded input_example_file as a DataFrame
            tempest_input_df = pd.read_csv(input_example_path)

            # Update the 'Input Data File Full Path' column to point to the uploaded data_file_name
            # This replaces the hardcoded path with the name of the file actually uploaded by the user
            if 'Input Data File Full Path' in tempest_input_df.columns:
                tempest_input_df['Input Data File Full Path'] = data_file_name
                tempest_input_df.to_csv(input_example_path, index=False) # Save the modified version
                st.info(f"Updated 'Input Data File Full Path' in `Input_Example_Tempest.csv` to `{data_file_name}`.")
            else:
                st.warning("Column 'Input Data File Full Path' not found in `Input_Example_Tempest.csv`. Workflow might not use the correct data file.")
            # --- End modification ---

            # Now, call the refactored workflow function with paths to the temporary files
            # Ensure run_tempest_workflow can handle these paths
            workflow_results = run_tempest_workflow(input_example_path, data_file_path)

            st.subheader("Workflow Results")
            st.write(workflow_results["status"])
            
            if workflow_results["processed_dataframe"] is not None:
                st.subheader("Processed Data (First 5 Rows)")
                st.dataframe(workflow_results["processed_dataframe"]) # Display as an interactive table

                # Optional: Provide a download button for the processed data
                @st.cache_data # Cache this function to prevent re-running on every interaction
                def convert_df_to_csv(df):
                    return df.to_csv(index=False).encode('utf-8')

                csv_output = convert_df_to_csv(workflow_results["processed_dataframe"])
                st.download_button(
                    label="Download Processed Data as CSV",
                    data=csv_output,
                    file_name="processed_tempest_data.csv",
                    mime="text/csv",
                )
            
            if workflow_results["example_input_df"] is not None:
                st.subheader("Input_Example_Tempest.csv (After Modification)")
                st.dataframe(workflow_results["example_input_df"])

else:
    st.info("Please upload both the configuration and data files to run the workflow.")