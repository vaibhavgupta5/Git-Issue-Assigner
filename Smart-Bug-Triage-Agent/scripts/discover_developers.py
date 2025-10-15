#!/usr/bin/env python
"""Script to discover and create developer profiles from GitHub repositories."""

import sys
import os
import argparse
import logging
from typing import Optional

# Add the project root to the Python path
project_root = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, project_root)

# Load environment variables from .env file
env_file = os.path.join(project_root, '.env')
if os.path.exists(env_file):
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                # Remove quotes if present
                value = value.strip('"\'')
                os.environ[key] = value

from smart_bug_triage.agents.developer_discovery import DeveloperDiscoveryService
from smart_bug_triage.api.github_client import GitHubAPIClient
from smart_bug_triage.database.connection import DatabaseManager
from smart_bug_triage.config.settings import Settings


def setup_logging(level: str = "INFO"):
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('developer_discovery.log')
        ]
    )


def main():
    """Main function to run developer discovery."""
    parser = argparse.ArgumentParser(description='Discover developers from GitHub repositories')
    parser.add_argument('owner', nargs='?', help='Repository owner (GitHub username or organization)')
    parser.add_argument('repo', nargs='?', help='Repository name')
    parser.add_argument('--github-token', help='GitHub personal access token (or set GITHUB_TOKEN env var)')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                       help='Logging level')
    parser.add_argument('--dry-run', action='store_true', help='Show discovered developers without saving to database')
    parser.add_argument('--all', action='store_true', help='Discover from all configured repositories')
    
    args = parser.parse_args()
    
    # Set up logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    try:
        # Load settings
        settings = Settings(args.config)
        
        # Get GitHub token
        github_token = args.github_token or os.getenv('GITHUB_TOKEN') or settings.api_config.github_token
        if not github_token:
            logger.error("GitHub token is required. Set GITHUB_TOKEN environment variable or use --github-token")
            return 1
        
        # Validate settings
        if not settings.validate():
            logger.error("Configuration validation failed")
            return 1
        
        # Initialize components
        logger.info("Initializing GitHub client...")
        github_client = GitHubAPIClient(github_token)
        
        if not github_client.test_connection():
            logger.error("Failed to connect to GitHub API")
            return 1
        
        if not args.dry_run:
            logger.info("Initializing database connection...")
            db_manager = DatabaseManager(settings.database_config)
            
            if not db_manager.test_connection():
                logger.error("Failed to connect to database")
                return 1
        else:
            db_manager = None
        
        # Initialize discovery service
        logger.info("Initializing developer discovery service...")
        discovery_service = DeveloperDiscoveryService(
            github_client=github_client,
            db_manager=db_manager,
            settings=settings
        )
        
        # Determine repositories to scan
        repositories_to_scan = []
        
        if args.all or (not args.owner and not args.repo):
            # Use configured repositories
            if settings.developer_discovery_config.github_organization:
                org = settings.developer_discovery_config.github_organization
                if settings.developer_discovery_config.github_repositories:
                    for repo in settings.developer_discovery_config.github_repositories:
                        repositories_to_scan.append((org, repo))
                else:
                    logger.warning(f"GitHub organization '{org}' configured but no repositories specified")
            else:
                logger.error("No repositories configured. Set GITHUB_ORGANIZATION and GITHUB_REPOSITORIES in .env file")
                return 1
        else:
            # Use command line arguments
            if not args.owner or not args.repo:
                logger.error("Both owner and repo must be specified, or use --all for configured repositories")
                return 1
            repositories_to_scan.append((args.owner, args.repo))
        
        if not repositories_to_scan:
            logger.error("No repositories to scan")
            return 1
        
        logger.info(f"Will scan {len(repositories_to_scan)} repositories: {repositories_to_scan}")
        
        # Discover developers from all repositories
        all_contributors = []
        all_profiles = []
        
        for owner, repo in repositories_to_scan:
            logger.info(f"Discovering developers from {owner}/{repo}...")
            try:
                contributors = discovery_service.discover_repository_developers(owner, repo)
                
                if not contributors:
                    logger.warning(f"No active contributors found in {owner}/{repo}")
                    continue
                
                logger.info(f"Found {len(contributors)} active contributors in {owner}/{repo}")
                all_contributors.extend(contributors)
                
            except Exception as e:
                logger.error(f"Failed to discover developers from {owner}/{repo}: {e}")
                continue
        
        if not all_contributors:
            logger.warning("No active contributors found in any repository")
            return 0
        
        # Remove duplicates (same user might contribute to multiple repos)
        unique_contributors = {}
        for contributor in all_contributors:
            if contributor.username not in unique_contributors:
                unique_contributors[contributor.username] = contributor
            else:
                # Merge contribution data
                existing = unique_contributors[contributor.username]
                existing.commits_last_6_months += contributor.commits_last_6_months
                # Merge languages (combine counts)
                for lang, count in contributor.languages.items():
                    existing.languages[lang] = existing.languages.get(lang, 0) + count
        
        contributors = list(unique_contributors.values())
        logger.info(f"Found {len(contributors)} unique contributors across all repositories")
        
        # Analyze skills and create profiles
        for i, contributor in enumerate(contributors, 1):
            logger.info(f"Analyzing contributor {i}/{len(contributors)}: {contributor.username}")
            
            # Analyze skills
            skill_analysis = discovery_service.analyze_developer_skills(contributor)
            
            # Create profile
            profile = discovery_service.create_developer_profile(contributor, skill_analysis)
            all_profiles.append(profile)
            
        # Display all profiles
        print(f"\n{'='*60}")
        print(f"DISCOVERED DEVELOPER PROFILES")
        print(f"{'='*60}")
        
        for i, (profile, contributor) in enumerate(zip(all_profiles, contributors), 1):
            # Get the skill analysis for display
            skill_analysis = discovery_service.analyze_developer_skills(contributor)
            
            print(f"\n--- Developer Profile {i} ---")
            print(f"Name: {profile.name}")
            print(f"GitHub Username: {profile.github_username}")
            print(f"Email: {profile.email}")
            print(f"Experience Level: {profile.experience_level}")
            print(f"Max Capacity: {profile.max_capacity}")
            print(f"Skills: {', '.join(profile.skills[:5])}{'...' if len(profile.skills) > 5 else ''}")
            print(f"Preferred Categories: {', '.join([cat.value for cat in profile.preferred_categories])}")
            print(f"Primary Languages: {', '.join(skill_analysis.primary_languages)}")
            print(f"Secondary Languages: {', '.join(skill_analysis.secondary_languages)}")
            print(f"Framework Skills: {', '.join(skill_analysis.framework_skills[:3])}{'...' if len(skill_analysis.framework_skills) > 3 else ''}")
            print(f"Confidence Score: {skill_analysis.confidence_score:.2f}")
            print(f"Contributions (6 months): {contributor.commits_last_6_months}")
            print(f"Languages: {dict(list(contributor.languages.items())[:3])}")
        
        if args.dry_run:
            print(f"\n--- Dry Run Complete ---")
            print(f"Discovered {len(all_profiles)} developer profiles")
            print("Use without --dry-run to save profiles to database")
            return 0
        
        # Save profiles to database
        logger.info("Saving developer profiles to database...")
        saved_count = 0
        
        for profile in all_profiles:
            if discovery_service.save_developer_to_database(profile):
                saved_count += 1
                logger.info(f"Saved profile for {profile.github_username}")
            else:
                logger.error(f"Failed to save profile for {profile.github_username}")
        
        print(f"\n--- Discovery Complete ---")
        print(f"Successfully saved {saved_count}/{len(all_profiles)} developer profiles to database")
        
        if saved_count < len(all_profiles):
            logger.warning(f"Failed to save {len(all_profiles) - saved_count} profiles")
            return 1
        
        return 0
        
    except KeyboardInterrupt:
        logger.info("Discovery interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Discovery failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())