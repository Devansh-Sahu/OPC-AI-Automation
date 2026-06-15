"use client";

import { useAgentRunWebSocket } from "../lib/websocket";
import { useEffect, useRef } from "react";

const STEPS = ["analyze_repo", "retrieve_code", "plan_implementation", "generate_code", "run_tests", "review_code", "create_pr"];

export function AgentRunLive({ runId }: { runId: string }) {
  const { messages, status } = useAgentRunWebSocket(runId);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll terminal
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const currentStepIndex = messages.length > 0 
    ? STEPS.indexOf(messages[messages.length - 1].step) 
    : -1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between glass-card p-4 rounded-lg">
        <div className="flex items-center gap-3">
          <div className={`h-3 w-3 rounded-full ${status === 'connected' ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`}></div>
          <span className="font-mono text-sm">Connection: {status.toUpperCase()}</span>
        </div>
        <div className="font-mono text-sm text-muted-foreground">Run ID: {runId}</div>
      </div>

      {/* Progress Bar */}
      <div className="glass-card p-6 rounded-lg">
        <div className="flex justify-between mb-2">
          {STEPS.map((step, idx) => (
            <div key={step} className="flex flex-col items-center gap-2">
              <div className={`h-8 w-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors
                ${idx < currentStepIndex ? 'bg-green-500 text-white' : 
                  idx === currentStepIndex ? 'bg-ose-blue text-white animate-pulse' : 
                  'bg-muted text-muted-foreground'}`}>
                {idx + 1}
              </div>
              <span className="text-xs text-muted-foreground hidden md:block">
                {step.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')}
              </span>
            </div>
          ))}
        </div>
        <div className="relative mt-4 h-2 bg-muted rounded-full overflow-hidden">
          <div 
            className="absolute top-0 left-0 h-full bg-gradient-to-r from-ose-blue to-ose-cyan transition-all duration-500"
            style={{ width: `${Math.max(5, ((currentStepIndex + 1) / STEPS.length) * 100)}%` }}
          />
        </div>
      </div>

      {/* Terminal View */}
      <div className="bg-[#0a0a0f] border border-border rounded-lg p-4 font-mono text-sm h-96 overflow-y-auto shadow-inner">
        {messages.length === 0 ? (
          <div className="text-muted-foreground">Waiting for agent to start...</div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className="mb-2">
              <span className="text-muted-foreground">[{new Date(msg.timestamp).toLocaleTimeString()}]</span>{" "}
              <span className={
                msg.type === "error" ? "text-red-500" :
                msg.type === "step_started" ? "text-ose-cyan" :
                msg.type === "waiting_for_approval" ? "text-ose-purple font-bold" :
                "text-green-500"
              }>
                {msg.type.toUpperCase()}
              </span>{" "}
              <span className="text-gray-300">[{msg.step}]</span>{" "}
              <span className="text-white">{msg.message || ""}</span>
              
              {msg.type === "waiting_for_approval" && msg.pr_url && (
                <div className="mt-2 ml-8">
                  <a href={msg.pr_url} target="_blank" rel="noreferrer" className="text-ose-blue hover:underline">
                    👉 View Draft PR: {msg.pr_url}
                  </a>
                </div>
              )}
            </div>
          ))
        )}
        <div ref={logEndRef} />
      </div>
    </div>
  );
}
