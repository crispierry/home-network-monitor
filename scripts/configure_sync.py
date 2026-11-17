#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import re
import ssl
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import monitor as m
import peer_transport as transport
import sync


def pair(root, host, bundle, expected_fingerprint):
    peer='Mini-Two' if host=='Mini-One' else 'Mini-One'
    if not isinstance(bundle,dict) or bundle.get('host')!=peer or not sync.ID.fullmatch(bundle.get('host_id','')):
        raise ValueError('Wrong peer identity')
    certificate=bundle.get('certificate','')
    if len(certificate)>8192 or certificate.count('-----BEGIN CERTIFICATE-----')!=1 or 'PRIVATE' in certificate:
        raise ValueError('Expected one public certificate')
    digest=sync.digest(ssl.PEM_cert_to_DER_cert(certificate))
    if not re.fullmatch('[a-f0-9]{64}',expected_fingerprint) or digest!=expected_fingerprint or digest!=bundle.get('fingerprint'):
        raise ValueError('Fingerprint differs from trusted out-of-band value')
    transport.identity(root,host)
    path=root/'keys/peer.pem'
    if path.exists() and transport.fingerprint(path)!=digest:
        raise ValueError('Already paired with a different certificate; inspect before replacing')
    m.atomic(path,certificate); path.chmod(0o600)
    sync.save(root/'config.json',dict(role='hub' if host=='Mini-One' else 'client',enabled=False,
        peer_id=bundle['host_id'],peer_host=peer,peer_fingerprint=digest))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('identity','pair','enable','disable'))
    p.add_argument('--bundle',type=Path,help='Public identity JSON received through trusted file transfer')
    p.add_argument('--fingerprint',help='SHA-256 public certificate fingerprint verified on the other Mac')
    a=p.parse_args()
    host=m.identity()['local_hostname']; m.validate_host(host)
    if host not in ('Mini-One','Mini-Two'): raise SystemExit('Only the paired Minis are supported')
    root=sync.ROOT
    if a.action=='identity':
        print(json.dumps(transport.identity(root,host),indent=2)); return
    if a.action=='pair':
        if not a.bundle or not a.fingerprint: p.error('pair requires --bundle and --fingerprint')
        pair(root,host,sync.read(a.bundle,16384),a.fingerprint)
        print('Paired public certificate; transfer remains disabled.'); return
    c=sync.read(root/'config.json')
    if a.action=='enable':
        transport.context(root,server=c['role']=='hub')
        if transport.fingerprint(root/'keys/peer.pem')!=c['peer_fingerprint']: raise SystemExit('Pairing changed')
        print('Enabling paired TLS on home LAN TCP 19443; Mini-One listens, Mini-Two connects.')
    c['enabled']=a.action=='enable'; sync.save(root/'config.json',c)
    print('Configuration saved; worker applies it within 5 seconds.')

if __name__=='__main__': main()
