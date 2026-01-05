import { useState, useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, Loader2, Hammer, Calendar, GraduationCap, Bell, PanelLeftOpen } from "lucide-react";
import { ReasoningAccordion } from "./ReasoningAccordion";
import { api } from "../lib/api";

const STARTER_PROMPTS = [
  {
    icon: <Calendar className="w-5 h-5 text-blue-500" />,
    title: "Upcoming Deadlines",
    prompt: "What assignments are due this week?"
  },
  {
    icon: <GraduationCap className="w-5 h-5 text-emerald-500" />,
    title: "Check Grades",
    prompt: "Show me my current grades in all courses."
  },
  {
    icon: <Bell className="w-5 h-5 text-amber-500" />,
    title: "Recent Updates",
    prompt: "Summarize the announcements from the last 7 days."
  }
];

function WelcomeScreen({ onSelectPrompt }) {
  return (
    <div className="flex flex-col items-center justify-center w-full max-w-3xl space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col items-center space-y-4">
        <div className="w-12 h-12 bg-gray-800 rounded-xl flex items-center justify-center shadow-lg">
           <span className="text-white font-bold text-xl">C</span>
        </div>
        <h2 className="text-2xl font-semibold text-gray-100">How can I help you today?</h2>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 w-full px-4">
        {STARTER_PROMPTS.map((item, idx) => (
          <button
            key={idx}
            onClick={() => onSelectPrompt(item.prompt)}
            className="flex flex-col items-start p-4 bg-gray-900 border border-gray-800 hover:bg-gray-800 hover:border-gray-700 hover:shadow-md rounded-xl transition-all text-left duration-200"
          >
            <div className="mb-3 p-2 bg-gray-800 rounded-lg">{item.icon}</div>
            <span className="text-sm font-medium text-gray-300">{item.title}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatArea({ activeThreadId, onMessageSent, sidebarOpen, toggleSidebar }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [activeTool, setActiveTool] = useState(null);
  const scrollRef = useRef(null);

  useEffect(() => {
    if (activeThreadId) {
      api.getMessages(activeThreadId)
        .then(data => setMessages(data || []))
        .catch(() => setMessages([]));
    }
  }, [activeThreadId]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, activeTool, loading]);

  const handleSend = async (text) => {
    if (!text.trim() || !activeThreadId) return;

    const userMsg = { type: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setMessages((prev) => [...prev, { type: "assistant", content: "", reasoning: "" }]);

    try {
      let isFirstChunk = true;
      await api.chatStream(text, activeThreadId, (chunk) => {
        if (isFirstChunk && onMessageSent) {
             onMessageSent();
             isFirstChunk = false;
        }
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
      setMessages(prev => [...prev.slice(0, -1), { type: "assistant", content: "❌ Error connecting to server." }]);
    } finally {
      setLoading(false);
      setActiveTool(null);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    handleSend(input);
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full bg-gray-950 relative">
      
      {/* Sidebar Toggle (Visible when sidebar closed) */}
      {!sidebarOpen && (
        <div className="absolute top-4 left-4 z-10">
          <button 
            onClick={toggleSidebar}
            className="p-2 text-gray-400 hover:text-gray-100 hover:bg-gray-900 rounded-md transition-colors"
            title="Open Sidebar"
          >
            <PanelLeftOpen size={24} />
          </button>
        </div>
      )}

      {/* Messages Area (Flex-1 takes all available space) */}
      <div className="flex-1 overflow-y-auto scrollbar-thin scrollbar-thumb-gray-200">
        {isEmpty ? (
          // Centering Container
          <div className="h-full flex flex-col items-center justify-center p-4">
             <WelcomeScreen onSelectPrompt={handleSend} />
          </div>
        ) : (
          // Conversation Flow
          <div className="flex flex-col items-center w-full py-4 md:py-8 space-y-6">
            {messages.map((msg, idx) => (
              <div key={idx} className="w-full max-w-3xl px-4">
                <div className="flex gap-4">
                  {/* Avatar */}
                  <div className={`w-8 h-8 rounded-sm flex items-center justify-center flex-shrink-0 mt-1 ${msg.type === "user" ? "bg-gray-700" : "bg-emerald-600"}`}>
                    <span className="text-white text-xs font-medium">{msg.type === "user" ? "U" : "AI"}</span>
                  </div>
                  
                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="font-semibold text-sm mb-1 text-gray-100">
                        {msg.type === "user" ? "You" : "Canvas AI"}
                    </div>
                    
                    {msg.type === "assistant" && msg.reasoning && (
                      <ReasoningAccordion content={msg.reasoning} />
                    )}
                    
                    <div className="prose prose-sm max-w-none text-gray-200 leading-relaxed">
                      {msg.content ? (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                      ) : (
                        loading && !msg.reasoning && <Loader2 className="animate-spin text-gray-400" size={16} />
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {/* Tool Indicator */}
            {activeTool && (
              <div className="flex items-center gap-2 text-gray-400 text-sm bg-gray-900 px-4 py-2 rounded-full border border-gray-800 animate-pulse">
                <Hammer size={14} /> 
                <span>Using tool: <span className="font-mono text-blue-400">{activeTool}</span>...</span>
              </div>
            )}
            <div ref={scrollRef} />
          </div>
        )}
      </div>

      {/* Input Area (Fixed at bottom, naturally stacked) */}
      <div className="flex-none w-full bg-gray-950 p-4 border-t border-gray-800">
        <div className="max-w-3xl mx-auto">
          <form onSubmit={handleSubmit} className="relative flex items-center rounded-2xl border border-gray-700 shadow-sm bg-gray-900 focus-within:border-gray-600 focus-within:ring-1 focus-within:ring-gray-600 transition-all">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Message Canvas AI..."
              className="flex-1 bg-transparent text-gray-100 pl-4 pr-12 py-3.5 focus:outline-none text-sm placeholder:text-gray-500"
              disabled={loading}
              autoFocus
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className={`absolute right-2 p-1.5 rounded-lg transition-all ${input.trim() ? "bg-white text-black hover:bg-gray-200" : "bg-gray-800 text-gray-600"}`}
            >
              {loading ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />}
            </button>
          </form>
          <p className="text-center text-xs text-gray-500 mt-2">
            Canvas AI can make mistakes. Check important assignments in Canvas.
          </p>
        </div>
      </div>
    </div>
  );
}