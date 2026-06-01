import json
import os

topologies = ['asymmetric', 'linear', 'diamond']

for topo in topologies:
    input_file = f"src/notebooks/experimental_studies_{topo}.ipynb"
    output_file = f"src/notebooks/experimental_studies_{topo}_t2_depolar.ipynb"
    
    with open(input_file, 'r', encoding='utf-8') as f:
        nb = json.load(f)
        
    new_cells = []
    
    # Modify the first two cells (Markdown intro and setup)
    intro_cell = dict(nb['cells'][0])
    intro_cell['source'] = [s.replace('modificando i parametri ed estraendo i risultati per la visualizzazione.', 'modificando i parametri T2 e Depolar Rate ed estraendo i risultati per la visualizzazione.') for s in intro_cell['source']]
    new_cells.append(intro_cell)
    
    # Second cell (imports and function)
    new_cells.append(nb['cells'][1])
    new_cells.append(nb['cells'][2])

    # Now let's create custom cells for T2 and Depolar Rate
    # T2 test
    md_t2 = {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 1. Test: Variazione Decoerenza (Memory T2)\n",
            "Aspettativa: T2 rappresenta la decoerenza di fase. Al diminuire di T2, la fedeltà scende, causando un aumento del QBER."
        ]
    }
    
    code_t2 = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "t2_values = [1e7, 1e6, 1e5] # da 10ms a 0.1ms\n",
            f"topologies = [('{topo.capitalize()}', 'config/{topo}_topology.json', 'sim_{topo}.py', 'results/{topo}_metrics.csv')]\n",
            "all_results_t2 = {}\n",
            "\n",
            "for topo_name, topo_file, sim_script, def_csv in topologies:\n",
            "    print(f\"\\n--- Avvio test Decoerenza T2 per topologia: {topo_name} ---\")\n",
            "    all_results_t2[topo_name] = {}\n",
            "    for t2 in t2_values:\n",
            "        custom_csv = f'results/{topo_name.lower()}_t2_{int(t2)}.csv'\n",
            "        df = run_experiment(\n",
            "            topology_file=topo_file,\n",
            "            config_updates={'memory_T2': t2},\n",
            "            simulation_script=sim_script,\n",
            "            default_csv=def_csv,\n",
            "            custom_csv_name=custom_csv\n",
            "        )\n",
            "        all_results_t2[topo_name][t2] = df\n",
            "\n",
            "print(\"\\nTutte le simulazioni di decoerenza T2 completate!\")"
        ]
    }
    
    plot_t2 = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "for topo_name, results_t2 in all_results_t2.items():\n",
            "    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)\n",
            "    \n",
            "    for t2, df in results_t2.items():\n",
            "        time_ms = df['time_stamp'] / 1e6\n",
            "        ax1.plot(time_ms, df['qber']*100, label=f\"T2={t2:.1e} s\")\n",
            "        ax2.plot(time_ms, df['skr_bps'], label=f\"T2={t2:.1e} s\")\n",
            "\n",
            "    ax1.set_ylabel(\"QBER (%)\")\n",
            "    ax1.set_title(f\"[{topo_name}] Effetto della Decoerenza (T2) sul QBER\")\n",
            "    ax1.axhline(y=11, color='orange', linestyle=':', label=\"Soglia 11%\")\n",
            "    ax1.legend()\n",
            "    ax1.grid(True)\n",
            "\n",
            "    ax2.set_ylabel(\"SKR (bps)\")\n",
            "    ax2.set_xlabel(\"Time (ms)\")\n",
            "    ax2.set_title(f\"[{topo_name}] Effetto della Decoerenza (T2) sul Secret Key Rate\")\n",
            "    ax2.legend()\n",
            "    ax2.grid(True)\n",
            "\n",
            "    plt.tight_layout()\n",
            f"    plt.savefig(f'results/plots/exp_t2_{topo}.png')\n",
            "    plt.show()\n",
            "    print(\"-\"*40)"
        ]
    }
    
    # Depolar Rate test
    md_depolar = {
        "cell_type": "markdown",
        "metadata": {},
        "source": [
            "## 2. Test: Variazione Depolar Rate (Channel Depolar Rate)\n",
            "Aspettativa: All'aumentare del depolar rate (tasso di depolarizzazione), il QBER aumenta rapidamente."
        ]
    }
    
    code_depolar = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "depolar_values = [0.01, 0.05, 0.1]\n",
            f"topologies = [('{topo.capitalize()}', 'config/{topo}_topology.json', 'sim_{topo}.py', 'results/{topo}_metrics.csv')]\n",
            "all_results_depolar = {}\n",
            "\n",
            "for topo_name, topo_file, sim_script, def_csv in topologies:\n",
            "    print(f\"\\n--- Avvio test Depolar Rate per topologia: {topo_name} ---\")\n",
            "    all_results_depolar[topo_name] = {}\n",
            "    for dep in depolar_values:\n",
            "        custom_csv = f'results/{topo_name.lower()}_depolar_{dep}.csv'\n",
            "        df = run_experiment(\n",
            "            topology_file=topo_file,\n",
            "            config_updates={'channel_depolar_rate': dep},\n",
            "            simulation_script=sim_script,\n",
            "            default_csv=def_csv,\n",
            "            custom_csv_name=custom_csv\n",
            "        )\n",
            "        all_results_depolar[topo_name][dep] = df\n",
            "\n",
            "print(\"\\nTutte le simulazioni di Depolar Rate completate!\")"
        ]
    }
    
    plot_depolar = {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [
            "for topo_name, results_depolar in all_results_depolar.items():\n",
            "    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)\n",
            "    \n",
            "    for dep, df in results_depolar.items():\n",
            "        time_ms = df['time_stamp'] / 1e6\n",
            "        ax1.plot(time_ms, df['qber']*100, label=f\"Depolar={dep}\")\n",
            "        ax2.plot(time_ms, df['skr_bps'], label=f\"Depolar={dep}\")\n",
            "\n",
            "    ax1.set_ylabel(\"QBER (%)\")\n",
            "    ax1.set_title(f\"[{topo_name}] Effetto del Depolar Rate sul QBER\")\n",
            "    ax1.axhline(y=11, color='orange', linestyle=':', label=\"Soglia 11%\")\n",
            "    ax1.legend()\n",
            "    ax1.grid(True)\n",
            "\n",
            "    ax2.set_ylabel(\"SKR (bps)\")\n",
            "    ax2.set_xlabel(\"Time (ms)\")\n",
            "    ax2.set_title(f\"[{topo_name}] Effetto del Depolar Rate sul Secret Key Rate\")\n",
            "    ax2.legend()\n",
            "    ax2.grid(True)\n",
            "\n",
            "    plt.tight_layout()\n",
            f"    plt.savefig(f'results/plots/exp_depolar_{topo}.png')\n",
            "    plt.show()\n",
            "    print(\"-\"*40)"
        ]
    }
    
    new_cells.extend([md_t2, code_t2, plot_t2, md_depolar, code_depolar, plot_depolar])
    nb['cells'] = new_cells
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1)
    print(f"Generated {output_file}")
