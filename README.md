# HERMES: High-Efficiency Routing for Quantum Entanglement and Messengers

**HERMES** è un simulatore di rete quantistica ad eventi discreti sviluppato in **Python 3** tramite il framework **NetSquid**. Il progetto implementa e analizza un algoritmo di **routing dinamico e adattivo** per la distribuzione dell'entanglement end-to-end tra due nodi terminali (Alice e Bob), superando i limiti di tolleranza ai guasti delle attuali architetture lineari statiche (*single point of failure*).

L'infrastruttura software separa nettamente il **Piano Data Quantistico** (gestione e conservazione dei qubit tramite protocollo BBM92) dal **Piano di Controllo Classico** (orchestrator di rete e logica decisionale per il routing).

---

## 🚀 Obiettivi Scientifici e Vantaggi Competitivi

A differenza delle reti classiche, il routing quantistico deve fare i conti con i vincoli imposti dalla fisica fondamentale (Teorema di No-Cloning) e dalla decoerenza hardware. HERMES dimostra l'efficacia del routing dinamico basato su tre pilastri:

1. **Cyber-Resilienza Attiva:** Monitoraggio runtime del canale tramite protocollo **BBM92** (variante basata su entanglement del BB84). Se un attacco informatico (*Intercept-Resend*) o un degradamento termico spinge il **QBER (Quantum Bit Error Rate) $\ge 11\%$** o la **Fidelity $F < 0.75$**, l'Orchestratore interviene istantaneamente deviando il flusso quantistico senza interrompere la sessione applicativa.
2. **Ottimizzazione del Secret Key Rate (SKR):** Selezione dinamica del cammino a maggiore Fidelity per massimizzare la generazione di chiavi crittografiche utili dopo la fase di *privacy amplification*.
3. **Analisi del Trade-off Geometria-Decoerenza:** Studio quantitativo dell'impatto delle distanze fisiche e del tempo di memorizzazione dei qubit ($T_2$) sulle memorie quantistiche locali quando si devia il traffico su linee asimmetriche.

---

## 📐 Topologie a Confronto

Il simulatore istanzia tre scenari geometrici, tutti sottoposti a iniezione di rumore dinamico (tramite l'agente "Eve") a metà simulazione ($t_{attack}$):

* **Topologia Lineare (Baseline):** Alice $\rightarrow$ R1 $\rightarrow$ Bob (20 km totali). Rappresenta il benchmark negativo: un attacco su R1 azzera permanentemente l'SKR.
* **Topologia a Diamante Bilanciata:** Alice, Bob e due ripetitori indipendenti (R1 superiore, R2 inferiore) con tratte equamente bilanciate a 20 km totali per entrambi i rami. Scenario di ripristino ideale in cui l'SKR ritorna a livelli ottimali dopo lo switch.
* **Topologia Asimmetrica / Triangolare:** Il percorso di backup passante per R2 modella una deviazione geografica svantaggiosa (40 km totali). Permette di mappare il costo della distanza in termini di decoerenza temporale ($T_2$).

---

## 🛠️ Struttura del Progetto

```text
HERMES/
├── config/                  # File JSON di configurazione delle topologie hardware
├── src/                     # Codice sorgente core del simulatore
│   ├── components/          # Hardware quantistico (nodi, memorie, canali in fibra e rumore)
│   ├── protocols/           # Logica dei nodi (BBM92 Endpoint, Ripetitori, Attaccante Eve)
│   ├── routing/             # Orchestratore e logica decisionale per lo switch di canale
│   └── utils/               # Moduli di raccolta telemetria (QBER, Fidelity, SKR)
├── sim_linear.py            # Script di esecuzione dello scenario Lineare
├── sim_diamond.py           # Script di esecuzione dello scenario Diamante Bilanciato
├── sim_asymmetric.py        # Script di esecuzione dello scenario Asimmetrico
├── plot_results.py          # Script per la visualizzazione grafica (Matplotlib) dei risultati
├── requirements.txt         # Elenco dipendenze Python
└── README.md                # Questo file
```

---

## ⚙️ Installazione e Prerequisiti

HERMES richiede **Python 3.8+**. Si consiglia l'utilizzo di un ambiente virtuale (virtualenv).

### 1. Clonazione del progetto
```bash
git clone <repository_url>
cd HERMES
```

### 2. Creazione dell'ambiente virtuale
```bash
python -m venv .venv
# Attivazione su Windows:
.venv\Scripts\activate
# Attivazione su Linux/macOS:
source .venv/bin/activate
```

### 3. Installazione delle dipendenze
I pacchetti principali richiesti sono `netsquid`, `numpy` e `matplotlib`. Puoi installarli tutti tramite il file `requirements.txt`:
```bash
pip install -r requirements.txt
```
*(Nota: la libreria `netsquid` potrebbe richiedere la registrazione e l'autenticazione tramite pip config, consultare la [documentazione ufficiale di NetSquid](https://netsquid.org) per le specifiche).*

---

## 🚀 Come Utilizzare il Simulatore

Il progetto fornisce script preimpostati per avviare la simulazione su ciascuna delle tre topologie. Ogni simulazione ha una durata prestabilita durante la quale l'algoritmo BBM92 stabilisce le chiavi, finché a metà del tempo l'agente "Eve" innesca il guasto/attacco su R1 costringendo l'algoritmo di routing a intervenire.

Per eseguire uno scenario, lancia il relativo file dalla cartella radice:

```bash
# Esegue la baseline lineare (Nessun recupero possibile dopo l'attacco)
python sim_linear.py

# Esegue la topologia a diamante (Recupero ottimale tramite R2)
python sim_diamond.py

# Esegue la topologia asimmetrica (Recupero sub-ottimale a causa della maggiore distanza di R2)
python sim_asymmetric.py
```

I risultati grezzi (.csv e vettori numpy .npz) verranno salvati automaticamente nella cartella `results/` creata a runtime.

---

## 📊 Visualizzazione dei Risultati

Dopo aver eseguito le tre simulazioni per raccogliere i dati, è possibile generare i grafici comparativi di **SKR (Secret Key Rate)**, **QBER** e **Fidelity** per confrontare l'efficacia del routing nelle diverse configurazioni fisiche.

Per farlo, lanciare l'apposito script di plotting:

```bash
python plot_results.py
```

I grafici verranno salvati come immagini (es. `results/comparison_plot.png`) o visualizzati direttamente a schermo tramite finestra Matplotlib, mostrando l'evidente differenza nel comportamento tra le reti statiche e la cyber-resilienza adattiva implementata da HERMES.
