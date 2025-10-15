// Firebase configuration and initialization
import { initializeApp } from 'firebase/app';
import { getFirestore, collection, addDoc, getDocs, deleteDoc, doc, query, orderBy, Timestamp } from 'firebase/firestore';

// Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyBk73CevJd4MbecV6vGSedaQDCVv0izLCY",
  authDomain: "vaibhav-a3d20.firebaseapp.com",
  projectId: "vaibhav-a3d20",
  storageBucket: "vaibhav-a3d20.firebasestorage.app",
  messagingSenderId: "943569311855",
  appId: "1:943569311855:web:18a056c54322a78989559a"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
export const db = getFirestore(app);

// Collection reference
export const BATCHES_COLLECTION = 'triageBatches';

// Types for Firebase operations
export interface FirebaseBatch {
  id?: string;
  timestamp: Timestamp;
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

// Define the types used in FirebaseBatch
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

// Firebase operations
export const firebaseOperations = {
  // Save a new batch to Firebase
  async saveBatch(batchData: Omit<FirebaseBatch, 'id' | 'timestamp'>) {
    try {
      const docRef = await addDoc(collection(db, BATCHES_COLLECTION), {
        ...batchData,
        timestamp: Timestamp.now()
      });
      console.log('✅ Batch saved with ID:', docRef.id);
      return { success: true, id: docRef.id };
    } catch (error) {
      console.error('❌ Error saving batch:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  },

  // Load all batches from Firebase
  async loadBatches() {
    try {
      const q = query(collection(db, BATCHES_COLLECTION), orderBy('timestamp', 'desc'));
      const querySnapshot = await getDocs(q);
      
      const batches: (FirebaseBatch & { id: string })[] = [];
      querySnapshot.forEach((doc) => {
        const data = doc.data() as FirebaseBatch;
        batches.push({
          ...data,
          id: doc.id
        });
      });
      
      console.log(`✅ Loaded ${batches.length} batches from Firebase`);
      return { success: true, batches };
    } catch (error) {
      console.error('❌ Error loading batches:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error', batches: [] };
    }
  },

  // Delete a batch from Firebase
  async deleteBatch(batchId: string) {
    try {
      await deleteDoc(doc(db, BATCHES_COLLECTION, batchId));
      console.log('✅ Batch deleted:', batchId);
      return { success: true };
    } catch (error) {
      console.error('❌ Error deleting batch:', error);
      return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
    }
  }
};