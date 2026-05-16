import SwiftUI

struct ChatView: View {
    @Environment(Settings.self) var settings
    let conversation: Conversation

    @State private var messages: [Message] = []
    @State private var draft: String = ""
    @State private var streaming: String = ""
    @State private var sending: Bool = false
    @State private var error: String?

    private var client: APIClient {
        APIClient(serverURL: settings.serverURL, authToken: settings.authToken)
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(messages) { m in
                            MessageBubble(role: m.role, content: m.content).id(m.id)
                        }
                        if !streaming.isEmpty {
                            MessageBubble(role: "assistant", content: streaming).id("streaming")
                        }
                        if let error {
                            Text(error)
                                .font(.caption)
                                .foregroundStyle(.red)
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) { _, _ in
                    if let last = messages.last {
                        withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                    }
                }
                .onChange(of: streaming) { _, _ in
                    proxy.scrollTo("streaming", anchor: .bottom)
                }
            }
            Divider()
            HStack(alignment: .bottom) {
                TextField("Message", text: $draft, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                Button {
                    Task { await send() }
                } label: {
                    Image(systemName: "arrow.up.circle.fill").font(.title)
                }
                .disabled(sending || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding()
        }
        .navigationTitle(conversation.title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        do {
            messages = try await client.getMessages(conversationID: conversation.id)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draft = ""
        sending = true
        error = nil
        defer { sending = false }

        messages.append(Message(
            id: UUID().uuidString,
            conversation_id: conversation.id,
            role: "user",
            content: text,
            created_at: Date().timeIntervalSince1970
        ))
        streaming = ""

        do {
            for try await event in client.streamChat(conversationID: conversation.id, content: text) {
                switch event.type {
                case "delta":
                    if let c = event.content { streaming.append(c) }
                case "error":
                    error = event.content ?? "unknown error"
                case "done":
                    break
                default:
                    break
                }
            }
        } catch {
            self.error = error.localizedDescription
        }

        streaming = ""
        messages = (try? await client.getMessages(conversationID: conversation.id)) ?? messages
    }
}

struct MessageBubble: View {
    let role: String
    let content: String

    var body: some View {
        HStack {
            if role == "user" { Spacer(minLength: 40) }
            Text(content)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(role == "user" ? Color.accentColor.opacity(0.22) : Color.gray.opacity(0.15))
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .frame(maxWidth: .infinity, alignment: role == "user" ? .trailing : .leading)
            if role == "assistant" { Spacer(minLength: 40) }
        }
    }
}
