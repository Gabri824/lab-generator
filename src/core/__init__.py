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
from .analyzer import _analizza_frr, _descrivi_lista, _descrivi_route_map, _problemi_di
from . import frr_autofix
from .device_editor import *
from .routing_ops import *
from .wizard import *
from . import ops_api
