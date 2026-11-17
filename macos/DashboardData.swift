import Foundation
import Darwin

let evidenceHome = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/NetworkMonitor")
let programHome = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/NetworkMonitor")
let commissioningIDs: Set<String> = []

func timestamp(_ value: Any?) -> Double? {
    guard let text = value as? String else { return nil }
    return ISO8601DateFormatter.fractional.date(from: text)?.timeIntervalSince1970 ?? ISO8601DateFormatter.plain.date(from: text)?.timeIntervalSince1970
}
extension ISO8601DateFormatter {
    static let fractional: ISO8601DateFormatter = { let f = ISO8601DateFormatter(); f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]; return f }()
    static let plain = ISO8601DateFormatter()
}
func number(_ value: Any?) -> Double? {
    guard let n = value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
    let x = n.doubleValue
    return x.isFinite && x >= 0 ? x : nil
}
import CoreFoundation

struct CheckEvidence: Codable, Identifiable {
    var id: String
    var ok: Bool
    var latency: Double?
    var target: String
    var kind: String
    var detail: String
    var confirmedDown: Bool
    var time: Double
    static func parse(_ raw: [String:Any], down: Bool = false) -> CheckEvidence? {
        guard let id = raw["id"] as? String, let ok = raw["ok"] as? Bool, let time = timestamp(raw["started_at"]) else { return nil }
        return .init(id: id, ok: ok, latency: ok ? number(raw["latency_ms"]) : nil,
                     target: raw["target"] as? String ?? "", kind: raw["kind"] as? String ?? "",
                     detail: raw["detail"] as? String ?? "", confirmedDown: down, time: time)
    }
    var name: String { friendlyCheck(id) }
}
func friendlyCheck(_ id: String) -> String {
    let names = ["orbi": "Main Orbi", "gateway": "AT&T gateway", "cloudflare": "Cloudflare", "google": "Google", "system": "Mac resolver", "peer": "Other computer", "satellite_1": "Satellite 1", "satellite_2": "Satellite 2"]
    for suffix in ["_icmp", "_tcp", "_dns", "_https", "_identity"] where id.hasSuffix(suffix) {
        let prefix = String(id.dropLast(suffix.count))
        let method = ["_icmp":"ping", "_tcp":"connection", "_dns":"DNS", "_https":"fresh HTTPS", "_identity":"identity"][suffix]!
        return (names[prefix] ?? prefix) + " · " + method
    }
    return id.replacingOccurrences(of: "_", with: " ")
}

struct Episode: Codable, Identifiable {
    var check: String
    var start: Double
    var recovery: Double?
    var confirmed: Double?
    var id: String { check + String(start) }
}
struct IncidentEvidence: Codable, Identifiable {
    var id: String
    var start: Double
    var recovery: Double?
    var uncertain: Bool
    var hypotheses: [String]
    var episodes: [Episode]
    var commissioning: Bool { commissioningIDs.contains(id) }
    static func parse(_ raw: [String:Any]) -> IncidentEvidence? {
        guard let id = raw["id"] as? String, let start = timestamp(raw["started_at"]) else { return nil }
        let episodes = (raw["episodes"] as? [[String:Any]] ?? []).compactMap { r -> Episode? in
            guard let check = r["check"] as? String, let start = timestamp(r["first_failed_at"]) else { return nil }
            return .init(check: check, start: start, recovery: timestamp(r["first_recovered_at"]), confirmed: timestamp(r["confirmed_at"]))
        }
        return .init(id: id, start: start, recovery: timestamp(raw["recovered_at"]), uncertain: raw["has_observation_gap"] as? Bool ?? false,
                     hypotheses: raw["hypotheses"] as? [String] ?? [], episodes: episodes)
    }
}

struct InternetInterruption: Identifiable {
    var incidentID: String
    var start: Double
    var recovery: Double?
    var uncertain: Bool
    var id: String { incidentID + String(start) }
}

func internetInterruptions(_ incidents: [IncidentEvidence], start: Double, end: Double) -> [InternetInterruption] {
    var result: [InternetInterruption] = []
    for incident in incidents where !incident.commissioning {
        let cloudflare = incident.episodes.filter { $0.check == "cloudflare_https" && $0.confirmed != nil }
        let google = incident.episodes.filter { $0.check == "google_https" && $0.confirmed != nil }
        var intervals: [InternetInterruption] = []
        for a in cloudflare {
            for b in google {
                let onset = max(a.start,b.start)
                let finish = min(a.recovery ?? end,b.recovery ?? end)
                guard onset < finish, max(a.confirmed!,b.confirmed!) <= finish, onset <= end, finish >= start else { continue }
                let recovery = [a.recovery,b.recovery].compactMap { $0 }.min()
                intervals.append(.init(incidentID:incident.id,start:onset,recovery:recovery,uncertain:incident.uncertain))
            }
        }
        for interval in intervals.sorted(by: { $0.start < $1.start }) {
            if let last = result.last, last.incidentID == interval.incidentID, interval.start <= (last.recovery ?? end) {
                result[result.count-1].recovery = last.recovery == nil || interval.recovery == nil ? nil : max(last.recovery!,interval.recovery!)
            } else { result.append(interval) }
        }
    }
    return result.sorted { $0.start > $1.start }
}

