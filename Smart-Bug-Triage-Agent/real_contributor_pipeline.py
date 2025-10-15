#!/usr/bin/env python
"""
REAL CONTRIBUTOR Bug Assignment Pipeline
======================================
This pipeline uses ACTUAL GitHub contributors from your repository,
not fake hardcoded developers!
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Add project to path
sys.path.insert(0, str(Path.cwd()))

def load_environment():
    """Load environment variables."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("✅ Environment loaded")
        return True
    except ImportError:
        print("⚠️  python-dotenv not installed, using existing environment")
        return True
    except Exception as e:
        print(f"❌ Failed to load environment: {e}")
        return False

class RealContributorBugPipeline:
    """Pipeline that uses REAL GitHub contributors from your repository."""
    
    def __init__(self):
        self.running = False
        self.assignments_made = []
        self.processed_issues = set()
        
    def fetch_collaborators(self, github_client, repo_name):
        """Fetch repository collaborators."""
        print("🔍 FETCHING REPOSITORY COLLABORATORS")
        print("-" * 50)
        
        try:
            repo = github_client.github.get_repo(repo_name)
            collaborators = list(repo.get_collaborators())
            
            print(f"✅ Found {len(collaborators)} collaborators")
            
            collaborator_data = {}
            for collab in collaborators:
                try:
                    user = github_client.github.get_user(collab.login)
                    collaborator_data[collab.login] = {
                        'user': user,
                        'permissions': collab.permissions,
                        'type': 'collaborator'
                    }
                    print(f"   → {collab.login} (Permissions: {collab.permissions})")
                except Exception as e:
                    print(f"   ⚠️  Could not fetch details for {collab.login}: {e}")
            
            return collaborator_data
            
        except Exception as e:
            print(f"❌ Error fetching collaborators: {e}")
            return {}
    
    def fetch_real_contributors(self, github_client, repo_name):
        """Fetch actual contributors from GitHub repository."""
        print("\n🔍 FETCHING REAL CONTRIBUTORS FROM REPOSITORY")
        print("-" * 50)
        
        try:
            repo = github_client.github.get_repo(repo_name)
            contributors = list(repo.get_contributors())
            
            print(f"✅ Found {len(contributors)} real contributors")
            
            contributor_data = {}
            for contributor in contributors:
                try:
                    user = github_client.github.get_user(contributor.login)
                    contributor_data[contributor.login] = {
                        'user': user,
                        'contributions': contributor.contributions,
                        'type': 'contributor'
                    }
                    print(f"   → {contributor.login} ({contributor.contributions} contributions)")
                except Exception as e:
                    print(f"   ⚠️  Could not fetch details for {contributor.login}: {e}")
            
            return contributor_data
            
        except Exception as e:
            print(f"❌ Error fetching contributors: {e}")
            return {}
    
    def merge_developers(self, github_client, contributor_data, collaborator_data):
        """Merge contributors and collaborators into a unified developer list."""
        print("\n🔗 MERGING CONTRIBUTORS AND COLLABORATORS")
        print("-" * 50)
        
        all_usernames = set(contributor_data.keys()) | set(collaborator_data.keys())
        
        real_developers = []
        developer_statuses = {}
        
        for username in all_usernames:
            try:
                # Determine source (contributor, collaborator, or both)
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
                    contributions = 0  # Collaborators may not have contributions yet
                
                # Analyze their repositories to guess skills
                skills = self.analyze_contributor_skills(user)
                
                # Create developer profile based on real data
                developer_id = f"real_{username}"
                
                # Determine experience level based on contributions
                if contributions >= 10:
                    experience = "Senior"
                    max_capacity = 5
                elif contributions >= 5:
                    experience = "Mid-level"
                    max_capacity = 4
                else:
                    experience = "Junior"
                    max_capacity = 3
                
                from smart_bug_triage.models.common import DeveloperProfile, BugCategory
                
                # Map skills to categories
                preferred_categories = []
                if any(skill in skills for skill in ['Python', 'Backend', 'Django', 'Flask']):
                    preferred_categories.append(BugCategory.BACKEND)
                if any(skill in skills for skill in ['JavaScript', 'React', 'Vue', 'HTML', 'CSS']):
                    preferred_categories.append(BugCategory.FRONTEND)
                if any(skill in skills for skill in ['Database', 'SQL', 'MongoDB']):
                    preferred_categories.append(BugCategory.DATABASE)
                if any(skill in skills for skill in ['API', 'REST', 'GraphQL']):
                    preferred_categories.append(BugCategory.API)
                
                if not preferred_categories:
                    preferred_categories = [BugCategory.BACKEND]  # Default
                
                developer = DeveloperProfile(
                    id=developer_id,
                    name=user.name or username,
                    github_username=username,
                    email=user.email or f"{username}@github.local",
                    skills=skills,
                    experience_level=experience,
                    max_capacity=max_capacity,
                    preferred_categories=preferred_categories,
                    timezone="UTC"
                )
                
                real_developers.append(developer)
                developer_statuses[developer_id] = {
                    "workload": 0,
                    "available": True,
                    "current_issues": [],
                    "contributions": contributions,
                    "source_type": source_type
                }
                
                print(f"   ✅ {username} ({source_type})")
                print(f"      Real Name: {user.name or 'Not provided'}")
                print(f"      Contributions: {contributions}")
                print(f"      Detected Skills: {', '.join(skills[:4])}...")
                print(f"      Experience Level: {experience}")
                print(f"      Max Capacity: {max_capacity}")
                print()
                
            except Exception as e:
                print(f"   ⚠️  Error processing {username}: {e}")
                continue
        
        print(f"✅ Total unified developers: {len(real_developers)}")
        return real_developers, developer_statuses
    
    def analyze_contributor_skills(self, user):
        """Analyze contributor's repositories to determine skills."""
        skills = set()
        
        try:
            # Get user's repositories
            repos = list(user.get_repos())[:10]  # Limit to avoid rate limits
            
            for repo in repos:
                # Analyze repository languages
                try:
                    languages = repo.get_languages()
                    for language in languages.keys():
                        if language == 'Python':
                            skills.update(['Python', 'Backend'])
                        elif language == 'JavaScript':
                            skills.update(['JavaScript', 'Frontend'])
                        elif language == 'Java':
                            skills.update(['Java', 'Backend'])
                        elif language == 'HTML':
                            skills.update(['HTML', 'Frontend'])
                        elif language == 'CSS':
                            skills.update(['CSS', 'Frontend'])
                        elif language == 'TypeScript':
                            skills.update(['TypeScript', 'Frontend'])
                        elif language in ['Shell', 'Dockerfile']:
                            skills.add('DevOps')
                        else:
                            skills.add(language)
                except:
                    continue
                
                # Analyze repository name and description for frameworks
                repo_text = f"{repo.name} {repo.description or ''}".lower()
                
                if any(framework in repo_text for framework in ['react', 'vue', 'angular']):
                    skills.update(['Frontend', 'React'])
                if any(framework in repo_text for framework in ['django', 'flask', 'fastapi']):
                    skills.update(['Backend', 'API'])
                if any(db in repo_text for db in ['database', 'sql', 'mongo']):
                    skills.add('Database')
                if any(api in repo_text for api in ['api', 'rest', 'graphql']):
                    skills.add('API')
                
        except Exception as e:
            print(f"   ⚠️  Could not analyze skills for {user.login}: {e}")
        
        # Default skills if none detected
        if not skills:
            skills = {'Python', 'Backend', 'General'}
        
        return list(skills)
    
    def display_all_developers(self, developers, developer_statuses):
        """Display all available developers in a formatted CLI table."""
        print("\n" + "=" * 110)
        print("👥 ALL AVAILABLE REAL CONTRIBUTORS & COLLABORATORS")
        print("=" * 110)
        
        # Header
        header = f"{'#':<3} {'GitHub Username':<20} {'Real Name':<20} {'Source':<14} {'Experience':<12} {'Capacity':<10} {'Skills':<25}"
        print(header)
        print("-" * 110)
        
        # Display each developer
        for idx, dev in enumerate(developers, 1):
            status = developer_statuses[dev.id]
            skills_display = ', '.join(dev.skills[:2])
            if len(dev.skills) > 2:
                skills_display += f" (+{len(dev.skills)-2})"
            
            source_icon = {
                "Both": "👤+🤝",
                "Contributor": "👤",
                "Collaborator": "🤝"
            }
            source_display = f"{source_icon.get(status['source_type'], '❓')} {status['source_type']}"
            
            row = f"{idx:<3} {dev.github_username:<20} {dev.name[:19]:<20} {source_display:<14} {dev.experience_level:<12} {status['workload']}/{dev.max_capacity:<8} {skills_display:<25}"
            print(row)
        
        print("-" * 110)
        
        # Show breakdown
        contributors_count = sum(1 for d in developers if developer_statuses[d.id]['source_type'] in ['Contributor', 'Both'])
        collaborators_count = sum(1 for d in developers if developer_statuses[d.id]['source_type'] in ['Collaborator', 'Both'])
        both_count = sum(1 for d in developers if developer_statuses[d.id]['source_type'] == 'Both')
        
        print(f"Total Developers: {len(developers)} | Contributors: {contributors_count} | Collaborators: {collaborators_count} | Both: {both_count}")
        print("=" * 110)
    
    def assign_issue_on_github(self, github_client, repo_name, issue, developer, category, confidence, assignment_score, source_type):
        """Actually assign the issue to a developer on GitHub."""
        try:
            repo = github_client.github.get_repo(repo_name)
            github_issue = repo.get_issue(issue.number)
            
            # Remove all existing assignees to ensure only one assignee
            current_assignees = [assignee.login for assignee in github_issue.assignees]
            if current_assignees:
                github_issue.remove_from_assignees(*current_assignees)
                print(f"      🗑️  Removed existing assignees: {', '.join(current_assignees)}")
            
            # 1. Assign the developer to the issue
            print(f"      📌 Assigning issue #{issue.number} to {developer.github_username} on GitHub...")
            github_issue.add_to_assignees(developer.github_username)
            
            # 2. Add a comment explaining the assignment
            source_emoji = {
                "Both": "👤+🤝 Contributor & Collaborator",
                "Contributor": "👤 Repository Contributor",
                "Collaborator": "🤝 Repository Collaborator"
            }
            
            comment_body = f"""🤖 **AI-Powered Bug Triage Assignment**

This issue has been automatically analyzed and assigned by our Smart Bug Triage Agent.

**Assignment Details:**
- 👤 **Assigned To:** @{developer.github_username} ({developer.name})
- 📝 **Role:** {source_emoji.get(source_type, source_type)}
- 🏷️ **Category:** {category}
- 🎯 **AI Confidence:** {confidence:.2%}
- 📊 **Assignment Score:** {assignment_score:.3f}
- 💼 **Experience Level:** {developer.experience_level}
- 🔧 **Relevant Skills:** {', '.join(developer.skills[:5])}

**Why this developer?**
This assignment was made based on:
- Skill match with issue category
- Current workload and capacity
- Experience level and contribution history
- AI analysis of issue content

---
*Generated by Smart Bug Triage Agent 🤖*
"""
            github_issue.create_comment(comment_body)
            print(f"      💬 Added assignment comment to issue")
            
            # 3. Add label to indicate AI assignment
            try:
                github_issue.add_to_labels("🤖 ai-assigned")
                print(f"      🏷️  Added 'ai-assigned' label")
            except Exception as label_error:
                print(f"      ⚠️  Could not add label (may not exist): {label_error}")
            
            print(f"      ✅ Successfully updated GitHub issue #{issue.number}")
            return True
            
        except Exception as e:
            print(f"      ❌ Failed to assign on GitHub: {e}")
            return False
    
    def run_real_contributor_pipeline(self):
        """Run pipeline with real contributors."""
        print("🎯 REAL CONTRIBUTOR BUG ASSIGNMENT PIPELINE")
        print("=" * 60)
        print("👨‍🎓 Student: Satvik Srivastava")
        print("🕒 Time:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("🎯 GOAL: Use REAL GitHub contributors (not fake ones!)")
        print("=" * 60)
        
        # Load environment
        if not load_environment():
            return False
        
        # Check GitHub token
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            print("❌ GITHUB_TOKEN not found in environment")
            return False
        
        try:
            print("\n🔧 STEP 1: INITIALIZING SYSTEM WITH REAL DATA")
            print("-" * 50)
            
            # Import required modules
            from smart_bug_triage.api.github_client import GitHubAPIClient
            from smart_bug_triage.models.common import BugReport
            from smart_bug_triage.nlp.pipeline import NLPPipeline
            
            # Initialize components
            github_client = GitHubAPIClient(token=github_token)
            nlp_pipeline = NLPPipeline()
            
            if not github_client.test_connection():
                print("❌ GitHub connection failed")
                return False
            
            print("✅ GitHub API connected")
            print("✅ NLP pipeline initialized")
            
            print("\n👥 STEP 2: LOADING REAL CONTRIBUTORS & COLLABORATORS")
            print("-" * 50)
            
            # Fetch repository name
            repo_name = "satvik-svg/Smart-Bug-Triage-Agent"
            
            # Fetch REAL contributors
            contributor_data = self.fetch_real_contributors(github_client, repo_name)
            
            # Fetch REAL collaborators
            collaborator_data = self.fetch_collaborators(github_client, repo_name)
            
            # Merge both lists
            developers, developer_statuses = self.merge_developers(
                github_client, contributor_data, collaborator_data
            )
            
            if not developers:
                print("❌ No real contributors or collaborators found!")
                return False
            
            print(f"\n✅ Loaded {len(developers)} REAL developers (contributors + collaborators)")
            
            # Display all developers in a formatted table
            self.display_all_developers(developers, developer_statuses)
            
            print("\n🔍 STEP 3: MONITORING WITH REAL CONTRIBUTORS & COLLABORATORS")
            print("-" * 50)
            print("Starting monitoring with REAL developer assignment...")
            print("Press Ctrl+C to stop")
            print()
            
            self.running = True
            iteration = 0
            
            # Set up signal handler
            import signal
            def signal_handler(signum, frame):
                print(f"\n⚠️  Shutting down...")
                self.running = False
            
            signal.signal(signal.SIGINT, signal_handler)
            
            while self.running:
                try:
                    iteration += 1
                    current_time = datetime.now().strftime("%H:%M:%S")
                    
                    print(f"🔄 [{current_time}] Developer Assignment Cycle #{iteration}")
                    
                    # Fetch GitHub issues
                    repo = github_client.github.get_repo(repo_name)
                    issues = list(repo.get_issues(state='open'))
                    
                    new_issues = []
                    for issue in issues:
                        issue_id = f"github_{issue.id}"
                        if issue_id not in self.processed_issues:
                            new_issues.append(issue)
                            self.processed_issues.add(issue_id)
                    
                    if new_issues:
                        print(f"   🆕 Found {len(new_issues)} new issues")
                        
                        for issue in new_issues:
                            print(f"\n   📋 Processing: #{issue.number} - {issue.title}")
                            
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
                            
                            # AI Analysis
                            analysis = nlp_pipeline.analyze_bug_report(bug_report.title, bug_report.description)
                            category = analysis.get('classification', {}).get('category', 'General')
                            confidence = analysis.get('classification', {}).get('confidence', 0.5)
                            
                            print(f"      🧠 AI Analysis: {category} (confidence: {confidence:.2f})")
                            
                            # Find best REAL contributor
                            best_developer = None
                            best_score = 0
                            
                            category_skills = {
                                'Backend/API': ['Python', 'Backend', 'API', 'Java'],
                                'Frontend/UI': ['JavaScript', 'Frontend', 'React', 'HTML', 'CSS'],
                                'Database': ['Database', 'Python', 'Backend'],
                                'Mobile': ['JavaScript', 'React'],
                                'General': ['Python', 'JavaScript']
                            }
                            
                            required_skills = category_skills.get(category, ['Python'])
                            
                            print(f"      🎯 Finding REAL developer for {category} issue...")
                            
                            for developer in developers:
                                status = developer_statuses[developer.id]
                                
                                if not status['available']:
                                    continue
                                
                                # Calculate skill match
                                skill_matches = sum(1 for skill in required_skills if skill in developer.skills)
                                skill_score = skill_matches / len(required_skills) if required_skills else 0
                                
                                # Workload score
                                workload_score = max(0, (developer.max_capacity - status['workload']) / developer.max_capacity)
                                
                                # Experience bonus
                                experience_bonus = 0.2 if developer.experience_level == "Senior" else 0.1
                                
                                # Contribution history bonus (real data!)
                                contribution_bonus = min(0.1, status['contributions'] / 100.0)
                                
                                # Final score
                                final_score = (skill_score * 0.5 + workload_score * 0.25 + 
                                             experience_bonus * 0.15 + contribution_bonus * 0.1)
                                
                                if final_score > best_score:
                                    best_score = final_score
                                    best_developer = developer
                            
                            # Make assignment to REAL contributor
                            if best_developer:
                                dev_status = developer_statuses[best_developer.id]
                                print(f"      ✅ ASSIGNED TO: {best_developer.github_username}")
                                print(f"         Real Name: {best_developer.name}")
                                print(f"         Source: {dev_status['source_type']}")
                                print(f"         Assignment Score: {best_score:.3f}")
                                print(f"         GitHub Profile: https://github.com/{best_developer.github_username}")
                                print(f"         Real Contributions: {dev_status['contributions']}")
                                
                                # Assign on GitHub
                                github_assigned = self.assign_issue_on_github(
                                    github_client, repo_name, issue, 
                                    best_developer, category, confidence, best_score,
                                    dev_status['source_type']
                                )
                                
                                # Create assignment record
                                assignment = {
                                    'timestamp': datetime.now().isoformat(),
                                    'issue_id': bug_report.id,
                                    'issue_number': issue.number,
                                    'issue_title': issue.title,
                                    'issue_url': issue.html_url,
                                    'assigned_to': best_developer.github_username,
                                    'real_name': best_developer.name,
                                    'developer_id': best_developer.id,
                                    'source_type': dev_status['source_type'],
                                    'category': category,
                                    'confidence': confidence,
                                    'assignment_score': best_score,
                                    'github_profile': f"https://github.com/{best_developer.github_username}",
                                    'real_contributions': dev_status['contributions'],
                                    'is_real_developer': True,
                                    'github_assigned': github_assigned
                                }
                                
                                self.assignments_made.append(assignment)
                                
                                # Update workload
                                developer_statuses[best_developer.id]['workload'] += 1
                                developer_statuses[best_developer.id]['current_issues'].append(issue.number)
                                
                            else:
                                print(f"      ❌ No suitable developer available")
                    
                    else:
                        print(f"   📊 No new issues found")
                    
                    # Show statistics with REAL contributors
                    print(f"   📈 Assignments to REAL developers: {len(self.assignments_made)}")
                    
                    print(f"   👥 Developer Status:")
                    for dev in developers:
                        status = developer_statuses[dev.id]
                        issues = ', '.join([f"#{n}" for n in status['current_issues']]) if status['current_issues'] else "None"
                        source_icon = "👤+🤝" if status['source_type'] == "Both" else ("👤" if status['source_type'] == "Contributor" else "🤝")
                        print(f"      {source_icon} {dev.github_username} ({status['contributions']} commits): {status['workload']}/{dev.max_capacity} (Issues: {issues})")
                    
                    print()
                    
                    if self.running:
                        time.sleep(30)
                    
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    print(f"❌ Error: {e}")
                    time.sleep(10)
            
            # Final results
            print(f"\n🎊 REAL DEVELOPER PIPELINE RESULTS")
            print("=" * 50)
            
            if self.assignments_made:
                print(f"✅ Assignments Made to REAL Developers: {len(self.assignments_made)}")
                print()
                
                for i, assignment in enumerate(self.assignments_made, 1):
                    print(f"Assignment {i}:")
                    print(f"   📋 Issue #{assignment['issue_number']}: {assignment['issue_title']}")
                    print(f"   👤 Developer: {assignment['assigned_to']} ({assignment['real_name']})")
                    print(f"   🔗 GitHub Profile: {assignment['github_profile']}")
                    print(f"   📊 Source: {assignment['source_type']}")
                    print(f"   📊 Real Contributions: {assignment['real_contributions']} commits")
                    print(f"   🏷️  Category: {assignment['category']}")
                    print(f"   🎯 Score: {assignment['assignment_score']:.3f}")
                    print(f"   ✅ Is Real Developer: {assignment['is_real_developer']}")
                    print(f"   🔗 Assigned on GitHub: {'✅ Yes' if assignment.get('github_assigned') else '❌ No'}")
                    print()
                
                print("🎉 SUCCESS: Used REAL developers from your repository!")
                print("   ✅ No fake developers")
                print("   ✅ Real GitHub profiles")
                print("   ✅ Real contribution history")
                print("   ✅ Skills analyzed from actual repositories")
                print("   ✅ Issues assigned on GitHub with AI comments")
                print("   ✅ Includes both contributors AND collaborators")
            
            else:
                print("📊 No new issues during monitoring, but REAL developers are loaded and ready!")
            
            return True
            
        except Exception as e:
            print(f"❌ Error in real contributor pipeline: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Main function."""
    pipeline = RealContributorBugPipeline()
    pipeline.run_real_contributor_pipeline()

if __name__ == "__main__":
    main()