import json
import logging
import os
import numpy as np
import netsquid as ns

from src.components.nodes import generate_topology_nodes
from src.components.channels import HermesQuantumChannel, HermesClassicalChannel
from src.protocols.bbm92_endpoint import BBM92EndpointProtocol
from src.protocols.repeater_node import create_repeater_protocol
from src.protocols.adversary import AdversaryProtocol
from src.utils.metrics_collector import MetricsCollector

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sim_linear")

def connect_nodes(n1, n2, distance_km, has_quantum, has_classical, params):
    """Crea e connette i canali unidirezionali tra due nodi."""
    depolar_rate = params.get("channel_depolar_rate", 0.01)
    attenuation = params.get("fiber_attenuation_db_per_km", 0.2)
    
    channels = []
    
    if has_quantum:
        q_ch_1_to_2 = HermesQuantumChannel(f"qch_{n1.name}_to_{n2.name}", distance_km, depolar_rate, attenuation)
        q_ch_2_to_1 = HermesQuantumChannel(f"qch_{n2.name}_to_{n1.name}", distance_km, depolar_rate, attenuation)
        
        n1.ports[f"qout_{n2.name}"].connect(q_ch_1_to_2.ports["send"])
        q_ch_1_to_2.ports["recv"].connect(n2.ports[f"qin_{n1.name}"])
        
        n2.ports[f"qout_{n1.name}"].connect(q_ch_2_to_1.ports["send"])
        q_ch_2_to_1.ports["recv"].connect(n1.ports[f"qin_{n2.name}"])
        
        channels.extend([q_ch_1_to_2, q_ch_2_to_1])

    if has_classical:
        c_ch_1_to_2 = HermesClassicalChannel(f"cch_{n1.name}_to_{n2.name}", distance_km)
        c_ch_2_to_1 = HermesClassicalChannel(f"cch_{n2.name}_to_{n1.name}", distance_km)
        
        n1.ports[f"cout_{n2.name}"].connect(c_ch_1_to_2.ports["send"])
        c_ch_1_to_2.ports["recv"].connect(n2.ports[f"cin_{n1.name}"])
        
        n2.ports[f"cout_{n1.name}"].connect(c_ch_2_to_1.ports["send"])
        c_ch_2_to_1.ports["recv"].connect(n1.ports[f"cin_{n2.name}"])
        
        channels.extend([c_ch_1_to_2, c_ch_2_to_1])
        
    return channels

def run_linear_simulation():
    # 1. Inizializzazione del Simulatore
    logger.info("Inizializzazione simulatore NetSquid per topologia lineare...")
    ns.sim_reset()

    # 2. Costruzione del Setup Fisico
    config_path = os.path.join("config", "linear_topology.json")
    with open(config_path, "r") as f:
        topology_config = json.load(f)
        
    # Creazione Nodi
    nodes = generate_topology_nodes(topology_config)
    alice = nodes["Alice"]
    bob = nodes["Bob"]
    r1 = nodes["R1"]
    
    # Creazione e connessione Canali
    params = topology_config.get("parameters", {})
    all_channels = []
    for ch_cfg in topology_config.get("channels", []):
        n1 = nodes[ch_cfg["node1"]]
        n2 = nodes[ch_cfg["node2"]]
        dist = ch_cfg["distance_km"]
        hq = ch_cfg.get("has_quantum", False)
        hc = ch_cfg.get("has_classical", False)
        ch_list = connect_nodes(n1, n2, dist, hq, hc, params)
        all_channels.extend(ch_list)
        
    # 3. Assegnazione dei Protocolli
    # Protocolli Endpoint (BBM92)
    alice_proto = BBM92EndpointProtocol(node=alice, is_bob=False, other_node_name="Bob", active_repeater="R1")
    bob_proto = BBM92EndpointProtocol(node=bob, is_bob=True, other_node_name="Alice", active_repeater="R1")
    
    # Protocollo Ripetitore (Entanglement Swapping su R1 in modalità ACTIVE)
    r1_proto = create_repeater_protocol(
        node=r1,
        alice_port_prefix="Alice",
        bob_port_prefix="Bob",
        is_primary=True,
        cycle_time_ns=100
    )
    
    # Avvia i protocolli
    alice_proto.start()
    bob_proto.start()
    r1_proto.start()

    # 4. Iniezione del Pericolo (Adversary)
    # L'attacco scatta al tempo t_attack = 500 ms (500_000_000 ns)
    t_attack_ns = 500e6 
    adversary = AdversaryProtocol(
        name="Eve",
        target_node=r1,
        target_channels=[],
        t_attack=t_attack_ns,
        attack_depolar_rate=0.25 # Altera il depolar_rate di R1
    )
    adversary.start()

    # Inizializza il collettore di metriche
    metrics_collector = MetricsCollector(
        endpoint_protocols=[alice_proto, bob_proto],
        collection_name="linear_metrics"
    )
    metrics_collector.start()

    # 5. Esecuzione e Salvataggio
    logger.info("Avvio della simulazione (durata totale: 1000 ms)...")
    # Facciamo girare la simulazione per 1 secondo (1_000_000_000 ns) 
    # così vediamo l'effetto dell'attacco che avviene a metà
    ns.sim_run(duration=1e9)
    
    logger.info("Simulazione completata. Salvataggio risultati...")
    metrics_collector.stop()
    
    arrays = metrics_collector.get_numpy_arrays()
    if arrays:
        # Salva in .npz
        os.makedirs("results", exist_ok=True)
        npz_path = os.path.join("results", "linear_results.npz")
        np.savez(npz_path, **arrays)
        logger.info(f"Vettori salvati in: {npz_path}")
        
        # Salva in CSV per comodità
        metrics_collector.dump_to_csv("results")
    else:
        logger.warning("Nessun dato raccolto dalla simulazione!")

if __name__ == "__main__":
    run_linear_simulation()
