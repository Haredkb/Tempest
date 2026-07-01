# Tempest VTP Streamlit App

Streamlit app for running Tempest 1D on a VTP data CSV plus either an uploaded parameter CSV or manual parameter entry.

## Run Locally

From the project root:

```powershell
streamlit run tempest_app.py
```

If you want to force the configured conda Python explicitly:

```powershell
C:/Users/dhare/AppData/Local/anaconda3/python.exe -m streamlit run tempest_app.py
```

## Files

- `tempest_app.py` - main Streamlit UI and solver entry point
- `tempest1d.py` - Tempest 1D model and EKF/RTS implementation
- `Input_Example_Tempest*.csv` - example parameter files
- `IB1_FV01.csv` - example VTP data file

## Notes

- The app expects a timestamp column in the VTP CSV.
- Temperature columns should match the station prefix and depth naming used by the parameter input.
- Generated folders such as `__pycache__`, `.ipynb_checkpoints`, and local IDE settings are ignored by git.