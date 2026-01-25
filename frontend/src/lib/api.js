// VITE_API_URL should be the full base path including /api (e.g., http://...elb.amazonaws.com/api)
// For local dev, default to http://localhost:8000/api
const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

// Debug: log the API base URL
console.log("API_BASE:", API_BASE);

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