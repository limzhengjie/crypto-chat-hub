import { MessageSquare, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface ChatSession {
  id: string;
  title: string;
  timestamp: string;
  preview: string;
}

interface ChatSidebarProps {
  sessions: ChatSession[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export function ChatSidebar({ sessions, activeId, onSelect, onNew, onDelete }: ChatSidebarProps) {
  return (
    <div className="flex flex-col h-full bg-card border-r border-border">
      <div className="p-4 border-b border-border">
        <Button onClick={onNew} variant="outline" className="w-full justify-start gap-2 text-sm">
          <Plus className="h-4 w-4" />
          New Chat
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-2 space-y-1">
        {sessions.length === 0 && (
          <div className="flex flex-col items-center justify-center h-32 text-muted-foreground text-xs text-center px-4">
            <MessageSquare className="h-8 w-8 mb-2 opacity-30" />
            No conversations yet. Start a new chat!
          </div>
        )}
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => onSelect(session.id)}
            className={`group w-full text-left rounded-lg p-3 transition-colors duration-150 ${
              activeId === session.id
                ? "bg-secondary border border-primary/20"
                : "hover:bg-secondary/50 border border-transparent"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground truncate">{session.title}</p>
                <p className="text-xs text-muted-foreground truncate mt-0.5">{session.preview}</p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(session.id);
                }}
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-destructive"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground mt-1 font-mono">{session.timestamp}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
