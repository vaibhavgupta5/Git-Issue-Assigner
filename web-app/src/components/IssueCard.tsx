interface IssueCardProps {
  issueNumber: number;
  issueTitle: string;
  issueDescription: string;
  issueUrl: string;
  category: string;
  confidence: number;
  requiredSkills: string[];
  assignedTo?: string;
  assignmentScore?: number;
  labels?: string[];
}

export default function IssueCard({
  issueNumber,
  issueTitle,
  issueDescription,
  issueUrl,
  category,
  confidence,
  requiredSkills,
  assignedTo,
  assignmentScore,
  labels = []
}: IssueCardProps) {
  const getCategoryColor = (cat: string) => {
    const colors: Record<string, string> = {
      'Backend/API': '#3b82f6',
      'Frontend/UI': '#ec4899',
      'Database': '#8b5cf6',
      'Mobile': '#10b981',
      'General': '#6b7280'
    };
    return colors[cat] || '#6b7280';
  };

  const getConfidenceEmoji = (conf: number) => {
    if (conf >= 0.8) return '🎯';
    if (conf >= 0.6) return '✅';
    if (conf >= 0.4) return '⚠️';
    return '❓';
  };

  return (
    <div className="bg-black border-4 border-white p-6 hover:border-blue-500 transition-colors">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <span className="text-gray-400 font-mono text-sm">#{issueNumber}</span>
            <a 
              href={issueUrl} 
              target="_blank" 
              rel="noopener noreferrer"
              className="text-white font-bold text-lg hover:text-blue-400 transition-colors"
            >
              {issueTitle}
            </a>
          </div>
          
          {/* Labels */}
          {labels.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {labels.map((label, idx) => (
                <span 
                  key={idx}
                  className="px-2 py-1 text-xs font-mono border border-white text-white"
                >
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
        
        {/* Category Badge */}
        <div 
          className="px-4 py-2 border-4 font-bold text-sm"
          style={{ 
            borderColor: getCategoryColor(category),
            color: getCategoryColor(category)
          }}
        >
          {category}
        </div>
      </div>

      {/* Description */}
      <p className="text-gray-300 text-sm mb-4 line-clamp-2">
        {issueDescription}
      </p>

      {/* AI Analysis Section */}
      <div className="border-t-2 border-white pt-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-2xl">{getConfidenceEmoji(confidence)}</span>
          <span className="text-white font-bold">AI Analysis</span>
          <span className="text-gray-400 text-sm">
            {(confidence * 100).toFixed(0)}% confidence
          </span>
        </div>

        {/* Required Skills */}
        {requiredSkills && requiredSkills.length > 0 && (
          <div className="mb-3">
            <div className="text-white text-sm font-bold mb-2">🔧 Required Skills:</div>
            <div className="flex flex-wrap gap-2">
              {requiredSkills.map((skill, idx) => (
                <span 
                  key={idx}
                  className="px-3 py-1 bg-black border-2 border-blue-500 text-blue-500 font-mono text-sm"
                >
                  {skill}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Assignment Info */}
      {assignedTo && (
        <div className="border-t-2 border-green-500 pt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-green-500 font-bold text-sm">✅ ASSIGNED TO:</span>
              <span className="text-white font-mono">{assignedTo}</span>
            </div>
            {assignmentScore !== undefined && (
              <div className="text-green-500 font-mono text-sm">
                Score: {assignmentScore.toFixed(3)}
              </div>
            )}
          </div>
        </div>
      )}

      {/* View on GitHub Link */}
      <div className="mt-4 pt-4 border-t-2 border-gray-700">
        <a 
          href={issueUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 font-mono text-sm flex items-center gap-2"
        >
          🔗 View on GitHub →
        </a>
      </div>
    </div>
  );
}
