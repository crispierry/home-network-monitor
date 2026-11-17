import Foundation
import Darwin
@main struct MemoryBenchmark {
 static func main() throws {
  let root=URL(fileURLWithPath:CommandLine.arguments[1]); let now=1800000000.0
  let reader=EvidenceReader(root:root)
  let start=Date()
  var snapshot=try reader.update(now:now)
  for _ in 0..<5 { snapshot=try reader.update(now:now) }
  var usage=rusage(); getrusage(RUSAGE_SELF,&usage)
  print("peak_rss_bytes=\(usage.ru_maxrss)")
  print("samples=\(snapshot.samples.count) malformed=\(reader.malformed) seconds=\(Date().timeIntervalSince(start))")
 }
}
