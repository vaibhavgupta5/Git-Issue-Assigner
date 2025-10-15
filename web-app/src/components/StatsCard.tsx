interface StatsCardProps {
  title: string;
  value: number;
  icon: string;
}

export function StatsCard({ title, value, icon }: StatsCardProps) {
  return (
    <div className="border-r-4 border-b-4 border-white p-6 bg-black hover:bg-gray-950 transition-colors">
      <div className="flex items-center justify-between mb-4">
        <span className="text-4xl">{icon}</span>
        <span className="text-5xl font-bold">{value}</span>
      </div>
      <div className="text-sm text-gray-400 font-mono uppercase">{title}</div>
    </div>
  );
}
