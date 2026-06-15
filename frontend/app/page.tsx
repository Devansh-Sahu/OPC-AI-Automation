"use client";

import { useEffect, useState } from "react";
import { api, DashboardStats } from "../lib/api";
import { ActivityFeed } from "../components/dashboard/activity-feed";
import { QuickActions } from "../components/dashboard/quick-actions";

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);

  useEffect(() => {
    // Mock data for dev since backend is not fully seeded
    setStats({
      total_issues_found: 142,
      draft_prs_created: 18,
      prs_merged: 5,
      success_rate_percent: 82.5,
      active_agent_runs: 3,
      total_cost_usd: 0.00
    });
  }, []);

  if (!stats) return <div className="p-8 text-ose-cyan">Loading dashboard...</div>;

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-500">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2">
            OpenSource <span className="gradient-text">AI Engineer</span>
          </h1>
          <p className="text-muted-foreground text-lg">
            Autonomous Staff-level Engineering Dashboard
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="h-3 w-3 rounded-full bg-green-500 animate-pulse-slow"></div>
          <span className="text-sm font-medium text-green-500">System Online</span>
        </div>
      </div>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <KpiCard title="Total Issues Scored" value={stats.total_issues_found} icon="🔍" trend="+12 this week" />
        <KpiCard title="Draft PRs Created" value={stats.draft_prs_created} icon="🚀" trend="+3 this week" />
        <KpiCard title="PRs Merged" value={stats.prs_merged} icon="🎉" trend="+1 this week" />
        <KpiCard title="Success Rate" value={`${stats.success_rate_percent}%`} icon="📈" />
        <KpiCard title="Active Agents" value={stats.active_agent_runs} icon="🤖" className="border-ose-cyan/50" />
        <KpiCard title="Total Cost" value={`₹${stats.total_cost_usd.toFixed(2)}`} icon="💰" className="border-green-500/50" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div className="lg:col-span-2">
          <ActivityFeed />
        </div>
        <div>
          <QuickActions />
        </div>
      </div>
    </div>
  );
}

function KpiCard({ title, value, icon, trend, className = "" }: any) {
  return (
    <div className={`glass-card p-6 rounded-xl hover:scale-[1.02] transition-transform duration-300 ${className}`}>
      <div className="flex justify-between items-start mb-4">
        <h3 className="text-muted-foreground font-medium">{title}</h3>
        <span className="text-2xl">{icon}</span>
      </div>
      <div className="text-4xl font-bold text-foreground mb-2">{value}</div>
      {trend && <div className="text-sm text-ose-cyan">{trend}</div>}
    </div>
  );
}
