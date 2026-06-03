import math
import os
import logging
import netsquid as ns
import numpy as np
import pandas as pd
from netsquid.util.datacollector import DataCollector

logger = logging.getLogger(__name__)

def binary_entropy(p: float) -> float:
    """Calcola l'entropia binaria di Shannon h(p)."""
    if p <= 0 or p >= 1:
        return 0.0
    return -p * math.log2(p) - (1 - p) * math.log2(1 - p)

class MetricsCollector:
    """
    Wrapper specializzato attorno alla classe nativa DataCollector di NetSquid.
    Intercetta i segnali di misurazione a runtime e storicizza l'evoluzione temporale
    della rete quantistica.
    """
    def __init__(self, endpoint_protocols, collection_name="hermes_metrics"):
        """
        Inizializza il raccoglitore di metriche.
        """
        self.endpoint_protocols = endpoint_protocols
        self.collection_name = collection_name
        
        self.collector = DataCollector(
            self._collect_data,
            include_time_stamp=True,
            include_entity_name=True
        )
        
        # Sottoscrizione asincrona ai segnali di aggiornamento
        for proto in self.endpoint_protocols:
            # Assicuriamoci che il protocollo abbia il segnale METRICS_UPDATE registrato
            if hasattr(proto, '_signals') and "METRICS_UPDATE" in proto._signals:
                event_expr = ns.pydynaa.EventExpression(
                    source=proto, 
                    event_type=proto._signals["METRICS_UPDATE"]
                )
                self.collector.collect_on(event_expr)
                logger.debug(f"[{self.collection_name}] Sottoscritto al segnale METRICS_UPDATE di {proto.name}")

    def _collect_data(self, event):
        """
        Funzione di callback interna invocata dal DataCollector al trigger dell'evento.
        
        Estrae QBER, Fidelity e calcola il Secret Key Rate (SKR) stimato.
        Restituisce un dizionario che NetSquid inserirà nel DataFrame temporale.
        """
        result = event.source.get_signal_result("METRICS_UPDATE")
        if not result:
            return {}
            
        qber = result.get("qber", 0.0)
        fidelity = result.get("fidelity", 1.0)
        sifted_key_len = result.get("sifted_key_len", 0)
        
        # Calcolo del Secret Key Rate (SKR) in bps (bit per second)
        # SKR_assoluto = N_sifted * (1 - 2*h(QBER))
        # Rate (bps) = SKR_assoluto / T_secondi
        sim_time_ns = ns.sim_time()
        time_sec = sim_time_ns * 1e-9
        
        skr_bps = 0.0
        if time_sec > 0:
            h_qber = binary_entropy(qber)
            privacy_factor = 1.0 - 2.0 * h_qber
            
            # Se il QBER supera circa l'11%, il fattore diventa negativo (nessuna chiave sicura estraibile)
            if privacy_factor < 0:
                privacy_factor = 0.0
                
            secure_bits = sifted_key_len * privacy_factor
            skr_bps = secure_bits / time_sec
            
        return {
            "node": result.get("node", "Unknown"),
            "qber": qber,
            "fidelity": fidelity,
            "skr_bps": skr_bps,
            "sifted_key_len": sifted_key_len,
            "active_repeater": result.get("active_repeater", "Unknown")
        }

    def start(self):
        """Avvia la raccolta dati."""
        # Il DataCollector di NetSquid raccoglie automaticamente al trigger degli eventi.
        logger.info(f"[{self.collection_name}] DataCollector avviato.")

    def stop(self):
        """Ferma la raccolta dati."""
        logger.info(f"[{self.collection_name}] DataCollector fermato.")

    def get_numpy_arrays(self):
        """
        Restituisce l'andamento temporale delle metriche sotto forma di vettori NumPy.
        
        :return: Dizionario contenente i vettori numpy per time, fidelity, qber e skr.
        """
        df = self.collector.dataframe
        if df is None or df.empty:
            return {}
            
        return {
            "time": df["time_stamp"].to_numpy(),
            "fidelity": df["fidelity"].to_numpy(),
            "qber": df["qber"].to_numpy(),
            "skr": df["skr_bps"].to_numpy(),
            "nodes": df["node"].to_numpy(),
            "active_repeater": df["active_repeater"].to_numpy() if "active_repeater" in df.columns else np.array([])
        }

    def dump_to_csv(self, output_dir="results"):
        df = self.collector.dataframe
        if df is None or df.empty:
            logger.warning(f"[{self.collection_name}] Nessun dato da esportare.")
            return None
            
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{self.collection_name}.csv")
        
        df.to_csv(file_path, index=False)
        logger.info(f"[{self.collection_name}] Dati metrici esportati in {file_path}")
        return file_path
