"""
src/core/persistence.py
Esportazione/Importazione XML e JSON, parsing di lab.conf/startup, ricostruzione metadati e rinomina dispositivi.
"""
import json
import os
import re
import shutil
import xml.etree.ElementTree as ET
from xml.dom import minidom

from .cli_io import correggi_nome_kathara, input, nome_kathara_valido
from .generators import (
    build_lab_conf_text,
    crea_dns_host,
    crea_host_multi,
    crea_router_files,
    crea_www_file,
)
from .net_frr import auto_generate_bgp_neighbors, rimuovi_network_bgp_interne


def _chiedi_nome(tipo, default, usati):
    """Chiede il nome di un dispositivo verificando validità Kathará e unicità."""
    s = None
    while True:
        if s is None:
            s = input(f"\nNome {tipo} (default {default}): ").strip() or default
        if not nome_kathara_valido(s):
            proposta = correggi_nome_kathara(s)
            print(f"❌ '{s}' non è valido per Kathará (solo lettere minuscole, cifre e _).")
            r = input(f"Usare '{proposta}'? (S/n, oppure scrivi un altro nome): ").strip()
            if r.lower() in ('', 's', 'si', 'sì'):
                s = proposta
            elif r.lower() == 'n':
                s = None
            else:
                s = r
            continue
        if s in usati:
            print(f"Nome '{s}' già usato. Scegli un altro.")
            s = None
            continue
        return s


def export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws):
    """Esporta una rappresentazione XML del laboratorio in `lab_path/<lab_name>.xml`."""
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
            ET.SubElement(www_el, 'server', attrib=w_attrib)

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

        out_path = os.path.join(lab_path, f"{lab_name}.xml")
        with open(out_path, 'wb') as f:
            f.write(pretty)
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


def parse_lab_conf_for_nodes(lab_path):
    """Parse `lab.conf` per ricavare nodi, mapping interfacce->LAN e immagini."""
    nodes = {}
    conf_path = os.path.join(lab_path, 'lab.conf')
    if not os.path.exists(conf_path):
        return nodes, None
    lab_conf_text = None
    try:
        with open(conf_path, 'r', encoding='utf-8') as f:
            lab_conf_text = f.read()
    except Exception:
        return nodes, None

    lines = [L.strip() for L in lab_conf_text.splitlines() if L.strip() and not L.strip().startswith('#')]
    p = re.compile(r"^\s*(?P<name>[^\[\s]+)\s*\[\s*(?P<idx>[^\]]+)\s*\]\s*=\s*(?:\"(?P<qval>.*)\"|(?P<val>[^#]*))")
    for L in lines:
        m = p.match(L)
        if not m:
            continue
        name = m.group('name')
        idx = m.group('idx')
        val = m.group('qval') if m.group('qval') is not None else m.group('val')
        val = val.strip()
        node = nodes.setdefault(name, {'interfaces': {}, 'image': ''})
        if idx == 'image':
            node['image'] = val.strip('"')
        else:
            try:
                node['interfaces'][int(idx)] = val
            except Exception:
                node['interfaces'][idx] = val
    return nodes, lab_conf_text


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
    """Rinomina sul posto i dispositivi con nomi non validi per Kathará di un lab già creato."""
    nodes, testo = parse_lab_conf_for_nodes(lab_path)
    mappa = _scegli_nomi_validi(list(nodes), interactive, 'lascia così')
    if not mappa:
        return False

    def sostituisci(t):
        for vecchio, nuovo in mappa.items():
            t = re.sub(rf"^(\s*){re.escape(vecchio)}(\s*\[)", rf"\g<1>{nuovo}\g<2>", t, flags=re.M)
            t = t.replace(f'name="{vecchio}"', f'name="{nuovo}"')
        return t

    def _scrivi_testo(p, t):
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            f.write(t)

    _scrivi_testo(os.path.join(lab_path, 'lab.conf'), sostituisci(testo))
    for vecchio, nuovo in mappa.items():
        for v, n in ((vecchio, nuovo), (f"{vecchio}.startup", f"{nuovo}.startup")):
            if os.path.exists(os.path.join(lab_path, v)):
                os.rename(os.path.join(lab_path, v), os.path.join(lab_path, n))
    xml = os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')
    if os.path.exists(xml):
        with open(xml, 'r', encoding='utf-8') as f:
            _scrivi_testo(xml, sostituisci(f.read()))
    print("✅ Dispositivi rinominati (lab.conf, cartelle, .startup, XML). Il resto del lab non è cambiato.")
    return True


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


