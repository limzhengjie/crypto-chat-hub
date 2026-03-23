import { Button } from "@/components/ui/button";
import { TrendingUp, TrendingDown } from "lucide-react";

interface CoinButtonProps {
  name: string;
  symbol: string;
  price: string;
  change: number;
  active: boolean;
  onClick: () => void;
}

export function CoinButton({ name, symbol, price, change, active, onClick }: CoinButtonProps) {
  const isPositive = change >= 0;

  return (
    <Button
      variant="coin"
      onClick={onClick}
      className={`flex flex-col items-start gap-1 h-auto py-3 px-4 min-w-[140px] ${
        active ? "border-primary/60 glow-green bg-crypto-surface-hover" : ""
      }`}
    >
      <div className="flex items-center gap-2 w-full">
        <span className="font-semibold text-sm">{symbol}</span>
        <span className="text-xs text-muted-foreground">{name}</span>
      </div>
      <div className="flex items-center justify-between w-full">
        <span className="font-mono text-sm">{price}</span>
        <span className={`flex items-center gap-0.5 text-xs font-mono ${isPositive ? "text-crypto-green" : "text-crypto-red"}`}>
          {isPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          {isPositive ? "+" : ""}{change.toFixed(2)}%
        </span>
      </div>
    </Button>
  );
}
