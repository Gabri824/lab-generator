"""
src/core/persistence.py
Esportazione/Importazione XML e JSON, parsing di lab.conf/startup, ricostruzione metadati e rinomina dispositivi.
"""
import ipaddress
import json
import os
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .cli_io import correggi_nome_kathara, input, nome_kathara_valido
from .modello import errore_nome_dispositivo, errore_nome_usato
from .net_frr import iface_for_nexthop
from .stato import leggi_stato, parse_lab_conf_for_nodes
from .supporto import percorso_xml


def _chiedi_nome(tipo, default, usati):
    """Chiede il nome di un dispositivo verificando validità Kathará e unicità."""
    s = None
    while True:
        if s is None:
            s = input(f"\nNome {tipo} (default {default}): ").strip() or default
        e = errore_nome_dispositivo(s)
        if e:
            proposta = correggi_nome_kathara(s)
            print(f"❌ {e}")
            r = input(f"Usare '{proposta}'? (S/n, oppure scrivi un altro nome): ").strip()
            if r.lower() in ('', 's', 'si', 'sì'):
                s = proposta
            elif r.lower() == 'n':
                s = None
            else:
                s = r
            continue
        if errore_nome_usato(s, usati):
            print(errore_nome_usato(s, usati))
            s = None
            continue
        return s


