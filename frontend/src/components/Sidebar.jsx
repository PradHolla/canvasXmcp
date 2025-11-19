import { MessageSquare, Trash2, Plus } from "lucide-react";

export function Sidebar({ threads, activeThreadId, onSelect, onDelete, onNew }) {
  return (
    <div className="w-64 bg-gray-900 text-white flex flex-col h-full border-r border-gray-800">
      <div className="p-4 border-b border-gray-800">
        <h1 className="font-bold text-xl flex items-center gap-2 mb-4">
          🎓 Canvas AI
        </h1>
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg transition-colors"
        >
          <Plus size={16} /> New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {threads.map((thread) => (
          <div
            key={thread.thread_id}
            className={`group flex items-center justify-between p-3 rounded-lg cursor-pointer transition-colors ${
              activeThreadId === thread.thread_id
                ? "bg-gray-800"
                : "hover:bg-gray-800/50"
            }`}
            onClick={() => onSelect(thread.thread_id)}
          >
            <div className="flex items-center gap-3 overflow-hidden">
              <MessageSquare size={16} className="text-gray-400 flex-shrink-0" />
              <span className="truncate text-sm text-gray-300">
                {thread.title || "New Conversation"}
              </span>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete(thread.thread_id);
              }}
              className="opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}