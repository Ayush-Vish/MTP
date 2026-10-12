import re

with open("scripts/reproduce_5guard.py", "r") as f:
    content = f.read()

# Update function signature
content = content.replace(
    "def generate_plots(data, data_avg, algs, iters, sim_interval, sr_type_list, sr_list, tot_sim, use_brain):",
    "def generate_plots(data, data_avg, algs, iters, sim_interval, sr_type_list, sr_list, tot_sim, use_brain, fgr_choices=None):"
)

# Update call
content = content.replace(
    "generate_plots(data, data_avg, algs, iters, sim_interval,\n                       sr_type_list, sr_list, tot_sim, use_brain)",
    "generate_plots(data, data_avg, algs, iters, sim_interval,\n                       sr_type_list, sr_list, tot_sim, use_brain, fgr_choices)"
)

replacement = """
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
        ax.set_xlabel("$\\\\it{t}$", fontsize=20)
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
        ax.set_xlabel("$\\\\it{t}$", fontsize=20)
        ax.set_ylabel(f"Avg {domain_names[d].upper()} Resource Efficiency (%)" if d > 0 else "Avg Resource Efficiency (%)", fontsize=18)
        if d == 0:
            ax.legend(all_legends, fontsize=11, ncol=2)
        ax.tick_params(labelsize=16)
        fig.tight_layout(pad=0.5)
        save_fig_dual(fig, f"resource_eff_{domain_names[d]}_{offset}", f"fig9_{paper_letters_res[d]}_resource_eff_{domain_names[d]}")
        plt.close(fig)
"""

content = re.sub(r'# --- Plot 5: Overhead cost.*?# --- Plot 7: Violation cost', replacement + '\\n    # --- Plot 7: Violation cost', content, flags=re.DOTALL)

fig8_and_5 = """
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
        ax.set_xlabel("$\\\\it{t}$", fontsize=22)
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
    ax.set_xlabel("$\\\\it{t}$", fontsize=22)
    ax.set_ylabel("Avg SR's Isolation Level", fontsize=22)
    ax.set_yticks([0, 1, 2])
    ax.legend(fontsize=16, ncol=3)
    ax.tick_params(labelsize=18)
    fig.tight_layout(pad=0.5)
    save_fig_dual(fig, f"isolation_level_{offset}", f"fig5_isolation_level{'_brain' if use_brain else ''}")
    plt.close(fig)
"""

content = content.replace("# --- Plot 9: Multi-panel Figure 6 Composite ---", fig8_and_5 + "\\n    # --- Plot 9: Multi-panel Figure 6 Composite ---")

with open("scripts/reproduce_5guard.py", "w") as f:
    f.write(content)