func observerName(_ host: String) -> String {
    let name = host.replacingOccurrences(of:".local",with:"")
    return name == "Mini-One" ? "Mini-One" : name == "Mini-Two" ? "Mini-Two" : host
}

struct DeviceEvidence: Codable, Identifiable {
    var id: String
    var name: String
    var address: String
    var status: String
    var identity: String
    var attachment: String
    var inventoryAt: String
    var note: String
    var observed: Double
    var lastReply: Double?
    var latency: Double?
    var isLocal: Bool
    func stale(at now: Double) -> Bool { now-observed > 180 || now < observed-5 }
    static func parse(_ raw: [String:Any]) -> DeviceEvidence? {
        guard let id = raw["id"] as? String, let name = raw["name"] as? String,
              let time = timestamp(raw["observed_at"]) else { return nil }
        return .init(id:id, name:name, address:raw["address"] as? String ?? "", status:raw["status"] as? String ?? "unknown",
                     identity:raw["identity"] as? String ?? "unverified", attachment:raw["attachment"] as? String ?? "Unknown",
                     inventoryAt:raw["inventory_at"] as? String ?? "Unknown", note:raw["note"] as? String ?? "",
                     observed:time, lastReply:timestamp(raw["last_reply_at"]), latency:number(raw["latency_ms"]), isLocal:raw["is_local"] as? Bool ?? false)
    }
}
struct DeviceEvent: Codable, Identifiable {
    var name: String
    var kind: String
    var time: Double
    var onset: Double
    var uncertain: Bool
    var id: String { name + kind + String(time) }
    static func parse(_ raw: [String:Any]) -> DeviceEvent? {
        guard let name = raw["name"] as? String, let kind = raw["type"] as? String, let time = timestamp(raw["at"]) else { return nil }
        return .init(name:name, kind:kind, time:time, onset:timestamp(raw["first_failed_at"] ?? raw["first_recovered_at"]) ?? time, uncertain:raw["continuity_uncertain"] as? Bool ?? false)
    }
}

struct HostContext: Codable {
    var at: Double
    var interval: Double?
    var cpu: Double?
    var cpuStatus: String
    var pressure: String
    var swap: Double?
    var interfaces: [String]
    func stale(at now: Double) -> Bool { now-at > 180 || now < at-5 }
    static func parse(_ raw: [String:Any]) -> HostContext? {
        guard let at = timestamp(raw["at"]) else { return nil }
        let interfaces = raw["interfaces"] as? [String:[String:Any]] ?? [:]
        let details = interfaces.keys.sorted().map { name -> String in
            let row = interfaces[name]!
            guard row["status"] as? String == "available", let rx = number(row["rx_mbps"]), let tx = number(row["tx_mbps"]), let re = number(row["rx_errors_delta"]), let te = number(row["tx_errors_delta"]) else { return "\(name): rates unavailable (\(row["status"] as? String ?? "unknown"))" }
            return String(format:"%@: receive %.2f · send %.2f Mbps · errors %.0f in / %.0f out",name,rx,tx,re,te)
        }
        let cpu = number(raw["cpu_busy_percent"])
        return .init(at:at, interval:number(raw["interval_seconds"]), cpu:raw["cpu_status"] as? String == "available" && (cpu ?? 101) <= 100 ? cpu:nil, cpuStatus:raw["cpu_status"] as? String ?? "unavailable", pressure:raw["memory_pressure"] as? String ?? "unknown", swap:number(raw["swap_used_mib"]), interfaces:details)
    }
}

