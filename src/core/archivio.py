"""
src/core/archivio.py
Archivio del lab per la consegna (.tar.gz o .zip), con solo i file della configurazione.

Lo usano la GUI (scheda Archivio) e il terminale (menu principale e post-creazione).
Restano fuori:
- <lab>.xml dentro il lab (lab creati prima che l'XML stesse in .labgenerator/);
- la cartella shared/ vuota che Kathará crea a ogni lstart;
- file e cartelle nascosti (il cui nome inizia con '.');
- residui degli editor (*~, *.swp) e __pycache__.
"""
import os
import re
import tarfile
import zipfile

_RE_NOME = re.compile(r'^[A-Za-z0-9_.-]+$')


def nome_archivio_valido(nome):
    return bool(nome) and bool(_RE_NOME.match(nome)) and nome not in ('.', '..')


def _escluso(nome):
    """Nome di un file o di una cartella del lab da lasciare fuori dall'archivio."""
    return nome.startswith('.') or nome == '__pycache__' or nome.endswith('~') or nome.endswith('.swp')


def contenuto_archivio(base, lab):
    """(file da archiviare, esclusi): percorsi relativi a `base`, con '/'."""
    lab_dir = os.path.join(base, lab)
    esclusi = []
    xml = os.path.join(lab_dir, f"{lab}.xml")
    if os.path.isfile(xml):
        esclusi.append(f"{lab}/{lab}.xml")
    shared = os.path.join(lab_dir, 'shared')
    if os.path.isdir(shared) and not os.listdir(shared):
        esclusi.append(f"{lab}/shared")
    file = []
    for radice, cartelle, nomi in os.walk(lab_dir):
        rel_radice = os.path.relpath(radice, base).replace(os.sep, '/')
        tenute = []
        for c in sorted(cartelle):
            if _escluso(c):
                esclusi.append(f"{rel_radice}/{c}")
            else:
                tenute.append(c)
        cartelle[:] = tenute
        for n in sorted(nomi):
            rel = f"{rel_radice}/{n}"
            if rel in esclusi:
                continue
            if _escluso(n):
                esclusi.append(rel)
                continue
            file.append(rel)
    return file, esclusi


def crea_archivio(base, lab, nome, formato):
    """Crea <base>/<nome>.tar.gz (o .zip) con la cartella del lab senza i file esclusi.
    Restituisce (percorso, elenco dei file, comando equivalente, esclusi)."""
    lab_dir = os.path.join(base, lab)
    file, esclusi = contenuto_archivio(base, lab)
    fuori = set(esclusi)
    if formato == 'zip':
        dest = os.path.join(base, f"{nome}.zip")
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
            for rel in file:
                z.write(os.path.join(base, rel), rel)
        cartelle_escluse = {e for e in esclusi if os.path.isdir(os.path.join(base, e))}
        comando = f"zip -r {nome}.zip {lab} -x " + ' '.join(
            f"'{e}/'" if e.endswith('/shared') else (f"'{e}/*'" if e in cartelle_escluse else f"'{e}'")
            for e in esclusi)
    else:
        dest = os.path.join(base, f"{nome}.tar.gz")

        def filtro(info):
            if info.name in fuori:
                return None
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            return info
        with tarfile.open(dest, 'w:gz') as t:
            t.add(lab_dir, arcname=lab, filter=filtro)
        comando = ' '.join(['tar'] + [f"--exclude='{e}'" for e in esclusi] + [f"-czvf {nome}.tar.gz {lab}"])
    return dest, file, comando, esclusi
