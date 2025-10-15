#!/usr/bin/env python
"""
FastAPI Server for Bug Triage Dashboard
========================================
Provides real-time data about developers, assignments, and system status.
Integrates with smart_bug_triage agents for intelligent assignment.
"""

import os
import sys
import asyncio
import time
import json
import requests
import re
import math
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Add project to path
sys.path.insert(0, str(Path.cwd()))

# Load environment
load_dotenv()

# Import smart_bug_triage modules
from smart_bug_triage.api.github_client import GitHubAPIClient
from smart_bug_triage.nlp.pipeline import NLPPipeline
from smart_bug_triage.models.common import (
    BugReport, CategorizedBug, DeveloperProfile, 
    DeveloperStatus, BugCategory, Priority
)
from smart_bug_triage.agents.assignment_algorithm import AssignmentAlgorithm
from smart_bug_triage.agents.developer_discovery import DeveloperDiscoveryService

app = FastAPI(title="Smart Bug Triage API", version="1.0.0")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
pipeline_state = {
    "developers": [],
    "developer_statuses": {},
    "assignments": [],
    "processed_issues": set(),
    "is_running": False,
    "current_repo": None,
    "last_updated": None,
    "error": None,
    # Agent instances
    "github_client": None,
    "nlp_pipeline": None,
    "assignment_algorithm": None,
    "developer_profiles": {},  # Maps developer_id to DeveloperProfile objects
    # API keys
    "gemini_api_key": os.getenv("GEMINI_API_KEY")
}

# Gemini API Integration
async def categorize_with_gemini(issue_title: str, issue_body: str, labels: List[str]) -> Dict[str, any]:
    """
    Use Gemini 1.5 Flash API to categorize issues with high accuracy
    """
    if not pipeline_state.get("gemini_api_key"):
        print("⚠️ Gemini API key not found, skipping AI categorization")
        return {"category": "General", "confidence": 0.5, "reasoning": "No API key"}
    
    try:
        # Prepare the prompt
        categories = [
            "Frontend/UI - User interface, web pages, components, styling, user experience",
            "Backend/API - Server logic, APIs, databases, authentication, business logic", 
            "Database - Database design, queries, migrations, data modeling",
            "Mobile - Mobile apps, iOS, Android, React Native, Flutter, Kotlin",
            "DevOps - Deployment, CI/CD, infrastructure, containers, cloud",
            "Security - Security vulnerabilities, authentication, encryption",
            "ML/AI - Machine learning, AI models, data science, analytics",
            "Performance - Optimization, speed, memory, scalability",
            "Documentation - Documentation, README, guides, tutorials",
            "Testing - Unit tests, integration tests, test automation",
            "General - Everything else or unclear categorization"
        ]
        
        prompt = f"""
Analyze the following GitHub issue and categorize it into ONE of these categories:

{chr(10).join(categories)}

Issue Details:
Title: {issue_title}
Description: {issue_body}
Labels: {', '.join(labels) if labels else 'None'}

Please respond with ONLY a JSON object in this exact format:
{{
    "category": "exact_category_name",
    "confidence": 0.85,
    "reasoning": "brief explanation of why this category fits"
}}

The category must be exactly one of: Frontend/UI, Backend/API, Database, Mobile, DevOps, Security, ML/AI, Performance, Documentation, Testing, General
"""

        # Make API call to Gemini
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={pipeline_state['gemini_api_key']}"
                
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 200
            }
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            
            if "candidates" in result and len(result["candidates"]) > 0:
                try:
                    candidate = result["candidates"][0]
                    print(f"    Debug: Candidate structure: {list(candidate.keys())}")
                    
                    # Try to extract text from various possible response structures
                    text_response = None
                    
                    if "content" in candidate and "parts" in candidate["content"]:
                        if candidate["content"]["parts"] and "text" in candidate["content"]["parts"][0]:
                            text_response = candidate["content"]["parts"][0]["text"].strip()
                    elif "text" in candidate:
                        text_response = candidate["text"].strip()
                    elif "output" in candidate:
                        text_response = candidate["output"].strip()
                    
                    if not text_response:
                        print(f"    ⚠️ Could not extract text from response structure: {candidate}")
                        return {"category": "General", "confidence": 0.5, "reasoning": "No text in response"}
                    
                    print(f"    Debug: Extracted text (first 100 chars): {text_response[:100]}...")
                    
                    # Parse JSON response
                    try:
                        # Clean the response to extract JSON
                        if "```json" in text_response:
                            text_response = text_response.split("```json")[1].split("```")[0].strip()
                        elif "```" in text_response:
                            text_response = text_response.split("```")[1].strip()
                        
                        gemini_result = json.loads(text_response)
                        
                        # Validate the response
                        if "category" in gemini_result and "confidence" in gemini_result:
                            print(f"    🤖 Gemini categorization: {gemini_result['category']} (confidence: {gemini_result['confidence']})")
                            return gemini_result
                        else:
                            print(f"    ⚠️ Invalid Gemini response format: {gemini_result}")
                            
                    except json.JSONDecodeError as e:
                        print(f"    ⚠️ Failed to parse Gemini JSON response: {e}")
                        print(f"    Raw response: {text_response[:200]}...")
                        
                except (KeyError, IndexError, TypeError) as e:
                    print(f"    ⚠️ Error accessing Gemini response structure: {e}")
                    print(f"    Full response: {result}")
            else:
                print(f"    ⚠️ No candidates in Gemini response: {result}")
        else:
            print(f"    ⚠️ Gemini API error: {response.status_code} - {response.text[:200]}")
            
    except Exception as e:
        print(f"    ⚠️ Gemini API call failed: {e}")
    
    # Fallback response
    return {"category": "General", "confidence": 0.5, "reasoning": "API call failed"}


async def generate_roadmap_with_gemini(issue_title: str, issue_body: str, category: str, developer_skills: List[str], experience_level: str) -> str:
    """
    Use Gemini 1.5 Flash API to generate intelligent roadmap and task breakdown
    """
    if not pipeline_state.get("gemini_api_key"):
        return generate_fallback_roadmap(issue_title, category, developer_skills)
    
    try:
        # Create comprehensive prompt for roadmap generation
        prompt = f"""
You are an expert software development project manager. Generate a detailed roadmap and task breakdown for the following GitHub issue.

**Issue Details:**
- Title: {issue_title}
- Description: {issue_body[:500]}...
- Category: {category}
- Assigned Developer Skills: {', '.join(developer_skills[:10])}
- Experience Level: {experience_level}

**Requirements:**
1. Create a step-by-step roadmap with numbered tasks
2. Include technical considerations and best practices
3. Suggest specific technologies/tools based on the category
4. Estimate complexity and time considerations
5. Add helpful tips for the developer's experience level
6. Include testing and documentation steps
7. Consider potential challenges and solutions

**Format as markdown with:**
- Clear numbered steps (1. 2. 3...)
- Sub-tasks with bullet points
- Code snippets or commands where relevant
- Emojis for visual appeal
- Estimated time/complexity indicators

Generate a comprehensive but concise roadmap (500-800 words).
"""

        # API request payload
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1000,
            }
        }

        # Make API call to Gemini
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={pipeline_state['gemini_api_key']}"
        
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            response_data = response.json()
            print(f"    Debug: Response keys: {list(response_data.keys())}")
            
            if "candidates" in response_data and response_data["candidates"]:
                try:
                    candidate = response_data["candidates"][0]
                    print(f"    Debug: Candidate keys: {list(candidate.keys())}")
                    
                    # Try multiple response structures
                    content = None
                    
                    if "content" in candidate and "parts" in candidate["content"]:
                        if candidate["content"]["parts"] and "text" in candidate["content"]["parts"][0]:
                            content = candidate["content"]["parts"][0]["text"]
                    elif "text" in candidate:
                        content = candidate["text"]
                    elif "output" in candidate:
                        content = candidate["output"]
                    
                    if content:
                        print(f"    🗺️ Generated roadmap with Gemini ({len(content)} chars)")
                        return content
                    else:
                        print(f"    ⚠️ No text content found in candidate: {candidate}")
                        
                except (KeyError, IndexError, TypeError) as e:
                    print(f"    ⚠️ Error parsing Gemini response structure: {e}")
                    print(f"    Debug response: {response_data}")
            else:
                print(f"    ⚠️ No candidates in Gemini roadmap response: {response_data}")
        else:
            print(f"    ⚠️ Gemini roadmap API error: {response.status_code}")
            print(f"    Error response: {response.text[:200]}")
            
    except Exception as e:
        print(f"    ⚠️ Gemini roadmap generation failed: {e}")
    
    # Fallback to basic roadmap
    return generate_fallback_roadmap(issue_title, category, developer_skills)


