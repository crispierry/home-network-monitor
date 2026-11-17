import ctypes
import re
import sys
import time


def cpu_ticks():
    if sys.platform != 'darwin':
        return None
    try:
        lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
        lib.mach_host_self.restype = ctypes.c_uint
        lib.host_statistics.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.POINTER(ctypes.c_uint), ctypes.POINTER(ctypes.c_uint)]
        lib.mach_port_deallocate.argtypes = [ctypes.c_uint, ctypes.c_uint]
        port = lib.mach_host_self()
        try:
            ticks, count = (ctypes.c_uint * 4)(), ctypes.c_uint(4)

            if lib.host_statistics(port, 3, ticks, ctypes.byref(count)) == 0 and count.value == 4:
                return list(ticks)
        finally:
            lib.mach_port_deallocate(ctypes.c_uint.in_dll(lib, 'mach_task_self_').value, port)
    except (OSError, AttributeError, ValueError):
        pass
    return None


def interface_counters(result):

    out = {}
    if result.get('exit') != 0 or result.get('truncated'):
        return out
    for line in result.get('output', '').splitlines():
        fields = line.split()
        if len(fields) < 10 or fields[0].rstrip('*') not in ('en0', 'en1') or not fields[2].startswith('<Link#'):
            continue

        try:
            packets_in, errors_in, bytes_in, packets_out, errors_out, bytes_out, collisions = map(int, fields[-7:])
        except ValueError:
            continue
        values = dict(rx_bytes=bytes_in, tx_bytes=bytes_out, rx_errors=errors_in, tx_errors=errors_out)
        if min(values.values()) >= 0:
            out[fields[0].rstrip('*')] = values
    return out


def swap_mib(result):
    match = re.search(r'\bused\s*=\s*([\d.]+)([KMGT])\b', result.get('output', '')) if result.get('exit') == 0 else None
    if not match:
        return None
    try:
        return float(match[1]) * {'K': 1/1024, 'M': 1, 'G': 1024, 'T': 1024**2}[match[2]]
    except ValueError:
        return None


class Sampler:
    def __init__(self):
        self.previous = None

    def sample(self, run, counters, at, now=None, ticks=None):
        now = time.monotonic() if now is None else now
        ticks = cpu_ticks() if ticks is None else ticks
        current = interface_counters(counters)
        pressure = run(['/usr/sbin/sysctl', '-n', 'kern.memorystatus_vm_pressure_level'], timeout=2)
        swap = run(['/usr/sbin/sysctl', '-n', 'vm.swapusage'], timeout=2)
        result = dict(at=at, interval_seconds=None, cpu_busy_percent=None, cpu_status='unavailable' if ticks is None else 'warming_up',
            memory_pressure={ '1': 'normal', '2': 'warning', '4': 'critical' }.get(pressure.get('output', '').strip(), 'unknown') if pressure.get('exit') == 0 else 'unknown',
            swap_used_mib=swap_mib(swap), interfaces={},
            interpretation='Observer-wide CPU and interface traffic, not application attribution or internet capacity. Averages can hide brief spikes. No reading is not zero.')
        elapsed = now-self.previous[0] if self.previous else None
        valid = elapsed is not None and 0 < elapsed <= 180
        if valid:
            result['interval_seconds'] = round(elapsed, 3)
        elif self.previous:
            result['cpu_status'] = 'gap' if ticks is not None else 'unavailable'
        if valid and ticks is not None and self.previous[1] is not None:
            delta = [a-b for a, b in zip(ticks, self.previous[1])]
            if min(delta) >= 0 and sum(delta) > 0:
                result.update(cpu_busy_percent=round(100*(sum(delta)-delta[2])/sum(delta), 2), cpu_status='available')
            else:
                result['cpu_status'] = 'counter_reset_or_no_delta'
        for name, values in current.items():
            row = dict(counters=values, rx_mbps=None, tx_mbps=None, rx_errors_delta=None, tx_errors_delta=None, status='warming_up')
            before = self.previous[2].get(name) if self.previous else None
            if self.previous and not valid:
                row['status'] = 'gap'
            elif valid and before is not None:
                delta = {k: values[k]-before[k] for k in values}
                if min(delta.values()) < 0:
                    row['status'] = 'counter_reset'
                else:
                    row.update(status='available', rx_mbps=round(delta['rx_bytes']*8/elapsed/1e6, 4),
                        tx_mbps=round(delta['tx_bytes']*8/elapsed/1e6, 4), rx_errors_delta=delta['rx_errors'], tx_errors_delta=delta['tx_errors'])
            result['interfaces'][name] = row
        self.previous = (now, ticks, current)
        return result
