#!/usr/bin/env python3
"""Reproduce the 5Guard base paper experiments.

Converts the logic from external/5guard/simulation.ipynb into a standalone,
reproducible Python script.  Runs all seven algorithms (OPT, IAR, DTR, RNR,
NIS, CIS, FGR) on the 5Guard synthetic topology (and optionally BRAIN),
collects the paper's full metric suite, generates publication-quality SVG
plots, and dumps a JSON summary.

Usage (from secguard/ project root):
    .venv_linux/bin/python scripts/reproduce_5guard.py              # synthetic
    .venv_linux/bin/python scripts/reproduce_5guard.py --brain      # BRAIN topo
    .venv_linux/bin/python scripts/reproduce_5guard.py --iters 2    # quick test
"""

from __future__ import annotations

import argparse
import concurrent.futures
from contextlib import redirect_stdout
import copy
import json
import math
import os
import pickle
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve 5Guard path so its modules can be imported
# ---------------------------------------------------------------------------
PROJECT_ROOT  = Path(__file__).resolve().parent.parent
FIVEGUARD_DIR = PROJECT_ROOT / "external" / "5guard"
if not FIVEGUARD_DIR.exists():
    sys.exit(f"5Guard not found at {FIVEGUARD_DIR}. Run scripts/fetch_5guard.py first.")

# 5Guard modules use bare imports (e.g. "from libraries import *")
sys.path.insert(0, str(FIVEGUARD_DIR))
os.chdir(FIVEGUARD_DIR)  # 5Guard reads relative paths like dataset/brain.xml

# Set solver before importing libraries (default to scip to avoid Gurobi model-size limit)
if "--solver" in sys.argv:
    _idx = sys.argv.index("--solver")
    if _idx + 1 < len(sys.argv):
        os.environ["FIVEGUARD_SOLVER"] = sys.argv[_idx + 1].lower()
elif "FIVEGUARD_SOLVER" not in os.environ:
    os.environ["FIVEGUARD_SOLVER"] = "scip"

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

# Import everything via 5Guard's own import chain — this handles Gurobi/SCIP
# fallback and ensures globals (F_MAX, BANDWIDTH_SCALE, etc.) propagate to
# all algorithm modules correctly.
from libraries import *
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter
import matplotlib.ticker as ticker

# Algorithm solvers (already imported by libraries.py via star-import)
from algorithms.opt import opt_iter
from algorithms.iar import iar_iter
from algorithms.dtr import dtr_iter
from algorithms.rnr import rnr_iter
from algorithms.nis import nis_iter
from algorithms.cis import cis_iter
from algorithms.fgr import fgr_iter


# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "paper_figures_reproduction"
PLOTS_DIR     = ARTIFACTS_DIR / "plots"
DATA_DIR      = ARTIFACTS_DIR / "data"


def ensure_dirs(output_dir=None):
    global ARTIFACTS_DIR, PLOTS_DIR, DATA_DIR
    if output_dir:
        out_p = Path(output_dir)
        if not out_p.is_absolute():
            ARTIFACTS_DIR = (PROJECT_ROOT / out_p).resolve()
        else:
            ARTIFACTS_DIR = out_p.resolve()
    else:
        ARTIFACTS_DIR = PROJECT_ROOT / "artifacts" / "paper_figures_reproduction"
    PLOTS_DIR = ARTIFACTS_DIR / "plots"
    DATA_DIR  = ARTIFACTS_DIR / "data"

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 5Guard also needs these directories
    (FIVEGUARD_DIR / "plots").mkdir(exist_ok=True)
    (FIVEGUARD_DIR / "saved_model").mkdir(exist_ok=True)
    (FIVEGUARD_DIR / "saved_data" / "synthetic").mkdir(parents=True, exist_ok=True)
    (FIVEGUARD_DIR / "saved_data" / "brain").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Core simulation loop (mirrors simulation.ipynb Cell 16)
# ---------------------------------------------------------------------------
ALGS_ALL = ["opt", "iar", "dtr", "rnr", "nis", "cis", "fgr"]
ALGS_FGR = ["opt", "iar", "dtr", "rnr", "fgr"]

ALG_FUNC = {
    "opt": opt_iter,
    "iar": iar_iter,
    "dtr": dtr_iter,
    "rnr": rnr_iter,
    "nis": nis_iter,
    "cis": cis_iter,
    "fgr": fgr_iter,
}

LIMIT = 0.6  # DTR rounding threshold


def init_data(algs, iters, sim_interval):
    """Initialise metric arrays (mirrors Cell 11)."""
    data = {}
    for a in algs:
        data[a] = {
            "profit":  np.zeros((iters, sim_interval)),
            "violat":  np.zeros((iters, sim_interval, 5)),
            "migrat":  np.zeros((iters, sim_interval)),
            "deploy":  np.zeros((iters, sim_interval, 4)),
            "overhe":  np.zeros((iters, sim_interval, 4)),
            "reseff":  np.zeros((iters, sim_interval, 4)),
            "reject":  np.zeros((iters, sim_interval, 3)),
            "time":    np.zeros((iters, sim_interval)),
            "feasib":  np.zeros((iters, sim_interval)),
            "timeou":  np.zeros((iters, sim_interval)),
            "R_t":     [[] for _ in range(iters)],
            "X_t":     [[] for _ in range(iters)],
            "Y_t":     [[] for _ in range(iters)],
        }
    return data