def export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws, resolver=None, stampa=True):
    """Esporta una rappresentazione XML del laboratorio in .labgenerator/<lab>/<lab_name>.xml,
    fuori dalla cartella del lab (core/supporto.py).

    resolver: nome del server DNS scelto come resolver di tutti i dispositivi (o None)."""
    try:
        root = ET.Element('lab', attrib={'name': lab_name})

        routers_el = ET.SubElement(root, 'routers')
        for rname, rdata in routers.items():
            r_el = ET.SubElement(routers_el, 'router', attrib={'name': rname})
            prot_el = ET.SubElement(r_el, 'protocols')
            for p in rdata.get('protocols', []):
                p_el = ET.SubElement(prot_el, 'protocol')
                p_el.text = str(p)
            asn = rdata.get('asn', '')
            if asn:
                asn_el = ET.SubElement(r_el, 'asn')
                asn_el.text = str(asn)
            if rdata.get('ospf_area'):
                oa = ET.SubElement(r_el, 'ospf_area')
                oa.text = str(rdata.get('ospf_area'))
                if rdata.get('ospf_area_stub'):
                    oas = ET.SubElement(r_el, 'ospf_area_stub')
                    oas.text = '1'
            if rdata.get('ospf_aree'):
                aree_el = ET.SubElement(r_el, 'ospf_aree')
                for rete, area in rdata['ospf_aree'].items():
                    ET.SubElement(aree_el, 'rete', attrib={'area': str(area)}).text = str(rete)
            if rdata.get('ospf_aree_stub'):
                stub_el = ET.SubElement(r_el, 'ospf_aree_stub')
                for area in rdata['ospf_aree_stub']:
                    ET.SubElement(stub_el, 'area').text = str(area)
            if isinstance(rdata.get('ospf_extra_areas'), dict):
                extra_el = ET.SubElement(r_el, 'ospf_extra_areas')
                for k, v in rdata.get('ospf_extra_areas', {}).items():
                    e = ET.SubElement(extra_el, 'area', attrib={'first_octet': str(k)})
                    if isinstance(v, dict):
                        if v.get('area'):
                            ET.SubElement(e, 'id').text = str(v.get('area'))
                        if v.get('stub'):
                            ET.SubElement(e, 'stub').text = '1'
                    else:
                        ET.SubElement(e, 'id').text = str(v)
            if 'interfaces' in rdata:
                ifs_el = ET.SubElement(r_el, 'interfaces')
                for iface in rdata['interfaces']:
                    i_el = ET.SubElement(ifs_el, 'interface')
                    i_el.set('name', iface.get('name', ''))
                    i_el.set('lan', iface.get('lan', ''))
                    i_el.set('ip', iface.get('ip', ''))
            if rdata.get('igp_redistribute_bgp') is False:
                ET.SubElement(r_el, 'igp_redistribute_bgp').text = '0'
            for key, tag in (('igp_networks', 'igp_network'), ('bgp_extra_networks', 'bgp_extra_network')):
                if rdata.get(key):
                    el = ET.SubElement(r_el, key)
                    for n in rdata[key]:
                        ET.SubElement(el, tag).text = str(n)
            if rdata.get('loopbacks'):
                lbs_el = ET.SubElement(r_el, 'loopbacks')
                for lb in rdata['loopbacks']:
                    ET.SubElement(lbs_el, 'loopback').text = str(lb)
            if rdata.get('static_routes'):
                sr_el = ET.SubElement(r_el, 'static_routes')
                for sr in rdata['static_routes']:
                    if isinstance(sr, dict):
                        ET.SubElement(sr_el, 'route', attrib={k: str(v) for k, v in sr.items() if v})
                    else:
                        ET.SubElement(sr_el, 'route', attrib={'cmd': str(sr)})

        hosts_el = ET.SubElement(root, 'hosts')
        for h in hosts:
            h_ifaces = h.get('interfaces') or []
            first = h_ifaces[0] if h_ifaces else {}
            h_attrib = {
                'name': h.get('name', ''),
                'ip': h.get('ip') or first.get('ip', ''),
                'gateway': h.get('gateway') or '',
                'lan': h.get('lan') or first.get('lan', '')
            }
            if h.get('gw_dev'):
                h_attrib['gw_dev'] = h.get('gw_dev')
            if h.get('image'):
                h_attrib['image'] = h.get('image')
            if h.get('nameserver'):
                h_attrib['nameserver'] = ','.join(h['nameserver'])
            h_el = ET.SubElement(hosts_el, 'host', attrib=h_attrib)
            if h_ifaces:
                ifs_el = ET.SubElement(h_el, 'interfaces')
                for iface in h_ifaces:
                    ET.SubElement(
                        ifs_el, 'interface',
                        attrib={
                            'name': iface.get('name', ''),
                            'lan': iface.get('lan', ''),
                            'ip': iface.get('ip', '')
                        }
                    )
            if h.get('dns'):
                ET.SubElement(h_el, 'dns').text = '1'
                if h.get('root_type'):
                    ET.SubElement(h_el, 'root_type').text = str(h.get('root_type'))
                if isinstance(h.get('forwarders'), list):
                    fw_el = ET.SubElement(h_el, 'forwarders')
                    for fwd in h.get('forwarders'):
                        ET.SubElement(fw_el, 'forwarder').text = str(fwd)
                if isinstance(h.get('zones'), dict):
                    zones_el = ET.SubElement(h_el, 'zones')
                    for zname, records in h.get('zones').items():
                        z_el = ET.SubElement(zones_el, 'zone', attrib={'name': zname})
                        if isinstance(records, dict):
                            for rname, rip in records.items():
                                rec = ET.SubElement(z_el, 'record', attrib={'name': rname})
                                if isinstance(rip, dict):
                                    for k, v in rip.items():
                                        c = ET.SubElement(rec, k)
                                        c.text = str(v)
                                else:
                                    rec.text = str(rip)
                if h.get('allow_recursion'):
                    ET.SubElement(h_el, 'allow_recursion').text = str(h.get('allow_recursion'))
                if h.get('dnssec_validation'):
                    ET.SubElement(h_el, 'dnssec_validation').text = '1'
                if h.get('delegations'):
                    dl_el = ET.SubElement(h_el, 'delegations')
                    for dl in h['delegations']:
                        ET.SubElement(dl_el, 'delegation', attrib={k: str(dl.get(k, '')) for k in ('zone', 'ns', 'ip')})

        www_el = ET.SubElement(root, 'www')
        for w in wwws:
            w_attrib = {
                'name': w.get('name', ''),
                'ip': w.get('ip', ''),
                'gateway': w.get('gateway', ''),
                'lan': w.get('lan', '')
            }
            if w.get('image'):
                w_attrib['image'] = w.get('image')
            if w.get('nameserver'):
                w_attrib['nameserver'] = ','.join(w['nameserver'])
            ET.SubElement(www_el, 'server', attrib=w_attrib)

        if resolver:
            ET.SubElement(root, 'resolver').text = str(resolver)

        try:
            with open(os.path.join(lab_path, 'lab.conf'), 'r', encoding='utf-8') as f:
                labconf = f.read()
            lc_el = ET.SubElement(root, 'lab_conf')
            lc_el.text = labconf
        except Exception:
            pass

        rough = ET.tostring(root, 'utf-8')
        reparsed = minidom.parseString(rough)
        pretty = reparsed.toprettyxml(indent='  ', encoding='utf-8')

        out_path = percorso_xml(lab_path, lab_name)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(pretty)
        if stampa:
            print(f"\n\n✅ Esportato XML: {out_path}")
    except Exception as e:
        print('Errore esportazione XML:', e)