struct DiagnosticEvidence: Codable {
    var completed: Double
    var availablePages: Int
    var details: [String]
    var hostContext: HostContext? = nil
    func stale(at now: Double) -> Bool { now-completed > 180 || now < completed-5 }
    static func parse(_ raw: [String:Any]) -> DiagnosticEvidence? {
        guard raw["type"] as? String == "diagnostic_snapshot", let completed = timestamp(raw["finished_at"]) else { return nil }
        let pages = raw["gateway"] as? [String:[String:Any]] ?? [:]
        func field(_ page: String, _ key: String) -> String? {
            for table in pages[page]?["tables"] as? [[String:Any]] ?? [] {
                if let values = (table["fields"] as? [String:Any])?[key] as? [Any], let first = values.first { return String(describing:first) }
            }
            return nil
        }
        var details: [String] = []
        details.append("AT&T broadband: " + (field("broadbandstatistics", "Broadband Connection") ?? "unavailable"))
        details.append("Optical link: " + (field("fiberstat", "Optical WAN Operational Status") ?? "unavailable"))
        if let power = (pages["fiberstat"]?["optical_readings"] as? [String:Double])?["Rx Power"] { details.append(String(format:"Optical receive power: %.1f dBm", power/10)) }
        if let bps = field("lanstatistics", "Transmit Speed"), let value = Double(bps) { details.append(String(format:"Gateway port 1 link: %.1f Gbps", value/1_000_000_000)) }
        let ipv6 = raw["ipv6"] as? [[String:Any]] ?? []
        details.append("IPv6 HTTPS: \(ipv6.filter { $0["ok"] as? Bool == true }.count)/\(ipv6.count) replies · requires a working IPv6 baseline")
        return .init(completed:completed, availablePages:pages.values.filter { $0["status"] as? String == "available" }.count, details:details, hostContext:(raw["host_metrics"] as? [String:Any]).flatMap(HostContext.parse))
    }
}

struct CurrentEvidence: Codable {
    var host: String
    var completed: Double
    var interval: Double
    var interface: String
    var wifiInterface: String?
    var wifiSignal: String?
    var wifiChannel: String?
    var wifiAt: Double?
    var checks: [CheckEvidence]
    var incidents: [IncidentEvidence]
    var speedActive: Bool
    var devices: [DeviceEvidence]? = nil
    var deviceEvents: [DeviceEvent]? = nil
    var diagnostics: DiagnosticEvidence? = nil
    var recordingPaused: Bool? = nil
    var path: String { interface == "en0" ? "Ethernet · en0" : interface == wifiInterface || interface == "en1" ? "Wi-Fi · \(interface)" : "Interface \(interface)" }
    var passing: Int { checks.filter(\.ok).count }
    var openIncident: IncidentEvidence? { incidents.first { $0.recovery == nil } }
    func stale(at now: Double) -> Bool { recordingPaused == true || now - completed > max(45, interval * 3) || now < completed - 5 }
    var internet: Int { groupStatus(checks, ids: ["cloudflare_https", "google_https"]) }
    static func parse(_ raw: [String:Any]) -> CurrentEvidence? {
        guard let host = (raw["host"] as? [String:Any])?["hostname"] as? String,
              let completed = timestamp(raw["last_completed_at"]), let all = raw["checks"] as? [String:[String:Any]], !all.isEmpty else { return nil }
        let checks = all.compactMap { key, s -> CheckEvidence? in
            guard let latest = s["latest"] as? [String:Any], latest["id"] as? String == key else { return nil }
            return CheckEvidence.parse(latest, down: s["down"] as? Bool ?? false)
        }.sorted { $0.id < $1.id }
        guard checks.count == all.count, Set(checks.map(\.id)).count == checks.count else { return nil }
        var incidents = (raw["recent_incidents"] as? [[String:Any]] ?? []).compactMap(IncidentEvidence.parse)
        if let incident = raw["incident"] as? [String:Any], let item = IncidentEvidence.parse(incident) { incidents.append(item) }
        let network = raw["network"] as? [String:Any] ?? [:], wifi = raw["wifi"] as? [String:Any] ?? [:]
        return .init(host: host, completed: completed, interval: number(raw["interval_seconds"]) ?? 30,
                     interface: network["interface"] as? String ?? "unknown", wifiInterface: wifi["interface"] as? String,
                     wifiSignal: wifi["signal_noise"] as? String, wifiChannel: wifi["channel"] as? String, wifiAt: timestamp(wifi["at"]),
                     checks: checks, incidents: incidents.sorted { $0.start > $1.start }, speedActive: raw["speed_test_active"] as? Bool ?? false,
                     devices:(raw["devices"] as? [[String:Any]])?.compactMap(DeviceEvidence.parse),
                     deviceEvents:(raw["device_events"] as? [[String:Any]])?.compactMap(DeviceEvent.parse),
                     diagnostics:(raw["diagnostic_snapshot"] as? [String:Any]).flatMap(DiagnosticEvidence.parse), recordingPaused:raw["recording_paused"] as? Bool)
    }
}

