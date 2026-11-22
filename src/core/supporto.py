"""
src/core/supporto.py
File di supporto del generatore: stanno fuori dalla cartella del lab, così il lab contiene solo
i file della configurazione ed è sempre pronto da consegnare.

    <cartella dei lab>/
    ├── <lab>/                         il lab
    ├── .backup_labgenerator/<lab>/    copie di sicurezza (file_utils.copia_di_sicurezza)
    └── .labgenerator/<lab>/
        ├── <lab>.xml                  metadati (rigenerati dai file dopo ogni scrittura)
        └── disegno.json               posizioni del disegno nella GUI

È l'unico punto che decide questi percorsi.
"""
import os
import shutil

CARTELLA = '.labgenerator'


def cartella_supporto(lab_path):
    lab = os.path.abspath(lab_path)
    return os.path.join(os.path.dirname(lab), CARTELLA, os.path.basename(lab))


def nome_lab(lab_path):
    return os.path.basename(os.path.normpath(lab_path))


def percorso_xml(lab_path, nome=None):
    """Dove sta l'XML dei metadati del lab."""
    return os.path.join(cartella_supporto(lab_path), f"{nome or nome_lab(lab_path)}.xml")


def percorso_disegno(lab_path):
    """Dove la GUI salva la disposizione del disegno."""
    return os.path.join(cartella_supporto(lab_path), 'disegno.json')


def xml_nel_lab(lab_path):
    """Percorso dell'XML rimasto dentro il lab (lab creati prima della fase 1.7), oppure None."""
    p = os.path.join(lab_path, f"{nome_lab(lab_path)}.xml")
    return p if os.path.isfile(p) else None


def sposta_xml_fuori(lab_path):
    """Sposta l'XML di un lab vecchio da dentro il lab a .labgenerator/<lab>/, dopo la copia di
    sicurezza. Se fuori c'è già un XML (rigenerato dai file, quindi più aggiornato), tiene quello e
    toglie solo quello dentro. Restituisce (percorso dell'XML fuori, copia di sicurezza)."""
    from .file_utils import copia_di_sicurezza
    dentro = xml_nel_lab(lab_path)
    if not dentro:
        return None, None
    copia = copia_di_sicurezza(lab_path)
    fuori = percorso_xml(lab_path)
    os.makedirs(os.path.dirname(fuori), exist_ok=True)
    if os.path.exists(fuori):
        os.remove(dentro)
    else:
        shutil.move(dentro, fuori)
    return fuori, copia
