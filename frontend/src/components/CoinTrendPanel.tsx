import { TrendingUp, TrendingDown, Activity, DollarSign, BarChart3 } from "lucide-react";

interface CoinData {
  symbol: string;
  name: string;
  price: string;
  change24h: number;
  marketCap: string;
  volume: string;
  high24h: string;
  low24h: string;
  sparkline: number[];
}

interface CoinTrendPanelProps {
  coin: CoinData;
}

function MiniChart({ data, positive }: { data: number[]; positive: boolean }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const height = 48;
  const width = 200;
  const step = width / (data.length - 1);

  const points = data
    .map((v, i) => `${i * step},${height - ((v - min) / range) * height}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-12" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={positive ? "hsl(142 72% 50%)" : "hsl(0 72% 55%)"}
        strokeWidth="2"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function CoinTrendPanel({ coin }: CoinTrendPanelProps) {
  const isPositive = coin.change24h >= 0;

  return (
    <div className="animate-fade-in-up rounded-xl border border-border bg-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-secondary flex items-center justify-center">
            <span className="font-mono font-bold text-sm text-primary">{coin.symbol.charAt(0)}</span>
          </div>
          <div>
            <h3 className="font-semibold text-foreground">{coin.name}</h3>
            <span className="text-xs text-muted-foreground font-mono">{coin.symbol}</span>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono font-semibold text-lg text-foreground">{coin.price}</p>
          <p className={`text-sm font-mono flex items-center gap-1 justify-end ${isPositive ? "text-crypto-green" : "text-crypto-red"}`}>
            {isPositive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            {isPositive ? "+" : ""}{coin.change24h.toFixed(2)}%
          </p>
        </div>
      </div>

      <div className="rounded-lg bg-secondary/50 p-3">
        <MiniChart data={coin.sparkline} positive={isPositive} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2 rounded-lg bg-secondary/40 p-3">
          <DollarSign className="h-4 w-4 text-muted-foreground" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Market Cap</p>
            <p className="font-mono text-sm text-foreground">{coin.marketCap}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-secondary/40 p-3">
          <BarChart3 className="h-4 w-4 text-muted-foreground" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Volume 24h</p>
            <p className="font-mono text-sm text-foreground">{coin.volume}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-secondary/40 p-3">
          <Activity className="h-4 w-4 text-crypto-green" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">24h High</p>
            <p className="font-mono text-sm text-foreground">{coin.high24h}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-secondary/40 p-3">
          <Activity className="h-4 w-4 text-crypto-red" />
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground">24h Low</p>
            <p className="font-mono text-sm text-foreground">{coin.low24h}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
