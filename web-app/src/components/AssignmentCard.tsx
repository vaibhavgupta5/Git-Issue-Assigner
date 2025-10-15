interface AssignmentCardProps {
  assignment: {
    issue_number: number;
    issue_title: string;
    issue_url: string;
    assigned_to: string;
    real_name: string;
    source_type: string;
    category: string;
    confidence: number;
    assignment_score: number;
    github_profile: string;
    github_assigned: boolean;
    timestamp: string;
  };
  index: number;
}

export function AssignmentCard({ assignment, index }: AssignmentCardProps) {
  const sourceIcon = assignment.source_type === 'Both' ? '👤+🤝' : 
                     assignment.source_type === 'Contributor' ? '👤' : '🤝';
  
  return (
    <div className="border-r-4 border-b-4 border-white p-6 bg-black hover:bg-gray-950 transition-colors">
      <div className="flex items-start justify-between gap-6">
        {/* Left: Assignment Number */}
        <div className="flex-shrink-0">
          <div className="w-12 h-12 border-r-2 border-b-2 border-white flex items-center justify-center">
            <span className="text-2xl font-bold">#{index}</span>
          </div>
        </div>

        {/* Middle: Issue Details */}
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-3">
            <a
              href={assignment.issue_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xl font-bold hover:text-gray-400 transition-colors"
            >
              Issue #{assignment.issue_number}: {assignment.issue_title}
            </a>
            {assignment.github_assigned && (
              <span className="px-2 py-1 text-xs bg-green-500/20 text-green-500 font-bold">
                ✓ ASSIGNED ON GITHUB
              </span>
            )}
          </div>

          <div className="flex flex-wrap gap-4 text-sm mb-4">
            <div className="flex items-center gap-2">
              <span className="text-gray-400">CATEGORY:</span>
              <span className="font-bold px-2 py-1 border border-white/30">{assignment.category}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-400">CONFIDENCE:</span>
              <span className="font-bold">{(assignment.confidence * 100).toFixed(0)}%</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-gray-400">SCORE:</span>
              <span className="font-bold">{assignment.assignment_score.toFixed(3)}</span>
            </div>
          </div>

          {/* Assigned Developer */}
          <div className="flex items-center gap-4 p-4 border border-white/20">
            <span className="text-2xl">{sourceIcon}</span>
            <div className="flex-1">
              <div className="font-bold text-lg">{assignment.real_name}</div>
              <a
                href={assignment.github_profile}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-gray-400 hover:text-white transition-colors"
              >
                @{assignment.assigned_to}
              </a>
            </div>
            <div className="text-right text-xs text-gray-400">
              {new Date(assignment.timestamp).toLocaleString()}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
