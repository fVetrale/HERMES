import logging
import random
from enum import Enum, auto
from typing import Optional

import netsquid as ns
from netsquid.protocols import NodeProtocol
from netsquid.components.component import Message

logger = logging.getLogger(__name__)

class Basis(Enum):
    Z = 0
    X = 1

class BBM92EndpointProtocol(NodeProtocol):
    """
    Protocollo asincrono per gli endpoint (Alice e Bob) della rete.
    Implementa il protocollo applicativo BBM92 con:
    - Ricezione qubit dal ripetitore attivo.
    - Correzione attiva basata sui messaggi di HERALDING (solo per Bob).
    - Probing statistico (10%) per calcolo runtime di QBER e Fidelity.
    - Sifting classico (90%) per la generazione della chiave.
    """
    def __init__(self, node, is_bob: bool, other_node_name: str, active_repeater: str = "R1", probing_rate: float = 0.1, sample_window: int = 50):
        super().__init__(node=node, name=f"BBM92_{node.name}")
        self.is_bob = is_bob
        self.other_node_name = other_node_name
        self._active_repeater = active_repeater
        self.probing_rate = probing_rate
        self.sample_window = sample_window
        
        self.seq_num = 0
        
        # Buffer di ricezione quantistica e classica
        self.qubit_queue = []
        self.herald_queue = {}
        
        # Sifting / Probing buffers
        self.local_measurements = {}
        self.remote_measurements = {}
        
        self.matched_probes = 0
        self.error_probes = 0
        self.qber = 0.0
        self.fidelity = 1.0
        self.recent_probe_results = [] # Per finestra mobile QBER
        
        self.sifted_key = []
        
        self.add_signal("METRICS_UPDATE")
        
        logger.info(f"[{self.node.name}] Inizializzato BBM92 (is_bob={self.is_bob}, probing={self.probing_rate*100}%)")

    @property
    def qin_active(self):
        return self.node.ports.get(f"qin_{self._active_repeater}")

    @property
    def cin_active(self):
        return self.node.ports.get(f"cin_{self._active_repeater}")

    @property
    def cout_other(self):
        # Porta per notificare l'altro endpoint
        return self.node.ports.get(f"cout_{self.other_node_name}")

    @property
    def cin_other(self):
        # Porta per ricevere notifiche dall'altro endpoint
        return self.node.ports.get(f"cin_{self.other_node_name}")

    def switch_repeater(self, new_repeater: str):
        """
        Commuta l'ascolto su un nuovo ripetitore (es. da R1 a R2) e pulisce i buffer.
        """
        logger.warning(f"[{self.node.name}] Switch routing: {self._active_repeater} -> {new_repeater}")
        self._active_repeater = new_repeater
        self.qubit_queue.clear()
        self.herald_queue.clear()
        self.local_measurements.clear()
        self.remote_measurements.clear()
        self.recent_probe_results.clear()
        self.matched_probes = 0

    def run(self):
        while True:
            # Attendiamo l'arrivo di messaggi su una qualsiasi delle porte rilevanti
            evts = []
            if self.qin_active:
                evts.append(self.await_port_input(self.qin_active))
            if self.cin_active:
                evts.append(self.await_port_input(self.cin_active))
            if self.cin_other:
                evts.append(self.await_port_input(self.cin_other))
                
            if not evts:
                # Nessuna porta valida, attendiamo un istante e riproviamo
                yield self.await_timer(100)
                continue
                
            if len(evts) == 1:
                yield evts[0]
            elif len(evts) == 2:
                yield evts[0] | evts[1]
            elif len(evts) == 3:
                yield evts[0] | evts[1] | evts[2]
            else:
                yield ns.pydynaa.EventExpression.lor(evts)
            
            self._read_inputs()
            self._process_pairs()
            self._process_sifting()

    def _read_inputs(self):
        # 1. Qubits
        if self.qin_active:
            while True:
                msg = self.qin_active.rx_input()
                if msg is None: break
                q = msg.items[0]
                if isinstance(q, list): q = q[0]
                seq = msg.meta.get("seq", -1)
                if seq != -1:
                    self.qubit_queue.append((seq, q))
                
        # 2. Heralds
        if self.cin_active:
            while True:
                msg = self.cin_active.rx_input()
                if msg is None: break
                if msg.meta.get("header") == "HERALDING":
                    seq = msg.meta.get("seq", -1)
                    if seq != -1:
                        self.herald_queue[seq] = (msg.items[0], msg.items[1])
                    
        # 3. Sifting messages dall'altro nodo
        if self.cin_other:
            while True:
                msg = self.cin_other.rx_input()
                if msg is None: break
                if msg.meta.get("header") == "SIFTING":
                    data = msg.items[0]
                    self.remote_measurements[data["seq"]] = data

    def _process_pairs(self):
        qubits_to_keep = []
        for seq, qubit in self.qubit_queue:
            if seq not in self.herald_queue:
                qubits_to_keep.append((seq, qubit))
                continue
                
            m0, m1 = self.herald_queue.pop(seq)
            
            # Correzione Attiva (solo Bob)
            if self.is_bob:
                if m1 == 1:
                    ns.qubits.operate(qubit, ns.X)
                if m0 == 1:
                    ns.qubits.operate(qubit, ns.Z)
                    
            # Selezione base e Probe
            is_probe = (seq % max(1, int(1.0 / self.probing_rate)) == 0)
            basis = Basis.X if random.random() < 0.5 else Basis.Z
            
            # Misurazione
            if basis == Basis.X:
                ns.qubits.operate(qubit, ns.H)
                
            res, _ = ns.qubits.measure(qubit)
            res = int(res)
            
            local_data = {
                "seq": seq,
                "basis": basis,
                "is_probe": is_probe,
                "res": res
            }
            self.local_measurements[seq] = local_data
            
            # Invia classica ad altro endpoint
            if self.cout_other:
                self.cout_other.tx_output(Message([local_data], header="SIFTING"))

            
        self.qubit_queue = qubits_to_keep

    def _process_sifting(self):
        seqs_to_process = [seq for seq in self.local_measurements if seq in self.remote_measurements]
        
        for seq in sorted(seqs_to_process):
            local = self.local_measurements.pop(seq)
            remote = self.remote_measurements.pop(seq)
            
            # Se le basi coincidono
            if local["basis"] == remote["basis"]:
                if local["is_probe"]:
                    is_error = (local["res"] != remote["res"])
                    self.recent_probe_results.append(is_error)
                    if len(self.recent_probe_results) > self.sample_window:
                        self.recent_probe_results.pop(0)
                        
                    self.matched_probes += 1
                    
                    # Calcolo QBER
                    if len(self.recent_probe_results) > 0:
                        self.qber = sum(self.recent_probe_results) / len(self.recent_probe_results)
                        # Approssimazione Fidelity in canale depolarizzante
                        self.fidelity = max(0.0, 1.0 - 1.5 * self.qber)
                        
                    if self.matched_probes % self.sample_window == 0:
                        self.send_signal("METRICS_UPDATE", result={
                            "node": self.node.name,
                            "qber": self.qber,
                            "fidelity": self.fidelity,
                            "matched_probes": self.matched_probes,
                            "sifted_key_len": len(self.sifted_key),
                            "active_repeater": self._active_repeater
                        })
                        logger.debug(f"[{self.node.name}] Metrics Window - QBER: {self.qber:.4f}, Fidelity: {self.fidelity:.4f}")
                        
                else:
                    # Memorizzazione chiave finale
                    self.sifted_key.append(local["res"])


if __name__ == "__main__":
    import os
    import sys
    import json
    
    # Test isolato simile a repeater_node.py
    logging.basicConfig(level=logging.DEBUG)
    ns.sim_reset()
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(current_dir, ".."))
    from components.nodes import generate_topology_nodes
    
    config_path = os.path.join(current_dir, "..", "..", "config", "diamond_topology.json")
    with open(config_path, "r") as f:
        topology = json.load(f)
        
    nodes = generate_topology_nodes(topology)
    alice = nodes.get("Alice")
    bob = nodes.get("Bob")
    
    # Crea protocolli
    proto_alice = BBM92EndpointProtocol(node=alice, is_bob=False, other_node_name="Bob")
    proto_bob = BBM92EndpointProtocol(node=bob, is_bob=True, other_node_name="Alice")
    
    print("[✓] Protocolli Alice e Bob creati con successo.")
