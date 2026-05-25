"""
src/components/nodes.py — Hardware Factory per i nodi della rete HERMES.

Modulo responsabile dell'istanziazione e configurazione dei nodi quantistici
(QuantumNode) e dei relativi processori quantistici locali (QuantumProcessor).

La decoerenza trasversale T₂ viene modellata tramite un DepolarNoiseModel
dipendente dal tempo, associato a ogni slot di memoria del processore.
Il set di istruzioni atomiche (X, Z, MEASURE) è pre-registrato per consentire
le operazioni di correzione attiva e misurazione proiettiva richieste dal
protocollo BBM92.

Le porte fisiche (quantistiche e classiche) del nodo sono generate dinamicamente
a partire dalla configurazione JSON della topologia selezionata a runtime.
"""

import netsquid as ns
from netsquid.components.qprocessor import QuantumProcessor
from netsquid.nodes import Node as QuantumNode
from netsquid.components.models.qerrormodels import DepolarNoiseModel
from netsquid.components.instructions import INSTR_X, INSTR_Z, INSTR_MEASURE

from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
#  Factory Functions
# ---------------------------------------------------------------------------

def create_quantum_processor(
    name: str,
    num_positions: int,
    t2_time: float = 0.0,
) -> QuantumProcessor:
    """
    Configura e restituisce un QuantumProcessor con decoerenza T₂ opzionale.

    Il modello di rumore utilizza `DepolarNoiseModel` con dipendenza temporale
    (`time_independent=False`), in modo che il tasso di depolarizzazione γ
    agisca proporzionalmente al tempo di permanenza del qubit in memoria.

    Il set di istruzioni hardware registrato comprende:
        - INSTR_X   (Porta Pauli-X per la correzione di bit-flip)
        - INSTR_Z   (Porta Pauli-Z per la correzione di phase-flip)
        - INSTR_MEASURE (Misurazione proiettiva nella base computazionale)

    :param name: Nome identificativo del processore (es. "qproc_Alice").
    :param num_positions: Numero di slot di memoria quantistica del processore.
    :param t2_time: Tempo di decoerenza trasversale T₂ in nanosecondi (ns).
                    Se <= 0 o non specificato, il modello di rumore non viene
                    applicato.
    :returns: Oggetto QuantumProcessor configurato.
    """
    # --- Modello di rumore sulla memoria ---
    memory_noise_model = None
    if t2_time > 0:
        # γ = 1 / T₂  [ns⁻¹]
        depolar_rate: float = 1.0 / t2_time
        memory_noise_model = DepolarNoiseModel(
            depolar_rate=depolar_rate,
            time_independent=False,  # dipendenza temporale attiva
        )

    # --- Set di istruzioni atomiche ---
    physical_instructions = [
        ns.components.qprocessor.PhysicalInstruction(INSTR_X, duration=1, parallel=True),
        ns.components.qprocessor.PhysicalInstruction(INSTR_Z, duration=1, parallel=True),
        ns.components.qprocessor.PhysicalInstruction(INSTR_MEASURE, duration=10, parallel=False),
    ]

    # --- Costruzione del processore ---
    qprocessor = QuantumProcessor(
        name=name,
        num_positions=num_positions,
        memory_noise_models=[memory_noise_model] * num_positions,
        phys_instructions=physical_instructions,
    )

    return qprocessor


def build_node(
    node_name: str,
    num_mem_positions: int,
    t2_time: float,
    physical_ports_config: Dict[str, List[str]],
) -> QuantumNode:
    """
    Fabbrica e restituisce un QuantumNode completo per la rete HERMES.

    Il nodo viene dotato di:
        1. Un QuantumProcessor locale (creato via `create_quantum_processor`).
        2. Porte quantistiche dinamiche (nomi letti dal JSON).
        3. Porte classiche dinamiche (nomi letti dal JSON).

    :param node_name: Nome univoco del nodo nella rete (es. "Alice", "R1").
    :param num_mem_positions: Numero di slot di memoria del processore locale.
    :param t2_time: Tempo di decoerenza T₂ in nanosecondi.
    :param physical_ports_config: Dizionario con le chiavi:
        - ``"qports"``: lista di nomi stringa per le porte quantistiche.
        - ``"cports"``: lista di nomi stringa per le porte classiche.
    :returns: Oggetto QuantumNode pronto per essere collegato alla rete.
    """
    # 1. Creazione del processore quantistico locale
    qprocessor = create_quantum_processor(
        name=f"qproc_{node_name}",
        num_positions=num_mem_positions,
        t2_time=t2_time,
    )

    # 2. Istanziazione del nodo
    node = QuantumNode(name=node_name, qmemory=qprocessor)

    # 3. Iniezione delle porte quantistiche
    qport_names = physical_ports_config.get("qports", [])
    if qport_names:
        node.add_ports(qport_names)

    # 4. Iniezione delle porte classiche
    cport_names = physical_ports_config.get("cports", [])
    if cport_names:
        node.add_ports(cport_names)

    return node


