import SwiftUI
import Charts
import AppKit

func adaptiveColor(_ light: NSColor, _ dark: NSColor) -> Color {
    Color(nsColor:NSColor(name:nil) { appearance in
        appearance.bestMatch(from:[.darkAqua,.aqua]) == .darkAqua ? dark : light
    })
}
let ocean = adaptiveColor(NSColor(red:0.04,green:0.40,blue:0.46,alpha:1),NSColor(red:0.30,green:0.78,blue:0.83,alpha:1))
let mint = adaptiveColor(NSColor(red:0.06,green:0.43,blue:0.29,alpha:1),NSColor(red:0.35,green:0.82,blue:0.60,alpha:1))
let amber = adaptiveColor(NSColor(red:0.60,green:0.32,blue:0.02,alpha:1),NSColor(red:0.98,green:0.72,blue:0.31,alpha:1))
let coral = adaptiveColor(NSColor(red:0.72,green:0.15,blue:0.15,alpha:1),NSColor(red:1,green:0.49,blue:0.49,alpha:1))
func levelColor(_ level: Int) -> Color { level == 2 ? mint : level == 1 ? amber : level == 0 ? coral : .gray }
func levelText(_ level: Int) -> String { level == 2 ? "Passing" : level == 1 ? "Mixed results" : level == 0 ? "Failing" : "No evidence" }
func localTime(_ time: Double, seconds: Bool = false) -> String {
    let f = DateFormatter(); f.timeZone = TimeZone(identifier:"America/Los_Angeles"); f.dateFormat = seconds ? "MMM d, h:mm:ss a" : "MMM d, h:mm a"
    return f.string(from:Date(timeIntervalSince1970:time))
}
func elapsed(_ seconds: Double) -> String {
    guard seconds.isFinite else { return "unknown" }
    guard seconds >= 0 else { return "clock changed" }
    if seconds < 60 { return "\(Int(seconds)) sec" }
    if seconds < 3600 { return "\(Int(seconds/60)) min \(Int(seconds.truncatingRemainder(dividingBy:60))) sec" }
    return String(format:"%.1f hr", seconds/3600)
}
func throughput(_ value: Double?) -> (String,String) {
    guard let value = value, value.isFinite, value > 0 else { return ("—", "not measured") }
    return value >= 1000 ? (String(format:"%.2f",value/1000),"Gbps") : (String(format:"%.0f",value),"Mbps")
}
func metric(_ value: Double?, digits: Int = 1) -> String { value.map { String(format:"%.*f",digits,$0) } ?? "—" }


struct ComfortableDisclosureStyle: DisclosureGroupStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(alignment:.leading,spacing:0) {
            Button {
                withAnimation(.easeInOut(duration:0.16)) { configuration.isExpanded.toggle() }
            } label: {
                HStack(spacing:12) {
                    configuration.label
                    Spacer(minLength:8)
                    Image(systemName:configuration.isExpanded ? "chevron.up" : "chevron.down")
                        .font(.system(size:12,weight:.semibold)).foregroundStyle(.secondary)
                }
                .frame(maxWidth:.infinity,minHeight:44,alignment:.leading)
                .padding(.horizontal,12)
                .background(Color.primary.opacity(0.035),in:RoundedRectangle(cornerRadius:8))
                .contentShape(Rectangle())
            }.buttonStyle(.plain)
             .accessibilityValue(configuration.isExpanded ? "Expanded" : "Collapsed")
             .accessibilityHint("Show or hide details")
            if configuration.isExpanded { configuration.content.padding(.horizontal,12).padding(.bottom,8) }
        }
    }
}
var dashboardVersion: String {
    let info = Bundle.main.infoDictionary ?? [:]
    return "Version \(info["CFBundleShortVersionString"] as? String ?? "development") (\(info["CFBundleVersion"] as? String ?? "—"))"
}
func deviceIcon(_ id: String) -> String {
    switch id {
    case "mini_one", "mini_two": return "macmini"
    case "ring_doorbell": return "video.doorbell"
    case "ring_camera": return "web.camera"
    case "alexa": return "hifispeaker"
    case "google_home": return "homepodmini"
    default: return "network"
    }
}
func deviceCategory(_ id: String) -> String {
    switch id {
    case "mini_one": return "Wired Mac"
    case "mini_two": return "Wi-Fi Mac"
    case "ring_doorbell": return "Doorbell camera"
    case "ring_camera": return "Security camera"
    case "alexa": return "Alexa display"
    case "google_home": return "Google speaker · model unconfirmed"
    default: return "Network device"
    }
}

struct Panel<Content:View>: View {
    let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    var body: some View {
        VStack(alignment:.leading,spacing:0) { content }.padding(20).frame(maxWidth:.infinity,alignment:.leading)
            .background(Color(nsColor:.controlBackgroundColor),in:RoundedRectangle(cornerRadius:16))
            .overlay(RoundedRectangle(cornerRadius:16).stroke(Color.primary.opacity(0.07),lineWidth:1))
    }
}
struct SmallLabel: View {
    let text: String
    var body: some View { Text(text.uppercased()).font(.system(size:12,weight:.semibold,design:.rounded)).tracking(1.2).foregroundStyle(.secondary) }
}
struct StatCard: View {
    var title: String; var value: String; var unit: String; var detail: String; var icon: String; var tint: Color = ocean
    var body: some View {
        Panel {
            HStack { Text(title).font(.system(size:13,weight:.medium)); Spacer(); Image(systemName:icon).foregroundStyle(tint) }
            HStack(alignment:.firstTextBaseline,spacing:6) {
                Text(value).font(.system(size:31,weight:.semibold,design:.rounded)).monospacedDigit()
                Text(unit).font(.system(size:13)).foregroundStyle(.secondary)
            }.padding(.vertical,5)
            Text(detail).font(.system(size:13)).foregroundStyle(.secondary).lineLimit(2).frame(minHeight:36,alignment:.topLeading)
        }
    }
}