def _run_single_iteration(args_tuple):
    """Worker function to run a single iteration across all time steps."""
    (
        alg,
        iteration,
        sim_interval,
        sr_slice,
        V_P_S,
        V_P_R,
        E_P,
        E_P_l,
        L,
        L_pqi,
        solver,
    ) = args_tuple

    import sys as _py_sys
    os.environ["FIVEGUARD_SOLVER"] = solver
    _py_sys.path.insert(0, str(FIVEGUARD_DIR))
    os.chdir(FIVEGUARD_DIR)

    from libraries import gp, GRB
    from algorithms.opt import opt_iter
    from algorithms.iar import iar_iter
    from algorithms.dtr import dtr_iter
    from algorithms.rnr import rnr_iter
    from algorithms.nis import nis_iter
    from algorithms.cis import cis_iter
    from algorithms.fgr import fgr_iter

    func_map = {
        "opt": opt_iter,
        "iar": iar_iter,
        "dtr": dtr_iter,
        "rnr": rnr_iter,
        "nis": nis_iter,
        "cis": cis_iter,
        "fgr": fgr_iter,
    }
    func = func_map[alg]
    limit = 0.6

    # Create initial model template for this iteration
    m = gp.Model("e2esliceiso")
    if alg == "fgr":
        m.write(str(FIVEGUARD_DIR / f"saved_model/model_backup_fgr_{iteration}.mps"))
        for sub in ["opt", "iar", "dtr", "rnr"]:
            m.write(str(FIVEGUARD_DIR / f"saved_model/model_backup_fgr_{sub}_{iteration}.mps"))
    else:
        m.write(str(FIVEGUARD_DIR / f"saved_model/model_backup_{alg}_{iteration}.mps"))

    keys = [
        "profit", "violat", "migrat", "deploy", "overhe",
        "reseff", "reject", "time", "feasib", "timeou",
    ]
    iter_data = {
        "profit":  np.zeros(sim_interval),
        "violat":  np.zeros((sim_interval, 5)),
        "migrat":  np.zeros(sim_interval),
        "deploy":  np.zeros((sim_interval, 4)),
        "overhe":  np.zeros((sim_interval, 4)),
        "reseff":  np.zeros((sim_interval, 4)),
        "reject":  np.zeros((sim_interval, 3)),
        "time":    np.zeros(sim_interval),
        "feasib":  np.zeros(sim_interval),
        "timeou":  np.zeros(sim_interval),
        "R_t":     [],
        "X_t":     [],
        "Y_t":     [],
    }
    fgr_choices = [0] * sim_interval
    t_start = time.time()

    # Silence per-step verbose ASCII tables to prevent console I/O bottlenecks
    with open(os.devnull, "w") as fnull:
        with redirect_stdout(fnull):
            for t in range(sim_interval):
                prev_profit = iter_data["profit"][t - 1] if t > 0 else 0
                R_t = iter_data["R_t"] if t > 0 else []
                X_t = copy.deepcopy(iter_data["X_t"]) if t > 0 else []
                Y_t = copy.deepcopy(iter_data["Y_t"]) if t > 0 else []

                sr_req = sr_slice[t]

                try:
                    if alg == "fgr":
                        result, fgr_choice, X_t, Y_t = func(
                            limit, prev_profit, iteration, t,
                            sr_req, R_t,
                            V_P_S, V_P_R, E_P, E_P_l, L, L_pqi,
                            X_t, Y_t,
                        )
                        fgr_choices[t] = fgr_choice
                    elif alg == "dtr":
                        result, X_t, Y_t = func(
                            limit, prev_profit, iteration, t,
                            sr_req, R_t,
                            V_P_S, V_P_R, E_P, E_P_l, L, L_pqi,
                            0, X_t, Y_t,
                        )
                    else:
                        result, X_t, Y_t = func(
                            prev_profit, iteration, t,
                            sr_req, R_t,
                            V_P_S, V_P_R, E_P, E_P_l, L, L_pqi,
                            0, X_t, Y_t,
                        )
                except Exception:
                    if t > 0:
                        for k in keys:
                            iter_data[k][t] = iter_data[k][t - 1]
                    continue

                if result[8] == 1:  # feasible
                    for idx_k, k in enumerate(keys):
                        iter_data[k][t] = result[idx_k]
                    iter_data["R_t"] = result[10]
                    iter_data["X_t"] = X_t
                    iter_data["Y_t"] = Y_t
                else:  # infeasible
                    if t > 0:
                        for idx_k, k in enumerate(keys):
                            iter_data[k][t] = iter_data[k][t - 1]
                        iter_data["reject"][t] = result[6]
                        iter_data["time"][t]   = result[7]
                        iter_data["feasib"][t] = result[8]
                        iter_data["timeou"][t] = result[9]

    elapsed = time.time() - t_start
    return iteration, iter_data, fgr_choices, elapsed


