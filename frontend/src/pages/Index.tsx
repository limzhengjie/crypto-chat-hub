import { useState, useRef, useEffect } from "react";
import { Send, PanelLeftClose, PanelLeft, Zap, Download, Share2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ChatSidebar, type ChatSession } from "@/components/ChatSidebar";
import { ChatMessage } from "@/components/ChatMessage";
import { CoinButton } from "@/components/CoinButton";
import { CoinTrendPanel } from "@/components/CoinTrendPanel";
import { COINS } from "@/lib/cryptoData";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const QUICK_ACTIONS = [
  "What's happening with Ethereum right now?",
  "Compare ETH vs SOL as investments",
  "What are the biggest risks for ETH holders?",
  "Generate a quick BTC market summary",
];

const SAMPLE_RESPONSES: Record<string, string> = {
  default:
    "That's a great crypto question! While I'm a demo interface, in a full version I'd connect to real-time market data and AI to give you detailed analysis. Try clicking on a coin above to see its trends!",
  btc: "Bitcoin is the original cryptocurrency, created in 2009 by Satoshi Nakamoto. It uses proof-of-work consensus and has a fixed supply of 21 million coins. BTC is often called 'digital gold' due to its store-of-value properties.",
  eth: "Ethereum is a decentralized platform that enables smart contracts and dApps. After 'The Merge' in 2022, it transitioned to proof-of-stake, reducing energy consumption by ~99.95%. ETH powers the largest DeFi and NFT ecosystems.",
  sol: "Solana is known for its high throughput — processing up to 65,000 TPS with sub-second finality. Its proof-of-history consensus mechanism makes it popular for DeFi, NFTs, and high-frequency trading applications.",
  xrp: "XRP is designed for fast, low-cost international payments. RippleNet connects banks and payment providers globally. Transactions settle in 3-5 seconds with minimal fees, making it ideal for cross-border transfers.",
  usdt: "Tether (USDT) is the largest stablecoin by market cap, pegged 1:1 to the US dollar. It's widely used as a trading pair and for moving value between exchanges without exposure to crypto volatility.",
};

