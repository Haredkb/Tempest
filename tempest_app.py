"""
Tempest 1D -- Streamlit Application
Estimates vertical subsurface hydraulic specific discharge from temperature time series
using an Extended Kalman Filter (EKF) + Rauch-Tung-Striebel (RTS) smoother.

Usage:
    streamlit run tempest_app.py

Inputs:
    1. Parameter CSV  -- same format as Input_Example_Tempest_MB.csv, or
       enter the parameter values directly in the app
    2. VTP data CSV   -- same format as IB1_FV01.csv
"""

# -- Auto-install missing packages from requirements_tempest_app.txt ----------
import importlib
import subprocess
import sys
import os
from pathlib import Path

_REQUIREMENTS_FILE = Path(__file__).parent / "requirements_tempest_app.txt"

_IMPORT_NAMES = {
    "filterpy":   "filterpy",
    "streamlit":  "streamlit",
    "pandas":     "pandas",
    "numpy":      "numpy",
    "matplotlib": "matplotlib",
    "scipy":      "scipy",
}

def _check_and_install():
    """
    Check each package in requirements_tempest_app.txt.
    Install any that are missing, one at a time so progress is visible.
    Returns True if any packages were installed (caller should re-exec).
    """
    if not _REQUIREMENTS_FILE.exists():
        print("[tempest_app] WARNING: requirements_tempest_app.txt not found -- skipping.",
              flush=True)
        return False

    missing = []
    for line in _REQUIREMENTS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pkg = line.split(">=")[0].split("==")[0].split("<=")[0].split("!=")[0].strip()
        mod = _IMPORT_NAMES.get(pkg.lower(), pkg.lower().replace("-", "_"))
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(line)

    if not missing:
        print("[tempest_app] All required packages present.", flush=True)
        return False

    print("\n[tempest_app] Missing packages: " + str(missing), flush=True)
    print("[tempest_app] Installing -- this may take a minute...", flush=True)

    # Upgrade pip first -- newer pip has much better pre-built wheel resolution
    print("[tempest_app]   upgrading pip...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "--quiet"],
        stdout=subprocess.DEVNULL,
    )

    any_failed = False
    for spec in missing:
        print("[tempest_app]   pip install " + spec + " ...", flush=True)
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install",
             "--prefer-binary", "--progress-bar", "on", spec],
        )
        if result.returncode == 0:
            print("[tempest_app]   " + spec + " installed OK", flush=True)
        else:
            print("[tempest_app]   " + spec + " FAILED (exit code "
                  + str(result.returncode) + ")", flush=True)
            print("[tempest_app]   TIP: run run_tempest.bat instead -- it tries", flush=True)
            print("[tempest_app]        conda first, which handles binary deps cleanly.", flush=True)
            any_failed = True
    print("[tempest_app] Installation complete.\n", flush=True)
    return not any_failed  # True = all installs succeeded, safe to re-exec


if _check_and_install():
    # Packages were just installed into this Python environment. Python's import
    # cache was built before they existed, so simply re-launch this same command
    # under the same interpreter -- the fresh process will find everything.
    print("[tempest_app] Restarting to load newly installed packages...", flush=True)
    os.execv(sys.executable, [sys.executable] + sys.argv)
# -- End auto-install ----------------------------------------------------------

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tempest1d import EKF, ModelProperties, run_EKF, run_RTS