def run_simulation(
    alg: str,
    data: dict,
    iters: int,
    sim_interval: int,
    tot_sim: int,
    sr_list: list,
    V_P_S, V_P_R, E_P, E_P_l, L, L_pqi,
    use_brain: bool,
    workers: int = 4,
):
    """Run one algorithm with parallel iterations across CPU cores."""
    fgr_alg_choices = [[0] * sim_interval for _ in range(iters)]
    solver = os.environ.get("FIVEGUARD_SOLVER", "scip")

    tasks = [
        (
            alg,
            i,
            sim_interval,
            sr_list[i * tot_sim : i * tot_sim + sim_interval],
            V_P_S,
            V_P_R,
            E_P,
            E_P_l,
            L,
            L_pqi,
            solver,
        )
        for i in range(iters)
    ]

    actual_workers = min(iters, workers)
    print(f"  Dispatching {iters} iterations to {actual_workers} parallel workers...")

    with concurrent.futures.ProcessPoolExecutor(max_workers=actual_workers) as executor:
        futures = {executor.submit(_run_single_iteration, task): task[1] for task in tasks}
        completed_count = 0
        for future in concurrent.futures.as_completed(futures):
            iteration, iter_data, fgr_choices, elapsed = future.result()
            completed_count += 1
            for k in [
                "profit", "violat", "migrat", "deploy", "overhe",
                "reseff", "reject", "time", "feasib", "timeou",
            ]:
                data[alg][k][iteration] = iter_data[k]
            data[alg]["R_t"][iteration] = iter_data["R_t"]
            data[alg]["X_t"][iteration] = iter_data["X_t"]
            data[alg]["Y_t"][iteration] = iter_data["Y_t"]
            fgr_alg_choices[iteration]  = fgr_choices
            print(
                f"  [{alg.upper()}] Iteration {iteration+1:2d}/{iters} finished in "
                f"{elapsed:5.1f}s (final profit: {iter_data['profit'][-1]:10.2f}, "
                f"progress: {completed_count}/{iters})"
            )

    # Save pickle
    topo = "brain" if use_brain else "synthetic"
    pkl_path = FIVEGUARD_DIR / f"saved_data/{topo}/{alg}.pkl"
    with open(pkl_path, "wb") as f:
        pickle.dump(data[alg], f)

    return fgr_alg_choices


# ---------------------------------------------------------------------------
# Compute averages and generate plots (mirrors Cells 36-56)
# ---------------------------------------------------------------------------
PROPERTIES = {
    "opt": {"color": "#e4ac3e", "marker": "v", "ls": "-",  "hatch": "\\\\", "label": "OPT"},
    "iar": {"color": "#416fbd", "marker": "h", "ls": "-",  "hatch": "O",   "label": "IAR"},
    "dtr": {"color": "#64b749", "marker": "^", "ls": "-",  "hatch": "-",   "label": "DTR"},
    "rnr": {"color": "#742993", "marker": "D", "ls": "-",  "hatch": "...", "label": "RNR"},
    "nis": {"color": "#9d2136", "marker": ">", "ls": "--", "hatch": ".",   "label": "NIS"},
    "cis": {"color": "#d9532d", "marker": "<", "ls": "--", "hatch": "o",   "label": "CIS"},
    "fgr": {"color": "#777777", "marker": "o", "ls": "-",  "hatch": "/",   "label": "5Guard"},
}


def compute_averages(data, algs, iters, sim_interval):
    """Compute iteration-averaged metrics."""
    kpis = ["profit", "violat", "migrat", "deploy", "overhe", "reseff", "reject", "time"]
    data_avg = {}
    for a in algs:
        data_avg[a] = {}
        for k in kpis:
            data_avg[a][k] = np.sum(data[a][k], axis=0) / iters
    return data_avg


