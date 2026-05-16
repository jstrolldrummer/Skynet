import SwiftUI

struct ContentView: View {
    @State private var path = NavigationPath()
    @State private var showingSettings = false

    var body: some View {
        NavigationStack(path: $path) {
            ConversationListView(path: $path)
                .navigationTitle("Skynet")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button {
                            showingSettings = true
                        } label: {
                            Image(systemName: "gear")
                        }
                    }
                }
                .navigationDestination(for: Conversation.self) { conv in
                    ChatView(conversation: conv)
                }
                .sheet(isPresented: $showingSettings) {
                    SettingsView()
                }
        }
    }
}
