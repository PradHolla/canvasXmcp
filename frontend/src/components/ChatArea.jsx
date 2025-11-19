import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Loader2, Hammer } from "lucide-react";
import { ReasoningAccordion } from "./ReasoningAccordion";
import { api } from "../lib/api";

export function ChatArea({ activeThreadId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const scrollRef = useRef(null);

  // Load history when thread changes
  useEffect(() => {
    if (activeThreadId) {
      setLoading(true);
      api.getMessages(activeThreadId)
        .then(setMessages)
        .finally(() => setLoading(false));
    } else {
      setMessages([]);
    }
  }, [activeThreadId]);

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim() || !activeThreadId) return;

    const userMsg = { type: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Placeholder for AI response
    setMessages((prev) => [
      ...prev,
      { type: "assistant", content: "", reasoning: "" },
    ]);

    try {
      await api.chatStream(userMsg.content, activeThreadId, (chunk) => {
        if (chunk.type === "content") {
          setMessages((prev) => {
            const last = { ...prev[prev.length - 1] };
            last.content += chunk.text;
            return [...prev.slice(0, -1), last];
          });
        } else if (chunk.type === "reasoning") {
          setMessages((prev) => {
            const last = { ...prev[prev.length - 1] };
            last.reasoning = (last.reasoning || "") + chunk.text;
            return [...prev.slice(0, -1), last];
          });
        } else if (chunk.type === "tool_start") {
          setActiveTool(chunk.tool);
        } else if (chunk.type === "tool_end") {
          setActiveTool(null);
        }
      });
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
      setActiveTool(null);
    }
  };

  if (!activeThreadId) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50">
        <div className="text-center space-y-4 text-gray-500">
          <h2 className="text-2xl font-bold">Welcome to Canvas AI</h2>
          <p>Select a conversation or start a new one.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-screen bg-white">
      {/* Messages Area */}
      <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-6">
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex w-full ${
              msg.type === "user" ? "justify-end" : "justify-start"
            }`}
          >
            <div
              className={`max-w-3xl rounded-2xl px-6 py-4 ${
                msg.type === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-gray-100 text-gray-900"
              }`}
            >
              {msg.type === "assistant" && msg.reasoning && (
                <ReasoningAccordion content={msg.reasoning} />
              )}
              
              <div className="prose prose-sm max-w-none dark:prose-invert">
                {msg.content ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                ) : (
                  // Show spinner if content is empty (waiting for reasoning)
                  loading && !msg.reasoning && <Loader2 className="animate-spin" size={20}/>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Tool Indicator */}
        {activeTool && (
          <div className="flex justify-center">
            <div className="flex items-center gap-2 bg-amber-100 text-amber-800 px-3 py-1 rounded-full text-xs font-medium animate-pulse">
              <Hammer size={12} />
              Using tool: {activeTool}...
            </div>
          </div>
        )}
        
        <div ref={scrollRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-gray-200 bg-white">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto relative">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your assignments, grades, or courses..."
            className="w-full bg-gray-100 text-gray-900 rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="absolute right-2 top-2 p-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {loading ? <Loader2 className="animate-spin" size={18} /> : <Send size={18} />}
          </button>
        </form>
        <div className="text-center mt-2">
            <p className="text-xs text-gray-400">AI can make mistakes. Check important info.</p>
        </div>
      </div>
    </div>
  );
}