def generate_plots(data, data_avg, algs, iters, sim_interval, sr_type_list, sr_list, tot_sim, use_brain, fgr_choices=None):
    """Generate the paper's key SVG and PNG plots with figure-matching filenames."""
    plt.rcParams["font.family"] = "DejaVu Serif"
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["ps.fonttype"] = 42

    markevery = int(sim_interval / 10 + 1)
    linewidth = 2
    marker_size = 12
    mew = 2
    step = 10
    xtick_step = max(sim_interval // 5, 1)
    offset = 16 if use_brain else 0
    xpoints = range(sim_interval)

    algs_fgr = [a for a in ALGS_FGR if a in algs]
    colors_fgr   = [PROPERTIES[a]["color"]  for a in algs_fgr]
    markers_fgr  = [PROPERTIES[a]["marker"] for a in algs_fgr]
    ls_fgr       = [PROPERTIES[a]["ls"]     for a in algs_fgr]
    legends_fgr  = [PROPERTIES[a]["label"]  for a in algs_fgr]

    yerr_lo  = {a: {k: np.maximum(data_avg[a][k] - np.min(data[a][k], axis=0), 0)
                    for k in ["profit", "migrat", "time"]}
                for a in algs_fgr}
    yerr_hi  = {a: {k: np.maximum(np.max(data[a][k], axis=0) - data_avg[a][k], 0)
                    for k in ["profit", "migrat", "time"]}
                for a in algs_fgr}

    def save_fig_dual(fig, basename, paper_name):
        fig.savefig(str(PLOTS_DIR / f"{basename}.svg"), format="svg")
        fig.savefig(str(PLOTS_DIR / f"{paper_name}.svg"), format="svg")
        fig.savefig(str(PLOTS_DIR / f"{paper_name}.png"), format="png", dpi=300)

    # --- Plot 1: Profit over time --- (Fig 6b / 6f)
    fig, ax = plt.subplots(figsize=(6, 6))
    for i, alg in enumerate(algs_fgr):
        ax.plot(xpoints, data_avg[alg]["profit"],
                marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax.grid()
    ax.set_xlabel("$\\it{t}$", fontsize=20)
    ax.set_ylabel("Profit", fontsize=20)
    ax.legend(legends_fgr, fontsize=13)
    ax.tick_params(labelsize=16)
    ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax.yaxis.get_major_formatter().set_scientific(True)
    ax.yaxis.get_major_formatter().set_powerlimits((-1, 1))
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"profit_{offset}", f"fig6_{'f' if use_brain else 'b'}_profit")
    plt.close(fig)

    # --- Plot 2: Cumulative migration --- (Fig 6c / 6g)
    fig, ax = plt.subplots(figsize=(6, 6))
    for i, alg in enumerate(algs_fgr):
        ax.plot(xpoints, np.cumsum(data_avg[alg]["migrat"]),
                marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax.grid()
    ax.set_xlabel("$\\it{t}$", fontsize=20)
    ax.set_ylabel("Cumulative Migration", fontsize=20)
    ax.legend(legends_fgr, fontsize=13)
    ax.tick_params(labelsize=16)
    ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax.yaxis.get_major_formatter().set_scientific(True)
    ax.yaxis.get_major_formatter().set_powerlimits((-1, 1))
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"migration_{offset}", f"fig6_{'g' if use_brain else 'c'}_migration")
    plt.close(fig)

    # --- Plot 3: Allocation time --- (Fig 7)
    fig, ax = plt.subplots(figsize=(10, 4.75))
    for i, alg in enumerate(algs_fgr):
        ax.plot(xpoints, data_avg[alg]["time"],
                marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])

    # Overlay timeout deadlines
    timeout_times = np.zeros((iters, sim_interval))
    for it in range(iters):
        for idx_t in range(sim_interval):
            timeout_times[it][idx_t] = sr_list[it * tot_sim + idx_t].timeout
    timeout_avg = np.mean(timeout_times, axis=0)
    ax.plot(xpoints, timeout_avg, color="black", linewidth=linewidth, linestyle=":")

    ax.grid()
    ax.set_xlabel("$\\it{t}$", fontsize=22)
    ax.set_ylabel("Allocation Time (sec.)", fontsize=22)
    ax.legend(legends_fgr + ["Deadline"], fontsize=14, ncol=3)
    ax.tick_params(labelsize=18)
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"alloc_time_{offset}", f"fig7_alloc_time{'_brain' if use_brain else ''}")
    plt.close(fig)

    # --- Plot 4: Admission rate bar chart --- (Fig 6a / 6e)
    fig, ax = plt.subplots(figsize=(6, 6))
    bar_width = 0.12
    positions = [np.arange(3) + i * bar_width for i in range(len(algs_fgr))]
    sr_type_list_used = [
        sr_type_list[t]
        for it in range(iters)
        for t in range(it * tot_sim, it * tot_sim + sim_interval)
    ]
    NUM_L0 = (sr_type_list_used.count(0) + sr_type_list_used.count(2)) / iters
    NUM_L1 = sr_type_list_used.count(1) / iters
    NUM_L2 = sr_type_list_used.count(3) / iters
    denom = np.clip([NUM_L0, NUM_L1, NUM_L2], 1e-9, None)

    for i, alg in enumerate(algs_fgr):
        values = (1 - np.sum(data_avg[alg]["reject"], axis=0) / denom) * 100
        values = np.clip(values, 0, 100)
        ax.bar(positions[i], values, width=bar_width,
               color=PROPERTIES[alg]["color"], edgecolor="black",
               hatch=PROPERTIES[alg]["hatch"])
    ax.set_xticks(positions[len(algs_fgr) // 2])
    ax.set_xticklabels(["0", "1", "2"])
    ax.set_ylim(top=119)
    ax.set_xlabel("Isolation Level", fontsize=20)
    ax.set_ylabel("Slice Admission (%)", fontsize=20)
    ax.legend(legends_fgr, fontsize=12, loc="upper center", ncol=3)
    ax.tick_params(labelsize=16)
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"admission_{offset}", f"fig6_{'e' if use_brain else 'a'}_admission")
    plt.close(fig)

    
    # --- Plot 5: Overhead cost (all 7 algs) and domains (Fig 9) ---
    all_colors  = [PROPERTIES[a]["color"]  for a in algs]
    all_markers = [PROPERTIES[a]["marker"] for a in algs]
    all_ls      = [PROPERTIES[a]["ls"]     for a in algs]
    all_legends = [PROPERTIES[a]["label"]  for a in algs]

    domain_names = ["total", "ran", "tn", "cn"]
    paper_letters = ['a', 'e', 'i', 'm'] if not use_brain else ['b', 'f', 'j', 'n']
    for d in range(4):
        fig, ax = plt.subplots(figsize=(6, 6))
        for i, alg in enumerate(algs):
            ax.plot(xpoints, data_avg[alg]["overhe"][:, d],
                    marker=all_markers[i], markevery=markevery, markersize=marker_size,
                    color=all_colors[i], linewidth=linewidth, markerfacecolor="none",
                    markeredgecolor=all_colors[i], markeredgewidth=mew, linestyle=all_ls[i])
        ax.grid()
        ax.set_xlabel("$\it{t}$", fontsize=20)
        ax.set_ylabel(f"{domain_names[d].upper()} Overhead Cost" if d > 0 else "Total Overhead Cost", fontsize=20)
        if d == 0:
            ax.legend(all_legends, fontsize=11, ncol=2)
        ax.tick_params(labelsize=16)
        ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
        ax.yaxis.get_major_formatter().set_scientific(True)
        ax.yaxis.get_major_formatter().set_powerlimits((-1, 1))
        fig.tight_layout(pad=0.5)
        save_fig_dual(fig, f"overhead_{domain_names[d]}_{offset}", f"fig9_{paper_letters[d]}_overhead_{domain_names[d]}")
        plt.close(fig)

    # --- Plot 6: Resource efficiency (all 7 algs) and domains (Fig 9 cont) ---
    paper_letters_res = ['c', 'g', 'k', 'o'] if not use_brain else ['d', 'h', 'l', 'p']
    for d in range(4):
        fig, ax = plt.subplots(figsize=(6, 6))
        for i, alg in enumerate(algs):
            ax.plot(xpoints, data_avg[alg]["reseff"][:, d],
                    marker=all_markers[i], markevery=markevery, markersize=marker_size,
                    color=all_colors[i], linewidth=linewidth, markerfacecolor="none",
                    markeredgecolor=all_colors[i], markeredgewidth=mew, linestyle=all_ls[i])
        ax.grid()
        ax.set_xlabel("$\it{t}$", fontsize=20)
        ax.set_ylabel(f"Avg {domain_names[d].upper()} Resource Efficiency (%)" if d > 0 else "Avg Resource Efficiency (%)", fontsize=18)
        if d == 0:
            ax.legend(all_legends, fontsize=11, ncol=2)
        ax.tick_params(labelsize=16)
        fig.tight_layout(pad=0.5)
        save_fig_dual(fig, f"resource_eff_{domain_names[d]}_{offset}", f"fig9_{paper_letters_res[d]}_resource_eff_{domain_names[d]}")
        plt.close(fig)

    # --- Plot 7: Violation cost --- (Fig 6d / 6h)
    fig, ax = plt.subplots(figsize=(6, 6))
    for i, alg in enumerate(algs_fgr):
        ax.plot(xpoints, data_avg[alg]["violat"][:, 0],
                marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax.grid()
    ax.set_xlabel("$\\it{t}$", fontsize=20)
    ax.set_ylabel("Violation Cost", fontsize=20)
    ax.legend(legends_fgr, fontsize=13)
    ax.tick_params(labelsize=16)
    ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax.yaxis.get_major_formatter().set_scientific(True)
    ax.yaxis.get_major_formatter().set_powerlimits((-1, 1))
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"violation_{offset}", f"fig6_{'h' if use_brain else 'd'}_violation")
    plt.close(fig)

    # --- Plot 8: Deployment cost ---
    fig, ax = plt.subplots(figsize=(6, 6))
    for i, alg in enumerate(algs_fgr):
        ax.plot(xpoints, data_avg[alg]["deploy"][:, 0],
                marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax.grid()
    ax.set_xlabel("$\\it{t}$", fontsize=20)
    ax.set_ylabel("Deployment Cost", fontsize=20)
    ax.legend(legends_fgr, fontsize=13)
    ax.tick_params(labelsize=16)
    ax.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax.yaxis.get_major_formatter().set_scientific(True)
    ax.yaxis.get_major_formatter().set_powerlimits((-1, 1))
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"deployment_{offset}", f"deployment_{offset}")
    plt.close(fig)

    
    # --- Plot: Fig 8 (Algorithm Usage) ---
    if fgr_choices is not None:
        fig, ax = plt.subplots(figsize=(10, 4.75))
        usage_time = np.zeros((iters, sim_interval, 4))
        for it in range(iters):
            for t in range(sim_interval):
                if t == 0:
                    for a in range(4):
                        usage_time[it][t][a] = 100.0 if fgr_choices[it][t] == a else 0.0
                else:
                    for a in range(4):
                        usage_time[it][t][a] = fgr_choices[it][0:t].count(a) / t * 100.0

        usage_avg = np.mean(usage_time, axis=0) # shape (sim_interval, 4)
        
        ax.plot(xpoints, usage_avg[:, 1], color=PROPERTIES["iar"]["color"], linestyle="-", linewidth=linewidth, label="IAR")
        ax.plot(xpoints, usage_avg[:, 2], color=PROPERTIES["dtr"]["color"], linestyle="--", linewidth=linewidth, label="DTR")
        ax.plot(xpoints, usage_avg[:, 3], color=PROPERTIES["rnr"]["color"], linestyle=":", linewidth=linewidth, label="RNR")
        ax.grid()
        ax.set_xlabel("$\\it{t}$", fontsize=22)
        ax.set_ylabel("Average Usage (%)", fontsize=22)
        ax.legend(fontsize=16, ncol=3)
        ax.tick_params(labelsize=18)
        fig.tight_layout(pad=0.5)
        save_fig_dual(fig, f"alg_usage_{offset}", f"fig8_alg_usage{'_brain' if use_brain else ''}")
        plt.close(fig)

    # --- Plot: Fig 5 (Isolation Level) ---
    fig, ax = plt.subplots(figsize=(10, 4.75))
    
    isol_level_cavg = {"nis": np.zeros(sim_interval), "cis": np.ones(sim_interval)*2, "iaw": np.zeros(sim_interval)}
    
    for t in range(sim_interval):
        val_sum = 0
        for it in range(iters):
            stype = sr_type_list[it * tot_sim + (t % tot_sim)]
            lvl = 0 if (stype == 0 or stype == 2) else (1 if stype == 1 else 2)
            val_sum += lvl
        isol_level_cavg["iaw"][t] = val_sum / iters
        
    for key in ["nis", "cis", "iaw"]:
        cavg = np.zeros(sim_interval)
        csum = 0
        for t in range(sim_interval):
            csum += isol_level_cavg[key][t]
            cavg[t] = csum / (t + 1)
        isol_level_cavg[key] = cavg

    ax.plot(xpoints, isol_level_cavg["nis"], color=PROPERTIES["nis"]["color"], linestyle=PROPERTIES["nis"]["ls"], linewidth=linewidth, label="NIS")
    ax.plot(xpoints, isol_level_cavg["cis"], color=PROPERTIES["cis"]["color"], linestyle=PROPERTIES["cis"]["ls"], linewidth=linewidth, label="CIS")
    ax.plot(xpoints, isol_level_cavg["iaw"], color=PROPERTIES["iar"]["color"], linestyle="-", linewidth=linewidth, label="Isolation-Aware")
    ax.grid()
    ax.set_xlabel("$\\it{t}$", fontsize=22)
    ax.set_ylabel("Avg SR's Isolation Level", fontsize=22)
    ax.set_yticks([0, 1, 2])
    ax.legend(fontsize=16, ncol=3)
    ax.tick_params(labelsize=18)
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"isolation_level_{offset}", f"fig5_isolation_level{'_brain' if use_brain else ''}")
    plt.close(fig)

    # --- Plot 9: Multi-panel Figure 6 Composite ---
    fig_comb, (ax_adm, ax_prof, ax_mig, ax_viol) = plt.subplots(1, 4, figsize=(24, 5.5))
    
    # 1. Admission
    for i, alg in enumerate(algs_fgr):
        values = (1 - np.sum(data_avg[alg]["reject"], axis=0) / denom) * 100
        values = np.clip(values, 0, 100)
        ax_adm.bar(positions[i], values, width=bar_width,
                   color=PROPERTIES[alg]["color"], edgecolor="black",
                   hatch=PROPERTIES[alg]["hatch"])
    ax_adm.set_xticks(positions[len(algs_fgr) // 2])
    ax_adm.set_xticklabels(["0", "1", "2"])
    ax_adm.set_ylim(top=119)
    ax_adm.set_xlabel(f"Isolation Level\n\n({'a' if not use_brain else 'e'})", fontsize=18)
    ax_adm.set_ylabel("Slice Admission (%)", fontsize=18)
    ax_adm.legend(legends_fgr, fontsize=11, loc="upper center", ncol=3)
    ax_adm.tick_params(labelsize=14)
    ax_adm.grid(axis="y")

    # 2. Profit
    for i, alg in enumerate(algs_fgr):
        ax_prof.plot(xpoints, data_avg[alg]["profit"],
                     marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                     color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                     markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax_prof.grid()
    ax_prof.set_xlabel(f"$\\it{{t}}$\n\n({'b' if not use_brain else 'f'})", fontsize=18)
    ax_prof.set_ylabel("Profit", fontsize=18)
    ax_prof.legend(legends_fgr, fontsize=11)
    ax_prof.tick_params(labelsize=14)
    ax_prof.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax_prof.yaxis.get_major_formatter().set_scientific(True)
    ax_prof.yaxis.get_major_formatter().set_powerlimits((-1, 1))

    # 3. Cumulative Migration
    for i, alg in enumerate(algs_fgr):
        ax_mig.plot(xpoints, np.cumsum(data_avg[alg]["migrat"]),
                    marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                    color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                    markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax_mig.grid()
    ax_mig.set_xlabel(f"$\\it{{t}}$\n\n({'c' if not use_brain else 'g'})", fontsize=18)
    ax_mig.set_ylabel("Cumulative Migration", fontsize=18)
    ax_mig.legend(legends_fgr, fontsize=11)
    ax_mig.tick_params(labelsize=14)
    ax_mig.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax_mig.yaxis.get_major_formatter().set_scientific(True)
    ax_mig.yaxis.get_major_formatter().set_powerlimits((-1, 1))

    # 4. Violation Cost
    for i, alg in enumerate(algs_fgr):
        ax_viol.plot(xpoints, data_avg[alg]["violat"][:, 0],
                     marker=markers_fgr[i], markevery=markevery, markersize=marker_size,
                     color=colors_fgr[i], linewidth=linewidth, markerfacecolor="none",
                     markeredgecolor=colors_fgr[i], markeredgewidth=mew, linestyle=ls_fgr[i])
    ax_viol.grid()
    ax_viol.set_xlabel(f"$\\it{{t}}$\n\n({'d' if not use_brain else 'h'})", fontsize=18)
    ax_viol.set_ylabel("Violation Cost", fontsize=18)
    ax_viol.legend(legends_fgr, fontsize=11)
    ax_viol.tick_params(labelsize=14)
    ax_viol.yaxis.set_major_formatter(ScalarFormatter(useMathText=True))
    ax_viol.yaxis.get_major_formatter().set_scientific(True)
    ax_viol.yaxis.get_major_formatter().set_powerlimits((-1, 1))

    fig_comb.tight_layout()
    comb_name = f"fig6_{'a_to_d' if not use_brain else 'e_to_h'}_combined"
    fig_comb.savefig(str(PLOTS_DIR / f"{comb_name}.svg"), format="svg")
    fig_comb.savefig(str(PLOTS_DIR / f"{comb_name}.png"), format="png", dpi=300)
    plt.close(fig_comb)

    print(f"  Plots saved to {PLOTS_DIR}/")


# ---------------------------------------------------------------------------
# JSON summary
# ---------------------------------------------------------------------------
def build_summary(data, data_avg, algs, iters, sim_interval, sr_type_list, tot_sim, elapsed, use_brain):
    """Build a JSON-serialisable result summary."""
    # Final time-step averaged metrics
    T = sim_interval - 1
    summary = {
        "topology": "brain" if use_brain else "synthetic",
        "iterations": iters,
        "simulation_interval": sim_interval,
        "total_wall_clock_seconds": round(elapsed, 1),
        "algorithms": {},
    }
    for a in algs:
        summary["algorithms"][a] = {
            "final_profit_mean": round(float(data_avg[a]["profit"][T]), 4),
            "final_violation_mean": round(float(data_avg[a]["violat"][T, 0]), 4),
            "cumulative_migration_mean": round(float(np.sum(data_avg[a]["migrat"])), 4),
            "final_overhead_mean": round(float(data_avg[a]["overhe"][T, 0]), 4),
            "final_deployment_mean": round(float(data_avg[a]["deploy"][T, 0]), 4),
            "mean_resource_efficiency": round(float(np.mean(data_avg[a]["reseff"][:, 0])), 4),
            "total_rejections_L0": round(float(np.sum(data_avg[a]["reject"][:, 0])), 4),
            "total_rejections_L1": round(float(np.sum(data_avg[a]["reject"][:, 1])), 4),
            "total_rejections_L2": round(float(np.sum(data_avg[a]["reject"][:, 2])), 4),
            "mean_alloc_time_sec": round(float(np.mean(data_avg[a]["time"])), 6),
        }
    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Reproduce 5Guard base paper experiments")
    parser.add_argument("--brain", action="store_true",
                        help="Use BRAIN (Berlin) topology instead of synthetic")
    parser.add_argument("--iters", type=int, default=10,
                        help="Monte Carlo iterations (paper uses 10)")
    parser.add_argument("--interval", type=int, default=140,
                        help="Simulation interval / time steps (paper uses 140)")
    parser.add_argument("--algs", nargs="+", default=None,
                        help="Algorithms to run (default: all seven)")
    parser.add_argument("--skip-plots", action="store_true",
                        help="Skip plot generation")
    parser.add_argument("--solver", choices=["scip", "gurobi"], default="scip",
                        help="Solver backend: 'scip' (default, unrestricted) or 'gurobi'")
    parser.add_argument("--workers", type=int, default=None,
                        help="Number of parallel workers (default: min(iters, cpu_count))")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Directory to save reproduction results and plots (default: artifacts/paper_figures_reproduction)")
    parser.add_argument("--load", action="store_true",
                        help="Load existing pickled data instead of simulating")
    args = parser.parse_args()

    ensure_dirs(args.output_dir)

    use_brain = args.brain
    iters = args.iters
    sim_interval = args.interval
    tot_sim = max(200, sim_interval)
    algs = args.algs or ALGS_ALL
    workers = args.workers or min(iters, os.cpu_count() or 4)

    # Validate algorithms
    for a in algs:
        if a not in ALG_FUNC:
            sys.exit(f"Unknown algorithm: {a}. Choose from {list(ALG_FUNC.keys())}")

    gp.setParam("OutputFlag", 0)

    # --- Topology setup ---
    print(f"=== 5Guard Reproduction ===")
    print(f"Topology:   {'BRAIN' if use_brain else 'Synthetic'}")
    print(f"Iterations: {iters}, Interval: {sim_interval}")
    print(f"Algorithms: {algs}")
    print(f"Workers:    {workers} parallel processes (CPUs: {os.cpu_count()})")
    print()

    if use_brain:
        V_P_S, V_P_R, E_P, E_P_l, L, L_pqi = init_setup_brain()
    else:
        V_P_S, V_P_R, E_P, E_P_l, L, L_pqi = init_setup_synth()

    print(f"Physical Servers: {len(V_P_S)}")
    print(f"NR Base Stations: {len(V_P_R)}")
    print(f"Physical Paths:   {len(E_P)}")
    print()

    # --- Slice request generation ---
    sr_types = create_sr_resources()
    sr_probs = [0.7, 0.15, 0.1, 0.05]  # eMBB, URLLC, mMTC, MCRI
    sr_list, sr_type_list = init_setup_sr(iters, tot_sim, sr_types, sr_probs)
    print(f"Generated {len(sr_list)} slice requests")
    print()

    # --- Run simulations ---
    data = init_data(algs, iters, sim_interval)
    fgr_choices = None
    wall_start = time.time()

    for alg in algs:
        t0 = time.time()
        print(f"--- Running {alg.upper()} ---")
        try:
            topo = "brain" if use_brain else "synthetic"
            pkl_path = FIVEGUARD_DIR / f"saved_data/{topo}/{alg}.pkl"
            if args.load and pkl_path.exists():
                print(f"  [{alg.upper()}] Loading from {pkl_path}")
                with open(pkl_path, "rb") as f:
                    data[alg] = pickle.load(f)
                if alg == "fgr":
                    # Load fgr choices somehow, but since we didn't save them in pkl, this is tricky.
                    # Wait, if we can't load fgr_choices, Fig 8 will fail.
                    pass
            else:
                choices = run_simulation(
                    alg, data, iters, sim_interval, tot_sim, sr_list,
                    V_P_S, V_P_R, E_P, E_P_l, L, L_pqi, use_brain,
                    workers=workers,
                )
                if alg == "fgr":
                    fgr_choices = choices
        except Exception as e:
            print(f"  [{alg.upper()}] FAILED: {e}")
            print(f"  Skipping {alg.upper()} and continuing...")
            continue
        dt = time.time() - t0
        print(f"  {alg.upper()} completed in {dt:.1f}s\n")

    elapsed = time.time() - wall_start
    print(f"Total wall-clock time: {elapsed:.1f}s\n")

    # --- Compute averages ---
    data_avg = compute_averages(data, algs, iters, sim_interval)

    # --- Generate plots ---
    if not args.skip_plots:
        print("Generating plots...")
        generate_plots(data, data_avg, algs, iters, sim_interval,
                       sr_type_list, sr_list, tot_sim, use_brain, fgr_choices)

    # --- Save JSON summary ---
    summary = build_summary(data, data_avg, algs, iters, sim_interval,
                            sr_type_list, tot_sim, elapsed, use_brain)
    topo_tag = "brain" if use_brain else "synthetic"
    json_path = ARTIFACTS_DIR / f"5guard_results_{topo_tag}.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Results saved to {json_path}")

    # --- Print summary table ---
    print(f"\n{'='*80}")
    print(f"5Guard Reproduction Results ({topo_tag} topology)")
    print(f"{'='*80}")
    print(f"{'Algorithm':<10} {'Final Profit':>14} {'Migrations':>12} {'Overhead':>12} "
          f"{'Rej L0':>8} {'Rej L1':>8} {'Rej L2':>8} {'Alloc(s)':>10}")
    print("-" * 80)
    for a in algs:
        s = summary["algorithms"].get(a, {})
        if s:
            print(f"{a.upper():<10} {s['final_profit_mean']:>14.2f} "
                  f"{s['cumulative_migration_mean']:>12.2f} "
                  f"{s['final_overhead_mean']:>12.2f} "
                  f"{s['total_rejections_L0']:>8.1f} "
                  f"{s['total_rejections_L1']:>8.1f} "
                  f"{s['total_rejections_L2']:>8.1f} "
                  f"{s['mean_alloc_time_sec']:>10.4f}")
    print("=" * 80)
    print()
    print("Done.")


if __name__ == "__main__":
    main()
