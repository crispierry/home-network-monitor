import SwiftUI
import AppKit
import UniformTypeIdentifiers
import Darwin

@MainActor final class DashboardStore: ObservableObject {
    @Published var live: DashboardSnapshot?
    @Published var peer: DashboardSnapshot?
    @Published var scope = "This Mini"
    @Published var syncStatus = "Not configured"
    @Published var lastSync: Double?
    private var initialScopeChosen = false
    var expectedPeer: String? {
        peer?.state.host ?? live?.state.checks.first(where: { $0.id == "peer_icmp" }).map { $0.target }
    }
    var hasMultipleObservers: Bool { expectedPeer != nil }
    var peerSubtitle: String {
        guard let peer = peer else { return syncStatus == "Not configured" ? "Sharing not configured" : "Not connected · awaiting data" }
        if peer.state.stale(at:now) { return "Observation stale · health unknown" }
        return syncStatus == "Connected" ? "Connected · recent evidence" : "Disconnected · saved evidence"
    }
    @Published var localBytes: Double?
    @Published var syncBytes: Double?
    private let peerCache = PeerEvidenceReader()
    @Published var resourceSummary = "Process measurements unavailable. Use Activity Monitor to inspect CPU and memory; recording works independently."
    var syncRoot: URL { fixture ? root.appendingPathComponent("Sync") : programHome.appendingPathComponent("Sync") }
    var wholeHome: Bool { scope == "Both Minis" && !useImported }
    var selectedPeer: Bool { scope == "Other Mini" && !useImported }
    var homeSnapshots: [DashboardSnapshot] { [live,peer].compactMap{$0}.sorted{$0.state.host < $1.state.host} }
    @Published var imported: DashboardSnapshot?
    @Published var useImported = false
    @Published var now = Date().timeIntervalSince1970
    @Published var error: String?
    @Published var message: String?
    @Published var loading = true
    @Published var paused = false
    @Published var managing = false
    @Published var malformed = 0
    @Published var speedRunning = false
    @Published var investigationRunning = false
    @Published var backgroundInvestigation = false
    @Published var showObservation = false
    var observationService = "Workbench / remote access"
    @Published var section = "Overview"
    @Published var hours = 24
    let root: URL
    let fixture: Bool
    private let worker = DispatchQueue(label:"network-monitor.evidence", qos:.utility, autoreleaseFrequency:.workItem)
    private var reader: EvidenceReader
    private var busy = false
    private var timer: Timer?
    var snapshot: DashboardSnapshot? { useImported ? imported : selectedPeer ? peer : live }
    var isLive: Bool { !useImported && !fixture }
    var isLocal: Bool { !useImported && !selectedPeer && !fixture }
    var canRecordObservation: Bool { !useImported && !selectedPeer && live != nil && (!fixture || root.standardizedFileURL != evidenceHome.standardizedFileURL) }
    var reference: Double { isLive ? now : snapshot?.captured ?? now }
    var start: Double { reference - Double(hours)*3600 }
    var samples: [SamplePoint] { snapshot?.samples.filter { $0.time + $0.interval >= start && $0.time <= reference } ?? [] }
    var chartStart: Double { max(start, min(samples.first?.time ?? start, snapshot?.speeds.first(where: { $0.time >= start })?.time ?? reference)) }
    var chartEnd: Double { max(chartStart + 60, reference) }
    var currentStale: Bool { snapshot?.state.stale(at: reference) ?? true }
    var displayedIncidents: [IncidentEvidence] { snapshot?.state.incidents.filter { ($0.recovery ?? reference) >= start && $0.start <= reference } ?? [] }
    var displayedNotes: [UserObservation] { snapshot?.notes.filter { $0.time >= start && $0.time <= reference } ?? [] }
    var latestSpeed: SpeedPoint? { snapshot?.speeds.last { $0.status == "success" } }
    init(root: URL = evidenceHome, fixture: Bool = false) {
        self.root = root; self.fixture = fixture; self.reader = EvidenceReader(root: root)
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self = self else { return }
                let time = Date().timeIntervalSince1970
                if NSApp.isHidden && time-self.now < 30 { return }
                self.now = time; self.refresh()
            }
        }
    }
    func refresh() {
        guard !busy && !managing else { return }; busy = true
        paused = !fixture && FileManager.default.fileExists(atPath:FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/NetworkMonitor/monitoring-paused").path)
        if let size = try? root.appendingPathComponent("investigation-active.json").resourceValues(forKeys:[.fileSizeKey]).fileSize, size <= 4096,
           let bytes = try? Data(contentsOf:root.appendingPathComponent("investigation-active.json")),
           let active = try? JSONSerialization.jsonObject(with:bytes) as? [String:Any],
           let expiry = active["expires"] as? Double, let pid = active["pid"] as? Int32 {
            backgroundInvestigation = expiry > Date().timeIntervalSince1970 && expiry < Date().timeIntervalSince1970+185 && kill(pid,0) == 0
        } else { backgroundInvestigation = false }
        let reader = reader
        let syncRoot = syncRoot
        let peerCache = peerCache
        worker.async {
            var peerValue: DashboardSnapshot?
            var sync: [String:Any] = [:]
            if let data = try? Data(contentsOf:syncRoot.appendingPathComponent("status.json")),
               let value = try? JSONSerialization.jsonObject(with:data) as? [String:Any] { sync = value }
            peerValue = try? peerCache.update(root:syncRoot)
            let status = sync
            let cached = peerValue
            let result = Result { try reader.update() }; let count = reader.malformed
            DispatchQueue.main.async {
                self.busy = false; self.loading = false; self.malformed = count
                self.peer = cached
                let state = status["state"] as? String ?? "not_configured"
                let updated = status["updated_at"] as? Double ?? 0
                self.syncStatus = sharingStatus(state:state, updated:updated, lastExchange:status["last_sync_at"] as? Double, now:Date().timeIntervalSince1970)
                self.lastSync = status["last_sync_at"] as? Double
                self.localBytes = status["local_bytes"] as? Double
                self.syncBytes = status["sync_bytes"] as? Double
                if let at = status["resources_at"] as? Double, at <= self.now+5, self.now-at <= 180, let resources = status["resources"] as? [String:[String:Double]] {
                    self.resourceSummary = ["recorder","dashboard","sync"].compactMap { name in
                        guard let row = resources[name], let ram = row["rss_mib"] else { return nil }
                        return "\(name.capitalized): \(row["cpu_percent"].map{String(format:"%.2f%% CPU",$0)} ?? "CPU measuring") · \(String(format:"%.0f",ram)) MiB RAM"
                    }.joined(separator:"\n")
                } else {
                    self.resourceSummary = "Process measurements unavailable. Use Activity Monitor to inspect CPU and memory; recording works independently."
                }
                switch result {
                case .success(let value):
                    self.live = value; self.error = nil
                    if !self.initialScopeChosen {
                        self.initialScopeChosen = true
                        if self.hasMultipleObservers { self.scope = "Both Minis" }
                    }
                case .failure(let problem):
                    if self.paused { self.live = nil; self.error = nil } else { self.error = problem.localizedDescription }
                }
            }
        }
    }
    func revealEvidence() { NSWorkspace.shared.open(root) }
    func importSnapshot() {
        let panel = NSOpenPanel(); panel.title = "Open a saved evidence snapshot"; panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            let size = try url.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? 0
            guard size <= 50*1024*1024 else { throw NSError(domain:"NetworkMonitor", code:3,userInfo:[NSLocalizedDescriptionKey:"The snapshot is too large (maximum 50 MB)."])}
            let value = try JSONDecoder().decode(DashboardSnapshot.self, from: Data(contentsOf:url)); try value.validate()
            imported = value; useImported = true; message = "Imported \(value.state.host). This is a saved snapshot, not a live connection."
        } catch { message = "Could not import: \(error.localizedDescription)" }
    }
    func exportSnapshot() {
        guard let snapshot = snapshot else { return }
        let panel = NSSavePanel(); panel.title = "Export private monitoring evidence"; panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "\(snapshot.state.host)-network-evidence.json"
        panel.message = "Includes host names, local addresses, timings and your symptom notes. Share only with people you choose."
        guard panel.runModal() == .OK, let url = panel.url else { return }
        do {
            var value = snapshot; value.samples = samples; value.speeds = value.speeds.filter { $0.time >= start }; value.notes = displayedNotes
            let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]
            try encoder.encode(value).write(to:url, options:.atomic)
            try FileManager.default.setAttributes([.posixPermissions:0o600], ofItemAtPath:url.path)
            message = "Saved \(url.lastPathComponent). Keep it for later investigation or import it in Network Monitor to compare saved evidence."
        } catch { message = "Export failed: \(error.localizedDescription)" }
    }
    func addObservation(time: Date, service: String, others: String, note: String) {
        guard canRecordObservation, let host = live?.state.host else { return }
        let value = UserObservation(time:time.timeIntervalSince1970,recorded:Date().timeIntervalSince1970,host:host,service:service,othersWorked:others,note:String(note.prefix(2000)))
        worker.async {
            do {
                let fm = FileManager.default
                var files = try fm.contentsOfDirectory(at:self.root,includingPropertiesForKeys:[.fileSizeKey,.creationDateKey])
                    .filter { $0.lastPathComponent.hasPrefix("observations-") && $0.pathExtension == "jsonl" }.sorted { $0.lastPathComponent < $1.lastPathComponent }

                for file in files {
                    let created = try file.resourceValues(forKeys:[.creationDateKey]).creationDate ?? Date()
                    if Date().timeIntervalSince(created) > 180*86400 { try fm.removeItem(at:file) }
                }
                files = files.filter { fm.fileExists(atPath:$0.path) }
                var data = try JSONEncoder().encode(value); data.append(10)
                let lastSize = try files.last?.resourceValues(forKeys:[.fileSizeKey]).fileSize ?? 0
                let destination: URL
                if let last = files.last, lastSize + data.count < 1024*1024 { destination = last }
                else {
                    while files.count >= 4 { try fm.removeItem(at:files.removeFirst()) }
                    destination = self.root.appendingPathComponent("observations-\(Int(Date().timeIntervalSince1970*1000))-\(UUID().uuidString).jsonl")
                    fm.createFile(atPath:destination.path,contents:Data(),attributes:[.posixPermissions:0o600])
                }
                let handle = try FileHandle(forUpdating:destination); defer { try? handle.close() }
                let length = try handle.seekToEnd()
                if length > 0 {
                    try handle.seek(toOffset:length-1)
                    if try handle.read(upToCount:1) != Data([10]) {
                        try handle.seek(toOffset:0)
                        let existing = try handle.readToEnd() ?? Data()
                        try handle.truncate(atOffset:existing.lastIndex(of:10).map { UInt64($0+1) } ?? 0)
                    }
                }
                try handle.seekToEnd(); try handle.write(contentsOf:data); try handle.synchronize()
                DispatchQueue.main.async { self.message = "Observation saved. It will appear beside measured incidents without being treated as a probe failure."; self.refresh() }
            } catch { DispatchQueue.main.async { self.message = "Could not save observation: \(error.localizedDescription)" } }
        }
    }
    func manage(_ action: String) {
        guard !fixture, !useImported, !selectedPeer, !managing, !speedRunning else { return }
        let alert = NSAlert()
        alert.messageText = action == "clear-peer-cache" ? "Clear this Mac’s saved peer evidence?" : action == "pause" ? "Stop monitoring on this Mac?" : action == "resume" ? "Resume monitoring?" : "Permanently delete this Mac's active history?"
        alert.informativeText = action == "clear-peer-cache" ? "Removes only the local copy of the other Mini’s evidence. Source logs remain intact. Synchronization can download retained evidence again." : action == "pause" ? "Checks and scheduled speed tests will stop, including after login. Existing history stays available. Resume here when you are ready." : action == "resume" ? "Background checks and the existing speed-test schedule will resume." : "Deletes samples, incidents, speed results, symptom notes and service logs in the active evidence folder. This cannot be undone. Export first if needed. The active synchronization export is also removed. Configuration, peer caches, exported snapshots and archived backups are kept. The other Mac may retain a historical copy. Monitoring stays stopped."
        alert.alertStyle = action == "delete-history" ? .critical : .warning
        alert.addButton(withTitle:"Cancel"); alert.addButton(withTitle:action == "clear-peer-cache" ? "Clear peer cache" : action == "pause" ? "Stop monitoring" : action == "resume" ? "Resume" : "Delete history")
        guard alert.runModal() == .alertSecondButtonReturn else { return }
        managing = true
        worker.async {
            do {
                let home = FileManager.default.homeDirectoryForCurrentUser
                let plist = try Data(contentsOf:home.appendingPathComponent("Library/LaunchAgents/com.crispierry.network-monitor.plist"))
                let dict = try PropertyListSerialization.propertyList(from:plist,format:nil) as? [String:Any]
                guard let args = dict?["ProgramArguments"] as? [String], args.count > 2 else { throw NSError(domain:"Monitor",code:1,userInfo:[NSLocalizedDescriptionKey:"Recorder installation is missing."]) }
                let process = Process(); process.executableURL = URL(fileURLWithPath:args[1])
                process.arguments = [home.appendingPathComponent("Library/Application Support/NetworkMonitor/manage.py").path, action] + (["delete-history","clear-peer-cache"].contains(action) ? ["--confirm"] : [])
                let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
                try process.run(); let bytes = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
                let result = String(data:bytes,encoding:.utf8) ?? "Inspect service status."
                if process.terminationStatus == 0 && action == "clear-peer-cache" { self.peerCache.reset() }
                DispatchQueue.main.async {
                    if process.terminationStatus == 0 && action == "clear-peer-cache" { self.peer = nil }
                    self.managing = false
                    if process.terminationStatus == 0 && action == "delete-history" { self.live = nil; self.reader = EvidenceReader(root:self.root) }
                    self.message = result; self.refresh()
                }
            } catch { DispatchQueue.main.async { self.managing = false; self.message = error.localizedDescription } }
        }
    }
    func requestInvestigation(_ action: String) {
        guard ["capture","routes"].contains(action), isLocal, !paused, !managing, !investigationRunning, !speedRunning else { return }
        let alert = NSAlert()
        alert.messageText = action == "capture" ? "Capture a one-minute connection close-up?" : "Record a route investigation?"
        alert.informativeText = action == "capture" ? "Sends small pings to the main Orbi, Cloudflare and Google about once per second. It does not run a bandwidth test. Results are saved locally." : "Sends bounded route probes to Cloudflare and Google for up to one minute. Uses MTR when installed, otherwise repeated macOS traceroute. Intermediate-hop loss is not a diagnosis."
        alert.addButton(withTitle:"Start capture"); alert.addButton(withTitle:"Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        investigationRunning = true
        DispatchQueue.global(qos:.utility).async {
            let process = Process(); process.executableURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin/network-monitor")
            process.arguments = ["investigate", action]
            let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
            do {
                try process.run(); let bytes = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
                let text = String(data:bytes,encoding:.utf8) ?? "Inspect local evidence."
                DispatchQueue.main.async {
                    self.investigationRunning = false
                    self.message = process.terminationStatus == 0 ? "Investigation saved. Review the recorded episode on Performance." : String(text.prefix(1000))
                    self.refresh()
                }
            } catch { DispatchQueue.main.async { self.investigationRunning = false; self.message = error.localizedDescription } }
        }
    }
    func requestSpeed() {
        guard isLocal, !speedRunning, !paused, !managing else { return }
        let alert = NSAlert(); alert.messageText = "Measure download and upload speed?"
        alert.informativeText = "This can use several GB and temporarily slow other devices for up to 35 seconds. The recorder will skip it if health or the host's scheduled time window is unsuitable."
        alert.addButton(withTitle:"Run test"); alert.addButton(withTitle:"Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        speedRunning = true
        DispatchQueue.global(qos:.utility).async {
            let process = Process(); process.executableURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".local/bin/network-monitor")
            process.arguments = ["speed"]; let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
            do {
                try process.run(); let bytes = pipe.fileHandleForReading.readDataToEndOfFile(); process.waitUntilExit()
                let output = String(data:bytes,encoding:.utf8) ?? "Test completed; inspect performance history."
                DispatchQueue.main.async { self.speedRunning = false; self.message = output; self.refresh() }
            } catch { DispatchQueue.main.async { self.speedRunning = false; self.message = "Test could not start: \(error.localizedDescription)" } }
        }
    }
}


final class PeerEvidenceReader: @unchecked Sendable {
    private var reader: EvidenceReader?
    private var generation: String?
    func reset() { reader = nil; generation = nil }
    func update(root: URL) throws -> DashboardSnapshot? {
        let data = try Data(contentsOf:root.appendingPathComponent("peer/current.json"))
        guard let pointer = try JSONSerialization.jsonObject(with:data) as? [String:Any],
              let directory = pointer["directory"] as? String, ["slot-a","slot-b"].contains(directory) else { return nil }
        let path = root.appendingPathComponent("peer/"+directory)
        let next = pointer["generation"] as? String
        if reader == nil || generation != next { reader = EvidenceReader(root:path); generation = next }
        reader?.root = path
        return try reader?.update()
    }
}
