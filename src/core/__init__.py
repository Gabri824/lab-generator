"""
src/core/__init__.py
Esporta l'interfaccia pubblica del package core per la CLI e per la GUI.
"""
from .templates import *
from .cli_io import *
from .file_utils import *
from .file_utils import _applica_modifiche, _leggi_righe, _righe_file, _scrivi_esatte, _scrivi_righe
from .net_frr import *
from .net_frr import _as_number, _contiene, _norm_net, _strip_cidr
from .generators import *
from .persistence import *
from .analyzer import *
from .analyzer import _analizza_frr, _descrivi_lista, _descrivi_route_map
from .device_editor import *
from .routing_ops import *
from .wizard import *
from .stato import leggi_stato, senza_testi, righe as righe_testo
from .modifiche import Conflitto, anteprima, nuovo_piano, scrivi_piano
from .modello import completa_lab, problemi_di, valida_lab
from .generazione import genera_lab, lab_conf_da_modello
from .operazioni import OPERAZIONI, ErroreOperazione
from .supporto import cartella_supporto, percorso_xml, sposta_xml_fuori, xml_nel_lab
from .archivio import contenuto_archivio, crea_archivio