def load_lab_from_xml(path):
    """Carica un lab da file XML generato dallo script."""
    tree = ET.parse(path)
    root = tree.getroot()
    lab_name = root.attrib.get('name') or os.path.splitext(os.path.basename(path))[0]

    routers = {}
    for r in root.findall('./routers/router'):
        rname = r.attrib.get('name')
        protocols = [p.text for p in r.findall('./protocols/protocol') if p.text]
        asn_el = r.find('asn')
        asn = asn_el.text if asn_el is not None else ''
        ospf_area = None
        ospf_stub = False
        oa_el = r.find('ospf_area')
        if oa_el is not None and oa_el.text:
            ospf_area = oa_el.text
        oas_el = r.find('ospf_area_stub')
        if oas_el is not None:
            ospf_stub = True

        extra_areas = {}
        for ea in r.findall('./ospf_extra_areas/area'):
            key = ea.attrib.get('first_octet')
            aid = ea.findtext('id')
            stub = ea.findtext('stub') is not None
            if key:
                if aid:
                    extra_areas[str(key)] = {'area': aid, 'stub': stub}
                else:
                    extra_areas[str(key)] = {'area': None, 'stub': stub}

        interfaces = []
        for it in r.findall('./interfaces/interface'):
            interfaces.append({
                'name': it.attrib.get('name', ''),
                'lan': it.attrib.get('lan', ''),
                'ip': it.attrib.get('ip', '')
            })
        rd = {'protocols': protocols, 'asn': asn, 'interfaces': interfaces}
        if ospf_area:
            rd['ospf_area'] = ospf_area
            rd['ospf_area_stub'] = ospf_stub
        if extra_areas:
            rd['ospf_extra_areas'] = extra_areas
        aree = {e.text.strip(): e.attrib.get('area', '') for e in r.findall('./ospf_aree/rete') if e.text}
        if aree:
            rd['ospf_aree'] = aree
            rd['ospf_aree_stub'] = [e.text.strip() for e in r.findall('./ospf_aree_stub/area') if e.text]
        for key, tag in (('igp_networks', 'igp_network'), ('bgp_extra_networks', 'bgp_extra_network')):
            vals = [e.text.strip() for e in r.findall(f'./{key}/{tag}') if e.text]
            if vals:
                rd[key] = vals
        if (r.findtext('igp_redistribute_bgp') or '').strip() == '0':
            rd['igp_redistribute_bgp'] = False
        loopbacks = [lb.text for lb in r.findall('./loopbacks/loopback') if lb.text]
        if loopbacks:
            rd['loopbacks'] = loopbacks
        static_routes = []
        for sr in r.findall('./static_routes/route'):
            if sr.attrib.get('cmd') and len(sr.attrib) == 1:
                static_routes.append(sr.attrib['cmd'])
            else:
                static_routes.append(dict(sr.attrib))
        if static_routes:
            rd['static_routes'] = static_routes
        routers[rname] = rd

    hosts = []
    for h in root.findall('./hosts/host'):
        name = h.attrib.get('name', '')
        ip = h.attrib.get('ip', '')
        gateway = h.attrib.get('gateway', '')
        lan = h.attrib.get('lan', '')
        image = h.attrib.get('image', '')
        host_rec = {'name': name, 'ip': ip, 'gateway': gateway, 'lan': lan}
        if image:
            host_rec['image'] = image
        if h.attrib.get('gw_dev'):
            host_rec['gw_dev'] = h.attrib.get('gw_dev')
        if h.attrib.get('nameserver'):
            host_rec['nameserver'] = h.attrib['nameserver'].split(',')
        h_ifaces = [
            {'name': it.attrib.get('name', ''), 'lan': it.attrib.get('lan', ''), 'ip': it.attrib.get('ip', '')}
            for it in h.findall('./interfaces/interface')
        ]
        if h_ifaces:
            host_rec['interfaces'] = h_ifaces
        if h.find('dns') is not None:
            host_rec['dns'] = True
            rt = h.find('root_type')
            if rt is not None and rt.text:
                host_rec['root_type'] = rt.text
            fwd_el = h.find('forwarders')
            if fwd_el is not None:
                host_rec['forwarders'] = [f.text for f in fwd_el.findall('forwarder') if f.text]
            zones_el = h.find('zones')
            if zones_el is not None:
                zones = {}
                for z in zones_el.findall('zone'):
                    zname = z.attrib.get('name')
                    records = {}
                    for rec in z.findall('record'):
                        rname = rec.attrib.get('name')
                        if len(list(rec)) == 0:
                            rip = rec.text
                            if rname and rip:
                                records[rname] = rip
                        else:
                            crec = {}
                            for c in rec:
                                crec[c.tag] = c.text
                            records[rname] = crec
                    zones[zname] = records
                host_rec['zones'] = zones
            deleghe = [dict(e.attrib) for e in h.findall('./delegations/delegation')]
            if deleghe:
                host_rec['delegations'] = deleghe
            ar_el = h.find('allow_recursion')
            if ar_el is not None and ar_el.text:
                host_rec['allow_recursion'] = ar_el.text.strip()
            dv_el = h.find('dnssec_validation')
            if dv_el is not None and (dv_el.text and dv_el.text.strip() in ('1', 'true', 'yes')):
                host_rec['dnssec_validation'] = True
        hosts.append(host_rec)

    wwws = []
    for w in root.findall('./www/server'):
        name = w.attrib.get('name', '')
        ip = w.attrib.get('ip', '')
        gateway = w.attrib.get('gateway', '')
        lan = w.attrib.get('lan', '')
        image = w.attrib.get('image', '')
        wrec = {'name': name, 'ip': ip, 'gateway': gateway, 'lan': lan}
        if image:
            wrec['image'] = image
        if w.attrib.get('nameserver'):
            wrec['nameserver'] = w.attrib['nameserver'].split(',')
        wwws.append(wrec)

    lab_conf_text = None
    lc = root.find('lab_conf')
    if lc is not None and lc.text:
        lab_conf_text = lc.text

    return lab_name, routers, hosts, wwws, lab_conf_text


