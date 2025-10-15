# 🔥 Firebase Setup Guide

## 📋 Prerequisites

1. **Google Account**: You need a Google account to access Firebase
2. **Firebase Project**: Create a new Firebase project at [Firebase Console](https://console.firebase.google.com/)

## 🚀 Setup Steps

### 1. Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click "Create a project"
3. Enter project name: `smart-bug-triage` (or any name you prefer)
4. Choose whether to enable Google Analytics (optional)
5. Click "Create project"

### 2. Enable Firestore Database

1. In your Firebase project, go to "Firestore Database"
2. Click "Create database"
3. Choose "Start in test mode" (for development)
4. Select a location close to your users
5. Click "Done"

### 3. Get Firebase Configuration

1. In Firebase Console, click the ⚙️ gear icon → "Project settings"
2. Scroll down to "Your apps" section
3. Click the `</>` icon to add a web app
4. Register your app with name: `Smart Bug Triage Web`
5. Copy the Firebase configuration object

### 4. Update Configuration

Replace the config in `src/lib/firebase.ts`:

```typescript
const firebaseConfig = {
  apiKey: "AIzaSyDPvKmMFqKj7YxGKH8H1NwXpLk2J3mN4O5",
  authDomain: "your-project.firebaseapp.com",
  projectId: "your-project-id",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "123456789012",
  appId: "1:123456789012:web:abcdef123456789"
};
```

### 5. Update Firestore Rules (Optional)

For development, you can use these rules in Firestore → Rules:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Allow read/write access to all documents
    match /{document=**} {
      allow read, write: if true;
    }
  }
}
```

⚠️ **Note**: These rules allow anyone to read/write. For production, implement proper authentication and security rules.

## 🔧 Environment Variables (Optional)

For better security, you can use environment variables:

1. Create `.env.local` in your project root:

```env
NEXT_PUBLIC_FIREBASE_API_KEY=your-api-key
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789
NEXT_PUBLIC_FIREBASE_APP_ID=your-app-id
```

2. Update `src/lib/firebase.ts`:

```typescript
const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
  storageBucket: process.env.NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID
};
```

## 🧪 Testing the Setup

1. Start your development server: `npm run dev`
2. Open your app and try to save a batch
3. Check the Firebase Console → Firestore Database → Data
4. You should see a `triageBatches` collection with your saved data

## 📊 Data Structure

Your data will be stored in Firestore with this structure:

```
triageBatches/
├── [auto-generated-id]/
│   ├── repository: "user/repo-name"
│   ├── timestamp: Firebase Timestamp
│   ├── developers: Array of Developer objects
│   ├── assignments: Array of Assignment objects
│   └── stats: Object with counts
```

## 🔒 Security Considerations

- **Development**: Test mode allows all read/write operations
- **Production**: Implement authentication and proper security rules
- **API Keys**: While API keys are public in client-side apps, restrict them by HTTP referrer in Firebase Console

## 🐛 Troubleshooting

### Common Issues:

1. **"Firebase config not found"**
   - Make sure you've updated the config in `firebase.ts`

2. **"Permission denied"**
   - Check Firestore rules allow read/write operations

3. **"Network error"**
   - Verify internet connection and Firebase project is active

4. **TypeScript errors**
   - Make sure Firebase SDK is installed: `npm install firebase`

## 🎉 Success!

Once configured, your Smart Bug Triage system will:
- ✅ Save all batch data to Firebase Firestore
- ✅ Load saved batches from the cloud
- ✅ Delete batches with confirmation
- ✅ Persist data across devices and sessions
- ✅ Provide real-time sync capabilities

Your data is now safely stored in the cloud! 🚀