struct DashboardView: View {
    @ObservedObject var store: DashboardStore
    var body: some View {
        NavigationSplitView {
            ScrollView {
            VStack(alignment:.leading,spacing:16) {
                HStack(spacing:12) {
                    if let image = NSImage(named:"AppIcon") { Image(nsImage:image).resizable().frame(width:42,height:42) }
                    else { Image(systemName:"house.and.flag.fill").font(.largeTitle).foregroundStyle(ocean) }
                    VStack(alignment:.leading,spacing:2) { Text("Network").font(.system(size:18,weight:.bold)); Text("MONITOR").font(.system(size:12,weight:.semibold)).tracking(2.5).foregroundStyle(.secondary) }
                }.padding(.top,18)
                VStack(alignment:.leading,spacing:6) {
                    SmallLabel(text:"This home")
                    Text("Home network").font(.title3.weight(.semibold))
                    Text("AT&T fiber · Orbi mesh").font(.system(size:13)).foregroundStyle(.secondary)
                }
                VStack(spacing:6) {
                    nav("Overview", "chart.xyaxis.line")
                    nav("Performance", "waveform.path.ecg")
                    nav("Devices", "desktopcomputer")
                    nav("Incidents", "exclamationmark.bubble")
                    nav("Evidence", "doc.text.magnifyingglass")
                    nav("Monitoring & storage", "slider.horizontal.3")
                }
                Divider()
                VStack(alignment:.leading,spacing:10) {
                    SmallLabel(text:"Observation points")
                    if store.hasMultipleObservers {
                        Button { store.scope = "Both Minis"; store.useImported = false } label: {
                            hostRow(name:"Whole home",subtitle:"Compare observers",selected:store.wholeHome,image:"house")
                        }.buttonStyle(.plain)
                    }
                    Button { store.useImported = false; store.scope = "This Mini" } label: {
                        hostRow(name:store.live?.state.host ?? "This Mac", subtitle:store.fixture ? "Synthetic test evidence" : "Local recorder", selected:!store.useImported && store.scope == "This Mini", image:"desktopcomputer")
                    }.buttonStyle(.plain)
                    if let peerName = store.expectedPeer {
                        Button { store.useImported = false; store.scope = "Other Mini" } label: {
                            hostRow(name:peerName,subtitle:store.peerSubtitle,selected:store.selectedPeer,image:"desktopcomputer")
                        }.buttonStyle(.plain)
                    }
                    if let other = store.imported {
                        Button { store.useImported = true } label: { hostRow(name:other.state.host,subtitle:"Saved snapshot",selected:store.useImported,image:"doc.badge.clock") }.buttonStyle(.plain)
                    }
                    Button("Import snapshot…",systemImage:"square.and.arrow.down",action:store.importSnapshot).font(.system(size:13)).buttonStyle(.borderless)
                }
                Spacer()
                VStack(alignment:.leading,spacing:7) {
                    Label("Recording is independent",systemImage:"record.circle").font(.system(size:13).weight(.medium)).foregroundStyle(ocean)
                    Text("Use Monitoring & storage to stop recording.").font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                    Text("Times shown in Pacific time").font(.system(size:13)).foregroundStyle(.secondary)
                    Text(dashboardVersion).font(.system(size:11,weight:.medium,design:.monospaced)).foregroundStyle(.secondary).textSelection(.enabled).help("Installed dashboard version; also available in About Network Monitor")
                }
            }.padding(.horizontal,20).padding(.bottom,22).frame(maxHeight:.infinity)
            }.navigationSplitViewColumnWidth(min:210,ideal:230,max:250)
        } detail: {
            ScrollView {
                VStack(alignment:.leading,spacing:20) {
                    header
                    if store.fixture { Label("SYNTHETIC TEST EVIDENCE · not your live network",systemImage:"testtube.2").font(.headline).foregroundStyle(amber) }
                    if let error = store.error, !store.useImported {
                        Label("Cannot read current evidence: \(error)",systemImage:"exclamationmark.triangle.fill").foregroundStyle(coral).padding().frame(maxWidth:.infinity,alignment:.leading).background(coral.opacity(0.08),in:RoundedRectangle(cornerRadius:12))
                    }
                    if store.section == "Monitoring & storage" { MonitoringView(store:store) }
                    else if store.wholeHome { WholeHomeView(store:store) }
                    else if let snapshot = store.snapshot {
                        if store.selectedPeer { Label("Cached peer evidence · freshness is based on observation time",systemImage:"arrow.triangle.2.circlepath").font(.system(size:13)).foregroundStyle(.secondary) }
                        if store.paused && !store.useImported { Label("Monitoring stopped · showing saved history",systemImage:"pause.circle.fill").foregroundStyle(amber) }
                        if !store.isLive { Label("\(store.fixture ? "SYNTHETIC TEST EVIDENCE" : "SAVED SNAPSHOT") · captured \(localTime(snapshot.captured,seconds:true)). This view is not live.",systemImage:"clock.badge.exclamationmark").font(.callout.weight(.medium)).foregroundStyle(amber) }
                        if store.section == "Overview" { OverviewView(store:store,snapshot:snapshot) }
                        else if store.section == "Performance" { PerformanceView(store:store) }
                        else if store.section == "Incidents" { IncidentList(store:store) }
                        else if store.section == "Devices" { DevicesView(store:store, state:snapshot.state) }
                        else { EvidenceView(store:store,snapshot:snapshot) }
                    } else if store.selectedPeer {
                        Panel {
                            Label(store.expectedPeer ?? "Other computer",systemImage:"macmini").font(.title2)
                            Text(store.peerSubtitle).font(.headline).padding(.top,12)
                            Text("No synchronized evidence is available yet. Both computers record independently. Check sharing on both Macs in Monitoring & storage.").foregroundStyle(.secondary).padding(.top,8)
                            Button("Open sharing status") { store.section = "Monitoring & storage" }.padding(.top,12)
                        }
                    } else {
                        Panel {
                            if store.loading { ProgressView("Reading local monitoring evidence…").padding(30) }
                            else { Label("No recorded history",systemImage:"questionmark.folder").font(.title3); Text("Open Monitoring & storage to resume recording or manage this Mac. New results appear after the next sample.").foregroundStyle(.secondary).padding(.top,8); Button("Open evidence folder",action:store.revealEvidence).padding(.top,10) }
                        }
                    }
                }.padding(24).frame(maxWidth:1260).frame(maxWidth:.infinity)
            }.background(Color(nsColor:.windowBackgroundColor))
        }.navigationSplitViewStyle(.balanced)
        .padding(.top,8)
        .frame(minWidth:1000,minHeight:700)
        .tint(ocean)
        .controlSize(.large)
        .disclosureGroupStyle(ComfortableDisclosureStyle())
        .environment(\.timeZone,TimeZone(identifier:"America/Los_Angeles")!)
        .sheet(isPresented:$store.showObservation) { ObservationSheet(store:store) }
        .alert("Network Monitor",isPresented:Binding(get:{store.message != nil},set:{if !$0 {store.message=nil}})) { Button("OK") { store.message=nil } } message: { Text(store.message ?? "") }
    }
    func nav(_ title:String,_ icon:String) -> some View {
        Button { store.section=title } label: {
            HStack(spacing:10) { Image(systemName:icon).frame(width:18); Text(title).font(.system(size:13,weight:store.section == title ? .semibold:.regular)); Spacer() }
                .padding(.horizontal,12).padding(.vertical,11).foregroundStyle(store.section == title ? ocean : Color.primary)
                .frame(minHeight:24)
                .background(store.section == title ? ocean.opacity(0.12) : .clear,in:RoundedRectangle(cornerRadius:9))
                .contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityAddTraits(store.section == title ? .isSelected : []).help("Open \(title)")
    }
    func hostRow(name:String,subtitle:String,selected:Bool,image:String) -> some View {
        HStack(alignment:.top,spacing:8) { Image(systemName:image).foregroundStyle(selected ? ocean:.secondary); VStack(alignment:.leading,spacing:3) { Text(name).font(.system(size:12,weight:.semibold)); Text(subtitle).font(.system(size:13)).foregroundStyle(.secondary) }; Spacer(); if selected { Image(systemName:"checkmark.circle.fill").foregroundStyle(ocean).font(.system(size:13)) } }.padding(.vertical,8).frame(minHeight:44).contentShape(Rectangle())
    }
    var header: some View {
        HStack(alignment:.top) {
            VStack(alignment:.leading,spacing:7) {
                SmallLabel(text:"Home network / \(store.section)")
                Text(store.section == "Overview" ? "Network overview" : store.section).font(.system(size:25,weight:.semibold,design:.rounded))
                if store.wholeHome { Text(store.homeSnapshots.map { "\($0.state.host) · \($0.state.path)" }.joined(separator:"   +   ")).font(.callout).foregroundStyle(.secondary) }
                else if let state = store.snapshot?.state { Text("\(state.host)  ·  \(state.path)").font(.callout).foregroundStyle(.secondary) }
            }
            Spacer(minLength:16)
            VStack(alignment:.trailing,spacing:10) {
                if store.section != "Monitoring & storage" {
                Picker("History range",selection:$store.hours) { Text("1 hour").tag(1); Text("24 hours").tag(24); Text("7 days").tag(168) }.labelsHidden().pickerStyle(.segmented).frame(width:255).help("Choose how much recorded history to show")
                HStack(spacing:10) {
                    Button { store.refresh() } label: { Label("Refresh",systemImage:"arrow.clockwise") }.help("Read new evidence").keyboardShortcut("r",modifiers:.command)
                    Button("Report access problem",systemImage:"flag",action:{store.showObservation=true}).disabled(!store.canRecordObservation)
                }
                }
            }
        }
    }
}

struct OverviewView: View {
    @ObservedObject var store: DashboardStore
    let snapshot: DashboardSnapshot
    @State var compare = false
    var state: CurrentEvidence { snapshot.state }
    var body: some View {
        VStack(spacing:20) {
            HealthPanel(store:store,state:state)
            HStack {
                Label("\(state.devices?.count ?? 0) watched devices",systemImage:"house.fill").font(.callout.weight(.medium))
                Text("Local device reachability").font(.system(size:13)).foregroundStyle(.secondary)
                Spacer()
                Button("View devices") { store.section = "Devices" }.buttonStyle(.borderless)
            }
            metrics
            HStack {
                Text("Choppy meetings or brief slowdowns?").font(.callout)
                Spacer()
                Button("Inspect performance") { store.section = "Performance" }.buttonStyle(.borderless)
            }
            HStack(alignment:.top,spacing:18) {
                LatencyPanel(store:store,compare:$compare).frame(maxWidth:.infinity)
                SpeedPanel(store:store).frame(maxWidth:.infinity)
            }
            TimelinePanel(store:store)
            HStack(alignment:.top,spacing:18) {
                Panel {
                    HStack { Text("Recent incidents").font(.headline); Spacer(); Button("View all") { store.section="Incidents" }.buttonStyle(.borderless) }
                    if store.displayedIncidents.isEmpty {
                        Label("No confirmed incidents in this window",systemImage:"checkmark.circle").foregroundStyle(mint).padding(.top,15)
                        Text("Isolated failed probes remain visible in the timeline and raw evidence.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,5)
                    } else {
                        ForEach(store.displayedIncidents.prefix(3)) { incident in
                            HStack(alignment:.top) { Circle().fill(incident.commissioning ? Color.gray : incident.recovery == nil ? coral:amber).frame(width:8,height:8).padding(.top,5); VStack(alignment:.leading,spacing:4) { Text(incident.commissioning ? "Setup · local permission" : incident.recovery == nil ? "Incident still open" : "Recovered incident").font(.system(size:13,weight:.semibold)); Text("\(localTime(incident.start)) · \(incident.episodes.count) affected checks").font(.system(size:13)).foregroundStyle(.secondary) }; Spacer(); Text(elapsed((incident.recovery ?? store.reference)-incident.start)).font(.system(size:13)).monospacedDigit() }.padding(.top,12)
                        }
                    }
                }.frame(maxWidth:.infinity)
                Panel {
                    Label("Remote access is a separate question",systemImage:"person.crop.rectangle.badge.exclamationmark").font(.headline)
                    Text("Fresh internet requests from a Mini do not prove that Workbench or a Ring camera is reachable remotely.").font(.callout).foregroundStyle(.secondary).padding(.top,8)
                    Text("If access fails while other devices work, record the time and affected devices. Compare that report with this Mac’s evidence and, if available, another observer.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                    Button("Report a symptom",action:{store.showObservation=true}).disabled(!store.canRecordObservation).padding(.top,10)
                }.frame(maxWidth:.infinity)
            }
            if let peer = store.imported, !store.useImported {
                Panel {
                    HStack { Label("Compare both observation points",systemImage:"rectangle.connected.to.line.below").font(.headline); Spacer(); Toggle("Overlay saved peer latency",isOn:$compare).toggleStyle(.switch).controlSize(.small) }
                    Text("Live \(state.host) vs \(peer.state.host), captured \(localTime(peer.captured)). Only overlapping recorded times can be compared. Select the saved host in the sidebar for its incidents and path timeline.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                }
            }
        }
    }
    var metrics: some View {
        let pings = store.samples.reduce(0) { $0+$1.pingTotal }, failed = store.samples.reduce(0) { $0+$1.pingFailed }
        let recent = [state.checks.first{$0.id=="cloudflare_icmp"}?.latency,state.checks.first{$0.id=="google_icmp"}?.latency].compactMap{$0}
        let latency = recent.isEmpty ? nil : recent.reduce(0,+)/Double(recent.count)
        let speed = store.latestSpeed, down = throughput(speed?.down), up = throughput(speed?.up)
        return HStack(spacing:14) {
            StatCard(title:"Response time",value:metric(latency),unit:"ms",detail:"Mean of latest successful public pings",icon:"waveform.path")
            StatCard(title:"Ping loss",value:pings == 0 ? "—":String(format:"%.2f",100*Double(failed)/Double(pings)),unit:"%",detail:"\(failed) of \(pings) probes · missing time excluded",icon:"waveform.path.ecg",tint:failed > 0 ? amber:mint)
            StatCard(title:"Download",value:down.0,unit:down.1,detail:speed.map{"Last test · "+localTime($0.time)} ?? "No successful speed test yet",icon:"arrow.down",tint:ocean)
            StatCard(title:"Upload",value:up.0,unit:up.1,detail:speed.map{"Last test · "+localTime($0.time)} ?? "No successful speed test yet",icon:"arrow.up",tint:.indigo)
        }
    }
}

struct ObserverContextPanel: View {
    let host: String
    let context: HostContext?
    let now: Double
    var body: some View {
        Panel {
            Label("\(host) · computer context",systemImage:"cpu").font(.headline)
            if let c = context {
                Text("Observed \(localTime(c.at,seconds:true)) · \(c.interval.map { "averages over " + elapsed($0) } ?? "first reading")").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,6)
                if c.stale(at:now) { Label("Historical reading · current condition unknown",systemImage:"clock").foregroundStyle(amber).padding(.top,8) }
                HStack(alignment:.top,spacing:32) {
                    VStack(alignment:.leading) { Text(c.cpu.map { metric($0)+"%" } ?? "Unknown").font(.title2).monospacedDigit(); Text("CPU busy · all cores").font(.system(size:13)).foregroundStyle(.secondary) }
                    VStack(alignment:.leading) { Text(c.pressure.capitalized).font(.title2); Text("Memory pressure").font(.system(size:13)).foregroundStyle(.secondary) }
                    VStack(alignment:.leading) { Text(c.swap.map { metric($0)+" MiB" } ?? "Unknown").font(.title2).monospacedDigit(); Text("Swap used").font(.system(size:13)).foregroundStyle(.secondary) }
                }.padding(.top,16)
                ForEach(c.interfaces,id:\.self) { Text($0).font(.callout).monospacedDigit().padding(.top,6) }
                if c.interfaces.isEmpty { Text("Interface counters unavailable").foregroundStyle(.secondary).padding(.top,8) }
                if c.cpu == nil { Text("CPU reading: \(c.cpuStatus.replacingOccurrences(of:"_",with:" "))").font(.system(size:13)).foregroundStyle(.secondary) }
            } else { Text("No computer-context readings yet. This requires the updated recorder on this Mini.").foregroundStyle(.secondary).padding(.top,10) }
            Text("Traffic includes local and internet activity on this Mac; it is not available bandwidth. Averages can hide short spikes. These readings cannot rule out a problem on your meeting computer.").font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true).padding(.top,12)
        }
    }
}

struct LoadComparisonPanel: View {
    let samples: [SamplePoint]
    var interfaces: [String] { Array(Set(samples.map(\.interface))).sorted() }
    var body: some View {
        Panel {
            Label("Does a speed test coincide with slower responses?",systemImage:"arrow.up.arrow.down").font(.headline)
            Text("Cloudflare ping · selected history · successful replies only").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,6)
            Grid(alignment:.leading,horizontalSpacing:24,verticalSpacing:10) {
                GridRow { Text("Interface / period"); Text("Replies"); Text("Typical"); Text("95th percentile") }.font(.system(size:13).weight(.semibold)).foregroundStyle(.secondary)
                ForEach(interfaces,id:\.self) { name in
                    let rows = samples.filter { $0.interface == name }
                    comparisonRow(name+" · during this Mini’s tests",rows:rows,loaded:true)
                    comparisonRow(name+" · other samples",rows:rows,loaded:false)
                }
            }.padding(.top,16)
            if samples.isEmpty { Text("No samples in this period").foregroundStyle(.secondary).padding(.top,8) }
            Text("Milliseconds. Small reply counts are inconclusive. Other samples can include household traffic or the other Mini’s test; they are not an idle baseline. A difference suggests an association, not proof of bufferbloat. Missed probes remain visible in packet-loss views.").font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true).padding(.top,12)
        }
    }
    func comparisonRow(_ label: String, rows: [SamplePoint], loaded: Bool) -> some View {
        let value = loadLatency(rows,loaded:loaded)
        return GridRow { Text(label); Text("\(value.count)"); Text(metric(value.median)+" ms"); Text(metric(value.p95)+" ms") }.font(.callout).monospacedDigit()
    }
}

struct PerformanceView: View {
    @ObservedObject var store: DashboardStore
    @State var compare = false
    var recent: [SamplePoint] { store.samples.filter { $0.time >= store.reference-300 } }
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            Panel {
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:8) {
                        Text("How steady is this connection?").font(.title3.weight(.semibold))
                        Text("Last 5 minutes · \(store.snapshot?.state.host ?? "This Mac") · ending \(localTime(store.reference,seconds:true))").font(.system(size:13)).foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Report Zoom problem") { store.observationService = "Zoom / video meeting"; store.showObservation = true }.disabled(!store.canRecordObservation)
                }
                if store.currentStale || (store.paused && !store.useImported) || (!store.useImported && store.error != nil) {
                    Label("No fresh evidence · measurements below are historical",systemImage:"clock.badge.exclamationmark").foregroundStyle(amber).padding(.top,12)
                }
                let total = recent.reduce(0) { $0+$1.pingTotal }
                let missed = recent.reduce(0) { $0+$1.pingFailed }
                HStack(alignment:.firstTextBaseline,spacing:8) {
                    Text(total == 0 ? "—" : String(format:"%.1f%%",100*Double(missed)/Double(total))).font(.system(size:30,weight:.semibold,design:.rounded)).monospacedDigit()
                    Text("public ping loss · \(missed) of \(total) probes missed").font(.callout).foregroundStyle(.secondary)
                }.padding(.top,18)
                Text("Recorded coverage: \(elapsed(observedSeconds(samples:recent,start:store.reference-300,end:store.reference))) of 5 min. Missing time is unknown.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,4)
                Grid(alignment:.leading,horizontalSpacing:20,verticalSpacing:12) {
                    GridRow { Text("Path"); Text("Replies"); Text("Typical"); Text("95th percentile"); Text("Variation") }.font(.system(size:13).weight(.semibold)).foregroundStyle(.secondary)
                    pathRow("Main Orbi",key:\.orbi)
                    pathRow("Cloudflare",key:\.cloudflare)
                    pathRow("Google",key:\.google)
                }.padding(.top,20).frame(maxWidth:.infinity,alignment:.leading)
                Text("Milliseconds, successful pings only. Variation is the mean change between adjacent replies to the same target; gaps and failures break the calculation. It is not Zoom's packet jitter. Sparse 15-second checks can miss short bursts.").font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true).padding(.top,14)
                if recent.contains(where: { $0.loaded }) { Label("A speed test overlapped this window and may have affected latency.",systemImage:"arrow.up.arrow.down").font(.system(size:13)).foregroundStyle(amber).padding(.top,8) }
            }
            HStack(alignment:.top,spacing:18) {
                LatencyPanel(store:store,compare:$compare).frame(maxWidth:.infinity)
                SpeedPanel(store:store).frame(maxWidth:.infinity)
            }
            DisclosureGroup("Investigations and computer details") {
            ObserverContextPanel(host:store.snapshot?.state.host ?? "This Mac", context:store.snapshot?.state.diagnostics?.hostContext, now:store.reference)
            InvestigationPanel(store:store)
            LoadComparisonPanel(samples:store.samples.filter { $0.time >= store.start && $0.time <= store.reference })
            }.disclosureGroupStyle(ComfortableDisclosureStyle())
            Panel {
                Text("Separate the Mac, Wi-Fi and shared internet path").font(.headline)
                Text("Start with this Mac’s router, internet and computer measurements at the exact meeting time. A second observer is optional; its overlapping results can help separate local and shared problems.").font(.callout).foregroundStyle(.secondary).padding(.top,8)
                VStack(alignment:.leading,spacing:10) {
                    Text("Internet responses worsen while the router stays steady → investigate the upstream path or congestion.")
                    Text("Responses to the router also worsen → investigate this Mac, its local link or the router.")
                    if store.peer != nil || store.imported != nil {
                        Text("Compare fresh overlapping evidence from the other observer. Problems on only one path suggest a local issue; simultaneous failures suggest a shared path.")
                    }
                    Text("Network probes stay steady but Zoom struggles → inspect Zoom's actual connection and the meeting computer; this does not clear the network or prove a machine fault.")
                }.font(.callout).padding(.top,14)
                Text("These are hypotheses. Router ICMP handling, filtering and host scheduling can affect probes. A home network recorder cannot diagnose a meeting running on a different connection.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,14)
                HStack { Button("Import snapshot…",action:store.importSnapshot); if store.imported != nil && !store.useImported { Toggle("Overlay peer latency",isOn:$compare).toggleStyle(.switch).controlSize(.small) } }.padding(.top,12)
            }
            Panel {
                Text("During a poor Zoom meeting").font(.headline)
                Text("1. Report the problem here to mark its time on the charts. Include the meeting computer and location.").padding(.top,12)
                Text("2. Open Zoom → Settings → Statistics. Check Overall CPU/memory, then Audio and Video send/receive loss, latency and jitter.").padding(.top,8)
                Text("3. Compare that time with this Mac’s evidence. High CPU suggests local load; fresh results from an optional second observer can help identify a shared problem. Neither alone is a definitive diagnosis.").padding(.top,8)
                Text("Keep bandwidth tests for outside the meeting: they deliberately load the connection. Scheduled tests follow each observer’s configured hours. This app records CPU and memory pressure on each monitoring Mini, but not Zoom media statistics or the separate meeting computer.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,12)
                Link("Zoom's guide to meeting statistics",destination:URL(string:"https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0070504")!).font(.system(size:13)).padding(.top,10)
            }
        }
    }
    func pathRow(_ name: String, key: KeyPath<SamplePoint,Double?>) -> some View {
        let value = recentPathMetrics(recent,key:key,end:store.reference)
        return GridRow { Text(name).fontWeight(.medium); Text("\(value.replies)"); Text(metric(value.median)+" ms"); Text(metric(value.p95)+" ms"); Text(metric(value.variation)+" ms") }.font(.callout).monospacedDigit()
    }
}

