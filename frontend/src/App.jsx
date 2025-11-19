import { useState, useEffect } from "react";
import { v4 as uuidv4 } from "uuid";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";
import { api } from "./lib/api";

function App() {
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);

  // Load threads on mount
  useEffect(() => {
    refreshThreads();
  }, []);

  const refreshThreads = async () => {
    try {
      const list = await api.getThreads();
      setThreads(list);
    } catch (e) {
      console.error("Failed to load threads", e);
    }
  };

  const handleNewChat = () => {
    const newId = uuidv4();
    const newThread = { thread_id: newId, title: "New Chat" };
    setThreads([newThread, ...threads]);
    setActiveThreadId(newId);
  };

  const handleDeleteThread = async (id) => {
    if (confirm("Delete this conversation?")) {
      await api.deleteThread(id);
      setThreads(threads.filter((t) => t.thread_id !== id));
      if (activeThreadId === id) setActiveThreadId(null);
    }
  };

  return (
    <div className="flex h-screen w-full bg-gray-50">
      <Sidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={setActiveThreadId}
        onNew={handleNewChat}
        onDelete={handleDeleteThread}
      />
      <ChatArea activeThreadId={activeThreadId} />
    </div>
  );
}

export default App;