let laneNames = ["Internet HTTPS", "Main Orbi", "AT&T gateway", "DNS resolution", "Satellite 1", "Satellite 2", "Other computer"]
let laneIDs = [["cloudflare_https", "google_https"], ["orbi_icmp", "orbi_tcp"], ["gateway_icmp", "gateway_tcp"], ["system_dns", "orbi_dns", "cloudflare_dns", "google_dns"], ["satellite_1_icmp", "satellite_1_tcp", "satellite_1_identity"], ["satellite_2_icmp", "satellite_2_tcp", "satellite_2_identity"], ["peer_icmp"]]

func configuredLaneIndices(_ checks: [CheckEvidence]) -> [Int] {
    let ids = Set(checks.map(\.id))
    return laneIDs.indices.filter { index in index < 4 || laneIDs[index].contains { ids.contains($0) } }
}

func groupStatus(_ checks: [CheckEvidence], ids: [String]) -> Int {
    let found = checks.filter { ids.contains($0.id) }
    guard found.count == ids.count, Set(found.map(\.id)) == Set(ids) else { return -1 }
    let good = found.filter(\.ok).count
    return good == found.count ? 2 : good == 0 ? 0 : 1
}
struct SamplePoint: Codable, Identifiable {
    var time: Double
    var interval: Double
    var lanes: [Int]
    var cloudflare: Double?
    var google: Double?
    var orbi: Double?
    var failed: Int
    var total: Int
    var pingFailed: Int
    var pingTotal: Int
    var loaded: Bool
    var interface: String
    var loadKnown: Bool? = nil
    var id: Double { time }
    var valid: Bool {
        time.isFinite && time >= 0 && (15...300).contains(interval) && lanes.count == laneNames.count &&
        lanes.allSatisfy { (-1...2).contains($0) } && (1...100).contains(total) &&
        failed >= 0 && failed <= total && (0...2).contains(pingTotal) && pingFailed >= 0 && pingFailed <= pingTotal &&
        pingTotal <= total && [cloudflare,google,orbi].allSatisfy { $0 == nil || ($0!.isFinite && $0! >= 0) }
    }
    static func parse(_ raw: [String:Any]) -> SamplePoint? {
        if raw["schema"] as? String == "network-monitor.sample.v1" {
            guard let bytes = try? JSONSerialization.data(withJSONObject:raw),
                  let point = try? JSONDecoder().decode(SamplePoint.self,from:bytes),
                  point.valid else { return nil }
            return point
        }
        guard let time = timestamp(raw["started_at"]), let list = raw["checks"] as? [[String:Any]], !list.isEmpty else { return nil }
        let checks = list.compactMap { CheckEvidence.parse($0) }
        guard checks.count == list.count else { return nil }
        let latency = { (id: String) in checks.first { $0.id == id }?.latency }
        let pings = checks.filter { ["cloudflare_icmp", "google_icmp"].contains($0.id) }
        let point = SamplePoint(time: time, interval: number(raw["interval_seconds"]) ?? 30,
                     lanes: laneIDs.map { groupStatus(checks, ids: $0) }, cloudflare: latency("cloudflare_icmp"), google: latency("google_icmp"), orbi: latency("orbi_icmp"),
                     failed: checks.filter { !$0.ok }.count, total: checks.count, pingFailed: pings.filter { !$0.ok }.count, pingTotal: pings.count,
                     loaded: raw["speed_test_active"] as? Bool ?? false, interface: (raw["network"] as? [String:Any])?["interface"] as? String ?? "unknown", loadKnown:raw["speed_test_active"] is Bool)
        return point.valid ? point : nil
    }
}
struct RecentPathMetrics {
    var replies: Int
    var median: Double?
    var p95: Double?
    var variation: Double?
}

func loadLatency(_ samples: [SamplePoint], loaded: Bool) -> (count:Int, median:Double?, p95:Double?) {
    let values = samples.filter { ($0.loadKnown == true || $0.loaded) && $0.loaded == loaded }.compactMap(\.cloudflare).filter { $0.isFinite && $0 >= 0 }.sorted()
    guard !values.isEmpty else { return (0,nil,nil) }
    let middle = values.count/2
    return (values.count, values.count % 2 == 0 ? (values[middle-1]+values[middle])/2:values[middle], values[Int(ceil(Double(values.count)*0.95))-1])
}


func recentPathMetrics(_ samples: [SamplePoint], key: KeyPath<SamplePoint, Double?>, end: Double) -> RecentPathMetrics {
    let rows = samples.filter { $0.time >= end-300 && $0.time <= end }.sorted { $0.time < $1.time }
    let values = rows.compactMap { $0[keyPath:key] }.filter { $0.isFinite && $0 >= 0 }.sorted()
    var changes: [Double] = []
    for (a,b) in zip(rows, rows.dropFirst()) {
        if let x = a[keyPath:key], let y = b[keyPath:key], x.isFinite, y.isFinite,
           b.time > a.time, b.time-a.time <= a.interval*1.5, a.interface == b.interface {
            changes.append(abs(y-x))
        }
    }
    let middle = values.count/2
    let median: Double? = values.isEmpty ? nil : values.count % 2 == 0 ? (values[middle-1]+values[middle])/2 : values[middle]
    return .init(replies:values.count, median:median,
                 p95:values.isEmpty ? nil : values[max(0,Int(ceil(Double(values.count)*0.95))-1)],
                 variation:changes.isEmpty ? nil : changes.reduce(0,+)/Double(changes.count))
}

