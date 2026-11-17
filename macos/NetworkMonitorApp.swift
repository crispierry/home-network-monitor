import AppKit
import SwiftUI

@main struct NetworkMonitorApplication {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}
@MainActor final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuItemValidation {
    var window: NSWindow!
    var store: DashboardStore!
    func applicationDidFinishLaunching(_ notification: Notification) {
        let args = CommandLine.arguments
        var root = evidenceHome
        let fixture = args.contains("--fixture")
        if let index = args.firstIndex(of:"--evidence-dir"), args.indices.contains(index+1) { root = URL(fileURLWithPath:args[index+1]) }
        store = DashboardStore(root:root,fixture:fixture)
        let menu = NSMenu()
        let applicationMenu = NSMenu(); applicationMenu.addItem(withTitle:"About Network Monitor",action:#selector(NSApplication.orderFrontStandardAboutPanel(_:)),keyEquivalent:"")
        applicationMenu.addItem(.separator()); applicationMenu.addItem(withTitle:"Hide Network Monitor",action:#selector(NSApplication.hide(_:)),keyEquivalent:"h")
        applicationMenu.addItem(withTitle:"Quit Network Monitor",action:#selector(NSApplication.terminate(_:)),keyEquivalent:"q")
        let applicationItem=NSMenuItem(); applicationItem.submenu=applicationMenu; menu.addItem(applicationItem)
        func addMenu(_ title:String, _ items:[NSMenuItem]) {
            let submenu=NSMenu(title:title)
            items.forEach { submenu.addItem($0) }
            let item=NSMenuItem(title:title,action:nil,keyEquivalent:""); item.submenu=submenu; menu.addItem(item)
        }
        func command(_ title:String, _ action:Selector, _ key:String="") -> NSMenuItem {
            let item=NSMenuItem(title:title,action:action,keyEquivalent:key); item.target=self; return item
        }
        addMenu("File", [command("Import Other Mini…",#selector(importEvidence),"o"),
                         command("Export Snapshot…",#selector(exportEvidence),"s"),
                         command("Open Local Logs",#selector(openLogs)), .separator(),
                         command("Report a Connection Problem…",#selector(reportProblem),"n")])
        addMenu("Edit", [NSMenuItem(title:"Undo",action:Selector(("undo:")),keyEquivalent:"z"),
                         NSMenuItem(title:"Cut",action:#selector(NSText.cut(_:)),keyEquivalent:"x"),
                         NSMenuItem(title:"Copy",action:#selector(NSText.copy(_:)),keyEquivalent:"c"),
                         NSMenuItem(title:"Paste",action:#selector(NSText.paste(_:)),keyEquivalent:"v"),
                         NSMenuItem(title:"Select All",action:#selector(NSText.selectAll(_:)),keyEquivalent:"a")])
        var views=[NSMenuItem]()
        for (index,title) in ["Overview","Performance","Devices","Incidents","Evidence","Monitoring & storage"].enumerated() {
            let item=command(title,#selector(selectSection(_:)),String(index+1)); item.tag=index; views.append(item)
        }
        views += [.separator(),command("Refresh Evidence",#selector(refreshEvidence),"r")]
        addMenu("View",views)
        addMenu("Window", [NSMenuItem(title:"Minimize",action:#selector(NSWindow.performMiniaturize(_:)),keyEquivalent:"m"),
                           NSMenuItem(title:"Zoom",action:#selector(NSWindow.performZoom(_:)),keyEquivalent:""),
                           command("Show Dashboard",#selector(showDashboard))])
        NSApp.windowsMenu=menu.items.last?.submenu
        NSApp.mainMenu=menu
        window=NSWindow(contentRect:NSRect(x:0,y:0,width:1200,height:860),styleMask:[.titled,.closable,.miniaturizable,.resizable],backing:.buffered,defer:false)
        window.title="Network Monitor · \(dashboardVersion)"; window.titleVisibility = .hidden; window.titlebarAppearsTransparent=true; window.minSize=NSSize(width:1000,height:700)
        window.isReleasedWhenClosed=false; window.setFrameAutosaveName("NetworkMonitorDashboard")
        window.contentView=NSHostingView(rootView:DashboardView(store:store))
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true)
    }
    @objc func selectSection(_ sender:NSMenuItem) {
        store.section=["Overview","Performance","Devices","Incidents","Evidence","Monitoring & storage"][sender.tag]
        showDashboard()
    }
    @objc func importEvidence() { store.importSnapshot() }
    @objc func exportEvidence() { store.exportSnapshot() }
    @objc func openLogs() { store.revealEvidence() }
    @objc func refreshEvidence() { store.refresh() }
    @objc func reportProblem() { store.showObservation=true; showDashboard() }
    @objc func showDashboard() { window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps:true) }
    func validateMenuItem(_ item:NSMenuItem) -> Bool {
        if item.action == #selector(exportEvidence) { return store?.snapshot != nil }
        if item.action == #selector(reportProblem) { return store?.canRecordObservation == true }
        if item.action == #selector(selectSection(_:)) { item.state = item.title == store?.section ? .on : .off }
        return true
    }
    func applicationShouldHandleReopen(_ sender:NSApplication,hasVisibleWindows flag:Bool)->Bool { window.makeKeyAndOrderFront(nil); return true }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender:NSApplication)->Bool { true }
}
