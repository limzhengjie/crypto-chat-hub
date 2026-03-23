export interface CoinData {
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

function generateSparkline(base: number, volatility: number, positive: boolean): number[] {
  const points: number[] = [];
  let value = base;
  for (let i = 0; i < 24; i++) {
    value += (Math.random() - (positive ? 0.35 : 0.65)) * volatility;
    points.push(value);
  }
  return points;
}

export const COINS: CoinData[] = [
  {
    symbol: "BTC",
    name: "Bitcoin",
    price: "$67,432.18",
    change24h: 2.34,
    marketCap: "$1.32T",
    volume: "$28.4B",
    high24h: "$68,100.00",
    low24h: "$65,890.50",
    sparkline: generateSparkline(67000, 400, true),
  },
  {
    symbol: "ETH",
    name: "Ethereum",
    price: "$3,521.47",
    change24h: -1.12,
    marketCap: "$423.1B",
    volume: "$14.2B",
    high24h: "$3,610.00",
    low24h: "$3,480.20",
    sparkline: generateSparkline(3500, 30, false),
  },
  {
    symbol: "USDT",
    name: "Tether",
    price: "$1.0002",
    change24h: 0.01,
    marketCap: "$110.8B",
    volume: "$52.1B",
    high24h: "$1.0004",
    low24h: "$0.9998",
    sparkline: generateSparkline(1.0, 0.0003, true),
  },
  {
    symbol: "SOL",
    name: "Solana",
    price: "$172.84",
    change24h: 5.67,
    marketCap: "$76.3B",
    volume: "$3.8B",
    high24h: "$178.20",
    low24h: "$162.40",
    sparkline: generateSparkline(170, 4, true),
  },
  {
    symbol: "XRP",
    name: "Ripple",
    price: "$0.6234",
    change24h: -0.89,
    marketCap: "$34.1B",
    volume: "$1.2B",
    high24h: "$0.6380",
    low24h: "$0.6150",
    sparkline: generateSparkline(0.62, 0.008, false),
  },
];