struct SpeedPoint: Codable, Identifiable {
    var time: Double
    var end: Double
    var status: String
    var down: Double?
    var up: Double?
    var idle: Double?
    var downRPM: Double?
    var upRPM: Double?
    var interface: String
    var reason: String?
    var id: Double { time }
    static func parse(_ raw: [String:Any]) -> SpeedPoint? {
        guard let time = timestamp(raw["started_at"]), let status = raw["status"] as? String else { return nil }
        return .init(time: time, end: timestamp(raw["finished_at"]) ?? time, status: status,
                     down: number(raw["download_mbps"]), up: number(raw["upload_mbps"]), idle: number(raw["idle_latency_ms"]),
                     downRPM: number(raw["download_responsiveness_rpm"]), upRPM: number(raw["upload_responsiveness_rpm"]),
                     interface: raw["requested_interface"] as? String ?? "unknown", reason: raw["reason"] as? String)
    }
}
struct UserObservation: Codable, Identifiable {
    var id: String = UUID().uuidString
    var time: Double
    var recorded: Double
    var host: String
    var service: String
    var othersWorked: String
    var note: String
}
struct InvestigationPoint: Codable {
    var time: Double
    var target: String
    var phase: String
    var interface: String
    var ok: Bool
    var latency: Double?
}
struct InvestigationGroup: Codable, Identifiable {
    var target: String
    var phase: String
    var interface: String
    var attempted: Int
    var missed: Int
    var loss: Double
    var p10: Double?
    var median: Double?
    var p95: Double?
    var maximum: Double?
    var id: String { target+phase+interface }
}
struct InvestigationReport: Codable, Identifiable {
    var schema: String
    var id: String
    var kind: String
    var reason: String
    var host: String
    var time: Double
    var end: Double
    var status: String
    var details: [String]
    var groups: [InvestigationGroup]
    var points: [InvestigationPoint]
    var title: String { ["close-up":"One-minute close-up", "load-comparison":"Latency around a speed test", "routes":"Route investigation", "lan":"Between-Mini LAN test"][kind] ?? "Investigation" }
    var valid: Bool {
        schema == "network-monitor.investigation.v1" && time.isFinite && end.isFinite && time >= 0 && end >= time && end-time <= 300 &&
        ["close-up","load-comparison","routes","lan"].contains(kind) && ["complete","incomplete","cancelled"].contains(status) && id.count <= 64 && reason.count <= 2000 && host.count <= 100 && details.count <= 20 && details.allSatisfy { $0.count <= 2000 } &&
        points.count <= 300 && groups.count <= 36 && Set(groups.map(\.id)).count == groups.count &&
        points.allSatisfy { ["Main Orbi","Cloudflare","Google"].contains($0.target) && ["before","during","after","observation"].contains($0.phase) && $0.interface.count <= 30 && $0.time.isFinite && $0.time >= time-5 && $0.time <= end+5 && ($0.latency == nil || ($0.latency!.isFinite && $0.latency! >= 0)) } &&
        groups.allSatisfy { ["Main Orbi","Cloudflare","Google"].contains($0.target) && ["before","during","after","observation"].contains($0.phase) && $0.interface.count <= 30 && $0.attempted > 0 && $0.attempted <= 300 && $0.missed >= 0 && $0.missed <= $0.attempted && $0.loss.isFinite && abs($0.loss-100*Double($0.missed)/Double($0.attempted)) < 0.001 && [$0.p10,$0.median,$0.p95,$0.maximum].allSatisfy { $0 == nil || ($0!.isFinite && $0! >= 0) } }
    }
}

