#!/usr/bin/env python
"""Script to list your GitHub repositories."""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
env_file = project_root / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                value = value.strip('"\'')
                os.environ[key] = value

from smart_bug_triage.api.github_client import GitHubAPIClient

def main():
    """List GitHub repositories."""
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("❌ GITHUB_TOKEN not found in environment")
        return 1
    
    try:
        print("🔍 Fetching your GitHub repositories...")
        client = GitHubAPIClient(github_token)
        
        # Get authenticated user info
        response = client.get("/user")
        user_data = response.json()
        username = user_data['login']
        
        print(f"👤 GitHub User: {username}")
        print(f"📧 Email: {user_data.get('email', 'Not public')}")
        print(f"📝 Name: {user_data.get('name', 'Not set')}")
        
        # Get user's repositories
        print(f"\n📚 Your Repositories:")
        print("-" * 50)
        
        response = client.get("/user/repos", params={
            "type": "all",
            "sort": "updated",
            "per_page": 50
        })
        
        repos = response.json()
        
        if not repos:
            print("No repositories found")
            return 0
        
        for i, repo in enumerate(repos, 1):
            print(f"{i:2d}. {repo['full_name']}")
            print(f"    📝 {repo.get('description', 'No description')}")
            print(f"    🔗 {repo['html_url']}")
            print(f"    📅 Updated: {repo['updated_at'][:10]}")
            print(f"    🌟 Stars: {repo['stargazers_count']} | 🍴 Forks: {repo['forks_count']}")
            print(f"    📊 Language: {repo.get('language', 'Unknown')}")
            print(f"    {'🔒 Private' if repo['private'] else '🌍 Public'}")
            print()
        
        print(f"\n💡 To configure repositories for monitoring, update your .env file:")
        print(f"GITHUB_ORGANIZATION={username}")
        print(f"GITHUB_REPOSITORIES=repo1,repo2,repo3")
        
        # Show example configuration
        public_repos = [repo['name'] for repo in repos if not repo['private']][:3]
        if public_repos:
            print(f"\n📋 Example configuration with your repositories:")
            print(f"GITHUB_ORGANIZATION={username}")
            print(f"GITHUB_REPOSITORIES={','.join(public_repos)}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())