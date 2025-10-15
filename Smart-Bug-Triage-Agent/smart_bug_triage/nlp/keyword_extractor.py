"""
Keyword extraction and technical term identification for bug reports.
Extracts relevant keywords and technical terms to help with classification and assignment.
"""

import re
import spacy
from typing import List, Dict, Set, Tuple, Any
from collections import Counter, defaultdict
import logging

logger = logging.getLogger(__name__)


class KeywordExtractor:
    """Extracts keywords and technical terms from bug reports."""
    
    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize the keyword extractor.
        
        Args:
            model_name: Name of the spaCy model to use
        """
        try:
            self.nlp = spacy.load(model_name)
        except OSError:
            logger.warning(f"Model {model_name} not found, using blank model")
            self.nlp = spacy.blank("en")
        
        # Technical term patterns
        self.technical_patterns = self._get_technical_patterns()
        
        # Programming language patterns
        self.language_patterns = self._get_language_patterns()
        
        # Framework and library patterns
        self.framework_patterns = self._get_framework_patterns()
    
    def _get_technical_patterns(self) -> Dict[str, List[str]]:
        """Get patterns for technical terms by category."""
        return {
            'web_technologies': [
                'html', 'css', 'javascript', 'js', 'typescript', 'ts',
                'http', 'https', 'rest', 'api', 'graphql', 'json', 'xml',
                'ajax', 'fetch', 'xhr', 'websocket', 'sse'
            ],
            'databases': [
                'sql', 'mysql', 'postgresql', 'postgres', 'sqlite', 'mongodb',
                'redis', 'elasticsearch', 'database', 'db', 'table', 'schema',
                'query', 'index', 'migration', 'orm', 'nosql'
            ],
            'frameworks': [
                'react', 'vue', 'angular', 'svelte', 'django', 'flask',
                'express', 'fastapi', 'spring', 'laravel', 'rails',
                'nextjs', 'nuxt', 'gatsby', 'webpack', 'vite'
            ],
            'infrastructure': [
                'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'heroku',
                'nginx', 'apache', 'server', 'deployment', 'ci/cd',
                'jenkins', 'github actions', 'gitlab ci', 'terraform'
            ],
            'testing': [
                'test', 'testing', 'unit test', 'integration test', 'e2e',
                'jest', 'mocha', 'pytest', 'junit', 'selenium', 'cypress',
                'mock', 'stub', 'fixture', 'assertion', 'coverage'
            ],
            'security': [
                'security', 'authentication', 'authorization', 'oauth',
                'jwt', 'token', 'session', 'csrf', 'xss', 'sql injection',
                'encryption', 'ssl', 'tls', 'certificate', 'vulnerability'
            ],
            'performance': [
                'performance', 'optimization', 'cache', 'caching', 'memory',
                'cpu', 'load', 'latency', 'throughput', 'bottleneck',
                'profiling', 'monitoring', 'metrics', 'benchmark'
            ]
        }
    
    def _get_language_patterns(self) -> List[str]:
        """Get programming language patterns."""
        return [
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#',
            'php', 'ruby', 'go', 'rust', 'swift', 'kotlin', 'scala',
            'r', 'matlab', 'shell', 'bash', 'powershell', 'sql'
        ]
    
    def _get_framework_patterns(self) -> Dict[str, List[str]]:
        """Get framework and library patterns by language."""
        return {
            'python': [
                'django', 'flask', 'fastapi', 'pandas', 'numpy', 'scipy',
                'tensorflow', 'pytorch', 'sklearn', 'requests', 'celery'
            ],
            'javascript': [
                'react', 'vue', 'angular', 'node', 'express', 'lodash',
                'jquery', 'bootstrap', 'tailwind', 'd3', 'three'
            ],
            'java': [
                'spring', 'hibernate', 'junit', 'maven', 'gradle',
                'jackson', 'apache', 'tomcat', 'jetty'
            ],
            'php': [
                'laravel', 'symfony', 'codeigniter', 'composer',
                'doctrine', 'twig', 'phpunit'
            ]
        }
    
    def extract_technical_terms(self, text: str) -> Dict[str, List[str]]:
        """
        Extract technical terms from text by category.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping categories to lists of found terms
        """
        text_lower = text.lower()
        found_terms = defaultdict(list)
        
        # Extract by technical categories
        for category, terms in self.technical_patterns.items():
            for term in terms:
                # Use word boundaries for exact matches
                pattern = rf'\b{re.escape(term)}\b'
                if re.search(pattern, text_lower):
                    found_terms[category].append(term)
        
        # Extract programming languages
        languages = []
        for lang in self.language_patterns:
            pattern = rf'\b{re.escape(lang)}\b'
            if re.search(pattern, text_lower):
                languages.append(lang)
        if languages:
            found_terms['programming_languages'] = languages
        
        # Extract frameworks by language context
        for lang, frameworks in self.framework_patterns.items():
            if lang in languages:
                for framework in frameworks:
                    pattern = rf'\b{re.escape(framework)}\b'
                    if re.search(pattern, text_lower):
                        if 'frameworks' not in found_terms:
                            found_terms['frameworks'] = []
                        found_terms['frameworks'].append(framework)
        
        return dict(found_terms)
    
    def extract_error_patterns(self, text: str) -> List[Dict[str, str]]:
        """
        Extract error patterns and stack traces.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of error pattern dictionaries
        """
        errors = []
        
        # Common error patterns
        error_patterns = [
            (r'(\w*Error|\w*Exception):\s*(.+)', 'exception'),
            (r'HTTP\s+(\d{3})\s*:?\s*(.+)', 'http_error'),
            (r'Error\s+(\d+)\s*:?\s*(.+)', 'error_code'),
            (r'Fatal\s+error:\s*(.+)', 'fatal_error'),
            (r'Warning:\s*(.+)', 'warning'),
            (r'Notice:\s*(.+)', 'notice'),
            (r'Traceback.*?(?=\n\n|\Z)', 'traceback'),
            (r'at\s+[\w.]+\([\w./]+:\d+:\d+\)', 'stack_trace_line')
        ]
        
        for pattern, error_type in error_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                error_info = {
                    'type': error_type,
                    'text': match.group(0),
                    'location': (match.start(), match.end())
                }
                
                # Extract additional details for specific error types
                if error_type == 'exception' and len(match.groups()) >= 2:
                    error_info['exception_type'] = match.group(1)
                    error_info['message'] = match.group(2)
                elif error_type == 'http_error':
                    error_info['status_code'] = match.group(1)
                    error_info['message'] = match.group(2) if len(match.groups()) >= 2 else ''
                
                errors.append(error_info)
        
        return errors
    
    def extract_file_references(self, text: str) -> List[Dict[str, str]]:
        """
        Extract file paths and references.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of file reference dictionaries
        """
        file_refs = []
        
        # File path patterns
        file_patterns = [
            (r'[A-Za-z]:\\[^\s<>""|?*]+', 'windows_path'),
            (r'/[^\s<>""|?*]+\.[a-zA-Z0-9]+', 'unix_path'),
            (r'[\w./]+\.(?:py|js|ts|java|php|rb|go|rs|cpp|c|h|css|html|json|xml|yml|yaml|md|txt)', 'file_extension'),
            (r'src/[\w./]+', 'source_path'),
            (r'test/[\w./]+|tests/[\w./]+', 'test_path'),
            (r'node_modules/[\w./]+', 'dependency_path')
        ]
        
        for pattern, ref_type in file_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                file_refs.append({
                    'type': ref_type,
                    'path': match.group(0),
                    'location': (match.start(), match.end())
                })
        
        return file_refs
    
    def extract_version_numbers(self, text: str) -> List[Dict[str, str]]:
        """
        Extract version numbers and identifiers.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of version dictionaries
        """
        versions = []
        
        # Version patterns
        version_patterns = [
            (r'v?\d+\.\d+\.\d+(?:-[a-zA-Z0-9]+)?', 'semantic_version'),
            (r'version\s+(\d+\.\d+(?:\.\d+)?)', 'version_number'),
            (r'build\s+(\d+)', 'build_number'),
            (r'commit\s+([a-f0-9]{7,40})', 'commit_hash'),
            (r'tag\s+([\w.-]+)', 'tag')
        ]
        
        for pattern, version_type in version_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                versions.append({
                    'type': version_type,
                    'version': match.group(1) if len(match.groups()) >= 1 else match.group(0),
                    'location': (match.start(), match.end())
                })
        
        return versions
    
    def extract_keywords_by_importance(self, preprocessed_data: Dict[str, Any], top_k: int = 20) -> List[Tuple[str, float]]:
        """
        Extract keywords ranked by importance using TF-IDF-like scoring.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            top_k: Number of top keywords to return
            
        Returns:
            List of (keyword, score) tuples sorted by importance
        """
        # Get lemmatized tokens
        title_lemmas = preprocessed_data.get('title_lemmas', [])
        description_lemmas = preprocessed_data.get('description_lemmas', [])
        
        # Combine with higher weight for title
        all_tokens = title_lemmas * 3 + description_lemmas
        
        # Filter out common words and short tokens
        filtered_tokens = [
            token for token in all_tokens 
            if len(token) > 2 and token.isalpha()
        ]
        
        # Count frequencies
        token_counts = Counter(filtered_tokens)
        
        # Calculate scores (simple frequency-based for now)
        total_tokens = len(filtered_tokens)
        scored_keywords = []
        
        for token, count in token_counts.items():
            # Simple TF score
            tf_score = count / total_tokens
            
            # Boost technical terms
            boost = 1.0
            text_lower = preprocessed_data.get('full_text', '').lower()
            
            # Check if it's a technical term
            for category, terms in self.technical_patterns.items():
                if token in terms:
                    boost = 2.0
                    break
            
            # Check if it's a programming language
            if token in self.language_patterns:
                boost = 2.5
            
            final_score = tf_score * boost
            scored_keywords.append((token, final_score))
        
        # Sort by score and return top k
        scored_keywords.sort(key=lambda x: x[1], reverse=True)
        return scored_keywords[:top_k]
    
    def extract_all_keywords(self, preprocessed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract all types of keywords and terms from preprocessed bug data.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            
        Returns:
            Dictionary containing all extracted keywords and terms
        """
        full_text = preprocessed_data.get('full_text', '')
        
        return {
            'technical_terms': self.extract_technical_terms(full_text),
            'error_patterns': self.extract_error_patterns(full_text),
            'file_references': self.extract_file_references(full_text),
            'version_numbers': self.extract_version_numbers(full_text),
            'important_keywords': self.extract_keywords_by_importance(preprocessed_data),
            'entities': preprocessed_data.get('entities', {}),
            'summary': self._create_keyword_summary(preprocessed_data, full_text)
        }
    
    def _create_keyword_summary(self, preprocessed_data: Dict[str, Any], full_text: str) -> Dict[str, Any]:
        """
        Create a summary of the most relevant keywords for quick analysis.
        
        Args:
            preprocessed_data: Output from BugTextPreprocessor
            full_text: Full text of the bug report
            
        Returns:
            Summary dictionary
        """
        technical_terms = self.extract_technical_terms(full_text)
        important_keywords = self.extract_keywords_by_importance(preprocessed_data, 10)
        error_patterns = self.extract_error_patterns(full_text)
        
        # Get top technical categories
        top_categories = []
        for category, terms in technical_terms.items():
            if terms:
                top_categories.append(category)
        
        # Get primary programming language
        languages = technical_terms.get('programming_languages', [])
        primary_language = languages[0] if languages else None
        
        # Check for critical indicators
        has_errors = len(error_patterns) > 0
        has_stack_trace = any(error['type'] in ['traceback', 'stack_trace_line'] for error in error_patterns)
        
        return {
            'top_keywords': [kw for kw, _ in important_keywords[:5]],
            'technical_categories': top_categories[:3],
            'primary_language': primary_language,
            'has_errors': has_errors,
            'has_stack_trace': has_stack_trace,
            'complexity_indicators': {
                'technical_term_count': sum(len(terms) for terms in technical_terms.values()),
                'error_count': len(error_patterns),
                'keyword_diversity': len(set(kw for kw, _ in important_keywords))
            }
        }