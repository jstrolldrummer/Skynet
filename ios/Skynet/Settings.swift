import Foundation
import Observation

@Observable
final class Settings {
    var serverURL: String { didSet { persist() } }
    var authToken: String { didSet { persist() } }

    private init(serverURL: String, authToken: String) {
        self.serverURL = serverURL
        self.authToken = authToken
    }

    static func load() -> Settings {
        let d = UserDefaults.standard
        return Settings(
            serverURL: d.string(forKey: "serverURL") ?? "",
            authToken: d.string(forKey: "authToken") ?? ""
        )
    }

    private func persist() {
        let d = UserDefaults.standard
        d.set(serverURL, forKey: "serverURL")
        d.set(authToken, forKey: "authToken")
    }
}
