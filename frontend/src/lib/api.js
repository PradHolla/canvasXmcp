const API_BASE = "http://localhost:8000/api";

export const api = {
  getThreads: async () => {
    const res = await fetch(`${API_BASE}/threads`);
    return res.json();
  },

  getMessages: async (threadId) => {
    const res = await fetch(`${API_BASE}/threads/${threadId}/messages`);
    return res.json();
  },

  deleteThread: async (threadId) => {
    await fetch(`${API_BASE}/threads/${threadId}`, { method: "DELETE" });
  },

  chatStream: async (message, threadId, onChunk) => {
    const response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, thread_id: threadId }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n\n");

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const dataStr = line.slice(6);
          if (dataStr === "[DONE]") return;
          
          try {
            const data = JSON.parse(dataStr);
            onChunk(data);
          } catch (e) {
            console.error("Error parsing chunk", e);
          }
        }
      }
    }
  }
};