struct HealthPanel: View {
    @ObservedObject var store: DashboardStore
    let state: CurrentEvidence
    var stale: Bool { (store.paused && !store.useImported) || store.currentStale || (!store.useImported && store.error != nil) }
    var title: String { store.paused && !store.useImported ? "Monitoring stopped" : stale ? "Monitoring needs attention" : state.internet == 2 ? "Internet reachable" : state.internet == 1 ? "Internet partially reachable" : state.internet == 0 ? "Internet checks failing" : "Internet status unknown" }
    var tint: Color { stale ? amber : levelColor(state.internet) }
    var description: String {
        if store.paused && !store.useImported { return "Saved results are shown below. Resume from Monitoring & storage to collect new evidence." }
        if stale { return "Current connectivity is unknown. Check the recorder, login/sleep state and evidence freshness." }
        if state.internet == 2 { return "Fresh HTTPS requests passed to Cloudflare and Google." }
        if state.internet == 1 { return "One independent HTTPS endpoint passed; compare provider and protocol results." }
        return "Both fresh HTTPS requests failed or are missing. Inspect the path timeline before attributing a cause."
    }
    var body: some View {
        Panel {
            HStack(alignment:.center,spacing:18) {
                Image(systemName:stale ? "clock.badge.exclamationmark" : state.internet == 2 ? "checkmark.shield.fill":"exclamationmark.shield.fill")
                    .font(.system(size:32)).foregroundStyle(tint).frame(width:64,height:64).background(tint.opacity(0.1),in:RoundedRectangle(cornerRadius:16))
                VStack(alignment:.leading,spacing:7) {
                    Text(title).font(.system(size:23,weight:.semibold,design:.rounded))
                    Text(description).font(.callout).foregroundStyle(.secondary)
                    HStack(spacing:12) {
                        Label("\(state.passing)/\(state.checks.count) checks passing",systemImage:state.passing==state.checks.count ? "checkmark.circle":"exclamationmark.circle").foregroundStyle(state.passing==state.checks.count ? mint:amber)
                        if state.openIncident != nil { Text("Incident open · awaiting confirmed recovery").foregroundStyle(amber) }
                    }.font(.system(size:13))
                }
                Spacer(minLength:12)
                VStack(alignment:.trailing,spacing:6) {
                    Label(store.paused && !store.useImported ? "STOPPED" : stale ? "STALE EVIDENCE" : store.isLive ? "RECORDER ACTIVE":"SAVED EVIDENCE",systemImage:stale ? "exclamationmark.triangle":"record.circle").font(.system(size:12,weight:.bold)).tracking(0.6).foregroundStyle(stale ? amber:mint)
                    Text("Sample \(elapsed(store.reference-state.completed)) ago").font(.system(size:13)).monospacedDigit()
                    Text("Checks every \(Int(state.interval)) sec").font(.system(size:13)).foregroundStyle(.secondary)
                    if state.speedActive { Label("Speed test load",systemImage:"speedometer").font(.system(size:13)).foregroundStyle(amber) }
                }
            }
        }
    }
}


