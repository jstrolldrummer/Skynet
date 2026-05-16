import Foundation

struct Conversation: Identifiable, Codable, Hashable {
    let id: String
    var title: String
    let created_at: Double
    var updated_at: Double
}

struct Message: Identifiable, Codable, Hashable {
    let id: String
    let conversation_id: String
    let role: String
    var content: String
    let created_at: Double
}

struct ChatEvent: Codable {
    let type: String
    let content: String?
    let message_id: String?
}
