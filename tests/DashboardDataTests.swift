import Foundation

func require(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    if !condition() { throw NSError(domain:"DashboardTests",code:1,userInfo:[NSLocalizedDescriptionKey:message]) }
}
func check(_ id:String,_ ok:Bool,_ time:Double,_ latency:Double?=10) -> CheckEvidence {
    .init(id:id,ok:ok,latency:ok ? latency:nil,target:"192.0.2.1",kind:"icmp",detail:"synthetic",confirmedDown:false,time:time)
}
func point(_ time:Double,_ value:Double?=10) -> SamplePoint {
    .init(time:time,interval:15,lanes:Array(repeating:2,count:laneNames.count),cloudflare:value,google:value,orbi:1,failed:value == nil ? 2:0,total:21,pingFailed:value == nil ? 2:0,pingTotal:2,loaded:false,interface:"en0")
}
@main struct DashboardDataTests {
    static func main() throws {
        let host = HostContext.parse(["at":"2026-11-16T20:00:00Z", "cpu_status":"available", "cpu_busy_percent":0, "memory_pressure":"normal"])
        try require(host?.cpu == 0,"Measured zero CPU remains a valid reading")
        try require(host?.stale(at:host!.at+181) == true,"Host readings have independent freshness")
        try require(HostContext.parse(["at":"2026-11-16T20:00:00Z", "cpu_status":"gap", "cpu_busy_percent":50])?.cpu == nil,"Gaps do not expose stale CPU")
        var loadedPoint = point(1,100); loadedPoint.loaded = true
        var otherPoint = point(2,10); otherPoint.loadKnown = true
        let unknownPoint = point(3,900)
        try require(loadLatency([loadedPoint,otherPoint,unknownPoint],loaded:false).median == 10,"Missing load tags are excluded from comparison")
        try require(loadLatency([loadedPoint,otherPoint],loaded:true).median == 100,"Loaded replies kept separate")
        try require(loadLatency([],loaded:true).median == nil,"No loaded evidence is unknown")
        try require(sharingStatus(state:"connected",updated:100,lastExchange:100,now:110) == "Connected","Recent exchange is connected")
        try require(sharingStatus(state:"connected",updated:200,lastExchange:100,now:210).hasPrefix("Disconnected"),"Fresh worker cannot hide a stale exchange")
        try require(sharingStatus(state:"connected",updated:100,lastExchange:100,now:210) == "Sync worker not reporting","Dead worker cannot appear connected")
        let now=Date().timeIntervalSince1970
        func speed(_ offset:Double,_ down:Double?,_ up:Double?=50,_ status:String="success",_ interface:String="en0") -> SpeedPoint {
            .init(time:now+offset,end:now+offset,status:status,down:down,up:up,idle:nil,downRPM:nil,upRPM:nil,interface:interface,reason:nil)
        }
        let speedRows=[speed(-4000,100),speed(-3000,200,nil),speed(-2000,300),speed(-1000,nil),speed(-500,500),speed(-100,700)]
        let throughput=throughputSummary(speedRows,direction:"Download",window:(now-3500)...now)
        try require(throughput.mean == 425 && throughput.points.count == 4,"Average uses only measured values in the visible interval; missing values are not zero")
        try require(throughput.points.map(\.trend) == [200,250,500,600],"Moving average warms up and resets after missing measurements")
        try require(throughput.points[1].segment != throughput.points[2].segment,"Trend does not bridge a missing value")
        let upload=throughputSummary(speedRows,direction:"Upload",window:(now-3500)...now)
        try require(upload.mean == 50 && upload.points.count == 4,"Upload is averaged independently of download availability")
        let broken=throughputSummary([speed(-10000,10),speed(-9000,20,50,"failed"),speed(-8000,30),speed(-7000,40,50,"success","en1"),speed(-10,50,50,"success","en1")],direction:"Download",window:(now-11000)...now)
        try require(Set(broken.points.map(\.segment)).count == 3,"Failed tests and interface changes break trend segments")
        let sparse=throughputSummary([speed(-10000,100),speed(-1,200)],direction:"Download",window:(now-11000)...now)
        try require(sparse.points.map(\.trend) == [100,200] && sparse.points[0].segment != sparse.points[1].segment,"A gap over two hours resets and breaks the trend")
        try require(throughputSummary([speed(-1,0)],direction:"Download",window:(now-10)...now).mean == 0,"A measured zero is valid")
        try require(throughputSummary([speed(-1,nil),speed(-2,Double.infinity),speed(-3,-1)],direction:"Download",window:(now-10)...now).mean == nil,"Missing and invalid throughput never fabricate an average")
        try require(throughputSummary(speedRows,direction:"Download",window:(now-600)...now).mean == 600,"Zoom recalculates the mean from the newly visible measured tests")
        let overlap = IncidentEvidence(id:"overlap",start:now-120,recovery:now-30,uncertain:false,hypotheses:[],episodes:[
            .init(check:"cloudflare_https",start:now-120,recovery:now-45,confirmed:now-105),
            .init(check:"google_https",start:now-100,recovery:now-30,confirmed:now-85)])
        let interrupted = internetInterruptions([overlap],start:now-90,end:now)
        try require(interrupted.count == 1 && interrupted[0].start == now-100 && interrupted[0].recovery == now-45,"Internet interruption uses overlapping HTTPS episodes, retaining onset before window")
        var separate = overlap; separate.episodes[1].start = now-40; separate.episodes[1].confirmed = now-35
        try require(internetInterruptions([separate],start:now-200,end:now).isEmpty,"Different destinations failing at different times is not an internet interruption")
        var single = overlap; single.episodes.removeLast()
        try require(internetInterruptions([single],start:now-200,end:now).isEmpty,"One destination failing cannot count as lost internet access")
        var unconfirmed = overlap; unconfirmed.episodes[1].confirmed = nil
        try require(internetInterruptions([unconfirmed],start:now-200,end:now).isEmpty,"One failed sample cannot confirm an interruption")
        var open = overlap; open.recovery = nil; open.uncertain = true
        for i in open.episodes.indices { open.episodes[i].recovery = nil }
        let ongoing = internetInterruptions([open],start:now-200,end:now)
        try require(ongoing.count == 1 && ongoing[0].recovery == nil && ongoing[0].uncertain,"Open interruptions preserve unknown recovery and monitoring gaps")
        try require(internetInterruptions([overlap],start:now-20,end:now).isEmpty,"Recovered interruptions outside the window are excluded")
        var changedPath = point(now-15,500); changedPath.interface = "en1"
        let callSamples = [point(now-400,999),point(now-120,10),point(now-105,20),point(now-90,nil),point(now-75,100),point(now-30,300),changedPath]
        let call = recentPathMetrics(callSamples,key:\.google,end:now)
        try require(call.replies == 5 && call.p95 == 500 && call.variation == 10,"Recent performance excludes old points and breaks variation at loss, gaps and path changes")
        try require(recentPathMetrics([],key:\.orbi,end:now).median == nil,"No performance evidence must not become zero")
        try require(configuredLaneIndices([check("orbi_icmp",true,now)]) == [0,1,2,3],"A single observer has no absent-peer or satellite lanes")
        try require(configuredLaneIndices([check("peer_icmp",false,now),check("satellite_1_icmp",false,now)]) == [0,1,2,3,4,6],"Configured failed paths remain visible rather than being hidden")
        try require(groupStatus([check("a",true,now)],ids:["a","b"]) == -1,"Missing checks must be unknown")
        try require(groupStatus([check("a",true,now),check("b",false,now)],ids:["a","b"]) == 1,"Partial success is degraded, not offline")
        try require(number(true) == nil && number(-1) == nil && number(Double.infinity) == nil,"Reject invalid numeric evidence")
        let staleState=CurrentEvidence(host:"Synthetic-Mini",completed:now-46,interval:15,interface:"en0",checks:[check("cloudflare_https",true,now),check("google_https",true,now)],incidents:[],speedActive:false)
        try require(staleState.stale(at:now),"45-second stale threshold at 15-second cadence")
        try require(staleState.stale(at:now-100),"Clock reversal is stale")
        let device = DeviceEvidence.parse(["id":"camera","name":"Camera","observed_at":ISO8601DateFormatter.fractional.string(from:Date(timeIntervalSince1970:now-181)),"status":"responding"])
        try require(device?.stale(at:now) == true,"Old device replies must be stale independently of recorder freshness")
        let observations=[point(now-120),point(now-105),point(now-90,nil),point(now-75),point(now-10)]
        let lines=latencyPoints(samples:observations,start:now-200)
        let segments=Set(lines.filter{$0.series=="Cloudflare"}.map(\.segment))
        try require(segments.count == 3,"Latency must break at failed probes AND missing intervals")
        try require(lines.allSatisfy{$0.value>0},"Missing latency cannot become zero")
        let dense=(0..<1000).map{point(now-Double(1000-$0),$0==501 ? 500:10)}
        let reduced=latencyPoints(samples:dense,start:now-1001,maxBuckets:10)
        try require(reduced.contains{$0.value==500},"Peak-preserving aggregation must retain spikes")
        let bounds=0.0...3600.0
        let tiny=ChartWindow.fit(1900...1901,inside:bounds)
        try require(tiny.upperBound-tiny.lowerBound == 60,"Minimum zoom keeps enough context for 15-second samples")
        let edge=ChartWindow.zoom(bounds,factor:0.5,around:3590,inside:bounds)
        try require(edge == 1800...3600,"Zoom near latest data clamps inside the parent window")
        try require(ChartWindow.move(edge,direction:1,inside:bounds) == edge,"Navigation cannot move beyond available range")
        try require(ChartWindow.move(edge,direction:-1,inside:bounds) == 900...2700,"Pan preserves duration and overlaps the preceding window")
        try require(ChartWindow.zoom(edge,factor:10,around:nil,inside:bounds) == bounds,"Zoom out is capped at full range")
        let detail=latencyPoints(samples:dense,window:(now-505)...(now-490))
        try require(detail.filter{$0.series == "Cloudflare"}.count == 16,"Zoom must reveal original samples, not zoom a reduced full-range line")
        try require(detail.allSatisfy{((now-505)...(now-490)).contains($0.time)},"No samples outside zoom can affect the chart")
        try require(inspectedSample(observations,at:now-45,window:(now-200)...now) == nil,"Clicking a gap cannot snap to a distant healthy reply")
        try require(inspectedSample(observations,at:now-90,window:(now-200)...now)?.cloudflare == nil,"Failed ping remains a recorded no-reply sample")
        let spans=laneSpans(samples:[point(now-90),point(now-75),point(now-15)],start:now-100,end:now)
        try require(spans.contains{$0.status == -1 && $0.start==now-60 && $0.end==now-15},"Timeline gaps must be explicitly unknown")
        try require(observedSeconds(samples:[point(now-90),point(now-75),point(now-15)],start:now-100,end:now) == 45,"Coverage cannot count gaps")
        let jitter=laneSpans(samples:[point(now-30),point(now-14.9)],start:now-30,end:now)
        try require(!jitter.contains{$0.status == -1},"Subsecond scheduler jitter is not an outage")
        var capture = InvestigationReport(schema:"network-monitor.investigation.v1",id:"synthetic",kind:"close-up",reason:"fixture",host:"Synthetic-Mini",time:now-60,end:now,status:"complete",details:[],groups:[],points:[.init(time:now-5,target:"Cloudflare",phase:"observation",interface:"en1",ok:false,latency:nil)])
        try require(capture.valid,"A missed reply in a bounded diagnostic session is valid evidence")
        capture.points[0].target = "Local loopback"
        try require(capture.valid,"Local control measurements remain visible in the dashboard")
        capture.points[0].target = "Satellite 2"
        try require(capture.valid,"Configured satellite measurements remain visible")
        capture.points[0].target = "Unexpected target"
        try require(!capture.valid,"Unknown diagnostic targets remain rejected")
        capture.points[0].target = "Cloudflare"
        capture.points[0].latency = -1
        try require(!capture.valid,"Reject negative investigation latency")
        capture.points[0].latency = nil
        capture.groups = [.init(target:"Cloudflare",phase:"observation",interface:"en1",attempted:1,missed:1,loss:0,p10:nil,median:nil,p95:nil,maximum:nil)]
        try require(!capture.valid,"Reject a loss percentage inconsistent with attempts and misses")
        capture.groups = []; capture.end = now+500
        try require(!capture.valid,"Reject unbounded imported diagnostic sessions")
        let root=FileManager.default.temporaryDirectory.appendingPathComponent("dashboard-test-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:root) }
        let iso=ISO8601DateFormatter.fractional.string(from:Date(timeIntervalSince1970:now-5))
        let diagnostic = DiagnosticEvidence.parse(["type":"diagnostic_snapshot", "finished_at":iso, "gateway":["fiberstat":["status":"available", "optical_readings":["Rx Power":-181.0]]]])
        try require(diagnostic?.availablePages == 1 && diagnostic?.details.contains("Optical receive power: -18.1 dBm") == true,"Diagnostic summary preserves negative optical values and counts only available pages")
        try require(diagnostic?.stale(at:now+300) == true,"Supplemental evidence ages independently")
        try require(DiagnosticEvidence.parse(["type":"diagnostic_error", "at":iso]) == nil,"Collector errors must not appear healthy")
        let rawCheck:[String:Any]=["id":"cloudflare_icmp","ok":true,"latency_ms":11,"target":"192.0.2.1","kind":"icmp","detail":"synthetic","started_at":iso]
        let rawState:[String:Any]=["host":["hostname":"Synthetic-Mini"],"last_completed_at":iso,"interval_seconds":15,"checks":["cloudflare_icmp":["latest":rawCheck,"down":false]],"recent_incidents":[]]
        let rawSample:[String:Any]=["started_at":iso,"interval_seconds":15,"checks":[rawCheck]]
        try JSONSerialization.data(withJSONObject:rawState).write(to:root.appendingPathComponent("state.json"))
        var data=try JSONSerialization.data(withJSONObject:rawSample); data.append(10)
        let journal=root.appendingPathComponent("samples-test.jsonl")
        try data.write(to:journal)
        let reader=EvidenceReader(root:root)
        var snapshot=try reader.update(now:now)
        try require(snapshot.samples.count==1,"Read initial sample")
        let again=try reader.update(now:now)
        try require(again.samples.count==1,"Unchanged file must not duplicate samples")
        var partial=data; partial.append(Data("{\"unfinished\":".utf8)); try partial.write(to:journal)
        snapshot=try reader.update(now:now)
        try require(snapshot.samples.count==1 && reader.malformed==0,"Partial trailing record must be retried, not treated as a full record")
        try (data+Data("malformed\n".utf8)).write(to:journal)
        _=try reader.update(now:now)
        try require(reader.malformed==1,"Report malformed complete records")

        let chunkFile=root.appendingPathComponent("chunk-test.txt")
        let longLine=String(repeating:"x",count:100_000)
        let prefix="first\n\n"+longLine+"\n"
        try Data((prefix+"partial").utf8).write(to:chunkFile)
        let chunkHandle=try FileHandle(forReadingFrom:chunkFile)
        var chunkLines:[String]=[]
        let committed=try readCompleteJSONLines(chunkHandle,from:0,through:UInt64(prefix.utf8.count+7),chunkSize:4096) { chunkLines.append(String(decoding:$0,as:UTF8.self)) }
        try require(chunkLines == ["first",longLine] && committed == UInt64(prefix.utf8.count),"Chunk reader keeps long records and leaves incomplete tail unconsumed")
        try chunkHandle.close()
        try Data((prefix+"partial\n").utf8).write(to:chunkFile)
        let resumedHandle=try FileHandle(forReadingFrom:chunkFile); try resumedHandle.seek(toOffset:committed)
        var resumed:[String]=[]
        _=try readCompleteJSONLines(resumedHandle,from:committed,through:UInt64(prefix.utf8.count+8),chunkSize:3) { resumed.append(String(decoding:$0,as:UTF8.self)) }
        try resumedHandle.close()
        try require(resumed == ["partial"],"Next refresh retries exactly the completed tail")
        let aged=try reader.update(now:now+8*86400)
        try require(aged.samples.isEmpty && reader.samples.isEmpty,"Expired chart samples leave both caches even when files are unchanged")
        try require(snapshot.samples.count == 1,"Published snapshots remain immutable while the reader prunes its cache")
        try require(groupStatus([check("a",true,now),check("a",true,now)],ids:["a","b"]) == -1,"Duplicate check identities cannot fabricate two-provider success")
        var negativePing = snapshot; negativePing.samples[0].pingFailed = -1
        var negativeLatency = snapshot; negativeLatency.samples[0].cloudflare = -5
        var duplicateSamples = snapshot; duplicateSamples.samples.append(duplicateSamples.samples[0])
        var negativeSpeed = snapshot; negativeSpeed.speeds = [.init(time:now,end:now,status:"success",down:-1,interface:"en0")]
        for malformedSnapshot in [negativePing,negativeLatency,duplicateSamples,negativeSpeed] {
            do { try malformedSnapshot.validate(); throw NSError(domain:"test",code:99) }
            catch let e as NSError { try require(e.code != 99,"Reject impossible imported measurement or duplicate timeline") }
        }
        try require(!observationIsPaused(snapshot.state,local:false,localPaused:true),"Pausing this Mac must not pause the peer view")
        try require(observationIsPaused(snapshot.state,local:true,localPaused:true),"Local pause applies to local evidence")
        var pausedPeer=snapshot.state; pausedPeer.recordingPaused=true
        try require(observationIsPaused(pausedPeer,local:false,localPaused:false),"Peer pause remains visible on the other Mac")
        let syncRoot=root.appendingPathComponent("Sync")
        let peerRoot=syncRoot.appendingPathComponent("peer")
        let slotA=peerRoot.appendingPathComponent("slot-a"), slotB=peerRoot.appendingPathComponent("slot-b")
        try FileManager.default.createDirectory(at:slotA,withIntermediateDirectories:true)
        try FileManager.default.createDirectory(at:slotB,withIntermediateDirectories:true)
        try JSONSerialization.data(withJSONObject:rawState).write(to:slotA.appendingPathComponent("state.json"))
        try data.write(to:slotA.appendingPathComponent("samples-test.jsonl"))
        var otherState=rawState; otherState["host"]=["hostname":"Second-Synthetic-Mini"]
        try JSONSerialization.data(withJSONObject:otherState).write(to:slotB.appendingPathComponent("state.json"))
        let pointer=peerRoot.appendingPathComponent("current.json")
        try JSONSerialization.data(withJSONObject:["directory":"slot-a","generation":"a"]).write(to:pointer)
        let lock=Darwin.open(peerRoot.appendingPathComponent("cache.lock").path,O_CREAT | O_RDWR,0o600)
        defer { Darwin.close(lock) }
        let peerReader=PeerEvidenceReader()
        let firstPeer=try peerReader.update(root:syncRoot)
        try require(firstPeer?.state.host == "Synthetic-Mini","Read first peer generation")
        flock(lock,LOCK_EX)
        try JSONSerialization.data(withJSONObject:["directory":"slot-b","generation":"a"]).write(to:pointer)
        let busyPeer=try peerReader.update(root:syncRoot)
        try require(busyPeer?.state.host == "Synthetic-Mini","During cache swap retain last complete snapshot without blocking UI")
        flock(lock,LOCK_UN)
        let nextPeer=try peerReader.update(root:syncRoot)
        try require(nextPeer?.state.host == "Second-Synthetic-Mini","Read newly committed peer slot after unlocking")
        try FileManager.default.removeItem(at:pointer)
        let clearedPeer=try peerReader.update(root:syncRoot)
        try require(clearedPeer == nil,"Explicit peer cache deletion must clear the displayed peer")
        let encoded=try JSONEncoder().encode(snapshot)
        try JSONDecoder().decode(DashboardSnapshot.self,from:encoded).validate()
        var invalid=snapshot; invalid.samples[0].lanes=[]
        do { try invalid.validate(); throw NSError(domain:"test",code:99) } catch let e as NSError { try require(e.code != 99,"Reject malformed imported timeline") }
        print("Dashboard data tests passed: missing evidence, stale clocks, partial failure, chart discontinuities, peak retention, coverage, incremental/torn journals, snapshot validation.")
    }
}
