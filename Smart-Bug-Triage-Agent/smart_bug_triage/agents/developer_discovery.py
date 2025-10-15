"""Developer discovery and management system."""

import logging
from typing import List, Dict, Optional, Set, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import json
import os

from ..api.github_client import GitHubAPIClient, GitHubUser
from ..models.common import DeveloperProfile, BugCategory
from ..models.database import Developer, DeveloperStatus
from ..database.connection import DatabaseManager
from ..config.settings import Settings


@dataclass
class ContributorStats:
    """Statistics for a repository contributor."""
    username: str
    user_id: int
    contributions: int
    commits_last_6_months: int
    languages: Dict[str, int]  # language -> lines of code
    files_touched: Set[str]
    last_activity: datetime
    email: Optional[str] = None
    name: Optional[str] = None


@dataclass
class SkillAnalysis:
    """Skill analysis results for a developer."""
    primary_languages: List[str]
    secondary_languages: List[str]
    framework_skills: List[str]
    experience_level: str
    estimated_categories: List[BugCategory]
    confidence_score: float


class DeveloperDiscoveryService:
    """Service for discovering and managing developers from GitHub repositories."""
    
    def __init__(self, github_client: GitHubAPIClient, db_manager: DatabaseManager, settings: Settings):
        """Initialize the developer discovery service.
        
        Args:
            github_client: GitHub API client
            db_manager: Database manager
            settings: Application settings
        """
        self.github_client = github_client
        self.db_manager = db_manager
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        
        # Load manual developer overrides if they exist
        self.manual_overrides = self._load_manual_overrides()
        
        # Language to skill mapping
        self.language_skills = {
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
            'json': ['JSON', 'API', 'Configuration']
        }
        
        # Framework detection patterns
        self.framework_patterns = {
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
            'kubernetes': ['Kubernetes', 'DevOps', 'Orchestration'],
            'terraform': ['Terraform', 'DevOps', 'Infrastructure'],
            'aws': ['AWS', 'Cloud', 'DevOps'],
            'gcp': ['GCP', 'Cloud', 'DevOps'],
            'azure': ['Azure', 'Cloud', 'DevOps']
        }
    
    def discover_repository_developers(self, owner: str, repo: str) -> List[ContributorStats]:
        """Discover developers from a GitHub repository.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            List of contributor statistics
        """
        self.logger.info(f"Discovering developers from {owner}/{repo}")
        
        try:
            # Get repository contributors
            contributors = self.github_client.get_repository_contributors(owner, repo)
            
            # Get detailed stats for each contributor
            contributor_stats = []
            for contributor in contributors:
                stats = self._analyze_contributor(owner, repo, contributor)
                if stats:
                    contributor_stats.append(stats)
            
            # Filter active contributors
            active_contributors = self._filter_active_contributors(contributor_stats)
            
            self.logger.info(f"Found {len(active_contributors)} active developers in {owner}/{repo}")
            return active_contributors
            
        except Exception as e:
            self.logger.error(f"Failed to discover developers from {owner}/{repo}: {e}")
            raise
    
    def _analyze_contributor(self, owner: str, repo: str, contributor: GitHubUser) -> Optional[ContributorStats]:
        """Analyze a single contributor's activity and skills.
        
        Args:
            owner: Repository owner
            repo: Repository name
            contributor: GitHub user information
            
        Returns:
            Contributor statistics or None if analysis fails
        """
        try:
            # Get contributor's commits in the repository
            repository = self.github_client.get_repository(owner, repo)
            
            # Get commits by this contributor in the last 6 months
            since_date = datetime.now() - timedelta(days=180)
            commits = repository.get_commits(author=contributor.login, since=since_date)
            
            # Analyze commits for language usage and file patterns
            languages = Counter()
            files_touched = set()
            commit_count = 0
            last_activity = None
            
            for commit in commits:
                commit_count += 1
                if last_activity is None or commit.commit.author.date > last_activity:
                    last_activity = commit.commit.author.date
                
                # Analyze files in the commit
                for file in commit.files:
                    files_touched.add(file.filename)
                    
                    # Determine language from file extension
                    file_ext = os.path.splitext(file.filename)[1].lower()
                    language = self._detect_language_from_extension(file_ext)
                    if language:
                        # Weight by lines added (approximate contribution)
                        lines_added = file.additions if file.additions else 0
                        languages[language] += lines_added
            
            # If no recent activity, skip this contributor
            if commit_count == 0:
                return None
            
            return ContributorStats(
                username=contributor.login,
                user_id=contributor.id,
                contributions=commit_count,
                commits_last_6_months=commit_count,
                languages=dict(languages),
                files_touched=files_touched,
                last_activity=last_activity or datetime.now(),
                email=contributor.email,
                name=contributor.name
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to analyze contributor {contributor.login}: {e}")
            return None
    
    def _detect_language_from_extension(self, extension: str) -> Optional[str]:
        """Detect programming language from file extension.
        
        Args:
            extension: File extension (e.g., '.py', '.js')
            
        Returns:
            Language name or None if not recognized
        """
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript',
            '.java': 'java',
            '.go': 'go',
            '.rs': 'rust',
            '.cpp': 'c++',
            '.cc': 'c++',
            '.cxx': 'c++',
            '.c': 'c',
            '.cs': 'c#',
            '.php': 'php',
            '.rb': 'ruby',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.dart': 'dart',
            '.html': 'html',
            '.htm': 'html',
            '.css': 'css',
            '.scss': 'css',
            '.sass': 'css',
            '.sql': 'sql',
            '.sh': 'shell',
            '.bash': 'shell',
            '.zsh': 'shell',
            '.dockerfile': 'dockerfile',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.xml': 'xml',
            '.md': 'markdown',
            '.rst': 'restructuredtext'
        }
        
        return extension_map.get(extension.lower())
    
    def _filter_active_contributors(self, contributors: List[ContributorStats]) -> List[ContributorStats]:
        """Filter contributors to find active developers.
        
        Args:
            contributors: List of all contributors
            
        Returns:
            List of active contributors
        """
        active_contributors = []
        
        for contributor in contributors:
            # Filter criteria for active developers
            is_active = (
                contributor.commits_last_6_months >= 5 and  # At least 5 commits in 6 months
                len(contributor.languages) > 0 and  # Has programming language activity
                contributor.last_activity > datetime.now() - timedelta(days=90)  # Active in last 3 months
            )
            
            if is_active:
                active_contributors.append(contributor)
        
        # Sort by contribution level (commits + language diversity)
        active_contributors.sort(
            key=lambda c: c.commits_last_6_months + len(c.languages),
            reverse=True
        )
        
        return active_contributors
    
    def analyze_developer_skills(self, contributor: ContributorStats) -> SkillAnalysis:
        """Analyze a developer's skills based on their contribution patterns.
        
        Args:
            contributor: Contributor statistics
            
        Returns:
            Skill analysis results
        """
        # Analyze primary and secondary languages
        total_lines = sum(contributor.languages.values())
        language_percentages = {
            lang: (lines / total_lines) * 100 
            for lang, lines in contributor.languages.items()
        }
        
        # Primary languages (>20% of code)
        primary_languages = [
            lang for lang, pct in language_percentages.items() 
            if pct >= 20.0
        ]
        
        # Secondary languages (5-20% of code)
        secondary_languages = [
            lang for lang, pct in language_percentages.items() 
            if 5.0 <= pct < 20.0
        ]
        
        # Extract skills from languages
        all_skills = set()
        for language in contributor.languages.keys():
            if language in self.language_skills:
                all_skills.update(self.language_skills[language])
        
        # Detect frameworks from file patterns
        framework_skills = self._detect_frameworks(contributor.files_touched)
        all_skills.update(framework_skills)
        
        # Estimate experience level based on contribution patterns
        experience_level = self._estimate_experience_level(contributor)
        
        # Map skills to bug categories
        estimated_categories = self._map_skills_to_categories(list(all_skills))
        
        # Calculate confidence score based on data quality
        confidence_score = self._calculate_skill_confidence(contributor, len(all_skills))
        
        return SkillAnalysis(
            primary_languages=primary_languages,
            secondary_languages=secondary_languages,
            framework_skills=framework_skills,
            experience_level=experience_level,
            estimated_categories=estimated_categories,
            confidence_score=confidence_score
        )
    
    def _detect_frameworks(self, files_touched: Set[str]) -> List[str]:
        """Detect frameworks and technologies from file patterns.
        
        Args:
            files_touched: Set of file paths
            
        Returns:
            List of detected frameworks
        """
        frameworks = set()
        
        for file_path in files_touched:
            file_lower = file_path.lower()
            
            # Check for framework-specific patterns
            for pattern, skills in self.framework_patterns.items():
                if pattern in file_lower:
                    frameworks.update(skills)
            
            # Check for specific configuration files
            if 'package.json' in file_lower:
                frameworks.add('Node.js')
            elif 'requirements.txt' in file_lower or 'pyproject.toml' in file_lower:
                frameworks.add('Python Package Management')
            elif 'pom.xml' in file_lower or 'build.gradle' in file_lower:
                frameworks.add('Java Build Tools')
            elif 'dockerfile' in file_lower:
                frameworks.add('Docker')
            elif 'docker-compose' in file_lower:
                frameworks.add('Docker Compose')
            elif '.github/workflows' in file_lower:
                frameworks.add('GitHub Actions')
        
        return list(frameworks)
    
    def _estimate_experience_level(self, contributor: ContributorStats) -> str:
        """Estimate developer experience level based on contribution patterns.
        
        Args:
            contributor: Contributor statistics
            
        Returns:
            Experience level (junior, mid, senior, lead, principal)
        """
        # Scoring factors
        commit_score = min(contributor.commits_last_6_months / 50, 1.0)  # Normalize to 0-1
        language_diversity = min(len(contributor.languages) / 5, 1.0)  # Normalize to 0-1
        file_diversity = min(len(contributor.files_touched) / 100, 1.0)  # Normalize to 0-1
        
        # Combined experience score
        experience_score = (commit_score * 0.4 + language_diversity * 0.3 + file_diversity * 0.3)
        
        # Map to experience levels
        if experience_score >= 0.8:
            return 'senior'
        elif experience_score >= 0.6:
            return 'mid'
        elif experience_score >= 0.4:
            return 'junior'
        elif experience_score >= 0.2:
            return 'junior'
        else:
            return 'junior'
    
    def _map_skills_to_categories(self, skills: List[str]) -> List[BugCategory]:
        """Map developer skills to bug categories.
        
        Args:
            skills: List of developer skills
            
        Returns:
            List of relevant bug categories
        """
        category_mapping = {
            BugCategory.FRONTEND: ['Frontend', 'JavaScript', 'TypeScript', 'React', 'Vue.js', 'Angular', 'HTML', 'CSS', 'UI/UX'],
            BugCategory.BACKEND: ['Backend', 'Python', 'Java', 'Go', 'C#', 'PHP', 'Ruby', 'API', 'Microservices'],
            BugCategory.DATABASE: ['Database', 'SQL', 'Data Analysis', 'Data Science'],
            BugCategory.API: ['API', 'Backend', 'Microservices', 'REST', 'GraphQL'],
            BugCategory.MOBILE: ['Mobile', 'iOS', 'Android', 'Swift', 'Kotlin', 'Flutter', 'Dart'],
            BugCategory.SECURITY: ['Security', 'Rust', 'Systems'],
            BugCategory.PERFORMANCE: ['Performance', 'Systems', 'Low Level', 'C++', 'Rust', 'Go']
        }
        
        relevant_categories = []
        for category, category_skills in category_mapping.items():
            # Check if developer has skills relevant to this category
            if any(skill in skills for skill in category_skills):
                relevant_categories.append(category)
        
        return relevant_categories if relevant_categories else [BugCategory.UNKNOWN]
    
    def _calculate_skill_confidence(self, contributor: ContributorStats, skill_count: int) -> float:
        """Calculate confidence score for skill analysis.
        
        Args:
            contributor: Contributor statistics
            skill_count: Number of detected skills
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Factors that increase confidence
        commit_factor = min(contributor.commits_last_6_months / 20, 1.0)
        language_factor = min(len(contributor.languages) / 3, 1.0)
        skill_factor = min(skill_count / 5, 1.0)
        recency_factor = 1.0 if contributor.last_activity > datetime.now() - timedelta(days=30) else 0.7
        
        # Combined confidence score
        confidence = (commit_factor * 0.3 + language_factor * 0.3 + skill_factor * 0.2 + recency_factor * 0.2)
        
        return min(confidence, 1.0)
    
    def create_developer_profile(self, contributor: ContributorStats, skill_analysis: SkillAnalysis) -> DeveloperProfile:
        """Create a developer profile from contributor data and skill analysis.
        
        Args:
            contributor: Contributor statistics
            skill_analysis: Skill analysis results
            
        Returns:
            Developer profile
        """
        # Check for manual overrides
        override = self.manual_overrides.get(contributor.username)
        
        # Build skills list
        skills = list(set(
            skill_analysis.primary_languages + 
            skill_analysis.secondary_languages + 
            skill_analysis.framework_skills
        ))
        
        # Apply manual overrides if they exist
        if override:
            skills = override.get('skills', skills)
            experience_level = override.get('experience_level', skill_analysis.experience_level)
            max_capacity = override.get('max_capacity', 10)
            preferred_categories = [
                BugCategory(cat) for cat in override.get('preferred_categories', [])
            ] or skill_analysis.estimated_categories
            name = override.get('name', contributor.name or contributor.username)
            email = override.get('email', contributor.email or f"{contributor.username}@example.com")
        else:
            experience_level = skill_analysis.experience_level
            max_capacity = self._estimate_max_capacity(skill_analysis.experience_level)
            preferred_categories = skill_analysis.estimated_categories
            name = contributor.name or contributor.username
            email = contributor.email or f"{contributor.username}@example.com"
        
        return DeveloperProfile(
            id=f"dev_{contributor.user_id}",
            name=name,
            github_username=contributor.username,
            email=email,
            skills=skills,
            experience_level=experience_level,
            max_capacity=max_capacity,
            preferred_categories=preferred_categories,
            timezone='UTC'  # Default timezone, can be overridden manually
        )
    
    def _estimate_max_capacity(self, experience_level: str) -> int:
        """Estimate maximum capacity based on experience level.
        
        Args:
            experience_level: Developer experience level
            
        Returns:
            Maximum capacity (number of concurrent issues)
        """
        capacity_map = {
            'junior': 5,
            'mid': 8,
            'senior': 12,
            'lead': 15,
            'principal': 20
        }
        
        return capacity_map.get(experience_level, 8)
    
    def save_developer_to_database(self, profile: DeveloperProfile) -> bool:
        """Save developer profile to database.
        
        Args:
            profile: Developer profile to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db_manager.get_session() as session:
                # Check if developer already exists
                existing = session.query(Developer).filter_by(
                    github_username=profile.github_username
                ).first()
                
                if existing:
                    # Update existing developer
                    existing.name = profile.name
                    existing.email = profile.email
                    existing.skills = profile.skills
                    existing.experience_level = profile.experience_level
                    existing.max_capacity = profile.max_capacity
                    existing.preferred_categories = [cat.value for cat in profile.preferred_categories]
                    existing.timezone = profile.timezone
                    existing.updated_at = datetime.now()
                    
                    self.logger.info(f"Updated existing developer: {profile.github_username}")
                else:
                    # Create new developer
                    developer = Developer(
                        id=profile.id,
                        name=profile.name,
                        github_username=profile.github_username,
                        email=profile.email,
                        skills=profile.skills,
                        experience_level=profile.experience_level,
                        max_capacity=profile.max_capacity,
                        preferred_categories=[cat.value for cat in profile.preferred_categories],
                        timezone=profile.timezone
                    )
                    
                    session.add(developer)
                    
                    # Create initial status record
                    status = DeveloperStatus(
                        developer_id=profile.id,
                        current_workload=0,
                        open_issues_count=0,
                        complexity_score=0.0,
                        availability='available',
                        calendar_free=True,
                        focus_time_active=False,
                        last_updated=datetime.now()
                    )
                    
                    session.add(status)
                    
                    self.logger.info(f"Created new developer: {profile.github_username}")
                
                session.commit()
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to save developer {profile.github_username}: {e}")
            return False
    
    def _load_manual_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Load manual developer configuration overrides.
        
        Returns:
            Dictionary of manual overrides keyed by GitHub username
        """
        override_file = os.path.join(self.settings.config_dir, 'developer_overrides.json')
        
        if os.path.exists(override_file):
            try:
                with open(override_file, 'r') as f:
                    overrides = json.load(f)
                self.logger.info(f"Loaded {len(overrides)} manual developer overrides")
                return overrides
            except Exception as e:
                self.logger.error(f"Failed to load developer overrides: {e}")
        
        return {}
    
    def save_manual_overrides(self, overrides: Dict[str, Dict[str, Any]]) -> bool:
        """Save manual developer configuration overrides.
        
        Args:
            overrides: Dictionary of overrides keyed by GitHub username
            
        Returns:
            True if successful, False otherwise
        """
        override_file = os.path.join(self.settings.config_dir, 'developer_overrides.json')
        
        try:
            # Ensure config directory exists
            os.makedirs(self.settings.config_dir, exist_ok=True)
            
            with open(override_file, 'w') as f:
                json.dump(overrides, f, indent=2)
            
            self.logger.info(f"Saved {len(overrides)} manual developer overrides")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save developer overrides: {e}")
            return False
    
    def discover_and_create_developers(self, owner: str, repo: str) -> List[DeveloperProfile]:
        """Complete workflow to discover and create developer profiles.
        
        Args:
            owner: Repository owner
            repo: Repository name
            
        Returns:
            List of created developer profiles
        """
        self.logger.info(f"Starting developer discovery for {owner}/{repo}")
        
        try:
            # Step 1: Discover contributors
            contributors = self.discover_repository_developers(owner, repo)
            
            # Step 2: Analyze skills and create profiles
            profiles = []
            for contributor in contributors:
                skill_analysis = self.analyze_developer_skills(contributor)
                profile = self.create_developer_profile(contributor, skill_analysis)
                
                # Step 3: Save to database
                if self.save_developer_to_database(profile):
                    profiles.append(profile)
                    self.logger.info(
                        f"Created developer profile: {profile.name} ({profile.github_username}) "
                        f"- Skills: {', '.join(profile.skills[:3])}{'...' if len(profile.skills) > 3 else ''}"
                    )
            
            self.logger.info(f"Successfully created {len(profiles)} developer profiles")
            return profiles
            
        except Exception as e:
            self.logger.error(f"Failed to discover and create developers: {e}")
            raise