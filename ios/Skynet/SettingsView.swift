import SwiftUI

struct SettingsView: View {
    @Environment(Settings.self) var settings
    @Environment(\.dismiss) var dismiss

    @State private var serverURL = ""
    @State private var authToken = ""
    @State private var testStatus: String?
    @State private var testing = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("https://your-mac.tail-net.ts.net:8080", text: $serverURL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    SecureField("Auth token", text: $authToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }
                Section {
                    Button {
                        Task { await test() }
                    } label: {
                        HStack {
                            Text("Test connection")
                            Spacer()
                            if testing { ProgressView() }
                        }
                    }
                    .disabled(testing || serverURL.isEmpty)
                    if let testStatus {
                        Text(testStatus).font(.caption)
                    }
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Save") {
                        settings.serverURL = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
                        settings.authToken = authToken
                        dismiss()
                    }
                    .bold()
                }
            }
            .onAppear {
                serverURL = settings.serverURL
                authToken = settings.authToken
            }
        }
    }

    private func test() async {
        testing = true
        defer { testing = false }
        let client = APIClient(
            serverURL: serverURL.trimmingCharacters(in: .whitespacesAndNewlines),
            authToken: authToken
        )
        do {
            _ = try await client.listConversations()
            testStatus = "Connected"
        } catch {
            testStatus = error.localizedDescription
        }
    }
}
