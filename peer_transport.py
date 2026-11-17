import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import ssl
import struct
import subprocess
import threading
import time

import monitor as m
import sync

PORT=19443
NETWORK=ipaddress.ip_network('10.0.0.0/24')
MAX_FRAME=sync.MAX_MANIFEST


def identity(root, host):
    if host not in ('Mini-One','Mini-Two'): raise ValueError('Unknown host')
    keys=root/'keys'; keys.mkdir(parents=True,exist_ok=True,mode=0o700)
    key,cert=keys/'private.pem',keys/'certificate.pem'
    if key.exists() != cert.exists(): raise ValueError('Incomplete identity; inspect before replacing')
    if not key.exists():
        old=os.umask(0o077)
        try:
            subprocess.run(['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes',
                '-keyout',str(key),'-out',str(cert),'-days','3650','-subj','/CN='+host+'.local',
                '-addext','subjectAltName=DNS:'+host+'.local',
                '-addext','extendedKeyUsage=serverAuth,clientAuth'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        finally: os.umask(old)
    key.chmod(0o600); cert.chmod(0o600)
    host_id=sync.optional(root/'identity.json')
    if not host_id:
        import uuid
        host_id={'host_id':uuid.uuid4().hex}; sync.save(root/'identity.json',host_id)
    return dict(host=host,host_id=host_id['host_id'],certificate=cert.read_text(),fingerprint=fingerprint(cert))


def fingerprint(cert):
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert.read_text())).hexdigest()


def context(root, server=False):
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if server else ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version=ssl.TLSVersion.TLSv1_3
    ctx.verify_mode=ssl.CERT_REQUIRED
    ctx.load_cert_chain(str(root/'keys/certificate.pem'),str(root/'keys/private.pem'))
    ctx.load_verify_locations(cafile=str(root/'keys/peer.pem'))
    return ctx


def check_peer(sock, root):
    if hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()!=fingerprint(root/'keys/peer.pem'):
        raise ssl.SSLError('Unpaired certificate')


def exact(sock, size):
    if type(size) is not int or not 0<=size<=sync.MAX_FILE+MAX_FRAME: raise ValueError('Invalid length')
    chunks=[]; remaining=size
    while remaining:
        data=sock.recv(min(65536,remaining))
        if not data: raise ValueError('Incomplete message')
        chunks.append(data); remaining-=len(data)
    return b''.join(chunks)


def frame(sock, value):
    data=json.dumps(value,separators=(',',':'),allow_nan=False).encode()
    if len(data)>MAX_FRAME: raise ValueError('Oversized message')
    sock.sendall(struct.pack('!I',len(data))+data)


