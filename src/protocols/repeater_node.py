"""
src/protocols/repeater_node.py — Protocollo asincrono per i nodi ripetitore HERMES.

Implementa il protocollo guidato dagli eventi (Event-Driven) che gira
permanentemente sui nodi intermedi (R₁, R₂) della rete quantistica.

Responsabilità principali:
    1. Gestione degli stati operativi ACTIVE / STANDBY:
       - R₁ parte in modalità ACTIVE (sorgente a piena potenza).
       - R₂ parte in modalità STANDBY (sorgente attenuata al minimo per
         risparmio energetico e contenimento del rumore, pronta allo switch).
    2. Generazione delle coppie EPR (|Φ⁺⟩) e invio simultaneo dei fotoni
       gemelli verso Alice e Bob attraverso i canali quantistici.
    3. Esecuzione della Bell State Measurement (BSM) sui qubit intrappolati
       in memoria locale, non appena entrambi i lati confermano l'arrivo.
    4. Invio di un messaggio classico di heralding a 2 bit ad Alice e Bob
       con l'esito della misura di Bell per la correzione Pauli (Sifting).

La BSM viene realizzata tramite la sequenza standard:
    CNOT(q₀, q₁) → H(q₀) → MEASURE(q₀) → MEASURE(q₁)
che proietta i due qubit nella base di Bell, producendo un risultato
(m₀, m₁) ∈ {(0,0), (0,1), (1,0), (1,1)} corrispondente rispettivamente
a |Φ⁺⟩, |Ψ⁺⟩, |Φ⁻⟩, |Ψ⁻⟩.
"""

import logging
from enum import Enum, auto
from typing import Optional, Tuple

import netsquid as ns
from netsquid.protocols import NodeProtocol
from netsquid.components.instructions import (
    INSTR_X,
    INSTR_Z,
    INSTR_MEASURE,
    INSTR_CNOT,
    INSTR_H,
)
from netsquid.components.qprocessor import PhysicalInstruction
from netsquid.qubits import ketstates, qubitapi
from netsquid.components.component import Message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
#  Costanti di Protocollo
# ---------------------------------------------------------------------------

class RepeaterState(Enum):
    """Stati operativi del nodo ripetitore."""
    ACTIVE = auto()    # Sorgente a piena potenza — genera e inoltra coppie EPR
    STANDBY = auto()   # Sorgente attenuata — in attesa di comando di switch

# Segnali emessi dal protocollo verso l'orchestratore
SIGNAL_BSM_DONE = "BSM_DONE"
SIGNAL_STATE_SWITCH = "STATE_SWITCH"


# ---------------------------------------------------------------------------
#  Utilità: estensione del gate-set del processore
# ---------------------------------------------------------------------------

def ensure_bsm_capable(qprocessor):
    """
    Verifica che il QuantumProcessor supporti CNOT e H, necessari per la BSM.

    Se le istruzioni non sono già registrate, le aggiunge dinamicamente
    al set di istruzioni fisiche del processore (PhysicalInstruction).

    :param qprocessor: Il QuantumProcessor da validare/estendere.
    """
    existing_instrs = {
        pi.instruction for pi in qprocessor.phys_instructions
    } if hasattr(qprocessor, 'phys_instructions') and qprocessor.phys_instructions else set()

    additions = []
    if INSTR_CNOT not in existing_instrs:
        additions.append(
            PhysicalInstruction(INSTR_CNOT, duration=4, parallel=False)
        )
    if INSTR_H not in existing_instrs:
        additions.append(
            PhysicalInstruction(INSTR_H, duration=1, parallel=True)
        )

    for pi in additions:
        qprocessor.add_physical_instruction(pi)
        logger.debug(
            "Aggiunta istruzione %s al processore %s",
            pi.instruction.name, qprocessor.name,
        )


# ---------------------------------------------------------------------------
#  Protocollo Ripetitore
# ---------------------------------------------------------------------------