def generate_roadmap_sync(issue_title: str, issue_body: str, category: str, developer_skills: List[str], experience_level: str) -> str:
    """
    Synchronous wrapper for generate_roadmap_with_gemini that handles async execution properly
    """
    try:
        import asyncio
        import concurrent.futures
        
        # Check if we're in an async context
        try:
            # Try to get the current running loop
            loop = asyncio.get_running_loop()
            
            # We're in an async context, so we need to run in a thread pool
            with concurrent.futures.ThreadPoolExecutor() as executor:
                # Create a new event loop in the thread pool
                future = executor.submit(
                    lambda: asyncio.run(
                        generate_roadmap_with_gemini(
                            issue_title, issue_body, category, developer_skills, experience_level
                        )
                    )
                )
                return future.result(timeout=60)  # 60 second timeout
                
        except RuntimeError:
            # No running loop, we can use asyncio.run directly
            return asyncio.run(
                generate_roadmap_with_gemini(
                    issue_title, issue_body, category, developer_skills, experience_level
                )
            )
            
    except Exception as e:
        print(f"    ⚠️ Error in roadmap generation: {e}")
        # Fallback to basic roadmap
        return generate_fallback_roadmap(issue_title, category, developer_skills)


def generate_fallback_roadmap(issue_title: str, category: str, developer_skills: List[str]) -> str:
    """Generate a basic roadmap when Gemini API is unavailable"""
    
    category_steps = {
        "Frontend/UI": [
            "🎨 Design and plan UI components",
            "⚛️ Set up component structure",
            "🎯 Implement core functionality", 
            "📱 Add responsive design",
            "✨ Add animations and interactions",
            "🧪 Write unit tests",
            "📖 Update documentation"
        ],
        "Backend/API": [
            "📋 Design API endpoints and data models",
            "🏗️ Set up database schema",
            "⚙️ Implement core business logic",
            "🔒 Add authentication and validation",
            "📊 Add logging and monitoring",
            "🧪 Write integration tests",
            "📖 Update API documentation"
        ],
        "Mobile": [
            "📱 Design mobile-first UI",
            "🏗️ Set up navigation structure", 
            "⚙️ Implement core features",
            "🔄 Add offline capabilities",
            "🧪 Test on multiple devices",
            "📦 Prepare for app store",
            "📖 Update user documentation"
        ]
    }
    
    steps = category_steps.get(category, [
        "📋 Analyze requirements",
        "🏗️ Plan implementation approach", 
        "⚙️ Implement core functionality",
        "🧪 Write comprehensive tests",
        "📖 Update documentation"
    ])
    
    skills_text = f"**Relevant Skills:** {', '.join(developer_skills[:5])}" if developer_skills else ""
    
    roadmap = f"""## 🗺️ Development Roadmap

**Task:** {issue_title}
**Category:** {category}
{skills_text}

### Implementation Steps:

"""
    
    for i, step in enumerate(steps, 1):
        roadmap += f"{i}. {step}\n"
    
    roadmap += f"""
### 💡 Tips:
- Break down complex tasks into smaller commits
- Test frequently during development
- Ask for code review before merging
- Update tests when adding new features

**Estimated Complexity:** Medium | **Suggested Timeline:** 2-5 days

---
*Generated by Smart Bug Triage Agent 🤖*"""
    
    return roadmap


# Models
class Developer(BaseModel):
    id: str
    name: str
    github_username: str
    email: str
    skills: List[str]
    experience_level: str
    max_capacity: int
    workload: int
    available: bool
    current_issues: List[int]
    contributions: int
    source_type: str

class Assignment(BaseModel):
    timestamp: str
    issue_id: str
    issue_number: int
    issue_title: str
    issue_url: str
    assigned_to: str
    real_name: str
    developer_id: str
    source_type: str
    category: str
    confidence: float
    assignment_score: float
    github_profile: str
    real_contributions: int
    is_real_developer: bool
    github_assigned: bool

class SystemStatus(BaseModel):
    is_running: bool
    current_repo: Optional[str]
    total_developers: int
    total_assignments: int
    contributors_count: int
    collaborators_count: int
    both_count: int
    last_updated: Optional[str]
    error: Optional[str]

class StartPipelineRequest(BaseModel):
    repo_name: str

# Helper function to fetch developers using agents
def fetch_developers_and_collaborators(repo_name: str):
    """Fetch real contributors and collaborators from repository using agents."""
    try:
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            raise Exception("GITHUB_TOKEN not found")
        
        # Initialize GitHub client
        github_client = GitHubAPIClient(token=github_token)
        pipeline_state["github_client"] = github_client
        
        if not github_client.test_connection():
            raise Exception("GitHub connection failed")
        
        # Fetch contributors and collaborators
        repo = github_client.github.get_repo(repo_name)
        contributors = list(repo.get_contributors())
        collaborators = list(repo.get_collaborators())
        
        contributor_data = {}
        for contributor in contributors:
            try:
                user = github_client.github.get_user(contributor.login)
                contributor_data[contributor.login] = {
                    'user': user,
                    'contributions': contributor.contributions,
                    'type': 'contributor'
                }
            except:
                continue
        
        collaborator_data = {}
        for collab in collaborators:
            try:
                user = github_client.github.get_user(collab.login)
                collaborator_data[collab.login] = {
                    'user': user,
                    'permissions': collab.permissions,
                    'type': 'collaborator'
                }
            except:
                continue
        
        # Merge developers
        all_usernames = set(contributor_data.keys()) | set(collaborator_data.keys())
        
        developers_list = []
        developer_statuses = {}
        developer_profiles = {}  # Store DeveloperProfile objects
        
        for username in all_usernames:
            try:
                is_contributor = username in contributor_data
                is_collaborator = username in collaborator_data
                
                if is_contributor and is_collaborator:
                    source_type = "Both"
                    user = contributor_data[username]['user']
                    contributions = contributor_data[username]['contributions']
                elif is_contributor:
                    source_type = "Contributor"
                    user = contributor_data[username]['user']
                    contributions = contributor_data[username]['contributions']
                else:
                    source_type = "Collaborator"
                    user = collaborator_data[username]['user']
                    contributions = 0
                
                # Analyze skills using enhanced function
                skills = analyze_skills(user)
                
                # Enhanced parameters for activity analysis
                from datetime import datetime, timedelta
                six_months_ago = datetime.now() - timedelta(days=180)
                recent_commits = 0
                pr_count = 0
                issue_count = 0
                review_count = 0
                
                try:
                    events = list(user.get_events()[:100])
                    recent_commits = sum(1 for event in events 
                                         if event.type == 'PushEvent' and 
                                         event.created_at > six_months_ago)
                    pr_count = sum(1 for event in events if event.type == 'PullRequestEvent')
                    issue_count = sum(1 for event in events if event.type == 'IssuesEvent')
                    review_count = sum(1 for event in events if event.type == 'PullRequestReviewEvent')
                except:
                    recent_commits = contributions
                
                # Recency score
                recency_score = 0.5
                try:
                    if events:
                        days_since_activity = (datetime.now() - events[0].created_at).days
                        recency_score = max(0, 1 - (days_since_activity / 180))
                except:
                    pass
                
                developer_id = f"real_{username}"
                
                # Determine experience level using activity score
                activity_score = contributions + (pr_count * 2) + (review_count * 3)
                if activity_score >= 20 or contributions >= 10:
                    experience = "Senior"
                    max_capacity = 5
                elif activity_score >= 10 or contributions >= 5:
                    experience = "Mid-level"
                    max_capacity = 4
                else:
                    experience = "Junior"
                    max_capacity = 3
                
                # Create DeveloperProfile object for assignment algorithm
                developer_profile = DeveloperProfile(
                    id=developer_id,
                    name=user.name or username,
                    github_username=username,
                    email=user.email or f"{username}@github.local",
                    skills=skills,
                    experience_level=experience,
                    max_capacity=max_capacity,
                    preferred_categories=[BugCategory.UNKNOWN],  # Default preference
                    timezone="UTC"  # Default timezone
                )
                
                # Store profile for assignment algorithm
                developer_profiles[developer_id] = developer_profile
                
                # Create developer dict for API response
                developer = {
                    "id": developer_id,
                    "name": user.name or username,
                    "github_username": username,
                    "email": user.email or f"{username}@github.local",
                    "skills": skills,
                    "experience_level": experience,
                    "max_capacity": max_capacity,
                    "workload": 0,
                    "available": True,
                    "current_issues": [],
                    "contributions": contributions,
                    "source_type": source_type,
                    "recent_commits": recent_commits,
                    "pr_count": pr_count,
                    "issue_count": issue_count,
                    "review_count": review_count,
                    "recency_score": recency_score,
                    "activity_score": activity_score
                }
                
                developers_list.append(developer)
                
                # Create DeveloperStatus for assignment algorithm
                developer_statuses[developer_id] = {
                    "workload": 0,
                    "available": True,
                    "current_issues": [],
                    "contributions": contributions,
                    "source_type": source_type,
                    "recent_commits": recent_commits,
                    "recency_score": recency_score
                }
                
            except Exception as e:
                print(f"Error processing {username}: {e}")
                continue
        
        # Store developer profiles in pipeline state
        pipeline_state["developer_profiles"] = developer_profiles
        
        print(f"✅ Successfully loaded {len(developers_list)} developers")
        return developers_list, developer_statuses
        
    except Exception as e:
        print(f"❌ Error fetching developers: {e}")
        import traceback
        traceback.print_exc()
        raise Exception(f"Failed to fetch developers: {str(e)}")

