"""
src/protocols/adversary.py — Protocollo Avversario (Eve) per l'attacco dinamico.

Questo modulo definisce il comportamento dell'avversario (Eve), che agisce 
come un demone temporizzato nel simulatore a eventi discreti.
Non scambia messaggi classici, ma altera le proprietà fisiche dell'hardware
a un tempo prestabilito (t_attack).
"""

import netsquid as ns
from netsquid.protocols import Protocol
from netsquid.components.models.qerrormodels import DepolarNoiseModel
import logging

class AdversaryProtocol(Protocol):
    """
    Protocollo indipendente per simulare un attacco (sabotaggio) in corso di simulazione.
    Monitora l'orologio interno e inietta rumore modificando i parametri dei modelli di errore.
    """

    def __init__(self, name="Eve", target_node=None, target_channels=None, t_attack=1e6, attack_depolar_rate=0.25):

        super().__init__(name=name)
        self.target_node = target_node
        self.target_channels = target_channels or []
        self.t_attack = t_attack
        self.attack_depolar_rate = attack_depolar_rate

    def run(self):
        current_time = ns.sim_time()
        time_to_wait = self.t_attack - current_time
        
        if time_to_wait > 0:
            logging.info(f"[{self.name}] In modalità sonno. Attacco programmato al tempo {self.t_attack} ns.")
            yield self.await_timer(time_to_wait)
        
        # Iniezione Dinamica del Rumore (Sabotaggio)
        logging.warning(f"[{self.name}] RISVEGLIO! Tempo {ns.sim_time()} ns. Iniezione del rumore in corso...")

        # Sabotaggio del nodo bersaglio (es. memorie del ripetitore R1)
        if self.target_node is not None:
            qproc = self.target_node.qmemory
            if qproc is not None:
                for i in range(qproc.num_positions):
                    mem_pos = qproc.subcomponents.get(f"mem_position{i}")
                    if mem_pos is not None:
                        noise_model = mem_pos.models.get("noise_model")
                        if isinstance(noise_model, DepolarNoiseModel):
                            noise_model.depolar_rate = self.attack_depolar_rate
                            logging.warning(
                                f"[{self.name}] Sabotata memoria {i} del nodo '{self.target_node.name}': "
                                f"depolar_rate = {self.attack_depolar_rate}"
                            )

        # Sabotaggio dei canali bersaglio collegati
        for channel in self.target_channels:
            # I modelli di rumore nei canali quantistici sono salvati in models["quantum_noise_model"]
            noise_model = channel.models.get("quantum_noise_model")
            if isinstance(noise_model, DepolarNoiseModel):
                noise_model.depolar_rate = self.attack_depolar_rate
                logging.warning(
                    f"[{self.name}] Sabotato canale quantistico '{channel.name}': "
                    f"depolar_rate = {self.attack_depolar_rate}"
                )

        logging.warning(f"[{self.name}] Attacco completato. Parametri fisici alterati oltre la soglia critica.")
