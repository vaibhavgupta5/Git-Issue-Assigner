# Smart Bug Triage and Developer Assignment System

A multi-agent AI system for automated bug triage and intelligent developer assignment using machine learning and natural language processing.

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** (Python 3.9 or higher recommended)
- **PostgreSQL** (for database)
- **RabbitMQ** (for message queue - optional for basic usage)
- **Git** (for repository access)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/satvik-svg/Smart-Bug-Triage-Agent.git
cd Smart-Bug-Triage-Agent
```

2. **Install Python dependencies:**
```bash
pip3 install -r requirements.txt
```

3. **Download required NLP model:**
```bash
python -m spacy download en_core_web_sm
```

4. **Set up environment variables:**

   **Step 4.1:** Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

   **Step 4.2:** Create a GitHub Personal Access Token:
   - Go to: https://github.com/settings/tokens
   - Click **"Generate new token"** → **"Generate new token (classic)"**
   - Give it a name (e.g., "Smart Bug Triage")
   - Select the following scopes:
     - ✅ `repo` (Full control of private repositories)
     - ✅ `read:org` (Read org and team membership)
     - ✅ `read:user` (Read user profile data)
   - Click **"Generate token"**
   - **IMPORTANT:** Copy the token immediately (you won't see it again!)

   **Step 4.3:** Edit the `.env` file and add your GitHub token:
   ```bash
   # Open .env file in your preferred editor
   nano .env
   # or
   code .env
   ```

   **Step 4.4:** Replace the placeholder values:
   ```bash
   # REQUIRED: Replace with your actual GitHub token
   GITHUB_TOKEN=ghp_YOUR_ACTUAL_TOKEN_HERE
   
   # REQUIRED: Replace with your GitHub username/organization
   GITHUB_ORGANIZATION=your_github_username
   
   # REQUIRED: Replace with your repositories (comma-separated)
   GITHUB_REPOSITORIES=repo1,repo2,repo3
   
   # Optional: Database configuration (if using PostgreSQL)
   # DB_HOST=localhost
   # DB_PORT=5432
   # DB_NAME=smart_bug_triage
   # DB_USERNAME=your_db_username
   # DB_PASSWORD=your_db_password
   ```

   **Step 4.5:** Save the file and verify your configuration:
   ```bash
   python scripts/validate_config.py
   ```

   **⚠️ SECURITY WARNING:**
   - **NEVER commit the `.env` file to Git** (it's already in `.gitignore`)
   - **NEVER share your GitHub token publicly**
   - If you accidentally expose your token, revoke it immediately at https://github.com/settings/tokens

---

## 🎯 How to Run the Project

### Method 1: Interactive Launcher (Recommended for Beginners)

Start the interactive menu to choose what to run:

```bash
python launcher.py
```

This will show you a menu with options to:
- Start the complete live pipeline
- Run system tests/demos
- Test individual components

---

### Method 2: Real Contributor Pipeline

Run the pipeline that uses **REAL GitHub contributors** from your repository:

```bash
python real_contributor_pipeline.py
```

**What it does:**
- Fetches actual contributors from your GitHub repository
- Analyzes their skills from their commit history
- Monitors for new issues
- Automatically assigns issues to real contributors

**Requirements:**
- GitHub token with repository access
- Repository with actual contributors

---

### Method 3: Complete Bug Assignment Pipeline

Run the complete bug assignment system:

```bash
python complete_bug_assignment_pipeline.py
```

**What it does:**
- Detects new GitHub issues
- Analyzes them using AI/NLP
- Assigns them to developers
- Shows the complete workflow

---

### Method 4: Full Production Pipeline

Start the complete multi-agent system:

```bash
python start_complete_pipeline.py
```

**What it does:**
- Starts Listener Agent (monitors GitHub/Jira)
- Starts Triage Agent (AI classification)
- Starts Assignment Agent (developer matching)
- Starts Developer Agents (issue assignment)
- Runs complete end-to-end pipeline

**Requirements:**
- All environment variables configured
- Database running
- RabbitMQ running (optional)

---

### Method 5: Monitoring Service

Start the monitoring and metrics service:

```bash
python start_monitoring.py
```

---

## 🛠️ Utility Scripts

### Setup Environment
```bash
python scripts/setup_environment.py
```
Interactive script to configure your environment variables.

### Validate Configuration
```bash
python scripts/validate_config.py
```
Check if your configuration is correct before running.

### Initialize Database
```bash
python scripts/init_database.py
```
Set up the database schema and tables.

### Setup RabbitMQ Queues
```bash
python scripts/setup_rabbitmq_queues.py
```
Create required message queues in RabbitMQ.

### Discover Developers
```bash
python scripts/discover_developers.py
```
Automatically discover and analyze developers from repositories.

### List Repositories
```bash
python scripts/list_repositories.py
```
List accessible GitHub repositories.

### Run Triage Agent Standalone
```bash
python scripts/run_triage_agent.py
```
Run only the AI triage agent.

### Run Monitoring Service
```bash
python scripts/run_monitoring_service.py
```
Run the monitoring service standalone.

---

## 📋 Configuration Files

### `config.json`
System-wide configuration including database, message queue, and agent settings.

### `developers_config.json`
Developer profiles including skills, capacity, and preferences.

### `.env`
Environment variables for sensitive credentials (GitHub token, database password, etc.)

---

## 🏗️ Project Structure

```
.
├── launcher.py                          # Interactive launcher
├── complete_bug_assignment_pipeline.py  # Complete assignment pipeline
├── real_contributor_pipeline.py         # Real contributor pipeline
├── start_complete_pipeline.py           # Full production system
├── start_monitoring.py                  # Monitoring service
├── requirements.txt                     # Python dependencies
├── config.json                          # System configuration
├── developers_config.json               # Developer profiles
├── .env                                 # Environment variables
│
├── smart_bug_triage/                    # Main package
│   ├── agents/                          # Agent implementations
│   ├── api/                             # External API integrations
│   ├── config/                          # Configuration management
│   ├── database/                        # Database layer
│   ├── health/                          # Health checks
│   ├── message_queue/                   # Message queue system
│   ├── models/                          # Data models
│   ├── monitoring/                      # Monitoring system
│   ├── nlp/                             # NLP/AI pipeline
│   ├── notifications/                   # Notification system
│   └── utils/                           # Utility functions
│
└── scripts/                             # Utility scripts
    ├── setup_environment.py
    ├── validate_config.py
    ├── init_database.py
    ├── discover_developers.py
    └── ...