struct ZoomableTimeChart<Marks: ChartContent>: View {
    let bounds: ClosedRange<Double>
    var emptyMessage: (ClosedRange<Double>)->String? = { _ in nil }
    let inspect: (Double, ClosedRange<Double>) -> String
    @ChartContentBuilder var marks: (ClosedRange<Double>) -> Marks
    @State private var focused: ClosedRange<Double>?
    @State private var selected: Double?
    var window: ClosedRange<Double> { focused.map { ChartWindow.fit($0,inside:bounds) } ?? bounds }
    var span: Double { window.upperBound-window.lowerBound }
    func change(_ next: ClosedRange<Double>) {
        focused = next.lowerBound <= bounds.lowerBound && next.upperBound >= bounds.upperBound ? nil : next
        selected=nil
    }
    func zoom(_ factor: Double) { change(ChartWindow.zoom(window,factor:factor,around:selected,inside:bounds)) }
    var body: some View {
        VStack(alignment:.leading,spacing:10) {
            ViewThatFits(in:.horizontal) {
                HStack(spacing:8) { navigation; Spacer(minLength:4); presets }
                VStack(alignment:.leading,spacing:8) { navigation; presets }
            }.padding(.top,12)
            Text("\(localTime(window.lowerBound,seconds:span <= 300)) – \(localTime(window.upperBound,seconds:span <= 300)) · Pacific\(focused == nil ? " · full range" : " · zoomed")")
                .font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
            Chart {
                marks(window)
                if let selected=selected, window.contains(selected) {
                    RuleMark(x:.value("Inspect time",Date(timeIntervalSince1970:selected))).foregroundStyle(.secondary.opacity(0.6))
                }
            }
            .chartXScale(domain:Date(timeIntervalSince1970:window.lowerBound)...Date(timeIntervalSince1970:window.upperBound))
            .chartYScale(domain:.automatic(includesZero:true))
            .chartXAxis { AxisMarks(values:.automatic(desiredCount:4)) { value in
                AxisGridLine(); AxisTick()
                AxisValueLabel {
                    if let date=value.as(Date.self) { Text(axisTime(date,seconds:span <= 300,days:span > 86400)) }
                }
            } }
            .chartYAxis { AxisMarks(position:.leading) }
            .chartOverlay { proxy in
                GeometryReader { geometry in
                    if let anchor=proxy.plotFrame {
                        let frame=geometry[anchor]
                        TimeChartGesture(proxy:proxy,width:frame.width,height:frame.height,
                            select:{ selected=$0 },focus:{ change(ChartWindow.fit($0,inside:bounds)) })
                            .frame(width:frame.width,height:frame.height).position(x:frame.midX,y:frame.midY)
                    }
                }
            }
            .frame(height:220)
            if let message=emptyMessage(window) { Label(message,systemImage:"chart.xyaxis.line").font(.system(size:13)).foregroundStyle(.secondary) }
            Text(selected.map{inspect($0,window)} ?? "Drag across a time range to zoom. Click to inspect; use the buttons to zoom or move through time.")
                .font(.system(size:13)).foregroundStyle(.secondary).frame(minHeight:34,alignment:.topLeading).fixedSize(horizontal:false,vertical:true)
        }
    }
    var navigation: some View {
        HStack(spacing:6) {
            navButton("Zoom in",icon:"plus.magnifyingglass",disabled:span <= ChartWindow.minimumSpan+0.1) { zoom(0.5) }
            navButton("Zoom out",icon:"minus.magnifyingglass",disabled:focused == nil) { zoom(2) }
            Divider().frame(height:20)
            navButton("Earlier",icon:"chevron.left",disabled:window.lowerBound <= bounds.lowerBound+0.1) { change(ChartWindow.move(window,direction:-1,inside:bounds)) }
            navButton("Later",icon:"chevron.right",disabled:window.upperBound >= bounds.upperBound-0.1) { change(ChartWindow.move(window,direction:1,inside:bounds)) }
            Button("Reset") { focused=nil; selected=nil }.disabled(focused == nil && selected == nil).help("Return to the full time range and follow new observations")
        }.controlSize(.large)
    }
    var presets: some View {
        Menu("Latest…") {
            ForEach([5,15,60],id:\.self) { minutes in
                Button("Last \(minutes == 60 ? "hour" : "\(minutes) minutes")") {
                    change(ChartWindow.fit((bounds.upperBound-Double(minutes)*60)...bounds.upperBound,inside:bounds))
                }
            }
        }.fixedSize().help("Jump to a recent interval; the selected interval then stays fixed")
    }
    func navButton(_ name:String,icon:String,disabled:Bool,action:@escaping ()->Void) -> some View {
        Button(action:action) { Image(systemName:icon).frame(minWidth:28,minHeight:26).contentShape(Rectangle()) }
            .disabled(disabled).help(name).accessibilityLabel(name)
    }
}
func axisTime(_ date:Date,seconds:Bool,days:Bool) -> String {
    let formatter=DateFormatter(); formatter.timeZone=TimeZone(identifier:"America/Los_Angeles")
    formatter.dateFormat=days ? "MMM d HH:mm" : seconds ? "HH:mm:ss" : "HH:mm"
    return formatter.string(from:date)
}
struct TimeChartGesture: View {
    let proxy: ChartProxy
    let width: CGFloat
    let height: CGFloat
    let select: (Double)->Void
    let focus: (ClosedRange<Double>)->Void
    @State private var dragStart: CGFloat?
    @State private var dragEnd: CGFloat?
    func time(_ x:CGFloat) -> Double? { proxy.value(atX:min(width,max(0,x)),as:Date.self)?.timeIntervalSince1970 }
    var body: some View {
        ZStack(alignment:.topLeading) {
            Color.clear
            if let start=dragStart, let end=dragEnd, abs(end-start)>8 {
                Rectangle().fill(ocean.opacity(0.18)).overlay(Rectangle().stroke(ocean,lineWidth:1))
                    .frame(width:abs(end-start),height:height).offset(x:min(start,end))
            }
        }.contentShape(Rectangle())
        .gesture(DragGesture(minimumDistance:0)
            .onChanged { event in
                dragStart=min(width,max(0,event.startLocation.x)); dragEnd=min(width,max(0,event.location.x))
            }
            .onEnded { event in
                defer { dragStart=nil; dragEnd=nil }
                guard let start=time(event.startLocation.x), let end=time(event.location.x) else { return }
                if abs(event.translation.width)>8 && abs(event.translation.width)>abs(event.translation.height) {
                    focus(min(start,end)...max(start,end))
                } else if abs(event.translation.width)<=8 && abs(event.translation.height)<=8 { select(end) }
            })
        .accessibilityLabel("Interactive chart. Drag horizontally to zoom, or click to inspect. Zoom and navigation buttons are above the chart.")
    }
}
func pingInspection(_ samples:[SamplePoint],time:Double,window:ClosedRange<Double>,name:String,cloudflareOnly:Bool=false) -> String {
    guard let s=inspectedSample(samples,at:time,window:window) else { return "\(name): no sample near this time" }
    let first=s.cloudflare.map{"\(metric($0)) ms"} ?? "no reply"
    let second=cloudflareOnly ? "" : " · Google \(s.google.map{"\(metric($0)) ms"} ?? "no reply")"
    return "\(name) · \(localTime(s.time,seconds:true)) · \(cloudflareOnly ? "" : "Cloudflare ")\(first)\(second)\(s.loaded ? " · speed-test load" : "")"
}

struct LatencyPanel: View {
    @ObservedObject var store: DashboardStore
    @Binding var compare: Bool
    func points(_ window:ClosedRange<Double>) -> [LatencyPoint] {
        var points=latencyPoints(samples:store.samples,window:window)
        if compare, !store.useImported, let peer=store.imported {
            points += latencyPoints(samples:peer.samples,window:window).map { var p=$0; p.series="\(peer.state.host) · \(p.series)"; return p }
        }
        return points
    }
    var body: some View {
        Panel {
            HStack { Text("Internet response time").font(.headline); Spacer(); Text("Lower is better").font(.system(size:13)).foregroundStyle(.secondary) }
            Text("Public ping latency · milliseconds · gaps are failed or missing checks").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,3)
            ZoomableTimeChart(bounds:store.chartStart...store.chartEnd,emptyMessage:{ points($0).isEmpty ? "No successful ping measurements in this interval" : nil },inspect:{ time,window in
                var detail=pingInspection(store.samples,time:time,window:window,name:store.snapshot?.state.host ?? "This Mini")
                if compare, !store.useImported, let peer=store.imported { detail += "\n"+pingInspection(peer.samples,time:time,window:window,name:peer.state.host) }
                return detail
            }) { window in
                ForEach(points(window)) { p in
                    LineMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Latency",p.value),series:.value("Continuous segment",p.group)).foregroundStyle(by:.value("Provider",p.series)).interpolationMethod(.linear)
                    if window.upperBound-window.lowerBound <= 900 {
                        PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Latency",p.value)).foregroundStyle(by:.value("Provider",p.series)).symbolSize(20)
                    }
                    if p.loaded { PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Latency",p.value)).symbol(.diamond).symbolSize(30).foregroundStyle(amber) }
                }
            }.chartForegroundStyleScale(range:[ocean,Color.indigo,Color.pink,Color.orange])
             .id("\(store.hours)-\(store.snapshot?.state.host ?? "")-\(store.useImported)-\(compare)")
            Text("◆ Speed-test load · Close views show original samples, normally 15 seconds apart. Zoom adds no measurements.").font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
        }
    }
}
func emptyChart(_ text:String) -> some View { VStack(spacing:10){ Image(systemName:"chart.xyaxis.line").font(.largeTitle).foregroundStyle(.tertiary); Text(text).font(.system(size:13)).foregroundStyle(.secondary).multilineTextAlignment(.center) }.frame(maxWidth:.infinity).frame(height:230) }

struct SpeedPanel: View {
    @ObservedObject var store: DashboardStore
    var speeds: [SpeedPoint] { store.snapshot?.speeds.filter { $0.time>=store.start && $0.time<=store.reference && $0.status=="success" } ?? [] }
    var body: some View {
        Panel {
            HStack { Text("Download & upload").font(.headline); Spacer(); Text("Mbps").font(.system(size:13)).foregroundStyle(.secondary) }
            Text("Individual speed tests · no estimate between tests").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,3)
            ZoomableTimeChart(bounds:store.chartStart...store.chartEnd,emptyMessage:{ window in speeds.contains{window.contains($0.time)} ? nil : "No successful speed tests in this interval" },inspect:{ time,window in
                guard let s=speeds.filter({window.contains($0.time)}).min(by:{abs($0.time-time)<abs($1.time-time)}) else { return "No successful speed tests in this interval" }
                return "Nearest test · \(localTime(s.time,seconds:true)) · ↓ \(metric(s.down)) / ↑ \(metric(s.up)) Mbps · idle \(metric(s.idle)) ms"
            }) { window in
                ForEach(speeds.filter{window.contains($0.time)}) { s in
                    if let value=s.down { PointMark(x:.value("Time",Date(timeIntervalSince1970:s.time)),y:.value("Mbps",value)).foregroundStyle(by:.value("Direction","Download")).symbol(by:.value("Direction","Download")).symbolSize(80) }
                    if let value=s.up { PointMark(x:.value("Time",Date(timeIntervalSince1970:s.time)),y:.value("Mbps",value)).foregroundStyle(by:.value("Direction","Upload")).symbol(by:.value("Direction","Upload")).symbolSize(80) }
                }
            }.chartForegroundStyleScale(["Download":ocean,"Upload":Color.indigo])
             .id("\(store.hours)-\(store.snapshot?.state.host ?? "")-\(store.useImported)")
            HStack { Text("Scheduled tests · independent measurements").font(.system(size:13)).foregroundStyle(.secondary); Spacer(); Button(store.speedRunning ? "Testing…":"Test speed…",action:store.requestSpeed).disabled(!store.isLocal || store.speedRunning || store.currentStale || store.paused || store.managing) }.frame(minHeight:36)
        }
    }
}

