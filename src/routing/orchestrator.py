"""
src/routing/orchestrator.py — Piano di Controllo Classico (Orchestrator) per HERMES.
"""

import logging
import netsquid as ns
from netsquid.protocols import Protocol
from netsquid.components.component import Message

logger = logging.getLogger(__name__)

class OrchestratorProtocol(Protocol):
    """
    L'Orchestrator funge da piano di controllo centralizzato per la rete HERMES.
    Monitora le metriche di sicurezza (QBER, Fidelity) trasmesse dai nodi endpoint.
    Se rileva un attacco (soglia critica superata), invia pacchetti di routing prioritari
    e coordina la riconfigurazione dinamica dell'hardware per dirottare il traffico 
    quantistico sul percorso di backup (R2).
    """

    # Soglie di sicurezza
    THRESHOLD_QBER = 0.11
    THRESHOLD_FIDELITY = 0.75

    def __init__(self, name="Orchestrator", alice_proto=None, bob_proto=None, r1_proto=None, r2_proto=None):
        """
        Inizializza l'Orchestratore e riceve i riferimenti ai protocolli dei nodi.
        """
        super().__init__(name=name)
        self.alice = alice_proto
        self.bob = bob_proto
        self.r1 = r1_proto
        self.r2 = r2_proto
        self.alarm_triggered = False

    def start(self):
        """
        Avvia il protocollo registrandosi ai segnali di telemetria degli endpoint.
        """
        super().start()
        
        # In Netsquid l'handler del segnale deve avere la firma (event) o (event, **kwargs)
        # ma possiamo semplicemente intercettare i segnali METRICS_UPDATE
        class TelemetryListener:
            def __init__(self, orchestrator):
                self.orchestrator = orchestrator
                
            def __call__(self, event_expression):
                pass
                
        # Per semplicità, possiamo avviare un loop interno o usare wait_for
        # ma il modo corretto è usare un generatore run()
        pass

    def run(self):
        """
        Loop di monitoraggio continuo delle metriche.
        """
        logger.info(f"[{self.name}] Avviato. Monitoraggio telemetria in corso...")
        
        # Prepariamo gli eventi da attendere
        ev_alice = self.await_signal(self.alice, "METRICS_UPDATE") if self.alice else None
        ev_bob = self.await_signal(self.bob, "METRICS_UPDATE") if self.bob else None
        
        while not self.alarm_triggered:
            events = []
            if ev_alice: events.append(ev_alice)
            if ev_bob: events.append(ev_bob)
            
            if not events:
                yield self.await_timer(100)
                continue
                
            if len(events) == 1:
                yield events[0]
            else:
                yield events[0] | events[1]
                
            # Controllo soglie dopo il segnale
            if self.alice:
                self._check_metrics(self.alice)
            if self.bob:
                self._check_metrics(self.bob)

    def _check_metrics(self, endpoint_protocol):
        """
        Controlla l'ultimo aggiornamento delle metriche.
        """
        if self.alarm_triggered:
            return
            
        qber = endpoint_protocol.qber
        fidelity = endpoint_protocol.fidelity
        
        if qber >= self.THRESHOLD_QBER or fidelity < self.THRESHOLD_FIDELITY:
            self.trigger_path_switch(endpoint_protocol.node.name, qber, fidelity)

    def trigger_path_switch(self, source_node_name, qber, fidelity):
        """
        All'innesco dell'allarme, coordina lo switch hardware atomico sul ripetitore R2.
        """
        self.alarm_triggered = True
        logger.critical(f"[{self.name}] ALLARME DI SICUREZZA innescato da {source_node_name}!")
        logger.critical(f"[{self.name}] Metriche critiche: QBER = {qber*100:.2f}% (soglia 11%), Fidelity = {fidelity:.2f} (soglia 0.75)")
        logger.critical(f"[{self.name}] Avvio procedura di Path Switching (SWITCH_TO_PATH_R2)...")
        
        # 1. Spegnimento di R1 (Sorgente primaria)
        if self.r1:
            logger.warning(f"[{self.name}] Invio comando di STANDBY a {self.r1.node.name}")
            # Simuliamo l'invio del pacchetto classico prioritario
            msg = Message([self.r1.CMD_SWITCH_TO_STANDBY], header="SWITCH_TO_PATH_R2")
            if self.r1._cin_alice():
                self.r1._cin_alice().tx_input(msg)
            else:
                self.r1._switch_state(self.r1.CMD_SWITCH_TO_STANDBY)  # Fallback

            # Svuotiamo le memorie di R1
            qmem = self.r1.node.qmemory
            if qmem:
                for i in range(qmem.num_positions):
                    try:
                        qmem.pop(positions=[i])
                    except:
                        pass
                logger.warning(f"[{self.name}] Memorie quantistiche di {self.r1.node.name} svuotate.")

        # 2. Accensione di R2 (Sorgente di backup)
        if self.r2:
            logger.warning(f"[{self.name}] Invio comando di ACTIVE a {self.r2.node.name}")
            msg = Message([self.r2.CMD_SWITCH_TO_ACTIVE], header="SWITCH_TO_PATH_R2")
            if self.r2._cin_alice():
                self.r2._cin_alice().tx_input(msg)
            else:
                self.r2._switch_state(self.r2.CMD_SWITCH_TO_ACTIVE) # Fallback

        # 3. Riconfigurazione dei puntatori hardware in Alice e Bob
        logger.warning(f"[{self.name}] Riconfigurazione hardware puntatori di Alice e Bob verso R2...")
        if self.alice:
            self.alice.switch_repeater("R2")
        if self.bob:
            self.bob.switch_repeater("R2")
            
        logger.critical(f"[{self.name}] Path Switching completato con successo. Traffico dirottato su R2.")
