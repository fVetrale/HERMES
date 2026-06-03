import os
import pandas as pd
import matplotlib.pyplot as plt

def plot_results():
    """
    Legge i dati storicizzati in CSV per le tre topologie simulate 
    (Lineare, Diamante, Asimmetrica) e genera un grafico a due riquadri
    con l'andamento del QBER e del Secret Key Rate (SKR).
    """
    
    # Mappatura dei file CSV e delle impostazioni di plottaggio
    scenarios = {
        "Lineare": {
            "path": "results/linear_metrics.csv", 
            "color": "red", 
            "linestyle": "-"
        },
        "Diamante": {
            "path": "results/diamond_metrics.csv", 
            "color": "green", 
            "linestyle": "-"
        },
        "Asimmetrico": {
            "path": "results/asymmetric_metrics.csv", 
            "color": "blue", 
            "linestyle": "-"
        }
    }
    
    # Creazione della figura con due subplot sovrapposti
    fig, (ax_qber, ax_skr) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    
    for label, config in scenarios.items():
        if os.path.exists(config["path"]):
            df = pd.read_csv(config["path"])
            
            time_ms = df['time_stamp'] / 1e6
            qber_pct = df['qber'] * 100
            skr = df['skr_bps']
            
            ax_qber.plot(time_ms, qber_pct, label=label, 
                         color=config["color"], linestyle=config["linestyle"])
            
            ax_skr.plot(time_ms, skr, label=label, 
                        color=config["color"], linestyle=config["linestyle"])
        else:
            print(f"[Avviso] File {config['path']} non trovato. Esegui la relativa simulazione.")

    # --- Personalizzazione Subplot 1: QBER ---
    ax_qber.set_ylabel("QBER (%)")
    ax_qber.set_title("Andamento del Quantum Bit Error Rate (QBER)")
    # Linea verticale per l'attacco
    ax_qber.axvline(x=500, color='gray', linestyle='--', label="$t_{attack} = 500$ ms")
    # Linea orizzontale per la soglia di sicurezza dell'11%
    ax_qber.axhline(y=11, color='orange', linestyle=':', label="Soglia di Sicurezza (11%)")
    ax_qber.legend()
    ax_qber.grid(True, linestyle=':', alpha=0.7)
    
    # --- Personalizzazione Subplot 2: SKR ---
    ax_skr.set_ylabel("Secret Key Rate (bps)")
    ax_skr.set_title("Andamento del Secret Key Rate (SKR)")
    ax_skr.set_xlabel("Tempo di Simulazione (ms)")
    ax_skr.axvline(x=500, color='gray', linestyle='--')
    ax_skr.legend()
    ax_skr.grid(True, linestyle=':', alpha=0.7)
    
    plt.tight_layout()
    output_path = os.path.join("results", "network_performance.png")
    os.makedirs("results", exist_ok=True)
    plt.savefig(output_path, dpi=300)
    print(f"\nGrafico generato e salvato in: {output_path}")
    
    plt.show()

if __name__ == "__main__":
    plot_results()