struct TimelinePanel: View {
    @ObservedObject var store: DashboardStore
    @State var selected: Date?
    var laneIndices: [Int] { configuredLaneIndices(store.snapshot?.state.checks ?? []) }
    var visibleLanes: [String] { laneIndices.map { laneNames[$0] } }
    var spans:[LaneSpan] { laneSpans(samples:store.samples,start:store.chartStart,end:store.chartEnd).filter { visibleLanes.contains($0.lane) } }
    var nearest: SamplePoint? { guard let selected=selected else{return nil}; return store.samples.first { $0.time<=selected.timeIntervalSince1970 && $0.time+$0.interval>selected.timeIntervalSince1970 } }
    var body: some View {
        Panel {
            HStack { Text("Where did the path break?").font(.headline); Spacer(); ForEach([-1,2,1,0],id:\.self) { status in HStack(spacing:4) { Circle().fill(levelColor(status)).frame(width:7,height:7); Text(levelText(status)).font(.system(size:13)).foregroundStyle(.secondary) } } }
            Text("Each lane answers a different question. Satellite and gateway checks measure management reachability.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,4)
            HStack(alignment:.top,spacing:16) {
                VStack(alignment:.leading,spacing:0) {
                    ForEach(visibleLanes,id:\.self) { Text($0).font(.system(size:13,weight:.medium)).frame(height:26,alignment:.center) }
                }.frame(width:135,alignment:.leading)
                VStack(spacing:6) {
                    GeometryReader { geometry in
                        Canvas { context,size in
                            let width=size.width, duration=store.chartEnd-store.chartStart
                            for span in spans {
                                let row=visibleLanes.firstIndex(of:span.lane) ?? 0
                                let x=(span.start-store.chartStart)/duration*width
                                let w=(span.end-span.start)/duration*width
                                let rect=CGRect(x:x,y:Double(row)*26+6,width:max(0.5,w),height:14)
                                context.fill(Path(rect),with:.color(levelColor(span.status).opacity(span.status == -1 ? 0.22:0.85)))
                            }
                            for note in store.displayedNotes {
                                let x=(note.time-store.chartStart)/duration*width
                                var path=Path(); path.move(to:CGPoint(x:x,y:0)); path.addLine(to:CGPoint(x:x,y:size.height))
                                context.stroke(path,with:.color(.purple),style:StrokeStyle(lineWidth:1,dash:[4,3]))
                            }
                            if let selected=selected {
                                let x=(selected.timeIntervalSince1970-store.chartStart)/duration*width
                                var path=Path(); path.move(to:CGPoint(x:x,y:0)); path.addLine(to:CGPoint(x:x,y:size.height))
                                context.stroke(path,with:.color(.primary.opacity(0.5)),lineWidth:1)
                            }
                        }.contentShape(Rectangle())
                        .gesture(DragGesture(minimumDistance:0).onChanged { value in
                            selected=Date(timeIntervalSince1970:store.chartStart+max(0,min(1,value.location.x/geometry.size.width))*(store.chartEnd-store.chartStart))
                        }).onContinuousHover { phase in
                            if case .active(let point)=phase { selected=Date(timeIntervalSince1970:store.chartStart+max(0,min(1,point.x/geometry.size.width))*(store.chartEnd-store.chartStart)) }
                        }.accessibilityLabel("Path timeline. Click, drag or hover to inspect a time; passing, mixed, failing, and unknown are listed below.")
                    }.frame(height:CGFloat(visibleLanes.count)*26)
                    HStack { Text(Date(timeIntervalSince1970:store.chartStart),format:.dateTime.hour().minute()); Spacer(); Text(Date(timeIntervalSince1970:(store.chartStart+store.chartEnd)/2),format:.dateTime.hour().minute()); Spacer(); Text(Date(timeIntervalSince1970:store.chartEnd),format:.dateTime.hour().minute()) }.font(.system(size:13)).foregroundStyle(.secondary)
                }
            }.padding(.top,16).padding(.bottom,12)
            if let selected=selected {
                Text(nearest.map { s in localTime(s.time,seconds:true)+" · "+laneIndices.map{"\(laneNames[$0]): \(levelText(s.lanes[$0]))"}.joined(separator:" · ") } ?? "\(localTime(selected.timeIntervalSince1970,seconds:true)) · No observation at this time. Do not infer success or failure.").font(.system(size:13)).foregroundStyle(.secondary)
            } else { Text("Click, drag or hover to inspect a moment. Purple dashed lines mark your reported symptoms; grey means no observation.").font(.system(size:13)).foregroundStyle(.secondary) }
            let observed=observedSeconds(samples:store.samples,start:store.start,end:store.reference)
            Text("Recorded coverage: \(elapsed(observed)) of the selected \(store.hours)-hour window. Charts begin at the first retained observation; earlier time has no evidence.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,5)
        }
    }
}

struct IncidentList: View {
    @ObservedObject var store: DashboardStore
    var body: some View {
        VStack(alignment:.leading,spacing:18) {
            Panel { Text("Events, evidence, and your observations").font(.headline); Text("Two consecutive failed checks confirm an incident; two good samples confirm recovery. Times are first observations, not exact physical transitions. A single failed probe is retained in the raw evidence.").font(.callout).foregroundStyle(.secondary).padding(.top,7) }
            if store.displayedIncidents.isEmpty { Panel { Label("No confirmed incidents in this window",systemImage:"checkmark.circle").foregroundStyle(mint) } }
            ForEach(store.displayedIncidents) { incident in IncidentCard(incident:incident,reference:store.reference) }
            Text("Reported access problems").font(.title3.weight(.semibold)).padding(.top,10)
            if store.displayedNotes.isEmpty { Panel { Text("No human observations in this window.").foregroundStyle(.secondary); Button("Report access problem",action:{store.showObservation=true}).disabled(!store.canRecordObservation).padding(.top,8) } }
            ForEach(store.displayedNotes) { note in Panel { HStack { Label(note.service,systemImage:"flag.fill").foregroundStyle(.purple).font(.headline); Spacer(); Text(localTime(note.time,seconds:true)).font(.system(size:13)).foregroundStyle(.secondary) }; Text("Other devices still worked: \(note.othersWorked)").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,7); if !note.note.isEmpty { Text(note.note).font(.callout).textSelection(.enabled).padding(.top,5) }; Text("User report · \(note.host) · entered \(localTime(note.recorded)) · not an automated diagnosis").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,7) } }
        }
    }
}
struct IncidentCard: View {
    let incident: IncidentEvidence
    let reference: Double
    var body: some View {
        Panel {
            HStack(alignment:.top) {
                VStack(alignment:.leading,spacing:7) {
                    Label(incident.commissioning ? "Setup incident · macOS Local Network permission" : incident.recovery == nil ? "Open incident" : "Recovered incident",systemImage:incident.commissioning ? "wrench.and.screwdriver":"exclamationmark.circle").font(.headline).foregroundStyle(incident.commissioning ? .secondary : incident.recovery == nil ? coral:amber)
                    Text("\(localTime(incident.start,seconds:true)) → \(incident.recovery.map{localTime($0,seconds:true)} ?? "not yet recovered")").font(.callout)
                }; Spacer(); Text(elapsed((incident.recovery ?? reference)-incident.start)).font(.title3.weight(.semibold)).monospacedDigit()
            }
            if incident.commissioning { Text("Recorded while granting the monitor permission during installation. Do not count this as an established router or internet outage.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,9) }
            if incident.uncertain { Label("Monitoring gap overlaps this incident; continuity and duration are uncertain.",systemImage:"clock.badge.exclamationmark").font(.system(size:13)).foregroundStyle(amber).padding(.top,9) }
            DisclosureGroup("\(incident.episodes.count) affected checks · inspect timing") {
                Grid(alignment:.leading,horizontalSpacing:20,verticalSpacing:9) {
                    GridRow { Text("Check").bold(); Text("First failed").bold(); Text("First recovered").bold() }.foregroundStyle(.secondary)
                    ForEach(incident.episodes) { e in GridRow { Text(friendlyCheck(e.check)); Text(localTime(e.start,seconds:true)); Text(e.recovery.map{localTime($0,seconds:true)} ?? "Not yet") } }
                }.font(.system(size:13)).frame(maxWidth:.infinity,alignment:.leading).padding(.top,12)
            }.padding(.top,12)
            ForEach(incident.hypotheses,id:\.self) { text in Text(text).font(.system(size:13)).foregroundStyle(.secondary).padding(.top,7) }
            Text("Evidence ID: \(incident.id)").font(.system(size:12,design:.monospaced)).foregroundStyle(.tertiary).textSelection(.enabled).padding(.top,8)
        }
    }
}

struct EvidenceView: View {
    @ObservedObject var store: DashboardStore
    let snapshot: DashboardSnapshot
    var body: some View {
        VStack(alignment:.leading,spacing:18) {
            Panel {
                HStack { Label("Evidence stays on each Mac",systemImage:"externaldrive.badge.checkmark").font(.headline); Spacer(); Button("Open local logs",action:store.revealEvidence); Button("Export snapshot…",action:store.exportSnapshot) }
                Text("\(store.root.path)").font(.system(size:12,design:.monospaced)).foregroundStyle(.secondary).textSelection(.enabled).padding(.top,9)
                Text("Raw samples: up to 30 days / 256 MiB. Incidents: up to 180 days / 16 MiB. Speed tests: up to 180 days / 8 MiB. Diagnostic context: up to 30 days / 32 MiB. Size limits may shorten history. Export important evidence before it expires.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                if store.malformed>0 { Label("\(store.malformed) unreadable records skipped. Inspect raw evidence before drawing conclusions.",systemImage:"exclamationmark.triangle").font(.system(size:13)).foregroundStyle(amber).padding(.top,8) }
            }
            HStack(alignment:.top,spacing:18) {
                Panel { Text("What this can establish").font(.headline); bullet("Whether this Mini can make fresh outbound HTTPS requests."); bullet("Whether DNS and local router/gateway/satellite management probes respond."); bullet("Which checks failed first, recovered, or lacked observations."); bullet("Measured download/upload and responsiveness under test load.") }
                Panel { Text("What still needs other evidence").font(.headline); bullet("Inbound Workbench access remotely and camera cloud availability."); bullet("A satellite's actual radio/backhaul health and outage-time client attachments."); bullet("Router internal faults and the exact cause of a loss; counters and route traces help narrow the path."); bullet("Intervals when this Mac is asleep, logged out or without power.") }
            }
            Panel {
                Label("Ready for the next interruption",systemImage:"waveform.path.ecg").font(.headline)
                if let context = snapshot.state.diagnostics {
                    Text("Last diagnostic snapshot: \(localTime(context.completed,seconds:true)) · \(context.availablePages)/4 gateway pages captured").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                    if context.stale(at:store.reference) { Label("Diagnostic evidence is stale",systemImage:"clock.badge.exclamationmark").foregroundStyle(amber).padding(.top,6) }
                    ForEach(context.details,id:\.self) { detail in Text(detail).font(.callout).padding(.top,4) }
                } else {
                    Text("No diagnostic snapshot yet. Allow up to two minutes after the recorder starts.").foregroundStyle(.secondary).padding(.top,8)
                }
                Text("Captures gateway/fiber counters and Mac link state every minute and after probe changes. Bounded route traces help compare the healthy and failing paths. No router login or settings changes.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,10)
                Text("The export includes this summary. Full timestamped context is in diagnostics-*.jsonl in the local logs folder.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,6)
            }
            Panel {
                Text("Current probe evidence").font(.headline)
                Text("\(localTime(snapshot.state.completed,seconds:true)) · \(snapshot.state.path) · \(store.isLive ? "local recorder":"saved snapshot")").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,5)
                Grid(alignment:.leading,horizontalSpacing:18,verticalSpacing:9) {
                    GridRow { Text("Check"); Text("Result"); Text("Latency"); Text("Target"); Text("Evidence") }.fontWeight(.semibold).foregroundStyle(.secondary)
                    ForEach(snapshot.state.checks) { check in GridRow {
                        Text(check.name).frame(minWidth:160,alignment:.leading)
                        Label(check.ok ? "Pass":"Fail",systemImage:check.ok ? "checkmark.circle.fill":"xmark.circle.fill").foregroundStyle(check.ok ? mint:coral)
                        Text(check.latency.map{"\(metric($0)) ms"} ?? "—").monospacedDigit()
                        Text(check.target).font(.system(size:11,design:.monospaced))
                        Text(check.detail).font(.system(size:12,design:.monospaced)).foregroundStyle(.secondary).lineLimit(2)
                    } }
                }.font(.system(size:13)).padding(.top,16).textSelection(.enabled)
            }
            Panel {
                Text("Performance measurements").font(.headline)
                Text("RPM measures responsiveness under load; higher is better. It is not milliseconds. Skipped/incomplete tests are kept as evidence and never plotted as zero speed.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,7)
                ForEach((snapshot.speeds.filter{$0.time>=store.start}).reversed().prefix(20)) { s in
                    VStack(alignment:.leading,spacing:4) {
                        HStack { Text(localTime(s.time)).fontWeight(.medium); Text(s.status.capitalized).foregroundStyle(s.status=="success" ? mint:amber); Spacer(); Text("↓ \(metric(s.down))  ↑ \(metric(s.up)) Mbps").monospacedDigit() }
                        Text("Idle \(metric(s.idle)) ms · loaded download \(metric(s.downRPM, digits:0)) / upload \(metric(s.upRPM,digits:0)) RPM · \(s.interface)\(s.reason.map{" · "+$0} ?? "")").foregroundStyle(.secondary)
                    }.font(.system(size:13)).padding(.top,10)
                }
            }
            Panel { Text("Read the attachment map carefully").font(.headline); Text("Device attachment labels come from your dated manual inventory. Check the router’s device list when you need a current association. The monitor cannot continuously confirm which access point a device uses.").font(.callout).foregroundStyle(.secondary).padding(.top,8); if let signal=snapshot.state.wifiSignal { Text("Last Wi-Fi signal/noise: \(signal) · \(snapshot.state.wifiChannel ?? "channel unavailable") · \(snapshot.state.wifiAt.map{localTime($0)} ?? "time unavailable")").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8) } }
        }
    }
    func bullet(_ text:String) -> some View { HStack(alignment:.top,spacing:8) { Text("•").foregroundStyle(ocean); Text(text) }.font(.callout).foregroundStyle(.secondary).padding(.top,8) }
}

struct ObservationSheet: View {
    @ObservedObject var store: DashboardStore
    @Environment(\.dismiss) var dismiss
    @State var time=Date()
    @State var service="Workbench / remote access"
    @State var others="Unknown"
    @State var note=""
    init(store: DashboardStore) {
        self.store = store
        _service = State(initialValue:store.observationService)
    }
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            Text("Report a connection problem").font(.title2.weight(.semibold))
            Text("Save what you experienced alongside the measurements. This records a human observation, not a confirmed diagnosis.").font(.callout).foregroundStyle(.secondary)
            DatePicker("When did it happen?",selection:$time,in:...Date(),displayedComponents:[.date,.hourAndMinute])
            Picker("What was affected?",selection:$service) { ForEach(["Workbench / remote access","Zoom / video meeting","Ring doorbell","Garage camera","Several devices","Other"],id:\.self){Text($0)} }
            Picker("Other devices still worked?",selection:$others) { ForEach(["Unknown","Yes","No"],id:\.self){Text($0)} }
            Text(service == "Zoom / video meeting" ? "Which computer and location? Audio, video or screen sharing? Note Zoom's CPU, send/receive loss, latency and jitter if available. No meeting IDs or participant names needed." : "What stopped working? What still worked? Did it recover?").font(.system(size:13)).foregroundStyle(.secondary)
            TextEditor(text:$note).font(.body).frame(height:105).padding(6).overlay(RoundedRectangle(cornerRadius:8).stroke(Color.secondary.opacity(0.3)))
            Text("Keep passwords and account details out of these notes. Maximum 2,000 characters.").font(.system(size:13)).foregroundStyle(.secondary)
            HStack { Spacer(); Button("Cancel"){dismiss()}.keyboardShortcut(.cancelAction); Button("Save observation") { store.addObservation(time:time,service:service,others:others,note:note); dismiss(); store.section="Incidents" }.buttonStyle(.borderedProminent).keyboardShortcut(.defaultAction) }
        }.padding(28).frame(width:580).controlSize(.large)
    }
}

struct MonitoringView: View {
    @ObservedObject var store: DashboardStore
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            Panel {
                Label(store.paused ? "Monitoring is stopped" : "Background monitoring",systemImage:store.paused ? "pause.circle" : "record.circle").font(.title3.weight(.semibold))
                Text("These controls apply only to this Mac. Closing the app leaves the recorder running. Stopping here also prevents it restarting at the next login.").foregroundStyle(.secondary).padding(.top,8)
                HStack {
                    Button("Stop monitoring…") { store.manage("pause") }.disabled(store.paused)
                    Button("Resume monitoring…") { store.manage("resume") }.disabled(!store.paused)
                    if store.managing { ProgressView().controlSize(.small) }
                }.padding(.top,16)
            }
            Panel {
                Text("Recorded history").font(.title3.weight(.semibold))
                Text("Export an evidence snapshot before removing history you may need to investigate an outage.").foregroundStyle(.secondary).padding(.top,8)
                HStack { Button("Export snapshot…",action:store.exportSnapshot).disabled(store.snapshot == nil); Button("Open local logs",action:store.revealEvidence) }.padding(.top,12)
                Divider().padding(.vertical,16)
                Text("Delete active history").font(.headline)
                Text("Removes samples, incidents, diagnostic snapshots, speed results, symptom notes and service logs. Keeps the app, configuration, peer caches, user exports and archived backups. Removes this Mac’s active synchronization export. The other Mac may retain a historical copy. Stop monitoring first. Deletion is permanent and monitoring stays stopped.").font(.callout).foregroundStyle(.secondary).padding(.top,8)
                Button("Delete history…",role:.destructive) { store.manage("delete-history") }.disabled(!store.paused).padding(.top,14)
            }
            Panel {
                Text("Resources on this Mac").font(.headline)
                Text(store.resourceSummary).font(.callout).padding(.top,8)
                Text("CPU is a recent sample; 100% means one core. RAM is resident memory. Speed tests can temporarily increase load.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,6)
                Text("Local evidence: \(store.localBytes.map { metric($0/1048576)+" MiB" } ?? "not measured") · synchronization: \(store.syncBytes.map { metric($0/1048576)+" MiB" } ?? "not measured")").padding(.top,8)
                Text("Local journals: 324 MiB maximum plus state. Compact exports: 16 MiB. Peer cache: at most 64 MiB, including transfer staging and one prior generation. Size limits can shorten retained history. Exported archives and Trash are separate.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                if store.hasMultipleObservers || store.syncStatus != "Not configured" {
                    Text("Optional sharing: \(store.syncStatus)").font(.callout).padding(.top,8)
                }
                if store.peer != nil {
                    Button("Clear peer cache…") { store.manage("clear-peer-cache") }.padding(.top,10)
                }
            }
            Text("Monitoring runs independently on this Mac. After resuming, allow up to 60 seconds for fresh results.").font(.system(size:13)).foregroundStyle(.secondary)
        }.disabled(store.fixture || store.useImported || store.selectedPeer || store.managing || store.speedRunning)
    }
}

struct DevicesView: View {
    @ObservedObject var store: DashboardStore
    let state: CurrentEvidence
    var body: some View {
        VStack(alignment:.leading, spacing:20) {
            Panel {
                Text("Can we reach the devices that matter?").font(.title3.weight(.semibold))
                Text("One light check per minute from \(state.host). A reply proves local reachability; it does not prove video, voice commands or cloud access work.")
                    .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true).padding(.top,8)
                ForEach(state.devices ?? []) { device in
                    Divider().padding(.vertical,14)
                    deviceRow(device)
                }
                if (state.devices ?? []).isEmpty {
                    Text("No device observations yet. Allow up to 90 seconds after updating the recorder.").foregroundStyle(.secondary).padding(.top,20)
                }
            }
            Panel {
                Text("Recent device changes").font(.headline)
                Text("Two missed replies confirm a loss of replies only after a reply baseline. Recovery also needs two replies. Identity can remain unverified when macOS hides neighbor information.")
                    .font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true).padding(.top,6)
                let events = (state.deviceEvents ?? []).filter { $0.time >= store.start && $0.time <= store.reference }.reversed()
                if events.isEmpty { Text("No confirmed changes in this period.").foregroundStyle(.secondary).padding(.top,16) }
                ForEach(Array(events.prefix(20))) { event in
                    Divider().padding(.vertical,10)
                    HStack(alignment:.top) {
                        Image(systemName:event.kind == "device_recovered" ? "checkmark.circle" : "exclamationmark.circle").foregroundStyle(event.kind == "device_recovered" ? mint : amber)
                        VStack(alignment:.leading,spacing:4) {
                            Text("\(event.name) · \(event.kind == "device_recovered" ? "Replies resumed" : "Stopped replying")").font(.callout.weight(.medium))
                            Text("First observed \(localTime(event.onset,seconds:true)) · confirmed \(localTime(event.time,seconds:true))").font(.system(size:13)).foregroundStyle(.secondary)
                            if event.uncertain { Text("Observation gap: continuity is uncertain.").font(.system(size:13)).foregroundStyle(amber) }
                        }
                        Spacer()
                    }
                }
            }
            Panel {
                HStack(alignment:.top) {
                    VStack(alignment:.leading,spacing:8) {
                        Text("Ask Dots about your network").font(.headline)
                        Text("On this Mac: “Read Network Monitor’s local briefing. Which devices need attention, and what happened in the last 24 hours?”").font(.callout).textSelection(.enabled)
                        Text("The command reads local evidence and returns timestamped JSON. No server or router login. Dots needs local command access. No other computer is required.")
                            .font(.system(size:13)).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true)
                    }
                    Spacer()
                    Button("Copy query command") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString("~/.local/bin/network-monitor query --hours 24",forType:.string)
                    }.disabled(!store.isLive)
                }
            }
        }
    }
    func deviceRow(_ device: DeviceEvidence) -> some View {
        let stale = store.currentStale || (!store.useImported && store.paused) || device.stale(at:store.reference)
        let status = stale ? "stale" : device.status
        let labels = ["responding":"Reply received", "address_reply":"Address replies", "recovering":"Recovering", "unreachable":"No reply", "checking":"Checking", "unknown":"Not yet verified", "address_changed":"Check address", "stale":"No fresh evidence"]
        let tint: Color = status == "responding" ? mint : ["checking","recovering","unreachable","address_changed"].contains(status) ? amber : .secondary
        return DisclosureGroup {
            VStack(alignment:.leading,spacing:8) {
                Text(device.lastReply.map { "Last reply · \(localTime($0,seconds:true))" } ?? "No reply recorded yet")
                if !stale && device.identity == "unverified" { Text("Device identity unverified · monitoring the recorded IP address") }
                Text("Last recorded attachment: \(device.attachment) · inventory \(device.inventoryAt). Not a live association.")
                Text("Address identity: \(device.identity). ARP cache entries alone never count as a reply.")
                Text(device.note)
                Text("No reply can mean sleep, filtering, an address change or a connection problem. Device speed and cloud health are not measured here.")
            }.font(.callout).foregroundStyle(.secondary).frame(maxWidth:.infinity,alignment:.leading).padding(.top,12).textSelection(.enabled)
        } label: {
            HStack(alignment:.center,spacing:14) {
                Image(systemName:deviceIcon(device.id)).font(.system(size:24)).foregroundStyle(ocean)
                    .frame(width:48,height:48).background(ocean.opacity(0.10),in:RoundedRectangle(cornerRadius:12)).accessibilityHidden(true)
                VStack(alignment:.leading,spacing:5) {
                    Text(device.name).font(.system(size:15,weight:.semibold))
                    Text(deviceCategory(device.id)).font(.system(size:13)).foregroundStyle(.secondary)
                    Text(device.isLocal ? "This Mac · self-check" : device.address).font(.system(size:13)).foregroundStyle(.secondary)
                }.frame(maxWidth:.infinity,alignment:.leading)
                VStack(alignment:.trailing,spacing:5) {
                    Label(labels[status] ?? "Unknown",systemImage:status == "responding" || status == "address_reply" ? "checkmark.circle" : status == "unreachable" ? "exclamationmark.circle" : "questionmark.circle").foregroundStyle(tint).font(.callout.weight(.medium))
                    Text(!stale && device.latency != nil ? "\(metric(device.latency)) ms · \(elapsed(store.reference-device.observed)) ago" : "Sampled \(localTime(device.observed))")
                        .font(.system(size:13)).foregroundStyle(.secondary)
                    Text("Connection & evidence").font(.system(size:13)).foregroundStyle(ocean)
                }
            }.padding(.vertical,8)
        }
    }
}


