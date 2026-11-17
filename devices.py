from concurrent.futures import ThreadPoolExecutor
import ipaddress
import json
import re
import monitor as m

INTERVAL = 60


def mac(value):
    if not re.fullmatch(r'(?:[0-9a-fA-F]{1,2}:){5}[0-9a-fA-F]{1,2}', value):
        return None
    normalized = ':'.join(part.zfill(2).lower() for part in value.split(':'))


    return None if normalized in ('02:00:00:00:00:00', '00:00:00:00:00:00', 'ff:ff:ff:ff:ff:ff') else normalized


def inventory(path):
    if not path.exists():
        return []
    rows = m.read_json(path, 65536)
    if not isinstance(rows, list) or len(rows) > 12:
        raise ValueError('Device watch must be a list of at most 12 devices')
    ids = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'name', 'address', 'mac', 'attachment', 'inventory_at', 'note'}
                or not all(isinstance(v, str) and len(v) <= 300 for v in row.values())
                or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', row['id']) or row['id'] in ids
                or mac(row['mac']) is None):
            raise ValueError('Invalid device identity or inventory fields')
        if not ipaddress.IPv4Address(row['address']).is_private:
            raise ValueError('Device watches require a private IPv4 address')
        ids.add(row['id'])
    return rows


def collect(rows, timeout=3):

    with ThreadPoolExecutor(max_workers=6) as pool:
        replies = list(pool.map(lambda r: m.probe(dict(id=r['id'], kind='icmp', target=r['address']), timeout), rows))
    _, arp = m.command(['/usr/sbin/arp', '-an'], timeout=5)
    _, interfaces = m.command(['/sbin/ifconfig'], timeout=3)
    local = set(re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)\b', interfaces))
    neighbors = {}
    for address, identity in re.findall(r'\(([\d.]+)\) at ([0-9a-fA-F:]+) on ', arp):
        if mac(identity):
            neighbors.setdefault(address, set()).add(mac(identity))

    for block in re.split(r'(?m)^(?=\w[^\s]*: flags=)', interfaces):
        own_mac = re.search(r'\bether ([0-9a-fA-F:]+)', block)
        if own_mac and mac(own_mac[1]):
            for address in re.findall(r'\binet ([\d.]+)\b', block):
                neighbors.setdefault(address, set()).add(mac(own_mac[1]))
    result = []
    for row, reply in zip(rows, replies):
        observed = neighbors.get(row['address'], set())
        identity = 'match' if observed == {mac(row['mac'])} else 'mismatch' if observed else 'unverified'
        result.append(dict(row, observed_at=reply['started_at'], reply=reply['ok'],
            latency_ms=reply['latency_ms'], identity=identity, observed_macs=sorted(observed),
            is_local=row['address'] in local, detail=reply['detail']))
    return result


def update(rows, previous):

    old = {r['id']: r for r in previous}
    output, events = [], []
    for raw in rows:
        row = dict(raw)
        before = old.get(row['id'], {})
        if (before.get('mac'), before.get('address')) != (row['mac'], row['address']):
            before = {}
        gap = bool(before) and not 0 < m.epoch(row['observed_at'])-m.epoch(before['observed_at']) <= INTERVAL*3


        good = row['reply'] and row['identity'] != 'mismatch'
        failures = 0 if row['reply'] or row['identity'] == 'mismatch' else min(2, (0 if gap else before.get('failures', 0))+1)
        passes = min(2, (0 if gap else before.get('passes', 0))+1) if good else 0
        last_reply = row['observed_at'] if good else before.get('last_reply_at')
        down = before.get('confirmed_unreachable', False)
        first_failure = row['observed_at'] if failures == 1 else before.get('first_failure_at')
        first_recovery = row['observed_at'] if passes == 1 else before.get('first_recovery_at')
        uncertain = gap or before.get('continuity_uncertain', False)
        if not down and last_reply and failures >= 2 and row['identity'] != 'mismatch':
            down = True
            events.append(dict(type='device_unreachable', device_id=row['id'], name=row['name'],
                at=row['observed_at'], first_failed_at=first_failure, last_reply_at=last_reply,
                continuity_uncertain=uncertain, identity=row['identity'],
                note='No ping reply at the watched address. Sleep, filtering, address change or connectivity are hypotheses; device identity may be unverified and cloud health is unknown.'))
        elif down and passes >= 2:
            down = False
            events.append(dict(type='device_recovered', device_id=row['id'], name=row['name'],
                at=row['observed_at'], first_recovered_at=first_recovery, continuity_uncertain=uncertain))
            uncertain = False
        status = ('address_changed' if row['identity'] == 'mismatch' else
                  'recovering' if good and down else 'responding' if good and row['identity'] == 'match' else 'address_reply' if good else
                  'unreachable' if down else 'checking' if last_reply else 'unknown')
        row.update(status=status, last_reply_at=last_reply, failures=failures, passes=passes,
                   confirmed_unreachable=down, first_failure_at=first_failure,
                   first_recovery_at=first_recovery, continuity_uncertain=uncertain)
        output.append(row)
    return output, events