export default function Index() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessions, setSessions] = useState<ChatSession[]>([
    {
      id: "1",
      title: "Bitcoin price analysis",
      timestamp: "Today, 2:30 PM",
      preview: "What's the current BTC outlook?",
    },
    {
      id: "2",
      title: "ETH staking rewards",
      timestamp: "Yesterday",
      preview: "How much can I earn staking ETH?",
    },
  ]);
  const [activeSession, setActiveSession] = useState<string | null>("1");
  const [messages, setMessages] = useState<Message[]>([
    { role: "assistant", content: "Hey! I'm your crypto assistant. Ask me anything about cryptocurrencies, or tap a coin above to see its latest trends. 🚀" },
  ]);
  const [input, setInput] = useState("");
  const [activeCoin, setActiveCoin] = useState<string | null>(null);
  const [isTyping, setIsTyping] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const handleSend = () => {
    if (!input.trim()) return;
    const userMessage = input;
    setInput("");
    sendMessage(userMessage);
  };

  const handleNewChat = () => {
    const id = Date.now().toString();
    setSessions((prev) => [
      { id, title: "New conversation", timestamp: "Just now", preview: "..." },
      ...prev,
    ]);
    setActiveSession(id);
    setMessages([
      { role: "assistant", content: "Hey! I'm your crypto assistant. Ask me anything about cryptocurrencies, or tap a coin above to see its latest trends. 🚀" },
    ]);
    setActiveCoin(null);
  };

  const handleDeleteSession = (id: string) => {
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeSession === id) {
      setActiveSession(null);
    }
  };

  const sendMessage = (rawMessage: string) => {
    const userMessage = rawMessage.trim();
    if (!userMessage) return;

    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsTyping(true);

    const lower = userMessage.toLowerCase();
    let responseKey = "default";
    if (lower.includes("btc") || lower.includes("bitcoin")) responseKey = "btc";
    else if (lower.includes("eth") || lower.includes("ethereum")) responseKey = "eth";
    else if (lower.includes("sol") || lower.includes("solana")) responseKey = "sol";
    else if (lower.includes("xrp") || lower.includes("ripple")) responseKey = "xrp";
    else if (lower.includes("usdt") || lower.includes("tether")) responseKey = "usdt";

    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: SAMPLE_RESPONSES[responseKey] },
      ]);
      setIsTyping(false);
    }, 800 + Math.random() * 600);
  };

  const selectedCoinData = activeCoin ? COINS.find((c) => c.symbol === activeCoin) : null;

  const handleQuickAction = (prompt: string) => {
    setInput("");
    sendMessage(prompt);
  };

  const buildReportMarkdown = () => {
    const now = new Date().toISOString();
    const coinSection = selectedCoinData
      ? [
          "## Selected Coin Snapshot",
          `- Token: ${selectedCoinData.name} (${selectedCoinData.symbol})`,
          `- Price: ${selectedCoinData.price}`,
          `- 24h Change: ${selectedCoinData.change24h.toFixed(2)}%`,
          `- Market Cap: ${selectedCoinData.marketCap}`,
          `- Volume (24h): ${selectedCoinData.volume}`,
          `- 24h Range: ${selectedCoinData.low24h} -> ${selectedCoinData.high24h}`,
          "",
        ].join("\n")
      : "## Selected Coin Snapshot\n- No coin selected\n";

    const transcript = messages
      .map((message, i) => `### ${i + 1}. ${message.role === "user" ? "User" : "Assistant"}\n${message.content}`)
      .join("\n\n");

    return [
      "# CryptoChat Session Report",
      "",
      `- Generated at: ${now}`,
      `- Session ID: ${activeSession ?? "none"}`,
      "",
      coinSection,
      "## Conversation Transcript",
      transcript || "- No messages yet",
      "",
      "> Note: Demo mode report. Integrate backend AI + live APIs for production accuracy.",
      "",
    ].join("\n");
  };

  const handleExportReport = () => {
    setIsExporting(true);
    const markdown = buildReportMarkdown();
    const fileName = `cryptochat-report-${Date.now()}.md`;
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = fileName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    setIsExporting(false);
  };

  const handleShareReport = async () => {
    const markdown = buildReportMarkdown();
    const sharePayload = {
      title: "CryptoChat Session Report",
      text: markdown,
    };

    try {
      if (navigator.share) {
        await navigator.share(sharePayload);
        return;
      }

      await navigator.clipboard.writeText(markdown);
    } catch (_error) {
      // User may cancel share dialog; fallback to no-op in demo mode.
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <div
        className={`transition-all duration-300 ease-out ${
          sidebarOpen ? "w-72" : "w-0"
        } overflow-hidden shrink-0`}
      >
        <ChatSidebar
          sessions={sessions}
          activeId={activeSession}
          onSelect={setActiveSession}
          onNew={handleNewChat}
          onDelete={handleDeleteSession}
        />
      </div>

      {/* Main */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <header className="h-14 border-b border-border flex items-center px-4 gap-3 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="h-8 w-8"
          >
            {sidebarOpen ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeft className="h-4 w-4" />}
          </Button>
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-primary" />
            <h1 className="font-semibold text-foreground tracking-tight">CryptoChat</h1>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handleExportReport}
            disabled={isExporting}
            className="ml-auto"
          >
            <Download className="h-4 w-4 mr-1" />
            Export Report
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={handleShareReport}>
            <Share2 className="h-4 w-4 mr-1" />
            Share
          </Button>
          <span className="text-xs font-mono text-muted-foreground">Live Market Data</span>
        </header>

        {/* Coin Bar */}
        <div className="border-b border-border px-4 py-3 overflow-x-auto scrollbar-thin">
          <div className="flex gap-2">
            {COINS.map((coin) => (
              <CoinButton
                key={coin.symbol}
                name={coin.name}
                symbol={coin.symbol}
                price={coin.price}
                change={coin.change24h}
                active={activeCoin === coin.symbol}
                onClick={() => setActiveCoin(activeCoin === coin.symbol ? null : coin.symbol)}
              />
            ))}
          </div>
        </div>

        {/* Chat Area */}
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
            {/* Trend Panel */}
            {selectedCoinData && (
              <CoinTrendPanel coin={selectedCoinData} />
            )}

            {/* Messages */}
            {messages.map((msg, i) => (
              <ChatMessage key={i} role={msg.role} content={msg.content} />
            ))}

            {isTyping && (
              <div className="flex gap-3 animate-fade-in-up">
                <div className="h-8 w-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center">
                  <Zap className="h-4 w-4 text-primary animate-pulse" />
                </div>
                <div className="bg-card border border-border rounded-xl px-4 py-3">
                  <div className="flex gap-1">
                    <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "150ms" }} />
                    <span className="h-2 w-2 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-border p-4 shrink-0">
          <div className="max-w-3xl mx-auto">
            <div className="mb-3 flex flex-wrap gap-2">
              {QUICK_ACTIONS.map((action) => (
                <Button
                  key={action}
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => handleQuickAction(action)}
                >
                  {action}
                </Button>
              ))}
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex gap-2"
            >
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask anything about crypto..."
                className="flex-1 rounded-xl border border-border bg-card px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary/40 transition-all"
              />
              <Button
                type="submit"
                size="icon"
                disabled={!input.trim()}
                className="h-11 w-11 rounded-xl shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            </form>
            <p className="text-[10px] text-muted-foreground text-center mt-2">
              Demo mode — responses are simulated. Connect an AI backend for real-time analysis.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