def load_lab_from_json(path):
    """Carica un lab da file JSON."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    lab_name = data.get('lab', {}).get('name') or data.get('name') or os.path.splitext(os.path.basename(path))[0]
    routers = {}
    for r in data.get('routers', []):
        rname = r.get('name')
        protocols = r.get('protocols', [])
        asn = r.get('asn', '')
        interfaces = r.get('interfaces', [])
        rd = {'protocols': protocols, 'asn': asn, 'interfaces': interfaces}
        if r.get('ospf_area'):
            rd['ospf_area'] = r.get('ospf_area')
            rd['ospf_area_stub'] = bool(r.get('ospf_area_stub'))
        if r.get('ospf_extra_areas'):
            rd['ospf_extra_areas'] = r.get('ospf_extra_areas')
        if r.get('ospf_aree'):
            rd['ospf_aree'] = dict(r.get('ospf_aree'))
            rd['ospf_aree_stub'] = list(r.get('ospf_aree_stub') or [])
        if r.get('static_routes'):
            rd['static_routes'] = r.get('static_routes')
        if r.get('loopbacks'):
            rd['loopbacks'] = r.get('loopbacks')
        for key in ('igp_networks', 'bgp_extra_networks'):
            if r.get(key):
                rd[key] = list(r.get(key))
        if r.get('igp_redistribute_bgp') is False:
            rd['igp_redistribute_bgp'] = False
        routers[rname] = rd
    hosts = data.get('hosts', []) or []
    wwws = data.get('www', []) or data.get('wwws', []) or []
    lab_conf_text = data.get('lab_conf') or None
    return lab_name, routers, hosts, wwws, lab_conf_text


def leggi_resolver(path):
    """Nome del server DNS resolver salvato in un file XML o JSON del generatore (o None)."""
    try:
        if path.lower().endswith('.json'):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f).get('resolver') or None
        el = ET.parse(path).getroot().find('resolver')
        return el.text.strip() if el is not None and el.text and el.text.strip() else None
    except Exception:
        return None


def parse_startup_files(lab_path, nodes):
    """Legge i file <node>.startup per cercare configurazioni IP."""
    re_ip_add = re.compile(r"ip\s+a(?:ddr(?:ess)?)?\s+add\s+(?P<ip>[0-9\./]+)\s+dev\s+(?P<iface>\w+)")
    re_ifconfig = re.compile(r"ifconfig\s+(?P<iface>\w+)\s+(?P<ip>[0-9\./]+)")

    for node_name, node_data in nodes.items():
        startup_path = os.path.join(lab_path, f"{node_name}.startup")
        if not os.path.exists(startup_path):
            continue

        try:
            with open(startup_path, 'r', encoding='utf-8') as f:
                content = f.read()

            for m in re_ip_add.finditer(content):
                ip = m.group('ip')
                iface = m.group('iface')
                idx = -1
                if iface.startswith('eth'):
                    try:
                        idx = int(iface[3:])
                    except Exception:
                        pass

                if idx >= 0 and (str(idx) in node_data['interfaces'] or idx in node_data['interfaces']):
                    key = idx if idx in node_data['interfaces'] else str(idx)
                    if 'ips' not in node_data:
                        node_data['ips'] = {}
                    node_data['ips'][key] = ip

            for m in re_ifconfig.finditer(content):
                ip = m.group('ip')
                iface = m.group('iface')
                idx = -1
                if iface.startswith('eth'):
                    try:
                        idx = int(iface[3:])
                    except Exception:
                        pass

                if idx >= 0 and (str(idx) in node_data['interfaces'] or idx in node_data['interfaces']):
                    key = idx if idx in node_data['interfaces'] else str(idx)
                    if 'ips' not in node_data:
                        node_data['ips'] = {}
                    node_data['ips'][key] = ip

        except Exception as e:
            print(f"Errore parsing startup {node_name}: {e}")

    return nodes


def _scegli_nomi_validi(nomi, interactive, annulla):
    """Per i nomi non validi per Kathará propone un nome corretto e chiede conferma."""
    errati = [n for n in nomi if n and not nome_kathara_valido(n)]
    if not errati:
        return {}
    usati = {n for n in nomi if n not in errati}
    mappa = {}
    for n in errati:
        nuovo, k = correggi_nome_kathara(n), 2
        while nuovo in usati:
            nuovo, k = f"{correggi_nome_kathara(n)}_{k}", k + 1
        mappa[n] = nuovo
        usati.add(nuovo)
    print("\n⚠️ Nomi non validi per Kathará (solo lettere minuscole, cifre e _): il lab non si avvierebbe.")
    for vecchio, nuovo in mappa.items():
        print(f"   {vecchio} -> {nuovo}")
    if not interactive:
        print("   (rinominati automaticamente)")
        return mappa
    r = input(f"Rinominare così? (S = sì / m = scegli tu i nomi / n = {annulla}) [S]: ").strip().lower()
    if r == 'n':
        return None
    if r == 'm':
        usati = {n for n in nomi if n not in errati}
        for vecchio in mappa:
            mappa[vecchio] = _chiedi_nome(f"al posto di '{vecchio}'", mappa[vecchio], usati)
            usati.add(mappa[vecchio])
    return mappa


def correggi_nomi_lab(lab_path, interactive=True):
    """Rinomina sul posto i dispositivi con nomi non validi per Kathará di un lab già creato.

    Usa l'operazione 'rinomina' (core/operazioni.py): lab.conf, cartelle, .startup, hostname,
    descrizioni dei neighbor e XML, con la copia di sicurezza."""
    from .modifiche import Conflitto, scrivi_piano
    from .operazioni import ErroreOperazione, calcola_rinomina, dopo_scrittura

    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    mappa = _scegli_nomi_validi(list(nodes), interactive, 'lascia così')
    if not mappa:
        return False
    fatti = []
    for vecchio, nuovo in mappa.items():
        try:
            piano = calcola_rinomina(leggi_stato(lab_path), vecchio, nuovo)
            scrivi_piano(lab_path, piano)
            dopo_scrittura(lab_path, piano)
            fatti.append(f"{vecchio} -> {nuovo}")
        except (ErroreOperazione, Conflitto) as e:
            print(f"⚠️ {vecchio} non rinominato: {e}")
    if fatti:
        print(f"✅ Dispositivi rinominati ({', '.join(fatti)}): lab.conf, cartelle, .startup, hostname, "
              f"descrizioni dei neighbor e XML. Copia di sicurezza in .backup_labgenerator/.")
    return bool(fatti)


def correggi_nomi_importati(routers, hosts, wwws, lab_conf_text, interactive=True):
    """Nomi dei dispositivi non validi per Kathará in un XML/JSON: li rinomina prima di ricreare il lab."""
    nomi = list(routers) + [d.get('name') for d in list(hosts) + list(wwws) if isinstance(d, dict)]
    mappa = _scegli_nomi_validi(nomi, interactive, "annulla l'import")
    if mappa is None:
        print('Import annullato.')
        return None
    if not mappa:
        return routers, lab_conf_text
    routers = {mappa.get(n, n): d for n, d in routers.items()}
    for d in list(hosts) + list(wwws):
        if isinstance(d, dict) and d.get('name') in mappa:
            d['name'] = mappa[d['name']]
    if lab_conf_text:
        for vecchio, nuovo in mappa.items():
            lab_conf_text = re.sub(
                rf"^(\s*){re.escape(vecchio)}(\s*\[)",
                rf"\g<1>{nuovo}\g<2>",
                lab_conf_text,
                flags=re.M
            )
    return routers, lab_conf_text


def recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text=None, confirm=False,
                           resolver=None):
    """Ricrea il lab sul filesystem (import da XML/JSON) con core/generazione.genera_lab.

    Con confirm=True, se il lab esiste già chiede prima di sostituirlo; senza, lo sostituisce
    (con la copia di sicurezza). L'import è tollerante: i problemi dei dati vengono mostrati ma
    il lab viene creato comunque, come prima."""
    from .generazione import genera_lab

    lab_path = os.path.join(base, lab_name)
    if os.path.exists(lab_path) and confirm:
        print(f"⚠️ La cartella {lab_path} esiste già. Se la sovrascrivi, il lab viene rigenerato dall'XML:")
        print("   le modifiche fatte dopo la creazione dal menu Opzioni (policy, iBGP, network BGP,")
        print("   costi OSPF, deleghe DNS, resolver, ridistribuzione) NON sono nell'XML e andranno perse.")
        ans = input("Sovrascrivere? (s/n): ").strip().lower()
        if ans != 's':
            print("Annullato.")
            return None

    modello = {'routers': routers, 'hosts': hosts, 'wwws': wwws, 'resolver': resolver}
    esito = genera_lab(base, lab_name, modello, sovrascrivi=True, lab_conf_testo=lab_conf_text, tollerante=True)
    if esito['errori']:
        print("Attenzione: problemi nei dati importati (il lab viene creato comunque):")
        for p in esito['errori']:
            print(f"  - {p['campo']}: {p['messaggio']}")
    for m in esito['messaggi']:
        print(m)
    if esito['copia']:
        print(f"Il lab di prima è salvato in: {esito['copia']}")
    return lab_path


def _zone_dal_file(zona, record):
    """Record di una zona nel formato del wizard, con i nomi com'erano scritti nel file.

    crea_dns_host rimette da solo SOA e il primo '@ NS dns.<zona>.'; i glue A che seguono un
    NS o una delega diventano parte di quel record."""
    a_per_nome = {}
    for r in record:
        if r['tipo'] == 'A':
            a_per_nome.setdefault(r['nome'], r)
    out, glue_usati, ns_automatico = {}, set(), True
    for r in record:
        t, v = r['tipo'], r['valore']
        if t == 'SOA':
            continue
        if t == 'NS':
            ns = v.rstrip('.').lower()
            if r['nome'] == zona and ns_automatico and ns == f"dns.{zona}":
                ns_automatico = False
                continue
            g = a_per_nome.get(ns)
            if r['nome'] == zona:
                rec = {'type': 'NS', 'ns': v}
                if g:
                    rec['glue'] = g['valore']
            else:
                rec = {'type': 'DELEGATION', 'zone': r['scritto'], 'ns': v}
                if g:
                    rec['ns_ip'] = g['valore']
            if g:
                glue_usati.add(id(g))
            out[r['scritto']] = rec
        elif t == 'CNAME':
            out[r['scritto']] = {'type': 'CNAME', 'target': v}
        elif t == 'A' and id(r) not in glue_usati:
            out[r['scritto']] = v
    return out


def dati_da_stato(stato):
    """routers, hosts, wwws (formato dell'XML e del wizard) ricavati dal modello di un lab."""
    routers, hosts, wwws = {}, [], []
    for name in stato['ordine_lab_conf']:
        d = stato['dispositivi'][name]
        ifaces = [{'name': it['dev'], 'lan': it['lan'], 'ip': it['ip']} for it in d['interfacce']]
        st = d['startup']
        rotte = [dict(r) for r in st['statiche'] if r['via']]
        if d['tipo'] == 'router' and st['gateway']:
            rotte.append({'rete': 'default', 'via': st['gateway']['via'].split('/')[0],
                          'dev': st['gateway']['dev'], 'riga': st['gateway']['riga']})
        statiche = [{'network': r['rete'], 'via': r['via'], 'dev': r['dev']}
                    for r in sorted(rotte, key=lambda r: r['riga'])]

        # router senza FRR, con sole rotte statiche (crab): almeno due interfacce e rotte verso
        # altre reti; per il lettore dei file è un host, per il modello un router 'statico'
        statico = (d['tipo'] != 'router' and not d['frr'] and len(ifaces) >= 2
                   and any(r['rete'] != 'default' for r in rotte))
        if statico and st['gateway']:
            rotte.append({'rete': 'default', 'via': st['gateway']['via'].split('/')[0],
                          'dev': st['gateway']['dev'], 'riga': st['gateway']['riga']})
            statiche = [{'network': r['rete'], 'via': r['via'], 'dev': r['dev']}
                        for r in sorted(rotte, key=lambda r: r['riga'])]
        if d['tipo'] == 'router' or statico:
            f = d['frr'] or {}
            protos = [p for p in ('bgp', 'ospf', 'rip') if f.get(p)]
            if statiche:
                protos.append('statico')
            rd = {'protocols': protos, 'asn': d['asn'] or '', 'interfaces': ifaces}
            igp_nets, inietta = [], False
            for p in ('ospf', 'rip'):
                b = f.get(p)
                if not b:
                    continue
                for v in b['network']:
                    if v['rete'] not in igp_nets:
                        igp_nets.append(v['rete'])
                inietta = inietta or any(r['testo'].split()[0] == 'bgp' for r in b['redistribute'])
            if f.get('ospf'):
                aree = [v['area'] for v in f['ospf']['network'] if v.get('area')]
                area = aree[0] if aree else '0.0.0.0'
                rd['ospf_area'] = area
                rd['ospf_area_stub'] = any(x['area'] == area for x in f['ospf']['stub'])
                if len(set(aree)) > 1:        # router di confine (ABR): l'area di ogni rete
                    rd['ospf_aree'] = {v['rete']: v['area'] for v in f['ospf']['network'] if v.get('area')}
                    rd['ospf_aree_stub'] = list(dict.fromkeys(x['area'] for x in f['ospf']['stub']))
            if igp_nets:
                rd['igp_networks'] = igp_nets
            if f.get('bgp') and (f.get('ospf') or f.get('rip')) and not inietta:
                rd['igp_redistribute_bgp'] = False
            if f.get('bgp'):
                proprie = set()
                for it in ifaces:
                    try:
                        proprie.add(str(ipaddress.ip_interface(it['ip']).network))
                    except ValueError:
                        pass
                extra = [v['rete'] for v in f['bgp']['network'] if v['rete'] not in proprie]
                if extra:
                    rd['bgp_extra_networks'] = extra
            if d['loopback']:
                rd['loopbacks'] = list(d['loopback'])
            if statiche:
                rd['static_routes'] = statiche
            routers[name] = rd
            continue

        primo = ifaces[0] if ifaces else {'ip': '', 'lan': ''}
        voce = {'name': name, 'ip': primo['ip'], 'gateway': d['gateway'] or '', 'lan': primo['lan']}
        if d['immagine'] and d['immagine'] != 'kathara/base':
            voce['image'] = d['immagine']
        if d['tipo'] == 'www':
            wwws.append(voce)
            continue
        if d['tipo'] == 'dns' and d['dns']:
            zone = {z['zona']: z for z in d['dns']['zone']}
            radice = zone.get('.')
            root_type = radice['tipo'] if radice and radice['tipo'] in ('master', 'hint') else None
            voce.update({'dns': True, 'root_type': root_type, 'forwarders': d['dns']['forwarders']})
            autoritative = {n: _zone_dal_file(n, z['record']) for n, z in zone.items()
                            if n != '.' and z['tipo'] == 'master'}
            if autoritative:
                voce['zones'] = autoritative
            if d['dns']['allow_recursion']:
                voce['allow_recursion'] = '; '.join(d['dns']['allow_recursion'])
            voce['dnssec_validation'] = d['dns']['dnssec_validation'] == 'no'
            if root_type == 'master':
                glue = {r['nome']: r['valore'] for r in radice['record'] if r['tipo'] == 'A'}
                voce['delegations'] = [
                    {'zone': r['nome'], 'ns': r['valore'].rstrip('.'), 'ip': glue.get(r['valore'].rstrip('.').lower(), '')}
                    for r in radice['record'] if r['tipo'] == 'NS' and r['nome'] != '.']
            hosts.append(voce)
            continue
        voce['interfaces'] = ifaces
        if d['gateway']:
            voce['gw_dev'] = iface_for_nexthop(ifaces, d['gateway']) or 'eth0'
        hosts.append(voce)
    return routers, hosts, wwws


def modello_da_stato(stato):
    """Modello completo di un lab letto dai file: routers, hosts, wwws, resolver del lab e, per
    gli host, i www e i DNS che ne usano un altro (o lo hanno solo loro, come pc in palabra),
    il loro 'nameserver' (elenco di IP)."""
    routers, hosts, wwws = dati_da_stato(stato)
    res = resolver_da_stato(stato)
    ip_res = None
    if res:
        ip_res = next((it['ip'].split('/')[0] for it in stato['dispositivi'][res]['interfacce'] if it['ip']), None)
    for voce in hosts + wwws:
        ns = list(stato['dispositivi'][voce['name']]['nameserver'])
        if ns and ns != [ip_res]:
            voce['nameserver'] = ns
    return {'routers': routers, 'hosts': hosts, 'wwws': wwws, 'resolver': res}


def resolver_da_stato(stato):
    """Server DNS usato come resolver da tutti gli host, i www e i DNS del lab (come lo imposta il
    wizard), oppure None se i resolv.conf mancano o non sono tutti uguali."""
    altri = [d for d in stato['dispositivi'].values() if d['tipo'] != 'router']
    ns = {tuple(d['nameserver']) for d in altri}
    if not altri or len(ns) != 1:
        return None
    ip = ns.pop()
    if len(ip) != 1:
        return None
    chi = stato['proprietari'].get(ip[0])
    return chi if chi and stato['dispositivi'][chi]['tipo'] == 'dns' else None


def rebuild_lab_metadata_and_export(lab_path, stato=None, stampa=True):
    """Ricostruisce routers/hosts/www dai file del lab (lettore unico) e rigenera l'XML
    (in .labgenerator/<lab>/). Restituisce il percorso dell'XML."""
    lab_name = os.path.basename(os.path.normpath(lab_path))
    if stato is None:
        stato = leggi_stato(lab_path)
    m = modello_da_stato(stato)
    try:
        export_lab_to_xml(lab_name, lab_path, m['routers'], m['hosts'], m['wwws'], resolver=m['resolver'], stampa=stampa)
        xml = percorso_xml(lab_path, lab_name)
        return xml if os.path.isfile(xml) else None
    except Exception as e:
        print('Errore rigenerazione XML:', e)
        return None


def rigenera_xml(lab_path):
    """Dopo ogni scrittura: XML dei metadati rigenerato dai file, senza messaggi."""
    try:
        return rebuild_lab_metadata_and_export(lab_path, stampa=False)
    except Exception:
        return None
