import { Bot, User } from "lucide-react";

interface ChatMessageProps {
  role: "user" | "assistant";
  content: string;
}

export function ChatMessage({ role, content }: ChatMessageProps) {
  const isUser = role === "user";

  return (
    <div className={`flex gap-3 animate-fade-in-up ${isUser ? "flex-row-reverse" : ""}`}>
      <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${
        isUser ? "bg-secondary" : "bg-primary/10 border border-primary/20"
      }`}>
        {isUser ? (
          <User className="h-4 w-4 text-foreground" />
        ) : (
          <Bot className="h-4 w-4 text-primary" />
        )}
      </div>
      <div className={`max-w-[75%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
        isUser
          ? "bg-secondary text-foreground"
          : "bg-card border border-border text-foreground"
      }`}>
        {content}
      </div>
    </div>
  );
}
