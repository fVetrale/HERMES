import os
import json
import logging
import numpy as np
import netsquid as ns
from netsquid.protocols.protocol import Protocol
from netsquid.components.component import Message

from src.components.nodes import generate_topology_nodes
from src.protocols.bbm92_endpoint import BBM92EndpointProtocol
from src.protocols.repeater_node import create_repeater_protocol, RepeaterState
from src.protocols.adversary import AdversaryProtocol
from src.utils.metrics_collector import MetricsCollector
from src.components.channels import HermesQuantumChannel, HermesClassicalChannel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("sim_diamond")

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

class QuantumRoutingOrchestrator(Protocol):
    def __init__(self, alice_proto, bob_proto, r1_proto, r2_proto, qber_threshold=0.11):
        super().__init__(name="Orchestrator")
        self.alice_proto = alice_proto
        self.bob_proto = bob_proto
        self.r1_proto = r1_proto
        self.r2_proto = r2_proto
        self.qber_threshold = qber_threshold
        self.switched = False

    def run(self):
        if "METRICS_UPDATE" not in self.alice_proto._signals:
            return
            
        event_type = self.alice_proto._signals["METRICS_UPDATE"]
        while not self.switched:
            yield self.await_signal(self.alice_proto, "METRICS_UPDATE")
            
            result = self.alice_proto.get_signal_result("METRICS_UPDATE")
            if not result:
                continue
            
            qber = result.get("qber", 0.0)
            if qber >= self.qber_threshold:
                logger.warning(f"[Orchestrator] QBER critico rilevato ({qber:.2f} >= {self.qber_threshold}). Inizio reindirizzamento R1 -> R2!")
                self.switched = True
                
                # 1. Spegni R1
                r1_cin = self.r1_proto.node.ports.get("cin_Alice")
                if r1_cin:
                    r1_cin.tx_input(Message(["SWITCH_TO_STANDBY"]))
                
                # 2. Accendi R2
                r2_cin = self.r2_proto.node.ports.get("cin_Alice")
                if r2_cin:
                    r2_cin.tx_input(Message(["SWITCH_TO_ACTIVE"]))
                
                # 3. Riconfigura Alice e Bob
                self.alice_proto.switch_repeater("R2")
                self.bob_proto.switch_repeater("R2")

def run_diamond_simulation():
    # 1. Inizializzazione del Simulatore
    logger.info("Inizializzazione simulatore NetSquid per topologia a diamante...")
    ns.sim_reset()

    # 2. Costruzione del Setup Fisico
    config_path = os.path.join("config", "diamond_topology.json")
    with open(config_path, "r") as f:
        topology_config = json.load(f)
        
    # Creazione Nodi
    nodes = generate_topology_nodes(topology_config)
    alice = nodes["Alice"]
    bob = nodes["Bob"]
    r1 = nodes["R1"]
    r2 = nodes["R2"]
    
    # Creazione e connessione Canali
    params = topology_config.get("parameters", {})
    all_channels = []
    for ch_cfg in topology_config.get("channels", []):
        n1 = nodes[ch_cfg["node1"]]
        n2 = nodes[ch_cfg["node2"]]
        dist = ch_cfg["distance_km"]
        has_q = ch_cfg.get("has_quantum", True)
        has_c = ch_cfg.get("has_classical", True)
        channels = connect_nodes(n1, n2, dist, has_q, has_c, params)
        all_channels.extend(channels)
        
    # Aggiunta canale classico diretto Alice-Bob necessario per lo scambio messaggi Sifting (BBM92)
    dist_ab = 20.0
    alice.add_ports(["cout_Bob", "cin_Bob"])
    bob.add_ports(["cout_Alice", "cin_Alice"])
    all_channels.extend(connect_nodes(alice, bob, dist_ab, False, True, params))
        
    # 3. Assegnazione dei Protocolli
    # Protocolli Endpoint (BBM92) - Partono ascoltando R1
    alice_proto = BBM92EndpointProtocol(node=alice, is_bob=False, other_node_name="Bob", active_repeater="R1")
    bob_proto = BBM92EndpointProtocol(node=bob, is_bob=True, other_node_name="Alice", active_repeater="R1")
    
    # Protocollo Ripetitore R1 (ACTIVE)
    r1_proto = create_repeater_protocol(
        node=r1,
        alice_port_prefix="Alice",
        bob_port_prefix="Bob",
        is_primary=True,
        cycle_time_ns=100000
    )
    
    # Protocollo Ripetitore R2 (STANDBY)
    r2_proto = create_repeater_protocol(
        node=r2,
        alice_port_prefix="Alice",
        bob_port_prefix="Bob",
        is_primary=False,
        cycle_time_ns=10000
    )
    # Imposta lo stato iniziale
    r2_proto._state = RepeaterState.STANDBY
    
    # Avvia i protocolli
    alice_proto.start()
    bob_proto.start()
    r1_proto.start()
    r2_proto.start()

    # Orchestratore
    orchestrator = QuantumRoutingOrchestrator(alice_proto, bob_proto, r1_proto, r2_proto)
    orchestrator.start()

    # 4. Iniezione del Pericolo (Adversary)
    # L'attacco scatta al tempo t_attack = 500 ms
    t_attack_ns = 50e6

    # L'Eve distrugge il canale superiore R1
    r1_qchannels = [ch for ch in all_channels if isinstance(ch, HermesQuantumChannel) and ("R1" in ch.name)]

    adversary = AdversaryProtocol(
        name="Eve",
        target_node=r1,
        target_channels=r1_qchannels,
        t_attack=t_attack_ns,
        attack_depolar_rate=0.25 # Altera il depolar_rate di R1
    )
    adversary.start()

    # Inizializza il collettore di metriche
    metrics_collector = MetricsCollector(
        endpoint_protocols=[alice_proto, bob_proto],
        collection_name="diamond_metrics"
    )
    metrics_collector.start()

    # 5. Esecuzione e Salvataggio
    logger.info("Avvio della simulazione diamante (durata totale: 1000 ms)...")
    ns.sim_run(duration=1e9)
    
    logger.info("Simulazione completata. Salvataggio risultati...")
    metrics_collector.stop()
    
    arrays = metrics_collector.get_numpy_arrays()
    if arrays:
        # Salva in .npz
        os.makedirs("results", exist_ok=True)
        npz_path = os.path.join("results", "diamond_results.npz")
        np.savez(npz_path, **arrays)
        logger.info(f"Vettori salvati in: {npz_path}")
        
        # Salva in CSV per comodità
        metrics_collector.dump_to_csv("results")
    else:
        logger.warning("Nessun dato raccolto!")

if __name__ == "__main__":
    run_diamond_simulation()
