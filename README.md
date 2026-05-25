# HERMES: High-Efficiency Routing for Quantum Entanglement and Messengers

**HERMES** è un simulatore di rete quantistica ad eventi discreti sviluppato in **Python 3** tramite il framework **NetSquid**. Il progetto implementa e analizza un algoritmo di **routing dinamico e adattivo** per la distribuzione dell'entanglement end-to-end tra due nodi terminali (Alice e Bob), superando i limiti di tolleranza ai guasti delle attuali architetture lineari statiche (*single point of failure*).

L'infrastruttura software separa nettamente il **Piano Data Quantistico** (gestione e conservazione dei qubit) dal **Piano di Controllo Classico** (orchestrator di rete e logica decisionale).

---

## 🚀 Obiettivi Scientifici e Vantaggi Competitivi

A differenza delle reti classiche, il routing quantistico deve fare i conti con i vincoli imposti dalla fisica fondamentale (Teorema di No-Cloning) e dalla decoerenza hardware. HERMES dimostra l'efficacia del routing dinamico basato su tre pilastri:

1. **Cyber-Resilienza Attiva:** Monitoraggio runtime del canale tramite protocollo **BBM92** (variante basata su entanglement del BB84). Se un attacco informatico (*Intercept-Resend*) o un degradamento termico spinge il **QBER (Quantum Bit Error Rate) >= 11%** o la **Fidelity F < 0.75**, l'Orchestratore interviene istantaneamente deviando il flusso quantistico senza interrompere la sessione applicativa.
2. **Ottimizzazione del Secret Key Rate (SKR):** Selezione dinamica del cammino a maggiore Fidelity per massimizzare la generazione di chiavi utili dopo la fase classica di *privacy amplification*.
3. **Analisi del Trade-off Geometria-Decoerenza:** Studio quantitativo dell'impatto delle distanze fisiche e del tempo di memorizzazione dei qubit ($T_2$) sulle memorie quantistiche locali quando si devia il traffico su linee asimmetriche.

---

## 📐 Topologie a Confronto

Il simulatore istanzia tre scenari geometrici sottoposti a iniezione di rumore dinamico (`DepolarNoiseModel` e `FibreLossModel`) a metà simulazione ($t_{attack}$):

* **Topologia Lineare (Baseline):** Alice -> R1 -> Bob (20 km totali). Rappresenta il benchmark negativo: un attacco su R1 azzera permanentemente l'SKR.
* **Topologia a Diamante Bilanciata:** Alice, Bob e due ripetitori indipendenti (R1 superiore, R2 inferiore) con tratte equamente bilanciate a 20 km. Scenario di ripristino ideale con SKR che ritorna al 100% dopo lo switch.
* **Topologia Asimmetrica / Triangolare:** Il percorso di backup passante per R2 modella una deviazione geografica svantaggiosa (40 km totali). Permette di mappare il costo della distanza in termini di decoerenza temporale.

---

## 🛠️ Stack Tecnologico e Moduli Core NetSquid

Il simulatore sfrutta i componenti di basso livello del framework per garantire il pieno controllo del livello hardware:
* `QuantumNode` & `QuantumProcessor`: Modellazione hardware dei nodi e dei registri di memoria quantistica, configurati con coefficienti reali di decadimento longitudinale ($T_1$) e trasversale ($T_2$).
* `DepolarNoiseModel` & `FibreLossModel`: Simulazione dei disturbi stocastici e dell'attenuazione della luce in fibra (dB/km).
* `Protocol`: Implementazione asincrona guidata dagli eventi dei quattro protocolli concorrenti (`AliceRoutingProtocol`, `BobRoutingProtocol`, `RepeaterControlProtocol`, ed `EvePerturbationProtocol`).