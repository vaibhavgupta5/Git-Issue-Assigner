'use client';

import { useState } from 'react';

interface DeveloperCardProps {
  developer: {
    id: string;
    name: string;
    github_username: string;
    skills: string[];
    experience_level: string;
    max_capacity: number;
    workload: number;
    available: boolean;
    current_issues: number[];
    contributions: number;
    source_type: string;
    // Enhanced parameters
    recent_commits?: number;
    pr_count?: number;
    issue_count?: number;
    review_count?: number;
    recency_score?: number;
    activity_score?: number;
  };
}

export function DeveloperCard({ developer }: DeveloperCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  
  const sourceIcon = developer.source_type === 'Both' ? '👤+🤝' : 
                     developer.source_type === 'Contributor' ? '👤' : '🤝';
  
  const capacityPercent = (developer.workload / developer.max_capacity) * 100;
  
  return (
    <div className="border-r-4 border-b-4 border-white p-6 bg-black hover:bg-gray-950 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-2xl">{sourceIcon}</span>
          <div>
            <h3 className="font-bold text-lg">{developer.name}</h3>
            <a 
              href={`https://github.com/${developer.github_username}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-gray-400 hover:text-white transition-colors"
            >
              @{developer.github_username}
            </a>
          </div>
        </div>
        <div className="text-right">
          <div className={`px-3 py-1 text-xs font-bold ${
            developer.available ? 'bg-green-500/20 text-green-500' : 'bg-red-500/20 text-red-500'
          }`}>
            {developer.available ? 'AVAILABLE' : 'BUSY'}
          </div>
        </div>
      </div>

      {/* Experience & Source */}
      <div className="flex gap-3 mb-4 text-sm">
        <span className="px-2 py-1 border border-white/30 font-mono">
          {developer.experience_level}
        </span>
        <span className="px-2 py-1 border border-white/30 font-mono text-xs">
          {developer.source_type}
        </span>
      </div>

      {/* Capacity Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-400">CAPACITY</span>
          <span className="font-bold">{developer.workload}/{developer.max_capacity}</span>
        </div>
        <div className="h-2 bg-gray-800 border border-white/20">
          <div 
            className={`h-full transition-all ${
              capacityPercent < 50 ? 'bg-green-500' : 
              capacityPercent < 80 ? 'bg-yellow-500' : 'bg-red-500'
            }`}
            style={{ width: `${capacityPercent}%` }}
          />
        </div>
      </div>

      {/* Skills */}
      <div className="mb-4">
        <div className="text-xs text-gray-400 mb-2">SKILLS</div>
        <div className="flex flex-wrap gap-2">
          {developer.skills.slice(0, 5).map((skill, idx) => (
            <span key={idx} className="px-2 py-1 text-xs border border-white/20 font-mono">
              {skill}
            </span>
          ))}
          {developer.skills.length > 5 && (
            <span className="px-2 py-1 text-xs text-gray-400">
              +{developer.skills.length - 5}
            </span>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 mb-4 text-center text-sm">
        <div>
          <div className="text-gray-400 text-xs">CONTRIBUTIONS</div>
          <div className="font-bold text-xl">{developer.contributions}</div>
        </div>
        <div>
          <div className="text-gray-400 text-xs">ISSUES</div>
          <div className="font-bold text-xl">{developer.current_issues.length}</div>
        </div>
      </div>

      {/* Enhanced Stats */}
      {(developer.recent_commits !== undefined || developer.pr_count !== undefined) && (
        <div className="border-t-2 border-gray-800 pt-4 mb-4">
          <div className="text-xs text-gray-400 mb-3">RECENT ACTIVITY (6 MONTHS)</div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            {developer.recent_commits !== undefined && (
              <div className="flex items-center gap-2">
                <span>💻</span>
                <div>
                  <div className="text-gray-400">Commits</div>
                  <div className="font-bold">{developer.recent_commits}</div>
                </div>
              </div>
            )}
            {developer.pr_count !== undefined && (
              <div className="flex items-center gap-2">
                <span>🔀</span>
                <div>
                  <div className="text-gray-400">Pull Requests</div>
                  <div className="font-bold">{developer.pr_count}</div>
                </div>
              </div>
            )}
            {developer.review_count !== undefined && (
              <div className="flex items-center gap-2">
                <span>👀</span>
                <div>
                  <div className="text-gray-400">Reviews</div>
                  <div className="font-bold">{developer.review_count}</div>
                </div>
              </div>
            )}
            {developer.recency_score !== undefined && (
              <div className="flex items-center gap-2">
                <span>⚡</span>
                <div>
                  <div className="text-gray-400">Recency</div>
                  <div className="font-bold">{(developer.recency_score * 100).toFixed(0)}%</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Collapsible Detailed Analysis */}
      <div className="border-t-2 border-white/20">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="w-full py-3 flex items-center justify-between hover:bg-gray-900 transition-colors"
        >
          <span className="text-sm font-bold text-white">
            {showDetails ? '▼' : '▶'} DETAILED ANALYSIS
          </span>
          <span className="text-xs text-gray-400">
            {showDetails ? 'Hide' : 'Show'}
          </span>
        </button>

        {showDetails && (
          <div className="pb-4 space-y-4">
            {/* All Skills */}
            <div>
              <div className="text-xs text-gray-400 mb-2">📚 ALL SKILLS ({developer.skills.length})</div>
              <div className="flex flex-wrap gap-2">
                {developer.skills.map((skill, idx) => (
                  <span 
                    key={idx} 
                    className="px-2 py-1 text-xs border border-white/30 font-mono hover:border-blue-500 hover:text-blue-500 transition-colors"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>

            {/* Experience Breakdown */}
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <div className="text-gray-400 mb-1">📊 Experience Level</div>
                <div className="font-bold text-lg">{developer.experience_level}</div>
              </div>
              <div>
                <div className="text-gray-400 mb-1">⚙️ Max Capacity</div>
                <div className="font-bold text-lg">{developer.max_capacity} issues</div>
              </div>
            </div>

            {/* Activity Score */}
            {developer.activity_score !== undefined && (
              <div>
                <div className="text-gray-400 text-xs mb-2">🎯 Activity Score</div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-3 bg-gray-800 border border-white/20 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-green-500 to-blue-500"
                      style={{ width: `${Math.min(100, (developer.activity_score / 150) * 100)}%` }}
                    />
                  </div>
                  <span className="font-bold text-sm">{developer.activity_score}</span>
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Based on: Contributions + (PRs × 2) + (Reviews × 3)
                </div>
              </div>
            )}

            {/* Issue History */}
            {developer.current_issues.length > 0 && (
              <div>
                <div className="text-gray-400 text-xs mb-2">📋 Current Issues</div>
                <div className="flex flex-wrap gap-2">
                  {developer.current_issues.map((issueNum, idx) => (
                    <span 
                      key={idx}
                      className="px-2 py-1 text-xs bg-gray-900 border border-white/20 font-mono"
                    >
                      #{issueNum}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* GitHub Link */}
            <div className="pt-2 border-t border-gray-800">
              <a
                href={`https://github.com/${developer.github_username}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 text-xs font-mono flex items-center gap-2"
              >
                🔗 View Full GitHub Profile →
              </a>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