st.set_page_config(
    page_title="Tempest 1D",
    page_icon="magic.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -- Helpers -------------------------------------------------------------------

def safe_float(val, default=None):
    try:
        f = float(val)
        return default if (f != f) else f
    except (TypeError, ValueError):
        return default


def parse_param_csv(df):
    row = df.iloc[0]
    params = {}
    params["station_str"] = str(row.iloc[1]).strip()
    params["tBC"]         = safe_float(row.iloc[3])
    params["bBC"]         = safe_float(row.iloc[4])
    params["obsD"]        = safe_float(row.iloc[5])
    params["Kt"]          = safe_float(row.iloc[6], 2.9288)
    params["Cwater"]      = safe_float(row.iloc[7], 4.18e6)
    params["Csat"]        = safe_float(row.iloc[10])
    vq_raw = row.iloc[11]
    params["vq_mday2"] = (
        None
        if str(vq_raw).strip().lower() in ("none", "nan", "")
        else safe_float(vq_raw)
    )
    return params


def default_params():
    return {
        "station_str": "IB1FV01_",
        "tBC": 0.01,
        "bBC": 0.11,
        "obsD": 0.07,
        "Kt": 2.9288,
        "Cwater": 4.18e6,
        "Csat": 3.5e6,
        "vq_mday2": None,
    }


def build_column_names(station_str, tBC, bBC, obs_depths):
    top = station_str + str(int(round(tBC * 100))) + "cm"
    bot = station_str + str(int(round(bBC * 100))) + "cm"
    mid = [station_str + str(int(round(d * 100))) + "cm" for d in obs_depths]
    return top, bot, mid


def run_model(vtp_df, station_str, tBC, bBC, obs_depths,
              Kt, Cwater, Csat, vq_mday2, n_depths=41, T_noise_std=0.042):
    spd = 60.0 * 60.0 * 24.0

    topStr, botStr, midStr = build_column_names(station_str, tBC, bBC, obs_depths)

    missing_cols = [c for c in [topStr, botStr] + midStr if c not in vtp_df.columns]
    if missing_cols:
        raise ValueError(
            "Column(s) not found in VTP data: " + str(missing_cols)
            + "\nAvailable: " + str(list(vtp_df.columns))
        )

    mp = ModelProperties(
        top_depth=tBC, bottom_depth=bBC, n_depths=n_depths,
        Kt=Kt, Cw=Cwater, Cs=Csat
    )
    i_top = np.where(mp.depths == mp.top_depth)[0][0]
    i_bot = np.where(mp.depths == mp.bottom_depth)[0][0]

    T_top_all      = vtp_df[topStr].to_numpy(dtype=float)
    T_bot_all      = vtp_df[botStr].to_numpy(dtype=float)
    measure_points = np.array(obs_depths, dtype=float)
    n_meas         = len(measure_points)
    meas_all       = vtp_df[midStr].to_numpy(dtype=float).T

    datetime_all = vtp_df["timestamp"]
    times_all    = (datetime_all - datetime_all.iloc[0]).dt.total_seconds().to_numpy()

    all_valid = ~vtp_df[[topStr, botStr] + midStr].isna().any(axis=1).to_numpy()
    if all_valid.sum() < 10:
        raise ValueError("Too few valid (non-NaN) rows to run the filter.")

    meas           = meas_all[:, all_valid]
    T_top          = T_top_all[all_valid]
    T_bot          = T_bot_all[all_valid]
    times          = times_all[all_valid]
    dt             = np.diff(times)
    datetime_valid = datetime_all.values[all_valid]

    T_initial = np.linspace(T_top[0], T_bot[0], mp.n_depths)
    x0   = np.r_[T_initial[(i_top + 1):i_bot], 0.0]
    Tbc0 = np.r_[T_top[0], T_bot[0]]
    nx   = len(x0)

    if (vq_mday2 is not None) and np.isfinite(float(vq_mday2)):
        vq = float(vq_mday2) / spd / spd
    else:
        vqs = np.logspace(-10, -20, 20)
        vq  = vqs[8]

    ekf = EKF(measure_points, dt[0], mp, interp=True, Tbc0=Tbc0)
    ekf.x = x0
    ekf.P = np.eye(nx) * 5.0 ** 2
    ekf.P[-1, -1] = (1.0 / spd) ** 2
    ekf.Q = np.eye(nx) * 1e-2 ** 2
    ekf.Q[-1, -1] = vq
    ekf.control_covariance = np.eye(2) * T_noise_std ** 2
    ekf.R = np.eye(n_meas) * T_noise_std ** 2
    Qc = ekf.Q / dt[0]

    x_ekf, y_ekf, P_ekf = run_EKF(
        ekf, meas, T_top, T_bot, dt=dt, Qc=Qc, return_full_P=True
    )
    q_ekf    = x_ekf[:, mp.nz] * spd
    P_q_ekf  = P_ekf[:, -1, -1]
    q_ekf_ci = np.sqrt(P_q_ekf) * spd * 1.96

    x_rts, y_rts, P_q_rts = run_RTS(
        ekf, x_ekf, P_ekf, meas, T_top, T_bot, dt=dt, Qc=Qc, return_full_P=False
    )
    q_rts    = x_rts[:, mp.nz] * spd
    q_rts_ci = np.sqrt(P_q_rts) * spd * 1.96

    if n_meas == 1:
        base = pd.DataFrame({
            "datetime":   datetime_valid,
            "ekf_q":      q_ekf,
            "ekf_q_95ci": q_ekf_ci,
            "rts_q":      q_rts,
            "rts_q_95ci": q_rts_ci,
            "obs_T":      meas[0],
            "ekf_T_res":  y_ekf[:, 0],
            "rts_T_res":  y_rts[:, 0],
            "pcov_md2":   vq * spd * spd,
        })
        base["ekf_T"] = base["ekf_T_res"] + base["obs_T"]
        base["rts_T"] = base["rts_T_res"] + base["obs_T"]
    else:
        base = pd.DataFrame({
            "datetime":   datetime_valid,
            "ekf_q":      q_ekf,
            "ekf_q_95ci": q_ekf_ci,
            "rts_q":      q_rts,
            "rts_q_95ci": q_rts_ci,
            "pcov_md2":   vq * spd * spd,
        })
        for i, depth in enumerate(obs_depths):
            tag = str(int(round(depth * 100))) + "cm"
            base["obs_T_"     + tag] = meas[i]
            base["ekf_T_res_" + tag] = y_ekf[:, i]
            base["rts_T_res_" + tag] = y_rts[:, i]
            base["ekf_T_"     + tag] = base["ekf_T_res_" + tag] + base["obs_T_" + tag]
            base["rts_T_"     + tag] = base["rts_T_res_" + tag] + base["obs_T_" + tag]

    base["datetime"] = pd.to_datetime(base["datetime"])
    base["day"]  = base["datetime"].dt.date
    base["hour"] = base["datetime"].dt.hour

    return base, vq, spd


# ==============================================================================
#  UI
# ==============================================================================

st.title("Tempest 1D -- Vertical Saturated Flux Estimator")
st.caption(
    "Vertical Temperature Profile (VTP) method  |  "
    "Extended Kalman Filter + Rauch-Tung-Striebel Smoother"
)
st.markdown("---")

param_mode = st.radio(
    "Parameter input mode",
    ["Upload parameter CSV", "Enter parameters directly"],
    horizontal=True,
)

col_up1, col_up2 = st.columns(2)

with col_up1:
    st.subheader("1 - Parameter file")
    st.markdown(
        "Upload a CSV matching **`Input_Example_Tempest_MB.csv`**  \n"
        "*(station ID, depths, thermal properties, process variance)*"
    )
    if param_mode == "Upload parameter CSV":
        param_file = st.file_uploader(
            "Parameter CSV", type="csv", key="param_upload",
            label_visibility="collapsed"
        )
    else:
        param_file = None
        st.info("Using editable values below instead of an uploaded parameter CSV.")

with col_up2:
    st.subheader("2 - VTP data file")
    st.markdown(
        "Upload a CSV matching **`IB1_FV01.csv`**  \n"
        "*(timestamp column + temperature columns named STATIONID_Xcm)*"
    )
    data_file = st.file_uploader(
        "VTP data CSV", type="csv", key="data_upload",
        label_visibility="collapsed"
    )

if not data_file:
    st.info("Upload the VTP data file above to continue.")
    st.stop()

params = default_params()
if param_mode == "Upload parameter CSV":
    if not param_file:
        st.info("Upload a parameter CSV, or switch to manual entry to continue without one.")
        st.stop()
    try:
        param_df_raw = pd.read_csv(param_file)
        params = parse_param_csv(param_df_raw)
    except Exception as exc:
        st.error("Could not parse parameter file: " + str(exc))
        st.stop()

try:
    vtp_df = pd.read_csv(data_file, parse_dates=["timestamp"])
except Exception:
    try:
        data_file.seek(0)
        vtp_df = pd.read_csv(data_file)
        vtp_df["timestamp"] = pd.to_datetime(vtp_df["timestamp"])
    except Exception as exc:
        st.error("Could not parse VTP data file: " + str(exc))
        st.stop()

st.markdown("---")
st.subheader("3 - Review parameters")
st.caption("Values parsed from your parameter file -- adjust as needed before running.")

with st.expander("Edit parameters", expanded=True):
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**Site configuration**")
        station_str = st.text_input(
            "Station ID prefix",
            value=params["station_str"],
            help="Must match column name prefix in VTP data, e.g. 'IB1FV01_'"
        )
        tBC = st.number_input(
            "Top boundary depth (m)",
            value=float(params["tBC"]) if params["tBC"] is not None else 0.01,
            min_value=0.0, max_value=10.0, step=0.01, format="%.3f",
        )
        bBC = st.number_input(
            "Bottom boundary depth (m)",
            value=float(params["bBC"]) if params["bBC"] is not None else 0.11,
            min_value=0.0, max_value=10.0, step=0.01, format="%.3f",
        )
        obsD_default = (
            params["obsD"] if params["obsD"] is not None
            else round((tBC + bBC) / 2, 3)
        )
        obsD_str = st.text_input(
            "Observation depth(s) (m), comma-separated",
            value=str(obsD_default),
        )

    with col2:
        st.markdown("**Thermal properties**")
        Kt = st.number_input(
            "Thermal conductivity Kt (W/m/C)",
            value=float(params["Kt"]) if params["Kt"] is not None else 2.9288,
            min_value=0.0, format="%.4f",
        )
        Cwater = st.number_input(
            "Cwater (J/m3/C)",
            value=float(params["Cwater"]) if params["Cwater"] is not None else 4.18e6,
            min_value=0.0, format="%.4e",
        )
        Csat = st.number_input(
            "Csat (J/m3/C)",
            value=float(params["Csat"]) if params["Csat"] is not None else 3.5e6,
            min_value=0.0, format="%.4e",
            help="Bulk heat capacity of saturated sediment.",
        )

    with col3:
        st.markdown("**Filter settings**")
        vq_raw = params["vq_mday2"]
        vq_manual = st.checkbox(
            "Specify process variance manually",
            value=(vq_raw is not None),
        )
        if vq_manual:
            vq_mday2 = st.number_input(
                "vq (m/day^2)",
                value=float(vq_raw) if vq_raw is not None else 1e-5,
                min_value=0.0, format="%.2e",
            )
        else:
            vq_mday2 = None
            st.caption("Auto: vqs[8] from np.logspace(-10, -20, 20)")

        T_noise_std = st.number_input(
            "Temperature sensor noise std (C)",
            value=0.042, min_value=0.0, format="%.4f",
        )
        n_depths = st.slider(
            "Model grid nodes", min_value=21, max_value=101, value=41, step=10,
        )

try:
    obs_depths = [float(x.strip()) for x in obsD_str.split(",") if x.strip()]
    assert len(obs_depths) >= 1
except Exception:
    st.error("Could not parse observation depths. Enter one or more values separated by commas.")
    st.stop()

if tBC >= bBC:
    st.error("Top boundary depth must be less than bottom boundary depth.")
    st.stop()

bad_obs = [d for d in obs_depths if not (tBC < d < bBC)]
if bad_obs:
    st.error(
        "Observation depth(s) " + str(bad_obs)
        + " must lie strictly between "
        + str(tBC) + " m and " + str(bBC) + " m."
    )
    st.stop()

with st.expander("Preview VTP data", expanded=False):
    st.dataframe(vtp_df.head(10), use_container_width=True)
    st.caption(
        "{:,} rows  |  {} columns  |  {} to {}".format(
            len(vtp_df), len(vtp_df.columns),
            vtp_df["timestamp"].min(), vtp_df["timestamp"].max(),
        )
    )

topStr, botStr, midStr = build_column_names(station_str, tBC, bBC, obs_depths)
missing_cols = [c for c in [topStr, botStr] + midStr if c not in vtp_df.columns]
if missing_cols:
    st.warning(
        "Expected column(s) not found: " + str(missing_cols)
        + "  \nAvailable: " + str(list(vtp_df.columns))
    )

st.markdown("---")
st.subheader("4 - Run model")

run_btn = st.button(
    "Run EKF + RTS Smoother",
    type="primary",
    disabled=bool(missing_cols)
)

if run_btn:
    with st.spinner("Running Extended Kalman Filter and RTS Smoother..."):
        try:
            filtered, vq_used, spd = run_model(
                vtp_df=vtp_df,
                station_str=station_str,
                tBC=tBC, bBC=bBC,
                obs_depths=obs_depths,
                Kt=Kt, Cwater=Cwater, Csat=Csat,
                vq_mday2=vq_mday2,
                n_depths=n_depths,
                T_noise_std=T_noise_std,
            )
            st.session_state["filtered"]    = filtered
            st.session_state["vq_used"]     = vq_used
            st.session_state["spd"]         = spd
            st.session_state["obs_depths"]  = obs_depths
            st.session_state["station_str"] = station_str
        except Exception as exc:
            st.error("Model run failed: " + str(exc))
            import traceback
            with st.expander("Traceback"):
                st.code(traceback.format_exc())

if "filtered" in st.session_state:
    filtered    = st.session_state["filtered"]
    vq_used     = st.session_state["vq_used"]
    spd         = st.session_state["spd"]
    obs_depths  = st.session_state["obs_depths"]
    station_str = st.session_state["station_str"]
    n_meas      = len(obs_depths)

    st.success("Model run complete.")
    st.markdown("---")
    st.subheader("5 - Results")

    first_day     = filtered["day"].min()
    filtered_plot = filtered[filtered["day"] != first_day].copy()

    ekf_stats = filtered_plot.groupby("day")["ekf_q"].describe().reset_index()
    rts_stats = filtered_plot.groupby("day")["rts_q"].describe().reset_index()

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("EKF median daily mean", "{:.4f} m/day".format(np.median(ekf_stats["mean"])))
    m2.metric("RTS median daily mean", "{:.4f} m/day".format(np.median(rts_stats["mean"])))
    m3.metric("Process variance vq",   "{:.3e} m/day^2".format(vq_used * spd * spd))
    m4.metric("Valid timesteps",       "{:,}".format(len(filtered)))

    st.markdown("#### Estimated vertical specific discharge")
    fig1, ax1 = plt.subplots(figsize=(14, 4))
    ax1.plot(filtered_plot["datetime"], filtered_plot["ekf_q"],
             linewidth=1.5, color="#1f77b4", label="EKF", zorder=3)
    ax1.plot(filtered_plot["datetime"], filtered_plot["rts_q"],
             linewidth=1.5, color="#ff7f0e", label="RTS", linestyle="--", zorder=3)
    ax1.axhline(0, color="k", linewidth=0.7, linestyle=":", alpha=0.5)
    ax1.set_ylabel("Specific Discharge (m/day)", fontsize=12)
    ax1.tick_params(axis="x", rotation=45, labelsize=10)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax1.legend(frameon=False, fontsize=11)
    ekf_med = np.median(ekf_stats["mean"])
    rts_med = np.median(rts_stats["mean"])
    ax1.annotate("EKF mean: {:.3f} m/day".format(ekf_med),
                 xy=(0.01, 0.93), xycoords="axes fraction",
                 color="#1f77b4", fontsize=10)
    ax1.annotate("RTS mean: {:.3f} m/day".format(rts_med),
                 xy=(0.01, 0.84), xycoords="axes fraction",
                 color="#ff7f0e", fontsize=10)
    fig1.tight_layout()
    st.pyplot(fig1, use_container_width=True)

    st.markdown("#### Observed vs modelled temperature")

    if n_meas == 1:
        fig2, ax2 = plt.subplots(figsize=(6, 6))
        ax2.scatter(filtered_plot["obs_T"], filtered_plot["ekf_T"],
                    color="#1f77b4", alpha=0.4, s=15, edgecolors="none", label="EKF")
        ax2.scatter(filtered_plot["obs_T"], filtered_plot["rts_T"],
                    color="#ff7f0e", alpha=0.4, s=15, edgecolors="none", label="RTS")
        lo = min(filtered_plot[["obs_T", "ekf_T", "rts_T"]].min())
        hi = max(filtered_plot[["obs_T", "ekf_T", "rts_T"]].max())
        ax2.plot([lo, hi], [lo, hi], "k--", linewidth=1.5, label="1:1")
        ax2.set_xlabel("Observed Temp (C)", fontsize=12)
        ax2.set_ylabel("Modelled Temp (C)", fontsize=12)
        ax2.legend(frameon=False, fontsize=11)
        fig2.tight_layout()
        col_sc, _ = st.columns([1, 1])
        col_sc.pyplot(fig2)
    else:
        fig2, axes = plt.subplots(1, n_meas, figsize=(5 * n_meas, 5), squeeze=False)
        for i, depth in enumerate(obs_depths):
            tag     = str(int(round(depth * 100))) + "cm"
            ax      = axes[0][i]
            obs_col = filtered_plot["obs_T_" + tag]
            et_col  = filtered_plot["ekf_T_" + tag]
            rt_col  = filtered_plot["rts_T_" + tag]
            ax.scatter(obs_col, et_col, color="#1f77b4", alpha=0.4,
                       s=12, edgecolors="none", label="EKF")
            ax.scatter(obs_col, rt_col, color="#ff7f0e", alpha=0.4,
                       s=12, edgecolors="none", label="RTS")
            lo = min(obs_col.min(), et_col.min(), rt_col.min())
            hi = max(obs_col.max(), et_col.max(), rt_col.max())
            ax.plot([lo, hi], [lo, hi], "k--", linewidth=1.2)
            ax.set_title("Depth: " + tag, fontsize=11)
            ax.set_xlabel("Observed Temp (C)")
            ax.set_ylabel("Modelled Temp (C)")
            ax.legend(frameon=False, fontsize=9)
        fig2.tight_layout()
        st.pyplot(fig2, use_container_width=True)

    with st.expander("Daily summary statistics"):
        tab1, tab2 = st.tabs(["EKF", "RTS"])
        with tab1:
            st.dataframe(ekf_stats.round(4), use_container_width=True)
        with tab2:
            st.dataframe(rts_stats.round(4), use_container_width=True)

    with st.expander("Full results table"):
        st.dataframe(filtered.round(4), use_container_width=True)

    st.markdown("---")
    st.subheader("6 - Download")

    first_ts   = pd.Timestamp(filtered["datetime"].min())
    fname_stem = station_str + first_ts.strftime("%Y%m%d")

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download results CSV",
        data=csv_bytes,
        file_name=fname_stem + "_tempest_results.csv",
        mime="text/csv",
    )

    buf = io.BytesIO()
    fig1.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    st.download_button(
        label="Download discharge plot (PNG)",
        data=buf,
        file_name=fname_stem + "_discharge.png",
        mime="image/png",
    )
