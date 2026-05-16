import Foundation

enum APIError: Error, LocalizedError {
    case badURL
    case httpError(Int, String)

    var errorDescription: String? {
        switch self {
        case .badURL: return "Invalid server URL"
        case .httpError(let code, let msg): return "HTTP \(code): \(msg)"
        }
    }
}

struct APIClient {
    let serverURL: String
    let authToken: String

    private func makeRequest(_ path: String, method: String = "GET", body: Data? = nil) throws -> URLRequest {
        let base = serverURL.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: base + path) else { throw APIError.badURL }
        var req = URLRequest(url: url)
        req.httpMethod = method
        if !authToken.isEmpty {
            req.setValue("Bearer \(authToken)", forHTTPHeaderField: "Authorization")
        }
        if let body {
            req.httpBody = body
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return req
    }

    func listConversations() async throws -> [Conversation] {
        let req = try makeRequest("/conversations")
        let (data, resp) = try await URLSession.shared.data(for: req)
        try checkOK(resp, data: data)
        return try JSONDecoder().decode([Conversation].self, from: data)
    }

    func createConversation(title: String) async throws -> Conversation {
        let body = try JSONEncoder().encode(["title": title])
        let req = try makeRequest("/conversations", method: "POST", body: body)
        let (data, resp) = try await URLSession.shared.data(for: req)
        try checkOK(resp, data: data)
        return try JSONDecoder().decode(Conversation.self, from: data)
    }

    func getMessages(conversationID: String) async throws -> [Message] {
        let req = try makeRequest("/conversations/\(conversationID)/messages")
        let (data, resp) = try await URLSession.shared.data(for: req)
        try checkOK(resp, data: data)
        return try JSONDecoder().decode([Message].self, from: data)
    }

    func deleteConversation(id: String) async throws {
        let req = try makeRequest("/conversations/\(id)", method: "DELETE")
        let (data, resp) = try await URLSession.shared.data(for: req)
        try checkOK(resp, data: data)
    }

    func streamChat(conversationID: String, content: String) -> AsyncThrowingStream<ChatEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let body = try JSONEncoder().encode([
                        "conversation_id": conversationID,
                        "content": content,
                    ])
                    let req = try makeRequest("/chat", method: "POST", body: body)
                    let (bytes, resp) = try await URLSession.shared.bytes(for: req)
                    if let http = resp as? HTTPURLResponse,
                       !(200..<300).contains(http.statusCode) {
                        continuation.finish(throwing: APIError.httpError(http.statusCode, "chat failed"))
                        return
                    }
                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let json = String(line.dropFirst(6))
                        guard let data = json.data(using: .utf8) else { continue }
                        if let event = try? JSONDecoder().decode(ChatEvent.self, from: data) {
                            continuation.yield(event)
                            if event.type == "done" || event.type == "error" { break }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    private func checkOK(_ resp: URLResponse, data: Data) throws {
        guard let http = resp as? HTTPURLResponse else { return }
        if !(200..<300).contains(http.statusCode) {
            let body = String(data: data, encoding: .utf8) ?? ""
            throw APIError.httpError(http.statusCode, body)
        }
    }
}
