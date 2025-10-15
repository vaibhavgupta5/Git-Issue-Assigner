import { useState } from 'react';

interface RepoInputProps {
  onStart: (repoName: string) => Promise<void>;
  loading: boolean;
  error: string | null;
}

export function RepoInput({ onStart, loading, error }: RepoInputProps) {
  const [repoName, setRepoName] = useState('satvik-svg/Smart-Bug-Triage-Agent');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (repoName.trim()) {
      onStart(repoName.trim());
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="border-4 border-r-8 border-b-8 border-white p-8 bg-white">
        <label className="block text-sm font-bold text-black mb-4  tracking-wider">
          REPOSITORY (OWNER/REPO)
        </label>
        <div className="flex flex-col sm:flex-row gap-4">
          <input
            type="text"
            value={repoName}
            onChange={(e) => setRepoName(e.target.value)}
            placeholder="satvik-svg/Smart-Bug-Triage-Agent"
            className="flex-1 bg-black border-4 border-white px-6 py-4 text-white text-lg font-mono focus:outline-none focus:bg-white focus:text-black transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading || !repoName.trim()}
            className="px-10 py-4 bg-black text-white font-bold text-lg border-4 border-black hover:bg-white hover:text-black cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-white disabled:hover:text-black whitespace-nowrap"
          >
            {loading ? 'STARTING...' : 'START PIPELINE'}
          </button>
        </div>
        {error && (
          <div className="mt-6 p-6 border-4 border-white bg-white text-black">
            <span className="font-bold">ERROR: </span> {error}
          </div>
        )}
      </form>
    </div>
  );
}