class RepeaterProtocol(NodeProtocol):
    """
    Protocollo asincrono NetSquid per i nodi ripetitore (R₁, R₂).

    Il protocollo gira in un loop infinito all'interno del metodo ``run()``
    e, ad ogni iterazione:

        1. Genera una coppia EPR locale nello stato |Φ⁺⟩.
        2. Invia i due fotoni gemelli verso Alice (porta qout_Alice) e
           verso Bob (porta qout_Bob) attraverso i canali quantistici.
        3. Attende la conferma di ricezione (oppure un timeout configurabile).
        4. Esegue la BSM sui qubit rimasti in memoria locale.
        5. Invia il risultato di heralding (2 bit) sulle porte classiche
           (cout_Alice, cout_Bob).

    **Gestione ACTIVE/STANDBY:**

    - Se ``initial_state`` è ``STANDBY``, il protocollo resta in attesa di
      un messaggio ``SWITCH_TO_ACTIVE`` sulla porta classica di controllo
      prima di iniziare a generare coppie.
    - Il passaggio da ``ACTIVE`` a ``STANDBY`` (e viceversa) può essere
      comandato a runtime dall'orchestratore tramite messaggi classici.

    :param node: Il QuantumNode su cui gira il protocollo.
    :param name: Nome univoco dell'istanza del protocollo.
    :param alice_port_prefix: Prefisso delle porte verso Alice (default "Alice").
    :param bob_port_prefix: Prefisso delle porte verso Bob (default "Bob").
    :param initial_state: Stato operativo iniziale (ACTIVE o STANDBY).
    :param cycle_time_ns: Intervallo minimo in ns tra due cicli di generazione
                          (rate-limiting per evitare saturazione della memoria).
    """

    # Messaggi di controllo attesi dall'orchestratore
    CMD_SWITCH_TO_ACTIVE = "SWITCH_TO_ACTIVE"
    CMD_SWITCH_TO_STANDBY = "SWITCH_TO_STANDBY"

    def __init__(
        self,
        node,
        name: Optional[str] = None,
        alice_port_prefix: str = "Alice",
        bob_port_prefix: str = "Bob",
        initial_state: RepeaterState = RepeaterState.ACTIVE,
        cycle_time_ns: float = 0.0,
    ):
        protocol_name = name or f"RepeaterProtocol_{node.name}"
        super().__init__(node=node, name=protocol_name)

        # Prefissi porte (corrispondono alla naming convention di nodes.py)
        self._alice_prefix = alice_port_prefix
        self._bob_prefix = bob_port_prefix

        # Stato operativo
        self._state = initial_state
        self._cycle_time_ns = cycle_time_ns

        # Contatori statistici
        self.bsm_count: int = 0
        self.successful_bsm_count: int = 0

        # Registra i segnali personalizzati
        self.add_signal(SIGNAL_BSM_DONE)
        self.add_signal(SIGNAL_STATE_SWITCH)

        # Assicura che il processore supporti CNOT e H per la BSM
        ensure_bsm_capable(self.node.qmemory)

        logger.info(
            "[%s] Protocollo inizializzato — stato iniziale: %s",
            self.node.name, self._state.name,
        )

    # ------------------------------------------------------------------
    #  Proprietà pubbliche
    # ------------------------------------------------------------------

    @property
    def state(self) -> RepeaterState:
        """Restituisce lo stato operativo corrente del ripetitore."""
        return self._state

    @property
    def is_active(self) -> bool:
        """True se il ripetitore è in modalità ACTIVE."""
        return self._state == RepeaterState.ACTIVE

    # ------------------------------------------------------------------
    #  Porte di rete
    # ------------------------------------------------------------------

    def _qout_alice(self):
        """Porta quantistica in uscita verso Alice."""
        return self.node.ports[f"qout_{self._alice_prefix}"]

    def _qout_bob(self):
        """Porta quantistica in uscita verso Bob."""
        return self.node.ports[f"qout_{self._bob_prefix}"]

    def _cout_alice(self):
        """Porta classica in uscita verso Alice."""
        return self.node.ports[f"cout_{self._alice_prefix}"]

    def _cout_bob(self):
        """Porta classica in uscita verso Bob."""
        return self.node.ports[f"cout_{self._bob_prefix}"]

    def _cin_alice(self):
        """Porta classica in ingresso da Alice (per comandi orchestratore)."""
        return self.node.ports[f"cin_{self._alice_prefix}"]

    def _cin_bob(self):
        """Porta classica in ingresso da Bob (per comandi orchestratore)."""
        return self.node.ports[f"cin_{self._bob_prefix}"]

    # ------------------------------------------------------------------
    #  Metodi di supporto
    # ------------------------------------------------------------------

    def _switch_state(self, new_state: RepeaterState):
        """
        Transizione di stato ACTIVE ↔ STANDBY.

        Emette il segnale SIGNAL_STATE_SWITCH per notificare l'orchestratore
        e aggiorna il logging.
        """
        old_state = self._state
        self._state = new_state
        self.send_signal(SIGNAL_STATE_SWITCH, result={
            "node": self.node.name,
            "from": old_state.name,
            "to": new_state.name,
            "sim_time": ns.sim_time(),
        })
        logger.info(
            "[%s] Transizione di stato: %s → %s (t = %.2f ns)",
            self.node.name, old_state.name, new_state.name, ns.sim_time(),
        )

    def _generate_and_send_photons(self):
        """
        Genera due coppie EPR per l'Entanglement Swapping.
        La prima coppia è condivisa tra Alice e il ripetitore (posizione 0).
        La seconda coppia è condivisa tra Bob e il ripetitore (posizione 1).
        I qubit per Alice e Bob vengono inviati subito.
        """
        qmem = self.node.qmemory

        # Coppia A: per Alice e Ripetitore
        qA_Alice, qA_Rep = qubitapi.create_qubits(2)
        qubitapi.assign_qstate([qA_Alice, qA_Rep], ketstates.b00)
        
        # Coppia B: per Bob e Ripetitore
        qB_Bob, qB_Rep = qubitapi.create_qubits(2)
        qubitapi.assign_qstate([qB_Bob, qB_Rep], ketstates.b00)

        # I qubit locali restano al ripetitore per la BSM
        qmem.put(qA_Rep, positions=[0])
        qmem.put(qB_Rep, positions=[1])

        # Invio attraverso le porte quantistiche
        seq = self.bsm_count
        msg_alice = Message(qA_Alice, seq=seq)
        msg_bob = Message(qB_Bob, seq=seq)
        self._qout_alice().tx_output(msg_alice)
        self._qout_bob().tx_output(msg_bob)

        logger.debug(
            "[%s] Coppie EPR generate. Fotoni inviati → Alice (qout_%s) e Bob (qout_%s) (t = %.2f ns)",
            self.node.name, self._alice_prefix, self._bob_prefix, ns.sim_time(),
        )

    def _perform_bsm(self) -> Tuple[int, int]:
        """
        Esegue la Bell State Measurement (BSM) sui due qubit
        attualmente in memoria locale (posizioni 0 e 1).

        Sequenza gate:
            1. CNOT(q₀, q₁)  — q₀ = control, q₁ = target
            2. H(q₀)         — Hadamard sul qubit di controllo
            3. MEASURE(q₀)   — Misura nella base computazionale {|0⟩, |1⟩}
            4. MEASURE(q₁)   — Misura nella base computazionale {|0⟩, |1⟩}

        :returns: Tupla ``(m0, m1)`` con i risultati della misura.
                  La codifica del risultato della BSM è:
                    (0, 0) → |Φ⁺⟩  — nessuna correzione necessaria
                    (0, 1) → |Ψ⁺⟩  — correzione X su Bob
                    (1, 0) → |Φ⁻⟩  — correzione Z su Bob
                    (1, 1) → |Ψ⁻⟩  — correzione X + Z su Bob
        """
        qmem = self.node.qmemory

        # Recupera i qubit dalla memoria senza rimuoverli (peek)
        q0 = qmem.peek(positions=[0])[0]
        q1 = qmem.peek(positions=[1])[0]

        # 1. CNOT: q₀ (control) → q₁ (target)
        ns.qubits.operate([q0, q1], ns.CNOT)

        # 2. Hadamard su q₀
        ns.qubits.operate(q0, ns.H)

        # 3. Misura entrambi nella base computazionale
        m0, _ = ns.qubits.measure(q0)
        m1, _ = ns.qubits.measure(q1)

        # Pulizia della memoria dopo la misura
        qmem.pop(positions=[0])
        qmem.pop(positions=[1])

        self.bsm_count += 1
        logger.debug(
            "[%s] BSM completata: (m₀, m₁) = (%d, %d) (t = %.2f ns)",
            self.node.name, m0, m1, ns.sim_time(),
        )

        return int(m0), int(m1)

    def _send_heralding(self, m0: int, m1: int):
        """
        Invia il risultato della BSM come messaggio classico a 2 bit
        ad Alice e Bob per permettere la correzione Pauli (Sifting).

        Il messaggio è una tupla ``(m0, m1)`` inviata sulle porte
        classiche di uscita.

        :param m0: Risultato della misura sul qubit 0 (control).
        :param m1: Risultato della misura sul qubit 1 (target).
        """
        seq = self.bsm_count - 1
        heralding_msg = Message([m0, m1], header="HERALDING", seq=seq)

        self._cout_alice().tx_output(heralding_msg)
        self._cout_bob().tx_output(heralding_msg)

        self.successful_bsm_count += 1

        logger.info(
            "[%s] Heralding inviato ad Alice e Bob: (m₀=%d, m₁=%d) — "
            "BSM #%d (t = %.2f ns)",
            self.node.name, m0, m1, self.bsm_count, ns.sim_time(),
        )

    # ------------------------------------------------------------------
    #  Gestione comandi dall'orchestratore
    # ------------------------------------------------------------------

    def _check_control_messages(self):
        """
        Controlla le porte classiche in ingresso per eventuali comandi
        di switch dall'orchestratore (non bloccante).

        Messaggi riconosciuti:
            - ``SWITCH_TO_ACTIVE``:  Transizione STANDBY → ACTIVE
            - ``SWITCH_TO_STANDBY``: Transizione ACTIVE  → STANDBY
        """
        for port_fn in (self._cin_alice, self._cin_bob):
            try:
                port = port_fn()
            except KeyError:
                continue

            msg = port.rx_input()
            if msg is None:
                continue

            for item in msg.items:
                if item == self.CMD_SWITCH_TO_ACTIVE and not self.is_active:
                    self._switch_state(RepeaterState.ACTIVE)
                elif item == self.CMD_SWITCH_TO_STANDBY and self.is_active:
                    self._switch_state(RepeaterState.STANDBY)

    # ------------------------------------------------------------------
    #  Loop principale del protocollo (Event-Driven)
    # ------------------------------------------------------------------

    def run(self):
        """
        Loop asincrono principale del protocollo ripetitore.

        Comportamento:
            - In modalità **STANDBY**: il protocollo resta in ascolto
              sulle porte classiche, in attesa di un comando
              ``SWITCH_TO_ACTIVE`` dall'orchestratore. In questo stato
              la sorgente è attenuata al minimo (nessuna generazione
              di coppie EPR) per risparmiare risorse e limitare il
              rumore di fondo.
            - In modalità **ACTIVE**: il protocollo esegue il ciclo
              completo di entanglement generation → BSM → heralding.

        Il loop non termina mai: il protocollo gira per tutta la durata
        della simulazione NetSquid.
        """
        logger.info(
            "[%s] Protocollo avviato — stato: %s (t = %.2f ns)",
            self.node.name, self._state.name, ns.sim_time(),
        )

        while True:
            # ── STANDBY: attendi comando di attivazione ──────────────
            if not self.is_active:
                logger.debug(
                    "[%s] In STANDBY — in attesa di SWITCH_TO_ACTIVE...",
                    self.node.name,
                )
                # Attende un messaggio su una qualsiasi delle porte classiche
                # di ingresso (da Alice o da Bob / orchestratore)
                evt_expr = (
                    self.await_port_input(self._cin_alice()) |
                    self.await_port_input(self._cin_bob())
                )
                yield evt_expr
                self._check_control_messages()
                continue  # Rientra nel loop per rivalutare lo stato

            # ── ACTIVE: ciclo di generazione EPR + BSM + Heralding ───

            # 1 & 2. Genera due coppie EPR e invia i qubit esterni ad Alice e Bob
            self._generate_and_send_photons()

            # 3. Attendi conferma di ricezione da entrambi i lati
            #    (i qubit in memoria sono già stati inviati, ora attendiamo
            #     che i canali quantistici completino la consegna prima
            #     di procedere con la BSM sui qubit trattenuti localmente)
            #
            #    In questa implementazione, la BSM viene eseguita
            #    immediatamente sui qubit locali (entanglement swapping):
            #    il ripetitore ha già generato la coppia e inviato i fotoni,
            #    quindi può misurare i propri qubit subito.

            # 4. Esegui la Bell State Measurement sui qubit locali
            m0, m1 = self._perform_bsm()

            # 6. Invia i risultati di heralding ad Alice e Bob
            self._send_heralding(m0, m1)

            # 7. Emetti segnale BSM_DONE per l'orchestratore
            self.send_signal(SIGNAL_BSM_DONE, result={
                "node": self.node.name,
                "bsm_result": (m0, m1),
                "sim_time": ns.sim_time(),
            })

            # 8. Controlla eventuali comandi di switch pendenti
            self._check_control_messages()

            # 9. Rate-limiting: attendi il tempo minimo tra cicli
            if self._cycle_time_ns > 0:
                yield self.await_timer(duration=self._cycle_time_ns)

            # 10. Controlla di nuovo eventuali comandi arrivati durante
            #     il timer di rate-limiting
            self._check_control_messages()

            # Yield per cedere il controllo al simulatore prima del
            # prossimo ciclo (evita busy-loop a tempo zero)
            if self._cycle_time_ns <= 0:
                yield self.await_timer(duration=1)


