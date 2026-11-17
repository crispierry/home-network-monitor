from html.parser import HTMLParser
import re
import subprocess
import time

import monitor as m

INTERVAL = 60
PAGES = ('broadbandstatistics', 'fiberstat', 'sysinfo', 'lanstatistics')

TEXT_FIELDS = {'Broadband Connection Source', 'Broadband Connection', 'Line State',
    'Current Duplex', 'PON Link Status', 'UNI Status', 'IP Passthrough Status',
    'Optical WAN Operational Status', 'Fiber Module', 'Link State', 'Model Number',
    'Software Version', 'Time Since Last Reboot', 'Current Date/Time', 'Last Change', 'State'}
NUMERIC_FIELDS = {'Current Speed (Mbps)', 'Receive Packets', 'Transmit Packets',
    'Receive Bytes', 'Transmit Bytes', 'Receive Drops', 'Transmit Drops', 'Receive Errors',
    'Transmit Errors', 'Collisions', 'Transmit Discards', 'Receive Discards',
    'Transmit Speed', 'Transmit Dropped', 'Receive Dropped'}
METRICS = ('Temperature', 'Vcc', 'Tx Bias', 'Tx Power', 'Rx Power')


def journal(root):
    return m.Journal(root, 'diagnostics', 4*1024**2, 8, 30)


class StatusParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables, self.rows, self.row, self.cell = [], None, None, None
        self.headings, self.heading, self.hidden = [], None, 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'table':
            self.rows = []
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            self.cell = []
        elif tag in ('h1', 'h2', 'h3'):
            self.heading = []

    def handle_data(self, text):
        if not self.hidden:
            if self.cell is not None:
                self.cell.append(text)
            if self.heading is not None:
                self.heading.append(text)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden-1)
        elif tag in ('td', 'th') and self.cell is not None:
            if self.row is not None:
                self.row.append(' '.join(' '.join(self.cell).split()))
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.rows is not None:
                self.rows.append(self.row)
            self.row = None
        elif tag == 'table' and self.rows is not None:
            self.tables.append(self.rows)
            self.rows = None
        elif tag in ('h1', 'h2', 'h3') and self.heading is not None:
            self.headings.append(' '.join(' '.join(self.heading).split()))
            self.heading = None


def parse_status(body):
    parser = StatusParser()
    parser.feed(body)
    tables = []
    for index, rows in enumerate(parser.tables):
        fields = {}
        for row in rows:
            if len(row) < 2:
                continue
            label, values = row[0], row[1:5]
            if label in NUMERIC_FIELDS:
                if all(re.fullmatch(r'\d+', v) and len(v) <= 24 for v in values):
                    fields[label] = [int(v) for v in values]
            elif label in TEXT_FIELDS:
                fields[label] = [v[:120] for v in values]
        if fields:
            tables.append(dict(table_index=index, fields=fields))
    optical = {}
    for heading in parser.headings:
        match = re.fullmatch(r'(Temperature|Vcc|Tx Bias|Tx Power|Rx Power)\s+Currently\s+(-?\d+(?:\.\d+)?)', heading)
        if match:
            optical[match[1]] = float(match[2])
    return dict(tables=tables, optical_readings=optical,
                optical_units='Raw gateway display units; Tx/Rx Power are tenths of dBm. Other values retained without conversion.')


def run_command(args, timeout=4, limit=16384):
    start = time.monotonic()
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL':'C'})
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as exc:
        rc, out, err = 124, exc.stdout or b'', exc.stderr or b''
    except OSError as exc:
        return dict(exit=127, output='', error=type(exc).__name__, elapsed_ms=round((time.monotonic()-start)*1000))
    return dict(exit=rc, output=out[:limit].decode('utf-8', 'replace'),
                error=err[:512].decode('utf-8', 'replace'), truncated=len(out)>limit,
                elapsed_ms=round((time.monotonic()-start)*1000))


def gateway_page(address, page):
    if page not in PAGES:
        raise ValueError('Only allowlisted read-only status pages may be collected')

    import ipaddress
    ipaddress.IPv4Address(address)
    at = m.stamp()
    deadline = 15 if page == 'lanstatistics' else 3
    r = run_command(['/usr/bin/curl', '-q', '--silent', '--noproxy', '*', '--max-time', str(deadline),
        '--max-filesize', '262144', '--write-out', '\n__HTTP_STATUS__%{http_code}',
        'http://'+address+'/cgi-bin/'+page+'.ha'], deadline+1, 262200)
    body, _, status = r['output'].rpartition('\n__HTTP_STATUS__')
    result = dict(at=at, exit=r['exit'], http_status=status[:3], elapsed_ms=r['elapsed_ms'], status='unavailable')
    if r['exit'] == 0 and status == '200':
        parsed = parse_status(body)
        if parsed['tables'] or parsed['optical_readings']:
            result.update(status='available', **parsed)
        else:
            result['status'] = 'unrecognized_or_login_page'

    return result