def analyze_skills(user):
    """Enhanced skill analysis by scanning recent commits and repositories."""
    try:
        print(f"    📊 Analyzing skills for {user.login}...")
        
        # Language to skill mapping (from DeveloperDiscoveryService)
        language_skills = {
            'python': ['Python', 'Backend', 'API', 'Data Science'],
            'javascript': ['JavaScript', 'Frontend', 'Web Development'],
            'typescript': ['TypeScript', 'Frontend', 'Backend', 'Full Stack'],
            'java': ['Java', 'Backend', 'Enterprise', 'API'],
            'go': ['Go', 'Backend', 'Microservices', 'Performance'],
            'rust': ['Rust', 'Systems', 'Performance', 'Security'],
            'c++': ['C++', 'Systems', 'Performance', 'Low Level'],
            'c#': ['C#', 'Backend', '.NET', 'Enterprise'],
            'php': ['PHP', 'Backend', 'Web Development'],
            'ruby': ['Ruby', 'Backend', 'Web Development'],
            'swift': ['Swift', 'iOS', 'Mobile'],
            'kotlin': ['Kotlin', 'Android', 'Mobile', 'Backend'],
            'dart': ['Dart', 'Flutter', 'Mobile'],
            'html': ['HTML', 'Frontend', 'Web Development'],
            'css': ['CSS', 'Frontend', 'UI/UX'],
            'sql': ['SQL', 'Database', 'Data Analysis'],
            'shell': ['Shell', 'DevOps', 'Automation'],
            'dockerfile': ['Docker', 'DevOps', 'Containerization'],
            'yaml': ['YAML', 'DevOps', 'Configuration'],
            'json': ['JSON', 'API', 'Configuration'],
            'r': ['R', 'Data Science', 'Statistics'],
            'scala': ['Scala', 'Backend', 'Big Data'],
            'perl': ['Perl', 'Backend', 'Automation']
        }
        
        # File extension to language mapping
        extension_map = {
            '.py': 'python', '.pyx': 'python', '.pyw': 'python',
            '.js': 'javascript', '.jsx': 'javascript', '.mjs': 'javascript',
            '.ts': 'typescript', '.tsx': 'typescript',
            '.java': 'java',
            '.go': 'go',
            '.rs': 'rust',
            '.cpp': 'c++', '.cc': 'c++', '.cxx': 'c++', '.c++': 'c++',
            '.c': 'c',
            '.cs': 'c#',
            '.php': 'php', '.phtml': 'php',
            '.rb': 'ruby',
            '.swift': 'swift',
            '.kt': 'kotlin', '.kts': 'kotlin',
            '.dart': 'dart',
            '.html': 'html', '.htm': 'html',
            '.css': 'css', '.scss': 'css', '.sass': 'css', '.less': 'css',
            '.sql': 'sql',
            '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell', '.fish': 'shell',
            '.dockerfile': 'dockerfile',
            '.yaml': 'yaml', '.yml': 'yaml',
            '.json': 'json',
            '.xml': 'xml',
            '.r': 'r',
            '.scala': 'scala',
            '.pl': 'perl', '.pm': 'perl'
        }
        
        # Framework detection patterns
        framework_patterns = {
            'react': ['React', 'Frontend', 'JavaScript'],
            'vue': ['Vue.js', 'Frontend', 'JavaScript'],
            'angular': ['Angular', 'Frontend', 'TypeScript'],
            'django': ['Django', 'Backend', 'Python'],
            'flask': ['Flask', 'Backend', 'Python'],
            'fastapi': ['FastAPI', 'Backend', 'Python'],
            'express': ['Express.js', 'Backend', 'JavaScript'],
            'spring': ['Spring', 'Backend', 'Java'],
            'laravel': ['Laravel', 'Backend', 'PHP'],
            'rails': ['Ruby on Rails', 'Backend', 'Ruby'],
            'docker': ['Docker', 'DevOps', 'Containerization'],
            'kubernetes': ['Kubernetes', 'DevOps', 'Orchestration'],
            'terraform': ['Terraform', 'DevOps', 'Infrastructure'],
            'aws': ['AWS', 'Cloud', 'DevOps'],
            'azure': ['Azure', 'Cloud', 'DevOps'],
            'gcp': ['GCP', 'Cloud', 'DevOps'],
            'tensorflow': ['TensorFlow', 'ML/AI', 'Python'],
            'pytorch': ['PyTorch', 'ML/AI', 'Python'],
            'pandas': ['Pandas', 'Data Science', 'Python'],
            'numpy': ['NumPy', 'Data Science', 'Python'],
            'redis': ['Redis', 'Database', 'Caching'],
            'postgresql': ['PostgreSQL', 'Database', 'SQL'],
            'mongodb': ['MongoDB', 'Database', 'NoSQL'],
            'elasticsearch': ['Elasticsearch', 'Database', 'Search']
        }
        
        # Step 1: Analyze recent commits (last 5-10 commits)
        language_count_from_commits = {}
        framework_skills = set()
        total_commits_analyzed = 0
        
        try:
            repos = list(user.get_repos()[:5])  # Analyze top 5 repos
            print(f"       📁 Scanning {len(repos)} repositories...")
            
            for repo in repos:
                try:
                    # Get recent commits (last 8 per repo)
                    commits = list(repo.get_commits()[:8])
                    
                    for commit in commits:
                        try:
                            total_commits_analyzed += 1
                            if total_commits_analyzed > 50:  # Limit total commits analyzed
                                break
                                
                            # Analyze files in each commit
                            if hasattr(commit, 'files'):
                                for file in commit.files:
                                    filename = file.filename.lower()
                                    
                                    # Extract language from file extension
                                    for ext, lang in extension_map.items():
                                        if filename.endswith(ext):
                                            # Weight by lines added/changed
                                            lines_changed = (file.additions or 0) + (file.changes or 0)
                                            weight = max(lines_changed, 1)  # Minimum weight of 1
                                            
                                            if lang not in language_count_from_commits:
                                                language_count_from_commits[lang] = 0
                                            language_count_from_commits[lang] += weight
                                            break
                                    
                                    # Check for framework patterns in filename
                                    for pattern, skills in framework_patterns.items():
                                        if pattern in filename:
                                            framework_skills.update(skills)
                            
                        except Exception as e:
                            continue
                            
                    if total_commits_analyzed > 50:
                        break
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            print(f"       ⚠️ Could not analyze commits: {e}")
        
        print(f"       📈 Analyzed {total_commits_analyzed} commits")
        
        # Step 2: Supplement with repository languages (for broader context)
        language_count_from_repos = {}
        try:
            repos = list(user.get_repos()[:15])
            for repo in repos:
                try:
                    repo_languages = repo.get_languages()
                    for lang, bytes_count in repo_languages.items():
                        lang_lower = lang.lower()
                        if lang_lower not in language_count_from_repos:
                            language_count_from_repos[lang_lower] = 0
                        language_count_from_repos[lang_lower] += bytes_count
                        
                        # Check repository for frameworks
                        try:
                            contents = repo.get_contents("")
                            files_to_check = [content.name.lower() for content in contents[:20] if hasattr(content, 'name')]
                            
                            for filename in files_to_check:
                                # Check for specific configuration files
                                if 'package.json' in filename:
                                    framework_skills.update(['Node.js', 'JavaScript'])
                                elif 'requirements.txt' in filename or 'pyproject.toml' in filename:
                                    framework_skills.update(['Python Package Management', 'Python'])
                                elif 'pom.xml' in filename or 'build.gradle' in filename:
                                    framework_skills.update(['Java Build Tools', 'Java'])
                                elif 'dockerfile' in filename:
                                    framework_skills.update(['Docker', 'DevOps'])
                                elif 'docker-compose' in filename:
                                    framework_skills.update(['Docker Compose', 'DevOps'])
                                elif '.github/workflows' in filename or 'github/workflows' in filename:
                                    framework_skills.update(['GitHub Actions', 'DevOps'])
                                
                                # Framework patterns
                                for pattern, skills in framework_patterns.items():
                                    if pattern in filename:
                                        framework_skills.update(skills)
                        except:
                            pass
                            
                except Exception as e:
                    continue
        except Exception as e:
            print(f"       ⚠️ Could not analyze repositories: {e}")
        
        # Step 3: Combine commit-based and repo-based analysis
        # Prioritize commit-based analysis (more recent and accurate)
        combined_language_count = {}
        
        # Add commit-based languages with higher weight
        for lang, count in language_count_from_commits.items():
            combined_language_count[lang] = count * 3  # 3x weight for commit-based
        
        # Add repo-based languages with lower weight
        for lang, bytes_count in language_count_from_repos.items():
            # Normalize bytes to reasonable numbers
            normalized_count = min(bytes_count // 1000, 100)  # Scale down large byte counts
            if lang in combined_language_count:
                combined_language_count[lang] += normalized_count
            else:
                combined_language_count[lang] = normalized_count
        
        # Step 4: Convert to skills
        all_skills = set()
        
        if combined_language_count:
            # Sort languages by usage
            sorted_languages = sorted(combined_language_count.items(), key=lambda x: x[1], reverse=True)
            total_usage = sum(combined_language_count.values())
            
            print(f"       🔍 Top languages detected: {', '.join([f'{lang}({count})' for lang, count in sorted_languages[:5]])}")
            
            # Add skills from languages based on usage percentage
            for lang, count in sorted_languages:
                usage_percentage = (count / total_usage) * 100 if total_usage > 0 else 0
                
                if lang in language_skills:
                    lang_skills = language_skills[lang]
                    
                    if usage_percentage >= 15:  # Primary language (>15%)
                        all_skills.update(lang_skills)
                    elif usage_percentage >= 5:   # Secondary language (5-15%)
                        # Add specific skills but not general categories
                        specific_skills = [skill for skill in lang_skills 
                                         if skill not in ['Backend', 'Frontend', 'Web Development']]
                        all_skills.update(specific_skills)
                    else:  # Minor language (<5%)
                        # Add only the language name itself
                        all_skills.add(lang_skills[0] if lang_skills else lang.title())
        
        # Add framework skills
        all_skills.update(framework_skills)
        
        # Step 5: Fallback if no skills detected
        if not all_skills:
            print(f"       ⚠️ No skills detected, using fallback")
            all_skills = {'Python', 'JavaScript', 'Backend', 'Frontend'}
        
        # Step 6: Prioritize and limit skills
        skills_list = list(all_skills)
        
        def skill_priority(skill):
            # Primary languages get highest priority
            if skill in ['Python', 'JavaScript', 'TypeScript', 'Java', 'Go', 'C++']:
                return 0
            # Popular frameworks
            elif skill in ['React', 'Django', 'Flask', 'Spring', 'Express.js', 'Vue.js']:
                return 1
            # Infrastructure and tools
            elif skill in ['Docker', 'Kubernetes', 'AWS', 'PostgreSQL', 'MongoDB']:
                return 2
            # General categories
            elif skill in ['Backend', 'Frontend', 'DevOps', 'Database', 'API']:
                return 3
            else:
                return 4
        
        skills_list.sort(key=skill_priority)
        final_skills = skills_list[:12]  # Top 12 skills
        
        print(f"       ✅ Final skills: {', '.join(final_skills[:8])}...")
        return final_skills
        
    except Exception as e:
        print(f"       ❌ Error analyzing skills: {e}")
        return ['Python', 'JavaScript', 'Backend', 'Frontend']

def calculate_developer_fit_score(developer, required_skills, dev_status):
    """
    Calculates a nuanced developer fit score based on multiple factors.
    """
    # Weights for different factors
    W_SKILL = 0.50
    W_ACTIVITY = 0.25
    W_EXPERIENCE = 0.15
    W_WORKLOAD = -0.10 # Negative weight for workload

    # 1. Skill Score (0 to 1)
    if not required_skills:
        skill_score = 0.5 # Neutral score if no skills are required
    else:
        matches = sum(1 for skill in required_skills if skill in developer['skills'])
        skill_score = matches / len(required_skills)

    # 2. Activity Score (0 to 1) - Combines recency and total contributions
    recency = dev_status.get('recency_score', 0.5)
    contributions = dev_status.get('contributions', 0)
    # Use log to prevent massive contribution numbers from dominating and normalize
    # Normalizes score so 100 contributions is ~1.0, handles outliers gracefully
    activity_score = recency * (math.log1p(contributions) / math.log1p(100))
    activity_score = min(activity_score, 1.0) # Cap at 1.0

    # 3. Experience Score (0 to 1)
    exp_map = {'Junior': 0.3, 'Mid-level': 0.7, 'Senior': 1.0}
    experience_score = exp_map.get(developer['experience_level'], 0.5)

    # 4. Workload Score (0 to 1) - higher is worse
    workload = dev_status.get('workload', 0)
    max_capacity = developer.get('max_capacity', 5)
    if max_capacity == 0:
        workload_score = 1.0 # Fully loaded if capacity is zero
    else:
        # Penalize going over capacity more heavily
        workload_score = (workload / max_capacity) ** 1.5

    # Final weighted score
    final_score = (
        (skill_score * W_SKILL) +
        (activity_score * W_ACTIVITY) +
        (experience_score * W_EXPERIENCE) +
        (workload_score * W_WORKLOAD) # Applying negative weight
    )
    return final_score

def assign_issue_on_github(github_client, repo_name, issue, developer, category, confidence, score, source_type):
    """Assign issue to developer on GitHub with detailed comment and roadmap."""
    try:
        # Get repository and issue
        repo = github_client.github.get_repo(repo_name)
        github_issue = repo.get_issue(issue.number)
        
        # Remove all existing assignees to ensure only one assignee
        current_assignees = [assignee.login for assignee in github_issue.assignees]
        if current_assignees:
            github_issue.remove_from_assignees(*current_assignees)
            print(f"                 🗑️  Removed existing assignees: {', '.join(current_assignees)}")
        
        # Add the new assignee
        github_issue.add_to_assignees(developer['github_username'])
        
        # Generate intelligent roadmap using Gemini
        print(f"                 🗺️ Generating roadmap with Gemini...")
        
        # Generate roadmap synchronously using a helper function
        roadmap = generate_roadmap_sync(
            issue_title=issue.title,
            issue_body=issue.body or "",
            category=category,
            developer_skills=developer['skills'],
            experience_level=developer['experience_level']
        )
        
        # Prepare assignment comment with emoji
        source_emoji = {
            "Both": "👤+🤝",
            "Contributor": "👤",
            "Collaborator": "🤝"
        }
        
        comment = f"""🤖 **AI Bug Triage Assignment**

**Assigned to:** [{developer['name']}](https://github.com/{developer['github_username']}) {source_emoji.get(source_type, '')}
**Role:** {developer['experience_level']}

**Analysis:**
- **Category:** {category}
- **Confidence:** {confidence:.2%}
- **Assignment Score:** {score:.3f}
- **Skills Match:** {', '.join(developer['skills'][:5])}

**Why this assignment:**
This issue has been automatically triaged and assigned based on:
1. Skill matching with required expertise
2. Current workload and availability
3. Past contribution history ({pipeline_state['developer_statuses'][developer['id']]['contributions']} contributions)
4. Experience level

This developer was selected from real repository {source_type.lower()}s using AI-powered analysis.

---

{roadmap}

---
*Assigned by Smart Bug Triage Agent 🎯*"""
        
        # Post comment
        github_issue.create_comment(comment)
        
        # Add label
        try:
            github_issue.add_to_labels("🤖 ai-assigned")
        except:
            # Label might not exist, create or skip
            pass
        
        print(f"                 ✅ Successfully assigned on GitHub with AI roadmap!")
        return True
        
    except Exception as e:
        print(f"                 ❌ Failed to assign on GitHub: {e}")
        return False

async def monitor_issues_background():
    """Background task to monitor issues and make assignments using agents."""
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ No GITHUB_TOKEN found")
        return
    
    # Use existing github_client or create new one
    github_client = pipeline_state.get("github_client") or GitHubAPIClient(token=github_token)
    
    # Initialize NLP Pipeline
    nlp_pipeline = NLPPipeline()
    pipeline_state["nlp_pipeline"] = nlp_pipeline
    
    # Initialize Assignment Algorithm
    assignment_algorithm = AssignmentAlgorithm()
    pipeline_state["assignment_algorithm"] = assignment_algorithm
    
    print("🔄 Starting issue monitoring background task with agents...")
    print(f"    Loaded {len(pipeline_state['developers'])} developers")
    print(f"    Loaded {len(pipeline_state['developer_profiles'])} developer profiles")
    
    while pipeline_state["is_running"]:
        try:
            repo_name = pipeline_state["current_repo"]
            if not repo_name:
                print("⚠️ No repo name set, waiting...")
                await asyncio.sleep(10)
                continue
            
            print(f"🔍 Checking issues for {repo_name}...")
            
            # Fetch issues
            repo = github_client.github.get_repo(repo_name)
            issues = list(repo.get_issues(state='open'))
            
            print(f"    Found {len(issues)} open issues")
            
            new_issues = []
            for issue in issues:
                issue_id = f"github_{issue.id}"
                if issue_id not in pipeline_state["processed_issues"]:
                    new_issues.append(issue)
                    pipeline_state["processed_issues"].add(issue_id)
            
            if new_issues:
                print(f"🆕 Found {len(new_issues)} new issues")
                
                for issue in new_issues:
                    print(f"📋 Processing issue #{issue.number}: {issue.title}")
                    
                    # Create bug report
                    bug_report = BugReport(
                        id=f"github_{issue.id}",
                        title=issue.title,
                        description=issue.body or "No description provided",
                        reporter=issue.user.login,
                        created_at=issue.created_at,
                        platform="github",
                        url=issue.html_url,
                        labels=[label.name for label in issue.labels],
                        raw_data={'issue_number': issue.number}
                    )
                    
                    # AI Analysis using NLP Pipeline with enhanced rule-based fallback
                    analysis = nlp_pipeline.analyze_bug_report(bug_report.title, bug_report.description)
                    category_str = analysis.get('classification', {}).get('category', 'General')
                    confidence = analysis.get('classification', {}).get('confidence', 0.5)
                    
                    # Enhanced rule-based category detection for better accuracy
                    issue_text = f"{issue.title} {issue.body or ''}".lower()
                    labels_text = ' '.join([label.name.lower() for label in issue.labels])
                    combined_text = f"{issue_text} {labels_text}"
                    
                    # Initialize variables
                    category_str_normalized = category_str  # Default to NLP result
                    
                    # Rule-based category detection patterns
                    category_patterns = {
                        'Frontend/UI': [
                            # UI/Frontend keywords
                            r'\b(frontend|front-end|ui|ux|user interface|user experience)\b',
                            r'\b(react|vue|angular|svelte|next\.?js|nuxt)\b',
                            r'\b(javascript|typescript|js|ts|jsx|tsx)\b',
                            r'\b(html|css|scss|sass|tailwind|bootstrap)\b',
                            r'\b(component|render|display|layout|style|styling)\b',
                            r'\b(browser|chrome|firefox|safari|responsive|mobile)\b',
                            r'\b(dom|element|button|form|input|modal|dropdown)\b',
                            r'\b(animation|transition|hover|click|event)\b',
                            # Page and UI elements
                            r'\b(page|landing page|homepage|website|web page)\b',
                            r'\b(navbar|navigation|menu|sidebar|header|footer)\b',
                            r'\b(card|banner|hero|section|container|grid)\b',
                            r'\b(design|theme|template|layout|visual|appearance)\b',
                            r'\b(widget|dashboard|interface|screen|view)\b',
                            r'\b(icon|image|logo|gallery|carousel|slider)\b',
                            # User interaction
                            r'\b(user|client|visitor|customer|guest)\b',
                            r'\b(interactive|usability|accessibility|responsive)\b',
                            r'\b(loading|spinner|toast|notification|alert)\b',
                            # Web technologies
                            r'\b(webpack|vite|parcel|rollup|babel)\b',
                            r'\b(spa|single page|progressive web|pwa)\b',
                            # Labels
                            r'\b(frontend|ui|ux|javascript|react|vue|angular|design|website)\b'
                        ],
                        'Backend/API': [
                            # Backend/API keywords
                            r'\b(backend|back-end|api|server|endpoint|route)\b',
                            r'\b(python|java|go|rust|php|ruby|c#|node\.?js)\b',
                            r'\b(django|flask|fastapi|spring|express|laravel|rails)\b',
                            r'\b(rest|graphql|http|https|json|xml|response|request)\b',
                            r'\b(authentication|authorization|auth|login|token|jwt)\b',
                            r'\b(middleware|controller|service|model|orm)\b',
                            r'\b(microservice|monolith|scaling|performance)\b',
                            # Labels
                            r'\b(backend|api|server|python|java|django|flask)\b'
                        ],
                        'Database': [
                            # Database keywords
                            r'\b(database|db|sql|query|schema|table|collection)\b',
                            r'\b(postgresql|postgres|mysql|mongodb|redis|elasticsearch)\b',
                            r'\b(migration|seed|index|foreign key|primary key)\b',
                            r'\b(orm|sequelize|mongoose|prisma|typeorm)\b',
                            r'\b(transaction|commit|rollback|backup|restore)\b',
                            r'\b(connection|pool|timeout|deadlock|constraint)\b',
                            # Labels
                            r'\b(database|db|sql|postgresql|mysql|mongodb)\b'
                        ],
                        'Mobile': [
                            # Mobile keywords
                            r'\b(mobile|android|ios|iphone|ipad|tablet|app)\b',
                            r'\b(swift|kotlin|dart|flutter|react native|xamarin)\b',
                            r'\b(app store|play store|mobile app|native)\b',
                            r'\b(touch|gesture|swipe|tap|orientation)\b',
                            r'\b(push notification|camera|gps|location)\b',
                            # Labels
                            r'\b(mobile|android|ios|flutter|react-native|kotlin)\b'
                        ],
                        'DevOps': [
                            # DevOps keywords
                            r'\b(devops|deployment|deploy|ci/cd|pipeline|build)\b',
                            r'\b(docker|kubernetes|k8s|container|orchestration)\b',
                            r'\b(aws|azure|gcp|cloud|infrastructure|terraform)\b',
                            r'\b(jenkins|github actions|gitlab ci|travis|circleci)\b',
                            r'\b(monitoring|logging|metrics|prometheus|grafana)\b',
                            r'\b(nginx|apache|load balancer|proxy|ssl|https)\b',
                            # Labels
                            r'\b(devops|deployment|docker|kubernetes|ci|cd)\b'
                        ],
                        'Security': [
                            # Security keywords
                            r'\b(security|vulnerability|exploit|hack|breach)\b',
                            r'\b(xss|csrf|sql injection|authentication|authorization)\b',
                            r'\b(encryption|ssl|tls|certificate|oauth|jwt)\b',
                            r'\b(password|credential|token|session|privacy)\b',
                            r'\b(firewall|vpn|penetration test|audit)\b',
                            # Labels
                            r'\b(security|vulnerability|auth|encryption)\b'
                        ],
                        'ML/AI': [
                            # ML/AI keywords
                            r'\b(machine learning|ml|artificial intelligence|ai|deep learning)\b',
                            r'\b(tensorflow|pytorch|scikit|keras|pandas|numpy)\b',
                            r'\b(model|training|prediction|classification|regression)\b',
                            r'\b(neural network|algorithm|dataset|feature|pipeline)\b',
                            r'\b(jupyter|notebook|data science|analytics)\b',
                            # Labels
                            r'\b(ml|ai|machine-learning|data-science|tensorflow)\b'
                        ],
                        'Performance': [
                            # Performance keywords
                            r'\b(performance|optimization|slow|speed|latency|throughput)\b',
                            r'\b(memory|cpu|ram|disk|cache|caching)\b',
                            r'\b(load time|response time|benchmark|profiling)\b',
                            r'\b(bottleneck|scalability|scaling|concurrency)\b',
                            r'\b(compression|minification|bundling|lazy loading)\b',
                            # Labels
                            r'\b(performance|optimization|slow|memory|cache)\b'
                        ]
                    }
                    
                    # Score each category based on pattern matches
                    category_scores = {}
                    
                    for category, patterns in category_patterns.items():
                        score = 0
                        matches = []
                        
                        for pattern in patterns:
                            pattern_matches = re.findall(pattern, combined_text)
                            match_count = len(pattern_matches)
                            if match_count > 0:
                                score += match_count
                                matches.extend(pattern_matches)
                        
                        if score > 0:
                            category_scores[category] = {
                                'score': score,
                                'matches': list(set(matches))  # Remove duplicates
                            }
                    
                    # Determine best category
                    if category_scores:
                        # Sort by score
                        sorted_categories = sorted(category_scores.items(), key=lambda x: x[1]['score'], reverse=True)
                        best_category = sorted_categories[0][0]
                        best_score = sorted_categories[0][1]['score']
                        matches = sorted_categories[0][1]['matches']
                        
                        # Use rule-based result if it has good confidence
                        if best_score >= 2:  # At least 2 matches for confidence
                            category_str_normalized = best_category
                            confidence = min(0.95, 0.6 + (best_score * 0.1))  # Scale confidence
                            print(f"    🎯 Rule-based detection: {best_category} (score: {best_score}, matches: {matches[:3]})")
                        else:
                            # Use Gemini AI for better categorization
                            print(f"    🤖 Using Gemini AI for categorization (rule-based score too low: {best_score})")
                            gemini_result = await categorize_with_gemini(
                                issue_title=issue.title,
                                issue_body=issue.body or "",
                                labels=[label.name for label in issue.labels]
                            )
                            
                            if gemini_result['confidence'] > 0.7:
                                category_str_normalized = gemini_result['category']
                                confidence = gemini_result['confidence']
                                print(f"    ✅ Gemini high confidence: {category_str_normalized} ({confidence:.2f})")
                            else:
                                # Fall back to NLP result with normalization
                                category_str_normalized = 'General'
                                print(f"    ⚠️ Low confidence from all methods, using General")
                    else:
                        # No patterns matched, use Gemini AI
                        print(f"    🤖 No rule patterns matched, using Gemini AI")
                        gemini_result = await categorize_with_gemini(
                            issue_title=issue.title,
                            issue_body=issue.body or "",
                            labels=[label.name for label in issue.labels]
                        )
                        
                        if gemini_result['confidence'] > 0.6:
                            category_str_normalized = gemini_result['category']
                            confidence = gemini_result['confidence']
                            print(f"    ✅ Gemini categorization: {category_str_normalized} ({confidence:.2f})")
                        else:
                            category_str_normalized = 'General'
                            print(f"    ❌ Low confidence from all methods, using General")
                    # Map string category to BugCategory enum
                    category_mapping = {
                        'Backend/API': BugCategory.BACKEND,
                        'Frontend/UI': BugCategory.FRONTEND,
                        'Database': BugCategory.DATABASE,
                        'Mobile': BugCategory.MOBILE,
                        'DevOps': BugCategory.PERFORMANCE,  # Map DevOps to PERFORMANCE
                        'ML/AI': BugCategory.BACKEND,  # Map ML/AI to BACKEND
                        'Security': BugCategory.SECURITY,
                        'Performance': BugCategory.PERFORMANCE,
                        'Documentation': BugCategory.UNKNOWN,  # Map Documentation to UNKNOWN
                        'Testing': BugCategory.UNKNOWN,  # Map Testing to UNKNOWN
                        'General': BugCategory.UNKNOWN
                    }
                    category = category_mapping.get(category_str_normalized, BugCategory.UNKNOWN)
                    
                    print(f"    🧠 Final Analysis: {category_str} → {category_str_normalized} (confidence: {confidence:.2f})")
                    
                    # Extract keywords from analysis
                    keywords = analysis.get('skills', [])
                    if not keywords:
                        keywords = category_str.split('/')
                    
                    # Create CategorizedBug for assignment algorithm
                    categorized_bug = CategorizedBug(
                        bug_report=bug_report,
                        category=category,
                        severity=Priority.MEDIUM,  # Default severity
                        keywords=keywords,
                        confidence_score=confidence,
                        analysis_timestamp=datetime.now()
                    )
                    
                    # Enhanced category to skills mapping (using NLP-like analysis)
                    enhanced_category_skills = {
                        'Backend/API': [
                            'Python', 'Java', 'Go', 'Node.js', 'C#', 'PHP', 'Ruby',
                            'Django', 'Flask', 'FastAPI', 'Spring', 'Express.js', 'Laravel',
                            'API', 'REST', 'GraphQL', 'Backend', 'Microservices'
                        ],
                        'Frontend/UI': [
                            'JavaScript', 'TypeScript', 'React', 'Vue.js', 'Angular', 'Svelte',
                            'HTML', 'CSS', 'SCSS', 'Tailwind', 'Bootstrap', 'Next.js', 'Nuxt.js',
                            'Frontend', 'UI/UX', 'Web Development'
                        ],
                        'Database': [
                            'SQL', 'PostgreSQL', 'MySQL', 'MongoDB', 'Redis', 'Elasticsearch',
                            'Database', 'NoSQL', 'Data Modeling', 'Query Optimization',
                            'Python', 'Java', 'Backend'
                        ],
                        'Mobile': [
                            'Swift', 'Kotlin', 'Dart', 'React Native', 'Flutter', 'Xamarin',
                            'iOS', 'Android', 'Mobile', 'JavaScript', 'TypeScript'
                        ],
                        'DevOps': [
                            'Docker', 'Kubernetes', 'AWS', 'Azure', 'GCP', 'Terraform',
                            'Jenkins', 'GitHub Actions', 'CI/CD', 'DevOps', 'Infrastructure',
                            'Shell', 'Python', 'YAML'
                        ],
                        'ML/AI': [
                            'Python', 'TensorFlow', 'PyTorch', 'Scikit-learn', 'Pandas', 'NumPy',
                            'Machine Learning', 'Data Science', 'AI', 'Deep Learning',
                            'R', 'Jupyter', 'Statistics'
                        ],
                        'Security': [
                            'Security', 'Authentication', 'Authorization', 'Encryption', 'SSL/TLS',
                            'OAuth', 'JWT', 'Penetration Testing', 'Vulnerability Assessment',
                            'Python', 'Java', 'C++', 'Backend'
                        ],
                        'Performance': [
                            'Performance', 'Optimization', 'Caching', 'Load Testing',
                            'Profiling', 'Memory Management', 'C++', 'Go', 'Rust',
                            'Database', 'Backend', 'Systems Programming'
                        ],
                        'General': [
                            'Python', 'JavaScript', 'Java', 'Backend', 'Frontend',
                            'API', 'Database', 'Git', 'GitHub'
                        ]
                    }
                    
                    # Get base required skills from category
                    base_required_skills = enhanced_category_skills.get(category_str_normalized, enhanced_category_skills['General'])
                    
                    # Enhance with keyword extraction from NLP analysis
                    nlp_keywords = analysis.get('keywords', {})
                    
                    # Extract additional skills from various keyword sources
                    additional_skills = set()
                    
                    # From technical terms
                    if isinstance(nlp_keywords, dict):
                        for category_key, terms in nlp_keywords.items():
                            if isinstance(terms, list):
                                for term in terms:
                                    # Map common technical terms to skills
                                    term_lower = str(term).lower()
                                    if term_lower in ['python', 'java', 'javascript', 'typescript', 'go', 'rust', 'php', 'ruby']:
                                        additional_skills.add(term.title())
                                    elif term_lower in ['react', 'vue', 'angular', 'django', 'flask', 'spring', 'express']:
                                        additional_skills.add(term.title())
                                    elif term_lower in ['docker', 'kubernetes', 'aws', 'azure', 'terraform']:
                                        additional_skills.add(term.upper() if term_lower in ['aws'] else term.title())
                                    elif term_lower in ['sql', 'postgresql', 'mongodb', 'redis']:
                                        additional_skills.add(term.upper() if term_lower == 'sql' else term.title())
                    
                    # Extract from issue title and description using patterns
                    issue_text = f"{issue.title} {issue.body or ''}".lower()
                    
                    # Technology patterns to look for
                    tech_patterns = {
                        r'\b(python|py)\b': 'Python',
                        r'\b(javascript|js)\b': 'JavaScript',
                        r'\b(typescript|ts)\b': 'TypeScript',
                        r'\b(java)\b': 'Java',
                        r'\b(react|reactjs)\b': 'React',
                        r'\b(vue|vuejs)\b': 'Vue.js',
                        r'\b(angular)\b': 'Angular',
                        r'\b(django)\b': 'Django',
                        r'\b(flask)\b': 'Flask',
                        r'\b(fastapi)\b': 'FastAPI',
                        r'\b(express|expressjs)\b': 'Express.js',
                        r'\b(spring)\b': 'Spring',
                        r'\b(docker)\b': 'Docker',
                        r'\b(kubernetes|k8s)\b': 'Kubernetes',
                        r'\b(aws|amazon)\b': 'AWS',
                        r'\b(azure)\b': 'Azure',
                        r'\b(postgresql|postgres)\b': 'PostgreSQL',
                        r'\b(mongodb|mongo)\b': 'MongoDB',
                        r'\b(redis)\b': 'Redis',
                        r'\b(mysql)\b': 'MySQL',
                        r'\b(api|rest|graphql)\b': 'API',
                        r'\b(frontend|front-end|ui|frontend|uiux|design|ux|button)\b': 'Frontend',
                        r'\b(backend|back-end|server)\b': 'Backend',
                        r'\b(database|db)\b': 'Database',
                        r'\b(mobile|ios|android)\b': 'Mobile',
                        r'\b(ml|ai|machine learning|artificial intelligence)\b': 'ML/AI'
                    }
                    
                    for pattern, skill in tech_patterns.items():
                        if re.search(pattern, issue_text):
                            additional_skills.add(skill)
                    
                    # Combine base skills with extracted skills
                    all_required_skills = set(base_required_skills[:8])  # Take top 8 from category
                    all_required_skills.update(list(additional_skills)[:4])  # Add up to 4 extracted skills
                    
                    required_skills = list(all_required_skills)[:10]  # Limit to 10 total skills
                    
                    print(f"    🎯 Required Skills: {', '.join(required_skills[:5])}...")  # Show first 5
                    
                    # Get developer profiles and statuses for assignment algorithm
                    developer_profiles = list(pipeline_state["developer_profiles"].values())
                    
                    # Convert developer_statuses to DeveloperStatus objects
                    from smart_bug_triage.models.common import AvailabilityStatus
                    developer_status_objects = []
                    for dev_id, status in pipeline_state["developer_statuses"].items():
                        dev_status = DeveloperStatus(
                            developer_id=dev_id,
                            current_workload=status.get('workload', 0),
                            open_issues_count=len(status.get('current_issues', [])),
                            complexity_score=0.5,  # Default complexity
                            availability=AvailabilityStatus.AVAILABLE if status.get('available', True) else AvailabilityStatus.BUSY,
                            calendar_free=True,  # Default
                            focus_time_active=False,  # Default
                            last_activity_timestamp=datetime.now(),
                            last_updated=datetime.now()
                        )
                        developer_status_objects.append(dev_status)
                    
                    # Use Assignment Algorithm to find best developer
                    assignment_result = assignment_algorithm.find_best_developer(
                        bug=categorized_bug,
                        developers=developer_profiles,
                        developer_statuses=developer_status_objects,
                        feedback_history={}  # No historical feedback for now
                    )
                    
                    # Process assignment result or use fallback
                    if assignment_result and assignment_result.confidence_score >= 0.3:
                        best_developer_id = assignment_result.developer_id
                        best_score = assignment_result.confidence_score
                        reasoning = assignment_result.reasoning
                        print(f"    ✅ Algorithm selected developer with confidence {best_score:.2f}")
                    elif assignment_result:
                        # Use result but with warning
                        best_developer_id = assignment_result.developer_id
                        best_score = assignment_result.confidence_score
                        reasoning = f"Low confidence assignment: {assignment_result.reasoning}"
                        print(f"    ⚠️ Low confidence assignment ({best_score:.2f})")
                    else:
                        # Fallback: Improved developer scoring logic
                        print(f"    ⚠️ Algorithm found no match, using enhanced fallback logic...")
                        best_developer_id = None
                        best_score = 0.0
                        reasoning = "Fallback assignment based on skills, activity, and workload."
                        
                        available_devs = [
                            dev for dev in pipeline_state["developers"]
                            if pipeline_state["developer_statuses"][dev["id"]]["available"]
                        ]
                        
                        if available_devs:
                            # Sort by the new nuanced score
                            def score_dev_wrapper(dev):
                                dev_status = pipeline_state["developer_statuses"][dev["id"]]
                                return calculate_developer_fit_score(dev, required_skills, dev_status)

                            available_devs.sort(key=score_dev_wrapper, reverse=True)
                            best_dev = available_devs[0]
                            best_developer_id = best_dev["id"]
                            
                            # Use the calculated score for confidence
                            best_score = score_dev_wrapper(best_dev)
                            
                            reasoning = f"Fallback: Best fit. Score: {best_score:.3f}"
                            print(f"    ✅ Fallback assigned to {best_dev['github_username']} (score: {best_score:.2f})")
                    
                    # Find developer dict from developers list
                    if best_developer_id:
                        best_developer = None
                        for dev in pipeline_state["developers"]:
                            if dev["id"] == best_developer_id:
                                best_developer = dev
                                break
                        
                        if best_developer:
                            dev_status = pipeline_state["developer_statuses"][best_developer['id']]
                            print(f"        ✅ ASSIGNED TO: {best_developer['github_username']}")
                            print(f"            Real Name: {best_developer['name']}")
                            print(f"            Source: {dev_status['source_type']}")
                            print(f"            Assignment Score: {best_score:.3f}")
                            print(f"            Reasoning: {reasoning}")
                            print(f"            GitHub Profile: [https://github.com/](https://github.com/){best_developer['github_username']}")
                            print(f"            Real Contributions: {dev_status['contributions']}")
                            
                            # Assign on GitHub
                            github_assigned = assign_issue_on_github(
                                github_client, repo_name, issue, 
                                best_developer, category_str, confidence, best_score,
                                dev_status['source_type']
                            )
                            
                            assignment = {
                                'timestamp': datetime.now().isoformat(),
                                'issue_id': bug_report.id,
                                'issue_number': issue.number,
                                'issue_title': issue.title,
                                'issue_description': bug_report.description[:200] + '...' if len(bug_report.description) > 200 else bug_report.description,
                                'issue_url': issue.html_url,
                                'issue_labels': bug_report.labels,
                                'required_skills': required_skills,
                                'assigned_to': best_developer['github_username'],
                                'real_name': best_developer['name'],
                                'developer_id': best_developer['id'],
                                'source_type': dev_status['source_type'],
                                'category': category_str_normalized,
                                'confidence': confidence,
                                'assignment_score': best_score,
                                'assignment_reasoning': reasoning,
                                'github_profile': f"[https://github.com/](https://github.com/){best_developer['github_username']}",
                                'real_contributions': dev_status['contributions'],
                                'is_real_developer': True,
                                'github_assigned': github_assigned
                            }
                            
                            pipeline_state["assignments"].append(assignment)
                            
                            # Update workload
                            dev_status['workload'] += 1
                            dev_status['current_issues'].append(issue.number)
                            
                            # Update developer in list
                            for dev in pipeline_state["developers"]:
                                if dev["id"] == best_developer['id']:
                                    dev["workload"] = dev_status['workload']
                                    dev["current_issues"] = dev_status['current_issues']
                                    break
                        else:
                            print(f"    ⚠️ Developer {best_developer_id} not found in list")
                    else:
                        print(f"    ❌ No suitable developer found by assignment algorithm")
            
            # Show summary of all assignments
            if pipeline_state["assignments"]:
                print(f"\n📊 Assignment Summary ({len(pipeline_state['assignments'])} total):")
                for assignment in pipeline_state["assignments"][-5:]: # Show last 5
                    print(f"    #{assignment['issue_number']}: {assignment['issue_title'][:50]}...")
                    print(f"      → {assignment['assigned_to']} ({assignment['source_type']}) - Score: {assignment['assignment_score']:.2f}")
            
            pipeline_state["last_updated"] = datetime.now().isoformat()
            
            # Wait before next check
            await asyncio.sleep(30)
            
        except Exception as e:
            print(f"❌ Error in monitoring: {e}")
            pipeline_state["error"] = str(e)
            await asyncio.sleep(10)

# API Endpoints
@app.get("/")
def read_root():
    """Root endpoint."""
    return {
        "message": "Smart Bug Triage API",
        "version": "1.0.0",
        "endpoints": [
            "/developers",
            "/assignments",
            "/status",
            "/start",
            "/stop"
        ]
    }

@app.post("/start")
async def start_pipeline(request: StartPipelineRequest, background_tasks: BackgroundTasks):
    """Start the bug triage pipeline for a repository."""
    try:
        if pipeline_state["is_running"]:
            raise HTTPException(status_code=400, detail="Pipeline is already running")
        
        print(f"🚀 Starting pipeline for repository: {request.repo_name}")
        
        # Fetch developers
        developers, statuses = fetch_developers_and_collaborators(request.repo_name)
        
        if not developers:
            raise Exception("No developers found in repository")
        
        print(f"✅ Loaded {len(developers)} developers")
        
        pipeline_state["developers"] = developers
        pipeline_state["developer_statuses"] = statuses
        pipeline_state["current_repo"] = request.repo_name
        pipeline_state["is_running"] = True
        pipeline_state["assignments"] = []  # Clear previous assignments
        pipeline_state["processed_issues"] = set()  # Clear processed issues
        pipeline_state["last_updated"] = datetime.now().isoformat()
        pipeline_state["error"] = None
        
        # Start background monitoring task
        background_tasks.add_task(monitor_issues_background)
        
        return {
            "success": True,
            "message": f"Pipeline started for {request.repo_name}",
            "developers_loaded": len(developers)
        }
        
    except Exception as e:
        print(f"❌ Error starting pipeline: {e}")
        import traceback
        traceback.print_exc()
        pipeline_state["error"] = str(e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop")
async def stop_pipeline():
    """Stop the bug triage pipeline."""
    pipeline_state["is_running"] = False
    return {"success": True, "message": "Pipeline stopped"}

@app.get("/developers", response_model=List[Developer])
async def get_developers():
    """Get all available developers."""
    return pipeline_state["developers"]

@app.get("/assignments", response_model=List[Assignment])
async def get_assignments():
    """Get all issue assignments."""
    return pipeline_state["assignments"]

@app.get("/status", response_model=SystemStatus)
async def get_status():
    """Get system status and statistics."""
    developers = pipeline_state["developers"]
    
    contributors_count = sum(1 for d in developers if d["source_type"] in ['Contributor', 'Both'])
    collaborators_count = sum(1 for d in developers if d["source_type"] in ['Collaborator', 'Both'])
    both_count = sum(1 for d in developers if d["source_type"] == 'Both')
    
    return SystemStatus(
        is_running=pipeline_state["is_running"],
        current_repo=pipeline_state["current_repo"],
        total_developers=len(developers),
        total_assignments=len(pipeline_state["assignments"]),
        contributors_count=contributors_count,
        collaborators_count=collaborators_count,
        both_count=both_count,
        last_updated=pipeline_state["last_updated"],
        error=pipeline_state["error"]
    )

@app.post("/chat")
async def chat_with_gemini(request: dict):
    """
    Simple Gemini chat endpoint - ask questions and get answers
    
    Example request:
    POST /chat
    {
        "question": "What is the best way to implement authentication in a web app?"
    }
    """
    try:
        question = request.get("question", "").strip()
        
        if not question:
            raise HTTPException(status_code=400, detail="Question is required")
        
        if not pipeline_state.get("gemini_api_key"):
            raise HTTPException(status_code=500, detail="Gemini API key not configured")
        
        # Create a simple chat prompt
        prompt = f"""You are a helpful software development assistant. Please answer the following question clearly and concisely:

Question: {question}

Please provide a helpful, accurate, and practical answer. If it's a technical question, include relevant examples or code snippets when appropriate."""

        # API request payload
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 1500,
            }
        }

        # Make API call to Gemini
        url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){pipeline_state['gemini_api_key']}"
        
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            response_data = response.json()
            
            if "candidates" in response_data and response_data["candidates"]:
                try:
                    candidate = response_data["candidates"][0]
                    
                    # Extract text from response
                    answer = None
                    if "content" in candidate and "parts" in candidate["content"]:
                        if candidate["content"]["parts"] and "text" in candidate["content"]["parts"][0]:
                            answer = candidate["content"]["parts"][0]["text"]
                    elif "text" in candidate:
                        answer = candidate["text"]
                    
                    if answer:
                        return {
                            "question": question,
                            "answer": answer,
                            "timestamp": datetime.now().isoformat(),
                            "status": "success"
                        }
                    else:
                        raise HTTPException(status_code=500, detail="Could not extract answer from Gemini response")
                        
                except (KeyError, IndexError, TypeError) as e:
                    raise HTTPException(status_code=500, detail=f"Error parsing Gemini response: {e}")
            else:
                raise HTTPException(status_code=500, detail="No response from Gemini API")
        else:
            raise HTTPException(status_code=500, detail=f"Gemini API error: {response.status_code}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Smart Bug Triage API Server...")
    print("📡 API will be available at http://localhost:8000")
    print("📚 API Documentation at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)