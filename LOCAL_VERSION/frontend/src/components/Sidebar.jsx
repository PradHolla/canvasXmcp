import { MessageSquare, Trash2, Plus, MessageCircle, PanelLeftClose } from "lucide-react";

export function Sidebar({ threads, activeThreadId, onSelect, onDelete, onNew, isOpen, toggleSidebar }) {
  return (
    <div 
      className={`
        ${isOpen ? "w-64 translate-x-0" : "w-0 -translate-x-full opacity-0"} 
        bg-gray-900 text-white flex flex-col h-full flex-shrink-0 border-r border-gray-800 
        transition-all duration-300 ease-in-out overflow-hidden whitespace-nowrap
      `}
    >
      {/* Header / New Chat Button */}
      <div className="p-3 flex items-center justify-between gap-2">
        <button
          onClick={onNew}
          className="flex-1 flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-md border border-gray-700 transition-colors text-sm text-gray-200"
        >
          <Plus size={16} />
          <span>New chat</span>
        </button>
        
        <button 
          onClick={toggleSidebar}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-md transition-colors"
          title="Close sidebar"
        >
          <PanelLeftClose size={20} />
        </button>
      </div>

      {/* Scrollable List */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1 scrollbar-thin scrollbar-thumb-gray-700">
        <div className="text-xs font-medium text-gray-500 px-3 py-2 uppercase tracking-wider">
          History
        </div>

        {threads.length === 0 ? (
          <div className="text-gray-500 text-sm text-center mt-10 flex flex-col items-center gap-2">
            <MessageCircle size={24} className="opacity-20" />
            <span>No history yet</span>
          </div>
        ) : (
          threads.map((thread) => (
            <div
              key={thread.thread_id}
              onClick={() => onSelect(thread.thread_id)}
              className={`group flex items-center gap-3 p-3 text-sm rounded-md cursor-pointer transition-colors relative ${
                activeThreadId === thread.thread_id
                  ? "bg-gray-800 text-white"
                  : "text-gray-300 hover:bg-gray-800/50"
              }`}
            >
              <MessageSquare size={14} className="flex-shrink-0 text-gray-400" />
              <span className="truncate pr-6">
                {thread.title || "New Conversation"}
              </span>
              
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(thread.thread_id);
                }}
                className="absolute right-2 opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-400 transition-all"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))
        )}
      </div>
      
      {/* Footer */}
      <div className="p-3 border-t border-gray-800">
        <div className="flex items-center gap-3 px-3 py-2 rounded-md hover:bg-gray-800 cursor-pointer transition-colors">
          <div className="w-8 h-8 rounded bg-gradient-to-br from-purple-500 to-blue-600 flex items-center justify-center text-white font-bold text-xs">
            S
          </div>
          <div className="text-sm font-medium truncate">Student User</div>
        </div>
      </div>
    </div>
  );
}