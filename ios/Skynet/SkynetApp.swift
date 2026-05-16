import SwiftUI

@main
struct SkynetApp: App {
    @State private var settings = Settings.load()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(settings)
        }
    }
}