struct DashboardSnapshot: Codable {
    var schema = 1
    var captured: Double
    var state: CurrentEvidence
    var samples: [SamplePoint]
    var speeds: [SpeedPoint]
    var notes: [UserObservation]
    var investigations: [InvestigationReport]? = nil
    func validate() throws {
        guard (investigations?.count ?? 0) <= 4, investigations?.allSatisfy({ $0.valid && $0.end <= captured+5 }) ?? true, schema == 1, captured.isFinite, captured >= 0, captured <= Date().timeIntervalSince1970+300, state.completed.isFinite, state.completed >= 0, state.completed <= captured+5, (15...300).contains(state.interval), !state.checks.isEmpty,
              state.checks.count <= 100, (state.devices?.count ?? 0) <= 12, (state.deviceEvents?.count ?? 0) <= 200,
              state.devices?.allSatisfy({ $0.observed.isFinite && ($0.lastReply?.isFinite ?? true) }) ?? true,
              samples.count <= 100_000, speeds.count <= 10_000, notes.count <= 10_000,
              samples.allSatisfy({ $0.valid && $0.time <= captured+5 }),
              zip(samples,samples.dropFirst()).allSatisfy({ $0.time < $1.time }),
              Set(state.checks.map(\.id)).count == state.checks.count,
              state.checks.allSatisfy({ $0.time.isFinite && $0.time >= 0 && $0.time <= captured+5 && ($0.latency == nil || ($0.latency!.isFinite && $0.latency! >= 0)) }),
              speeds.allSatisfy({ $0.time.isFinite && $0.time >= 0 && $0.end.isFinite && $0.end <= captured+5 && $0.end >= $0.time && [$0.down,$0.up,$0.idle,$0.downRPM,$0.upRPM].allSatisfy { $0 == nil || ($0!.isFinite && $0! >= 0) } }),
              notes.allSatisfy({ $0.time.isFinite && $0.time >= 0 && $0.time <= captured+5 && $0.recorded.isFinite && $0.recorded <= captured+5 && $0.note.count <= 2000 }) else {
            throw NSError(domain: "NetworkMonitor", code: 1, userInfo: [NSLocalizedDescriptionKey:"This is not a supported Network Monitor snapshot."])
        }
    }
}

struct LaneSpan: Identifiable {
    var lane: String
    var start: Double
    var end: Double
    var status: Int
    var id: String { lane + String(start) }
}
func laneSpans(samples: [SamplePoint], start: Double, end: Double) -> [LaneSpan] {
    var output: [LaneSpan] = []
    for (index, lane) in laneNames.enumerated() {
        var spans: [LaneSpan] = [], cursor = start
        for (position, sample) in samples.enumerated() where sample.time + sample.interval > start && sample.time < end {
            let next = position+1 < samples.count ? samples[position+1].time : sample.time+sample.interval
            let observedEnd = next-sample.time <= sample.interval*1.5 ? next : sample.time+sample.interval
            let left = max(start, sample.time), right = min(end, observedEnd)
            if left > cursor { spans.append(.init(lane: lane, start: cursor, end: left, status: -1)) }
            if right > left {
                let value = sample.lanes[index]
                if let last = spans.last, last.status == value && abs(last.end-left) < 0.01 {
                    spans[spans.count-1].end = right
                } else { spans.append(.init(lane: lane, start: left, end: right, status: value)) }
                cursor = max(cursor, right)
            }
        }
        if cursor < end { spans.append(.init(lane: lane, start: cursor, end: end, status: -1)) }
        output += spans
    }
    return output
}
struct LatencyPoint: Identifiable {
    var time: Double
    var value: Double
    var series: String
    var segment: Int
    var loaded: Bool
    var id: String { series + String(time) }
    var group: String { series + String(segment) }
}
func latencyPoints(samples: [SamplePoint], start: Double, maxBuckets: Int = 500) -> [LatencyPoint] {
    let selected = samples.filter { $0.time >= start }
    guard let first = selected.first, let last = selected.last else { return [] }
    let bucketSeconds = max(1, (last.time - first.time) / Double(maxBuckets))
    var output: [LatencyPoint] = []
    for series in ["Cloudflare", "Google"] {
        var segment = 0, previous: SamplePoint?, bucket: Int?, pending: LatencyPoint?
        for sample in selected {
            let value = series == "Cloudflare" ? sample.cloudflare : sample.google
            if value == nil || (previous != nil && sample.time - previous!.time > max(sample.interval, previous!.interval) * 3) {
                if let p = pending { output.append(p); pending = nil }
                bucket = nil; segment += 1
            }
            if let value = value {
                let b = Int((sample.time-first.time)/bucketSeconds)
                let p = LatencyPoint(time: sample.time, value: value, series: series, segment: segment, loaded: sample.loaded)
                if b == bucket, let old = pending {

                    if value > old.value { pending = p }
                } else {
                    if let old = pending { output.append(old) }
                    pending = p; bucket = b
                }
            }
            previous = sample
        }
        if let p = pending { output.append(p) }
    }
    return output
}
func observedSeconds(samples: [SamplePoint], start: Double, end: Double) -> Double {
    var covered = 0.0, cursor = start
    for sample in samples {
        let a = max(start, sample.time, cursor), b = min(end, sample.time+sample.interval)
        if b > a { covered += b-a; cursor = b }
    }
    return covered
}


