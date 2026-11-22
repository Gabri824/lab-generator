"""
src/core/cli_io.py
Gestione dell'I/O da terminale, validazioni, navigazione guidata e compatibilità multipiattaforma.
"""
import builtins
import re

# le regole sui singoli valori stanno in modello.py (le usa anche la GUI);
# qui restano le domande, i messaggi a video e la navigazione.
# area_valida, correggi_nome_kathara e nome_kathara_valido sono reimportate per gli altri moduli.
from .modello import (  # noqa: F401
    area_valida,
    asn_valido,
    correggi_nome_kathara,
    errore_area,
    errore_asn,
    errore_destinazione,
    errore_ip,
    errore_ip_cidr,
    errore_ipv4,
    errore_lan,
    errore_nome_lab,
    errore_protocolli,
    nome_kathara_valido,
    parse_reti,
)

# Fix per freccette (cronologia/cursore) e bracketed paste su Linux
try:
    import readline
except ImportError:
    readline = None

_RE_BRACKETED_PASTE = re.compile(r'(?:\x1b\[|\^?\[\[?|~\[)20[01]~')


class TornaIndietro(Exception):
    """'<' digitato: torna alla domanda precedente."""


class RicominciaDispositivo(Exception):
    """'<<' digitato: ricomincia la configurazione del dispositivo corrente."""


class Annullato(Exception):
    """Invio a vuoto durante le domande di una policy: si torna al menu senza scrivere nulla."""


_NAV_ATTIVA = False


def input(prompt=''):
    """Sostituisce input(): rimuove eventuali residui di bracketed paste e intercetta '<' e '<<'."""
    s = builtins.input(prompt)
    s = _RE_BRACKETED_PASTE.sub('', s)
    if _NAV_ATTIVA:
        t = s.strip()
        if t == '<<':
            raise RicominciaDispositivo()
        if t == '<':
            raise TornaIndietro()
    return s


def input_non_vuoto(prompt):
    while True:
        v = input(prompt).strip()
        if v:
            return v


def input_lan(prompt):
    """Chiede il nome della LAN e valida che contenga solo lettere e numeri."""
    while True:
        s = input_non_vuoto(prompt).strip().upper()
        e = errore_lan(s)
        if not e:
            return s
        print(f"❌ {e}")


def input_lab_name(prompt):
    """Chiede il nome del laboratorio: solo minuscole, numeri, '_' e '-'."""
    while True:
        s = input_non_vuoto(prompt).strip()
        e = errore_nome_lab(s)
        if not e:
            return s
        print(f"❌ {e}")


def input_int(prompt, min_val=0):
    while True:
        s = input(prompt).strip()
        try:
            n = int(s)
            if n >= min_val:
                return n
            print(f"❌ Inserisci un intero ≥ {min_val}")
        except ValueError:
            print("❌ Inserisci un numero intero valido")


def valida_ip_cidr(prompt):
    """Valida e ritorna un indirizzo con CIDR (es. 10.0.0.1/24)."""
    while True:
        s = input(prompt).strip()
        e = errore_ip_cidr(s)
        if not e:
            return s
        print(f"❌ {e}")


def valida_ip_senza_cidr(prompt):
    while True:
        s = input(prompt).strip()
        e = errore_ipv4(s)
        if not e:
            return s
        print(f"❌ {e}")


def input_asn(prompt):
    """Numero AS: solo cifre."""
    while True:
        s = input_non_vuoto(prompt).strip()
        e = errore_asn(s)
        if not e:
            return s
        print(f"❌ {e}")


def input_area(prompt, default=None):
    """Area OSPF valida; con un default, Invio a vuoto ritorna il default."""
    while True:
        s = input(prompt).strip()
        if not s and default is not None:
            return default
        if s and not errore_area(s):
            return s
        if s:
            print(f"❌ {errore_area(s)}")


def chiedi_aree_ospf(reti, area, stub):
    """Router di confine OSPF (ABR): area di ogni rete.

    Restituisce (aree, aree_stub): aree = {rete: area}, aree_stub = aree da dichiarare stub;
    (None, None) se tutte le reti stanno in `area` (il caso normale, una sola area)."""
    if len(reti) < 2:
        return None, None
    if input(f"Tutte le network OSPF nell'area {area}? (S/n): ").strip().lower() != 'n':
        return None, None
    aree = {rete: input_area(f"  Area OSPF di {rete} (Invio = {area}): ", default=area) for rete in reti}
    if all(a == area for a in aree.values()):
        return None, None
    aree_stub = [area] if stub and area not in ('0', '0.0.0.0') else []
    for a in dict.fromkeys(aree.values()):
        if a != area and a not in ('0', '0.0.0.0') and input(f"  Area {a} stub? (s/N): ").strip().lower().startswith('s'):
            aree_stub.append(a)
    return aree, aree_stub


def input_destinazione(prompt):
    """Destinazione di una rotta statica: una rete con maschera oppure 'default'."""
    while True:
        s = input_non_vuoto(prompt).strip()
        e = errore_destinazione(s)
        if e:
            print(f"❌ {e}")
            continue
        return 'default' if s.lower() == 'default' else parse_reti(s)[0]


def valida_protocols(prompt):
    while True:
        s = input(prompt).strip().lower().replace(",", " ")
        e = errore_protocolli(s)
        if not e:
            return list(dict.fromkeys(t for t in s.split() if t))
        print(f"❌ {e}")


