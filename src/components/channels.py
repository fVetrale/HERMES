import netsquid as ns
from netsquid.components.qchannel import QuantumChannel
from netsquid.components.cchannel import ClassicalChannel
from netsquid.components.models.qerrormodels import DepolarNoiseModel, FibreLossModel
from netsquid.components.models.delaymodels import FibreDelayModel

class HermesQuantumChannel(QuantumChannel):
    """
    Canale Quantistico per la simulazione HERMES.
    
    Implementa le logiche fisiche richieste:
    - FibreLossModel: per simulare la perdita in dB/km proporzionale alla distanza.
    - DepolarNoiseModel: per gestire il rumore di depolarizzazione stocastica.
    - FibreDelayModel: calcola il ritardo basato sulla velocità della luce in fibra.
    """
    
    def __init__(self, name, length, depolar_rate=0.01, attenuation=0.2):
        """
        Inizializza un canale quantistico.
        
        :param name: Nome identificativo del canale.
        :param length: Lunghezza del canale in chilometri (km).
        :param depolar_rate: Parametro del modello di rumore di depolarizzazione (default: 0.01).
        :param attenuation: Attenuazione della fibra ottica in dB/km (default: 0.2).
        """
        # Modello di ritardo: calcola il ritardo di propagazione dei fotoni
        # in fibra ottica (~200.000 km/s)
        delay_model = FibreDelayModel()
        
        # Modello di perdita in fibra ottica dipendente dalla lunghezza
        loss_model = FibreLossModel(p_loss_init=0.0, p_loss_length=attenuation)
        
        # Modello di rumore di depolarizzazione (può essere modificato runtime 
        # per simulare attacchi o degrado hardware portandolo ad es. a 0.25)
        noise_model = DepolarNoiseModel(depolar_rate=depolar_rate, time_independent=True)
        
        super().__init__(
            name=name,
            length=length,
            models={
                "delay_model": delay_model,
                "quantum_loss": loss_model,
                "quantum_noise": noise_model
            }
        )

class HermesClassicalChannel(ClassicalChannel):
    """
    Canale Classico per la simulazione HERMES.
    
    Utilizzato per la trasmissione dei messaggi di heralding dei ripetitori 
    e dei comandi di routing (es. SWITCH_TO_PATH_R2) dall'orchestratore.
    """
    
    def __init__(self, name, length):
        """
        Inizializza un canale classico.
        
        :param name: Nome identificativo del canale.
        :param length: Lunghezza del canale in chilometri (km).
        """
        # Modello di ritardo: calcola il tempo di arrivo dei messaggi classici
        # in base alla velocità della luce nella fibra ottica
        delay_model = FibreDelayModel()
        
        super().__init__(
            name=name,
            length=length,
            models={
                "delay_model": delay_model
            }
        )
