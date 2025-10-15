'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { DeveloperCard } from '@/components/DeveloperCard';
import { StatsCard } from '@/components/StatsCard';
import { RepoInput } from '@/components/RepoInput';
import IssueCard from '@/components/IssueCard';
import { firebaseOperations, FirebaseBatch } from '@/lib/firebase';
import { Timestamp } from 'firebase/firestore';

interface Developer {
  id: string;
  name: string;
  github_username: string;
  email: string;
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
}

interface Assignment {
  timestamp: string;
  issue_id: string;
  issue_number: number;
  issue_title: string;
  issue_description?: string;
  issue_url: string;
  issue_labels?: string[];
  required_skills?: string[];
  assigned_to: string;
  real_name: string;
  developer_id: string;
  source_type: string;
  category: string;
  confidence: number;
  assignment_score: number;
  github_profile: string;
  real_contributions: number;
  is_real_developer: boolean;
  github_assigned: boolean;
}

interface SystemStatus {
  is_running: boolean;
  current_repo: string | null;
  total_developers: number;
  total_assignments: number;
  contributors_count: number;
  collaborators_count: number;
  both_count: number;
  last_updated: string | null;
  error: string | null;
}

interface SavedBatch {
  id: string;
  timestamp: string | Date | { toDate(): Date }; // Firebase Timestamp or string or Date
  repository: string;
  developers: Developer[];
  assignments: Assignment[];
  stats: {
    total_developers: number;
    total_assignments: number;
    contributors_count: number;
    collaborators_count: number;
  };
}

