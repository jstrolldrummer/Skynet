import SwiftUI

struct ConversationListView: View {
    @Environment(Settings.self) var settings
    @Binding var path: NavigationPath
    @State private var conversations: [Conversation] = []
    @State private var error: String?
    @State private var loading = false

    private var client: APIClient {
        APIClient(serverURL: settings.serverURL, authToken: settings.authToken)
    }

    var body: some View {
        List {
            if settings.serverURL.isEmpty {
                ContentUnavailableView(
                    "No server configured",
                    systemImage: "server.rack",
                    description: Text("Tap the gear icon to add your Mac's address and auth token.")
                )
                .listRowBackground(Color.clear)
            } else if let error {
                Text(error)
                    .foregroundStyle(.red)
                    .font(.caption)
            }
            ForEach(conversations) { conv in
                NavigationLink(value: conv) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(conv.title).font(.headline)
                        Text(Date(timeIntervalSince1970: conv.updated_at), style: .relative)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .onDelete(perform: delete)
        }
        .refreshable { await load() }
        .task(id: settings.serverURL + settings.authToken) { await load() }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button {
                    Task { await create() }
                } label: {
                    Image(systemName: "square.and.pencil")
                }
                .disabled(settings.serverURL.isEmpty)
            }
        }
    }

    private func load() async {
        guard !settings.serverURL.isEmpty else { return }
        loading = true
        defer { loading = false }
        do {
            conversations = try await client.listConversations()
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func create() async {
        do {
            let conv = try await client.createConversation(title: "New conversation")
            conversations.insert(conv, at: 0)
            path.append(conv)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func delete(at offsets: IndexSet) {
        let targets = offsets.map { conversations[$0] }
        conversations.remove(atOffsets: offsets)
        Task {
            for t in targets {
                try? await client.deleteConversation(id: t.id)
            }
        }
    }
}
