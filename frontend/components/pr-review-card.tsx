"use client";

interface PRReviewCardProps {
  pr: {
    title: string;
    repo: string;
    complexity_tier: string;
    testResults: { passed: boolean; count: number; coverage: string };
    aiReview: {
      critical_issues: string[];
      major_issues: string[];
      minor_suggestions: string[];
      summary: string;
    };
    diffPreview: string;
  };
  onApprove: () => void;
  onReject: () => void;
}

export function PRReviewCard({ pr, onApprove, onReject }: PRReviewCardProps) {
  const isCritical = pr.aiReview.critical_issues.length > 0;

  return (
    <div className="glass-card rounded-xl overflow-hidden border border-border">
      {/* Header */}
      <div className="p-6 border-b border-border flex justify-between items-start bg-[#0a0a0f]/50">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <span className="text-sm font-mono text-muted-foreground">{pr.repo}</span>
            <span className={`px-2 py-0.5 rounded text-xs font-bold 
              ${pr.complexity_tier === 'SENIOR' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/50' :
                pr.complexity_tier === 'STAFF' ? 'bg-red-500/20 text-red-400 border border-red-500/50' :
                'bg-ose-purple/20 text-ose-purple border border-ose-purple/50'}`}>
              {pr.complexity_tier}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-white">{pr.title}</h2>
        </div>
        <div className="flex gap-3">
          <button onClick={onReject} className="px-4 py-2 rounded-md font-medium text-red-400 bg-red-500/10 hover:bg-red-500/20 border border-red-500/30 transition-colors">
            Reject
          </button>
          <button onClick={onApprove} className="px-6 py-2 rounded-md font-bold text-white bg-green-500 hover:bg-green-400 hover:shadow-[0_0_15px_rgba(34,197,94,0.5)] transition-all">
            APPROVE & SUBMIT
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 p-6">
        {/* Left Column: Stats & Review */}
        <div className="md:col-span-1 space-y-6">
          
          {/* Test Results */}
          <div className="space-y-2">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Test Suite</h3>
            <div className={`p-4 rounded-lg border flex items-center justify-between ${pr.testResults.passed ? 'bg-green-500/10 border-green-500/30 text-green-400' : 'bg-red-500/10 border-red-500/30 text-red-400'}`}>
              <div className="flex items-center gap-2">
                <span>{pr.testResults.passed ? '✅' : '❌'}</span>
                <span className="font-bold">{pr.testResults.passed ? 'PASSED' : 'FAILED'}</span>
              </div>
              <div className="text-sm text-right">
                <div>{pr.testResults.count} tests</div>
                <div className="text-xs opacity-75">{pr.testResults.coverage} coverage</div>
              </div>
            </div>
          </div>

          {/* AI Review */}
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">AI Review Notes</h3>
            <p className="text-sm text-gray-300 italic">"{pr.aiReview.summary}"</p>
            
            {isCritical && (
              <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
                <h4 className="text-red-400 text-xs font-bold mb-1">CRITICAL ISSUES (DO NOT MERGE)</h4>
                <ul className="list-disc list-inside text-xs text-red-300 space-y-1">
                  {pr.aiReview.critical_issues.map((i, idx) => <li key={idx}>{i}</li>)}
                </ul>
              </div>
            )}
            
            {pr.aiReview.major_issues.length > 0 && (
              <div className="p-3 bg-orange-500/10 border border-orange-500/30 rounded-lg">
                <h4 className="text-orange-400 text-xs font-bold mb-1">MAJOR ISSUES</h4>
                <ul className="list-disc list-inside text-xs text-orange-300 space-y-1">
                  {pr.aiReview.major_issues.map((i, idx) => <li key={idx}>{i}</li>)}
                </ul>
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Diff Preview */}
        <div className="md:col-span-2">
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-2">Code Changes</h3>
          <div className="bg-[#0a0a0f] border border-border rounded-lg p-4 font-mono text-xs overflow-x-auto">
            <pre>
              {pr.diffPreview.split('\n').map((line, idx) => (
                <div key={idx} className={
                  line.startsWith('+') ? "text-green-400 bg-green-500/10" : 
                  line.startsWith('-') ? "text-red-400 bg-red-500/10" : 
                  "text-gray-400"
                }>
                  {line}
                </div>
              ))}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