export default function Home() {
  const [developers, setDevelopers] = useState<Developer[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedBatches, setSavedBatches] = useState<SavedBatch[]>([]);
  const [showSavedData, setShowSavedData] = useState(false);
  const [firebaseLoading, setFirebaseLoading] = useState(false);

  const API_BASE = 'http://localhost:8000';

  // Load saved batches from Firebase on component mount
  useEffect(() => {
    loadBatchesFromFirebase();
  }, []);

  // Load batches from Firebase
  const loadBatchesFromFirebase = async () => {
    setFirebaseLoading(true);
    try {
      const result = await firebaseOperations.loadBatches();
      if (result.success) {
        const formattedBatches = result.batches.map(batch => ({
          ...batch,
          timestamp: batch.timestamp?.toDate ? batch.timestamp.toDate().toISOString() : 
                    batch.timestamp instanceof Date ? batch.timestamp.toISOString() : 
                    batch.timestamp
        }));
        setSavedBatches(formattedBatches);
      } else {
        console.error('Failed to load batches:', result.error);
        alert(`❌ Failed to load batches: ${result.error}`);
      }
    } catch (error) {
      console.error('Error loading batches:', error);
      alert('❌ Error connecting to Firebase. Check your configuration.');
    }
    setFirebaseLoading(false);
  };

  // Save batch data to Firebase
  const saveBatch = async () => {
    if (!status?.current_repo || developers.length === 0) {
      alert('No data to save! Please start the pipeline first.');
      return;
    }

    setFirebaseLoading(true);
    try {
      const batchData = {
        repository: status.current_repo,
        developers: [...developers],
        assignments: [...assignments],
        stats: {
          total_developers: status.total_developers,
          total_assignments: status.total_assignments,
          contributors_count: status.contributors_count,
          collaborators_count: status.collaborators_count,
        }
      };

      const result = await firebaseOperations.saveBatch(batchData);
      
      if (result.success) {
        alert(`✅ Batch saved to Firebase! Repository: ${status.current_repo}, Developers: ${developers.length}, Assignments: ${assignments.length}`);
        // Reload batches from Firebase
        await loadBatchesFromFirebase();
      } else {
        alert(`❌ Failed to save batch: ${result.error}`);
      }
    } catch (error) {
      console.error('Error saving batch:', error);
      alert('❌ Error connecting to Firebase. Check your configuration.');
    }
    setFirebaseLoading(false);
  };

  // Delete a saved batch from Firebase
  const deleteBatch = async (batchId: string) => {
    setFirebaseLoading(true);
    try {
      const result = await firebaseOperations.deleteBatch(batchId);
      
      if (result.success) {
        alert('✅ Batch deleted from Firebase!');
        // Reload batches from Firebase
        await loadBatchesFromFirebase();
      } else {
        alert(`❌ Failed to delete batch: ${result.error}`);
      }
    } catch (error) {
      console.error('Error deleting batch:', error);
      alert('❌ Error connecting to Firebase. Check your configuration.');
    }
    setFirebaseLoading(false);
  };

  // Load a saved batch
  const loadBatch = (batch: SavedBatch) => {
    setDevelopers(batch.developers);
    setAssignments(batch.assignments);
    setStatus({
      is_running: false,
      current_repo: batch.repository,
      total_developers: batch.stats.total_developers,
      total_assignments: batch.stats.total_assignments,
      contributors_count: batch.stats.contributors_count,
      collaborators_count: batch.stats.collaborators_count,
      both_count: 0,
      last_updated: typeof batch.timestamp === 'string' ? batch.timestamp : new Date().toISOString(),
      error: null
    });
    setShowSavedData(false);
    const dateStr = typeof batch.timestamp === 'string' 
      ? new Date(batch.timestamp).toLocaleString() 
      : batch.timestamp instanceof Date 
      ? batch.timestamp.toLocaleString()
      : new Date().toLocaleString();
    alert(`✅ Loaded batch from ${batch.repository} (${dateStr})`);
  };

  const fetchData = async () => {
    try {
      const [devsRes, assignRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/developers`),
        fetch(`${API_BASE}/assignments`),
        fetch(`${API_BASE}/status`),
      ]);

      if (devsRes.ok) setDevelopers(await devsRes.json());
      if (assignRes.ok) setAssignments(await assignRes.json());
      if (statusRes.ok) setStatus(await statusRes.json());
    } catch (err) {
      console.error('Error fetching data:', err);
    }
  };

  const startPipeline = async (repoName: string) => {
    setLoading(true);
    setError(null);
    
    try {
      const response = await fetch(`${API_BASE}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_name: repoName }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail || 'Failed to start pipeline');
      }

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start pipeline');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  return (
    <motion.div 
      className="min-h-screen bg-black text-white"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      <div className="max-w-[1600px] mx-auto p-8">
        {/* Header */}
        <motion.div 
          className="mb-12"
          initial={{ y: -50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.2 }}
        >
          <motion.h1 
            className="text-5xl font-bold mb-4 border-r-4 border-b-4 border-white inline-block pr-8 pb-4"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.4 }}
            whileHover={{ scale: 1.05 }}
          >
            🤖 Smart Bug Triage
          </motion.h1>
          <motion.p 
            className="text-gray-400 mt-6 text-lg"
            initial={{ x: -30, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 0.6 }}
          >
            AI-Powered Developer Assignment System
          </motion.p>
        </motion.div>

        {/* Repo Input */}
        <motion.div
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.8 }}
        >
          <RepoInput onStart={startPipeline} loading={loading} error={error} />
        </motion.div>

        {/* Save/Load Controls */}
        <motion.div 
          className="flex gap-4 mb-8 mt-4"
          initial={{ y: 30, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.9 }}
        >
          <motion.button
            onClick={saveBatch}
            className="border-r-4 border-b-4 text-black border-white bg-white hover:bg-black hover:text-white px-6 py-3 font-bold transition-colors cursor-pointer"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            disabled={!status?.current_repo || developers.length === 0 || firebaseLoading}
          >
            {firebaseLoading ? '🔄 Saving...' : '💾 Save to Firebase'}
          </motion.button>
          
          <motion.button
            onClick={() => setShowSavedData(!showSavedData)}
            className="border-r-4 border-b-4 border-white text-white bg-black hover:bg-white hover:text-black px-6 py-3 font-bold transition-colors cursor-pointer"
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            disabled={firebaseLoading}
          >
            {firebaseLoading ? '🔄 Loading...' : `� ${showSavedData ? 'Hide' : 'Show'} Firebase Batches (${savedBatches.length})`}
          </motion.button>
        </motion.div>

        {/* Saved Batches Display */}
        <AnimatePresence>
          {showSavedData && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.4 }}
              className="mb-8 overflow-hidden"
            >
              <motion.div 
                className="border-r-4 border-b-4 border-purple-500 p-6 bg-gray-900"
                initial={{ y: -20, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.3, delay: 0.1 }}
              >
                <h3 className="text-2xl font-bold mb-4 text-purple-400">� Firebase Saved Batches</h3>
                
                {savedBatches.length === 0 ? (
                  <p className="text-gray-400">
                    {firebaseLoading ? '🔄 Loading from Firebase...' : 'No saved batches yet. Save your current data to Firebase!'}
                  </p>
                ) : (
                  <div className="space-y-4">
                    {savedBatches.map((batch, index) => (
                      <motion.div
                        key={batch.id}
                        initial={{ x: -20, opacity: 0 }}
                        animate={{ x: 0, opacity: 1 }}
                        transition={{ duration: 0.3, delay: index * 0.1 }}
                        className="border-r-2 border-b-2 border-gray-600 p-4 bg-gray-800 hover:bg-gray-700 transition-colors"
                      >
                        <div className="flex justify-between items-start">
                          <div className="flex-1">
                            <h4 className="text-lg font-bold text-white mb-2">🔗 {batch.repository}</h4>
                            <p className="text-sm text-gray-400 mb-2">
                              📅 {typeof batch.timestamp === 'string' 
                                ? new Date(batch.timestamp).toLocaleString()
                                : batch.timestamp instanceof Date
                                ? batch.timestamp.toLocaleString()
                                : new Date().toLocaleString()}
                            </p>
                            <div className="flex gap-4 text-sm">
                              <span className="text-blue-400">👥 {batch.stats.total_developers} developers</span>
                              <span className="text-green-400">📋 {batch.stats.total_assignments} assignments</span>
                              <span className="text-yellow-400">👤 {batch.stats.contributors_count} contributors</span>
                              <span className="text-purple-400">🤝 {batch.stats.collaborators_count} collaborators</span>
                            </div>
                          </div>
                          <div className="flex gap-2">
                            <motion.button
                              onClick={() => loadBatch(batch)}
                              className="border-r-2 border-b-2 border-green-400 bg-green-600 hover:bg-green-700 px-3 py-1 text-sm font-bold transition-colors"
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                              disabled={firebaseLoading}
                            >
                              ↻ Load
                            </motion.button>
                            <motion.button
                              onClick={() => {
                                if (confirm(`Delete batch for ${batch.repository}?`)) {
                                  deleteBatch(batch.id);
                                }
                              }}
                              className="border-r-2 border-b-2 border-red-400 bg-red-600 hover:bg-red-700 px-3 py-1 text-sm font-bold transition-colors"
                              whileHover={{ scale: 1.05 }}
                              whileTap={{ scale: 0.95 }}
                              disabled={firebaseLoading}
                            >
                              🗑️ Delete
                            </motion.button>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                )}
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Status Cards */}
        {status && (
          <motion.div 
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12"
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 1.0 }}
          >
            {[
              { title: "Total Developers", value: status.total_developers, icon: "👥" },
              { title: "Contributors", value: status.contributors_count, icon: "👤" },
              { title: "Collaborators", value: status.collaborators_count, icon: "🤝" },
              { title: "Assignments Made", value: status.total_assignments, icon: "�" }
            ].map((stat, index) => (
              <motion.div
                key={stat.title}
                initial={{ y: 30, opacity: 0, scale: 0.9 }}
                animate={{ y: 0, opacity: 1, scale: 1 }}
                transition={{ 
                  duration: 0.5, 
                  delay: 1.2 + (index * 0.1),
                  type: "spring",
                  stiffness: 100
                }}
                whileHover={{ 
                  y: -5, 
                  transition: { duration: 0.2 } 
                }}
              >
                <StatsCard
                  title={stat.title}
                  value={stat.value}
                  icon={stat.icon}
                />
              </motion.div>
            ))}
          </motion.div>
        )}

        {/* Current Repository */}
        {status?.current_repo && (
          <motion.div 
            className="mb-8 border-r-4 border-b-4 border-white p-6 bg-black"
            initial={{ x: -100, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.6, delay: 1.6 }}
            whileHover={{ 
              borderColor: "#10b981",
              transition: { duration: 0.3 }
            }}
          >
            <div className="flex items-center justify-between">
              <motion.div
                initial={{ x: -20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ duration: 0.5, delay: 1.8 }}
              >
                <span className="text-gray-400 text-sm">MONITORING</span>
                <h2 className="text-2xl font-bold">{status.current_repo}</h2>
              </motion.div>
              <motion.div 
                className="flex items-center gap-3"
                initial={{ x: 20, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                transition={{ duration: 0.5, delay: 2.0 }}
              >
                <motion.div 
                  className={`h-3 w-3 rounded-full ${status.is_running ? 'bg-green-500' : 'bg-red-500'}`}
                  animate={{ 
                    scale: status.is_running ? [1, 1.2, 1] : 1,
                  }}
                  transition={{ 
                    duration: 2, 
                    repeat: status.is_running ? Infinity : 0,
                    ease: "easeInOut" 
                  }}
                />
                <span className="font-bold">{status.is_running ? 'ACTIVE' : 'STOPPED'}</span>
              </motion.div>
            </div>
          </motion.div>
        )}

        {/* Developers Section */}
        <motion.section 
          className="mb-16"
          initial={{ y: 50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 2.2 }}
        >
          <motion.h2 
            className="text-3xl font-bold mb-8 border-r-4 border-b-4 border-white inline-block pr-6 pb-3"
            initial={{ x: -30, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 2.4 }}
            whileHover={{ scale: 1.02 }}
          >
            Available Developers
          </motion.h2>
          
          <AnimatePresence mode="wait">
            {developers.length === 0 ? (
              <motion.div 
                className="border-r-4 border-b-4 border-white p-12 text-center"
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                transition={{ duration: 0.4 }}
              >
                <motion.p 
                  className="text-gray-400 text-lg"
                  initial={{ y: 10, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ duration: 0.3, delay: 0.2 }}
                >
                  No developers loaded. Start the pipeline with a repository name.
                </motion.p>
              </motion.div>
            ) : (
              <motion.div 
                className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
              >
                {developers.map((dev, index) => (
                  <motion.div
                    key={dev.id}
                    initial={{ y: 50, opacity: 0, scale: 0.9 }}
                    animate={{ y: 0, opacity: 1, scale: 1 }}
                    transition={{ 
                      duration: 0.5, 
                      delay: 2.6 + (index * 0.1),
                      type: "spring",
                      stiffness: 100
                    }}
                    whileHover={{ 
                      y: -5,
                      transition: { duration: 0.2 }
                    }}
                  >
                    <DeveloperCard developer={dev} />
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.section>

        {/* Assignments Section */}
        <motion.section
          initial={{ y: 50, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ duration: 0.6, delay: 2.8 }}
        >
          <motion.h2 
            className="text-3xl font-bold mb-8 border-r-4 border-b-4 border-white inline-block pr-6 pb-3"
            initial={{ x: -30, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            transition={{ duration: 0.5, delay: 3.0 }}
            whileHover={{ scale: 1.02 }}
          >
            Issue Assignments
          </motion.h2>
          
          <AnimatePresence mode="wait">
            {assignments.length === 0 ? (
              <motion.div 
                className="border-r-4 border-b-4 border-white p-12 text-center"
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.9, opacity: 0 }}
                transition={{ duration: 0.4 }}
              >
                <motion.p 
                  className="text-gray-400 text-lg"
                  initial={{ y: 10, opacity: 0 }}
                  animate={{ y: 0, opacity: 1 }}
                  transition={{ duration: 0.3, delay: 0.2 }}
                >
                  No assignments yet. Waiting for issues...
                </motion.p>
              </motion.div>
            ) : (
              <motion.div 
                className="space-y-6"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
              >
                {assignments.map((assignment, index) => (
                  <motion.div
                    key={assignment.issue_id}
                    initial={{ x: -50, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    transition={{ 
                      duration: 0.5, 
                      delay: 3.2 + (index * 0.1),
                      type: "spring",
                      stiffness: 80
                    }}
                    whileHover={{ 
                      scale: 1.02,
                      transition: { duration: 0.2 }
                    }}
                  >
                    <IssueCard 
                      issueNumber={assignment.issue_number}
                      issueTitle={assignment.issue_title}
                      issueDescription={assignment.issue_description || 'No description provided'}
                      issueUrl={assignment.issue_url}
                      category={assignment.category}
                      confidence={assignment.confidence}
                      requiredSkills={assignment.required_skills || []}
                      assignedTo={assignment.assigned_to}
                      assignmentScore={assignment.assignment_score}
                      labels={assignment.issue_labels || []}
                    />
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.section>
      </div>
    </motion.div>
  );
}