# ---------------------------------------------------------------------------
#  Factory Function
# ---------------------------------------------------------------------------

def create_repeater_protocol(
    node,
    alice_port_prefix: str = "Alice",
    bob_port_prefix: str = "Bob",
    is_primary: bool = True,
    cycle_time_ns: float = 0.0,
) -> RepeaterProtocol:
    """
    Factory function per la creazione del protocollo ripetitore.

    Determina automaticamente lo stato iniziale in base al ruolo:
        - ``is_primary=True``  → R₁ parte in ACTIVE
        - ``is_primary=False`` → R₂ parte in STANDBY

    :param node: Il QuantumNode su cui installare il protocollo.
    :param alice_port_prefix: Prefisso porte verso Alice.
    :param bob_port_prefix: Prefisso porte verso Bob.
    :param is_primary: Se True, il nodo è il ripetitore primario (ACTIVE).
    :param cycle_time_ns: Intervallo minimo tra cicli di generazione (ns).
    :returns: Istanza configurata di RepeaterProtocol.
    """
    initial_state = (
        RepeaterState.ACTIVE if is_primary else RepeaterState.STANDBY
    )

    protocol = RepeaterProtocol(
        node=node,
        alice_port_prefix=alice_port_prefix,
        bob_port_prefix=bob_port_prefix,
        initial_state=initial_state,
        cycle_time_ns=cycle_time_ns,
    )

    logger.info(
        "Protocollo creato per %s — ruolo: %s — stato iniziale: %s",
        node.name,
        "primary" if is_primary else "backup",
        initial_state.name,
    )

    return protocol


