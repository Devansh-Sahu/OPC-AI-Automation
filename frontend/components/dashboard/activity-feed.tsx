import { useEffect, useState } from "react";
import { api } from "../../lib/api";

export function ActivityFeed() {
  const [runs, setRuns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const data = await api.get("/api/agent-runs?limit=5");
        setRuns(data.items || data || []);
      } catch (error) {
        console.error("Failed to fetch agent runs", error);
      } finally {
        setLoading(false);
      }
    };

    fetchRuns();
    const interval = setInterval(fetchRuns, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="glass-card p-6 rounded-xl border border-border h-[400px] overflow-hidden flex flex-col">
      <h3 className="text-xl font-bold mb-4 flex items-center gap-2">
        <span className="text-ose-cyan">⚡</span> Live Activity
      </h3>
      
      {loading ? (
        <div className="flex-1 flex items-center justify-center text-muted-foreground">Loading activity...</div>
      ) : runs.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground text-sm">
          <span className="text-4xl mb-2">💤</span>
          <p>No recent activity.</p>
          <p>Waiting for discovery agent to find issues...</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-4 pr-2 custom-scrollbar">
          {runs.map((run: any) => (
            <div key={run.id} className="p-3 rounded-lg bg-background/50 border border-border/50 text-sm">
              <div className="flex justify-between items-start mb-1">
                <span className="font-semibold text-primary">{run.agent_name}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${
                  run.status === 'COMPLETED' ? 'bg-green-500/20 text-green-500' :
                  run.status === 'FAILED' ? 'bg-red-500/20 text-red-500' :
                  'bg-yellow-500/20 text-yellow-500'
                }`}>
                  {run.status}
                </span>
              </div>
              <p className="text-muted-foreground">{run.target_identifier || 'Analyzing repository...'}</p>
              <div className="mt-2 text-xs text-muted-foreground/60">
                {new Date(run.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