def recreate_lab_from_data(lab_name, base, routers, hosts, wwws, lab_conf_text=None, confirm=False):
    """Ricrea il lab sul filesystem usando le funzioni esistenti."""
    lab_path = os.path.join(base, lab_name)
    if os.path.exists(lab_path):
        if confirm:
            print(f"⚠️ La cartella {lab_path} esiste già. Se la sovrascrivi, il lab viene rigenerato dall'XML:")
            print("   le modifiche fatte dopo la creazione dal menu Opzioni (policy, iBGP, network BGP,")
            print("   costi OSPF, deleghe DNS, resolver, ridistribuzione) NON sono nell'XML e andranno perse.")
            ans = input("Sovrascrivere? (s/n): ").strip().lower()
            if ans != 's':
                print("Annullato.")
                return None
        if os.path.isdir(lab_path):
            shutil.rmtree(lab_path)
        else:
            os.remove(lab_path)
    os.makedirs(lab_path, exist_ok=True)

    for rname, rdata in routers.items():
        crea_router_files(lab_path, rname, rdata, interactive=False)

    dns_root_ip = None
    for h in hosts:
        try:
            if isinstance(h, dict) and h.get('dns') and str(h.get('root_type', '')).lower() == 'master':
                ip = h.get('ip') or ''
                dns_root_ip = ip.split('/')[0] if '/' in ip else ip
                break
        except Exception:
            continue

    for h in hosts:
        try:
            if isinstance(h, dict) and (h.get('dns') or str(h.get('type', '')).lower() == 'dns'):
                fwd = h.get('forwarders') if isinstance(h.get('forwarders'), list) else None
                zones = h.get('zones') if isinstance(h.get('zones'), dict) else None
                rt = h.get('root_type') if isinstance(h.get('root_type'), str) else None
                allow_rec = h.get('allow_recursion') if isinstance(h.get('allow_recursion'), str) else None
                dnssec_val = bool(h.get('dnssec_validation'))
                if rt and str(rt).lower() != 'master' and dns_root_ip:
                    crea_dns_host(
                        lab_path, h.get('name'), h.get('ip'), h.get('gateway'), h.get('lan'),
                        forwarders=fwd, zones=zones, root_type=rt, root_server_ip=dns_root_ip,
                        allow_recursion=allow_rec, dnssec_validation=dnssec_val
                    )
                else:
                    crea_dns_host(
                        lab_path, h.get('name'), h.get('ip'), h.get('gateway'), h.get('lan'),
                        forwarders=fwd, zones=zones, root_type=rt,
                        allow_recursion=allow_rec, dnssec_validation=dnssec_val,
                        delegations=h.get('delegations') if isinstance(h.get('delegations'), list) else None
                    )
            else:
                ifaces = h.get('interfaces') or [{'name': 'eth0', 'ip': h.get('ip'), 'lan': h.get('lan')}]
                crea_host_multi(lab_path, h.get('name'), ifaces, h.get('gateway'), h.get('gw_dev') or 'eth0')
        except Exception as e:
            print(f"⚠️ Errore creando l'host {h.get('name') if isinstance(h, dict) else h}: {e}")

    for w in wwws:
        try:
            crea_www_file(lab_path, w.get('name'), w.get('ip'), w.get('gateway'), w.get('lan'))
        except Exception as e:
            print(f"⚠️ Errore creando il webserver {w.get('name')}: {e}")

    if not lab_conf_text:
        lab_conf_text = build_lab_conf_text(routers, hosts, wwws)
    try:
        with open(os.path.join(lab_path, 'lab.conf'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(lab_conf_text)
    except Exception as e:
        print(f"⚠️ Errore scrivendo lab.conf: {e}")

    auto_generate_bgp_neighbors(lab_path, routers)
    rimuovi_network_bgp_interne(lab_path, routers)

    try:
        export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws)
    except Exception:
        pass

    return lab_path


def rebuild_lab_metadata_and_export(lab_path):
    """Ricostruisce routers/hosts/www dal filesystem e rigenera l'XML."""
    lab_name = os.path.basename(os.path.normpath(lab_path))
    nodes, _ = parse_lab_conf_for_nodes(lab_path)
    routers = {}
    hosts = []
    wwws = []

    for name, meta in nodes.items():
        image = meta.get('image', '')
        ifaces = []
        for idx, lan in sorted(
            meta.get('interfaces', {}).items(),
            key=lambda x: int(x[0]) if isinstance(x[0], int) or str(x[0]).isdigit() else 0
        ):
            eth = f"eth{idx}"
            ifaces.append({'name': eth, 'lan': lan, 'ip': ''})

        startup_path = os.path.join(lab_path, f"{name}.startup")
        if os.path.exists(startup_path):
            try:
                with open(startup_path, 'r', encoding='utf-8') as f:
                    for L in f:
                        Ls = L.strip()
                        if not Ls:
                            continue
                        parts = Ls.split()
                        if len(parts) >= 5 and parts[0] == 'ip' and parts[1] == 'address' and parts[2] == 'add':
                            ip = parts[3]
                            dev = parts[5] if len(parts) > 5 and parts[4] == 'dev' else None
                            if dev:
                                for it in ifaces:
                                    if it['name'] == dev:
                                        it['ip'] = ip
            except Exception:
                pass

        if 'frr' in image.lower() or 'kathara/frr' in image.lower():
            frr_conf = os.path.join(lab_path, name, 'etc', 'frr', 'frr.conf')
            protos = []
            asn = ''
            if os.path.exists(frr_conf):
                try:
                    with open(frr_conf, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    if 'router bgp' in txt:
                        protos.append('bgp')
                        m = re.search(r'router bgp\s+(\d+)', txt)
                        if m:
                            asn = m.group(1)
                    if 'router ospf' in txt:
                        protos.append('ospf')
                    if 'router rip' in txt:
                        protos.append('rip')
                except Exception:
                    pass
            routers[name] = {'protocols': protos, 'asn': asn, 'interfaces': ifaces}
        else:
            www_index = os.path.join(lab_path, name, 'var', 'www', 'html', 'index.html')
            ip_val = ''
            gw_val = ''
            if os.path.exists(startup_path):
                try:
                    with open(startup_path, 'r', encoding='utf-8') as f:
                        for L in f:
                            if 'ip address add' in L:
                                parts = L.strip().split()
                                if len(parts) >= 4:
                                    ip_val = parts[3]
                            if 'ip route add default via' in L:
                                parts = L.strip().split()
                                if len(parts) >= 6:
                                    gw_val = parts[5]
                except Exception:
                    pass
            if os.path.exists(www_index):
                wwws.append({'name': name, 'ip': ip_val, 'gateway': gw_val, 'lan': meta.get('interfaces', {}).get(0, '')})
            else:
                hosts.append({'name': name, 'ip': ip_val, 'gateway': gw_val, 'lan': meta.get('interfaces', {}).get(0, '')})

    try:
        export_lab_to_xml(lab_name, lab_path, routers, hosts, wwws)
        return os.path.join(lab_path, f"{lab_name}.xml")
    except Exception as e:
        print('Errore rigenerazione XML:', e)
        return None


def _xml_del_lab(lab_path):
    p = os.path.join(lab_path, os.path.basename(os.path.normpath(lab_path)) + '.xml')
    return p if os.path.isfile(p) else None


def _ricarica_routers(lab_path, routers):
    p = _xml_del_lab(lab_path)
    if routers is not None and p:
        try:
            routers.clear()
            routers.update(load_lab_from_xml(p)[1])
        except Exception as e:
            print(f"⚠️ Non riesco a rileggere {os.path.basename(p)}: {e}")


def _mappa_dati(x, f):
    if isinstance(x, str):
        return f(x)
    if isinstance(x, list):
        return [_mappa_dati(v, f) for v in x]
    if isinstance(x, dict):
        return {k: _mappa_dati(v, f) for k, v in x.items()}
    return x


def _aggiorna_xml(lab_path, routers, trasforma):
    """Applica trasforma(routers, hosts, wwws) all'XML del lab e ai router in memoria."""
    p = _xml_del_lab(lab_path)
    if not p:
        if routers is not None:
            trasforma(routers, [], [])
        print("(nessun XML del generatore in questo lab: aggiornati solo i file)")
        return
    try:
        _, r, h, w, _ = load_lab_from_xml(p)
        trasforma(r, h, w)
        export_lab_to_xml(os.path.basename(os.path.normpath(lab_path)), lab_path, r, h, w)
        if routers is not None:
            routers.clear()
            routers.update(r)
    except Exception as e:
        print(f"⚠️ XML non aggiornato ({e}): i file del lab sono comunque modificati.")


def _xml_sostituisci(f):
    def t(r, h, w):
        for k in list(r):
            r[k] = _mappa_dati(r[k], f)
        h[:] = _mappa_dati(h, f)
        w[:] = _mappa_dati(w, f)
    return t