# ---------------------------------------------------------------------------
#  Test Isolato
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Reset del simulatore
    ns.sim_reset()

    # Percorso alla topologia di test
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(
        current_dir, "..", "..", "config", "diamond_topology.json"
    )
    config_path = os.path.abspath(config_path)

    print("=" * 65)
    print(" HERMES — Test Isolato di repeater_node.py")
    print("=" * 65)
    print(f"Caricamento topologia da: {config_path}")

    with open(config_path, "r") as f:
        topology = json.load(f)

    # Importa la factory dei nodi
    import sys
    sys.path.insert(0, os.path.join(current_dir, ".."))
    from components.nodes import generate_topology_nodes

    # Genera i nodi dalla topologia
    nodes = generate_topology_nodes(topology)

    # Verifica la presenza dei ripetitori
    r1 = nodes.get("R1")
    r2 = nodes.get("R2")

    if r1 is None or r2 is None:
        print("[✗] Topologia non valida: servono R1 e R2 (usa diamond_topology).")
        exit(1)

    print(f"\n[✓] Nodi generati: {list(nodes.keys())}")

    # Crea i protocolli per R1 (primary/ACTIVE) e R2 (backup/STANDBY)
    proto_r1 = create_repeater_protocol(
        node=r1,
        alice_port_prefix="Alice",
        bob_port_prefix="Bob",
        is_primary=True,
        cycle_time_ns=100,
    )

    proto_r2 = create_repeater_protocol(
        node=r2,
        alice_port_prefix="Alice",
        bob_port_prefix="Bob",
        is_primary=False,
        cycle_time_ns=100,
    )

    print(f"\n[✓] Protocollo R1: stato = {proto_r1.state.name}")
    print(f"[✓] Protocollo R2: stato = {proto_r2.state.name}")

    # Test della BSM isolata (senza rete, solo logica locale)
    print("\n" + "-" * 65)
    print(" Test BSM isolata su R1")
    print("-" * 65)

    # Genera e misura manualmente
    proto_r1._generate_and_send_photons()
    m0, m1 = proto_r1._perform_bsm()
    print(f"[✓] BSM completata: (m₀, m₁) = ({m0}, {m1})")
    print(f"    Contatore BSM: {proto_r1.bsm_count}")

    # Test dello switch di stato su R2
    print("\n" + "-" * 65)
    print(" Test switch di stato STANDBY → ACTIVE su R2")
    print("-" * 65)

    print(f"    Stato iniziale R2: {proto_r2.state.name}")
    proto_r2._switch_state(RepeaterState.ACTIVE)
    print(f"    Stato dopo switch: {proto_r2.state.name}")
    assert proto_r2.is_active, "R2 dovrebbe essere ACTIVE dopo lo switch"
    print("[✓] Switch di stato funzionante")

    # Test dello switch inverso
    proto_r2._switch_state(RepeaterState.STANDBY)
    print(f"    Stato dopo rollback: {proto_r2.state.name}")
    assert not proto_r2.is_active, "R2 dovrebbe essere STANDBY dopo il rollback"
    print("[✓] Rollback di stato funzionante")

    print("\n" + "=" * 65)
    print(" repeater_node.py — Tutti i test superati con successo.")
    print("=" * 65)
