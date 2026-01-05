import { useState } from "react";
import { ChevronDown, ChevronRight, BrainCircuit } from "lucide-react";

export function ReasoningAccordion({ content }) {
  const [isOpen, setIsOpen] = useState(false);

  if (!content) return null;

  return (
    <div className="my-2 border border-gray-200 rounded-md overflow-hidden bg-gray-50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 p-2 bg-gray-100 hover:bg-gray-200 transition-colors text-xs font-medium text-gray-600"
      >
        {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <BrainCircuit size={14} />
        Reasoning Process
      </button>
      {isOpen && (
        <div className="p-3 text-sm text-gray-600 font-mono whitespace-pre-wrap bg-white border-t border-gray-200">
          {content}
        </div>
      )}
    </div>
  );
}