def generate_topology_nodes(
    topology_config: dict,
) -> Dict[str, QuantumNode]:
    """
    Orchestratore: costruisce tutti i nodi della rete a partire dal dizionario
    di configurazione della topologia (estratto dal file JSON).

    Il dizionario atteso ha la struttura:

    .. code-block:: json

        {
            "topology_name": "diamond",
            "nodes": {
                "Alice": {
                    "role": "end_node",
                    "type": "source",
                    "active": true
                }
            },
            "channels": [
                {
                    "node1": "Alice",
                    "node2": "R1",
                    "distance_km": 10.0,
                    "has_quantum": true,
                    "has_classical": true
                }
            ],
            "parameters": {
                "memory_T2": 10000000.0
            }
        }

    :param topology_config: Dizionario Python estratto dal JSON di topologia.
    :returns: Dizionario ``{nome_nodo: QuantumNode}`` contenente tutti i nodi
              istanziati e configurati.
    :raises KeyError: Se mancano campi obbligatori nella configurazione.
    """
    nodes: Dict[str, QuantumNode] = {}
    
    params = topology_config.get("parameters", {})
    t2_time = params.get("memory_T2", 0.0)
    
    # Fissiamo 2 slot di memoria per nodo (necessari per BBM92 Entanglement Swapping)
    num_mem = 2 

    for name, node_cfg in topology_config.get("nodes", {}).items():
        if not node_cfg.get("active", True):
            continue
            
        qports = []
        cports = []
        
        # Determiniamo le porte necessarie ispezionando i canali
        for channel in topology_config.get("channels", []):
            if channel["node1"] == name or channel["node2"] == name:
                other_node = channel["node2"] if channel["node1"] == name else channel["node1"]
                
                if channel.get("has_quantum", False):
                    qports.extend([f"qin_{other_node}", f"qout_{other_node}"])
                if channel.get("has_classical", False):
                    cports.extend([f"cin_{other_node}", f"cout_{other_node}"])

        ports_config: Dict[str, List[str]] = {
            "qports": qports,
            "cports": cports,
        }

        node = build_node(
            node_name=name,
            num_mem_positions=num_mem,
            t2_time=t2_time,
            physical_ports_config=ports_config,
        )
        nodes[name] = node

    return nodes


# ---------------------------------------------------------------------------
#  Test Isolato
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os

    # Determina il percorso al file diamond_topology.json relativo a questo script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "..", "..", "config", "diamond_topology.json")
    config_path = os.path.abspath(config_path)

    print("=" * 60)
    print(" HERMES — Test Isolato di nodes.py")
    print("=" * 60)
    print(f"Caricamento topologia da: {config_path}")

    with open(config_path, "r") as f:
        sample_topology_config = json.load(f)

    # Generazione dei nodi dalla configurazione di test
    network_nodes = generate_topology_nodes(sample_topology_config)

    for node_name, node_obj in network_nodes.items():
        qproc = node_obj.qmemory
        print(f"\n[✓] Nodo '{node_name}' istanziato con successo.")
        print(f"    Processore : {qproc.name}")
        print(f"    Slot memoria: {qproc.num_positions}")

        # Verifica modello di rumore sulla memoria (slot 0)
        mem_pos_0 = qproc.subcomponents.get("mem_position0")
        if mem_pos_0 is not None:
            noise_model = mem_pos_0.models.get("noise_model")
            if noise_model is not None:
                gamma = noise_model.properties["depolar_rate"]
                print(f"    Modello T₂  : DepolarNoiseModel (γ = {gamma:.6e} ns⁻¹)")
            else:
                print("    Modello T₂  : Disattivato")
        else:
            print("    Modello T₂  : Nessuna posizione di memoria trovata")

        # Verifica porte fisiche del nodo
        port_names = sorted(node_obj.ports.keys())
        print(f"    Porte       : {port_names}")

    print("\n" + "=" * 60)
    print(" Hardware factory — Tutti i nodi generati correttamente.")
    print("=" * 60)
