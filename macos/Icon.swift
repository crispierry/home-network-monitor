import AppKit

let destination=URL(fileURLWithPath:CommandLine.arguments[1])
try FileManager.default.createDirectory(at:destination,withIntermediateDirectories:true)
func drawIcon(_ pixels:Int) -> Data {
    let bitmap=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:pixels,pixelsHigh:pixels,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current=NSGraphicsContext(bitmapImageRep:bitmap)
    let scale=Double(pixels)/1024
    let transform=AffineTransform(scale:scale); (transform as NSAffineTransform).concat()
    let tile=NSBezierPath(roundedRect:NSRect(x:80,y:80,width:864,height:864),xRadius:196,yRadius:196)
    NSGradient(colors:[NSColor(calibratedRed:0.035,green:0.17,blue:0.24,alpha:1),NSColor(calibratedRed:0.05,green:0.40,blue:0.43,alpha:1)])!.draw(in:tile,angle:55)
    NSColor.white.withAlphaComponent(0.10).setStroke(); tile.lineWidth=3; tile.stroke()
    let roof=NSBezierPath(); roof.move(to:NSPoint(x:250,y:522)); roof.line(to:NSPoint(x:512,y:748)); roof.line(to:NSPoint(x:774,y:522))
    roof.lineWidth=50; roof.lineCapStyle = .round; roof.lineJoinStyle = .round; NSColor(calibratedWhite:0.96,alpha:1).setStroke(); roof.stroke()
    let walls=NSBezierPath(); walls.move(to:NSPoint(x:318,y:524)); walls.line(to:NSPoint(x:318,y:302)); walls.line(to:NSPoint(x:706,y:302)); walls.line(to:NSPoint(x:706,y:524))
    walls.lineWidth=44; walls.lineCapStyle = .round; walls.lineJoinStyle = .round; NSColor(calibratedWhite:0.96,alpha:0.95).setStroke(); walls.stroke()
    let pulse=NSBezierPath(); pulse.move(to:NSPoint(x:235,y:430)); pulse.line(to:NSPoint(x:404,y:430)); pulse.line(to:NSPoint(x:456,y:535)); pulse.line(to:NSPoint(x:527,y:364)); pulse.line(to:NSPoint(x:579,y:462)); pulse.line(to:NSPoint(x:790,y:462))
    pulse.lineWidth=42; pulse.lineCapStyle = .round; pulse.lineJoinStyle = .round
    NSColor(calibratedRed:0.39,green:0.96,blue:0.72,alpha:1).setStroke(); pulse.stroke()
    NSColor(calibratedRed:0.39,green:0.96,blue:0.72,alpha:1).setFill()
    NSBezierPath(ovalIn:NSRect(x:208,y:403,width:54,height:54)).fill(); NSBezierPath(ovalIn:NSRect(x:763,y:435,width:54,height:54)).fill()
    NSColor(calibratedRed:1,green:0.76,blue:0.34,alpha:1).setFill(); NSBezierPath(ovalIn:NSRect(x:744,y:734,width:72,height:72)).fill()
    NSGraphicsContext.restoreGraphicsState()
    return bitmap.representation(using:.png,properties:[:])!
}
for size in [16,32,128,256,512] {
    try drawIcon(size).write(to:destination.appendingPathComponent("icon_\(size)x\(size).png"))
    try drawIcon(size*2).write(to:destination.appendingPathComponent("icon_\(size)x\(size)@2x.png"))
}
