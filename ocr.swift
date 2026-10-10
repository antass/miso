// OCR page images with macOS Vision. Usage: ocr <image>...  → one JSON array per line of output:
// [{"t": text, "x": left, "y": top, "w": width, "h": height}]  (coordinates 0–1, origin top-left)
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    var out: [[String: Any]] = []
    if let img = NSImage(contentsOfFile: path),
       let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = true
        let handler = VNImageRequestHandler(cgImage: cg, options: [:])
        try? handler.perform([req])
        for obs in req.results ?? [] {
            guard let cand = obs.topCandidates(1).first else { continue }
            let b = obs.boundingBox
            out.append(["t": cand.string, "x": b.minX, "y": 1 - b.maxY, "w": b.width, "h": b.height])
        }
    }
    let data = try! JSONSerialization.data(withJSONObject: out)
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}