func readCompleteJSONLines(_ handle: FileHandle, from offset: UInt64, through end: UInt64,
                           chunkSize: Int = 64*1024, consume: (Data) -> Void) throws -> UInt64 {
    precondition(chunkSize > 0)
    var pending = Data(), readOffset = offset, committed = offset
    while readOffset < end {
        let count = Int(min(UInt64(chunkSize),end-readOffset))
        let didRead = try autoreleasepool { () throws -> Bool in
            guard let chunk = try handle.read(upToCount:count), !chunk.isEmpty else { return false }
            readOffset += UInt64(chunk.count); pending.append(chunk)
            var lineStart = pending.startIndex
            for index in pending.indices where pending[index] == 10 {
                if index > lineStart { consume(Data(pending[lineStart..<index])) }
                lineStart = index+1
            }
            if lineStart > pending.startIndex {
                committed += UInt64(lineStart-pending.startIndex)
                pending = Data(pending[lineStart...])
            }
            return true
        }
        if !didRead { break }
    }
    return committed
}


final class EvidenceReader: @unchecked Sendable {
    var root: URL
    var offsets: [String:UInt64] = [:]
    var samples: [SamplePoint] = []
    var speeds: [SpeedPoint] = []
    var notes: [UserObservation] = []
    var malformed = 0
    init(root: URL) { self.root = root }
    func update(now: Double = Date().timeIntervalSince1970) throws -> DashboardSnapshot {
        let stateURL = root.appendingPathComponent("state.json")
        guard let stateSize = try stateURL.resourceValues(forKeys:[.fileSizeKey]).fileSize, stateSize <= 1024*1024 else {
            throw NSError(domain:"NetworkMonitor",code:2,userInfo:[NSLocalizedDescriptionKey:"Recorder state exceeds its size limit."])
        }
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: stateURL)) as? [String:Any] ?? [:]
        guard let state = CurrentEvidence.parse(raw) else { throw NSError(domain:"NetworkMonitor", code:2, userInfo:[NSLocalizedDescriptionKey:"The recorder's state is incomplete or unreadable."]) }
        let files = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: [.fileSizeKey])
            .filter { $0.pathExtension == "jsonl" && ["samples-", "performance-", "observations-"].contains(where: $0.lastPathComponent.hasPrefix) }.sorted { $0.lastPathComponent < $1.lastPathComponent }
        var changed = false
        for file in files {
            let size = UInt64((try file.resourceValues(forKeys: [.fileSizeKey])).fileSize ?? 0)
            var offset = offsets[file.lastPathComponent] ?? 0
            if offset > size { offset = 0 }
            guard size > offset else { continue }
            changed = true
            let handle = try FileHandle(forReadingFrom: file)
            defer { try? handle.close() }
            try handle.seek(toOffset: offset)

            guard size <= 9*1024*1024 else { continue }
            offsets[file.lastPathComponent] = try readCompleteJSONLines(handle, from:offset, through:size) { line in


                autoreleasepool {
                    do {
                        if file.lastPathComponent.hasPrefix("observations-") {
                            let note = try JSONDecoder().decode(UserObservation.self, from:line)
                            if !notes.contains(where: { $0.id == note.id }) { notes.append(note) }
                        } else {
                            guard let r = try JSONSerialization.jsonObject(with:line) as? [String:Any] else { malformed += 1; return }
                            if file.lastPathComponent.hasPrefix("samples-") {
                                if let p = SamplePoint.parse(r) { if p.time >= now-7*86400 { samples.append(p) } } else { malformed += 1 }
                            } else {
                                if let p = SpeedPoint.parse(r) { speeds.append(p) } else { malformed += 1 }
                            }
                        }
                    } catch { malformed += 1 }
                }
            }
        }
        let present = Set(files.map(\.lastPathComponent)); offsets = offsets.filter { present.contains($0.key) }
        if changed {
        samples = Array(Dictionary(samples.filter { $0.time >= now-7*86400 }.map { ($0.time,$0) }, uniquingKeysWith: { _,b in b }).values).sorted { $0.time < $1.time }
        speeds = Array(Dictionary(speeds.filter { $0.time >= now-180*86400 }.map { ($0.time,$0) }, uniquingKeysWith: { _,b in b }).values).sorted { $0.time < $1.time }
        notes = notes.filter { $0.recorded >= now-180*86400 }.sorted { $0.time > $1.time }
        }


        if let first = samples.first, first.time < now-7*86400 {
            samples.removeAll { $0.time < now-7*86400 }
        }
        if let first = speeds.first, first.time < now-180*86400 { speeds.removeAll { $0.time < now-180*86400 } }
        if notes.contains(where: { $0.recorded < now-180*86400 }) { notes.removeAll { $0.recorded < now-180*86400 } }
        var investigations: [InvestigationReport] = []
        let reportURL = root.appendingPathComponent("investigation-latest.json")
        if let size = try? reportURL.resourceValues(forKeys:[.fileSizeKey]).fileSize, size <= 512*1024,
           let bytes = try? Data(contentsOf:reportURL), let reports = try? JSONDecoder().decode([InvestigationReport].self,from:bytes), reports.count <= 4 {
            investigations = reports.filter { $0.valid && $0.end <= now+5 && $0.end >= now-30*86400 }
        }
        return .init(captured: now, state: state, samples: samples, speeds: speeds, notes: notes, investigations:investigations)
    }
}