def receive(sock):
    size=struct.unpack('!I',exact(sock,4))[0]
    if size>MAX_FRAME: raise ValueError('Oversized message')
    value=json.loads(exact(sock,size),parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number')))
    if not isinstance(value,dict): raise ValueError('Expected an object')
    return value


def connect(root, c):


    addresses=socket.getaddrinfo('Mini-One.local',PORT,socket.AF_INET,socket.SOCK_STREAM)
    last=None
    for _,_,_,_,address in addresses:
        if ipaddress.ip_address(address[0]) not in NETWORK: continue
        raw=None; secure=None
        try:
            raw=socket.create_connection(address,timeout=4)
            secure=context(root).wrap_socket(raw,server_hostname='Mini-One.local')
            secure.settimeout(5); check_peer(secure,root)
            return secure
        except (OSError,ValueError) as e:
            last=e
            if secure: secure.close()
            elif raw: raw.close()
    raise OSError('Paired Mini-One is unavailable') from last


def request(root,c,value):
    with connect(root,c) as sock:
        frame(sock,value); result=receive(sock)
        if not result.get('ok'): raise ValueError('Peer refused request')
        return result,exact(sock,result.get('length',0))


class RemoteFile:
    def __init__(self,root,c,name): self.root,self.c,self.name=root,c,name; self.offset=0
    def is_symlink(self): return False
    def open(self,_): return self
    def __enter__(self): return self
    def __exit__(self,*_): pass
    def seek(self,offset): self.offset=offset
    def read(self,size):
        _,data=request(self.root,self.c,dict(op='read',name=self.name,offset=self.offset,length=size))
        self.offset+=len(data); return data


class RemoteDirectory:
    def __init__(self,root,c): self.root,self.c=root,c
    def is_symlink(self): return False
    def __truediv__(self,name): return RemoteFile(self.root,self.c,name)


def previous_manifest(root):
    peer=sync.current_peer(root)
    return sync.optional(peer/'manifest.json') if peer else {}


def push(root,c):
    result,_=request(root,c,{'op':'received'})
    old=result.get('manifest',{}); new=sync.read(root/'outbox/manifest.json')
    if old: sync.validate_manifest(old,new['host_id'],'Mini-Two')
    prior={f['name']:f for f in old.get('files',[])} if old.get('generation')==new['generation'] else {}
    offsets={}
    for item in new['files']:
        previous=prior.get(item['name'])
        count=previous['size'] if previous and previous['size']<=item['size'] else 0
        if count:
            with (root/'outbox'/item['name']).open('rb') as f: prefix=f.read(count)
            if sync.digest(prefix)!=previous['sha256']: count=0
        offsets[item['name']]=count
    with connect(root,c) as sock:
        frame(sock,dict(op='publish',manifest=new,offsets=offsets))
        for item in new['files']:
            with (root/'outbox'/item['name']).open('rb') as f:
                f.seek(offsets[item['name']]); data=f.read(item['size']-offsets[item['name']])
            sock.sendall(data)
        if not receive(sock).get('ok'): raise ValueError('Peer rejected publication')


def exchange(root):
    c=sync.read(root/'config.json')
    if c.get('role')!='client' or not c.get('enabled'): raise ValueError('Client not enabled')
    push(root,c)
    return sync.transfer(RemoteDirectory(root,c),root/'peer',c['peer_id'],'Mini-One')


def handle(sock,root,c):
    request=receive(sock); op=request.get('op')
    if op=='received':
        frame(sock,dict(ok=True,manifest=previous_manifest(root))); return
    if op=='read':
        name=request.get('name',''); offset=request.get('offset'); length=request.get('length')
        if name!='manifest.json' and not sync.NAME.fullmatch(name): raise ValueError('Invalid file')
        if type(offset) is not int or offset<0 or offset>sync.MAX_FILE or type(length) is not int or not 0<=length<=sync.MAX_FILE+1: raise ValueError('Invalid range')
        path=root/'outbox'/name
        if path.is_symlink() or not path.is_file() or path.stat().st_size>sync.MAX_FILE: raise ValueError('Unavailable file')
        with path.open('rb') as f: f.seek(offset); data=f.read(length)
        frame(sock,dict(ok=True,length=len(data))); sock.sendall(data); return
    if op!='publish': raise ValueError('Unknown operation')
    manifest=request['manifest']; sync.validate_manifest(manifest,c['peer_id'],'Mini-Two')
    old=previous_manifest(root); cached=sync.current_peer(root)
    offsets=request.get('offsets',{})
    if not isinstance(offsets,dict) or set(offsets)!={x['name'] for x in manifest['files']}: raise ValueError('Invalid offsets')
    stage=root/'incoming'
    if stage.exists(): shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    try:
        for item in manifest['files']:
            count=offsets[item['name']]
            if type(count) is not int or not 0<=count<=item['size']: raise ValueError('Invalid offset')
            prefix=b''
            if count:
                if old.get('generation')!=manifest['generation'] or not cached: raise ValueError('Missing prefix')
                path=cached/item['name']
                if path.is_symlink(): raise ValueError('Invalid prefix')
                with path.open('rb') as f: prefix=f.read(count)
                if len(prefix)!=count: raise ValueError('Short prefix')
            payload=prefix+exact(sock,item['size']-count)
            if sync.digest(payload)!=item['sha256']: raise ValueError('Checksum mismatch')
            sync.validate_records(item['name'],payload,time.time())
            (stage/item['name']).write_bytes(payload); (stage/item['name']).chmod(0o600)
        sync.save(stage/'manifest.json',manifest)
        sync.transfer(stage,root/'peer',c['peer_id'],'Mini-Two')
        sync.save(root/'received.json',dict(at=time.time(),observed_at=m.epoch(manifest['state']['last_completed_at'])))
        frame(sock,dict(ok=True))
    finally:
        if stage.exists(): shutil.rmtree(stage)


def bind_address(data):
    state=m.read_state(data) or {}
    link=state.get('network',{}).get('active_link','')
    for value in re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)\b',link):
        if ipaddress.ip_address(value) in NETWORK: return value
    raise ValueError('No recorded home-LAN interface')


def serve(root,data=m.DATA):
    c=sync.read(root/'config.json')
    if not c.get('enabled') or c.get('role')!='hub': raise ValueError('Hub not enabled')
    address=bind_address(data); ctx=context(root,server=True)
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind((address,PORT)); listener.listen(2); listener.settimeout(2)
        checked=time.monotonic()
        while True:
            if time.monotonic()-checked>30:
                if bind_address(data)!=address: return
                checked=time.monotonic()
            try: raw,peer=listener.accept()
            except socket.timeout: continue
            if ipaddress.ip_address(peer[0]) not in NETWORK: raw.close(); continue

            holder=[raw]
            def expire(holder=holder):
                try: holder[0].shutdown(socket.SHUT_RDWR)
                except OSError: pass
            timer=threading.Timer(20,expire); timer.daemon=True; timer.start()
            try:
                raw.settimeout(4)
                with ctx.wrap_socket(raw,server_side=True) as secure:
                    holder[0]=secure; check_peer(secure,root); handle(secure,root,c)
            except (OSError,ValueError,KeyError,TypeError,RecursionError):
                raw.close()
            finally: timer.cancel()


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('action',choices=['identity','serve']); p.add_argument('--root',type=Path,default=sync.ROOT); p.add_argument('--data',type=Path,default=m.DATA); p.add_argument('--host',choices=['Mini-One','Mini-Two']); a=p.parse_args()
    os.umask(0o077)
    if a.action=='identity': print(json.dumps(identity(a.root,a.host)))
    else: serve(a.root,a.data)