```

---

## 🧠 System Components

### 1. **Listener Agent**
Monitors GitHub/Jira for new issues and bug reports.

### 2. **Triage Agent**
Uses AI/NLP to classify bugs by:
- Category (Frontend, Backend, Database, API, etc.)
- Severity (Critical, High, Medium, Low)
- Keywords and technical terms

### 3. **Assignment Agent**
Intelligently assigns bugs to developers based on:
- Developer skills and experience
- Current workload and capacity
- Past performance on similar issues
- Availability and calendar integration

### 4. **Developer Agents**
Execute assignments and manage developer interactions.

### 5. **Monitoring System**
Tracks performance, metrics, and system health.

---

## 🔧 Technology Stack

- **Language:** Python 3.8+
- **NLP/AI:** spaCy, scikit-learn
- **Database:** PostgreSQL (SQLAlchemy ORM)
- **Message Queue:** RabbitMQ (pika)
- **APIs:** PyGithub, Jira, Slack
- **Web Framework:** FastAPI
- **Monitoring:** Prometheus, structlog

---

## 📊 Key Features

✅ **AI-Powered Classification** - Automatic bug categorization using NLP  
✅ **Intelligent Assignment** - ML-based developer matching  
✅ **Real Contributor Analysis** - Skills extracted from actual commit history  
✅ **Multi-Platform Support** - GitHub and Jira integration  
✅ **Workload Management** - Tracks developer capacity in real-time  
✅ **Calendar Integration** - Respects developer availability  
✅ **Performance Tracking** - Monitors assignment success rates  
✅ **Scalable Architecture** - Multi-agent distributed system  

---

## 🚨 Troubleshooting

### Issue: "ModuleNotFoundError"
**Solution:**
```bash
pip3 install -r requirements.txt
python -m spacy download en_core_web_sm
```

### Issue: "GITHUB_TOKEN not found"
**Solution:** Add your GitHub token to the `.env` file:
```bash
GITHUB_TOKEN=ghp_your_token_here
```

### Issue: "Database connection failed"
**Solution:** 
1. Make sure PostgreSQL is running
2. Check database credentials in `.env`
3. Run: `python scripts/init_database.py`

### Issue: "RabbitMQ connection failed"
**Solution:** RabbitMQ is optional for basic usage. You can:
1. Install and start RabbitMQ, OR
2. Run pipelines that don't require message queue (real_contributor_pipeline.py)

---

## 📝 Important Notes

### **Always use `python` instead of `python`:**
```bash
# ✅ Correct
python script_name.py
pip3 install package_name

# ❌ Wrong (may use Python 2)
python script_name.py
pip install package_name
```

### **GitHub Token Permissions:**
Your GitHub token needs these scopes:
- `repo` - Access repositories
- `read:org` - Read organization data
- `read:user` - Read user profile data

### **System Requirements:**
- Minimum: 4GB RAM, 2 CPU cores
- Recommended: 8GB RAM, 4 CPU cores
- Storage: ~500MB for the application + dependencies

---

## 🎓 Student Information

**Project:** Smart Bug Triage and Developer Assignment System  
**Student:** Satvik Srivastava  
**Purpose:** Intelligent automation of bug triage and developer assignment using AI/ML  

---

## 📄 License

This project is for educational and research purposes.

---

## 🆘 Getting Help

If you encounter issues:

1. **Check Configuration:**
   ```bash
   python scripts/validate_config.py
   ```

2. **View Logs:** Check terminal output for error messages

3. **Test Components:** Use the interactive launcher to test individual components

4. **Environment Check:** Run setup script again:
   ```bash
   python scripts/setup_environment.py
   ```

---

**Ready to get started? Run the interactive launcher:**
```bash
python launcher.py
```