struct ChartWindow {
    static let minimumSpan: Double = 60
    static func fit(_ requested: ClosedRange<Double>, inside bounds: ClosedRange<Double>) -> ClosedRange<Double> {
        let width = min(bounds.upperBound-bounds.lowerBound, max(minimumSpan,requested.upperBound-requested.lowerBound))
        let center = (requested.lowerBound+requested.upperBound)/2
        let start = max(bounds.lowerBound,min(center-width/2,bounds.upperBound-width))
        return start...(start+width)
    }
    static func zoom(_ current: ClosedRange<Double>, factor: Double, around anchor: Double?, inside bounds: ClosedRange<Double>) -> ClosedRange<Double> {
        let center = min(current.upperBound,max(current.lowerBound,anchor ?? (current.lowerBound+current.upperBound)/2))
        let width = max(minimumSpan,(current.upperBound-current.lowerBound)*factor)
        return fit((center-width/2)...(center+width/2),inside:bounds)
    }
    static func move(_ current: ClosedRange<Double>, direction: Double, inside bounds: ClosedRange<Double>) -> ClosedRange<Double> {
        let shift = (current.upperBound-current.lowerBound)*0.5*direction
        return fit((current.lowerBound+shift)...(current.upperBound+shift),inside:bounds)
    }
}

func latencyPoints(samples: [SamplePoint], window: ClosedRange<Double>) -> [LatencyPoint] {

    latencyPoints(samples:samples.filter { $0.time <= window.upperBound },start:window.lowerBound)
}
func inspectedSample(_ samples: [SamplePoint], at time: Double, window: ClosedRange<Double>) -> SamplePoint? {
    guard let nearest = samples.filter({ window.contains($0.time) }).min(by:{ abs($0.time-time)<abs($1.time-time) }),
          abs(nearest.time-time) <= max(8,nearest.interval/2) else { return nil }
    return nearest
}

func sharingStatus(state: String, updated: Double, lastExchange: Double?, now: Double) -> String {
    guard updated > 0, now-updated >= -5, now-updated <= 90 else { return "Sync worker not reporting" }
    if state == "not_configured" { return "Not configured" }
    if state == "connected", let exchange = lastExchange, now-exchange >= -5, now-exchange <= 90 { return "Connected" }
    return "Disconnected · recording continues"
}

final class PeerEvidenceReader: @unchecked Sendable {
    private var reader: EvidenceReader?
    private var generation: String?
    private var cached: DashboardSnapshot?
    func reset() { reader = nil; generation = nil; cached = nil }
    func update(root: URL) throws -> DashboardSnapshot? {
        let peerRoot = root.appendingPathComponent("peer")
        guard FileManager.default.fileExists(atPath:peerRoot.appendingPathComponent("current.json").path) else { reset(); return nil }
        let fd = Darwin.open(peerRoot.appendingPathComponent("cache.lock").path,O_RDONLY | O_NOFOLLOW)
        guard fd >= 0 else { return cached }
        defer { Darwin.close(fd) }
        guard flock(fd,LOCK_SH | LOCK_NB) == 0 else { return cached }
        defer { flock(fd,LOCK_UN) }
        let data = try Data(contentsOf:peerRoot.appendingPathComponent("current.json"))
        guard let pointer = try JSONSerialization.jsonObject(with:data) as? [String:Any],
              let directory = pointer["directory"] as? String, ["slot-a","slot-b"].contains(directory) else { return nil }
        let path = root.appendingPathComponent("peer/"+directory)
        let next = pointer["generation"] as? String
        if reader == nil || generation != next { reader = EvidenceReader(root:path); generation = next }
        reader?.root = path
        cached = try reader?.update()
        return cached
    }
}

func observationIsPaused(_ state: CurrentEvidence?, local: Bool, localPaused: Bool) -> Bool {
    state?.recordingPaused == true || (local && localPaused)
}
