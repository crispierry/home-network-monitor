import Foundation
import CoreWLAN

let client = CWWiFiClient.shared()
var result: [String:Any] = ["status":"unavailable", "source":"CoreWLAN", "bssid":"unavailable (not exposed without additional permissions)"]
if let interface = client.interface() {
    let associated = interface.interfaceMode() == .station && interface.wlanChannel() != nil
    result["interface"] = interface.interfaceName
    result["power_on"] = interface.powerOn()
    result["associated"] = associated
    result["status"] = associated ? "available" : "not_associated"
    if associated {
        let signal = interface.rssiValue(), noise = interface.noiseMeasurement()
        if (-127 ... -1).contains(signal) { result["rssi_dbm"] = signal }
        if (-127 ... -1).contains(noise) { result["noise_dbm"] = noise }
        if (-127 ... -1).contains(signal) && (-127 ... -1).contains(noise) {
            result["signal_noise"] = "\(signal) dBm / \(noise) dBm"
            result["snr_db"] = signal-noise
        }
        let rate = interface.transmitRate()
        if rate.isFinite && rate > 0 { result["rate_mbps"] = rate }
        if let channel = interface.wlanChannel() {
            let band = [1:"2.4 GHz",2:"5 GHz",3:"6 GHz"][channel.channelBand.rawValue] ?? "band unknown"
            let width = [1:"20 MHz",2:"40 MHz",3:"80 MHz",4:"160 MHz"][channel.channelWidth.rawValue] ?? "width unknown"
            result["channel"] = "\(channel.channelNumber) (\(band), \(width))"
            result["channel_number"] = channel.channelNumber
            result["channel_band"] = channel.channelBand.rawValue
            result["channel_width"] = channel.channelWidth.rawValue
        }
        result["phy"] = [1:"802.11a",2:"802.11b",3:"802.11g",4:"802.11n",5:"802.11ac",6:"802.11ax",7:"802.11be"][interface.activePHYMode().rawValue] ?? "unknown"
        if let bssid = interface.bssid(), bssid.range(of:"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$",options:.regularExpression) != nil {
            result["bssid"] = bssid.lowercased()
        }
    }
}
if let data = try? JSONSerialization.data(withJSONObject:result,options:[.sortedKeys]), let text = String(data:data,encoding:.utf8) { print(text) }