def input_reti(prompt, default=None, opzionale=False):
    """Chiede una o più reti separate da virgola; invio -> default (se dato)."""
    while True:
        s = input(prompt).strip()
        if not s:
            if default:
                return list(default)
            if opzionale:
                return []
            print("❌ Inserisci almeno una rete (es. 100.0.0.0/8).")
            continue
        try:
            return parse_reti(s)
        except ValueError as e:
            print(f"❌ Rete non valida: {e}")


def valida_gateway(prompt, opzionale=False):
    """IP del gateway, con o senza /prefisso (la maschera viene tolta)."""
    while True:
        s = input(prompt).strip()
        if not s and opzionale:
            return ''
        e = errore_ip(s)
        if not e:
            return s.split('/')[0]
        print(f"❌ {e}" + (", invio per nessuno" if opzionale else ""))


def _si(prompt, default=False):
    r = input(prompt).strip().lower()
    if not r:
        return default
    return r in ('s', 'si', 'sì', 'y')


def _chiedi(prompt, vuoto_ok=False):
    """input() per le policy: Invio a vuoto annulla (salvo vuoto_ok=True)."""
    s = input(prompt).strip()
    if not s and not vuoto_ok:
        raise Annullato()
    return s


def _chiedi_ip(prompt):
    while True:
        s = _chiedi(prompt).split('/')[0]
        if not errore_ip(s):
            return s
        print("❌ IP non valido (es. 10.0.0.2). Invio a vuoto per annullare.")


def _chiedi_asn(prompt):
    while True:
        s = _chiedi(prompt)
        if asn_valido(s):
            return s
        print("❌ Numero AS non valido: solo cifre (es. 20). Invio a vuoto per annullare.")


def _chiedi_int(prompt, min_val=0):
    while True:
        s = _chiedi(prompt)
        if s.isdigit() and int(s) >= min_val:
            return int(s)
        print(f"❌ Inserisci un intero ≥ {min_val}. Invio a vuoto per annullare.")


def _chiedi_reti(prompt, vuoto_ok=False):
    while True:
        s = _chiedi(prompt, vuoto_ok=vuoto_ok)
        if not s:
            return []
        try:
            return parse_reti(s)
        except ValueError as e:
            print(f"❌ Rete non valida: {e}. Invio a vuoto per annullare.")


def _chiedi_direzione():
    while True:
        s = _chiedi('Direzione (in/out): ').lower()
        if s in ('in', 'out'):
            return s
        print("Scrivi 'in' oppure 'out' (Invio a vuoto per annullare).")


def print_menu(title, items, extra_options=None):
    """Stampa un menu ordinato con titolo, una riga vuota, opzioni numerate."""
    print(f"\n{title}\n")
    for i, it in enumerate(items, start=1):
        print(f"  {i}) {it}")
    if extra_options:
        for k, lab in extra_options:
            print(f"  {k}) {lab}")
    print("")


def select_router(routers, prompt="Seleziona router:"):
    keys = list(routers.keys())
    if not keys:
        print("Nessun router disponibile.")
        return None
    items = [f"{k} (ASN: {routers[k].get('asn','-')})" for k in keys]
    print_menu(prompt, items)
    while True:
        sel = input("Numero router (o nome, vuoto per annullare): ").strip()
        if not sel:
            return None
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(keys):
                return keys[idx - 1]
            print("Indice non valido.")
        else:
            if sel in routers:
                return sel
            print("Nome router non valido.")


def select_interface(router_data):
    if not router_data or not router_data.get('interfaces'):
        print('Nessuna interfaccia disponibile per questo router.')
        return None
    ifaces = router_data['interfaces']
    items = [f"{it.get('name')} - {it.get('ip')}" for it in ifaces]
    print_menu('Interfacce disponibili:', items)
    while True:
        sel = input('Seleziona interfaccia (numero o nome, vuoto per annullare): ').strip()
        if not sel:
            return None
        if sel.isdigit():
            idx = int(sel)
            if 1 <= idx <= len(ifaces):
                return ifaces[idx - 1]['name']
            print('Indice non valido.')
        else:
            for it in ifaces:
                if it.get('name') == sel:
                    return sel
            print('Nome interfaccia non valido.')


def esegui_passi(titolo, costruisci_passi, riepilogo):
    """Esegue una sequenza di domande con navigazione e ritorna lo stato confermato."""
    global _NAV_ATTIVA
    prev = _NAV_ATTIVA
    _NAV_ATTIVA = True
    stato = {}
    i = 0
    try:
        while True:
            passi = costruisci_passi(stato) + [lambda st: _conferma(titolo, riepilogo(st))]
            if i >= len(passi):
                return stato
            try:
                passi[i](stato)
                i += 1
            except TornaIndietro:
                if i == 0:
                    print(f"  (sei già alla prima domanda di: {titolo})")
                else:
                    i -= 1
            except RicominciaDispositivo:
                print(f"\n>> Ricomincio da capo: {titolo}")
                stato.clear()
                i = 0
    finally:
        _NAV_ATTIVA = prev


def _conferma(titolo, righe):
    print(f"\n--- Riepilogo {titolo} ---")
    for r in righe:
        print(f"  {r}")
    while True:
        ans = input("Confermi? (s = sì / r = rifai da capo / < = correggi l'ultima risposta) [s]: ").strip().lower()
        if ans in ('', 's', 'si', 'sì'):
            return
        if ans == 'r':
            raise RicominciaDispositivo()
        print("Rispondi s, r oppure <.")