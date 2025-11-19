import { useState, useEffect, useCallback } from "react";
import { v4 as uuidv4 } from "uuid";
import { Sidebar } from "./components/Sidebar";
import { ChatArea } from "./components/ChatArea";
import { api } from "./lib/api";

function App() {
  const [threads, setThreads] = useState([]);
  const [activeThreadId, setActiveThreadId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Load threads on mount
  useEffect(() => {
    refreshThreads().then((loadedThreads) => {
      startNewChat();
    });
  }, []);

  const refreshThreads = useCallback(async () => {
    try {
      const list = await api.getThreads();
      setThreads(list);
      return list;
    } catch (e) {
      console.error("Failed to load threads", e);
      return [];
    }
  }, []);

  const startNewChat = () => {
    const newId = uuidv4();
    setActiveThreadId(newId);
  };

  const handleDeleteThread = async (id) => {
    if (confirm("Delete this conversation?")) {
      await api.deleteThread(id);
      setThreads((prev) => prev.filter((t) => t.thread_id !== id));
      if (activeThreadId === id) startNewChat();
    }
  };

  return (
    <div className="flex h-screen w-full bg-white overflow-hidden">
      <Sidebar
        threads={threads}
        activeThreadId={activeThreadId}
        onSelect={setActiveThreadId}
        onNew={startNewChat}
        onDelete={handleDeleteThread}
        isOpen={sidebarOpen}
        toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
      />
      
      <main className="flex-1 flex flex-col h-full min-w-0 relative transition-all duration-300">
        <ChatArea 
          activeThreadId={activeThreadId} 
          onMessageSent={refreshThreads}
          sidebarOpen={sidebarOpen}
          toggleSidebar={() => setSidebarOpen(!sidebarOpen)}
        />
      </main>
    </div>
  );
}

export default App;