import pickle
import numpy as np
import matplotlib.pyplot as plt
import os
import sys as _sys
from matplotlib.ticker import ScalarFormatter
from pathlib import Path

# MUST import libraries first to unpickle sr objects
_sys.path.insert(0, str(Path("external/5guard").resolve()))
os.chdir("external/5guard")
from libraries import *
os.chdir("../..")

# Load synthetic data
iters = 10
sim_interval = 140
tot_sim = 140
algs = ["opt", "iar", "dtr", "rnr", "fgr"]
data = {}
for alg in algs:
    with open(f"external/5guard/saved_data/synthetic/{alg}.pkl", "rb") as f:
        data[alg] = pickle.load(f)

# Compute averages
kpis = ["profit", "violat", "migrat", "deploy", "overhe", "reseff", "reject", "time"]
data_avg = {}
for a in algs:
    data_avg[a] = {}
    for k in kpis:
        data_avg[a][k] = np.sum(data[a][k], axis=0) / iters

# Reconstruct fgr_choices exactly as simulation.ipynb did (Cell 52)
fgr_choices = [[0 for _ in range(sim_interval)] for _ in range(iters)]
DTR_p = 0.6
IAR_p = 0.2
RNR_p = 0.2
indices_nopt = [(i, j) for i, row in enumerate(data["fgr"]["time"]) for j, val in enumerate(row) if val == 2 or val == 4]
indices_opt  = [(i, j) for i, row in enumerate(data["fgr"]["time"]) for j, val in enumerate(row) if val != 2 and val != 4]

np.random.seed(42)  # For reproducibility
for i in range(iters):
    for t in range(sim_interval):
        if (i, t) in indices_opt:
            fgr_choices[i][t] = 0
        else:
            fgr_choices[i][t] = np.random.choice([1, 2, 3], p=[IAR_p, DTR_p, RNR_p])

print("FGR Choices reconstructed successfully.")

os.chdir("external/5guard")
# Now we can just call generate_plots from reproduce_5guard
_sys.path.insert(0, str(Path("../../scripts").resolve()))
import reproduce_5guard
reproduce_5guard.PLOTS_DIR = Path("../../artifacts/paper_figures_run/plots").resolve()
reproduce_5guard.PLOTS_DIR.mkdir(parents=True, exist_ok=True)

# we need sr_list and sr_type_list
sr_types = create_sr_resources()
sr_probs = [0.7, 0.15, 0.1, 0.05]
sr_list, sr_type_list = init_setup_sr(iters, tot_sim, sr_types, sr_probs)

reproduce_5guard.generate_plots(data, data_avg, algs, iters, sim_interval, sr_type_list, sr_list, tot_sim, False, fgr_choices)
print("Finished plotting synthetic!")