def local_context():
    interfaces = {}
    for name in ('en0', 'en1'):
        link = run_command(['/sbin/ifconfig', name])
        link['output'] = '\n'.join(line for line in link['output'].splitlines()
            if any(key in line for key in ('flags=', 'inet ', 'inet6 ', 'media:', 'status:')))
        dhcp = run_command(['/usr/sbin/ipconfig', 'getpacket', name])
        dhcp['output'] = '\n'.join(line for line in dhcp['output'].splitlines()
            if re.match(r'\s*(lease_time|renewal_t1_time_value|rebinding_t2_time_value|server_identifier|router|subnet_mask)\s*', line))
        interfaces[name] = dict(link=link, dhcp=dhcp)
    counters = run_command(['/usr/sbin/netstat', '-ibn'])
    counters['output'] = '\n'.join(line for line in counters['output'].splitlines()
        if re.match(r'^(Name\s|en[01]\s)', line))
    return dict(interfaces=interfaces,
        interface_counters=counters,
        ipv6_route=run_command(['/sbin/route', '-n', 'get', '-inet6', 'default']),
        system_load=run_command(['/usr/bin/uptime']))


def ipv6_checks():

    out = []
    for name, address, hostname, path in (
            ('cloudflare', '2606:4700:4700::1111', 'cloudflare-dns.com', '/dns-query'),
            ('google', '2001:4860:4860::8888', 'dns.google', '/resolve')):
        at = m.stamp()
        r = run_command(['/usr/bin/curl', '-q', '-6', '--silent', '--noproxy', '*',
            '--connect-timeout', '2', '--max-time', '3', '--output', '/dev/null',
            '--resolve', hostname+':443:['+address+']', '-H', 'Accept: application/dns-json',
            '--write-out', '%{http_code}', 'https://'+hostname+path+'?name=example.com&type=A'], 4)
        status = r['output'][:3]
        out.append(dict(target=name, address=address, at=at, ok=r['exit']==0 and status=='200',
                        exit=r['exit'], http_status=status, elapsed_ms=r['elapsed_ms']))
    return out


def collect(c, trigger, trace=False, host_sampler=None):
    result = dict(type='diagnostic_snapshot', schema='network-monitor.diagnostics.v1',
        at=m.stamp(), trigger=trigger, host=m.identity(), gateway={}, notes=[
            'Supplemental observations have individual timestamps and can occur after a brief failure has recovered.',
            'Gateway management unreachability does not prove a fiber fault. Counter resets/wraps are not negative traffic.',
            'IPv6 failures need a working baseline; traceroute stars can mean filtering. Neither changes IPv4 incident verdicts.'])

    result['local'] = local_context()
    if host_sampler is not None:
        result['host_metrics'] = host_sampler.sample(run_command, result['local']['interface_counters'], m.stamp())
    for page in PAGES:
        result['gateway'][page] = gateway_page(c['gateway'], page)
    result['ipv6'] = ipv6_checks()
    if trace:
        result['trace'] = run_command(['/usr/sbin/traceroute', '-n', '-m', '6', '-q', '1', '-w', '1', '1.1.1.1'], 9, 4096)
        result['trace']['target'] = '1.1.1.1'
    result['finished_at'] = m.stamp()
    return result


class Schedule:

    def __init__(self):
        self.last = None
        self.last_trace = None
        self.previous = None
        self.pending = None

    def observe(self, sample):
        failed = tuple(sorted(r['id'] for r in sample['checks'] if not r['ok']))
        signature = (failed, sample.get('network', {}).get('interface'))
        if self.previous is not None and signature != self.previous:
            self.pending = dict(reason='probe_or_route_changed', sample_at=sample['started_at'], failed_checks=list(failed))
        self.previous = signature

    def due(self, now, busy=False):
        if busy:
            return None
        if self.last is None or now-self.last >= INTERVAL or (self.pending and now-self.last >= 15):
            trigger = self.pending or dict(reason='periodic_baseline')
            self.pending = None
            trace = self.last_trace is None or (trigger['reason'] != 'periodic_baseline' and now-self.last_trace >= 300)
            self.last = now
            if trace:
                self.last_trace = now
            return trigger, trace
        return None