struct WholeHomeView: View {
    @ObservedObject var store: DashboardStore
    var hosts: [String] { Array(Set(store.homeSnapshots.map { $0.state.host } + (store.expectedPeer.map { [$0] } ?? []))).sorted() }
    func snapshot(_ host: String) -> DashboardSnapshot? { store.homeSnapshots.first { $0.state.host == host } }
    func stale(_ s: DashboardSnapshot) -> Bool { s.state.stale(at:store.now) || (s.state.host == store.live?.state.host && store.paused) }
    var body: some View {
        VStack(alignment:.leading,spacing:20) {
            HStack(alignment:.top,spacing:18) {
                ForEach(hosts,id:\.self) { host in
                    Panel {
                        HStack { Label(host,systemImage:"macmini").font(.title3.weight(.semibold)); Spacer(); if let localHost = store.live?.state.host, snapshot(host)?.state.host == localHost { Text("This Mac").font(.system(size:13)).foregroundStyle(.secondary) } }
                        Text(snapshot(host)?.state.path ?? "Path unavailable").foregroundStyle(.secondary).padding(.top,5)
                        if let s = snapshot(host) {
                            let old = stale(s)
                            Label(old ? "Current health unknown" : s.state.internet == 2 ? "Internet reachable" : s.state.internet == 0 ? "Internet checks failing" : "Mixed or incomplete results",systemImage:old ? "clock.badge.exclamationmark" : s.state.internet == 2 ? "checkmark.circle.fill" : "exclamationmark.triangle.fill")
                                .font(.headline).foregroundStyle(old ? .gray : levelColor(s.state.internet)).padding(.top,16)
                            Text("Observed \(localTime(s.state.completed,seconds:true))").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                            Text("\(elapsed(store.now-s.state.completed)) ago · \(s.state.passing)/\(s.state.checks.count) checks passed in that sample").font(.system(size:13)).foregroundStyle(.secondary)
                        } else {
                            Label("Not connected · no evidence yet",systemImage:"wifi.slash").foregroundStyle(.secondary).padding(.top,16)
                            Text("Sharing: \(store.syncStatus). Check the recorder on this Mac directly; its current health is unknown here.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,8)
                        }
                    }
                }
            }
            HStack {
                Label(store.syncStatus,systemImage:"arrow.triangle.2.circlepath").font(.callout)
                if let time = store.lastSync { Text("Last exchange \(elapsed(store.now-time)) ago").font(.system(size:13)).foregroundStyle(.secondary) }
                Spacer()
                Text("Observations keep their original timestamps").font(.system(size:13)).foregroundStyle(.secondary)
            }
            if store.section == "Devices" { devices }
            else if store.section == "Incidents" { incidents }
            else if store.section == "Evidence" {
                Panel {
                    Text("Two independent sources").font(.headline)
                    Text("The app reads local evidence and a validated peer cache. Raw diagnostic journals remain on the Mac that collected them. A failed synchronization is not proof of an internet outage.").foregroundStyle(.secondary).padding(.top,8)
                    Button("Copy whole-home query") { NSPasteboard.general.clearContents(); NSPasteboard.general.setString("~/.local/bin/network-monitor query --all-hosts --hours 24",forType:.string) }.padding(.top,12)
                    Text("Choose a Mini in the sidebar to inspect its detailed evidence. Controls apply only to this Mac.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,10)
                }
            } else {
                if store.section == "Performance" {
                    InvestigationPanel(store:store)
                    ForEach(hosts,id:\.self) { host in
                        ObserverContextPanel(host:host,context:snapshot(host)?.state.diagnostics?.hostContext,now:store.now)
                    }
                }
                latency
                loss
                speeds
                incidents
            }
        }
    }
    var latency: some View {
        Panel {
            Text("Response time · observer comparison").font(.headline)
            Text("Cloudflare ping · milliseconds · gaps are missing or failed observations").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,5)
            ZoomableTimeChart(bounds:store.start...store.now,emptyMessage:{ window in store.homeSnapshots.contains { s in s.samples.contains{window.contains($0.time) && $0.cloudflare != nil} } ? nil : "No successful ping measurements in this interval" },inspect:{ time,window in
                hosts.map { host in snapshot(host).map{pingInspection($0.samples,time:time,window:window,name:host,cloudflareOnly:true)} ?? "\(host): no evidence" }.joined(separator:"\n")
            }) { window in
                ForEach(hosts,id:\.self) { host in
                    if let s=snapshot(host) {
                        ForEach(latencyPoints(samples:s.samples,window:window).filter{$0.series == "Cloudflare"}) { p in
                            LineMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Milliseconds",p.value),series:.value("Segment",host+String(p.segment))).foregroundStyle(by:.value("Observer",host))
                            if window.upperBound-window.lowerBound <= 900 { PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Milliseconds",p.value)).foregroundStyle(by:.value("Observer",host)).symbolSize(24) }
                            if p.loaded { PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Milliseconds",p.value)).symbol(.diamond).symbolSize(30).foregroundStyle(amber) }
                        }
                    }
                }
            }.chartForegroundStyleScale(domain:hosts,range:[ocean,Color.purple]).id(store.hours)
            Text("◆ Speed-test load · Close views show original samples, normally 15 seconds apart. Zoom adds no measurements.").font(.system(size:13)).foregroundStyle(.secondary)
        }
    }
    var loss: some View {
        Panel {
            Text("Sampled packet loss and coverage").font(.headline)
            Text("Public ping observations in the selected period. Missing recording time is not counted as packet loss.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,6)
            ForEach(hosts,id:\.self) { host in
                if let s = snapshot(host) {
                    let samples = s.samples.filter{$0.time >= store.start && $0.time <= store.now}
                    let attempts = samples.reduce(0){$0+$1.pingTotal}
                    let missed = samples.reduce(0){$0+$1.pingFailed}
                    HStack {
                        Text(host).frame(width:100,alignment:.leading)
                        Text(attempts > 0 ? String(format:"%.2f%% lost",Double(missed)/Double(attempts)*100) : "No probes")
                        Spacer()
                        Text("\(missed)/\(attempts) missed · \(elapsed(observedSeconds(samples:samples,start:store.start,end:store.now))) observed").font(.system(size:13)).foregroundStyle(.secondary)
                    }.padding(.top,12)
                }
            }
        }
    }
    var speeds: some View {
        Panel {
            Text("Download and upload · separate measurements").font(.headline)
            Text("Mbps · separate tests at their recorded times").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,5)
            ZoomableTimeChart(bounds:store.start...store.now,emptyMessage:{ window in store.homeSnapshots.contains { s in s.speeds.contains{window.contains($0.time) && $0.status == "success"} } ? nil : "No successful speed tests in this interval" },inspect:{ time,window in
                hosts.map { host in
                    guard let s=snapshot(host)?.speeds.filter({window.contains($0.time) && $0.status == "success"}).min(by:{abs($0.time-time)<abs($1.time-time)}) else { return "\(host): no successful test in this interval" }
                    return "\(host) · nearest test \(localTime(s.time,seconds:true)) · ↓ \(metric(s.down)) / ↑ \(metric(s.up)) Mbps"
                }.joined(separator:"\n")
            }) { window in
                ForEach(hosts,id:\.self) { host in
                    if let s = snapshot(host) {
                        ForEach(s.speeds.filter{window.contains($0.time) && $0.status == "success"}) { p in
                            if let down=p.down { PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Mbps",down)).foregroundStyle(by:.value("Observer",host)).symbol(by:.value("Direction","Download")).symbolSize(60) }
                            if let up=p.up { PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Mbps",up)).foregroundStyle(by:.value("Observer",host)).symbol(by:.value("Direction","Upload")).symbolSize(60) }
                        }
                    }
                }
            }.chartForegroundStyleScale(domain:hosts,range:[ocean,Color.purple]).id(store.hours)
        }
    }
    var incidents: some View {
        Panel {
            Text("Incidents by observation point").font(.headline)
            Text("Compare overlapping times. One observer failing narrows the path; it does not identify a faulty router or satellite.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,6)
            ForEach(hosts,id:\.self) { host in
                Divider().padding(.vertical,12)
                Text(host).font(.headline)
                if let s = snapshot(host) {
                    let rows = s.state.incidents.filter{($0.recovery ?? store.now) >= store.start && $0.start <= store.now}
                    if rows.isEmpty { Text("No confirmed incidents in retained evidence for this period.").font(.callout).foregroundStyle(.secondary).padding(.top,6) }
                    ForEach(rows) { incident in
                        DisclosureGroup {
                            ForEach(incident.hypotheses,id:\.self) { Text($0).font(.callout).foregroundStyle(.secondary).padding(.top,6) }
                            ForEach(incident.episodes) { e in Text("\(friendlyCheck(e.check)) · \(localTime(e.start,seconds:true)) → \(e.recovery.map{localTime($0,seconds:true)} ?? "recovery not observed")").font(.system(size:13)).padding(.top,5) }
                        } label: {
                            Text("\(localTime(incident.start,seconds:true)) → \(incident.recovery.map{localTime($0,seconds:true)} ?? "recovery not observed")").font(.callout)
                        }.padding(.top,8)
                    }
                } else { Text("No evidence received").foregroundStyle(.secondary).padding(.top,6) }
            }
        }
    }
    var devices: some View {
        Panel {
            Text("Device replies seen from each Mini").font(.headline)
            Text("Local reachability only. Self-checks do not traverse the network. Address replies do not verify device identity or cloud access.").font(.system(size:13)).foregroundStyle(.secondary).padding(.top,7)
            let inventory = Dictionary((store.homeSnapshots.flatMap{$0.state.devices ?? []}).map{($0.id,$0)},uniquingKeysWith:{a,_ in a})
            ForEach(inventory.keys.sorted(),id:\.self) { id in
                if let device = inventory[id] {
                    Divider().padding(.vertical,12)
                    HStack(alignment:.top) {
                        Label(device.name,systemImage:deviceIcon(id)).font(.headline).frame(width:220,alignment:.leading)
                        ForEach(hosts,id:\.self) { host in
                            VStack(alignment:.leading,spacing:4) {
                                Text(host).font(.system(size:13).weight(.semibold))
                                if let s = snapshot(host), let d = s.state.devices?.first(where:{$0.id==id}) {
                                    Text(stale(s) || d.stale(at:store.now) ? "Unknown · stale" : d.isLocal ? "Local self-check" : d.status == "responding" ? "Verified reply" : d.status == "address_reply" ? "Address replies" : d.status == "unreachable" ? "No replies" : "Unknown")
                                    Text("\(elapsed(store.now-d.observed)) ago · \(d.identity)").font(.system(size:13)).foregroundStyle(.secondary)
                                } else { Text("No observation").foregroundStyle(.secondary) }
                            }.font(.callout).frame(maxWidth:.infinity,alignment:.leading)
                        }
                    }
                }
            }
        }
    }
}

struct InvestigationPanel: View {
    @ObservedObject var store: DashboardStore
    @State private var selection = ""
    @State private var target = "Cloudflare"
    @State private var selectedTime: Date?
    @State private var zoom = false
    @State private var offset = 0.0
    @State private var showLAN = false
    var reports: [InvestigationReport] { (store.snapshot?.investigations ?? []).sorted { $0.time > $1.time } }
    var report: InvestigationReport? { reports.first { $0.id == selection } ?? reports.first }
    var disabled: Bool { !store.isLocal || store.paused || store.managing || store.speedRunning || store.investigationRunning || store.backgroundInvestigation }
    var body: some View {
        Panel {
            HStack {
                VStack(alignment:.leading,spacing:5) {
                    Label("Connection investigation",systemImage:"waveform.path.ecg").font(.headline)
                    Text("\(store.snapshot?.state.host ?? "This Mini") · saved episodes, separate from current health").font(.system(size:13)).foregroundStyle(.secondary)
                }
                Spacer()
                if store.investigationRunning || store.backgroundInvestigation { ProgressView().controlSize(.small); Text("Capturing…").font(.system(size:13)) }
            }
            Text("Catch brief stalls with one-second ping rounds. A one-minute close-up also starts after a new failed or slow probe, at most once every five minutes. Scheduled speed tests capture latency before, during and after load.")
                .font(.callout).foregroundStyle(.secondary).fixedSize(horizontal:false,vertical:true).padding(.top,12)
            HStack(spacing:12) {
                Button("Capture 1 minute") { store.requestInvestigation("capture") }.disabled(disabled)
                Button("Inspect routes") { store.requestInvestigation("routes") }.disabled(disabled)
                Button("Test between Minis…") { showLAN.toggle() }
                Spacer()
                Button("Copy agent query") { copy("~/.local/bin/network-monitor investigate status") }
                Button("Credits") { NSWorkspace.shared.open(programHome.appendingPathComponent("ACKNOWLEDGMENTS.md")) }
            }.padding(.top,14)
            if showLAN { lanHelp.padding(.top,16) }
            if let report = report {
                Divider().padding(.vertical,14)
                Picker("Recorded episode",selection:$selection) {
                    Text("Most recent").tag("")
                    ForEach(reports) { r in Text("\(r.title) · \(localTime(r.time,seconds:true))").tag(r.id) }
                }.onChange(of:selection) { _,_ in offset=0; selectedTime=nil }
                HStack { Text(report.title).font(.title3.weight(.semibold)); Spacer(); Text(report.status.capitalized).foregroundStyle(report.status == "complete" ? .secondary : amber) }.padding(.top,12)
                Text("\(report.host) · \(localTime(report.time,seconds:true))–\(localTime(report.end,seconds:true)) · \(report.reason)")
                    .font(.system(size:13)).foregroundStyle(.secondary).textSelection(.enabled).padding(.top,4)
                if !report.points.isEmpty { episodeChart(report).padding(.top,14) }
                DisclosureGroup("How to read this capture") {
                    VStack(alignment:.leading,spacing:8) { ForEach(report.details,id:\.self) { Text($0).font(.callout).foregroundStyle(.secondary) } }.padding(.top,8).frame(maxWidth:.infinity,alignment:.leading)
                }.padding(.top,12)
                HStack {
                    Button("Open evidence folder",action:store.revealEvidence).disabled(!store.isLocal)
                    Button("Copy raw-history command") { copy("~/.local/bin/network-monitor investigate history --limit 5") }
                    Spacer()
                    Text("Latest episode per type shown · raw history retained locally").font(.system(size:13)).foregroundStyle(.secondary)
                }.padding(.top,12)
            } else {
                Text(store.backgroundInvestigation ? "A background capture is running. Its report will appear here when it finishes." : "No investigation captured yet. Routine monitoring continues; capture a close-up when the connection feels slow.")
                    .font(.callout).foregroundStyle(.secondary).padding(.top,16)
            }
        }
    }
    func episodeChart(_ report: InvestigationReport) -> some View {
        let start = report.time + (zoom ? min(offset,max(0,report.end-report.time-15)) : 0)
        let end = zoom ? min(report.end,start+15) : max(report.end,start+1)
        let points = report.points.filter { $0.target == target && $0.time >= start && $0.time <= end }
        let rows = report.groups.filter { $0.target == target }
        return VStack(alignment:.leading,spacing:12) {
            HStack {
                Picker("Path",selection:$target) { ForEach(["Main Orbi","Cloudflare","Google"],id:\.self) { Text($0).tag($0) } }.frame(maxWidth:320)
                Spacer()
                Toggle("15-second detail",isOn:$zoom).toggleStyle(.switch).controlSize(.small)
            }
            Chart {
                ForEach(Array(points.enumerated()),id:\.offset) { _,p in
                    if p.ok, let latency = p.latency {
                        PointMark(x:.value("Time",Date(timeIntervalSince1970:p.time)),y:.value("Response ms",latency))
                            .foregroundStyle(by:.value("Phase",p.phase)).symbolSize(22)
                    } else {
                        RuleMark(x:.value("Missed reply",Date(timeIntervalSince1970:p.time))).foregroundStyle(amber.opacity(0.35)).lineStyle(StrokeStyle(lineWidth:1,dash:[3,3]))
                    }
                }
            }.chartXScale(domain:Date(timeIntervalSince1970:start)...Date(timeIntervalSince1970:max(start+1,end)))
                .chartXSelection(value:$selectedTime).chartYAxisLabel("Milliseconds").frame(height:180)
            if zoom {
                HStack { Text("Earlier"); Slider(value:$offset,in:0...max(1,report.end-report.time-15)); Text("Later") }.font(.system(size:13))
            }
            if let selectedTime = selectedTime, let nearest = points.min(by:{ abs($0.time-selectedTime.timeIntervalSince1970) < abs($1.time-selectedTime.timeIntervalSince1970) }), abs(nearest.time-selectedTime.timeIntervalSince1970) <= 1.5 {
                Text("\(localTime(nearest.time,seconds:true)) · \(nearest.phase) · \(nearest.ok ? metric(nearest.latency)+" ms" : "No reply") · \(nearest.interface)").font(.system(size:13)).monospacedDigit()
            } else { Text("Click or drag to inspect a sample. Dashed amber lines are missed replies; blank time is unobserved.").font(.system(size:13)).foregroundStyle(.secondary) }
            Grid(alignment:.leading,horizontalSpacing:20,verticalSpacing:8) {
                GridRow { Text("Phase / interface"); Text("Missed / sent"); Text("Typical"); Text("10th–95th percentile") }.font(.system(size:13).weight(.semibold)).foregroundStyle(.secondary)
                ForEach(rows) { r in
                    GridRow { Text("\(r.phase.capitalized) · \(r.interface)"); Text("\(r.missed) / \(r.attempted)"); Text(metric(r.median)+" ms"); Text(metric(r.p10)+"–"+metric(r.p95)+" ms") }.font(.callout).monospacedDigit()
                }
            }
            Text("Statistics cover the full episode, including when zoomed. Latency uses successful replies; missing replies are not zero. This is not Zoom media jitter or a bufferbloat score.").font(.system(size:13)).foregroundStyle(.secondary)
        }
    }
    var lanHelp: some View {
        VStack(alignment:.leading,spacing:10) {
            Text("Optional test between computers").font(.headline)
            Text("This optional LAN test needs a second computer with iperf3. Open a temporary receiver on the wired computer, then run one 15-second test from the other computer. Repeat with the reverse direction. Internet monitoring and speed tests do not require this setup. This generates heavy LAN traffic; use it outside meetings and the :14–:20 / :44–:50 internet-test windows.")
            Text("The receiver binds to a private LAN address, accepts one client, and closes within 60 seconds. It is not authenticated: another LAN device could connect during that window. No receiver starts from this panel.")
            Button("Open LAN-test instructions") { NSWorkspace.shared.open(programHome.appendingPathComponent("INVESTIGATIONS.md")) }
            Text("The step-by-step commands use each Mini’s current LAN address. Saved results will appear here on the initiating Mini; export its snapshot to compare elsewhere.").foregroundStyle(.secondary)
        }.font(.callout).padding(14).frame(maxWidth:.infinity,alignment:.leading).background(ocean.opacity(0.06),in:RoundedRectangle(cornerRadius:10))
    }
    func copy(_ text: String) { NSPasteboard.general.clearContents(); NSPasteboard.general.setString(text,forType:.string) }
}
